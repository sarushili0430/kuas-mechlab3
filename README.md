# kuas_mechlab3

KUAS MechLab3 の **ROS2 (Humble) パッケージ**です。Python（`ament_python`）で実装しています。

コードフォーマット・型チェック・テスト・コミットメッセージ規約・CI を整備しており、全員が同じルールで開発できるようになっています。このドキュメントでは **環境構築の方法** と **ブランチを切って PR を作成するまでの流れ** を説明します。

---

## 開発の前提（設計方針）

このリポジトリには、テスト方法の異なる 2 種類のコードがあります。新しくコードを追加するときは、どちらに当たるかを意識してください。

| 種類 | 置き場所 | テスト方法 | ROS 環境 |
| --- | --- | --- | --- |
| **純 Python**（`rclpy` などに依存しないロジック） | `src/kuas_mechlab3/kuas_mechlab3/` | `pytest`（standalone） | 不要 |
| **ROS 依存**（`rclpy` を import するノード等） | 同上 | `colcon test` | 必要（Humble） |

ロジックはできるだけ純 Python 側に切り出しておくと、ROS 環境がなくても素早くテストできます（例: `utils.py` の `clamp()`）。

---

## 必要な環境

| ツール | バージョン | 備考 |
| --- | --- | --- |
| [Python](https://www.python.org/) | 3.10.18 | `.python-version` で固定。`pyenv` 等で合わせると確実 |
| [ROS2 Humble](https://docs.ros.org/en/humble/) | Humble | colcon ビルド／ROS 依存コードの実行・テストに必要 |
| [colcon](https://colcon.readthedocs.io/) | 任意 | ROS2 のビルドツール |
| [Git](https://git-scm.com/) | 任意 | バージョン管理 |

> **ROS2 Humble は Ubuntu 22.04 が前提**です。別 OS の場合は `ros:humble` の Docker コンテナを使うのが簡単です（CI もこのコンテナでビルドしています）。
>
> 純 Python の Lint / テストだけなら ROS2 環境は不要で、Python 3.10 さえあれば動きます。

---

## 環境構築

### 1. リポジトリをクローンする

```bash
git clone git@github.com:sarushili0430/kuas-mechlab3.git
cd kuas-mechlab3
```

### 2. Python の開発ツールを入れる（Lint / テスト / Git フック）

仮想環境を作って、開発用ツールをインストールします。

```bash
python -m venv .venv
source .venv/bin/activate          # Windows ネイティブは .venv\Scripts\activate（Git フックは .venv/bin 前提のため WSL 推奨）
pip install --upgrade pip
pip install -r requirements-dev.txt
```

`requirements-dev.txt` には black / mypy / pytest / pytest-cov / lefthook / commitizen が含まれます。

> ⚠️ **仮想環境の名前は必ず `.venv` にしてください。** Git フック（[`lefthook.yml`](./lefthook.yml)）は各ツールを `.venv/bin/black` のように**フルパスで直接呼び出します**。これは「venv を activate し忘れていてもフックが動く」ようにするための意図的な作りです。そのため、`venv` や `env` など別名で作るとフックがツールを見つけられず、コミット時に `command not found`（exit 127）でフックごと失敗します。別名にしたい場合は `lefthook.yml` 内のパスも合わせて変更してください。

### 3. Git フックを有効化する

[Lefthook](https://lefthook.dev/) でコミット前・コミットメッセージのチェックを自動化しています。**クローンごとに 1 回**、以下を実行してください。

```bash
lefthook install
```

これでコミット時に black / mypy / pytest が、コミットメッセージ確定時に Conventional Commits のチェックが走るようになります。

### 4. （ROS 依存コードを扱う場合）ROS2 環境を用意する

純 Python の作業だけならここは不要です。ROS のノードをビルド・実行する場合のみ、ROS2 Humble 環境で colcon ビルドします。

```bash
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y   # 初回のみ依存解決
colcon build
source install/setup.bash
```

---

## よく使うコマンド

仮想環境を有効化（`source .venv/bin/activate`）した状態で実行します。

| コマンド | 内容 |
| --- | --- |
| `black .` | コードを整形する |
| `black --check --diff .` | 整形が必要な箇所を確認する（CI と同じチェック） |
| `mypy` | 型チェック（`pyproject.toml` の設定で対象を解決） |
| `pytest` | 純 Python のユニットテストを実行 |
| `pytest --cov --cov-report=term-missing` | カバレッジ付きでテスト |
| `cz commit` | 対話形式で規約に沿ったコミットメッセージを作成 |

ROS 依存コードのビルド・テスト（ROS2 環境が必要）:

```bash
colcon build           # ビルド
colcon test            # ROS のテストを実行
colcon test-result --verbose   # テスト結果（失敗の詳細）を表示
```

---

## 開発のルール

### コードスタイル

- **フォーマッタ: black**（`line-length = 88`, Python 3.10）
- **型チェック: mypy**（`strict` モード）
- 設定は [`pyproject.toml`](./pyproject.toml) に集約しています。
- エディタには Python / black / mypy の拡張を入れ、保存時に自動整形されるようにしておくと快適です。

### Git フック（Lefthook）

[`lefthook.yml`](./lefthook.yml) で以下が自動実行されます。手元でルール違反を早めに検知するためのものです。

| フック | タイミング | 実行内容 |
| --- | --- | --- |
| `pre-commit` | コミット前 | `black --check`（ステージした `*.py`）／ `mypy`（全体）／ `pytest` |
| `commit-msg` | コミットメッセージ確定時 | `cz check`（Conventional Commits の検証） |

> どうしてもフックを 1 回だけスキップしたい場合は `git commit --no-verify` で回避できますが、CI で同じチェックが走るので基本は通してから push してください。

### コミットメッセージ（Conventional Commits）

コミットメッセージは [Conventional Commits](https://www.conventionalcommits.org/ja/) に従ってください。規約に違反するとコミットできません（`commit-msg` フックで弾かれます）。

```
<type>: <変更内容の要約>
```

主な `type`:

| type | 用途 |
| --- | --- |
| `feat` | 新機能の追加 |
| `fix` | バグ修正 |
| `docs` | ドキュメントのみの変更 |
| `refactor` | リファクタリング |
| `test` | テストの追加・修正 |
| `chore` | ビルドや補助ツール、設定の変更 |
| `ci` | CI 設定の変更 |

例:

```bash
git commit -m "feat: clamp ユーティリティを追加"
git commit -m "fix: clamp の境界値処理を修正"
git commit -m "docs: READMEに環境構築手順を追記"
```

`cz commit` を使うと、対話形式で規約に沿ったメッセージを組み立てられます。

---

## ブランチを切って PR を作成する

`main`（および `develop`）ブランチには **直接 push せず**、必ずブランチを切って Pull Request（PR）経由で取り込みます。

### 1. 最新の取り込み先ブランチから作業ブランチを切る

```bash
git switch main          # 運用に応じて develop の場合も
git pull
git switch -c feat/<やることがわかる名前>
```

ブランチ名はコミットと同じく `feat/`・`fix/`・`docs/` などの接頭辞を付けるとわかりやすいです（例: `feat/add-imu-node`、`fix/clamp-edge-case`）。

### 2. 変更してコミットする

```bash
black .             # コミット前に整形しておく
git add .
git commit -m "feat: ◯◯を追加"
```

コミット時に `pre-commit` フック（black / mypy / pytest）と `commit-msg` フックが自動で走ります。エラーが出たら直してから再度コミットしてください。

### 3. ブランチを push する

```bash
git push -u origin feat/<ブランチ名>
```

### 4. 取り込み先ブランチに向けて PR を作成する

GitHub 上で、作成したブランチから **`main`（または `develop`）に向けて** PR を作成します。

- 何を・なぜ変更したのかが伝わるように、本文に変更内容を書きましょう。
- ROS 依存のコードを追加した場合は、ローカルでも `colcon build` / `colcon test` が通ることを確認しておくと安心です。

GitHub CLI を使う場合:

```bash
gh pr create --base main --title "feat: ◯◯を追加" --body "変更内容の説明"
```

### 5. CI を通してレビューを受ける

PR を作成すると後述の CI が自動で走ります。すべてのチェックが通り、レビューで承認されたらマージします。

---

## CI（GitHub Actions）

`.github/workflows/` に以下のワークフローを用意しています。いずれも `main` / `develop` への push と、すべての PR で実行されます。

| ワークフロー | 内容 |
| --- | --- |
| `Lint` (`lint.yml`) | `black --check` と `mypy` でフォーマット・型チェック |
| `Test` (`test.yml`) | `pytest` を実行し、カバレッジを Actions の Summary に表示 + PR にコメント（純 Python のテスト） |
| `ROS2 Build & Test` (`ros2-build.yml`) | `ros:humble` コンテナで `colcon build` / `colcon test` を実行 |

ローカルの `pre-commit` フックは `Lint` / `Test` ジョブと同じチェックをしているため、フックが通っていればこれらの CI も基本的にグリーンになります。`colcon` のビルド／テストはローカルでは任意（CI に任せる運用）ですが、ROS 依存コードを変更したときは手元でも確認することを推奨します。

---

## ドライブトレイン (drive)

ML3 4輪スキッドステアを動かす `kuas_mechlab3.drive` サブパッケージ。`geometry_msgs/Twist` を購読し、mbed ファームへシリアルで 4 輪の setpoint (`s1/s2/s3/s4/d`) を送る。`cmd_vel` は標準インターフェースなので、`teleop_keyboard` の代わりに `teleop_twist_keyboard` や nav2 をそのまま繋げられる。

```
[teleop_keyboard] --cmd_vel(Twist)--> [mbed_driver] --serial "s1/s2/s3/s4/d"--> [mbed]
                                            └── ~/wheel_rpm, ~/wheel_pwm を publish
```

責任分離（リポジトリ方針どおり、純ロジックは pytest / ROS・I-O は colcon でテスト）:

| モジュール | 責任 | テスト |
| --- | --- | --- |
| `kinematics.py` | Twist→4輪ミキシング（`utils.clamp` を再利用） | pytest |
| `protocol.py` | ワイヤ形式生成 / テレメトリ解析（文字列のみ） | pytest |
| `serial_link.py` | シリアルポート I/O（pyserial、`protocol` に委譲） | colcon |
| `mbed_driver.py` | ROS I/O + フェイルセーフ（ウォッチドッグ / 終了時停止） | colcon |
| `teleop_keyboard.py` | tty 入力 → cmd_vel | colcon |

### 実行（ROS2 Humble 上）

```bash
colcon build --packages-select kuas_mechlab3
source install/setup.bash

# 端末A: ドライバ（launch 経由）
ros2 launch kuas_mechlab3 drivetrain_launch.py
# 端末B: teleop（tty が要るので別端末で）
ros2 run kuas_mechlab3 teleop_keyboard
```

### 主要パラメータ（mbed_driver）

| 名前 | 既定 | 説明 |
| --- | --- | --- |
| `port` | `/dev/ttyACM0` | シリアルポート |
| `max_linear` / `max_angular` | `0.5` / `2.0` | フルスケールの vx[m/s] / wz[rad/s] |
| `wheel_setpoint` | `10.5` | フルスケール時の開ループ setpoint |
| `turn_sign` | `1.0` | 旋回方向。実機が逆なら `-1.0`（REP-103: +wz=左旋回） |
| `cmd_timeout` | `0.4` | ウォッチドッグ [s]。cmd_vel が途絶えたら全輪停止 |

> ⚠️ シリアルポートは 1 プロセス占有。`mbed_driver` と素のシリアルツールは同時起動できない。

---

## ラズパイ実機での bring-up（config → デモ）

配線済みの ML3 を Raspberry Pi（ROS2 Humble）から**設定 〜 デモ走行**まで動かす手順。**確認は必ず車輪を浮かせて**から行うこと（全開 PWM で台から飛び出す・突入電流が出る）。

> **前提（このリポジトリ外で用意）**: 2× L298N + 4 モーターを配線し、モーター電源は 12V（LiPo 等、Nucleo からは取らない）。STM32 NUCLEO-F091RC に ML3 ファーム（Mbed / PlatformIO、`pio run -t upload`）を書き込み済みにして Pi に USB 接続し、`/dev/ttyACM0`（115200 baud）が見える状態にしておく。現キットはエンコーダ不動のため**オープンループ**（`PWM_CAP=1500` ≈ 37.5%）で動く。

### 1. Pi の config

```bash
# シリアルポートのアクセス権（初回のみ・再ログインで反映）
sudo usermod -aG dialout $USER
ls /dev/ttyACM*                  # ポート確認（通常 /dev/ttyACM0）

source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=11          # チーム分離用。自チームの ID に変更
```

### 2. ビルド

リポジトリのルートがそのまま colcon ワークスペース（`src/` を含む）。

```bash
git clone git@github.com:sarushili0430/kuas-mechlab3.git
cd kuas-mechlab3
rosdep install --from-paths src --ignore-src -r -y   # 初回のみ依存解決
colcon build --packages-select kuas_mechlab3
source install/setup.bash
```

### 3. 起動と方向確認（車輪を浮かせて）

端末を 2 つ使う（driver 起動中はシリアルを占有するため、素のシリアルツールとは併用不可）。

```bash
# 端末A: ドライバ
ros2 launch kuas_mechlab3 drivetrain_launch.py
# 端末B: teleop（tty が要るので別端末）
ros2 run kuas_mechlab3 teleop_keyboard
```

ポートや旋回方向を変えるときは launch ではなくノードを直接起動して上書きする:

```bash
ros2 run kuas_mechlab3 mbed_driver --ros-args -p port:=/dev/ttyACM0 -p turn_sign:=1.0
```

**方向チェック（重要）**: `w` で前進し、`a` で**反時計回り（左旋回, REP-103）**になるか確認する。期待と逆に回るなら `turn_sign:=-1.0` で再起動。指令が届いているかはテレメトリで確認できる:

```bash
ros2 topic echo /mbed_driver/wheel_pwm
```

### 4. デモ走行

teleop の端末で**キーを押している間だけ**動く（離すと停止）。

| キー | 動作 |
| --- | --- |
| `w` / `s` | 前進 / 後退 |
| `a` / `d` | 左旋回 / 右旋回 |
| `q` | 停止 |
| Ctrl+C | 終了（自動で停止を送出） |

`cmd_vel` は標準インターフェースなので、teleop の代わりに `teleop_twist_keyboard` や nav2 からも走らせられる。

> ⚠️ **安全**: Pi 側ウォッチドッグは cmd_vel が `cmd_timeout`（既定 0.4s）途絶えると全輪停止を送る（teleop が落ちても暴走しない）。ただし **USB が物理的に抜けた場合**は現ファームが最後の指令を保持し続ける（ファーム側ウォッチドッグ未実装）。無拘束デモの前は車輪を浮かせるか有線で。初回配線時の 1 輪ずつの方向検証には、別途 bring-up 用の per-wheel jog ツール（同じ `s1/s2/s3/s4/d` パケットを送る）を driver 停止中に使う。

---

## 前後カメラ (camera)

ロボットの**前後に USB Web カメラ（Logicool 等）**を付け、映像を JPEG 圧縮して ROS2 トピックに publish し、teleop 操縦者がブラウザで見られるよう HTTP（MJPEG）で配信する `kuas_mechlab3.camera` サブパッケージ。`camera_node` を前後で 2 つ起動して **source で JPEG 化した `sensor_msgs/CompressedImage`** を流し、`mjpeg_server` がそれを**購読**して `http://<pi>:8080/` で中継する。ラズパイ負荷を抑えるため、生画像ではなく圧縮済みフレームだけが DDS を流れる。

```
[front_camera] ──~/image_raw/compressed(CompressedImage,JPEG)──┐
[rear_camera]  ──~/image_raw/compressed────────────────────────┴─> [mjpeg_server] ──HTTP MJPEG──> ブラウザ（操縦者）
                                                （JPEG バイトをそのまま中継・再エンコードなし）
```

責任分離（リポジトリ方針どおり、純ロジックは pytest / cv2・ROS・I-O は colcon でテスト）:

| モジュール | 責任 | テスト |
| --- | --- | --- |
| `frame.py` | FOURCC 生成 / デバイス解決（純） | pytest |
| `mjpeg.py` | MJPEG over HTTP のフレーミング（純・バイト列のみ） | pytest |
| `capture.py` | cv2 デバイス I/O（`frame` に委譲） | colcon |
| `camera_node.py` | ROSノード: webcam → JPEG 化 → `~/image_raw/compressed` を publish | colcon |
| `mjpeg_server.py` | ROSノード: CompressedImage を購読し HTTP/MJPEG で中継 | colcon |

> カメラのデバイス番号（`/dev/video0` など）は**挿し直しや再起動で前後が入れ替わる**ことがある。確実に固定したいときは `ls -l /dev/v4l/by-id/` で出る安定したシンボリックリンク（例 `/dev/v4l/by-id/usb-...-video-index0`）を `front_device:=` / `rear_device:=` に渡す。

### 実行（ROS2 Humble 上）

```bash
colcon build --packages-select kuas_mechlab3
source install/setup.bash

# 前後カメラ + HTTP 配信をまとめて起動（device はロボットに合わせて上書き）
# 既定は Pi 向けに 320x240@30fps。解像度/fps は launch 引数で変更できる。
ros2 launch kuas_mechlab3 cameras_launch.py \
    front_device:=/dev/video0 rear_device:=/dev/video2
# 例: 画質優先（負荷増）。fps を上げるときは stream_fps も揃える
ros2 launch kuas_mechlab3 cameras_launch.py width:=640 height:=480 fps:=15.0 stream_fps:=15.0
```

操縦者の PC のブラウザで **`http://<ラズパイのIP>:8080/`** を開くと前後の映像が並んで表示される。ドライブトレイン（`drivetrain_launch.py` + `teleop_keyboard`）と併用すれば、映像を見ながらの teleop ができる。

> 単体のカメラだけ動かしたいときは `ros2 run kuas_mechlab3 camera_node --ros-args -r __node:=front_camera -p device:=/dev/video0` のようにノード単体でも起動できる（トピックは `/front_camera/image_raw/compressed`）。

### 主要パラメータ

`camera_node`:

| 名前 | 既定 | 説明 |
| --- | --- | --- |
| `device` | `0` | デバイス番号（`0`）または安定パス（`/dev/v4l/by-id/...`） |
| `width` / `height` | `320` / `240` | 解像度 [px]。Pi 向けの既定。負荷は画素数に比例 |
| `fps` | `30.0` | フレームレート（publish 周期もこれに従う） |
| `codec` | `MJPG` | USB 帯域節約用の FOURCC（カメラ→ホスト間） |
| `frame_id` | `camera` | ヘッダの座標フレーム（launch では front/rear を設定） |
| `jpeg_quality` | `80` | publish する JPEG の品質（1–100、帯域とのトレードオフ） |

`mjpeg_server`:

| 名前 | 既定 | 説明 |
| --- | --- | --- |
| `topics` | `[…/front_camera/image_raw/compressed, …/rear_camera/image_raw/compressed]` | 購読する CompressedImage トピック |
| `host` / `port` | `0.0.0.0` / `8080` | HTTP の待ち受け |
| `stream_fps` | `15.0` | HTTP 配信のフレームレート上限（カメラの fps と揃える） |

> **代替**: 標準の [`web_video_server`](https://github.com/RobotWebTools/web_video_server)（`sudo apt install ros-humble-web-video-server`）でも同じ `image_raw/compressed` トピックを HTTP/MJPEG 配信できる。`mjpeg_server` は依存を増やさず前後を 1 ページにまとめた自前版。

### テスト手順

**1. 純ロジック（ROS 不要・PC で即実行）**

`frame.py`（FOURCC / デバイス解決）と `mjpeg.py`（multipart 整形）は純 Python なので pytest で確認できる。

```bash
pytest src/kuas_mechlab3/test/test_frame.py src/kuas_mechlab3/test/test_mjpeg.py -v
```

**2. publish の確認（ROS2 Humble・実機）** — カメラを挿してビルド後:

```bash
ros2 launch kuas_mechlab3 cameras_launch.py front_device:=/dev/video0 rear_device:=/dev/video2

# 別端末で配信レートと中身を確認
ros2 topic hz /front_camera/image_raw/compressed       # ≈ fps 出ていれば OK
ros2 topic echo --no-arr /rear_camera/image_raw/compressed   # format=jpeg / data サイズを確認
ros2 run rqt_image_view rqt_image_view     # GUI があれば compressed トピックを選んで確認
```

**3. HTTP 配信（teleop 視点）の確認**

操縦者 PC のブラウザで `http://<ラズパイのIP>:8080/` を開き、前後の映像が更新されることを確認する。`curl -s http://<ip>:8080/ | grep stream` で index ページのストリーム URL も確認できる。映像が出ない場合は ① カメラの device パス、② `ros2 topic hz` でトピックが流れているか、③ ファイアウォール/ポート 8080 を順に切り分ける。

---

## ディレクトリ構成

```
.
├── .github/workflows/        # GitHub Actions（lint / test / ros2-build）
├── src/
│   └── kuas_mechlab3/        # ROS2 パッケージ（ament_python）
│       ├── kuas_mechlab3/    # パッケージ本体（Python ソース）
│       │   ├── __init__.py
│       │   ├── utils.py      # 純 Python のヘルパー（例: clamp）
│       │   ├── drive/        # ML3 ドライブトレイン（下記「ドライブトレイン」参照）
│       │   │   ├── kinematics.py      # 純: Twist→4輪ミキシング
│       │   │   ├── protocol.py        # 純: ワイヤ形式 / テレメトリ解析
│       │   │   ├── serial_link.py     # シリアル I/O（pyserial）
│       │   │   ├── mbed_driver.py     # ROSノード: cmd_vel→mbed
│       │   │   └── teleop_keyboard.py # ROSノード: キー→cmd_vel
│       │   └── camera/       # 前後 Web カメラ（下記「前後カメラ」参照）
│       │       ├── frame.py           # 純: FOURCC / デバイス解決
│       │       ├── mjpeg.py           # 純: MJPEG over HTTP フレーミング
│       │       ├── capture.py         # cv2 デバイス I/O
│       │       ├── camera_node.py     # ROSノード: webcam→JPEG→image_raw/compressed
│       │       └── mjpeg_server.py    # ROSノード: compressed 購読→HTTP 中継
│       ├── launch/           # ros2 launch ファイル（drivetrain / cameras）
│       ├── test/             # 純 Python のユニットテスト（pytest）
│       ├── package.xml       # ROS パッケージ定義 / 依存（rosdep）
│       ├── setup.py          # ament_python のパッケージ設定
│       └── setup.cfg
├── .python-version           # Python のバージョン固定（3.10.18）
├── pyproject.toml            # black / mypy / pytest / coverage / commitizen 設定
├── requirements.txt          # 純 Python のランタイム依存
├── requirements-dev.txt      # 開発ツール（black / mypy / pytest / lefthook / commitizen）
└── lefthook.yml              # Git フック（pre-commit / commit-msg）
```

> ROS2 のランタイム依存は `requirements.txt` ではなく、各パッケージの `package.xml`（rosdep）で宣言します。
