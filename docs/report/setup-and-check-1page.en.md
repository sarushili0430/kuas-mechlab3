# ML3 Teleoperated Robot — Setup and Verification

KUAS MechLab3 / Team 11 — `kuas-mechlab3` (robot side) · `kuas-mechlab3-cockpit` (operator UI)

Setup and verification for the four-wheel skid-steer robot **ML3**. The system has three layers — control (STM32
NUCLEO-F091RC / Mbed OS 6), integration (Raspberry Pi / ROS 2 Humble) and teleoperation (web cockpit) — and
**both the build and the checks go from the bottom layer up**.

## 1. Required environment

| Target | Tooling | Notes |
| --- | --- | --- |
| Nucleo | PlatformIO Core | `pip install platformio`. Builds the Mbed OS 6 firmware |
| Raspberry Pi | Ubuntu 22.04 + ROS 2 Humble / Python 3.10.18 | Python version is pinned by `.python-version` |
| Operator PC | Node.js + pnpm 11.5 | Builds the cockpit (Vite + React 19 + TypeScript). No ROS needed |

## 2. Setup

**① Microcontroller firmware** — connect the Nucleo over the ST-Link USB port and flash it. The wire contract with
the host is a text protocol — `s1/s2/s3/s4/d` (drive), `<shoulder_us>/<elbow_us>/a` (servo), `<0|1>/l` (LED) — with
telemetry at 50 Hz. Enable floating-point output in `mbed_app.json` (see §4).

```bash
pip install platformio
cd firmware/robot && pio run && pio run -t upload   # build -> flash over ST-Link
```

**② Robot side (Raspberry Pi)** — the repository root doubles as the colcon workspace. Runtime dependencies
(`rclpy`, `python3-opencv`, `python3-websockets`, `ros2bag`, …) are declared in `package.xml` and resolved by
`rosdep`; only `ultralytics`, which has no rosdep key, is installed with pip.

```bash
sudo usermod -aG dialout $USER          # serial permission (once; takes effect after re-login)
git clone git@github.com:sarushili0430/kuas-mechlab3.git && cd kuas-mechlab3
source /opt/ros/humble/setup.bash && export ROS_DOMAIN_ID=0    # team separation; keep it identical in every terminal
rosdep install --from-paths src --ignore-src -r -y             # first time only
colcon build --packages-select kuas_mechlab3 && source install/setup.bash
pip install ultralytics && ./scripts/prefetch-model.sh         # traffic-light detection (YOLOv8) + weights prefetch
```

**③ Operator PC (cockpit UI)** — keep it on the same LAN as the robot. In competition the build output is served on
`:8000` from the Pi by `ml3-cockpit.service`. HTTPS is not an option: the `http://` video and the `ws://` teleop
channel are blocked as mixed content.

```bash
git clone git@github.com:sarushili0430/kuas-mechlab3-cockpit.git && cd kuas-mechlab3-cockpit
pnpm install && pnpm build      # install deps (also enables the Git hooks) -> emit dist/
```

## 3. Verification (isolate from the bottom layer up)

**Always run these with the wheels off the ground** (full-duty PWM will drive the robot off the bench, and the
inrush current is significant).

| # | Target | Command | Expected result / decision |
| --- | --- | --- | --- |
| 1 | Pure logic | `pytest` | Kinematics, wire format and colour decision pass — `rclpy`-free pure functions, verifiable without the robot |
| 2 | Firmware alone | `stty -F /dev/ttyACM0 115200 raw -echo` → `cat /dev/ttyACM0` → `printf '3.00/3.00/3.00/3.00/d' > /dev/ttyACM0` | Telemetry streams at 50 Hz; all four wheels spin and stop after 0.5 s (single-process port — run with `mbed_driver` stopped) |
| 3 | Wheel direction | `python3 scripts/pi-jog.py 0` (then 1, 2, 3) / `python3 scripts/pi-drivetest.py forward` | A backwards wheel: flip `MOTOR_DIR[i]` and reflash. If **only the turn** is inverted it is a left/right assignment problem — use `turn_sign:=-1.0` |
| 4 | Camera identity | `./scripts/detect-cameras.sh` | Pin the cameras by USB port (`by-path`); `/dev/videoN` re-enumerates each boot |
| 5 | Whole stack | `./scripts/start-all.sh` → `ros2 node list \| sort` (+ `uniq -d`) | 8 nodes, no duplicates (a duplicate means the stack launched twice) |
| 6 | Video | `ros2 topic hz /front_camera/image_raw/compressed` | Roughly 20 Hz, and both panes update at `http://<ROBOT_IP>:8080/` |
| 7 | Teleop | Open `http://<ROBOT_IP>:8000/`, set the host to the Pi's IP, press connect | Connection pill turns green; **W/A/S/D** drives, **arrow keys** move the arm, releasing a key stops the robot |

