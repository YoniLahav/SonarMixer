# Knob Mixer

Control your audio software's volume channels with knobs: physical ones (a DIY encoder box, a keyboard dial) or the on-screen ones. It shows a small popup whenever something changes.

It's built from swappable parts, so you can use any number of knobs, map them to any channels, and connect any audio software or input device:

```
 inputs/                     core.py                        providers/
┌──────────────┐  knob X:   ┌──────────────────────┐  set   ┌──────────────────────┐
│ hotkeys      │  up/down/  │ knob → channel map   │ volume │ sonar  (SteelSeries) │
│ serial box   │ ─────────► │ step size, state,    │ ─────► │ windows (devices,    │
│ (your own)   │  set/mute  │ overlay              │  mute  │          per-app)    │
└──────────────┘            └──────────────────────┘        │ (your own)           │
                                                            └──────────────────────┘
```

Inputs know nothing about audio, and providers know nothing about knobs. Only the config connects them.

## Install & run

```
pip install -r requirements.txt
pythonw mixer.py              # tray icon + hotkeys + overlay (put a shortcut to this in shell:startup)
pythonw mixer.py --open       # also open the knob window (or just open it, if already running)
pythonw mixer.py --settings   # open settings
```

Left-click the tray icon to open the knobs. Right-click it for Settings and Quit. Closing the window leaves the app running in the tray. Windows 11 hides new tray icons under **^**, so drag the icon out to pin it.

## Settings

Everything is configured on the Settings page and saved to `%APPDATA%\KnobMixer\config.json`. Changes apply immediately, with no restart.

- **Audio software:** choose the provider.
- **Knobs:** add, remove and reorder knobs. Each knob has a label, a colour, a channel, and optional keys for turn-left, turn-right and press. Click ⏺ to record a key combo.
- **Input methods:** turn global hotkeys and the serial device on or off.
- **General:** step size and the on-screen popup.

### Choosing keys

Hotkeys use `RegisterHotKey`. Only the exact combos you configure are claimed, so no keyboard hook watches your typing and every other key works normally. **F13–F24 are the safest choice**: Windows supports them, but normal keyboards don't have them. The settings page warns you if a key would take over something you type with.

If a combo is already taken by another program, the settings page shows it as failed, and that program keeps it.

To use a keyboard dial (which usually sends Volume Up/Down/Mute), either bind those keys directly (this takes them over from Windows), or use PowerToys Keyboard Manager to remap them to F22/F23/F24.

## Providers

| type | channels | needs |
|---|---|---|
| `sonar` | `master`, `game`, `chat`, `media`, `aux`, `mic` | SteelSeries GG with Sonar in **Classic** mode |
| `windows` | `output`, `input`, `app:<exe>` (e.g. `app:spotify.exe`) | `pip install pycaw` |

Sonar notes:
- Master scales all channels proportionally.
- Sonar applies changes instantly, but GG's own window only shows them after you reopen it.

### Writing a provider

```python
from knobmixer.providers import AudioProvider, ProviderError

class VoicemeeterProvider(AudioProvider):
    label = "Voicemeeter"
    def channels(self):                       return [{"id": "strip0", "label": "Strip 1"}, ...]
    def get_state(self, channels=None):       return {"strip0": {"volume": 0.8, "muted": False}}
    def set_volume(self, channel, volume):    ...; return volume      # 0.0-1.0
    def set_mute(self, channel, muted):       ...
```

Raise `ProviderError` with a readable message when the software is unreachable. Then either add it to `BUILTIN` in `knobmixer/providers/__init__.py`, or choose **Custom adapter** in Settings and enter `my_module:VoicemeeterProvider` (the module must be importable).

## Inputs

| type | what it does |
|---|---|
| `hotkeys` | global key combos per knob (turn left / turn right / press) |
| `serial` | a DIY knob box over USB serial (`pip install pyserial`) |

### Serial protocol (for your own knob box)

The device sends one ASCII line per event. A knob is named by its 1-based position in the knob list, or by its id:

```
1 +1        turned right one detent      (any count: "2 -3")
1 press     pushed (toggle mute)
1 set 42    absolute position 42%        (for potentiometers / faders)
game +1     same, addressing the knob by id
```

With this protocol no keys are involved at all. It reconnects automatically if the device is unplugged.

Suggested hardware: EC11 rotary encoders (with push switch) and an RP2040 board such as a Pi Pico. A short CircuitPython or Arduino sketch prints the lines above.

### Writing an input

Subclass `knobmixer.inputs.InputSource` and implement `start()`, `stop()` and `status()`. When something happens, call `self.dispatch(knob_id, action, amount)`, where action is one of:
- `up` or `down`
- `adjust` with `amount` = a number of steps
- `set` with `amount` = 0.0–1.0
- `mute`

Register it in `knobmixer/inputs/__init__.py`, or add it to the config's `inputs` as `"my_module:MyInput": {"enabled": true, ...}`.

## Tools

```
python tools/cli.py                      # list the active provider's channels and state
python tools/cli.py game +5 | media 40 | mute chat
python tools/cli.py --provider windows   # use another provider
python tools/sendkey.py F14 5            # simulate key taps (F13-F24); "F21 hold" holds the key down
python -m knobmixer.overlay              # preview the popup
```

## Layout

```
mixer.py                  launcher
knobmixer/
  app.py                  tray, single instance, startup
  core.py                 Mixer: knob → channel routing, state, polling
  config.py               defaults, validation, load/save
  keys.py                 key-combo parsing
  overlay.py              on-screen popup (click-through, never takes focus)
  server.py               local web UI + JSON API on 127.0.0.1:8765
  providers/              base.py, sonar.py, windows.py
  inputs/                 base.py, hotkeys.py, serial_input.py
  web/                    index.html (knobs), settings.html
tools/                    cli.py, sendkey.py
```
