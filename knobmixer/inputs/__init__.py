"""Input source registry (same lazy / "module:Class" scheme as providers)."""
import importlib

from .base import InputSource

BUILTIN = {
    "hotkeys": ("knobmixer.inputs.hotkeys", "HotkeyInput", "Global hotkeys"),
    "serial": ("knobmixer.inputs.serial_input", "SerialInput", "Serial device (DIY knob box)"),
    "phone": ("knobmixer.inputs.phone", "PhoneInput", "Phone remote (web page on your network)"),
}


def resolve(kind):
    module, cls = BUILTIN[kind][:2] if kind in BUILTIN else kind.split(":", 1)
    return getattr(importlib.import_module(module), cls)


def available():
    return [{"type": k, "label": v[2]} for k, v in BUILTIN.items()]


__all__ = ["InputSource", "resolve", "available"]
