"""Load / validate / save the user's config (%APPDATA%\\KnobMixer\\config.json)."""
import copy
import json
import os
import re

from . import inputs, keys, providers

CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "KnobMixer")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
ACTIONS = ("down", "up", "mute")


def _knob(id_, label, channel, color, f):
    return {"id": id_, "label": label, "channel": channel, "color": color,
            "keys": {"down": f"F{f}", "up": f"F{f + 1}", "mute": f"F{f + 2}"}}


DEFAULT = {
    "provider": {"type": "sonar", "options": {}},
    "step": 0.02,
    "overlay": True,
    "inputs": {
        "hotkeys": {"enabled": True},
        "serial": {"enabled": False, "port": "", "baud": 115200},
        "phone": {"enabled": False, "port": 8771},
    },
    "knobs": [
        _knob("game", "Game", "game", "#4f6ee8", 13),
        _knob("media", "Media", "media", "#1fb5c4", 16),
        _knob("chat", "Chat", "chat", "#a557f2", 19),
        _knob("master", "Master", "master", "#d8dae0", 22),
    ],
}


def validate(raw):
    """Return (clean_config, errors). Errors are human-readable strings."""
    errors = []
    cfg = copy.deepcopy(DEFAULT)
    if not isinstance(raw, dict):
        return cfg, ["config must be a JSON object"]

    prov = raw.get("provider") or {}
    cfg["provider"] = {"type": str(prov.get("type") or "sonar"), "options": dict(prov.get("options") or {})}
    try:
        providers.resolve(cfg["provider"]["type"])
    except Exception:
        errors.append(f"unknown audio provider '{cfg['provider']['type']}'")

    try:
        cfg["step"] = float(raw.get("step", cfg["step"]))
        if not 0.001 <= cfg["step"] <= 0.25:
            errors.append("step must be between 0.1% and 25%")
    except (TypeError, ValueError):
        errors.append("step must be a number")
    cfg["overlay"] = bool(raw.get("overlay", True))

    cfg["inputs"] = {}
    for kind, opts in (raw.get("inputs") or DEFAULT["inputs"]).items():
        try:
            inputs.resolve(kind)
        except Exception:
            errors.append(f"unknown input '{kind}'")
            continue
        cfg["inputs"][kind] = {**DEFAULT["inputs"].get(kind, {}), **dict(opts or {})}
        cfg["inputs"][kind]["enabled"] = bool(cfg["inputs"][kind].get("enabled"))
    if "serial" in cfg["inputs"]:
        try:
            cfg["inputs"]["serial"]["baud"] = int(cfg["inputs"]["serial"].get("baud", 115200))
        except (TypeError, ValueError):
            errors.append("serial baud rate must be a number")
    if "phone" in cfg["inputs"]:
        try:
            cfg["inputs"]["phone"]["port"] = int(cfg["inputs"]["phone"].get("port", 8771))
            if not 1024 <= cfg["inputs"]["phone"]["port"] <= 65535:
                errors.append("phone remote port must be between 1024 and 65535")
        except (TypeError, ValueError):
            errors.append("phone remote port must be a number")

    knobs, seen_ids, seen_keys = [], set(), {}
    for i, k in enumerate(raw.get("knobs") or []):
        label = str(k.get("label") or "").strip() or f"Knob {i + 1}"
        id_ = re.sub(r"[^a-z0-9_-]", "", str(k.get("id") or label).lower()) or f"knob{i + 1}"
        while id_ in seen_ids:
            id_ += "_"
        seen_ids.add(id_)
        color = str(k.get("color") or "#888888")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            errors.append(f"{label}: color must look like #33aaff")
        channel = str(k.get("channel") or "").strip()
        if not channel:
            errors.append(f"{label}: pick a channel")
        knob_keys = {}
        for action in ACTIONS:
            combo = str((k.get("keys") or {}).get(action) or "").strip()
            if not combo:
                continue
            try:
                combo = keys.parse(combo)[0]
            except ValueError as e:
                errors.append(f"{label} {action}: {e}")
                continue
            if combo in seen_keys:
                errors.append(f"{combo} is used twice ({seen_keys[combo]} and {label} {action})")
            seen_keys[combo] = f"{label} {action}"
            knob_keys[action] = combo
        knobs.append({"id": id_, "label": label, "channel": channel, "color": color.lower(), "keys": knob_keys})
    if not knobs:
        errors.append("add at least one knob")
    cfg["knobs"] = knobs
    return cfg, errors


def load():
    """Return (config, errors). Creates the default config on first run."""
    if not os.path.exists(CONFIG_PATH):
        save(DEFAULT)
        return copy.deepcopy(DEFAULT), []
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        return copy.deepcopy(DEFAULT), [f"couldn't read {CONFIG_PATH} ({e}); using defaults"]
    return validate(raw)


def save(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_PATH)
