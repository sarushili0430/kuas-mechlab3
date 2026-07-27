# ML3 遠隔操縦ロボット — 環境構築と動作確認

KUAS MechLab3 / チーム 11 ／ `kuas-mechlab3`（ロボット側）・`kuas-mechlab3-cockpit`（操縦 UI）

4 輪スキッドステアロボット **ML3** の環境構築と動作確認の手順。制御（STM32 NUCLEO-F091RC / Mbed OS 6）・統合
（Raspberry Pi / ROS 2 Humble）・操縦（Web コックピット）の 3 層があり、**構築も確認も下の層から順に行う**。

## 1. 必要な環境

| 対象 | ツール | 備考 |
| --- | --- | --- |
| Nucleo | PlatformIO Core | `pip install platformio`。Mbed OS 6 をビルド |
| Raspberry Pi | Ubuntu 22.04 + ROS 2 Humble ／ Python 3.10.18 | Python は `.python-version` で固定 |
| 操縦者 PC | Node.js + pnpm 11.5 | コックピット（Vite + React 19 + TypeScript）のビルド。ROS 環境は不要 |

## 2. 構築手順

**① マイコンのファームウェア** — Nucleo を ST-Link 側の USB で PC に接続して書き込む。ホストとは
`s1/s2/s3/s4/d`（駆動）・`<肩us>/<肘us>/a`（サーボ）・`<0|1>/l`（LED）の文字列プロトコルで通信する契約で、
テレメトリが 50 Hz で返る。`mbed_app.json` で浮動小数点出力を有効にしておく（§4）。

```bash
pip install platformio
cd firmware/robot && pio run && pio run -t upload   # ビルド → ST-Link 経由で書き込み
```

**② ロボット側（Raspberry Pi）** — リポジトリのルートがそのまま colcon ワークスペースになっている。実行時
依存（`rclpy` / `python3-serial` / `python3-opencv` / `python3-websockets` / `ros2bag` 等）は `package.xml`
に宣言済みで `rosdep` が一括解決し、rosdep キーの無い `ultralytics` だけ pip で入れる。

```bash
sudo usermod -aG dialout $USER          # シリアル権限（初回のみ・再ログインで反映）
git clone git@github.com:sarushili0430/kuas-mechlab3.git && cd kuas-mechlab3
source /opt/ros/humble/setup.bash && export ROS_DOMAIN_ID=0    # チーム分離用。全ターミナルで揃える
rosdep install --from-paths src --ignore-src -r -y             # 初回のみ依存解決
colcon build --packages-select kuas_mechlab3 && source install/setup.bash
pip install ultralytics && ./scripts/prefetch-model.sh         # 信号機検出(YOLOv8)と重みの事前取得
```

**③ 操縦者 PC（コックピット UI）** — 機体と同じ LAN に置く。運用ではビルド成果物を Pi 上の配信ディレクトリに置き、
`ml3-cockpit.service`（`python3 -m http.server 8000`）で `:8000` から配信する。HTTPS 配信は `http://` の映像と
`ws://` の操縦が混在コンテンツでブロックされるため不可。

```bash
git clone git@github.com:sarushili0430/kuas-mechlab3-cockpit.git && cd kuas-mechlab3-cockpit
pnpm install && pnpm build      # 依存導入（Git フックも有効化）→ dist/ を生成
```

## 3. 動作確認（下位層から切り分ける）

**確認は必ず車輪を浮かせて行う**（全開 PWM で台から飛び出す・突入電流が流れるため）。

| # | 対象 | コマンド | 期待結果・判断 |
| --- | --- | --- | --- |
| 1 | 純ロジック（ROS 不要） | `pytest` | 運動学・ワイヤ形式・色判定などが通る。`rclpy` 非依存の純関数なので実機なしで検証できる |
| 2 | ファーム単体 | `stty -F /dev/ttyACM0 115200 raw -echo` → `timeout 2 cat /dev/ttyACM0` → `printf '3.00/3.00/3.00/3.00/d' > /dev/ttyACM0` | テレメトリが 50 Hz で流れ、全輪が回って 0.5 秒後に自動停止する（シリアルは 1 プロセス占有。`mbed_driver` 停止中に行う） |
| 3 | 各輪の回転方向 | `python3 scripts/pi-jog.py 0`（以降 1, 2, 3）／ `python3 scripts/pi-drivetest.py forward` | 逆回転した輪はファームの `MOTOR_DIR[i]` を反転して再フラッシュ。**旋回だけが逆**なら左右割当の問題なのでドライバの `turn_sign:=-1.0` で直す |
| 4 | カメラの識別 | `./scripts/detect-cameras.sh` | 前後の USB ポート（`by-path`）で固定する。`/dev/videoN` は再起動ごとに入れ替わる |
| 5 | 全体の起動 | `./scripts/start-all.sh` → `ros2 node list \| sort`（+ `uniq -d`） | 8 ノードが起動し、重複が出ない（重複＝二重起動） |
| 6 | 映像と通信 | `ros2 topic hz /front_camera/image_raw/compressed` ／ `http://<ROBOT_IP>:8080/` | 約 20 Hz で配信され、前後 2 画面が更新される |
| 7 | 操縦（結合確認） | ブラウザで `http://<ROBOT_IP>:8000/` → ホストに Pi の IP → 接続 | 接続ピルが緑になり、**W/A/S/D** で走行・**矢印キー**でアームが動く。キーを離すと停止する |

## 4. つまずいた点と対処

| 現象 | 原因 | 対処 |
| --- | --- | --- |
| テレメトリが `sp %f ...` のまま流れ全行破棄 | Mbed OS 6 の既定 printf が `%f` 非対応 | `mbed_app.json` で浮動小数点出力を有効化 |
| 前後カメラが入れ替わる | `/dev/videoN` が起動ごとに再割当。C270 2 台は `by-id` 不可 | USB ポート（`by-path`）で固定 |
| ノードが重複し rear カメラが出ない | 旧自動起動ユニットとの二重起動 | 競合する自動起動ユニットを無効化 |
| 会場で信号機ノードだけ上がらない | YOLO の重みを初回実行時に取得する作り | `prefetch-model.sh` で事前取得 |
