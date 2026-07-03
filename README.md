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
| `protocol.py` | ワイヤ形式生成 / テレメトリ解析 / サーボ形式・受領解析（文字列のみ） | pytest |
| `serial_link.py` | シリアルポート I/O（pyserial、`protocol` に委譲） | colcon |
| `mbed_driver.py` | ROS I/O（`cmd_vel` + `servo_cmd`）+ フェイルセーフ（ウォッチドッグ / 終了時停止） | colcon |
| `teleop_keyboard.py` | tty 入力 → cmd_vel | colcon |

### 実行（ROS2 Humble 上）

```bash
colcon build --packages-select kuas_mechlab3
source install/setup.bash

# ターミナルA: ドライバ（launch 経由）
ros2 launch kuas_mechlab3 drivetrain_launch.py
# ターミナルB: teleop（tty が要るので別ターミナルで）
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

### サーボ (アーム) 制御

肩・肘の 2 サーボ（DS3225, TIM15 50 Hz）は駆動輪と**同じシリアルポート**を共有するため、指令は `mbed_driver` 経由で送る。駆動パケット（終端 `d`）とは別系統の**サーボ専用パケット（終端 `a`）**なので、4 輪プロトコルには一切影響しない。

```
[ros2 topic pub] --servo_cmd(Float32MultiArray[deg])--> [mbed_driver] --serial "us1/us2/a"--> [mbed]
```

- **トピック**: `servo_cmd`（`std_msgs/Float32MultiArray`、`data=[肩deg, 肘deg]`）。要素が 2 未満なら警告して無視、多い分は捨てる。
- **単位**: ホスト側は**角度[deg]**、ワイヤは**パルス幅[µs]**。`mbed_driver` が `servo_min_deg..servo_max_deg`（既定 `0..180`）→ `servo_min_us..servo_max_us`（既定 `500..2500`）へ線形変換する。校正はパラメータで可能（再フラッシュ不要）。
- **開ループ・姿勢保持**: サーボはフィードバック無し。指令が途切れても最後の姿勢を**保持**する（車輪のようなウォッチドッグ中立化はしない＝アームが不意に動かない）。ファーム起動時はパルス無し（無通電）で、最初の `servo_cmd` が来るまで動かない。
- **安全帯**: ホスト・ファームの両方で µs を `[500, 2500]` にクランプ（機械端の手前で飽和）。

例（`mbed_driver` 起動中。肩=90°, 肘=45° へ）:

```bash
ros2 topic pub -1 /servo_cmd std_msgs/msg/Float32MultiArray "{data: [90.0, 45.0]}"
```

単体ブリングアップ（`mbed_driver` を止めてポートを空けてから。ファームの受領確認 `srv <us1> <us2>` を表示）:

```bash
python3 scripts/pi-servojog.py <肩deg> <肘deg> [保持秒]
```

| 名前 | 既定 | 説明 |
| --- | --- | --- |
| `servo_min_us` / `servo_max_us` | `500` / `2500` | パルス幅の下限 / 上限 [µs]（安全帯） |
| `servo_min_deg` / `servo_max_deg` | `0.0` / `180.0` | 角度→パルス幅マップの両端 [deg] |

---

## Nucleo ファームウェア（mbed）

`mbed_driver` の通信相手となる **STM32 NUCLEO-F091RC のファームウェア**。このリポジトリの Python 側は以下の「契約」でシリアル通信する（`protocol.py` / `test_protocol.py` が正）ので、Nucleo にはこの契約を満たすファームを**書き込んでおく必要がある**。モーターが全く動かないときは、まずこのファームが焼かれているか・契約が一致しているかを疑うこと。

| 方向 | 形式 | 例 |
| --- | --- | --- |
| Pi → Nucleo（駆動指令） | `s1/s2/s3/s4/d`（float 4 つを `/` 区切り、終端は文字 `d`。改行なし） | `10.50/10.50/-10.50/-10.50/d` |
| Pi → Nucleo（サーボ指令） | `us1/us2/a`（int 2 つ [µs] を `/` 区切り、終端は文字 `a`。改行なし） | `1500/900/a` |
| Nucleo → Pi（テレメトリ） | `sp .. \| rpm .. \| pwm ..` を 1 行ずつ（改行区切り） | `sp 10.50 10.50 0.00 0.00 \| rpm 0.00 0.00 0.00 0.00 \| pwm 2500 2500 0 0` |
| Nucleo → Pi（サーボ受領） | `srv us1 us2` を 1 行（サーボ指令の直後のみ） | `srv 1500 900` |

- ボーレート **115200**、ST-Link の USB シリアル（`/dev/ttyACM0`）を使う。
- 駆動（終端 `d`）とサーボ（終端 `a`）は**別終端の独立パケット**。ファームは両者を別々にパースし、`srv` 行は `rpm`/`pwm` を含まないので `parse_telemetry` に無視される（駆動テレメトリと干渉しない）。→ 4 輪プロトコルは無改修のまま。
- 車輪の対応（公称）は `s1=FL / s2=BL / s3=FR / s4=BR`（`kinematics.py` と同じ）。スキッドステアでは **左側=s1,s2 / 右側=s3,s4** のグルーピングだけが効くので、各輪の前進向きはファーム側の符号 `DIR[4]`（`main.cpp`）で吸収する。2026-06-16 のジョグ試験で `DIR={-1,+1,-1,+1}` と確定（実機物理コーナーは ch0=後左, ch1=前左, ch2=後右, ch3=前右）。1 輪が逆回転するときは該当 `DIR[i]` を反転して再フラッシュ（下記「モーターアライメント検証」）。
- setpoint のフルスケールは **±10.5**（Pi 側の `wheel_setpoint` 既定値と揃える）。エンコーダ不動のため**オープンループ**で、`|sp|=10.5` を `PWM_CAP=2500`（分母 4000 ≈ 62.5%）の PWM に直結する。
- **ファーム側ウォッチドッグ入り**: 指令が 0.5 秒途絶える（USB 抜け・Pi 側クラッシュ含む）と全輪停止する。
- **サーボ（肩・肘）は姿勢保持**: 車輪と違いウォッチドッグの対象外で、指令が途切れても最後のパルスを保持する（アームが不意に動かない）。起動時はパルス無し（無通電）で、最初のサーボ指令が来るまで動かない。µs はホスト・ファーム両方で **[500, 2500]** にクランプ（機械端の手前で飽和）。

### ピン割当（Tomoe-11 配線）

実機の配線は [`docs/robot-pinout-power-reference.md`](./docs/robot-pinout-power-reference.md)（PDF 版 `docs/robot-pinout-power-reference.pdf` も同梱。Tomoe-11 — Pinout & Power Reference）が正。L298N は **ENA/ENB ジャンパ ON のまま IN ピンを直接 PWM** する（モーター 1 個につき PWM 2 本の sign-magnitude 駆動。EN ピンは使わない）:

| 車輪 | L298N in | はんだパッド | MCU | ファームトークン | Timer·ch |
| --- | --- | --- | --- | --- | --- |
| s1: M1 FL（左前） | IN1 / IN2 | D7 / D8 | PA_8 / PA_9 | `D7` / `D8` | TIM1_CH1 / CH2 |
| s2: M2 BL（左後） | IN3 / IN4 | D5 / D4 | PB_4 / PB_5 | `D5` / `D4` | TIM3_CH1 / CH2 |
| s3: M3 FR（右前） | IN1 / IN2 | D11 / D12 | PA_7 / PA_6 | `PA_7_ALT2` / `PA_6_ALT0` | TIM17_CH1 / TIM16_CH1 |
| s4: M4 BR（右後） | IN3 / IN4 | D2 / PA_11 | PA_10 / PA_11 | `D2` / `PA_11` | TIM1_CH3 / CH4 |

> `_ALT` トークンは内部タイマーを選ぶ**ファームウェア専用表記**（はんだ付けするパッドは silk どおり D11/D12）。M3 だけ TIM16/17 に逃がすのは TIM1/TIM3 のチャネルと衝突させないため。

サーボ（アーム）は **TIM15**（駆動タイマーと非衝突）で 50 Hz PWM を出す。信号線のみ Nucleo、V+/GND は専用サーボレールへ（詳細は pinout reference §1d/§4）:

| サーボ | はんだパッド | MCU | ファームトークン | Timer·ch |
| --- | --- | --- | --- | --- |
| Servo 1（肩 shoulder） | PB_14 | PB_14 | `PB_14_ALT0` | TIM15_CH1 |
| Servo 2（肘 elbow） | PB_15 | PB_15 | `PB_15_ALT1` | TIM15_CH2 |

### プロジェクト構成（PlatformIO）

ファームの実体は **`firmware/robot/`** にある。PC（または Pi）に [PlatformIO Core](https://platformio.org/install/cli)（`pip install platformio`）を入れてビルドする:

```
firmware/robot/
├── platformio.ini
├── mbed_app.json
└── src/
    └── main.cpp
