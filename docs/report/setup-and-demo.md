# ML3 遠隔操縦ロボット — 環境構築から実機デモまで

KUAS MechLab3 / チーム 11

リポジトリ: `kuas-mechlab3`（ロボット側）／ `kuas-mechlab3-cockpit`（操縦 UI）

---

## 1. 目的とシステム構成

4 輪スキッドステアロボット **ML3** を、操縦者 PC のブラウザから遠隔操縦できる状態まで立ち上げる。
本レポートでは **環境構築（Setup）→ 単体動作確認 → 起動（Bring-up）→ 実機デモ** までの手順と、
その過程で判明した問題および対処をまとめる。対象システムは次の 3 層から成る。

| 層 | ハードウェア | ソフトウェア | 役割 |
| --- | --- | --- | --- |
| ①制御 | STM32 NUCLEO-F091RC | Mbed OS 6 ファームウェア | PWM 生成・サーボ駆動・ウォッチドッグ |
| ②統合 | Raspberry Pi（Ubuntu 22.04） | ROS 2 Humble パッケージ `kuas_mechlab3` | カメラ・通信・タスク処理 |
| ③操縦 | 操縦者の PC / スマートフォン | Web コックピット（React + Vite） | 映像表示・操作入力 |

```
 [操縦者PC ブラウザ]        [Raspberry Pi / ROS 2 Humble]           [Nucleo / 駆動部]
   映像 ←─ MJPEG :8080 ── mjpeg_server ← camera_node ×2 ← USB カメラ ×2
   操縦 ─→ WS    :9001 ─→ teleop_server → mbed_driver ─シリアル→ ファーム → モータ ×4
   録画 ─→ HTTP  :9002 ─→ record_server                       └→ サーボ ×2（アーム）／LED
                          traffic_light_node（信号機検出）／qr_detector（QR 読取）
```

通信チャネルは **映像（8080）・操縦（9001）・録画制御（9002）** の 3 本が互いに独立しており、どれか
1 本が落ちても他は動作を継続する。操縦者 PC 側に ROS 環境は不要で、ブラウザだけで完結する。

---

## 2. 環境構築（Setup）

### 2.1 マイコンのファームウェア書き込み

ホストとマイコンは以下の文字列プロトコルで通信する契約になっている。この契約を満たすファームを先に書き
込んでおかないと、上位のソフトを正しく起動してもモータは一切動かない。

| 方向 | 形式 | 例 |
| --- | --- | --- |
| Pi → Nucleo（駆動 / サーボ / LED） | `s1/s2/s3/s4/d` ・ `<肩us>/<肘us>/a` ・ `<0\|1>/l` | `10.50/10.50/-10.50/-10.50/d` |
| Nucleo → Pi（テレメトリ） | `sp .. \| rpm .. \| pwm ..` を 50 Hz で 1 行ずつ | `sp 10.50 … \| pwm 3600 …` |

書き込みは PlatformIO で行う。Nucleo を ST-Link 側の USB で PC に接続し、

```bash
pip install platformio
cd firmware/robot
pio run              # ビルド
pio run -t upload    # ST-Link 経由で書き込み
```

**設定上の注意**: `mbed_app.json` で `platform.minimal-printf-enable-floating-point: true` を有効にする。
Mbed OS 6 の既定 printf は `%f` を出力できず、テレメトリが `sp %f ...` のまま流れて Pi 側のパーサに
全行破棄されてしまうためである。主要な定数は次のとおり。

| 定数 | 値 | 意味 |
| --- | --- | --- |
| `SP_FULL` | 10.5 | フルスケール setpoint（Pi 側 `wheel_setpoint` と一致させる） |
| `PWM_CAP` / `PWM_MAX` | 3600 / 4000 | デューティ上限 90 %。常用フルデューティは電流・発熱が大きいため制限 |
| `MOTOR_DIR[4]` | `{-1, -1, +1, +1}` | 各輪の正転符号。実測のジョグ試験で確定 |
| `WATCHDOG_MS` | 500 | 指令が 0.5 秒途絶えたら全輪停止（USB 抜けにも効く） |

