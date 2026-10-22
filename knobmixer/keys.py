"""Key-combo strings ("Ctrl+Alt+F13") <-> Windows modifier flags + virtual-key codes."""

MODIFIERS = {"Ctrl": 0x2, "Alt": 0x1, "Shift": 0x4, "Win": 0x8}

VK = {f"F{i}": 0x6F + i for i in range(1, 25)}
VK.update({c: ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"})
VK.update({f"Num{i}": 0x60 + i for i in range(10)})
VK.update({
    "Insert": 0x2D, "Delete": 0x2E, "Home": 0x24, "End": 0x23, "PageUp": 0x21, "PageDown": 0x22,
    "Up": 0x26, "Down": 0x28, "Left": 0x25, "Right": 0x27, "Pause": 0x13, "ScrollLock": 0x91,
    "VolumeMute": 0xAD, "VolumeDown": 0xAE, "VolumeUp": 0xAF,
    "MediaNext": 0xB0, "MediaPrev": 0xB1, "MediaStop": 0xB2, "MediaPlayPause": 0xB3,
})
_LOOKUP = {k.lower(): k for k in list(VK) + list(MODIFIERS)}
_LOOKUP.update({"control": "Ctrl", "windows": "Win", "meta": "Win"})

# Keys that no normal keyboard has, so binding them can never clash with typing.
SAFE_KEYS = {f"F{i}" for i in range(13, 25)}


def parse(combo):
    """'ctrl+alt+f13' -> (canonical 'Ctrl+Alt+F13', mods, vk). Raises ValueError."""
    parts = [p.strip() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError("empty key")
    names = []
    for p in parts:
        name = _LOOKUP.get(p.lower())
        if name is None:
            raise ValueError(f"unknown key '{p}'")
        names.append(name)
    *mods, key = names
    if key in MODIFIERS or any(m not in MODIFIERS for m in mods):
        raise ValueError(f"'{combo}' must be modifiers followed by one key")
    mods = [m for m in MODIFIERS if m in mods]  # canonical order, no duplicates
    flags = sum(MODIFIERS[m] for m in mods)
    return "+".join(mods + [key]), flags, VK[key]


def is_safe(combo):
    """True if the combo can't interfere with normal typing (F13-F24 or has Ctrl/Alt/Win)."""
    canonical, flags, _ = parse(combo)
    return canonical.split("+")[-1] in SAFE_KEYS or bool(flags & ~MODIFIERS["Shift"])
