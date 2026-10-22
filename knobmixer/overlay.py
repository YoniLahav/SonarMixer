"""On-screen popup shown when a knob (hotkey / device) changes a channel.

Runs Tk in its own thread. The window is always "shown" but fully transparent
when idle, and is click-through + no-activate, so it never steals focus from
a game or swallows clicks.
"""
import ctypes
import queue
import threading
import tkinter as tk

BG, TRACK, MUTED_FILL, DANGER, TEXT = "#16171b", "#2a2c33", "#4a4d55", "#ef4d5a", "#e8e8ea"
KEY = "#010203"           # colour made fully transparent (rounded corners)
SHOW_MS, FADE_MS, ALPHA = 1200, 250, 0.95


class Overlay:
    def __init__(self):
        self.q = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def show(self, label, color, volume, muted):
        self.q.put((label, color, volume, muted))

    def _run(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # crisp text on scaled displays
        except (AttributeError, OSError):
            pass
        self.root = root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True, "-alpha", 0.0, "-transparentcolor", KEY)
        root.config(bg=KEY)
        self.s = s = root.winfo_fpixels("1i") / 96
        self.w, self.h = int(300 * s), int(66 * s)
        x = (root.winfo_screenwidth() - self.w) // 2
        y = root.winfo_screenheight() - self.h - int(140 * s)
        root.geometry(f"{self.w}x{self.h}+{x}+{y}")
        self.canvas = tk.Canvas(root, width=self.w, height=self.h, bg=KEY, highlightthickness=0)
        self.canvas.pack()
        root.update_idletasks()

        # layered | click-through | tool window (no taskbar) | never activate
        u32 = ctypes.windll.user32
        hwnd = u32.GetParent(root.winfo_id())
        u32.SetWindowLongW(hwnd, -20, u32.GetWindowLongW(hwnd, -20) | 0x80000 | 0x20 | 0x80 | 0x08000000)

        self._hide_job = None
        root.after(30, self._poll)
        root.mainloop()

    def _poll(self):
        latest = None
        while not self.q.empty():
            latest = self.q.get_nowait()  # only draw the newest state
        if latest:
            self._draw(*latest)
        self.root.after(30, self._poll)

    def _rounded(self, x0, y0, x1, y1, r, **kw):
        c = self.canvas
        c.create_rectangle(x0 + r, y0, x1 - r, y1, width=0, **kw)
        c.create_rectangle(x0, y0 + r, x1, y1 - r, width=0, **kw)
        for cx, cy in ((x0, y0), (x1 - 2 * r, y0), (x0, y1 - 2 * r), (x1 - 2 * r, y1 - 2 * r)):
            c.create_oval(cx, cy, cx + 2 * r, cy + 2 * r, width=0, **kw)

    def _draw(self, label, color, volume, muted):
        c, s, w, h = self.canvas, self.s, self.w, self.h
        c.delete("all")
        self._rounded(0, 0, w, h, int(12 * s), fill=BG)
        pad = int(18 * s)
        font = ("Segoe UI", 11, "bold")
        c.create_text(pad, int(22 * s), text=label.upper(), anchor="w", fill=color, font=font)
        c.create_text(w - pad, int(22 * s), anchor="e", font=font,
                      text="MUTED" if muted else f"{round(volume * 100)}%", fill=DANGER if muted else TEXT)
        by0, by1 = int(40 * s), int(48 * s)
        self._rounded(pad, by0, w - pad, by1, int(4 * s), fill=TRACK)
        fill_w = (w - 2 * pad) * volume
        if fill_w >= 8 * s:
            self._rounded(pad, by0, pad + fill_w, by1, int(4 * s), fill=MUTED_FILL if muted else color)

        self.root.attributes("-topmost", True, "-alpha", ALPHA)  # re-assert over games
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
        self._hide_job = self.root.after(SHOW_MS, self._fade, ALPHA)

    def _fade(self, alpha):
        alpha -= ALPHA / (FADE_MS / 25)
        self.root.attributes("-alpha", max(0.0, alpha))
        self._hide_job = self.root.after(25, self._fade, alpha) if alpha > 0 else None


if __name__ == "__main__":  # demo: python -m knobmixer.overlay
    import time
    o = Overlay()
    time.sleep(0.5)
    for v in (0.3, 0.32, 0.34, 0.36):
        o.show("Media", "#1fb5c4", v, False)
        time.sleep(0.15)
    time.sleep(2)
    o.show("Chat", "#a557f2", 0.8, True)
    time.sleep(2)
