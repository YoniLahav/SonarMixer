"""Windows Core Audio: the default output/input device plus per-app volumes.

Works with any audio setup, no extra software. Needs `pip install pycaw`.
Channels:
  output        default playback device
  input         default recording device (microphone)
  app:<exe>     every audio session of that program on the default playback device,
                e.g. "app:spotify.exe" (only present while the app has audio open)
"""
from concurrent.futures import ThreadPoolExecutor

from .base import AudioProvider, ProviderError


def _com_init():
    import comtypes
    comtypes.CoInitialize()


class WindowsProvider(AudioProvider):
    label = "Windows audio"

    def __init__(self, options):
        super().__init__(options)
        try:
            from pycaw.pycaw import AudioUtilities
        except ImportError as e:
            raise ProviderError("the Windows provider needs pycaw: pip install pycaw") from e
        self._au = AudioUtilities
        # COM objects must stay on the thread that created them, so all calls go
        # through one dedicated worker thread.
        self._pool = ThreadPoolExecutor(1, initializer=_com_init, thread_name_prefix="wincoreaudio")

    def _run(self, fn, *args):
        try:
            return self._pool.submit(fn, *args).result(timeout=3)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Windows audio error: {e}") from e

    # --- worker-thread helpers -------------------------------------------------
    def _device(self, which):
        au = self._au
        dev = au.GetSpeakers() if which == "output" else au.CreateDevice(au.GetMicrophone())
        return dev

    def _apps(self):
        apps = {}
        for s in self._au.GetAllSessions():
            if s.Process:
                apps.setdefault(s.Process.name().lower(), []).append(s.SimpleAudioVolume)
        return apps

    def _targets(self, channel):
        if channel in ("output", "input"):
            return "endpoint", self._device(channel).EndpointVolume
        if channel.startswith("app:"):
            sessions = self._apps().get(channel[4:].lower())
            if not sessions:
                raise ProviderError(f"{channel[4:]} has no audio open right now")
            return "sessions", sessions
        raise ProviderError(f"unknown Windows channel '{channel}'")

    def _channels(self):
        out = [{"id": "output", "label": f"Output: {self._device('output').FriendlyName}"},
               {"id": "input", "label": f"Input: {self._device('input').FriendlyName}"}]
        out += [{"id": f"app:{exe}", "label": f"App: {exe}"} for exe in sorted(self._apps())]
        return out

    def _get_state(self):
        state = {}
        for ch in ("output", "input"):
            ev = self._device(ch).EndpointVolume
            state[ch] = {"volume": ev.GetMasterVolumeLevelScalar(), "muted": bool(ev.GetMute())}
        for exe, sessions in self._apps().items():
            state[f"app:{exe}"] = {"volume": max(s.GetMasterVolume() for s in sessions),
                                   "muted": all(s.GetMute() for s in sessions)}
        return state

    def _set(self, channel, volume=None, muted=None):
        kind, target = self._targets(channel)
        for t in ([target] if kind == "endpoint" else target):
            if volume is not None:
                if kind == "endpoint":
                    t.SetMasterVolumeLevelScalar(volume, None)
                else:
                    t.SetMasterVolume(volume, None)
            if muted is not None:
                t.SetMute(int(muted), None)

    # --- AudioProvider ------------------------------------------------------------
    def channels(self):
        return self._run(self._channels)

    def get_state(self, channels=None):
        return self._run(self._get_state)

    def set_volume(self, channel, volume):
        volume = round(min(1.0, max(0.0, volume)), 4)
        self._run(self._set, channel, volume, None)
        return volume

    def set_mute(self, channel, muted):
        self._run(self._set, channel, None, muted)

    def close(self):
        self._pool.shutdown(wait=False)
