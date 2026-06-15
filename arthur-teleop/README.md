# ML3 Drivetrain Teleop — Reference Bundle

A **self-contained, hardware-validated** reference for driving the Team 11
("Tomoe-11") **4-motor skid-steer drivetrain** by keyboard. It is independent of
the rest of this repository — everything you need is in this folder.

- **Microcontroller:** STM32 **NUCLEO-F091RC** (Mbed OS firmware)
- **Companion computer:** Raspberry Pi 4 (Ubuntu 22.04 + **ROS 2 Humble**)
- **Motor drivers:** 2x **L298N** dual H-bridge -> 4 geared DC motors
- **Link:** Pi <-> Nucleo over the Nucleo's **mini-USB** (USB serial `/dev/ttyACM0`, 115200 baud)

Validated end-to-end on the hand-soldered robot: per-wheel direction, forward,
backward, and both turns.

## Layout
```
arthur-teleop/
├── firmware/robot/     STM32 Mbed firmware (PlatformIO project)
├── ros2/mbedros2/      ROS 2 package — keyboard teleop node (mbed_motor_ctrl)
├── scripts/            pi-drive.sh (launch teleop) · pi-jog.py (one-wheel test) · pi-drivetest.py (combined)
└── docs/               robot-pinout-power-reference.md / .pdf  (full pin map, wiring, power)
```

## How it works
The Pi sends four motor setpoints per packet over USB serial; the firmware drives
the four wheels and streams telemetry back.

- **Command (Pi -> Nucleo):** `s1/s2/s3/s4/d` — four floats, `/`-separated, `d` = end-of-packet, at 115200 baud.
  `s1..s4` map to motor1..motor4. **Left side = motor1 + motor2, right side = motor3 + motor4.**
- **Telemetry (Nucleo -> Pi):** `sp .. | rpm .. | pwm ..` (setpoints, measured rpm, applied PWM).

---

## Prerequisites

