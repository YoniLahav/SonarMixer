# Knob box firmware (RP2040-Zero + KY-040)

`code.py` turns an RP2040 board and up to a few rotary encoders into a knob box for the
**Serial device** input. Turn = volume up/down, push = mute.

## 1. Wiring

Power the encoders from **3V3, never 5V**: the RP2040's pins are not 5 V tolerant, and the
KY-040's on-board pull-ups connect CLK/DT to its `+` pin.

| KY-040 pin | Encoder 1 | Encoder 2 | Encoder 3 |
|---|---|---|---|
| CLK | GP0 | GP3 | GP6 |
| DT  | GP1 | GP4 | GP7 |
| SW  | GP2 | GP5 | GP8 |
| +   | 3V3 | 3V3 | 3V3 |
| GND | GND | GND | GND |

On the Waveshare RP2040-Zero, GP0–GP8 are the nine pins along one edge, and 5V/GND/3V3 are
at the top of the other edge, so the whole box can be wired from two sides of the board.

Other pins work too: edit `ENCODERS` in `code.py`. CLK and DT of each encoder must be
neighbouring GPIO numbers (e.g. GP26/GP27).

## 2. Install CircuitPython (once)

1. Download the `.uf2` for the **Waveshare RP2040-Zero** from
   <https://circuitpython.org/board/waveshare_rp2040_zero/> (latest stable).
2. Hold the **BOOT** button and plug the board in (or, if it's already plugged in, hold BOOT
   and tap RESET). A drive called **RPI-RP2** appears.
3. Drag the `.uf2` onto it. The board restarts and a drive called **CIRCUITPY** appears.

## 3. Copy the firmware

Copy `firmware/code.py` onto **CIRCUITPY** (replace the `code.py` that's there). It starts
running immediately, and again every time the board is plugged in. No libraries are needed:
`rotaryio` and `keypad` are built in.

## 4. Test it

Find the board's COM port: Device Manager → Ports (COM & LPT) → "USB Serial Device (COMx)".

Open that port in any serial monitor (e.g. PuTTY, Serial connection, speed 115200, or Thonny/Mu)
and turn a knob. You should see lines like:

```
1 +1
1 -2
2 press
```

If a knob goes the wrong way, set its entry in `DIRECTION` to `-1`, or swap its CLK and DT
wires.

**Close the serial monitor afterwards.** Only one program can hold a COM port at a time.

## 5. Connect it to Knob Mixer

Settings → **Input methods** → tick **Serial device**, enter the port (e.g. `COM5`), Save.
The status line should say `connected to COM5`. The baud rate doesn't matter for USB.

Encoder 1 controls the first knob in the **Knobs** list, encoder 2 the second, and so on, so
reorder the knobs there to choose which channel each encoder controls. With the default list,
that's Game, Chat, Media. Step size (how much one click changes the volume) is under General.

## Troubleshooting

- **Settings says "waiting for COM5 (SerialException)"**: wrong port, or another program
  (serial monitor, Thonny, Mu) still has it open.
- **"needs pyserial"**: `pip install pyserial`.
- **Nothing printed at all**: check CIRCUITPY has `code.py` (not `code.py.txt`), and open the
  serial monitor; a Python error from `code.py` is shown there.
- **Jumpy/skipping turns**: check the GND and 3V3 wires; cheap KY-040s sometimes need the
  `DIVISOR` changed to 2.
- **Press does nothing**: check the SW wire. The firmware enables the internal pull-up, so
  no extra resistor is needed.
