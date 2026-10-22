"""Knob Mixer launcher.

  pythonw mixer.py              tray icon + inputs + overlay (what runs at login)
  pythonw mixer.py --open       same, and open the knob window
  pythonw mixer.py --settings   same, and open settings
If it's already running, --open / --settings just open that window.
"""
from knobmixer.app import main

if __name__ == "__main__":
    main()