**Build machine** (compiles + flashes the firmware — can be the Pi itself):
- [PlatformIO Core](https://docs.platformio.org/en/latest/core/installation/index.html): `pip install platformio` (provides the `pio` command).

**Raspberry Pi** (runs the teleop):
- Ubuntu 22.04 + **ROS 2 Humble** at `/opt/ros/humble`, with `colcon`.
- Python `pyserial`: `python3 -c "import serial" 2>/dev/null || pip3 install pyserial` (or `sudo apt install -y python3-serial`).
- Your user in the **`dialout`** group (for serial access):
  ```bash
  groups | grep -q dialout || { sudo usermod -aG dialout "$USER"; echo "log out and back in to apply"; }
  ```

**Wiring** — full pin map in [`docs/robot-pinout-power-reference.md`](docs/robot-pinout-power-reference.md). The essentials that make or break it:
- On each L298N: **both `ENA` and `ENB` jumpers ON** (speed PWM rides the IN pins) and the `5V-EN` jumper ON.
- **Common ground is mandatory** — LiPo(-), both L298N GND, and the Nucleo GND all tie to one node. The Nucleo is powered from the Pi's USB, so without a Nucleo<->L298N ground wire the drivers cannot read the control signals and the motors will not move.
- **Motor power:** LiPo 3S (~11.1 V) -> both L298N `VS` through a ~5 A inline fuse. The Nucleo is **not** powered from the LiPo.

---

## Step 1 — Build & flash the firmware

```bash
cd firmware/robot
pio run                        # compile -> .pio/build/nucleo_f091rc/firmware.bin
```

Flash by **either** method:

- **A — ST-Link** (host with the Nucleo on USB and ST-Link udev rules):
  ```bash
  pio run -t upload            # upload_protocol = stlink
  ```
- **B — USB mass-storage** (works everywhere, including directly on the Pi): the Nucleo
  mounts as a USB drive named `NOD_F091RC` (some hosts show `NODE_F091RC`). Copy the binary onto it:
  ```bash
  cp .pio/build/nucleo_f091rc/firmware.bin /media/$USER/NOD_F091RC/ && sync
  # wait ~4 s — the bootloader flashes it and the board re-enumerates as /dev/ttyACM0
  ```
  *Building on WSL2:* build on WSL2, `scp firmware.bin` to the Pi, then run method **B** on the Pi.

Confirm the firmware is alive:
```bash
ls /dev/ttyACM*                                                    # expect /dev/ttyACM0
stty -F /dev/ttyACM0 115200 raw -echo; timeout 2 cat /dev/ttyACM0  # streams "sp .. | rpm .. | pwm .."
```

---

## Step 2 — Deploy the ROS 2 package on the Pi

```bash
mkdir -p ~/ros2_ws/src
cp -r ros2/mbedros2 ~/ros2_ws/src/
cd ~/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select mbedros2
source install/setup.bash
```

Copy the helper scripts to your home directory:
```bash
cp scripts/pi-drive.sh ~/drive.sh
cp scripts/pi-jog.py scripts/pi-drivetest.py ~/
chmod +x ~/drive.sh ~/pi-jog.py ~/pi-drivetest.py
```

---

## Step 3 — Verify wheel directions (once per build)

**Put the robot on a stand so all wheels spin freely off the ground, then connect the motor battery.**

Jog each wheel — index `0..3` -> motor1..motor4 (optional 2nd arg = seconds, default 1.5):
```bash
python3 ~/pi-jog.py 0     # then 1, 2, 3
```
Each wheel should spin so the robot would roll **forward**. The tool also reports that only that wheel's
PWM channel energized. If a wheel turns the wrong way, flip its sign in `firmware/robot/src/main.cpp` and
rebuild + reflash (Step 1):
```c
#define DIR1 (-1)   // flip +1 <-> -1 for the reversed wheel (DIR1..DIR4 = motor1..motor4)
```

Combined-motion check:
```bash
python3 ~/pi-drivetest.py forward     # also: backward | left | right | stop
```

---

## Step 4 — Keyboard teleop

Run the node **in a terminal on the Pi** so the Pi's own keyboard drives the robot:
```bash
bash ~/drive.sh
```
Controls — **hold to move; releasing auto-stops after ~0.4 s**:

| Key | Action |
|-----|--------|
| `w` / `s` | forward / backward |
| `a` / `d` | turn left / turn right |
| `q` | stop |
| `1` `2` `3` `4` | jog one wheel (bring-up) |

To pop the teleop terminal onto the Pi's **HDMI screen from a remote SSH session**:
```bash
ssh <user>@<pi-ip> 'DISPLAY=:0 mate-terminal --title="ML3 Teleop" -e "bash ~/drive.sh"'
```

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| No `/dev/ttyACM0` | Nucleo mini-USB plugged into the Pi; re-flash if just connected; `dmesg \| tail`. |
| `termios.error` / permission denied on serial | user in `dialout` (re-login), or `sudo chmod 666 /dev/ttyACM0` for the session. |
| Firmware streams telemetry but **no wheel moves** | L298N power LED lit? motor battery + ~5 A fuse seated? `ENA`/`ENB` jumpers ON? **common ground** wired between the Nucleo and the L298N? |
| One wheel spins the wrong way | flip that wheel's `DIRn` in `main.cpp`, rebuild + reflash. |
| `a` / `d` turn the wrong way | swap `turnLeft` / `turnRight` in `ros2/mbedros2/mbedros2/mbed_motor_ctrl.py` to match your chassis. |

## Notes
- **Open-loop:** the encoders are unused in this reference, so the firmware's `PWM_CAP` (in `main.cpp`, default `1500` ~ 37.5 %) sets the speed — raise it toward `4000` for full speed once directions are confirmed.
- **ROS domain:** `drive.sh` exports `ROS_DOMAIN_ID=11`; change it if your network needs a different domain.
- **Safety:** keep the wheels off the ground until directions are confirmed; `q` is an immediate stop.