### 2.2 ロボット側（Raspberry Pi）

```bash
sudo usermod -aG dialout $USER          # シリアル権限（初回のみ・再ログインで反映）
git clone git@github.com:sarushili0430/kuas-mechlab3.git && cd kuas-mechlab3
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0                  # チーム分離用。全ターミナルで揃える
rosdep install --from-paths src --ignore-src -r -y    # 初回のみ依存解決
colcon build --packages-select kuas_mechlab3 && source install/setup.bash
pip install ultralytics && ./scripts/prefetch-model.sh   # 信号機検出(YOLOv8)と重みの事前取得
```

リポジトリのルートがそのまま colcon ワークスペースになっている。ROS 2 の実行時依存（`rclpy` /
`sensor_msgs` / `python3-serial` / `python3-opencv` / `python3-websockets` / `ros2bag` 等）は
`package.xml` に宣言してあり `rosdep` が一括で解決する。`ultralytics` だけは rosdep キーが無いため
pip で導入し、モデル `yolov8n.pt` は初回実行時に自動取得されるためネットワークの無い会場に持ち込む
前に必ず事前取得しておく。

### 2.3 操縦者 PC（コックピット UI）

```bash
git clone git@github.com:sarushili0430/kuas-mechlab3-cockpit.git && cd kuas-mechlab3-cockpit
pnpm install    # 依存導入（Git フックも自動で有効化）
pnpm dev        # 開発サーバ / pnpm build で dist/ を生成
```

競技運用ではビルド成果物を Pi 上の静的配信ディレクトリに置き、`ml3-cockpit.service`（`python3 -m
http.server 8000`）で配信して `http://<ROBOT_IP>:8000/` から開く。機体が無い状態で UI だけ確認したい
ときは Storybook の `Cockpit/CockpitScreenContainer → Demo`（常に接続に成功するデモソケット）を使う。
なお UI を HTTPS で配信すると `http://` の映像と `ws://` の操縦が混在コンテンツとしてブロックされる
ため、`http://` 配信か `file://` で開く。

---

## 3. 単体動作確認（結線と回転方向の検証）

いきなり全体を起動せず下から順に切り分ける。**すべて車輪を浮かせた状態**で行う（全開 PWM で台から
飛び出す・突入電流が流れるため）。

**① 純ロジックのテスト（ROS 不要）** — キネマティクス、ワイヤ形式の生成／解析、信号色の判定、録画の
状態遷移といったロジックは `rclpy` に依存しない純関数として切り出してあるため、`pytest` だけで
実機・ROS 環境なしに検証できる。

**② ファームウェア単体の確認** — `mbed_driver` は停止しておく（シリアルは 1 プロセス占有のため）。

```bash
stty -F /dev/ttyACM0 115200 raw -echo
timeout 2 cat /dev/ttyACM0                       # テレメトリが 50 Hz で流れるか
printf '3.00/3.00/3.00/3.00/d' > /dev/ttyACM0    # 全輪が回り、0.5 秒後に自動停止すれば OK
```

**③ 各輪の回転方向の確認** — `python3 scripts/pi-jog.py 0`（以降 1, 2, 3）で 1 輪ずつ、
`python3 scripts/pi-drivetest.py forward` で全体の動きを確認する。逆回転した輪はファームの
`MOTOR_DIR[i]` を反転して再フラッシュする。一方、**旋回方向だけが逆**の場合は各輪の向きではなく左右
割当の問題なので、ファームではなくドライバのパラメータ `turn_sign:=-1.0` で直す。この切り分けを誤ると、
直進が壊れるまで無駄にファームを焼き直すことになる。

**④ カメラの識別** — `./scripts/detect-cameras.sh` を実行する。`/dev/videoN` の番号は再起動のたびに
入れ替わり、使用した 2 台の C270 はシリアル番号が同一で `by-id` でも区別できない。そこで **USB ポート
に紐づく `by-path`**（本機体は前＝ポート 1.4／後＝ポート 1.3）でデバイスを固定する。

---

## 4. 起動（Bring-up）

### 4.1 手動起動（構成を理解するための基本形）

