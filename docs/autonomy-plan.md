# 自律化 実行計画（Autonomy Plan）— teleop を模倣学習で習得する

固定ルートの teleop ロボットを、**PC 上のモデルが映像から `{vx, wz}` を生成し WebSocket で Pi に送って自律走行**させるまでの、フェーズ単位の詳細計画。AI エージェント（や人間）がこの文書だけを見て各フェーズを実行できることを狙う。

- 高レベルの俯瞰: README「自律化ロードマップ」。本書はその**実行詳細**。
- 設計の核: **両方向（ACT ゼロ学習 / SmolVLA finetune）を同じデータで開けておく**。共通基盤は **LeRobot データセット形式**。モデルは Phase 5 で 1 フラグ切替。
- **構成: 2 リポ** — ロボット（本リポ・ROS）と AI（別リポ・ROS 非依存）。境界は契約のみ（下記「リポジトリ構成（2 リポ）」）。

---

## 1. ゴールと不変条件

**ゴール**: 固定ルートを、PC 上のポリシーが前カメラ映像から `(vx, wz)` を生成し、`ws://<pi>:9001` に流して完走する。

**不変条件（ここは絶対に変えない）**:
- WS 境界 = `ws://<pi>:9001`、メッセージ `{"vx": <-1..1>, "wz": <-1..1>}`。**人間もモデルも同じスロットを埋める**。
- Pi 側（`teleop_server` → `cmd_vel` → `mbed_driver` → mbed、および 3 層の安全網）は**無変更**。モデルは「人間のテレオプ・クライアントの差し替え」でしかない。
- 学習ターゲット = `/cmd_norm`（WS 境界の正規化指令そのもの）。→ 学習と推論の出力空間が一致。

```
収集時:  [人間] cockpit.html / teleop_ws_client ──WS {vx,wz}──> [Pi] teleop_server ─> cmd_vel ─> mbed
              （同時に rosbag が /cmd_norm + カメラ + state を記録）
推論時:  [PC]  policy(映像) ──WS {vx,wz}──────────────────────> [Pi] teleop_server ─> cmd_vel ─> mbed
              （人間部分をモデルに差し替えただけ。安全網はそのまま）
```

---

## 1.5 リポジトリ構成（2 リポ）

AI（学習・推論）は**別リポジトリ**に分ける。両者は**データ/プロトコルの契約**でのみ繋がり、コード依存は無い。

| リポ | 役割 | 依存 | 含むもの |
| --- | --- | --- | --- |
| **kuas-mechlab3**（本リポ）| ロボット本体・データ収集・契約の正本 | ROS2 Humble・軽量 | Pi 側 ROS 一式、`/cmd_norm`、録画基盤、`recording.py`(schema)、本計画書 |
| **mechlab3-policy**（新規・想定名）| 学習・推論 | torch / lerobot / `rosbags` / `websockets`（**ROS 非依存**）| Phase 3 変換、Phase 5 学習、Phase 7 policy-runner、checkpoints |

**契約（これだけが境界）**:
- データ受け渡し: `datasets/raw/*/{bag, meta.json}`（schema = §3 / `recording.py`）。AI 側は `rosbags` で読む（**ROS 不要**）。
- 制御: WS `{"vx","wz"}` → `ws://<pi>:9001`（README teleop 節 / `docs/teleop-client.md`）。AI 側は `websockets` で送る。
- データセット本体は git に入れず **HF Hub or 共有ストレージ**で受け渡す。

→ GPU 機に ROS を入れる必要が無く、重い torch 依存が本リポの軽量 CI / `mypy --strict` / Pi 環境を汚さない。

---

## 2. 現在地（実装済み — Phase 1 / 2）

| 項目 | 実体 |
| --- | --- |
| 行動の publish | `teleop_server` が `/cmd_norm`（`geometry_msgs/TwistStamped`, vx=linear.x / wz=angular.z, [-1,1], ノードクロックの時刻付き）を `publish_rate`（20Hz）で出す |
| 正規化ロジック | `kuas_mechlab3.drive.teleop_command.command_to_norm`（純・pytest）。デッドゾーン前の生の意図 |
| エピソード録画 | `scripts/start-record.sh` → `scripts/record_episodes.py`（IO）+ `kuas_mechlab3.recording`（純・配置/スキーマ） |
| 録画の出力 | `datasets/raw/<日時>_<route>_NNN/` に `bag/`（rosbag2）+ `meta.json` |

**`meta.json` のスキーマ**（`kuas_mechlab3.recording.build_metadata`、`schema_version=1`）:
`route, operator, episode_index, started_at, stopped_at, duration_s, label(success|failure|unlabeled), notes, action_topic(/cmd_norm), image_topics, recorded_topics, bag_dir, ros_domain_id`。

