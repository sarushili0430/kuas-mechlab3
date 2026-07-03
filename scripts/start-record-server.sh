#!/usr/bin/env bash
# 録画コントロール HTTP API（record_server）を一発起動する。
# スマホ（cockpit の REC ボタン）や curl から start/stop/discard/status を叩いて
# ros2 bag record を遠隔で開始・終了できる。record_episodes.py（対話 CLI）の遠隔版。
#   待ち受け: http://<このマシンのIP>:9002/record/status
#
# 先に driver / cameras / teleop を起動しておくこと（別ターミナル or start-all.sh）。
# launch 引数はそのまま渡せる:
#   ./scripts/start-record-server.sh route:=route_a operator:=koyu
#   ./scripts/start-record-server.sh out:=datasets/raw port:=9002
#
# 責任分離: ここは ROS 環境を整えて record_server を launch するだけ。録画ロジックは
# record_session（bag ライフサイクル）、配置/スキーマは kuas_mechlab3.recording が担う。
source "$(dirname "$0")/lib-ros-env.sh"

echo "起動: 録画コントロール API -> http://0.0.0.0:9002/record/status"
exec ros2 launch kuas_mechlab3 record_launch.py "$@"
