#!/usr/bin/env bash
# ロボット一式（モーター driver + 前後カメラ + テレオプ WebSocket + 録画コントロール
# + 信号機検出 + QR 読み取り）を一発起動する。6 つの launch を 1 プロセスから束ねて起動し、
# Ctrl+C でまとめて停止する。boot 時から常駐させたいときは scripts/kuas-mechlab3.service を参照。
#   カメラ: http://<このマシンのIP>:8080/   操縦: ws://<このマシンのIP>:9001
#   録画:   http://<このマシンのIP>:9002/record/status（スマホの REC ボタンから叩く）
#   信号機: traffic_light_topic に「<team>Green」等を publish（緑でバリアが開く）
#   QR:     qr_topic に payload を publish し、読めている間だけ機体 LED を点灯（課題 #5）
#
# 上書き可能な環境変数: FRONT_DEVICE / REAR_DEVICE（start-cameras.sh と同じ）
#   ROUTE / OPERATOR  録画のルート名 / 操縦者名（既定 route_a / unknown）
#   TEAM_NUMBER       信号機メッセージのチーム番号（既定 11）
source "$(dirname "$0")/lib-ros-env.sh"

# ここから先は複数ノードのオーケストレーション。子プロセスの終了で
# スクリプト全体を落とさないよう errexit は切る（停止は trap で集中管理）。
set +e

FRONT_DEVICE="${FRONT_DEVICE:-/dev/video0}"
REAR_DEVICE="${REAR_DEVICE:-/dev/video2}"
ROUTE="${ROUTE:-route_a}"
OPERATOR="${OPERATOR:-unknown}"
TEAM_NUMBER="${TEAM_NUMBER:-11}"

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

echo "起動(1/6): drivetrain（モーター driver, /dev/ttyACM0）"
ros2 launch kuas_mechlab3 drivetrain_launch.py &
pids+=("$!")

echo "起動(2/6): cameras -> http://0.0.0.0:8080/ (front=${FRONT_DEVICE} rear=${REAR_DEVICE})"
ros2 launch kuas_mechlab3 cameras_launch.py \
  front_device:="${FRONT_DEVICE}" rear_device:="${REAR_DEVICE}" &
pids+=("$!")

echo "起動(3/6): teleop WebSocket -> ws://0.0.0.0:9001"
ros2 launch kuas_mechlab3 teleop_launch.py &
pids+=("$!")

echo "起動(4/6): 録画コントロール -> http://0.0.0.0:9002/record/status (route=${ROUTE} operator=${OPERATOR})"
ros2 launch kuas_mechlab3 record_launch.py route:="${ROUTE}" operator:="${OPERATOR}" &
pids+=("$!")

echo "起動(5/6): 信号機検出 -> traffic_light_topic (team=${TEAM_NUMBER}, 前カメラトピック購読)"
ros2 launch kuas_mechlab3 traffic_launch.py team_number:="${TEAM_NUMBER}" &
pids+=("$!")

echo "起動(6/6): QR 読み取り -> qr_topic + 機体 LED（課題 #5、前カメラトピック購読）"
ros2 launch kuas_mechlab3 qr_launch.py &
pids+=("$!")

echo "全ノード起動完了。Ctrl+C で全停止。"
# いずれかの子が落ちてもこのスクリプトは待ち続け、Ctrl+C で trap が掃除する。
wait