**録画されるトピック**（既定 `kuas_mechlab3.recording.default_topics`）:
`/cmd_norm`（行動）, `/front_camera/image_raw/compressed`, `/rear_camera/image_raw/compressed`, `/cmd_vel`, `/mbed_driver/wheel_pwm`, `/mbed_driver/wheel_rpm`。

---

## 3. データ契約（model-agnostic の要）

両モデルが同じデータセットを食えるよう、**union（和集合）フィールド**を Phase 3 で必ず出力する。

| 決め事 | 値 / 方針 |
| --- | --- |
| 制御周波数 | **10 Hz**（カメラ 30fps・指令 20Hz より低いので安全にリサンプル可） |
| 観測（画像） | `observation.images.front`（必須）、`observation.images.rear`（任意）。学習用に収集解像度を上げてよい（teleop 配信の 320x240 と分離可） |
| 観測（状態） | `observation.state = [vx_{t-1}, wz_{t-1}]`（**直前の行動**。先頭フレームは `[0,0]`）。本キットはエンコーダ無しのため proprioception の代わり。**ACT・SmolVLA とも state 入力を期待するので必ず入れる** |
| 行動 | `action = [vx, wz]`（`/cmd_norm` 由来、[-1,1]） |
| 言語命令 | `task = "follow the route"`（定数。**SmolVLA が使い、ACT は無視**） |
| 付帯 | `timestamp, episode_index, frame_index`（LeRobot 標準） |

> **なぜ union か**: これで Phase 5 が `--policy.type=act` ↔ `--policy.path=lerobot/smolvla_base` の**フラグ 1 つで両方向**に進める。データの録り直しは不要。

---

## 4. フェーズ計画

各フェーズ: **目的 / 入力 / 出力 / 手順 / 受け入れ基準 / 落とし穴**。

> **Phase 3 / 5 / 7 は AI リポ `mechlab3-policy` で実施**（Phase 4・Pi 側・契約は本リポ）。以下の `scripts/...` 表記は AI リポ内のパスと読み替える。

### Phase 3 — bag → LeRobot データセット変換 ⬜（次の着手点）

- **目的**: `datasets/raw/*/bag` を LeRobot 形式（`datasets/lerobot/<name>`）へ変換。
- **入力**: rosbag2（sqlite3 or mcap）+ `meta.json`。
- **出力**: `LeRobotDataset`（parquet + mp4 + meta）。`label=success` のみ採用（`failure/unlabeled` は除外、ただしフラグで残せると良い）。
- **手順**:
  1. 依存: `lerobot`, `rosbags`（ROS 無しで bag を読める Python ライブラリ。dev PC で動く）, `opencv-python`, `av`。
  2. **AI リポ**の `convert_to_lerobot.py`（IO）。同期・リサンプルの純ロジックは AI リポ内のモジュールへ切り出し pytest 対象にする（本 ROS リポには置かない）。
  3. bag から `/cmd_norm`（stamp 付き）, 前後カメラ `CompressedImage`（JPEG, stamp 付き）を読む。
  4. **時刻同期**: `/cmd_norm` の `header.stamp` を基準に 10Hz グリッドを作り、各 tick で「**その時刻以前で最新の**カメラフレーム」と「その tick の行動」を対にする（未来フレームを覗かない）。
  5. `observation.state` = 直前 tick の `action`（先頭は `[0,0]`）。`task` = 定数文字列。
  6. JPEG フレーム列 → mp4（LeRobot の video backend）。
  7. `LeRobotDataset` の `create` / `add_frame` / `save_episode` 系 API で書き出し（正確な API は LeRobot のバージョンに従う。docs 参照）。
- **受け入れ基準**:
  - 1 エピソードを変換し、**映像に行動ベクトルを重ねて再生**して同期が目視で合う（ズレ検出）。
  - `action` の値域が [-1,1]、`state` が 1 tick 遅れで `action` と一致、フレーム数と tick 数が整合。
- **落とし穴**: stamp の単調性/欠落、JPEG→mp4 のフレームレート整合、エピソード境界、`success` 以外の除外漏れ。

### Phase 4 — データ収集（実走行）⬜