ターミナルを 3 つ開き、**すべての先頭で** `source /opt/ros/humble/setup.bash`、`export
ROS_DOMAIN_ID=0`、`source install/setup.bash` を実行してから 1 つずつ起動する。`ROS_DOMAIN_ID` が
揃っていないとノード同士が互いを認識できない。

```bash
ros2 launch kuas_mechlab3 drivetrain_launch.py                                    # ① モータ driver
ros2 launch kuas_mechlab3 cameras_launch.py front_device:=... rear_device:=...    # ② カメラ + 配信
ros2 launch kuas_mechlab3 teleop_launch.py                                        # ③ 操縦 WebSocket
hostname -I                                                                       # Pi の IP を控える
```

### 4.2 一括起動と自動起動

`start-all.sh` は driver・カメラ・teleop・録画・信号機・QR の 6 つの launch を 1 プロセスから束ねて
起動し、`Ctrl+C` で全ノードへ停止指令を送ってまとめて落とす。`install-services.sh` はこれを systemd
ユニット化し、**電源投入だけでスタック一式が立ち上がる**状態にする。競技運用ではこちらを使う。

```bash
./scripts/start-all.sh                            # 6 系統を一括起動、Ctrl+C で一括停止
sudo ./scripts/install-services.sh                # systemd 登録（boot 常駐）
systemctl is-active kuas-mechlab3 ml3-cockpit     # → active / active
```

### 4.3 起動後の確認

| 確認項目 | コマンド | 期待結果 |
| --- | --- | --- |
| ノード数 | `ros2 node list \| sort` | 8 ノード（camera ×2 / mbed_driver / mjpeg_server / record_server / teleop_server / traffic_light_node / qr_detector） |
| 二重起動 | `ros2 node list \| sort \| uniq -d` | 何も出力されない |
| カメラ配信 | `ros2 topic hz /front_camera/image_raw/compressed` | 約 20 Hz |
| 映像 | ブラウザで `http://<ROBOT_IP>:8080/` | 前後 2 画面が更新される |

---

## 5. 実際に動かす（デモ）

### 5.1 遠隔操縦

操縦者 PC を機体と同じ LAN に接続してブラウザで `http://<ROBOT_IP>:8000/` を開き、ヘッダの
「接続先ホスト」に Pi の IP を入力して適用する（`localStorage` に保存される）。「接続」を押して接続ピルが
緑（WS 接続 OK）になったら、画面にフォーカスを当てて **W / A / S / D** で走行、**矢印キー**でアーム
（↑↓＝肘、←→＝肩）、ボタンで LED を操作する。方向の期待値は REP-103 準拠で `w` が前進、`a` が
反時計回り（左旋回）である。

コックピットは押下中の目標速度を **20 Hz で送り続ける**方式で、正規化軸値 `{"vx","wz"}`（各 −1〜1）を
JSON テキストで送信し、サーバ側が `max_linear`（0.5 m/s）／`max_angular`（2.0 rad/s）で物理量へ
スケールする。アームと LED は同じ WebSocket に別形の JSON（`{"servo":[肩,肘]}` / `{"led":true}`）を送る
**ラッチ方式**で、走行指令のように 0 へ減衰せず位置・状態を保持する。

### 5.2 競技タスクと走行データの記録

**信号機検出（課題 #9）** は前カメラのトピックを購読し、YOLOv8 で信号機を検出したうえで HSV マスクの
画素数から色を判定して、緑のとき `11Green` を publish する。検出できない／色が曖昧なフレームでは
**何も publish しない**（誤った状態を流さないためのフェイルセーフ）。**QR 読み取り（課題 #5）** は
OpenCV の `QRCodeDetector` でデコードし、読めている間だけ機体 LED を点灯、外すと約 1 秒のウォッチ
ドッグで消灯する。いずれのノードも `/dev/video*` を直接開かず `camera_node` が流す ROS トピックを購読
する設計にしたため、映像配信と同時に動かしてもカメラデバイスの競合が起きない。

