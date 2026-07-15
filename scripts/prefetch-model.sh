#!/usr/bin/env bash
# 競技会場ではネットが無いことがある。YOLOv8n の重み(yolov8n.pt)は信号機検出ノードの
# 初回 YOLO() 呼び出しでダウンロードされるため、事前に取得しておかないと起動時にネット
# 待ちで固まる。オンラインのうちに一度これを走らせ、重みをリポジトリ直下に置いておく。
# start-all.sh / systemd unit の WorkingDirectory がリポジトリ直下なので YOLO() はここを見る。
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root (= detector の実行時 CWD)
MODEL="${MODEL:-yolov8n.pt}"

# 存在するだけでは不十分: 途中で切れた前回 DL の 0/部分バイトを「取得済み」と
# 誤認しないよう、妥当なサイズ(yolov8n.pt は約 6MB)も確認する。
if [ -f "$MODEL" ] && [ "$(stat -c%s "$MODEL" 2>/dev/null || echo 0)" -ge 1000000 ]; then
  echo "既に存在: $(pwd)/$MODEL ($(du -h "$MODEL" | cut -f1))"
  exit 0
fi

echo "取得中: $MODEL -> $(pwd)/ (ultralytics 経由・要ネット)"
python3 - "$MODEL" <<'PY'
import sys
from ultralytics import YOLO

YOLO(sys.argv[1])  # missing weights are downloaded into the CWD
print("download OK")
PY
ls -lh "$MODEL"
