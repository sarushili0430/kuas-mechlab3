#!/usr/bin/env bash
# 人間のテレオプ・デモ走行を 1 エピソードずつ rosbag に記録する（模倣学習データ収集）。
# 各走行 = 1 bag + meta.json（ルート / 操縦者 / 成功・失敗ラベル）。
# 記録トピック: /cmd_norm（= 行動ラベル）+ 前後カメラ + cmd_vel / 車輪テレメトリ。
#
# 先に driver / cameras / teleop を起動しておくこと（別ターミナル or start-all.sh）。
# 使い方:
#   ./scripts/start-record.sh --route route_a --operator koyu
#   ./scripts/start-record.sh --route loop_1 --no-rear        # 後カメラを記録しない
#
# 責任分離: ここは ROS 環境を整えて記録ツールに exec するだけ（記録ロジックは
# record_episodes.py、データセット配置は kuas_mechlab3.recording が担う）。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib-ros-env.sh"

exec python3 "$SCRIPT_DIR/record_episodes.py" "$@"