## 4. Problems hit and fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Telemetry arrives as literal `sp %f ...`, so every line is discarded | Mbed OS 6's default printf lacks `%f` | Enable float printf in `mbed_app.json` |
| Front and rear cameras swap | `/dev/videoN` is reassigned on boot; the two C270s share a serial (`by-id` cannot separate them) | Pin them by USB port (`by-path`) |
| Duplicate nodes; the rear camera never appears | An older autostart unit launches the stack twice | Disable the competing unit |
| Traffic-light node fails to start at the venue | YOLO weights were downloaded on first run | Run `prefetch-model.sh` first |

---

# Appendix — Document style

The report above is written in Markdown and converted to a `.docx` for submission. Everything below is the
formatting spec used for that conversion; follow it to reproduce the same document. **The appendix itself is not
part of the deliverable** — only the report above §"Appendix" goes on the page.

## A. Layout target

- **One A4 page.** This is a hard constraint — the content is trimmed until it fits, not scaled down further.
- Page size A4 (210 × 297 mm), portrait, **15 mm margins** on all four sides (content width 180 mm).
- No headers, footers or page numbers. No table of contents.
- Always render the result and look at it. The English text above fills the page with roughly 10 mm to spare,
  so a font substitution on another machine can push the last table row over — if that happens, trim by §F
  rather than shrinking the type.

## B. Typography

The original is Japanese and uses Yu Gothic. **For the English build, swap the body face for a Latin sans**
(Source Sans 3, Calibri or Arial all work); keep every size and spacing value below unchanged.

| Element | Font | Size | Spacing |
| --- | --- | --- | --- |
| Title (`#`) | body, bold | 13 pt | 3 pt after |
| Section heading (`##`) | body, bold | 10 pt | 6.5 pt before, 2.5 pt after |
| Sub-heading (`###`) | body, bold | 8.5 pt | 5 pt before, 2 pt after |
| Body text | body | 9 pt | 2.5 pt after, line spacing 0.92 |
| Table cells | body | 7.5 pt | line spacing 0.82 |
| Code block | monospace (Consolas) | 7 pt | line spacing 0.75 |
| Inline code | monospace | 1 pt smaller than its surrounding text | — |

Body text colour is near-black `#1A1A1A` rather than pure black.

## C. Tables

- Width: the **full content width** (180 mm). Column widths are proportional to the widest cell in each column,
  damped by a square root so one long cell cannot starve the others, with a minimum column width.
- Header row: bold, shaded `#EDEFF2`, and marked as a repeating header row.
- Borders: 0.25 pt solid `#BFC4CC` on every edge, inside and out.
- Cell padding: 0.5 mm top/bottom, 1.6 mm left/right.

## D. Code blocks

- Shaded `#F2F3F5`, indented 3 mm on both sides, no border.
- One paragraph per line (no soft wrapping inside a block), 4 pt of space above and 3.5 pt below the block.
- Keep every line short enough to fit the content width; a wrapped code line reads as a formatting bug.
  Inline comments (`# …`) are aligned by hand.

## E. Markdown conventions used

- `**bold**` and `` `code` `` are the only inline formats; `code` inside `**bold**` keeps both.
- Soft line wraps inside a paragraph are joined into a single paragraph — the hard wrapping in the source is
  for readability of the Markdown, not a paragraph break. A blank line is a real paragraph break.
- Escape pipes inside table cells as `\|`.
- `---` renders as a horizontal rule (a thin bottom border on an empty paragraph), used once to separate the
  report from this appendix.

## F. What to trim first when it does not fit

In order, because each step costs the least information:

1. Shorten table cells so a row occupies one line instead of two — this is where most of the height goes.
2. Rewrite a three-line paragraph into two; drop restatements of something a table already says.
3. Merge adjacent short tables, or fold a table's least important column into another one.
4. Only then drop content, and say what was dropped rather than silently truncating.

Do **not** reduce the font size or the margins further to make it fit; below the sizes in §B the tables stop
being readable when printed.

## G. Producing the file

Two routes, both fine:

- **By hand in Word / Google Docs.** Set up §A, then define four paragraph styles (title, heading, body, code)
  and one table style from §B–§D and apply them. Everything above is expressed in pt and mm for this reason.
- **Scripted.** Convert the Markdown with a small script (this document was produced with a ~250-line Node
  script over the [`docx`](https://www.npmjs.com/package/docx) package) or with Pandoc plus a reference
  `.docx` carrying the styles above. Scripting is worth it if the text will be revised more than once, since
  fitting the page takes several trim-and-re-render rounds.

Either way, render to PDF and read the pages before sending it. Two failure modes are invisible in the
Markdown and obvious in the render: a table splitting across pages with one row orphaned, and a code line
wrapping.
