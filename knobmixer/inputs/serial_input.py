"""DIY knob box over USB serial. No keyboard involvement at all.

The device sends one ASCII line per event. A knob is named by its 1-based
position in the knob list or by its id:
    1 +1        turned one detent right   (any count: "2 -3")
    1 press     pushed (toggle mute)
    1 set 42    absolute position 42%     (for potentiometers / faders)
    game +1     same, addressing the knob by id
Needs `pip install pyserial`. Reconnects automatically if the device is unplugged.
"""
import threading

from .base import InputSource


def parse_line(line, knobs):
    """'2 -3' -> (knob_id, action, amount) or None if the line isn't understood."""
    parts = line.strip().split()
    if len(parts) < 2:
        return None
    ref, cmd = parts[0], parts[1].lower()
    if ref.isdigit():
        idx = int(ref) - 1
        knob = knobs[idx] if 0 <= idx < len(knobs) else None
    else:
        knob = next((k for k in knobs if k["id"] == ref), None)
    if knob is None:
        return None
    try:
        if cmd == "press":
            return knob["id"], "mute", None
        if cmd == "set" and len(parts) > 2:
            return knob["id"], "set", min(100.0, max(0.0, float(parts[2]))) / 100
        if cmd[0] in "+-":
            return knob["id"], "adjust", int(cmd)
    except ValueError:
        return None
    return None


class SerialInput(InputSource):
    label = "Serial device"

    def __init__(self, knobs, options, dispatch):
        super().__init__(knobs, options, dispatch)
        self._stop = threading.Event()
        self._thread = None
        self._state = "starting"

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="serial")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(2)

    def status(self):
        return {"state": self._state}

    def _run(self):
        try:
            import serial
        except ImportError:
            self._state = "needs pyserial: pip install pyserial"
            return
        port, baud = self.options.get("port", ""), int(self.options.get("baud", 115200))
        if not port:
            self._state = "no port set"
            return
        while not self._stop.is_set():
            try:
                with serial.serial_for_url(port, baud, timeout=0.5) as dev:
                    self._state = f"connected to {port}"
                    while not self._stop.is_set():
                        line = dev.readline().decode("ascii", "ignore")
                        event = parse_line(line, self.knobs) if line else None
                        if event:
                            self.dispatch(*event)
            except Exception as e:
                self._state = f"waiting for {port} ({e.__class__.__name__})"
                self._stop.wait(2)
        self._state = "stopped"
