#!/usr/bin/env python3
"""Combined-motion bring-up: send one named command for a fixed time, auto-stop.
Mirrors kuas_mechlab3's kinematics so we can verify whole-robot motion safely.

Usage:  python3 pi-drivetest.py <cmd> [seconds]
  cmd: forward | backward | left | right | stop

left/right follow REP-103 (the same convention as kuas_mechlab3 with
turn_sign=+1.0): +wz = counter-clockwise = turn left. If the robot turns the
wrong way, that is a chassis/turn-sign issue — fix turn_sign in the driver
rather than editing this script (per-wheel FORWARD direction is owned by the
firmware DIR[] signs, verified with pi-jog.py).
The firmware must own /dev/ttyACM0 alone — stop mbed_driver before running this.
"""

import serial, time, sys

SPD = 10.5
# 4 setpoints in Pi order: s1=ch0, s2=ch1, s3=ch2, s4=ch3.
# Left side = s1,s2 ; Right side = s3,s4 (matches kinematics.py grouping).
CMDS = {
    "forward": (SPD, SPD, SPD, SPD),
    "backward": (-SPD, -SPD, -SPD, -SPD),
    "left": (-SPD, -SPD, SPD, SPD),  # left side rev, right fwd -> CCW (REP-103 +wz)
    "right": (SPD, SPD, -SPD, -SPD),  # left side fwd, right rev -> CW
    "stop": (0.0, 0.0, 0.0, 0.0),
}
cmd = sys.argv[1]
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
v = CMDS[cmd]

s = serial.Serial("/dev/ttyACM0", 115200, timeout=0.2)


def send(t):
    s.write(("/".join(f"{x:.1f}" for x in t) + "/d").encode())


try:
    send((0, 0, 0, 0))
    time.sleep(0.2)
    s.reset_input_buffer()
    print(f"NOW: {cmd.upper()}  setpoints(s1..s4)={v}  for {dur}s")
    send(v)
    t = time.time()
    last = ""
    while time.time() - t < dur:
        l = s.readline().decode(errors="replace").strip()
        if "pwm" in l:
            last = l
    send((0, 0, 0, 0))
    time.sleep(0.3)
    print(f"  last telemetry: {last}")
    print("  STOPPED.")
finally:
    send((0, 0, 0, 0))
    s.close()
