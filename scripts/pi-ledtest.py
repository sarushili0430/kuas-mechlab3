#!/usr/bin/env python3
"""Bring-up tool: toggle the on-board green LED and print the firmware echo as
proof the command reached the Nucleo.

Usage:  python3 pi-ledtest.py on|off

Sends the "v/l" LED packet (v=1 on / 0 off, 'l' end-of-packet) on 115200 baud
/dev/ttyACM0 and waits for the firmware's "led v" echo. It never touches the
4-wheel drive packet ("s1/s2/s3/s4/d") or the servo packet ("us1/us2/a"); the
firmware parses all three independently on distinct terminators.

The LED HOLDS its state -- this tool does NOT auto-clear on exit. The firmware
must own /dev/ttyACM0 alone -- stop mbed_driver before running this.
"""

import serial, sys, time

if len(sys.argv) != 2 or sys.argv[1] not in ("on", "off"):
    sys.exit("usage: python3 pi-ledtest.py on|off")

on = sys.argv[1] == "on"
packet = f"{1 if on else 0}/l"

s = serial.Serial("/dev/ttyACM0", 115200, timeout=0.2)
try:
    print(f"LED -> {'ON' if on else 'OFF'}  (sending {packet!r})")
    s.write(packet.encode())
    echo = ""
    t = time.time()
    while time.time() - t < 0.5:
        ln = s.readline().decode(errors="replace").strip()
        if "led" in ln:
            echo = ln
    hint = "(none -- check wiring / is mbed_driver stopped?)"
    print(f"  firmware echo: {echo or hint}")
finally:
    s.close()
