class ProviderError(Exception):
    """The audio backend is unreachable or rejected a request (shown to the user)."""


class AudioProvider:
    """Adapter for one piece of audio software.

    To add support for another app, subclass this, implement the four methods,
    and register it in providers/__init__.py (or reference it from the config
    as "your_module:YourClass"). Volumes are always floats 0.0-1.0.
    """

    label = "Unnamed provider"

    def __init__(self, options):
        self.options = options or {}

    def channels(self):
        """List the channels a knob can control: [{"id": "game", "label": "Game"}, ...]."""
        raise NotImplementedError

    def get_state(self, channels=None):
        """Return {channel_id: {"volume": float, "muted": bool}}.

        `channels` limits the result when given (the provider may still return more).
        Channels that don't currently exist (e.g. an app that isn't running) are omitted.
        """
        raise NotImplementedError

    def set_volume(self, channel, volume):
        """Set volume (0.0-1.0) and return the value actually applied."""
        raise NotImplementedError

    def set_mute(self, channel, muted):
        raise NotImplementedError

    def close(self):
        pass
