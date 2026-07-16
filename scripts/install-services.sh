#!/usr/bin/env bash
# 競技用スタックを boot 常駐させるワンショットインストーラ。
# kuas-mechlab3.service(ロボット一式)と ml3-cockpit.service(操縦 UI 配信)を
# /etc/systemd/system に配置・有効化し、競合する自動起動(今季あった旧 ml3-ros.service
# 等)を無効化し、YOLO 重みを事前取得する。root 権限が要るので sudo で実行。
#
# 注意: このスクリプトはコピーと有効化まで。配置後に unit の User= / WorkingDirectory= /
#       ExecStart= / カメラ by-path(scripts/detect-cameras.sh で確認)を実機に合わせて
#       編集してから start すること。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR=/etc/systemd/system

if [ "$(id -u)" -ne 0 ]; then
  echo "root で実行してください: sudo $0" >&2
  exit 1
fi

# 競合する自動起動を無効化(二重起動 = ノード重複 + カメラ競合を防ぐ)。
# 単一要素だが、将来ほかの競合ユニットを足せるよう list 形式にしている。
# shellcheck disable=SC2043
for u in ml3-ros.service; do
  # そのユニットだけを直接問い合わせる(大きな一覧を grep -q に流すと pipefail 下で
  # SIGPIPE を拾って取りこぼす恐れがある)。
  if systemctl list-unit-files --no-legend "$u" 2>/dev/null | grep -q .; then
    echo "競合ユニットを無効化: $u"
    systemctl disable --now "$u" || true
  fi
done

echo "ユニットを配置: kuas-mechlab3.service / ml3-cockpit.service"
install -m 0644 "$REPO/scripts/kuas-mechlab3.service" "$UNIT_DIR/kuas-mechlab3.service"
install -m 0644 "$REPO/scripts/ml3-cockpit.service"   "$UNIT_DIR/ml3-cockpit.service"

systemctl daemon-reload
systemctl enable kuas-mechlab3.service ml3-cockpit.service

echo
echo ">> 次に $UNIT_DIR/{kuas-mechlab3,ml3-cockpit}.service の User= / パス / カメラ by-path を"
echo "   実機に合わせて編集してから起動:"
echo "     sudo systemctl start kuas-mechlab3 ml3-cockpit"
echo "     systemctl status kuas-mechlab3 ml3-cockpit"
echo
echo "YOLO 重みの事前取得を試行(要ネット):"
sudo -u "${SUDO_USER:-root}" bash "$REPO/scripts/prefetch-model.sh" \
  || echo "  (prefetch 失敗。ネット環境で $REPO/scripts/prefetch-model.sh を手動実行)"
echo
echo ">> 重みは $REPO/ に取得される。unit の WorkingDirectory が別クローンを指す場合は"
echo "   そのツリーにも yolov8n.pt を置くこと(検出ノードは WorkingDirectory から読む)。"
