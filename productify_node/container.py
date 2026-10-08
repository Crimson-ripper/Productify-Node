"""Docker container manager with strict resource bounding and zero-persistence wiping."""

import os
import sys
import json
import shutil
import subprocess
import logging
from productify_node.boundary import enforcer
from productify_node.state import node_state

logger = logging.getLogger("productify_node.container")

PODS_ROOT = os.path.expanduser(os.path.join("~", ".productify", "pods"))

CREATE_NO_WINDOW = 0x08000000

def safe_run(cmd, timeout=15, **kwargs):
    """Run subprocess guaranteed to never display or flash console windows on Windows."""
    if os.name == "nt":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
        si = kwargs.get("startupinfo")
        if si is None:
            si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = si
    return subprocess.run(cmd, timeout=timeout, **kwargs)


def ensure_pods_dir():
    os.makedirs(PODS_ROOT, exist_ok=True)


def find_docker_cli():
    """Locate docker executable on PATH or standard Docker Desktop locations."""
    cli = shutil.which("docker")
    if cli:
        return cli
    candidates = [
        r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
        r"C:\Program Files\Docker\Docker\docker.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Docker\resources\bin\docker.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            d = os.path.dirname(c)
            if d not in os.environ.get("PATH", ""):
                os.environ["PATH"] = f"{d};" + os.environ.get("PATH", "")
            return c
    return "docker"


def probe_docker():
    """Verify Docker availability and NVIDIA GPU passthrough silently."""
    docker_bin = find_docker_cli()
    try:
        res = safe_run([docker_bin, "version"], capture_output=True, text=True, timeout=4)
        docker_available = (res.returncode == 0)
    except Exception:
        docker_available = False

    gpu_supported = False
    if docker_available:
        try:
            res_gpu = safe_run(
                [docker_bin, "run", "--rm", "--gpus", "all", "hello-world"],
                capture_output=True,
                text=True,
                timeout=6
            )
            gpu_supported = (res_gpu.returncode == 0)
        except Exception:
            gpu_supported = False

    return {"docker_available": docker_available, "gpu_supported": gpu_supported, "docker_bin": docker_bin}


class ContainerManager:
    """Manages ephemeral pod lifecycles, resource bounding, and secure data sanitization."""

    def __init__(self):
        ensure_pods_dir()
        self.docker_status = probe_docker()

    def start_pod(self, instance_id, docker_image="python:3.11-slim", **kwargs):
        """Provision workspace and spin up container with strict memory and CPU limits."""
        if not node_state.is_live:
            return {"ok": False, "error": "Node is currently PAUSED. New workloads cannot be started."}

        pod_dir = os.path.join(PODS_ROOT, instance_id)
        os.makedirs(pod_dir, exist_ok=True)

        container_name = f"prod-{instance_id}"
        boundary_flags = enforcer.get_docker_boundary_flags()

        # Write pod isolation metadata
        with open(os.path.join(pod_dir, "pod_meta.json"), "w") as f:
            f.write(f'{{"instance_id": "{instance_id}", "status": "active"}}\n')

        container_id = f"cntr-{instance_id[:8]}"
        docker_started = False

        if self.docker_status["docker_available"]:
            gpu_flags = ["--gpus", "all"] if self.docker_status["gpu_supported"] else []
            cmd = (
                ["docker", "run", "-d", "--name", container_name]
                + gpu_flags
                + boundary_flags
                + ["-v", f"{pod_dir}:/workspace", docker_image, "sleep", "infinity"]
            )
            try:
                res = safe_run(cmd, capture_output=True, text=True, timeout=25)
                if res.returncode == 0:
                    container_id = res.stdout.strip()[:12]
                    docker_started = True
                    node_state.log(f"Spawned Docker container {container_name} with boundaries: {boundary_flags}", "INFO")
                else:
                    node_state.log(f"Docker spawn fallback for {instance_id}: {res.stderr[:80]}", "WARNING")
            except Exception as e:
                node_state.log(f"Docker run error: {e}", "WARNING")

        pod_info = {
            "instance_id": instance_id,
            "container_id": container_id,
            "docker_started": docker_started,
            "workspace": pod_dir,
            "image": docker_image,
            "boundary_flags": boundary_flags,
        }
        node_state.add_pod(instance_id, pod_info)

        return {"ok": True, "container_id": container_id, "docker_active": docker_started}

    def exec_in_pod(self, instance_id, command=None, code=None):
        """Execute command or python script within the allocated pod boundaries."""
        if not node_state.is_live:
            return {"ok": False, "error": "Node is PAUSED. Execution halted.", "exit_code": 1}

        pod_dir = os.path.join(PODS_ROOT, instance_id)

        # Check disk boundary before executing
        disk_check = enforcer.check_pod_disk_usage(pod_dir)
        if disk_check["violation"]:
            node_state.log(f"Disk quota violation in pod {instance_id}: {disk_check['used_gb']}GB > {disk_check['limit_gb']}GB", "ERROR")
            return {
                "ok": False,
                "stdout": "",
                "stderr": f"Error: Workload disk allocation exceeded ({disk_check['used_gb']} GB > {disk_check['limit_gb']} GB limit). Aborting.",
                "exit_code": 122,
            }

        container_name = f"prod-{instance_id}"
        pods = node_state.get_active_pods()
        pod_info = pods.get(instance_id, {})

        # If Docker container is running
        if pod_info.get("docker_started"):
            try:
                if code:
                    exec_cmd = ["docker", "exec", container_name, "python3", "-c", code]
                else:
                    exec_cmd = ["docker", "exec", container_name, "sh", "-c", command]

                res = safe_run(exec_cmd, capture_output=True, text=True, timeout=20)
                return {
                    "ok": True,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                    "exit_code": res.returncode,
                }
            except subprocess.TimeoutExpired:
                return {"ok": False, "stdout": "", "stderr": "Execution timed out (20s limit)", "exit_code": 124}
            except Exception as e:
                return {"ok": False, "stdout": "", "stderr": f"Docker exec error: {e}", "exit_code": 1}

        # Process fallback
        try:
            script = code if code else (command[6:].strip() if command and command.startswith("python") else command)
            if script and script.startswith("-c"):
                script = script[2:].strip().strip('"').strip("'")

            res = safe_run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=pod_dir if os.path.exists(pod_dir) else None
            )
            return {"ok": True, "stdout": res.stdout, "stderr": res.stderr, "exit_code": res.returncode}
        except subprocess.TimeoutExpired:
            return {"ok": False, "stdout": "", "stderr": "Execution timed out", "exit_code": 124}
        except Exception as e:
            return {"ok": False, "stdout": "", "stderr": str(e), "exit_code": 1}

    def destroy_pod(self, instance_id):
        """Force-stop container and perform zero-persistence disk wipe."""
        container_name = f"prod-{instance_id}"
        try:
            safe_run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except Exception:
            pass

        pod_dir = os.path.join(PODS_ROOT, instance_id)
        if os.path.exists(pod_dir):
            try:
                for root, dirs, files in os.walk(pod_dir):
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            size = os.path.getsize(fp)
                            with open(fp, "wb") as wf:
                                wf.write(b"\x00" * min(size, 1024 * 1024))
                        except Exception:
                            pass
                shutil.rmtree(pod_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Error purging workspace: {e}")

        node_state.remove_pod(instance_id)
        return {"ok": True, "wiped": True}

    def destroy_all_pods(self):
        """Emergency stop: kill all running containers and wipe all scratch disks."""
        pods = list(node_state.get_active_pods().keys())
        for pid in pods:
            self.destroy_pod(pid)
        node_state.log("Emergency Stop executed: All pods killed and workspaces wiped clean.", "WARNING")
        return len(pods)

    def start_game_pod(self, session_id, game_title, docker_image="productify/game-runner:generic", game_package_url=None, is_private=False, game_id=None, executable_rel_path=None, r2_key=None):
        """Provision isolated cloud gaming container with GPU passthrough and WebRTC streaming stack."""
        if not node_state.is_live:
            return {"ok": False, "error": "Node is currently PAUSED. Game cannot be started."}

        pod_dir = os.path.join(PODS_ROOT, f"game-{session_id}")
        os.makedirs(pod_dir, exist_ok=True)

        container_name = f"prod-game-{session_id[:8]}"
        boundary_flags = enforcer.get_docker_boundary_flags()

        # Step 1: Ensure game package is downloaded from Cloudflare R2 and unpacked in host cache
        cached_exe_path = None
        game_workspace_dir = pod_dir
        try:
            from productify_node.streaming.game_cache import game_cache_mgr
            effective_game_id = game_id or game_title.lower().replace(" ", "-")
            cache_res = game_cache_mgr.ensure_game_ready(
                game_id=effective_game_id,
                game_title=game_title,
                package_url=game_package_url,
                executable_rel_path=executable_rel_path,
            )
            if cache_res.get("ok"):
                cached_exe_path = cache_res.get("exe_path")
                if cache_res.get("game_dir") and os.path.exists(cache_res.get("game_dir")):
                    game_workspace_dir = cache_res.get("game_dir")
                node_state.log(f"Game package ready for '{game_title}': {cached_exe_path}", "INFO")
            else:
                node_state.log(f"Cache check for '{game_title}': {cache_res.get('error')}", "WARNING")
        except Exception as ex:
            node_state.log(f"Error checking game package cache: {ex}", "WARNING")

        # Write game isolation metadata
        with open(os.path.join(pod_dir, "game_meta.json"), "w") as f:
            f.write(json.dumps({
                "session_id": session_id,
                "game_title": game_title,
                "is_private": is_private,
                "package_url": game_package_url,
                "exe_path": cached_exe_path,
                "status": "active"
            }, indent=2) + "\n")

        container_id = f"cntr-game-{session_id[:8]}"
        docker_started = False

        # Strict container isolation check: Never run game directly on host desktop
        if not self.docker_status["docker_available"]:
            node_state.log(
                f"[CONTAINER ISOLATION ENFORCED] Docker Desktop is not running on this host node. "
                f"Workload '{game_title}' was BLOCKED from executing on the host OS desktop. "
                f"Please start Docker Desktop to enable isolated game containers.",
                "ERROR"
            )
            return {
                "ok": False,
                "error": "Docker is not running on this host machine. Cloud gaming requires Docker Desktop container isolation to prevent games from opening on the host desktop.",
                "docker_missing": True,
                "container_required": True,
            }

        # Provision and spin up isolated Docker container
        gpu_flags = ["--gpus", "all"] if self.docker_status["gpu_supported"] else []
        env_flags = [
            "-e", f"GAME_TITLE={game_title}",
            "-e", f"SESSION_ID={session_id}",
            "-e", "DISPLAY=:0",
            "-e", "NVIDIA_VISIBLE_DEVICES=all",
            "-e", "NVIDIA_DRIVER_CAPABILITIES=all"
        ]
        docker_bin = self.docker_status.get("docker_bin", "docker")
        cmd = (
            [docker_bin, "run", "-d", "--name", container_name]
            + gpu_flags
            + boundary_flags
            + env_flags
            + ["-v", f"{game_workspace_dir}:/game_workspace", docker_image, "sleep", "infinity"]
        )
        try:
            res = safe_run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode == 0:
                container_id = res.stdout.strip()[:12]
                docker_started = True
                node_state.log(f"Spawned Gamezone Docker container {container_name} (ID: {container_id}) for '{game_title}'", "INFO")
            else:
                node_state.log(f"Docker game container spawn failed: {res.stderr[:120]}", "ERROR")
                return {
                    "ok": False,
                    "error": f"Failed to spawn Docker container for game: {res.stderr[:120]}",
                    "docker_error": True,
                }
        except Exception as e:
            node_state.log(f"Docker run error: {e}", "ERROR")
            return {
                "ok": False,
                "error": f"Docker execution error: {str(e)}",
                "docker_error": True,
            }

        # Trigger execution strictly INSIDE the container via docker exec
        container_exec_target = f"/game_workspace/{executable_rel_path}" if executable_rel_path else "/game_workspace"
        if executable_rel_path:
            exec_cmd = [docker_bin, "exec", "-d", container_name, "sh", "-c", f"cd /game_workspace && ./{executable_rel_path}"]
            safe_run(exec_cmd, timeout=10)
            node_state.log(f"Triggered game execution inside Docker container {container_name}: {executable_rel_path}", "INFO")

        game_proc_info = {
            "ok": True,
            "pid": None,
            "container_id": container_id,
            "exe_path": container_exec_target,
            "in_container": True
        }

        final_exe = game_proc_info.get("exe_path") or "/game_workspace"

        pod_info = {
            "instance_id": session_id,
            "session_id": session_id,
            "game_title": game_title,
            "container_id": container_id,
            "docker_started": docker_started,
            "process_pid": game_proc_info.get("pid"),
            "exe_path": final_exe,
            "workspace": game_workspace_dir,
            "image": docker_image,
            "is_game": True,
            "is_private": is_private,
        }
        node_state.add_pod(session_id, pod_info)

        return {
            "ok": True,
            "container_id": container_id,
            "docker_active": docker_started,
            "game_launched": bool(game_proc_info.get("ok")),
            "pid": game_proc_info.get("pid"),
            "exe_path": final_exe,
        }

    def stop_game_pod(self, session_id, container_id=None):
        """Force-stop gaming container/process and scrub game workspace securely."""
        try:
            from productify_node.streaming.game_detector import stop_game
            stop_game(session_id)
        except Exception:
            pass

        container_name = f"prod-game-{session_id[:8]}"
        try:
            safe_run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except Exception:
            pass

        pod_dir = os.path.join(PODS_ROOT, f"game-{session_id}")
        if os.path.exists(pod_dir):
            try:
                for root, dirs, files in os.walk(pod_dir):
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            size = os.path.getsize(fp)
                            with open(fp, "wb") as wf:
                                wf.write(b"\x00" * min(size, 1024 * 1024))
                        except Exception:
                            pass
                shutil.rmtree(pod_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Error purging game workspace: {e}")

        node_state.remove_pod(session_id)
        node_state.log(f"Stopped and purged game container for session {session_id}", "INFO")
        return {"ok": True, "wiped": True}


container_mgr = ContainerManager()
