# Knob Mixer firmware for an RP2040 board (e.g. Waveshare RP2040-Zero) running CircuitPython.
#
# Reads rotary encoders with push switches (KY-040 / EC11) and prints the serial protocol
# that knobmixer/inputs/serial_input.py understands:
#     1 +1      knob 1 turned one detent right
#     2 -3      knob 2 turned three detents left
#     3 press   knob 3 pushed (toggle mute)
#
# Copy this file to the CIRCUITPY drive as code.py. See firmware/README.md for wiring.
import time

import board
import keypad
import rotaryio

# One entry per knob, in the same order as the knob list in Settings (knob 1 = first row).
# CLK and DT must be neighbouring GPIOs (RP2040 reads encoders with PIO, which needs that).
#   (CLK pin,   DT pin,     SW pin)
ENCODERS = [
    (board.GP0, board.GP1, board.GP2),
    (board.GP3, board.GP4, board.GP5),
    (board.GP6, board.GP7, board.GP8),
]

# Flip a knob's direction without rewiring: -1 reverses it. One value per knob.
DIRECTION = [1, 1, 1]

# Quadrature steps per click. 4 is right for most KY-040s. If you have to turn two clicks
# before anything happens (or it only reacts every other click), change it to 2.
DIVISOR = 4

# Don't send more often than this (seconds). Fast spins get summed into one line, e.g. "1 +5".
SEND_INTERVAL = 0.02

encoders = [rotaryio.IncrementalEncoder(clk, dt, divisor=DIVISOR) for clk, dt, _ in ENCODERS]
# KY-040 boards usually have no pull-up fitted on SW, so use the RP2040's internal one.
buttons = keypad.Keys([sw for _, _, sw in ENCODERS], value_when_pressed=False, pull=True)

last = [e.position for e in encoders]
event = keypad.Event()
next_send = 0

while True:
    while buttons.events.get_into(event):
        if event.pressed:
            print(f"{event.key_number + 1} press")

    now = time.monotonic()
    if now >= next_send:
        for i, enc in enumerate(encoders):
            pos = enc.position
            delta = (pos - last[i]) * DIRECTION[i]
            if delta:
                last[i] = pos
                print(f"{i + 1} {delta:+d}")
        next_send = now + SEND_INTERVAL
    time.sleep(0.002)
