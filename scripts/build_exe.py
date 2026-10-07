"""Build standalone Windows .exe for Productify Node using PyInstaller."""

import os
import sys
import shutil
import subprocess

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    icon_path = os.path.join(root, "assets", "productify.ico")
    main_py = os.path.join(root, "main.py")

    import customtkinter
    ctk_dir = os.path.dirname(customtkinter.__file__)

    # Ensure icon exists
    if not os.path.exists(icon_path):
        from scripts.generate_icon import generate_ico_file
        generate_ico_file(icon_path)

    is_onefile = "--onedir" not in sys.argv

    print("[*] Starting PyInstaller compilation for Unified Productify Node...")
    print(f"[*] Icon: {icon_path}")
    print(f"[*] CustomTkinter dir: {ctk_dir}")
    print(f"[*] Mode: {'--onefile (Single Standalone Executable)' if is_onefile else '--onedir (Folder Distribution)'}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=ProductifyNode",
        "--noconfirm",
        "--clean",
        "--windowed",
        f"--icon={icon_path}",
        f"--add-data={ctk_dir};customtkinter",
        "--hidden-import=pystray",
        "--hidden-import=pystray._win32",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--hidden-import=PIL.ImageDraw",
        "--hidden-import=webview",
        "--hidden-import=clr_loader",
        "--hidden-import=pythonnet",
        "--hidden-import=customtkinter",
        "--hidden-import=productify_node",
        "--hidden-import=productify_node.thermal_guard",
        "--hidden-import=productify_node.tray",
        "--hidden-import=productify_node.bridge.local_server",
        "--hidden-import=productify_node.gui.webview_app",
        "--hidden-import=productify_node.gui.ctk_app",
        "--hidden-import=productify_node.container",
        "--hidden-import=productify_node.tunnel",
        "--hidden-import=productify_node.boundary",
        "--hidden-import=productify_node.telemetry",
        "--hidden-import=productify_node.auth",
        "--hidden-import=productify_node.config",
        "--hidden-import=productify_node.state",
        "--hidden-import=productify_node.streaming",
        "--hidden-import=productify_node.streaming.installer",
        "--hidden-import=productify_node.streaming.sunshine_mgr",
        "--hidden-import=productify_node.streaming.game_cache",
        "--hidden-import=productify_node.streaming.diagnostics",
        "--hidden-import=productify_node.streaming.game_detector",
        "--hidden-import=productify_node.streaming.input_injector",
        "--hidden-import=productify_node.streaming.webrtc_streamer",
    ]

    moonlight_bin_dir = os.path.join(root, "bin", "moonlight-web")
    if os.path.exists(moonlight_bin_dir):
        cmd.append(f"--add-data={moonlight_bin_dir};bin/moonlight-web")

    if is_onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    cmd.append(main_py)

    print("[*] Running command:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=root)
    if res.returncode == 0:
        print("\n" + "=" * 60)
        print("[SUCCESS] ProductifyNode.exe successfully built!")
        if is_onefile:
            exe_path = os.path.join(root, "dist", "ProductifyNode.exe")
            target_exe = os.path.join(root, "ProductifyNode.exe")
            try:
                shutil.copy2(exe_path, target_exe)
                print(f"[*] Copied executable to root: {target_exe}")
            except Exception as e:
                print(f"[!] Note: Could not copy to root: {e}")
            print(f"Standalone executable: {exe_path}")
        else:
            dist_dir = os.path.join(root, "dist", "ProductifyNode")
            exe_path = os.path.join(dist_dir, "ProductifyNode.exe")
            print(f"Distribution folder: {dist_dir}")
            print(f"Executable: {exe_path}")
        print("=" * 60)
    else:
        print("[ERROR] PyInstaller build failed.")
        sys.exit(res.returncode)


if __name__ == "__main__":
    main()