```bash
ros2 topic echo /traffic_light_topic   # 緑を映すと 11Green（バリアが開く文字列）
ros2 topic echo /qr_topic              # QR の payload。/led_cmd に true/false が出る
curl -s -X POST http://<ROBOT_IP>:9002/record/start -d '{"route":"route_a"}'
```

コックピットの **REC** ボタン（上記 HTTP API）から、1 走行 = 1 エピソードとして rosbag に記録できる。
記録対象は `/cmd_norm`（正規化された操作指令＝将来の模倣学習の教師データ）、前後カメラ映像、`cmd_vel`、
車輪テレメトリで、走行後に成功／失敗ラベルを付けて保存するか、失敗走行は破棄する。

---

## 6. つまずいた点と対処

| 現象 | 原因 | 対処 |
| --- | --- | --- |
| テレメトリが `sp %f ...` のまま流れ全行破棄 | Mbed OS 6 の既定 printf が `%f` 非対応 | `mbed_app.json` で浮動小数点出力を有効化 |
| 前後カメラが入れ替わる | `/dev/videoN` が起動ごとに再割当。C270 2 台はシリアル同一で `by-id` 不可 | USB ポート（`by-path`）でデバイスを固定 |
| ノードが重複し rear カメラが出ない | 旧自動起動ユニットとの二重起動 | 競合ユニットを無効化（`install-services.sh` が自動化） |
| CPU 飽和・83 °C でサーマルスロットリング（映像配信まで巻き添え） | カメラ 30 Hz の全フレームで YOLO 推論していた | `detect_interval`（現在 1.0 s）で間引き。信号は数秒単位でしか変わらず取り逃しは無い |
| 同上（QR 側の負荷） | 同じ CPU・同じカメラを #9 と共有 | `decode_interval`（現在 0.5 s）で間引き、取り逃しの許されない #9 に CPU を譲る |
| アームが急に動いて突入電流が出る | サーボへ急峻なステップ目標を与えていた | ファーム側にスルーレート制限（25 µs/20 ms ≈ 112 °/s）を追加 |
| 旋回方向が逆 | 左右の割当の問題（各輪の向きではない） | ドライバの `turn_sign:=-1.0` で修正 |

---

## 7. 安全設計

無拘束でデモ走行させるため、独立した 4 層のフェイルセーフを設けた。上位が落ちても下位が必ず止める。

| 層 | 発火条件 | 応答時間 |
| --- | --- | --- |
| ① WebSocket 切断（タブを閉じる・Wi-Fi 断） | 次の送信サイクルで即 0 | 約 50 ms |
| ② `teleop_server` の `hold_timeout`（無入力） | 目標値を 0 へ減衰 | 0.4 s |
| ③ `mbed_driver` の `cmd_timeout`（ROS 側の停止・クラッシュ） | 全輪停止を送出 | 0.4 s |
| ④ ファームウェアのウォッチドッグ（**USB が物理的に抜けても**有効） | 全輪停止 | 0.5 s |

①〜③はソフトウェア層のため USB ケーブルが抜けると効かず、④だけがその状況をカバーする。無拘束デモの
前には必ず最新ファームが書かれていることを確認する。

---

## 8. まとめ

ファームウェア書き込み → Pi 側の ROS 2 ワークスペース構築 → 操縦 UI の準備、という順に環境を整え、
下位層から単体で切り分けながら確認したうえで全体を起動することで、**ブラウザから映像を見ながら実機を
遠隔操縦する**ところまで到達した。信号機検出・QR 読み取り・走行データ記録も同一スタック上で同時に動作
している。得られた知見は次の 3 点である。

1. **契約を先に固定する**。ホストとマイコンの通信形式を文字列プロトコルとして定義し、純ロジックとして
   テストできる形にしたことで、実機が無い状態でも大半のバグを潰せた。
2. **リソース競合は設計で避ける**。カメラをトピック経由で共有したことで 3 つの処理を 1 台のカメラで
   同時に動かせた。一方 CPU は共有資源のままなので処理レートの間引きが必要になった。
3. **安全機構は層を分ける**。ソフトウェア層のタイムアウトだけでは USB 断をカバーできず、ファームウェア
   側の独立したウォッチドッグが最後の砦になる。