```

`platformio.ini`:

```ini
[env:nucleo_f091rc]
platform = ststm32
board = nucleo_f091rc
framework = mbed
```

`mbed_app.json` — **必須**。Mbed OS 6 既定の minimal-printf は `%f` を出力できず、テレメトリが `sp %f ...` のまま壊れて `parse_telemetry` に全行捨てられるため、浮動小数点出力を有効化する:

```json
{
  "target_overrides": {
    "*": {
      "platform.minimal-printf-enable-floating-point": true,
      "platform.minimal-printf-set-floating-point-max-decimals": 2
    }
  }
}
```

`src/main.cpp`:

```cpp
#include "mbed.h"
#include <cstdio>
#include <cstring>

// ===== Tomoe-11 ピン割当（robot-pinout-power-reference.pdf §1a が正） =====
// L298N は ENA/ENB ジャンパ ON のまま、IN ピンを直接 PWM する
// （モーター 1 個につき PWM 2 本の sign-magnitude 駆動。EN ピンは使わない）。
struct MotorPins {
    PinName in1;  // 正転側
    PinName in2;  // 逆転側
};
static const MotorPins MOTOR_PINS[4] = {
    {D7, D8},                // s1/ch0: M1（公称 FL）PA_8 TIM1_CH1 / PA_9 TIM1_CH2 — 実機物理=後左 BL
    {D5, D4},                // s2/ch1: M2（公称 BL）PB_4 TIM3_CH1 / PB_5 TIM3_CH2 — 実機物理=前左 FL
    {PA_7_ALT2, PA_6_ALT0},  // s3/ch2: M3（公称 FR）D11 TIM17_CH1 / D12 TIM16_CH1 — 実機物理=後右 BR
    {D2, PA_11},             // s4/ch3: M4（公称 BR）PA_10 TIM1_CH3 / PA_11 TIM1_CH4 — 実機物理=前右 FR
};

