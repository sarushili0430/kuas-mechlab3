# ML3 遠隔操縦ロボット — 環境構築から実機デモまで

KUAS MechLab3 / チーム 11 ／ `kuas-mechlab3`（ロボット側）・`kuas-mechlab3-cockpit`（操縦 UI）

**目的**: 4 輪スキッドステアロボット **ML3** を、操縦者 PC のブラウザから遠隔操縦できる状態まで立ち上げる。
制御（STM32 NUCLEO-F091RC / Mbed OS 6）・統合（Raspberry Pi / ROS 2 Humble）・操縦（Web コックピット）の 3 層構成で、
**映像 :8080・操縦 :9001・録画制御 :9002** の 3 チャネルは互いに独立。操縦者 PC 側に ROS 環境は要らない。

```
 [操縦者PC ブラウザ]        [Raspberry Pi / ROS 2 Humble]           [Nucleo / 駆動部]
   映像 ←─ MJPEG :8080 ── mjpeg_server ← camera_node ×2 ← USB カメラ ×2
   操縦 ─→ WS    :9001 ─→ teleop_server → mbed_driver ─シリアル→ ファーム → モータ ×4
   録画 ─→ HTTP  :9002 ─→ record_server                       └→ サーボ ×2（アーム）／LED
                          traffic_light_node（信号機検出）／qr_detector（QR 読取）
```

## 1. 環境構築 → 実機デモの手順

| # | 段階 | 主なコマンド | 要点 |
| --- | --- | --- | --- |
| 1 | ファーム書き込み | `cd firmware/robot && pio run -t upload` | `mbed_app.json` で `%f` 出力を有効化（既定 printf では `sp %f ...` のまま流れてパーサに全行破棄される） |
| 2 | Pi 環境構築 | `rosdep install --from-paths src --ignore-src -r -y` → `colcon build --packages-select kuas_mechlab3` → `pip install ultralytics && ./scripts/prefetch-model.sh` | 依存は `package.xml`（rosdep）で解決。`ultralytics` のみ pip。YOLO の重みは会場に持ち込む前に事前取得 |
| 3 | 単体動作確認 | `pytest` → `cat /dev/ttyACM0` → `python3 scripts/pi-jog.py 0` → `./scripts/detect-cameras.sh` | **車輪を浮かせて**下位層から切り分ける。逆回転はファームの `MOTOR_DIR[i]`、旋回逆はドライバの `turn_sign` で直す（混同しない）。カメラは `by-path` で固定 |
| 4 | 操縦 UI | `pnpm install && pnpm build` → Pi 上で `:8000` 配信 | HTTPS 配信は `http://` 映像と `ws://` 操縦が混在コンテンツでブロックされるため不可 |
| 5 | 起動（Bring-up） | `./scripts/start-all.sh`（`install-services.sh` で systemd 常駐） | 6 launch を 1 プロセスで束ね `Ctrl+C` で一括停止。常駐なら電源投入だけで一式起動 |
| 6 | 起動後の確認 | `ros2 node list \| sort`（+ `uniq -d`）／ `ros2 topic hz /front_camera/image_raw/compressed` | 8 ノード・重複なし／約 20 Hz。ブラウザ `http://<ROBOT_IP>:8080/` で前後映像 |
| 7 | デモ走行 | ブラウザで `http://<ROBOT_IP>:8000/` → ホストに Pi の IP → 接続 | **W/A/S/D** で走行、**矢印キー**でアーム、ボタンで LED。緑信号で `11Green` を publish、QR は読める間だけ LED 点灯、**REC** で走行を rosbag 記録 |

操縦は正規化軸値 `{"vx","wz"}`（各 −1〜1）を **20 Hz で送り続ける**方式で、サーバ側が `max_linear`（0.5 m/s）／
`max_angular`（2.0 rad/s）で物理量へスケールする。アーム `{"servo":[肩,肘]}` と LED `{"led":true}` は同じ WebSocket
に送る**ラッチ方式**で、走行指令のように 0 へ減衰せず状態を保持する。

## 2. つまずいた点と対処

| 現象 | 原因 | 対処 |
| --- | --- | --- |
| テレメトリが `sp %f ...` のまま流れ全行破棄 | Mbed OS 6 の既定 printf が `%f` 非対応 | `mbed_app.json` で浮動小数点出力を有効化 |
| 前後カメラが入れ替わる | `/dev/videoN` が起動ごとに再割当。C270 2 台はシリアル同一で `by-id` 不可 | USB ポート（`by-path`）でデバイスを固定 |
| CPU 飽和・83 °C でサーマルスロットリング（映像配信まで巻き添え） | カメラ 30 Hz の全フレームで YOLO 推論していた | `detect_interval`（1.0 s）／QR 側 `decode_interval`（0.5 s）で間引き |
| アームが急に動いて突入電流が出る | サーボへ急峻なステップ目標を与えていた | ファーム側にスルーレート制限（25 µs/20 ms ≈ 112 °/s）を追加 |
| ノードが重複し rear カメラが出ない | 旧自動起動ユニットとの二重起動 | 競合ユニットを無効化（`install-services.sh` が自動化） |

## 3. 安全設計と結論

無拘束でデモ走行させるため、独立した 4 層のフェイルセーフを設けた ―
**① WS 切断で即 0**（約 50 ms）→ **② `teleop_server` の `hold_timeout`**（0.4 s）→
**③ `mbed_driver` の `cmd_timeout`**（0.4 s）→ **④ ファームのウォッチドッグ**（0.5 s）。
①〜③はソフトウェア層のため USB ケーブルが抜けると効かず、④だけがその状況をカバーする。

以上の手順で、**ブラウザから映像を見ながら実機を遠隔操縦する**ところまで到達した。信号機検出・QR 読み取り・
走行データ記録も同一スタック上で同時に動作している。得られた知見は、**通信の契約を先に固定して純ロジックとして
テスト可能にすること**、**カメラをトピック経由で共有してリソース競合を設計で避けること**（ただし CPU は共有資源の
ままなので処理レートの間引きが要る）、**安全機構は層を分けること**の 3 点である。
