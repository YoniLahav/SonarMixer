class InputSource:
    """Adapter for one way of operating the knobs (hotkeys, a serial device, MIDI, ...).

    An input only reports *what happened to which knob*; it knows nothing about
    audio. Call `self.dispatch(knob_id, action, amount=None)` with:
      "up" / "down"   one step (the configured step size)
      "adjust"        `amount` steps, may be negative (e.g. several encoder detents)
      "set"           absolute volume, `amount` in 0.0-1.0 (e.g. a potentiometer/fader)
      "mute"          toggle mute

    To add one, subclass this, implement start/stop/status, and register it in
    inputs/__init__.py (or reference it from the config as "your_module:YourClass").
    """

    label = "Unnamed input"

    def __init__(self, knobs, options, dispatch):
        self.knobs = knobs          # the configured knobs, in order
        self.options = options      # this input's section of the config
        self.dispatch = dispatch

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def status(self):
        """Short JSON-able status for the settings screen."""
        return {}