// 各輪の正転符号: +1 なら +setpoint で前進、-1 で反転。
// 2026-06-16 のジョグ試験でハード確定（arthur/dev で end-to-end 検証済み）。
// 物理コーナー: ch0=後左(BL), ch1=前左(FL), ch2=後右(BR), ch3=前右(FR)。
// 左側=ch0+ch1 / 右側=ch2+ch3 はスキッドステアの左右グルーピングと一致するので、
// ホスト側 kinematics（s1,s2=左 / s3,s4=右）は無改修でよい。
// 1 輪が逆回転する場合は該当 DIR[i] の符号を反転して再フラッシュ（scripts/pi-jog.py で確認）。
static const int DIR[4] = {-1, +1, -1, +1};

static const float SP_FULL      = 10.5f;  // Pi 側 wheel_setpoint と揃える
static const int   PWM_MAX      = 4000;   // pwm テレメトリの分母
static const int   PWM_CAP      = 2500;   // ≈62.5%。突入電流・速度を抑える上限
static const int   PWM_FREQ_HZ  = 20000;  // 可聴域より上
static const int   WATCHDOG_MS  = 500;    // 指令が途絶えたら全停止
static const int   TELEMETRY_MS = 20;     // テレメトリ 50 Hz

class L298NMotor {
public:
    explicit L298NMotor(const MotorPins& p) : in1_(p.in1), in2_(p.in2) {
        in1_.period_us(1000000 / PWM_FREQ_HZ);
        in2_.period_us(1000000 / PWM_FREQ_HZ);
        apply(0);
    }
    // pwm: -PWM_MAX..PWM_MAX（PWM_CAP で飽和）。符号が回転方向。
    // 正転は IN1 に PWM・IN2=0、逆転はその逆（fast-decay / coast）。
    void apply(int pwm) {
        if (pwm >  PWM_CAP) pwm =  PWM_CAP;
        if (pwm < -PWM_CAP) pwm = -PWM_CAP;
        pwm_ = pwm;
        float duty = float(pwm >= 0 ? pwm : -pwm) / PWM_MAX;
        in1_.write(pwm > 0 ? duty : 0.0f);
        in2_.write(pwm < 0 ? duty : 0.0f);
    }
    int pwm() const { return pwm_; }

private:
    PwmOut in1_, in2_;
    int pwm_ = 0;
};

static BufferedSerial pc(USBTX, USBRX, 115200);

static int elapsed_ms(const Timer& t) {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
               t.elapsed_time())
        .count();
}