- **目的**: 学習に足る**量と多様性**を集める。
- **手順**: 別ターミナルで `scripts/start-all.sh`（driver+カメラ+teleop）→ `scripts/start-record.sh --route <r> --operator <name>`。`[Enter]` 開始 → 走る → `[Enter]` 保存（成功/失敗）/ `d` 破棄。
- **多様性**: 照明・時間帯・開始位置・人や障害物の有無を散らす。**リカバリ走行（わざとコースから外して戻す）を 2〜3 割混ぜる**（分布ズレ＝雪だるま誤差の対策。ここが成功率を左右する）。
- **量の目安**: 1 ルート **20〜50 本**（成功ラベル）。失敗は分析用に `label=failure` で残すか破棄。
- **受け入れ基準**: success エピソード数・総時間・リカバリ走行の割合を記録（`meta.json` から集計できる）。

### Phase 5 — 学習（両方向 / どちらも同じデータ）⬜

- **共通準備**: `lerobot` を clone/インストール。Phase 3 のデータセットを指定。GPU 1 枚（A100 でなくとも 450M は consumer GPU で可、ACT はさらに軽い）。
- **(A) ACT（ゼロから train）**: 軽く・速い・推論レイテンシ最小。固定単一ルートで十分動く。
  ```
  python -m lerobot.scripts.train \
    --policy.type=act \
    --dataset.repo_id=<your dataset> \
    --batch_size=8 --steps=100000
  ```
- **(B) SmolVLA（事前学習を finetune）**: 少データに強い・将来言語指示が可能。`lerobot/smolvla_base` を起点。
  ```
  python -m lerobot.scripts.train \
    --policy.path=lerobot/smolvla_base \
    --dataset.repo_id=<your dataset> \
    --batch_size=64 --steps=20000
  ```
- **出力**: `outputs/.../checkpoints/`。
- **受け入れ基準**: train loss 収束。ただし**オフライン誤差は当てにしない**（本番は Phase 6 の閉ループ）。
- **注**: CLI フラグは LeRobot のバージョンで変わる。SmolVLA は `docs/source/smolvla.mdx` / 下記リンクに従う。

### Phase 6 — 閉ループ評価 + 再収集（簡易 DAgger）⬜

- **目的**: **実機での完走率**でモデルを評価・改善。
- **手順**: Phase 7 の policy-runner で実走 → 完走/失敗/人間介入回数を記録 → 失敗したシーンの**リカバリ走行を追加収集**（Phase 4）→ 再学習（Phase 5）。これを回す。
- **受け入れ基準**: ルート完走率の目標（要設定。例 ≥ 90%）。
- **安全**: 必ず**人間オーバーライド（デッドマン）**を握って開始。低速から。

### Phase 7 — デプロイ（policy-runner）⬜

- **目的**: PC 上で推論し WS 送信。**人間クライアントの差し替え**。
- **AI リポの `policy_runner.py`**（ROS 非依存。MJPEG 取得は `requests`/`cv2`、送信は `websockets`）: 中身は「`teleop_ws_client` の人間入力をモデル推論に置換」。
- **入力**: 前カメラの MJPEG（`http://<pi>:8080/stream?topic=/front_camera/image_raw/compressed`）。ROS が PC にあるなら topic 購読でも可。
- **ループ**:
  ```python
  ws = websocket.connect("ws://<pi>:9001")
  while True:
      frame = grab_latest_jpeg(MJPEG_URL)
      state = [prev_vx, prev_wz]
      chunk = policy.select_action({"observation.images.front": frame,
                                    "observation.state": state,
                                    "task": "follow the route"})
      vx, wz = chunk[0]                       # or temporal ensemble
      ws.send(json.dumps({"vx": float(vx), "wz": float(wz)}))
      prev_vx, prev_wz = vx, wz
      sleep(1 / CONTROL_HZ)                   # 10–20Hz
  ```
- **遅延対策**: アクションチャンク（先の数 step をまとめて予測しオープンループ実行）でネットワーク往復を隠す。
- **安全**: 起動時は人間が握る / デッドマンキー / レート制限 / WS 切断で Pi 側が自動停止（既存）。
- **モデル切替**: `--checkpoint <act or smolvla の path>` だけ。WS 仕様・Pi 側は不変。
- **受け入れ基準**: まず**ダミーポリシー（直進だけ等）で WS 経路を疎通**確認 → 実モデルで完走。

---

## 5. 予定する成果物 / 配置

```
# kuas-mechlab3（本リポ・ROS）
datasets/raw/                     # 録画した bag + meta.json（.gitignore 済み。AI リポへ渡す素材）
docs/autonomy-plan.md             # 本計画書（契約の正本）

# mechlab3-policy（AI リポ・ROS 非依存・torch / lerobot）
pyproject.toml                    # 依存: torch, lerobot, rosbags, websockets, opencv-python, av
convert_to_lerobot.py             # Phase 3（bag + meta → LeRobot 形式）
src/.../sync.py  (+ tests)        # 同期 / リサンプルの純ロジック（pytest）
policy_runner.py                  # Phase 7（映像 → policy → WS {vx,wz}）
train/                            # Phase 5 の学習設定・起動
outputs/checkpoints/              # 学習済みモデル（git 非追跡）
datasets/lerobot/                 # Phase 3 出力（git 非追跡。or HF Hub）
```

