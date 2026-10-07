"""Game discovery and process execution manager for Productify Node."""

import os
import sys
import glob
import subprocess
import logging

logger = logging.getLogger("productify_node.game_detector")

DEFAULT_SEARCH_PATHS = [
    os.path.expanduser(r"~\Downloads"),
    os.path.expanduser(r"~\Desktop"),
    os.path.expanduser(r"~\Games"),
    r"C:\Games",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
]

ACTIVE_GAME_PROCESSES = {}


def find_game_executable(game_title, explicit_path=None):
    """Scan local host machine for the matching game executable."""
    if explicit_path and os.path.exists(explicit_path):
        return os.path.abspath(explicit_path)

    # Normalize search tokens
    clean_title = "".join(c.lower() for c in (game_title or "") if c.isalnum())
    tokens = [clean_title]
    if clean_title.endswith("s"):
        tokens.append(clean_title[:-1])
    else:
        tokens.append(clean_title + "s")

    # If generic title, look for known games present on the machine
    if clean_title in ("cloudgame", "game", "default", "productifygamezone", "generic", ""):
        tokens.extend(["stacklands", "stackland"])

    # Quick targeted glob check in Downloads
    if any("stackland" in t for t in tokens):
        for p in glob.glob(os.path.expanduser(r"~\Downloads\*stackland*\**\*.exe"), recursive=True):
            if "crash" not in p.lower() and "unins" not in p.lower() and os.path.exists(p):
                logger.info(f"Glob resolved Stacklands executable: {p}")
                return os.path.abspath(p)

    for base_dir in DEFAULT_SEARCH_PATHS:
        if not os.path.exists(base_dir):
            continue
        try:
            for root, dirs, files in os.walk(base_dir):
                # Don't recurse too deep into system directories
                depth = root[len(base_dir):].count(os.sep)
                if depth > 4:
                    continue

                for f in files:
                    if not f.lower().endswith(".exe"):
                        continue
                    if "crash" in f.lower() or "unins" in f.lower():
                        continue
                    fname_clean = "".join(c.lower() for c in os.path.splitext(f)[0] if c.isalnum())
                    for token in tokens:
                        if token in fname_clean or fname_clean in token:
                            full_path = os.path.join(root, f)
                            logger.info(f"Found matching game binary for '{game_title}': {full_path}")
                            return full_path
        except Exception as e:
            logger.debug(f"Error scanning {base_dir}: {e}")

    return None


def launch_game(game_title, session_id, explicit_path=None):
    """Launch the game process on Laptop A host and track PID."""
    exe_path = find_game_executable(game_title, explicit_path)
    if not exe_path:
        logger.warning(f"Could not find local executable for '{game_title}'")
        return {
            "ok": False,
            "error": f"Game executable for '{game_title}' not found on host machine.",
            "searched_paths": DEFAULT_SEARCH_PATHS,
        }

    game_dir = os.path.dirname(exe_path)
    logger.info(f"Launching '{game_title}' from: {exe_path} (cwd: {game_dir})")

    try:
        si = None
        if os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 4  # SW_SHOWNOACTIVATE
        proc = subprocess.Popen(
            [exe_path],
            cwd=game_dir,
            shell=False,
            startupinfo=si,
        )
        ACTIVE_GAME_PROCESSES[session_id] = {
            "session_id": session_id,
            "game_title": game_title,
            "pid": proc.pid,
            "process": proc,
            "exe_path": exe_path,
        }
        return {
            "ok": True,
            "pid": proc.pid,
            "exe_path": exe_path,
            "game_dir": game_dir,
        }
    except Exception as e:
        logger.error(f"Failed to launch game executable: {e}")
        return {"ok": False, "error": str(e)}


def stop_game(session_id):
    """Terminate the active game process for this session."""
    info = ACTIVE_GAME_PROCESSES.pop(session_id, None)
    if not info:
        return {"ok": True, "already_stopped": True}

    proc = info.get("process")
    pid = info.get("pid")
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    if os.name == "nt" and pid:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    logger.info(f"Stopped game process for session {session_id} (PID {pid})")
    return {"ok": True, "stopped_pid": pid}
