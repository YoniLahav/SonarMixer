# Pin test for the knob box: shows ANY change on an encoder's pins, raw, with no decoding.
#
# To use: copy this file onto the CIRCUITPY drive and rename it to code.py (replacing the
# firmware for now). Put firmware/code.py back when you're done.
#
# Every time CLK, DT or SW changes, it prints a line like
#     CLK=0 DT=1 SW=1   (CLK changed)
# and flashes the board's RGB LED: red = CLK, green = DT, blue = SW.
# The pins use the RP2040's own pull-ups, so this works even if the encoder's + pin isn't
# connected, and you can watch the LED without opening PuTTY at all.
import time

import board
import digitalio
import neopixel_write

PINS = [("CLK", board.GP0), ("DT", board.GP1), ("SW", board.GP2)]  # encoder 1
COLORS = [(40, 0, 0), (0, 40, 0), (0, 0, 40)]  # red, green, blue

ios = []
for _, pin in PINS:
    io = digitalio.DigitalInOut(pin)
    io.pull = digitalio.Pull.UP
    ios.append(io)

led = digitalio.DigitalInOut(getattr(board, "NEOPIXEL", board.GP16))
led.direction = digitalio.Direction.OUTPUT


def show(rgb):
    r, g, b = rgb
    neopixel_write.neopixel_write(led, bytearray([g, r, b]))  # the LED expects GRB order


def state(values):
    return " ".join(f"{name}={int(v)}" for (name, _), v in zip(PINS, values))


last = [io.value for io in ios]
changes = 0
off_at = 0
print("pin test running. At rest:", state(last))
show((10, 10, 10))  # dim white = running
time.sleep(0.5)
show((0, 0, 0))

while True:
    now = [io.value for io in ios]
    if now != last:
        changed = [i for i in range(len(PINS)) if now[i] != last[i]]
        changes += 1
        names = ", ".join(PINS[i][0] for i in changed)
        print(f"{state(now)}   ({names} changed, #{changes})")
        show(COLORS[changed[0]])
        off_at = time.monotonic() + 0.15
        last = now
    if off_at and time.monotonic() > off_at:
        show((0, 0, 0))
        off_at = 0