int main() {
    L298NMotor motors[4] = {
        L298NMotor(MOTOR_PINS[0]), L298NMotor(MOTOR_PINS[1]),
        L298NMotor(MOTOR_PINS[2]), L298NMotor(MOTOR_PINS[3]),
    };
    pc.set_blocking(false);

    float sp[4] = {0.0f, 0.0f, 0.0f, 0.0f};
    char rx[64];
    size_t rx_len = 0;
    Timer cmd_timer, tel_timer;
    cmd_timer.start();
    tel_timer.start();

    while (true) {
        // --- 受信: 終端 'd' までためて "s1/s2/s3/s4" をパース ---
        char c;
        while (pc.read(&c, 1) == 1) {
            if (c == 'd') {
                rx[rx_len] = '\0';
                float v[4];
                if (sscanf(rx, "%f/%f/%f/%f", &v[0], &v[1], &v[2], &v[3]) == 4) {
                    for (int i = 0; i < 4; i++) {
                        sp[i] = v[i];
                        motors[i].apply(int(DIR[i] * v[i] / SP_FULL * PWM_CAP));
                    }
                    cmd_timer.reset();
                }
                rx_len = 0;
            } else if (rx_len < sizeof(rx) - 1) {
                rx[rx_len++] = c;
            } else {
                rx_len = 0;  // 壊れたパケットは捨てて次の 'd' で再同期
            }
        }

        // --- ウォッチドッグ: USB 抜け・Pi 停止でも確実に止める ---
        if (elapsed_ms(cmd_timer) > WATCHDOG_MS) {
            for (int i = 0; i < 4; i++) {
                sp[i] = 0.0f;
                motors[i].apply(0);
            }
        }

        // --- テレメトリ: 50 Hz（エンコーダ不動のため rpm は常に 0） ---
        if (elapsed_ms(tel_timer) >= TELEMETRY_MS) {
            tel_timer.reset();
            char line[120];
            int n = snprintf(
                line, sizeof(line),
                "sp %.2f %.2f %.2f %.2f | rpm 0.00 0.00 0.00 0.00 | pwm %d %d %d %d\n",
                sp[0], sp[1], sp[2], sp[3],
                motors[0].pwm(), motors[1].pwm(), motors[2].pwm(), motors[3].pwm());
            pc.write(line, n);
        }
        ThisThread::sleep_for(1ms);
    }
}
```

### 書き込み手順

Nucleo を USB で PC に接続して（ST-Link 側のミニ USB）:

```bash
cd firmware/robot
pio run                 # ビルド
pio run -t upload       # ST-Link 経由で書き込み
```

PlatformIO を使わない場合は、ビルドで出た `.pio/build/nucleo_f091rc/firmware.bin` を、マウントされた `NODE_F091RC` ドライブに**ドラッグ & ドロップ**するだけでも書き込める。

### ファーム単体での動作確認（driver なし・車輪を浮かせて）

書き込み後、Pi（または PC）から素のシリアルで契約どおり動くか確認できる（`mbed_driver` とは**同時に開けない**ので必ず driver 停止中に行う）:

```bash
stty -F /dev/ttyACM0 115200 raw -echo

# テレメトリが流れてくるか（"sp .. | rpm .. | pwm .." が 50 Hz で出れば OK）
timeout 2 cat /dev/ttyACM0

# 全輪をゆっくり回す（→ 0.5 秒後にウォッチドッグで自動停止すれば OK）
printf '3.00/3.00/3.00/3.00/d' > /dev/ttyACM0

# 明示停止
printf '0.00/0.00/0.00/0.00/d' > /dev/ttyACM0
```

ここまで通れば、あとは「ラズパイ実機での bring-up」どおり `mbed_driver` を起動するだけで動く。**指令を送ってもテレメトリの `pwm` が変わるのにモーターが回らない**場合は配線（EN ジャンパ・IN ピン・モーター電源 12V）側、`pwm` 自体が変わらない場合はピン割当かパケット形式のずれを疑う。

### モーターアライメント検証（scripts/）

各輪の前進向き（ファームの `DIR[4]`）は **`scripts/` の素のシリアルツール**で検証する。どちらも ROS 非依存（pyserial のみ）で `mbed_driver` と同じ `s1/s2/s3/s4/d` を送るため、**`mbed_driver` 停止中・車輪を浮かせて**実行する。

```bash
# 1 輪ずつ前進方向に回し、その輪のチャンネルだけが energize されるか確認
python3 scripts/pi-jog.py 0     # 以降 1, 2, 3（ch0=後左 / ch1=前左 / ch2=後右 / ch3=前右）
# 逆回転した輪は firmware/robot/src/main.cpp の該当 DIR[i] を反転 → 再ビルド・再フラッシュ

# 全体運動の確認（left/right は REP-103 / turn_sign=+1 準拠）
python3 scripts/pi-drivetest.py forward     # backward | left | right | stop
```

> 旋回（`a`/`d`）が逆になるのは各輪の前進向きではなく左右割当の問題なので、ファームではなく driver の `turn_sign` で直す。各輪の向きと直進が確認できたら、通常の teleop（`ros2 launch kuas_mechlab3 teleop_launch.py` / `ros2 run kuas_mechlab3 teleop_keyboard`）へ進む。

---

## ラズパイ実機での bring-up（config → デモ）

配線済みの ML3 を Raspberry Pi（ROS2 Humble）から**設定 〜 デモ走行**まで動かす手順。**確認は必ず車輪を浮かせて**から行うこと（全開 PWM で台から飛び出す・突入電流が出る）。

> **前提**: 2× L298N + 4 モーターを配線し、モーター電源は 12V（LiPo 等、Nucleo からは取らない）。STM32 NUCLEO-F091RC に上の「**Nucleo ファームウェア（mbed）**」を書き込み済みにして Pi に USB 接続し、`/dev/ttyACM0`（115200 baud）が見える状態にしておく。現キットはエンコーダ不動のため**オープンループ**（`PWM_CAP=2500` ≈ 62.5%）で動く。

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

ターミナルを 2 つ使う（driver 起動中はシリアルを占有するため、素のシリアルツールとは併用不可）。

```bash
# ターミナルA: ドライバ
ros2 launch kuas_mechlab3 drivetrain_launch.py
# ターミナルB: teleop（tty が要るので別ターミナル）
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