---

## 6. 実装規約（AI が必ず従うこと）

> 下記は**本リポ（ROS）**の規約。**AI リポ**は ROS 非依存の独立プロジェクトで、自前の規約（torch 系の lint / test、`package.xml` 無し）を持つ。両リポ共通なのは「**責任の分離**」「Conventional Commits」「契約（§3）の遵守」。

- **責任の分離を実装ごとに確認する**（リポジトリ全体の方針）。純ロジック = `kuas_mechlab3` パッケージ内 + `pytest`、ROS / I/O / subprocess = ノードや `scripts/` + colcon・手動。既存の `teleop_command`(純) vs `teleop_server`(ROS)、`recording`(純) vs `record_episodes.py`(IO) と同じ切り分けを踏襲。
- **Lint ゲート**（lefthook の pre-commit で自動実行）: `black`（line 88）/ `mypy --strict` / `pytest`。コミット前に全部緑にする。`mypy` は `files = src/kuas_mechlab3/{kuas_mechlab3,test}` のみ対象（`scripts/` は対象外だが `black` は効く）。
- **コミット**: Conventional Commits（commitizen の commit-msg フックが検証）。例 `feat(data): ...` / `docs(plan): ...`。
- **言語**: コメント・ドキュメントは日本語可。カタカナ語を好む（端末→ターミナル等）。
- **git push**: この環境は **SSH(22) が不通**。`gh` の HTTPS 認証ヘルパー経由で push/fetch する:
  ```
  git -c credential.helper='!gh auth git-credential' \
    push https://github.com/sarushili0430/kuas-mechlab3.git <branch>
  ```
  PR は develop ベース。`gh pr create --base develop --head <branch>`。
- **新規 ROS 依存**を import したら `package.xml` に `exec_depend` を足し、`pyproject.toml` の mypy override（missing imports）にも追記する。

---

## 7. 落とし穴チェックリスト

- [ ] **同期**: カメラと `/cmd_norm` を同一 Pi クロックで取り、固定 Hz リサンプルで「直近フレーム × その時の行動」を対に。未来フレーム禁止。ブラウザ側でログしない。
- [ ] **分布ズレ / 雪だるま誤差**: 上手い走行だけでなく**リカバリ走行**を混ぜる（Phase 4）。
- [ ] **遅延**: オフボード推論の往復はアクションチャンクで吸収（Phase 7）。
- [ ] **解像度**: 学習用キャプチャ解像度は teleop 配信と分離して上げてよい。
- [ ] **state の定義**: エンコーダ無し → `observation.state = 直前の行動`。両モデルで統一。
- [ ] **ラベル**: `success` のみ学習に使う。`failure/unlabeled` は除外（誤って成功扱いしない）。
- [ ] **安全**: 自律走行は必ず人間オーバーライド付き・低速から。

---

## 8. 用語（1 行定義）

- **VLM**: 画像+テキスト→テキスト。そのままでは行動を出せない。
- **VLA**: Vision-Language-Action。画像(+言語)→**行動**を出すロボット用ポリシー。
- **ACT**: Action Chunking Transformer。行動をチャンクで予測する小型ポリシー（ゼロから学習）。
- **SmolVLA**: ~450M の軽量 VLA（事前学習済み、finetune 前提、LeRobot ネイティブ）。
- **LeRobot**: HuggingFace のロボット模倣学習スタック / データ形式。ACT・SmolVLA 等を同じデータで学習できる。
- **DAgger**: 失敗状態のデモを足して学習し直し、分布ズレを潰す手法（ここでは「リカバリ走行を追加収集」の簡易版）。
- **アクションチャンク**: 先の複数 step の行動をまとめて予測し、オープンループ実行して遅延を隠す。

---

## 9. 参考リンク（SmolVLA / LeRobot）

- SmolVLA モデル（finetune の起点）: https://huggingface.co/lerobot/smolvla_base
- SmolVLA 解説ブログ: https://huggingface.co/blog/smolvla
- SmolVLA ドキュメント: https://huggingface.co/docs/lerobot/smolvla
- LeRobot 本体: https://github.com/huggingface/lerobot
- SmolVLA 使い方サンプル: https://github.com/huggingface/lerobot/blob/main/examples/tutorial/smolvla/using_smolvla_example.py
