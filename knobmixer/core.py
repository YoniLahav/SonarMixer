"""The mixer: routes knob actions from any input to channels on the active provider."""
import threading
import time

from . import inputs as input_registry
from . import providers
from .providers import ProviderError

POLL_SECONDS = 0.3      # pick up changes made elsewhere (e.g. in the audio app itself)
LOCAL_GRACE = 0.5       # ignore polls this soon after our own change, so knobs don't jitter
PAUSE_LIMIT = 30        # settings-page key recording can't leave hotkeys off longer than this


class Mixer:
    def __init__(self):
        self.lock = threading.RLock()
        self.cfg = None
        self.provider = None
        self.inputs = {}           # kind -> InputSource
        self.state = {}            # channel -> {"volume", "muted"}
        self.connected = False
        self.error = ""
        self.overlay = None        # anything with .show(label, color, volume, muted)
        self._last_local = {}      # channel -> monotonic time of our last change
        self._resume_timer = None
        self.navigate = None       # page the open UI window should switch to (one-shot)

    # --- configuration ------------------------------------------------------------
    def apply(self, cfg):
        """Switch to a new config: swaps the provider if needed and restarts inputs."""
        self._stop_inputs()  # outside the lock: an input thread may be waiting on it
        with self.lock:
            old = self.cfg
            self.cfg = cfg
            if old is None or old["provider"] != cfg["provider"]:
                self._close_provider()
                self.state = {}
                self._ensure_provider()
        self._start_inputs()
        self.refresh()

    def _ensure_provider(self):
        if self.provider is None:
            try:
                p = self.cfg["provider"]
                self.provider = providers.create(p["type"], p["options"])
            except ProviderError as e:
                self._fail(e)
        return self.provider

    def _close_provider(self):
        if self.provider:
            try:
                self.provider.close()
            except Exception:
                pass
        self.provider = None

    def _start_inputs(self):
        for kind, opts in self.cfg["inputs"].items():
            if not opts.get("enabled"):
                continue
            try:
                src = input_registry.resolve(kind)(self.cfg["knobs"], opts, self.dispatch)
                src.start()
                self.inputs[kind] = src
            except Exception as e:
                print(f"input '{kind}' failed to start: {e!r}")

    def _stop_inputs(self):
        for src in self.inputs.values():
            try:
                src.stop()
            except Exception:
                pass
        self.inputs = {}

    def pause_inputs(self):
        """Release all hotkeys so the settings page can record a key press."""
        self._stop_inputs()
        if self._resume_timer:
            self._resume_timer.cancel()
        self._resume_timer = threading.Timer(PAUSE_LIMIT, self.resume_inputs)
        self._resume_timer.daemon = True
        self._resume_timer.start()

    def resume_inputs(self):
        if self._resume_timer:
            self._resume_timer.cancel()
            self._resume_timer = None
        if not self.inputs:
            self._start_inputs()

    # --- actions ------------------------------------------------------------------
    def _fail(self, e):
        self.connected, self.error = False, str(e)

    def _knob(self, knob_id):
        return next((k for k in self.cfg["knobs"] if k["id"] == knob_id), None)

    def dispatch(self, knob_id, action, amount=None, source="input"):
        """Entry point for every input. action: up | down | adjust | set | mute."""
        knob = self._knob(knob_id)
        if knob is None:
            return
        ch = knob["channel"]
        with self.lock:
            provider = self._ensure_provider()
            if provider is None:
                return
            try:
                if action == "mute":
                    # Toggle against the live value so a stale cache never flips it the wrong way.
                    current = provider.get_state([ch]).get(ch)
                    if current is None:
                        raise ProviderError(f"channel '{ch}' isn't available")
                    muted = not current["muted"]
                    provider.set_mute(ch, muted)
                    self.state[ch] = {**current, "muted": muted}
                else:
                    cur = self.state.get(ch) or provider.get_state([ch]).get(ch)
                    if cur is None:
                        raise ProviderError(f"channel '{ch}' isn't available")
                    step = self.cfg["step"]
                    target = {"up": cur["volume"] + step, "down": cur["volume"] - step,
                              "adjust": cur["volume"] + step * (amount or 0), "set": amount}[action]
                    self.state[ch] = {**cur, "volume": provider.set_volume(ch, target)}
                self._last_local[ch] = time.monotonic()
                self.connected, self.error = True, ""
                st = dict(self.state[ch])
            except ProviderError as e:
                self._fail(e)
                return
            except Exception as e:  # never let one bad event kill an input thread
                self._fail(f"{action} on {knob['label']} failed: {e!r}")
                return
        if source != "ui" and self.overlay and self.cfg["overlay"]:
            self.overlay.show(knob["label"], knob["color"], st["volume"], st["muted"])

    # --- state --------------------------------------------------------------------
    def refresh(self):
        with self.lock:
            provider = self._ensure_provider()
        if provider is None:
            return
        try:
            fresh = provider.get_state()
        except ProviderError as e:
            with self.lock:
                self._fail(e)
            return
        now = time.monotonic()
        with self.lock:
            if provider is not self.provider:
                return  # provider was swapped while we were reading
            self.connected, self.error = True, ""
            for ch, st in fresh.items():
                if now - self._last_local.get(ch, 0) > LOCAL_GRACE:
                    self.state[ch] = st
            for ch in list(self.state):
                if ch not in fresh:
                    del self.state[ch]  # e.g. an app channel that closed

    def poll_forever(self):
        while True:
            self.refresh()
            time.sleep(POLL_SECONDS)

    def snapshot(self):
        with self.lock:
            knobs = []
            for k in self.cfg["knobs"]:
                st = self.state.get(k["channel"])
                knobs.append({"id": k["id"], "label": k["label"], "color": k["color"],
                              "channel": k["channel"], "available": st is not None,
                              "volume": st["volume"] if st else 0.0, "muted": st["muted"] if st else False})
            navigate, self.navigate = self.navigate, None
            return {"connected": self.connected, "error": self.error, "knobs": knobs,
                    "step": self.cfg["step"], "navigate": navigate,
                    "inputs": {kind: src.status() for kind, src in self.inputs.items()}}

    def list_channels(self, kind, options):
        """Channels for a provider, without switching to it (used by the settings page)."""
        with self.lock:
            current = self.provider if self.cfg["provider"] == {"type": kind, "options": options} else None
        if current:
            return current.channels()
        temp = providers.create(kind, options)
        try:
            return temp.channels()
        finally:
            temp.close()
