#!/usr/bin/env python3
"""Bring-up jog tool: command BOTH arm servos to target angles and print the
firmware echo as proof the signal reached the Nucleo.

Usage:  python3 pi-servojog.py <shoulder_deg> <elbow_deg> [hold_seconds]
  shoulder = Servo 1 (PB_14, TIM15_CH1)
  elbow    = Servo 2 (PB_15, TIM15_CH2)

One servo packet carries BOTH pulse widths and the servos are open-loop (no
feedback to "hold the other where it is"), so give both angles explicitly. Angles
map linearly onto [500, 2500] us over [0, 180] deg -- matching kuas_mechlab3's
protocol.py -- and the firmware clamps to the same safe band, then echoes
"srv <us1> <us2>". This sends the "us1/us2/a" servo packet on 115200 baud
/dev/ttyACM0; it never touches the 4-wheel drive packet ("s1/s2/s3/s4/d").

Servos HOLD their commanded position: this tool does NOT auto-return on exit, so
the arm stays where you sent it. The firmware must own /dev/ttyACM0 alone -- stop
mbed_driver before running this.
"""

import serial, time, sys

MIN_US, MAX_US = 500, 2500
MIN_DEG, MAX_DEG = 0.0, 180.0

shoulder = float(sys.argv[1])
elbow = float(sys.argv[2])
hold = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5


def to_us(deg):
    deg = max(MIN_DEG, min(MAX_DEG, deg))
    frac = (deg - MIN_DEG) / (MAX_DEG - MIN_DEG)
    return max(MIN_US, min(MAX_US, round(MIN_US + frac * (MAX_US - MIN_US))))


s = serial.Serial("/dev/ttyACM0", 115200, timeout=0.2)
us = [to_us(shoulder), to_us(elbow)]

try:
    print(
        f"NOW: shoulder={shoulder:.0f}deg({us[0]}us) "
        f"elbow={elbow:.0f}deg({us[1]}us), hold {hold}s"
    )
    s.write(f"{us[0]}/{us[1]}/a".encode())
    echo = ""
    t = time.time()
    while time.time() - t < 0.5:
        ln = s.readline().decode(errors="replace").strip()
        if "srv" in ln:
            echo = ln
    hint = "(none -- check wiring / is mbed_driver stopped?)"
    print(f"  firmware echo: {echo or hint}")
    time.sleep(hold)
    print(f"  DONE (servos hold {us[0]}/{us[1]}us; no auto-return).")
finally:
    s.close()
