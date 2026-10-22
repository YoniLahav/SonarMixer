"""Audio provider registry.

Built-ins are imported lazily so one provider's missing dependency (e.g. pycaw)
never breaks the others. A config may also name any class directly as
"some_module:SomeClass" to plug in a third-party adapter without editing this file.
"""
import importlib

from .base import AudioProvider, ProviderError

BUILTIN = {
    "sonar": ("knobmixer.providers.sonar", "SonarProvider", "SteelSeries Sonar"),
    "windows": ("knobmixer.providers.windows", "WindowsProvider", "Windows audio (devices & apps)"),
}


def resolve(kind):
    module, cls = BUILTIN[kind][:2] if kind in BUILTIN else kind.split(":", 1)
    return getattr(importlib.import_module(module), cls)


def create(kind, options=None):
    try:
        cls = resolve(kind)
    except Exception as e:
        raise ProviderError(f"can't load provider '{kind}': {e}") from e
    return cls(options or {})


def available():
    return [{"type": k, "label": v[2]} for k, v in BUILTIN.items()]


__all__ = ["AudioProvider", "ProviderError", "create", "available", "resolve"]
