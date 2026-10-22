"""Entry point: tray icon + inputs + overlay + local UI server."""
import ctypes
import ctypes.wintypes as wt
import os
import shutil
import subprocess
import sys
import threading
import urllib.request
import webbrowser

from . import APP_NAME, config
from .core import Mixer
from .server import make_server

PORT = 8765
URL = f"http://127.0.0.1:{PORT}/"
ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "icon.ico")


# Window titles of our pages (an Edge --app window is titled exactly like its page;
# normal browser tabs get " - Microsoft Edge" appended, so they never match).
TITLES = {"": "Knob Mixer", "settings": "Knob Mixer Settings"}


def find_window():
    """Return (hwnd, title) of an open Knob Mixer window, or (None, None)."""
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def check(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value in TITLES.values():
                found.append((hwnd, buf.value))
                return False
        return True

    user32.EnumWindows(check, 0)
    return found[0] if found else (None, None)


def open_ui(path=""):
    """Focus the existing mixer window (switching page if needed), or open one."""
    hwnd, title = find_window()
    if hwnd:
        user32 = ctypes.windll.user32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        if title != TITLES[path]:
            try:  # the open page picks this up on its next poll and navigates
                urllib.request.urlopen(urllib.request.Request(f"{URL}api/navigate?path=/{path}", method="POST"), timeout=2)
            except OSError:
                pass
        return
    url = URL + path
    edge = shutil.which("msedge") or r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if os.path.exists(edge):
        size = "900,720" if path == "settings" else "820,340"
        subprocess.Popen([edge, f"--app={url}", f"--window-size={size}"])
    else:
        webbrowser.open(url)


def run_tray(server):
    import pystray
    from PIL import Image

    img = Image.open(ICON)  # same icon as the window / taskbar / shortcuts

    def quit_app(icon):
        icon.stop()
        server.shutdown()

    icon = pystray.Icon("knob-mixer", img, APP_NAME, pystray.Menu(
        pystray.MenuItem("Open mixer", lambda: open_ui(), default=True),
        pystray.MenuItem("Settings…", lambda: open_ui("settings")),
        pystray.MenuItem("Quit", quit_app),
    ))
    threading.Thread(target=icon.run, daemon=True).start()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    page = "settings" if "--settings" in argv else "" if "--open" in argv else None
    cfg, load_errors = config.load()
    mixer = Mixer()
    try:
        server = make_server(PORT, mixer, load_errors)
    except OSError:
        # Already running (e.g. started at login): just open its window if asked.
        if page is not None:
            open_ui(page)
        return

    from .overlay import Overlay
    mixer.overlay = Overlay()
    mixer.apply(cfg)
    threading.Thread(target=mixer.poll_forever, daemon=True).start()
    run_tray(server)
    print(f"{APP_NAME} running at {URL}  (config: {config.CONFIG_PATH})")
    for e in load_errors:
        print(f"  config problem: {e}")
    if page is not None:
        open_ui(page)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
