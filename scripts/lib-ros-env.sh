#!/usr/bin/env bash
# 共通 ROS2 環境セットアップ。各 start-*.sh から source される前提。
# 責任分離: ここは「環境を整える」だけを担い、ノードの起動は呼び出し側が行う。
#
# 上書き可能な環境変数:
#   ROS_DOMAIN_ID  ノード同士が見える DDS ドメイン（既定 0。複数ターミナルで揃える）
#   ROS_SETUP      ROS2 本体の setup.bash（既定 /opt/ros/humble/setup.bash）
set -euo pipefail

# リポジトリのルート（このファイルの 1 つ上のディレクトリ）
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ノード同士が見えるよう、全ターミナルで同じ値にする
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"

# ROS2 本体
ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"
if [[ ! -f "$ROS_SETUP" ]]; then
  echo "ERROR: ROS2 が見つかりません: $ROS_SETUP" >&2
  echo "       ROS_SETUP=/path/to/setup.bash で上書きできます。" >&2
  exit 1
fi
# ROS の setup.bash は未定義変数(AMENT_TRACE_SETUP_FILES 等)を参照する作りのため、
# nounset(-u) 下では source した瞬間に「unbound variable」で落ちる。
# source の間だけ -u を外す(スクリプト自身のロジック保護には -u を残す)。
set +u
# shellcheck disable=SC1090
source "$ROS_SETUP"
set -u

# colcon ワークスペース（未ビルドなら案内して終了）
if [[ ! -f install/setup.bash ]]; then
  echo "ERROR: install/setup.bash が無い。先にビルドしてください:" >&2
  echo "       colcon build --packages-select kuas_mechlab3" >&2
  exit 1
fi
set +u
# shellcheck disable=SC1091
source install/setup.bash
set -u

echo "ROS env ready (ROS_DOMAIN_ID=${ROS_DOMAIN_ID}, ws=${REPO_ROOT})"
