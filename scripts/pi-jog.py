#!/usr/bin/env python3
"""Bring-up jog tool: spin ONE wheel open-loop for a fixed time, auto-stop,
and report firmware-side proof (which PWM channel energized + any encoder rpm).

Usage:  python3 pi-jog.py <idx> [seconds]
  idx 0 = ch0 / motor1  (実機物理コーナー = 後左 BL)
      1 = ch1 / motor2  (実機物理コーナー = 前左 FL)
      2 = ch2 / motor3  (実機物理コーナー = 後右 BR)
      3 = ch3 / motor4  (実機物理コーナー = 前右 FR)

Sends the same 4-setpoint packet the teleop node uses: "s1/s2/s3/s4/d"
(115200 baud on /dev/ttyACM0 — identical to kuas_mechlab3's protocol.py).
Only the selected wheel gets a nonzero setpoint; the other three are held at 0
(firmware watchdog/hard-stop). Always sends an all-stop on exit.

A POSITIVE setpoint must drive the selected wheel FORWARD. If it spins backward,
flip that wheel's sign (DIR[idx]) in firmware/robot/src/main.cpp and re-flash.
The firmware must own /dev/ttyACM0 alone — stop mbed_driver before running this.
"""

import serial, time, sys

# Validated physical corners (jog test 2026-06-16): ch0=BL, ch1=FL, ch2=BR, ch3=FR.
NAMES = ["ch0 後左 BL", "ch1 前左 FL", "ch2 後右 BR", "ch3 前右 FR"]
MAG = 10.5
idx = int(sys.argv[1])
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
assert 0 <= idx <= 3

s = serial.Serial("/dev/ttyACM0", 115200, timeout=0.2)


def send(v):
    s.write(("/".join(f"{x:.1f}" for x in v) + "/d").encode())


def parse(ln):
    pwm = rpm = None
    if "pwm" in ln and "rpm" in ln:
        try:
            pwm = [int(x) for x in ln.split("pwm")[1].split()]
            rpm = [float(x) for x in ln.split("rpm")[1].split("|")[0].split()]
        except Exception:
            pass
    return pwm, rpm


try:
    send([0, 0, 0, 0])
    time.sleep(0.2)
    s.reset_input_buffer()
    v = [0.0, 0.0, 0.0, 0.0]
    v[idx] = MAG
    print(f"NOW SPINNING: {NAMES[idx]}  (setpoint {MAG}, {dur}s)  — watch this wheel")
    send(v)
    t = time.time()
    peak = [0, 0, 0, 0]
    rpm_seen = []
    while time.time() - t < dur:
        pwm, rpm = parse(s.readline().decode(errors="replace").strip())
        if pwm:
            for i in range(4):
                peak[i] = max(peak[i], abs(pwm[i]))
        if rpm:
            rpm_seen.append(abs(rpm[idx]))
    send([0, 0, 0, 0])
    time.sleep(0.3)
    s.reset_input_buffer()
    stop_line = ""
    t = time.time()
    while time.time() - t < 0.5:
        l = s.readline().decode(errors="replace").strip()
        if "pwm" in l:
            stop_line = l
    others = max(peak[i] for i in range(4) if i != idx)
    er = max(rpm_seen) if rpm_seen else 0.0
    print(
        f"RESULT driven=ch{idx} peak_pwm={peak[idx]}  other_channels_max_pwm={others}  "
        f"peak_pwm_all={peak}"
    )
    print(
        f"  encoder_rpm_on_this_wheel(max)={er:.1f}   (0.0 = encoder silent, expected on this kit)"
    )
    print(f"  after_stop: {stop_line}")
    if peak[idx] > 100 and others < 100:
        print("  -> OK: firmware energized ONLY this wheel's channel.")
    elif others >= 100:
        print("  -> WARNING: another channel also moved — possible wiring/pin cross.")
    else:
        print(
            "  -> WARNING: this wheel's channel never energized — check command path."
        )
finally:
    send([0, 0, 0, 0])
    s.close()
