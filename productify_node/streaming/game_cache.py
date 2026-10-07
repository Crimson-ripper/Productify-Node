"""Cloudflare R2 High-Speed Game Downloader, Cache Manager, and Archive Unpacker."""

import os
import sys
import json
import time
import shutil
import zipfile
import tarfile
import urllib.request
import urllib.error
import logging
from productify_node.state import node_state

logger = logging.getLogger("productify_node.game_cache")

GAME_CACHE_ROOT = os.path.expanduser(os.path.join("~", ".productify", "game_cache"))


def ensure_cache_dir():
    os.makedirs(GAME_CACHE_ROOT, exist_ok=True)


def find_primary_executable(search_dir, preferred_rel_path=None):
    """Scan directory to locate the primary game launch executable."""
    if preferred_rel_path:
        cand = os.path.normpath(os.path.join(search_dir, preferred_rel_path))
        if os.path.isfile(cand):
            return cand

    # Candidate lists
    executables = []
    ignore_patterns = ["unins", "crash", "vcredist", "dxsetup", "setup", "update", "helper", "patcher", "unitycrashhandler", "eac_"]

    for root, dirs, files in os.walk(search_dir):
        for f in files:
            if f.lower().endswith(".exe"):
                fp = os.path.join(root, f)
                fn_lower = f.lower()
                is_ignored = any(p in fn_lower for p in ignore_patterns)
                if not is_ignored:
                    try:
                        sz = os.path.getsize(fp)
                        executables.append((fp, sz))
                    except Exception:
                        pass

    if executables:
        # Sort by file size descending (main game executables are typically largest)
        executables.sort(key=lambda x: -x[1])
        return executables[0][0]

    # Fallback to any executable found
    for root, dirs, files in os.walk(search_dir):
        for f in files:
            if f.lower().endswith(".exe"):
                return os.path.join(root, f)

    return None


class GameCacheManager:
    """Manages persistent caching of huge Cloudflare R2 game archives on host SSD."""

    def __init__(self):
        ensure_cache_dir()

    def get_game_cache_path(self, game_id):
        clean_id = "".join(c for c in game_id if c.isalnum() or c in ("-", "_"))
        return os.path.join(GAME_CACHE_ROOT, clean_id)

    def is_game_cached(self, game_id):
        target_dir = self.get_game_cache_path(game_id)
        marker_file = os.path.join(target_dir, "installed.json")
        if os.path.exists(marker_file):
            try:
                with open(marker_file, "r") as f:
                    data = json.load(f)
                exe_path = data.get("exe_path")
                if exe_path and os.path.exists(exe_path):
                    return True, exe_path, target_dir
            except Exception:
                pass
        return False, None, target_dir

    def ensure_game_ready(self, game_id, game_title, package_url=None, executable_rel_path=None):
        """Verify local cache or download and extract multi-GB archive from Cloudflare R2."""
        ensure_cache_dir()
        target_dir = self.get_game_cache_path(game_id)
        files_dir = os.path.join(target_dir, "files")

        # Check existing cache
        is_cached, cached_exe, _ = self.is_game_cached(game_id)
        if is_cached:
            node_state.log(f"Game '{game_title}' ({game_id}) found in SSD cache: {cached_exe}", "INFO")
            return {
                "ok": True,
                "cached": True,
                "exe_path": cached_exe,
                "game_dir": files_dir,
                "message": "Game launched from persistent host SSD cache."
            }

        if not package_url:
            node_state.log(f"No package URL or SSD cache available for game '{game_title}'", "WARNING")
            return {
                "ok": False,
                "error": f"No Cloudflare R2 package URL provided for '{game_title}'."
            }

        os.makedirs(files_dir, exist_ok=True)
        archive_path = os.path.join(target_dir, "package.download")

        node_state.log(f"Pulling game '{game_title}' from Cloudflare R2 into host cache...", "INFO")

        # Step 1: High-Speed Streaming Download from Cloudflare R2
        try:
            req = urllib.request.Request(
                package_url,
                headers={"User-Agent": "ProductifyNode-GameDownloader/1.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                total_size = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                last_log_time = time.time()
                chunk_size = 2 * 1024 * 1024  # 2MB chunks for max throughput

                with open(archive_path, "wb") as f_out:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        downloaded += len(chunk)

                        now = time.time()
                        if now - last_log_time > 3.0:
                            if total_size > 0:
                                pct = round((downloaded / total_size) * 100, 1)
                                mb = round(downloaded / (1024 * 1024), 1)
                                total_mb = round(total_size / (1024 * 1024), 1)
                                node_state.log(f"Downloading '{game_title}' from R2: {pct}% ({mb}/{total_mb} MB)", "INFO")
                            else:
                                mb = round(downloaded / (1024 * 1024), 1)
                                node_state.log(f"Downloading '{game_title}' from R2: {mb} MB fetched", "INFO")
                            last_log_time = now

            node_state.log(f"Finished downloading '{game_title}' package ({round(os.path.getsize(archive_path)/(1024*1024), 1)} MB). Unpacking...", "INFO")
        except Exception as e:
            if os.path.exists(archive_path):
                os.remove(archive_path)
            node_state.log(f"Cloudflare R2 download error for '{game_title}': {e}", "ERROR")
            return {"ok": False, "error": f"Download failed: {str(e)}"}

        # Step 2: Unpack archive into cache
        try:
            if zipfile.is_zipfile(archive_path):
                node_state.log(f"Extracting ZIP archive for '{game_title}'...", "INFO")
                with zipfile.ZipFile(archive_path, "r") as zf:
                    zf.extractall(files_dir)
            elif tarfile.is_tarfile(archive_path):
                node_state.log(f"Extracting TAR archive for '{game_title}'...", "INFO")
                with tarfile.open(archive_path, "r:*") as tf:
                    tf.extractall(files_dir)
            else:
                # If direct single binary, rename to executable
                target_exe_name = f"{game_id}.exe"
                shutil.copy2(archive_path, os.path.join(files_dir, target_exe_name))

            # Clean up the compressed archive to conserve host disk space
            if os.path.exists(archive_path):
                os.remove(archive_path)

            node_state.log(f"Unpacked '{game_title}' archive successfully.", "INFO")
        except Exception as ex:
            node_state.log(f"Failed to extract package for '{game_title}': {ex}", "ERROR")
            return {"ok": False, "error": f"Extraction error: {str(ex)}"}

        # Step 3: Locate primary game executable
        exe_path = find_primary_executable(files_dir, preferred_rel_path=executable_rel_path)
        if not exe_path:
            node_state.log(f"Could not locate an executable for '{game_title}' in {files_dir}", "WARNING")
            return {"ok": False, "error": "No game executable found in unpacked package."}

        # Step 4: Write cache marker
        marker_data = {
            "game_id": game_id,
            "game_title": game_title,
            "exe_path": exe_path,
            "installed_at": time.time(),
        }
        with open(os.path.join(target_dir, "installed.json"), "w") as f_meta:
            json.dump(marker_data, f_meta, indent=2)

        node_state.log(f"Game '{game_title}' cached and ready to play at: {exe_path}", "INFO")
        return {
            "ok": True,
            "cached": False,
            "exe_path": exe_path,
            "game_dir": files_dir,
            "message": "Game downloaded from Cloudflare R2 and installed in host SSD cache."
        }


game_cache_mgr = GameCacheManager()
