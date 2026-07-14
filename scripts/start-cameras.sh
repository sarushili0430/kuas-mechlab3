#!/usr/bin/env bash
# 前後カメラ + MJPEG 配信（cameras_launch.py）を一発起動する。
# 前後 2 つの camera_node が JPEG を publish し、mjpeg_server がブラウザへ中継する。
#   待ち受け: http://<このマシンのIP>:8080/
#
# 上書き可能な環境変数:
#   FRONT_DEVICE  前カメラの device（既定 /dev/video0。ls /dev/video* で確認）
#   REAR_DEVICE   後カメラの device（既定 /dev/video2）
# 追加の launch 引数もそのまま渡せる:
#   ./scripts/start-cameras.sh width:=640 height:=480 fps:=15.0 stream_fps:=15.0
source "$(dirname "$0")/lib-ros-env.sh"

FRONT_DEVICE="${FRONT_DEVICE:-/dev/video0}"
REAR_DEVICE="${REAR_DEVICE:-/dev/video2}"

echo "起動: cameras -> http://0.0.0.0:8080/ (front=${FRONT_DEVICE} rear=${REAR_DEVICE})"
exec ros2 launch kuas_mechlab3 cameras_launch.py \
  front_device:="${FRONT_DEVICE}" rear_device:="${REAR_DEVICE}" "$@"
