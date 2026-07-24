# ML3 Robot MCP server

An [MCP](https://modelcontextprotocol.io) server that lets a **local Claude** (e.g. Claude
Code) drive the KUAS MechLab3 robot, see through its cameras, and control dataset recording —
by speaking the robot's existing LAN protocols as a client. **stdio transport, no
authentication** (LAN-local use only).

It is deliberately **standalone**: its own `pyproject.toml`, only `mcp` + `websockets` + `httpx`,
and **no ROS 2 / colcon**. Run it on any machine on the robot's Wi‑Fi, next to the MCP client.

> ⚠️ **Reachability.** The server connects to the robot over the LAN (`ws://<host>:9001`,
> `http://<host>:8080`, `http://<host>:9002`). Claude/Claude Code **and** this server must run on
> a machine that can reach the robot. A cloud/remote Claude Code cannot reach a LAN robot — use a
> laptop on the same Wi‑Fi. To develop/test without hardware, use the bundled mock (below).

## Tools

| Tool | What it does |
|---|---|
| `drive(vx, wz, duration_s=0.5)` | Hold a normalized velocity (`vx`/`wz` in `-1..1`, `vx>0` forward, `wz>0` left) for a bounded time at ~20 Hz, then **auto‑stop**. Axes are scaled by `ML3_SPEED_SCALE`; `duration_s` is capped by `ML3_MAX_DURATION_S`. |
| `stop()` | Immediately send zero velocity. |
| `capture_camera(which="front")` | Grab one still frame (`front`/`rear`) and return it as an image Claude can see. |
| `record_status()` / `record_start(...)` / `record_stop(...)` / `record_discard()` | Control imitation‑learning recording (rosbag) on port 9002. |

The teleop channel has **no acknowledgement** — the robot never confirms motion. The right loop
is **look → move a little → look again**: `capture_camera` before and after each `drive`.

## Configuration (environment variables)

| Var | Default | Meaning |
|---|---|---|
| `ML3_HOST` | `192.168.1.42` | Robot IP / hostname |
| `ML3_WS_PORT` | `9001` | Teleop WebSocket port |
| `ML3_CAM_PORT` | `8080` | Camera MJPEG port |
| `ML3_REC_PORT` | `9002` | Recording HTTP port |
| `ML3_SPEED_SCALE` | `0.5` | Global speed governor (0–1) applied to every `drive` axis — keep low while testing |
| `ML3_MAX_DURATION_S` | `3.0` | Hard cap on a single `drive` command's duration |

## Install & run

With [uv](https://docs.astral.sh/uv/) (recommended — handles the venv and deps for you):

```bash
cd mcp-server
uv run ml3-mcp          # starts the stdio server
```

Or a plain venv:

```bash
cd mcp-server
python -m venv .venv && . .venv/bin/activate
pip install -e .
ml3-mcp                 # or: python -m ml3_mcp.server
```

## Register with Claude Code

A project‑scoped `.mcp.json` is provided at the **repo root** (`kuas-mechlab3/.mcp.json`) — open
Claude Code from `kuas-mechlab3/` and it will offer to load the `ml3-robot` server. Set your
robot's IP there via `ML3_HOST`. Alternatively, add it explicitly:

```bash
# from the repo root; adjust the command to your install (uv or the venv's ml3-mcp)
claude mcp add ml3-robot -e ML3_HOST=192.168.1.42 -e ML3_SPEED_SCALE=0.5 \
  -- uv run --directory mcp-server ml3-mcp
```

Confirm with `claude mcp list` or `/mcp`.

## Driving a course autonomously

Interactive Claude **is** the perceive‑act loop. Give it the course and let it use the tools.
Recommended model: **Claude Sonnet 5** (`claude-sonnet-5`) — strong vision + tool use, low
latency, cheap; step up to **Opus 4.8** (`claude-opus-4-8`, optionally Fast mode) for hard
navigation. Prompt template:

```
You are driving the ML3 robot via MCP tools. You cannot see the robot except through
capture_camera, and drive commands are NOT acknowledged.

COURSE OVERVIEW:
<one-paragraph description of the course / environment>

WAYPOINTS (in order):
1. <landmark / what you'll see> — <what to do: e.g. "go straight until the red cone">
2. <...>
3. <...>

RULES:
- Work one waypoint at a time. Before every move, call capture_camera("front") and describe
  what you see and how it maps to the current waypoint.
- Move in SHORT bursts: a single drive(...) with a small duration_s (start ~0.3–0.6s), then
  stop() and capture_camera again to check the result. Never chain multiple drives blind.
- Keep speeds modest. Turn with wz; go forward with a small positive vx. If unsure, move less.
- If a frame is ambiguous or you might hit something, stop() and re-capture instead of guessing.
- Announce when you believe a waypoint is reached, then proceed to the next.
- Say "COURSE COMPLETE" when the final waypoint is done, and stop().
```

## Testing (no hardware)

```bash
# unit + integration tests (spins up the in-process mock on real sockets)
uv run --extra dev pytest          # or: pip install -e '.[dev]' && pytest

# manual: run the mock, then drive it from the MCP Inspector or Claude Code
python mock_robot.py               # serves WS 9001 + HTTP 8080/9002 on 127.0.0.1
ML3_HOST=127.0.0.1 uv run ml3-mcp  # point the server at the mock
```

`tests/` covers: the MJPEG frame parser, `drive` clamping/duration cap + always‑stop, record
payload/409 handling, an end‑to‑end pass against the mock, and tool registration.
