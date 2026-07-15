#!/usr/bin/env bash
# 前後カメラを USB ポート(by-path)で一意に特定するヘルパ。
#
# なぜ by-path か: 2 台の C270 はシリアルが同一なので by-id では区別できず、
# /dev/videoN は起動ごとに番号が入れ替わる(この機体は前=video2 / 後=video0 と、
# start-all.sh の既定 video0/video2 とは逆になる → そのままだと前後が入れ替わる)。
# 物理 USB ポートに紐づく by-path だけが再起動をまたいで安定する。
#
# この機体の割り当て: FRONT = USB ポート 1.4 / REAR = USB ポート 1.3
# 前後が入れ替わって見えるときは、下 2 本を start-all.sh の FRONT_DEVICE /
# REAR_DEVICE(systemd 運用なら unit の Environment=)に設定する。
set -euo pipefail

echo "=== 接続中の USB カメラ (by-path, video-index0 が主キャプチャ) ==="
found=0
for p in /dev/v4l/by-path/*usb*-video-index0; do
  [ -e "$p" ] || continue
  found=1
  printf '  %s\n      -> %s\n' "$p" "$(readlink -f "$p")"
done
[ "$found" -eq 1 ] || { echo "  カメラが見つかりません。USB 接続を確認してください。"; exit 1; }

FRONT=/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.4:1.0-video-index0
REAR=/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.3:1.0-video-index0

echo
echo "=== この機体の既定マッピング (存在チェック) ==="
[ -e "$FRONT" ] && front_state=OK || front_state=MISSING
[ -e "$REAR" ]  && rear_state=OK  || rear_state=MISSING
printf '  FRONT (port 1.4): %s  [%s]\n' "$FRONT" "$front_state"
printf '  REAR  (port 1.3): %s  [%s]\n' "$REAR"  "$rear_state"

# 期待ポートにカメラが無ければ、貼り付け用の export は出さずに失敗させる
# (MISSING を見落として存在しない device を start-all.sh に渡すのを防ぐ)。
if [ "$front_state" != OK ] || [ "$rear_state" != OK ]; then
  echo
  echo "ERROR: 前後どちらかのカメラが既定ポートに見つかりません。USB 接続とポートを確認してください。" >&2
  exit 1
fi

echo
echo "start-all.sh / systemd にそのまま渡せる形:"
echo "  export FRONT_DEVICE=$FRONT"
echo "  export REAR_DEVICE=$REAR"
