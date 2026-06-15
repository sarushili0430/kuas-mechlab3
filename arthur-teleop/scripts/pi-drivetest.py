#!/usr/bin/env python3
"""Combined-motion bring-up: send one named command for a fixed time, auto-stop.
Mirrors the teleop node's mixing so we can verify whole-robot motion safely.

Usage:  python3 pi-drivetest.py <cmd> [seconds]
  cmd: forward | backward | left | right | stop
  (left/right use the SAME mixing as the teleop 'a'/'d' keys.)
"""
import serial, time, sys

SPD = 10.5
# 4 setpoints in Pi order: s1=M1 FL, s2=M2 BL, s3=M3 BR, s4=M4 FR.
CMDS = {
    "forward":  ( SPD,  SPD,  SPD,  SPD),
    "backward": (-SPD, -SPD, -SPD, -SPD),
    "left":     ( SPD,  SPD, -SPD, -SPD),   # teleop 'a' : left side +, right side -
    "right":    (-SPD, -SPD,  SPD,  SPD),   # teleop 'd' : left side -, right side +
    "stop":     ( 0.0,  0.0,  0.0,  0.0),
}
cmd = sys.argv[1]
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
v = CMDS[cmd]

s = serial.Serial("/dev/ttyACM0", 115200, timeout=0.2)
def send(t): s.write(("/".join(f"{x:.1f}" for x in t) + "/d").encode())
try:
    send((0,0,0,0)); time.sleep(0.2); s.reset_input_buffer()
    print(f"NOW: {cmd.upper()}  setpoints(s1..s4)={v}  for {dur}s")
    send(v)
    t = time.time(); last = ""
    while time.time() - t < dur:
        l = s.readline().decode(errors="replace").strip()
        if "pwm" in l: last = l
    send((0,0,0,0)); time.sleep(0.3)
    print(f"  last telemetry: {last}")
    print("  STOPPED.")
finally:
    send((0,0,0,0)); s.close()
