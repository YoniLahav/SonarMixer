"""SteelSeries Sonar (classic mode) via its local HTTP API.

GG writes its own address to coreProps.json; GG's /subApps endpoint then tells
us where Sonar's web server is listening. Both ports change when GG restarts,
so we rediscover automatically after any connection failure.

Sonar applies changes to the audio instantly, but GG's own window doesn't
refresh live for changes made from outside; it catches up when reopened.
"""
import json
import ssl
import threading
import urllib.error
import urllib.request

from .base import AudioProvider, ProviderError

CORE_PROPS = r"C:\ProgramData\SteelSeries\GG\coreProps.json"

# channel id -> (Sonar device name, label). "Master" scales all channels proportionally.
CHANNELS = {
    "master": ("Master", "Master"),
    "game": ("game", "Game"),
    "chat": ("chatRender", "Chat"),
    "media": ("media", "Media"),
    "aux": ("aux", "Aux"),
    "mic": ("chatCapture", "Mic"),
}


class SonarProvider(AudioProvider):
    label = "SteelSeries Sonar"

    def __init__(self, options):
        super().__init__(options)
        self.timeout = float(self.options.get("timeout", 1.0))
        self.base = None
        self._lock = threading.Lock()

    def _request(self, url, method="GET", context=None):
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=self.timeout, context=context) as r:
            body = r.read()
        return json.loads(body) if body else None

    def _discover(self):
        try:
            with open(CORE_PROPS, encoding="utf-8") as f:
                gg = json.load(f)["ggEncryptedAddress"]
            ctx = ssl._create_unverified_context()  # GG uses a self-signed cert on localhost
            sonar = self._request(f"https://{gg}/subApps", context=ctx)["subApps"]["sonar"]
        except (OSError, KeyError, ValueError) as e:
            raise ProviderError(f"SteelSeries GG not reachable: {e}") from e
        if not (sonar.get("isEnabled") and sonar.get("isReady") and sonar.get("isRunning")):
            raise ProviderError("Sonar is not running")
        base = sonar["metadata"]["webServerAddress"]
        mode = self._request(f"{base}/mode/")
        if mode != "classic":
            raise ProviderError(f"Sonar is in '{mode}' mode; only Classic mode is supported")
        self.base = base

    def _call(self, path, method="GET"):
        with self._lock:
            for attempt in (0, 1):
                if self.base is None:
                    self._discover()
                try:
                    return self._request(self.base + path, method)
                except (urllib.error.URLError, OSError) as e:
                    self.base = None  # GG/Sonar may have restarted on a new port
                    if attempt:
                        raise ProviderError(f"Sonar request failed: {e}") from e

    def _device(self, channel):
        if channel not in CHANNELS:
            raise ProviderError(f"unknown Sonar channel '{channel}'")
        return CHANNELS[channel][0]

    def channels(self):
        return [{"id": ch, "label": label} for ch, (_, label) in CHANNELS.items()]

    def get_state(self, channels=None):
        data = self._call("/volumeSettings/classic")
        state = {}
        for ch, (dev, _) in CHANNELS.items():
            s = data["masters"]["classic"] if dev == "Master" else data["devices"].get(dev, {}).get("classic")
            if s:
                state[ch] = {"volume": s["volume"], "muted": s["muted"]}
        return state

    def set_volume(self, channel, volume):
        volume = round(min(1.0, max(0.0, volume)), 4)
        self._call(f"/volumeSettings/classic/{self._device(channel)}/Volume/{volume}", "PUT")
        return volume

    def set_mute(self, channel, muted):
        self._call(f"/volumeSettings/classic/{self._device(channel)}/Mute/{'true' if muted else 'false'}", "PUT")