teleop のターミナルで**キーを押している間だけ**動く（離すと停止）。

| キー | 動作 |
| --- | --- |
| `w` / `s` | 前進 / 後退 |
| `a` / `d` | 左旋回 / 右旋回 |
| `q` | 停止 |
| Ctrl+C | 終了（自動で停止を送出） |

`cmd_vel` は標準インターフェースなので、teleop の代わりに `teleop_twist_keyboard` や nav2 からも走らせられる。

> ⚠️ **安全**: Pi 側ウォッチドッグは cmd_vel が `cmd_timeout`（既定 0.4s）途絶えると全輪停止を送る（teleop が落ちても暴走しない）。さらに上の「Nucleo ファームウェア（mbed）」にはファーム側ウォッチドッグ（0.5s）があり、**USB が物理的に抜けても**全輪停止する。古いファームのままだと最後の指令を保持し続けるので、無拘束デモの前に必ず最新ファームを書き込み、車輪を浮かせて確認すること。初回配線時の 1 輪ずつの方向検証には、`scripts/pi-jog.py`（同じ `s1/s2/s3/s4/d` パケットを送る per-wheel jog ツール）を driver 停止中に使う（上記「モーターアライメント検証」）。

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

# 別ターミナルで配信レートと中身を確認
ros2 topic hz /front_camera/image_raw/compressed       # ≈ fps 出ていれば OK
ros2 topic echo --no-arr /rear_camera/image_raw/compressed   # format=jpeg / data サイズを確認
ros2 run rqt_image_view rqt_image_view     # GUI があれば compressed トピックを選んで確認
```

**3. HTTP 配信（teleop 視点）の確認**

操縦者 PC のブラウザで `http://<ラズパイのIP>:8080/` を開き、前後の映像が更新されることを確認する。`curl -s http://<ip>:8080/ | grep stream` で index ページのストリーム URL も確認できる。映像が出ない場合は ① カメラの device パス、② `ros2 topic hz` でトピックが流れているか、③ ファイアウォール/ポート 8080 を順に切り分ける。

---

## リモート teleop (WebSocket)

操縦者の PC（ブラウザや手元のクライアント）から **WebSocket で `cmd_vel` を送る**ための `kuas_mechlab3.drive` の teleop ブリッジ。`teleop_server` が WS で正規化済みのドライブ指令 `{"vx", "wz"}`（各軸 -1..1）を受け取り、`teleop_keyboard` と同じく一定レートで `geometry_msgs/Twist` を `cmd_vel` に publish する。`cmd_vel` は標準インターフェースなので **`mbed_driver` / `kinematics` / ウォッチドッグには一切手を入れない**（`teleop_keyboard` をネットワーク越しにしただけ）。

```
[ブラウザ / teleop_ws_client] ──WS {"vx","wz"}(-1..1)──> [teleop_server] ──cmd_vel(Twist)──> [mbed_driver] ──serial──> [mbed]
        （操縦者PC）                                      （一定レートで republish、切断/無入力で 0）
```

責任分離（リポジトリ方針どおり、純ロジックは pytest / ROS・I-O は colcon でテスト）:

| モジュール | 責任 | テスト |
| --- | --- | --- |
| `teleop_command.py` | 純: JSON 指令の解析（不正は None）/ 正規化→物理量スケール（`utils.clamp` を再利用） | pytest |
| `teleop_server.py` | ROSノード: WS サーバ（背景 asyncio スレッド）+ 一定レートで `cmd_vel` を publish | colcon |
| `teleop_ws_client.py` | 操縦者 PC 用の簡易 WS クライアント（WASD→WS、rclpy 非依存） | 手動 |

**安全（三層・既存に上乗せ）**: ① WS 切断で次サイクルに即ゼロ（最速）② `hold_timeout`（既定 0.4s）で無入力なら減衰してゼロ ③ `mbed_driver` の `cmd_timeout` ウォッチドッグ（最終網・無変更）。WS 組み込みの ping/pong（`ping_interval`/`ping_timeout`）で、停止したクライアントの切断も検知する。

