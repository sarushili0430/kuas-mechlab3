# Servo + Green-LED Control — Design & Test Spec

Date: 2026-07-14 · Branch: `arthur/dev` (local, not pushed) · Status: approved, pre-implementation

## Goal
Add 2-DoF arm (2× DS3225 servo) + a green indicator LED on top of the working drive
firmware, testable end-to-end two ways: direct-serial CLI bring-up first, then through the
existing teleop cockpit UI. **Nothing that currently drives may regress.**

## Verified hardware facts (datasheet-checked 2026-07-14)
- Servo 1 (shoulder): pad **PB_14**, token `PB_14_ALT0` → **TIM15_CH1 (AF1)**.
- Servo 2 (elbow):   pad **PB_15**, token `PB_15_ALT1` → **TIM15_CH2 (AF1)**.
  Confirmed vs Mbed `PeripheralPins.c` (NUCLEO_F091RC) + STM32F0 AF table. Plain
  `PB_14`/`PB_15` map to TIM1_CH2N/CH3N — the *motors'* timer — so the `_ALT` tokens are required.
- Green LED: pad **D3 (PB_3)**, plain `DigitalOut` (no PWM; PB_3 absent from Mbed PWM map).
  220 Ω series resistor, already soldered.
- Servos: signal-only to the Nucleo; V+/GND on the dedicated 5–6 V servo rail; common ground.

## Approach
Reuse PR #18's proven servo interface (pins / protocol / clamp / jog / tests), **ported onto
the current firmware** — keep `MOTOR_DIR {+1,-1,+1,-1}` and `PWM_CAP 4000`; do **not** merge
PR #18's stale `main.cpp`. Add the green LED as a new independent command. For the UI, mirror
the existing drive pipeline (cockpit → WS → teleop_server → topic → mbed_driver → serial).

## Wire protocol (three independent packets, /dev/ttyACM0 @ 115200)
- Drive (unchanged): `s1/s2/s3/s4/d` — 4 floats, `d` EOP. Heartbeat + watchdog.
- Servo (PR #18):     `us1/us2/a`     — 2 ints µs, `a` EOP. Echo `srv us1 us2`. **Latched** (held).
- LED (new):          `v/l`           — v∈{0,1}, `l` EOP. Echo `led v`. **Latched**.

Distinct EOP bytes ⇒ firmware parses each independently; the drive format is untouched.

## Firmware — `firmware/robot/src/main.cpp` (additive only)
- `ServoOut` class: 50 Hz, idle pulse 0, clamp 500–2500 µs, holds last pulse, **not** on the drive watchdog.
- `SERVO_PINS = {PB_14_ALT0, PB_15_ALT1}`; parse `a` packet → apply both, echo `srv`.
- `DigitalOut led(D3)`; parse `l` packet → set, echo `led`.

## Pi package — `src/kuas_mechlab3/kuas_mechlab3/…`
- `drive/protocol.py`: PR #18 servo fns (`format_servo_us`, `angle_to_us`, `parse_servo_echo`)
  + new `LED_EOP='l'`, `format_led(on)`, `parse_led_echo`. Pure, unit-tested.
- `drive/serial_link.py`: PR #18 `send_servo_us` + new `send_led`.
- `drive/teleop_command.py`: new pure parsers `parse_servo_command` / `parse_led_command` (JSON→data).
- `drive/teleop_server.py`: WS handler dispatches by message shape — `{vx,wz}`→`cmd_vel` (today);
  `{servo:[sh,el]}`→publish `servo_cmd` (Float32MultiArray, degrees); `{led:bool}`→publish
  `led_cmd` (Bool). Servo/LED are **event-published on receipt** (latched), not on the drive
  heartbeat, and not zeroed by the failsafe.
- `drive/mbed_driver.py`: subscribe `servo_cmd` → `send_servo_us(angle_to_us(...))`;
  subscribe `led_cmd` → `send_led`. (PR #18 supplies the servo half.)

## Cockpit UI — `docs/cockpit.html`
Add two range sliders (shoulder / elbow, 0–180°) sending `{"servo":[sh,el]}` on input, and an
LED on/off toggle sending `{"led":true|false}`. Drive (WASD) unchanged.

## Test plan
- **Logic** (laptop pytest, no hardware): `test_protocol` servo+LED round-trips + clamp;
  `test_teleop_command` servo/led parse (valid / invalid / partial). Run before flashing.
- **Tier 1 — isolate hardware** (Pi, after flash, in order):
  1. `pio run` (green) → 2. `pio run -t upload` → 3. **drive regression** (`pi-jog` wheels 1–4
  unchanged) → 4. `pi-servojog` mid then small sweep (both move, echo `srv`) → 5. `pi-ledtest`
  on/off (LED + echo) → 6. watchdog/hold (servos hold, drive stops).
- **Tier 2 — cockpit UI** (Pi ROS stack + browser): sliders move the servos, toggle lights the
  LED, WASD still drives. Confirms the operator path.

## Flash (Pi via SSH)
`arthur/dev` stays local → rsync `firmware/robot` to the Pi, `pio run -t upload` there, on the
user's "flash" go. Pre-flash: servo rail 5–6 V + ≥1000 µF cap + common ground.

## Deferred / non-goals
- Logging servo/LED into `cmd_norm` for imitation learning (separate action-space decision).
- Servo preset positions (need bring-up calibration first).
- RGB "change colour" for the QR task — hardware is a single green LED for now (on/off only).

## Commits
All on `arthur/dev`, local, no push.
