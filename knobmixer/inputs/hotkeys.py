"""Global hotkeys via RegisterHotKey.

Only the exact configured combos are claimed. This isn't a keyboard hook, so
every other keystroke reaches your apps untouched. F13-F24 are the safest
choice: Windows supports them but normal keyboards don't have them.
"""
import ctypes
import ctypes.wintypes as wt
import threading

from .. import keys
from .base import InputSource

WM_HOTKEY, WM_TIMER, WM_QUIT = 0x0312, 0x0113, 0x0012
ACTIONS = ("down", "up", "mute")


class HotkeyInput(InputSource):
    label = "Global hotkeys"

    def __init__(self, knobs, options, dispatch):
        super().__init__(knobs, options, dispatch)
        self._thread = None
        self._tid = None
        self._status = {}

    def start(self):
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True, name="hotkeys")
        self._thread.start()
        ready.wait(2)

    def stop(self):
        if self._thread and self._tid:
            ctypes.windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            self._thread.join(2)
        self._thread = None

    def status(self):
        return {"bindings": self._status}

    def _run(self, ready):
        user32 = ctypes.windll.user32
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        bindings, status, next_id = {}, {}, 1
        for knob in self.knobs:
            for action in ACTIONS:
                combo = (knob.get("keys") or {}).get(action)
                if not combo:
                    continue
                combo, mods, vk = keys.parse(combo)
                ok = bool(user32.RegisterHotKey(None, next_id, mods, vk))
                status[combo] = {"knob": knob["label"], "action": action, "ok": ok,
                                 "error": "" if ok else "already taken by another app"}
                if ok:
                    bindings[next_id] = (knob["id"], action, vk)
                next_id += 1
        self._status = status
        ready.set()

        # Not using MOD_NOREPEAT: in testing it silently dropped ~1 in 8 quick
        # taps. Instead, a mute key held down (auto-repeat) is ignored until it
        # has been released, so holding it can't flip mute back and forth.
        held = set()
        user32.SetTimer(None, 0, 50, None)
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_TIMER:
                held = {vk for vk in held if user32.GetAsyncKeyState(vk) & 0x8000}
            elif msg.message == WM_HOTKEY and msg.wParam in bindings:
                knob_id, action, vk = bindings[msg.wParam]
                if action == "mute":
                    if vk in held:
                        continue
                    held.add(vk)
                self.dispatch(knob_id, action)
        for hotkey_id in bindings:
            user32.UnregisterHotKey(None, hotkey_id)