> 📄 **ブラウザ等から繋ぐ手順**（WS の接続方法と、カメラ映像を `<img>` で受け取る方法、最小コックピット HTML 例）は [`docs/teleop-client.md`](./docs/teleop-client.md) にまとめている。

### 実行（ROS2 Humble 上）

```bash
colcon build --packages-select kuas_mechlab3
source install/setup.bash

# ターミナルA: driver
ros2 launch kuas_mechlab3 drivetrain_launch.py
# ターミナルB: WS teleop ブリッジ（tty 不要なので launch 可）
ros2 launch kuas_mechlab3 teleop_launch.py
# ターミナルC: 手元から操縦（WASD）。別 PC からは --url を Pi の IP に
ros2 run kuas_mechlab3 teleop_ws_client --url ws://localhost:9001
```

カメラ（`cameras_launch.py`）も併用すれば、ブラウザで映像（`http://<ラズパイのIP>:8080/`）を見ながら WS で操縦できる。

### ワイヤ形式

1 メッセージ = JSON テキスト 1 個。`vx`/`wz` は **正規化済みの軸値 [-1, 1]**（`teleop_server` が `max_linear`/`max_angular` で物理量へスケール）。

```json
{"vx": 0.5, "wz": -0.3}
```

### 主要パラメータ（teleop_server）

| 名前 | 既定 | 説明 |
| --- | --- | --- |
| `host` / `port` | `0.0.0.0` / `9001` | WS の待ち受け（カメラの 8080 とは別ポート） |
| `publish_rate` | `20.0` | `cmd_vel` の publish レート [Hz] |
| `hold_timeout` | `0.4` | 無入力で 0 に落とすまで [s]（`teleop_keyboard` と同値） |
| `max_linear` / `max_angular` | `0.5` / `2.0` | 正規化 1.0 に割り当てる vx[m/s] / wz[rad/s]（`mbed_driver` と揃える） |
| `deadzone` | `0.05` | 軸のデッドゾーン（スティックのドリフト除去） |
| `ping_interval` / `ping_timeout` | `5.0` / `5.0` | WS keepalive [s]（無応答クライアントの切断検知） |

### テスト手順

**1. 純ロジック（ROS 不要・PC で即実行）**

`teleop_command.py`（JSON 解析 / スケール）は純 Python なので pytest で確認できる。

```bash
pytest src/kuas_mechlab3/test/test_teleop_command.py -v
```

**2. WS → cmd_vel の確認（ROS2 Humble・車輪を浮かせて）**

```bash
ros2 launch kuas_mechlab3 teleop_launch.py
# 別ターミナルで publish を確認
ros2 topic echo /cmd_vel
# さらに別ターミナルから送信（同梱クライアント、または依存ゼロの websocat）
ros2 run kuas_mechlab3 teleop_ws_client --url ws://localhost:9001
#   echo '{"vx":0.5,"wz":0.0}' | websocat ws://localhost:9001
```

送信中だけ Twist が出て、送信停止／切断後に `hold_timeout` 内でゼロへ戻れば OK。

