"""High-performance Win32 input injector for remote cloud gaming.

Translates browser WebRTC DataChannel events (mouse aim, clicks, keystrokes)
into native Windows OS input events via SendInput.
"""

import os
import sys
import ctypes
from ctypes import wintypes
import logging

logger = logging.getLogger("productify_node.input_injector")

# Win32 Constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

# Win32 C Structs
class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong),
    )

class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong),
    )

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )

class _INPUT_UNION(ctypes.Union):
    _fields_ = (
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    )

class INPUT(ctypes.Structure):
    _fields_ = (
        ("type", wintypes.DWORD),
        ("union", _INPUT_UNION),
    )

# Key Code to Win32 Virtual Key & Scan Code mapping
JS_CODE_TO_VK = {
    "KeyA": 0x41, "KeyB": 0x42, "KeyC": 0x43, "KeyD": 0x44, "KeyE": 0x45,
    "KeyF": 0x46, "KeyG": 0x47, "KeyH": 0x48, "KeyI": 0x49, "KeyJ": 0x4A,
    "KeyK": 0x4B, "KeyL": 0x4C, "KeyM": 0x4D, "KeyN": 0x4E, "KeyO": 0x4F,
    "KeyP": 0x50, "KeyQ": 0x51, "KeyR": 0x52, "KeyS": 0x53, "KeyT": 0x54,
    "KeyU": 0x55, "KeyV": 0x56, "KeyW": 0x57, "KeyX": 0x58, "KeyY": 0x59, "KeyZ": 0x5A,
    "Digit0": 0x30, "Digit1": 0x31, "Digit2": 0x32, "Digit3": 0x33, "Digit4": 0x34,
    "Digit5": 0x35, "Digit6": 0x36, "Digit7": 0x37, "Digit8": 0x38, "Digit9": 0x39,
    "Space": 0x20, "Enter": 0x0D, "Escape": 0x1B, "Backspace": 0x08, "Tab": 0x09,
    "ShiftLeft": 0xA0, "ShiftRight": 0xA1, "ControlLeft": 0xA2, "ControlRight": 0xA3,
    "AltLeft": 0x12, "AltRight": 0x12,
    "ArrowUp": 0x26, "ArrowDown": 0x28, "ArrowLeft": 0x25, "ArrowRight": 0x27,
}


class InputInjector:
    """Manages high-fidelity input synthesis for cloud gaming sessions."""

    def __init__(self):
        self.is_windows = (os.name == "nt")
        if self.is_windows:
            self.user32 = ctypes.windll.user32
            self.screen_width = self.user32.GetSystemMetrics(0)
            self.screen_height = self.user32.GetSystemMetrics(1)
        else:
            self.user32 = None
            self.screen_width = 1920
            self.screen_height = 1080

    def move_mouse_relative(self, dx, dy):
        """Relative mouse movement for first-person / locked cursor games."""
        if not self.is_windows:
            return
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dx = int(dx)
        inp.union.mi.dy = int(dy)
        inp.union.mi.dwFlags = MOUSEEVENTF_MOVE
        self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def move_mouse_absolute(self, norm_x, norm_y):
        """Absolute mouse placement (0.0 to 1.0) for point-and-click / card games like Stacklands."""
        if not self.is_windows:
            return
        # Map 0.0 - 1.0 to 0 - 65535 for MOUSEEVENTF_ABSOLUTE
        abs_x = int(max(0.0, min(1.0, norm_x)) * 65535)
        abs_y = int(max(0.0, min(1.0, norm_y)) * 65535)

        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dx = abs_x
        inp.union.mi.dy = abs_y
        inp.union.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
        self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def mouse_button(self, button, down):
        """Simulate mouse button press or release (0=left, 1=middle, 2=right)."""
        if not self.is_windows:
            return
        flags = 0
        if button == 0:
            flags = MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP
        elif button == 2:
            flags = MOUSEEVENTF_RIGHTDOWN if down else MOUSEEVENTF_RIGHTUP
        elif button == 1:
            flags = MOUSEEVENTF_MIDDLEDOWN if down else MOUSEEVENTF_MIDDLEUP

        if flags:
            inp = INPUT()
            inp.type = INPUT_MOUSE
            inp.union.mi.dwFlags = flags
            self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def mouse_wheel(self, delta_y):
        """Simulate vertical mouse scroll wheel."""
        if not self.is_windows:
            return
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dwFlags = MOUSEEVENTF_WHEEL
        inp.union.mi.mouseData = int(delta_y)
        self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def key_event(self, code, down):
        """Simulate keyboard key press or release."""
        if not self.is_windows:
            return
        vk = JS_CODE_TO_VK.get(code)
        if not vk:
            return

        scan_code = self.user32.MapVirtualKeyW(vk, 0)
        flags = 0
        if not down:
            flags |= KEYEVENTF_KEYUP
        if scan_code > 0:
            flags |= KEYEVENTF_SCANCODE

        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = vk
        inp.union.ki.wScan = scan_code
        inp.union.ki.dwFlags = flags
        self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def dispatch(self, event):
        """Dispatch JSON event from WebRTC DataChannel to native OS input."""
        evt_type = event.get("t") or event.get("type")
        if not evt_type:
            return

        try:
            if evt_type == "mm":  # Relative Mouse Move
                self.move_mouse_relative(event.get("dx", 0), event.get("dy", 0))
            elif evt_type == "ma":  # Absolute Mouse Move (0.0 to 1.0)
                self.move_mouse_absolute(event.get("x", 0.5), event.get("y", 0.5))
            elif evt_type == "mb":  # Mouse Button
                self.mouse_button(event.get("b", 0), event.get("d", False))
            elif evt_type == "mw":  # Mouse Wheel
                self.mouse_wheel(event.get("dy", 0))
            elif evt_type == "k":   # Keyboard Key
                self.key_event(event.get("c", ""), event.get("d", False))
        except Exception as e:
            logger.debug(f"Input dispatch error: {e}")


injector = InputInjector()
