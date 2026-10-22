"""Simulate the knob box: send F13-F24 key taps via SendInput.

Usage: python sendkey.py F14 [count]     e.g.  python sendkey.py F14 5
       python sendkey.py F21 hold        (hold for 1.5 s with auto-repeat)
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

KEYEVENTF_KEYUP = 0x2


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("_pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def send(vk, flags):
    ev = INPUT(type=1)  # INPUT_KEYBOARD
    ev.ki = KEYBDINPUT(vk, 0, flags, 0, 0)
    ctypes.windll.user32.SendInput(1, ctypes.byref(ev), ctypes.sizeof(INPUT))


def hold(vk, seconds):
    """Hold a key like a person would: key-down auto-repeating every 33 ms."""
    end = time.monotonic() + seconds
    send(vk, 0)
    time.sleep(0.5)
    while time.monotonic() < end:
        send(vk, 0)
        time.sleep(0.033)
    send(vk, KEYEVENTF_KEYUP)


if __name__ == "__main__":
    n = int(sys.argv[1].upper().lstrip("F"))
    if not 13 <= n <= 24:
        sys.exit("only F13-F24")
    vk = 0x7C + n - 13
    if len(sys.argv) > 2 and sys.argv[2] == "hold":
        hold(vk, 1.5)
    else:
        for _ in range(int(sys.argv[2]) if len(sys.argv) > 2 else 1):
            send(vk, 0)
            send(vk, KEYEVENTF_KEYUP)
            time.sleep(0.03)
