#!/usr/bin/env bash
# テレオプ WebSocket ブリッジ（teleop_server）を一発起動する。
# 操縦者の PC からの JSON 指令 {"vx","wz"} を受け取り cmd_vel に流す。
#   待ち受け: ws://<このマシンのIP>:9001
#
# launch 引数はそのまま渡せる:
#   ./scripts/start-teleop.sh port:=9001 max_linear:=0.5
source "$(dirname "$0")/lib-ros-env.sh"

echo "起動: teleop WebSocket -> ws://0.0.0.0:9001"
exec ros2 launch kuas_mechlab3 teleop_launch.py "$@"
