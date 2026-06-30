#!/usr/bin/env bash
# ロボット一式（モーター driver + 前後カメラ + テレオプ WebSocket + 録画）を一発起動する。
# 4 つの launch を 1 プロセスから束ねて起動し、Ctrl+C でまとめて停止する。
#   カメラ: http://<このマシンのIP>:8080/   操縦: ws://<このマシンのIP>:9001
#
# 録画（データ取得）は episode_recorder が担い、コックピットからの開始/停止指令
# （teleop_server が /record_cmd に中継）で 1 エピソードずつ datasets/raw に記録する。
# つまり Pi 側のターミナルに触れずに、操縦と同じ画面から録画を開始・終了できる。
# 手元の対話録画（[Enter] 開始/停止）が要るときは代わりに start-record.sh を使う
# （両方を同時に走らせない）。
#
# 上書き可能な環境変数:
#   FRONT_DEVICE / REAR_DEVICE  カメラ device（start-cameras.sh と同じ）
#   RECORD_ROUTE / RECORD_OPERATOR  録画の既定ルート/操縦者（コックピット指令で上書き可）
source "$(dirname "$0")/lib-ros-env.sh"

# ここから先は複数ノードのオーケストレーション。子プロセスの終了で
# スクリプト全体を落とさないよう errexit は切る（停止は trap で集中管理）。
set +e

FRONT_DEVICE="${FRONT_DEVICE:-/dev/video0}"
REAR_DEVICE="${REAR_DEVICE:-/dev/video2}"
RECORD_ROUTE="${RECORD_ROUTE:-route_a}"
RECORD_OPERATOR="${RECORD_OPERATOR:-${USER:-unknown}}"

pids=()
cleanup() {
  trap - INT TERM EXIT   # 二重起動を防ぐ
  echo
  echo "停止中... 全ノードに SIGINT を送ります"
  for pid in ${pids[@]+"${pids[@]}"}; do
    kill -INT "$pid" 2>/dev/null || true
  done
  wait
  echo "停止完了"
}
trap cleanup INT TERM EXIT

echo "起動(1/4): drivetrain（モーター driver, /dev/ttyACM0）"
ros2 launch kuas_mechlab3 drivetrain_launch.py &
pids+=("$!")

echo "起動(2/4): cameras -> http://0.0.0.0:8080/ (front=${FRONT_DEVICE} rear=${REAR_DEVICE})"
ros2 launch kuas_mechlab3 cameras_launch.py \
  front_device:="${FRONT_DEVICE}" rear_device:="${REAR_DEVICE}" &
pids+=("$!")

echo "起動(3/4): teleop WebSocket -> ws://0.0.0.0:9001"
ros2 launch kuas_mechlab3 teleop_launch.py &
pids+=("$!")

echo "起動(4/4): episode_recorder -> /record_cmd を待受 (route=${RECORD_ROUTE} operator=${RECORD_OPERATOR})"
ros2 launch kuas_mechlab3 record_launch.py \
  route:="${RECORD_ROUTE}" operator:="${RECORD_OPERATOR}" &
pids+=("$!")

echo "全ノード起動完了。Ctrl+C で全停止。"
# いずれかの子が落ちてもこのスクリプトは待ち続け、Ctrl+C で trap が掃除する。
wait