> **代替**: ブラウザから直接やるなら標準の [`rosbridge_suite`](https://github.com/RobotWebTools/rosbridge_suite)（`sudo apt install ros-humble-rosbridge-suite`）でも、roslibjs から `cmd_vel` を直接 publish でき、全トピック（テレメトリ含む）にアクセスできる。`teleop_server` は依存を増やさず teleop 専用に絞った自前版。

### 実機リモート操縦の手順書（ラズパイ側 / PC 側）

役割分担はシンプル: **ラズパイ＝ロボット本体。ここで ROS を動かす**。**PC＝操縦者。ブラウザだけ。ROS は要らない**。**必ず車輪を浮かせて**から始めること。

前提（初回だけ。詳細は上の「ラズパイ実機での bring-up」と同じ）: 配線・ファーム書き込み済み、`/dev/ttyACM0` が見える、前後カメラを USB 接続済み、ラズパイにこのリポジトリを clone 済み、シリアル権限 `sudo usermod -aG dialout $USER`（実行後に再ログイン）。

#### A. ラズパイ側でやること

ラズパイで**ターミナルを 3 つ**開く（`tmux` のペイン分割でも可）。**3 つすべての先頭で**まず次を実行する（`ROS_DOMAIN_ID` を 3 ターミナルで同じ値にするのが肝心。違うとノード同士が見えない）:

```bash
cd ~/kuas-mechlab3
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=11                       # 3 ターミナルとも同じ値にする
# 初回だけビルド（2 回目以降は不要）:
# colcon build --packages-select kuas_mechlab3
source install/setup.bash
```

そのうえで、ターミナルごとに 1 つずつ起動する:

```bash
# ターミナル1: モーター driver（/dev/ttyACM0 を使う）
ros2 launch kuas_mechlab3 drivetrain_launch.py

# ターミナル2: 前後カメラ + 映像配信（device は実機に合わせる。ls /dev/video* で確認）
ros2 launch kuas_mechlab3 cameras_launch.py front_device:=/dev/video0 rear_device:=/dev/video2

# ターミナル3: WebSocket teleop ブリッジ
ros2 launch kuas_mechlab3 teleop_launch.py
```

最後に**ラズパイの IP を調べてメモ**する（PC 側で使う）:

```bash
hostname -I        # 例: 192.168.1.42  ← 先頭のアドレス
```

これでラズパイ側は完了。**カメラ＝ポート 8080 / 操縦＝ポート 9001** で待ち受けている状態。

#### B. PC 側でやること（操縦者・ROS 不要）

ラズパイと**同じ Wi-Fi / LAN** に繋いだ PC で、ブラウザだけで完結する。

1. リポジトリの **[`docs/cockpit.html`](./docs/cockpit.html) を PC にコピー**する（GitHub から保存、または `scp <pi-user>@<pi-ip>:~/kuas-mechlab3/docs/cockpit.html .`）。
2. テキストエディタで開き、先頭付近の行
   ```js
   const PI = location.hostname || "192.168.1.42";
   ```
   の **`"192.168.1.42"` をラズパイの IP に書き換えて保存**する。
3. その `cockpit.html` を**ダブルクリックして開く**（ブラウザで `file://…`）。
4. ページを一度クリックしてフォーカスを当て、**W=前進 / S=後退 / A=左旋回 / D=右旋回**。前後カメラが映り、画面上部に `WS: connected` と出れば接続成功。

> 映像だけ確認したいときは、PC のブラウザで **`http://<ラズパイのIP>:8080/`** を開くだけでもよい。

#### 動いたかの確認 / うまくいかないとき

- ラズパイのターミナル1（driver）に指令ログが出る。別ターミナル（要 `source` + 同じ `ROS_DOMAIN_ID`）で `ros2 topic echo /mbed_driver/wheel_pwm` を見ると値が変わるのも確認できる。
- **キーを離す / タブを閉じる / Wi-Fi が切れる → 0.4 秒以内に停止**する（設計どおりの安全動作）。
- 旋回が逆 → クライアントではなく driver の `turn_sign` で直す（上の「主要パラメータ」/「bring-up」参照）。
- 画面が `WS: closed` のまま → IP とポート 9001、PC とラズパイが同じ LAN か、ファイアウォール（必要なら `sudo ufw allow 8080/tcp` と `sudo ufw allow 9001/tcp`）を確認。
- 映像が出ない → device パス（`ls /dev/video*`）と `http://<ip>:8080/` の直開きで切り分け。詳細は [docs/teleop-client.md](./docs/teleop-client.md)。

#### 終了

各ターミナルで `Ctrl+C`（teleop は終了時に自動で停止指令を送る）。

#### 一発起動スクリプト（`scripts/`）

上の「ターミナルごとに `source` してから launch を 1 つずつ」を、スクリプト 1 発に置き換えたもの。`source`（ROS2 本体 + `install/setup.bash`）・`ROS_DOMAIN_ID` の設定はスクリプト内でやるので、**素の新しいターミナルでそのまま実行してよい**（事前 `source` 不要）。前提は手動手順と同じ（`colcon build` 済み・`/dev/ttyACM0` と前後カメラが見える）。

| スクリプト | 起動するもの | 待ち受け |
| --- | --- | --- |
| `scripts/start-teleop.sh` | テレオプ WebSocket ブリッジ（`teleop_launch.py`） | `ws://<ラズパイのIP>:9001` |
| `scripts/start-cameras.sh` | 前後カメラ + MJPEG 配信（`cameras_launch.py`） | `http://<ラズパイのIP>:8080/` |
| `scripts/start-all.sh` | driver + カメラ + teleop を 1 プロセスで束ねて起動 | 上記の両方 |
| `scripts/lib-ros-env.sh` | 共通の環境セットアップ（各スクリプトが `source` する。直接は実行しない） | — |

共通の上書き用環境変数（どのスクリプトでも効く）:

| 環境変数 | 既定値 | 意味 |
| --- | --- | --- |
| `ROS_DOMAIN_ID` | `11` | DDS ドメイン。**PC 側で別ノードを動かすなら合わせる**（手動手順と同じ） |
| `ROS_SETUP` | `/opt/ros/humble/setup.bash` | ROS2 本体の `setup.bash`。Humble 以外を使うとき用 |

**`scripts/start-teleop.sh`** — テレオプだけ（driver もカメラも既に動いている時に、ブリッジだけ立て直したい等）。

```bash
./scripts/start-teleop.sh
# launch 引数はそのまま渡せる（teleop_launch.py の DeclareLaunchArgument）:
./scripts/start-teleop.sh port:=9001 max_linear:=0.5 max_angular:=2.0
```

**`scripts/start-cameras.sh`** — カメラ + 映像配信だけ。device は環境変数で、その他は launch 引数で渡す。

```bash
./scripts/start-cameras.sh
# 前後カメラの device を変える（既定は front=/dev/video0 rear=/dev/video2。ls /dev/video* で確認）:
FRONT_DEVICE=/dev/video0 REAR_DEVICE=/dev/video2 ./scripts/start-cameras.sh
# 解像度・FPS は launch 引数で:
./scripts/start-cameras.sh width:=640 height:=480 fps:=15.0 stream_fps:=15.0
```

**`scripts/start-all.sh`** — driver + カメラ + teleop を 1 発。3 つを束ねて起動し、**`Ctrl+C` で全ノードへ停止指令を送ってまとめて落とす**。実機オペレーションの通常運用はこれ 1 本でよい。

```bash
./scripts/start-all.sh
# カメラ device の上書きはそのまま効く:
FRONT_DEVICE=/dev/video0 REAR_DEVICE=/dev/video2 ./scripts/start-all.sh
```

> `start-all.sh` は 3 つの launch をまとめるため、個別の launch 引数（`port:=` など）は受け取らない。値を変えたいときは各 launch ファイルの既定値を直すか、`start-teleop.sh` / `start-cameras.sh` を個別に使う。

PC 側（操縦者）の手順は上の **B.** と同じ（`docs/cockpit.html` を開くだけ）。映像だけなら `http://<ラズパイのIP>:8080/` を直接開く。

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
│       │   │   ├── kinematics.py       # 純: Twist→4輪ミキシング
│       │   │   ├── protocol.py         # 純: ワイヤ形式 / テレメトリ解析
│       │   │   ├── teleop_command.py   # 純: WS 指令の解析 / スケール
│       │   │   ├── serial_link.py      # シリアル I/O（pyserial）
│       │   │   ├── mbed_driver.py      # ROSノード: cmd_vel→mbed
│       │   │   ├── teleop_keyboard.py  # ROSノード: キー→cmd_vel
│       │   │   ├── teleop_server.py    # ROSノード: WS→cmd_vel
│       │   │   └── teleop_ws_client.py # 操縦者PC用の簡易 WS クライアント
│       │   └── camera/       # 前後 Web カメラ（下記「前後カメラ」参照）
│       │       ├── frame.py           # 純: FOURCC / デバイス解決
│       │       ├── mjpeg.py           # 純: MJPEG over HTTP フレーミング
│       │       ├── capture.py         # cv2 デバイス I/O
│       │       ├── camera_node.py     # ROSノード: webcam→JPEG→image_raw/compressed
│       │       └── mjpeg_server.py    # ROSノード: compressed 購読→HTTP 中継
│       ├── launch/           # ros2 launch ファイル（drivetrain / cameras / teleop）
│       ├── test/             # 純 Python のユニットテスト（pytest）
│       ├── package.xml       # ROS パッケージ定義 / 依存（rosdep）
│       ├── setup.py          # ament_python のパッケージ設定
│       └── setup.cfg
├── firmware/
│   └── robot/                # STM32 NUCLEO-F091RC ファーム（PlatformIO/Mbed。上記「Nucleo ファームウェア」参照）
├── docs/                     # 補足ドキュメント（teleop-client.md / cockpit.html / robot-pinout-power-reference.md(+.pdf)）
├── scripts/                  # bring-up 用スクリプト
│   ├── start-all.sh          # driver + カメラ + teleop を一発起動（Ctrl+C で一括停止）
│   ├── start-teleop.sh       # テレオプ WS ブリッジだけ起動
│   ├── start-cameras.sh      # 前後カメラ + MJPEG 配信だけ起動
│   ├── lib-ros-env.sh        # 上記が source する共通 ROS 環境セットアップ
│   ├── pi-jog.py             # per-wheel 方向検証（ROS 非依存・pyserial のみ）
│   └── pi-drivetest.py       # 4 輪まとめ駆動テスト（同上）
├── .python-version           # Python のバージョン固定（3.10.18）
├── pyproject.toml            # black / mypy / pytest / coverage / commitizen 設定
├── requirements.txt          # 純 Python のランタイム依存
├── requirements-dev.txt      # 開発ツール（black / mypy / pytest / lefthook / commitizen）
└── lefthook.yml              # Git フック（pre-commit / commit-msg）
```

> ROS2 のランタイム依存は `requirements.txt` ではなく、各パッケージの `package.xml`（rosdep）で宣言します。
