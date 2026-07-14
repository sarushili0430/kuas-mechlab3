# 録画コントロール API（スマホから AI データ取得の開始/終了）

操縦者側（cockpit の REC ボタンや curl）から、**AI 学習用データ取得（エピソード録画）の開始/終了をスマホから**行うための HTTP API。対話 CLI [`scripts/record_episodes.py`](../scripts/record_episodes.py) の遠隔版で、同じ `ros2 bag record` ライフサイクルを叩く。

チャネルは操縦・映像とは**独立した 3 本目**で、`teleop_server` は無変更のまま（録画は別の関心事）:

| 向き | 何が流れるか | プロトコル | 配信元ノード | 既定エンドポイント |
| --- | --- | --- | --- | --- |
| **映像 IN** | 前後カメラの JPEG | HTTP / MJPEG | `mjpeg_server` | `http://<pi>:8080/` |
| **操縦 OUT** | ドライブ指令 `{"vx","wz"}` | WebSocket | `teleop_server` | `ws://<pi>:9001` |
| **録画 CTRL** | 録画の開始/終了/破棄 | **HTTP / JSON** | **`record_server`** | **`http://<pi>:9002`** |

> 前提: 先に driver / cameras / teleop を起動しておくこと（`/cmd_norm` と前後カメラのトピックが無いと中身の無い bag になる）。**認証はなく LAN 内利用が前提**（映像・操縦チャネルと同じ）。CORS は全許可なので `file://` や別オリジンの cockpit からも叩ける。

## 起動

```bash
./scripts/start-record-server.sh route:=route_a operator:=koyu
# もしくは start-all.sh が 4 本目として一緒に起動する（ROUTE / OPERATOR で指定）
```

## エンドポイント

| メソッド + パス | 役割 | リクエストボディ（任意） |
| --- | --- | --- |
| `GET /record/status` | 現在の録画状態 | — |
| `POST /record/start` | 録画開始（新エピソード） | `{"route","operator","rear","state"}`（各省略可・省略時はサーバ既定） |
| `POST /record/stop` | 保存して停止（ラベル付与） | `{"label":"success"|"failure","notes"}`（省略時 `success`） |
| `POST /record/discard` | 破棄して停止（番号は再利用） | — |

- **開始**は 1 走行 = 1 エピソード（`datasets/raw/<日時>_<route>_NNN/` に `bag/` + `meta.json`）。
- **終了**は 2 通り: `stop`（成功/失敗ラベルを付けて保存）か `discard`（失敗走行を丸ごと破棄）。
- ラベルは `recording.normalize_label` で正規化され、打ち間違いは黙って `success` にならず `unlabeled` になる（学習データを汚さない）。
- 二重開始（録画中の `start`）は **409** `{"error":"already_recording"}`、非録画中の `stop`/`discard` は **409** `{"error":"not_recording"}`。

### レスポンス例

```jsonc
// GET /record/status（録画中）
{ "recording": true, "index": 3, "episode": "20260703-120000_route-a_003",
  "started_at": "2026-07-03T12:00:00", "route": "route_a", "operator": "koyu" }

// POST /record/stop -d '{"label":"success"}'
{ "recording": false, "saved": "20260703-120000_route-a_003", "index": 3,
  "label": "success", "notes": "", "duration_s": 42.0 }
```

## ブラウザを使わない動作確認

```bash
curl -s      http://<pi>:9002/record/status
curl -s -X POST http://<pi>:9002/record/start  -d '{"route":"loop_1"}'
curl -s -X POST http://<pi>:9002/record/stop   -d '{"label":"success"}'
curl -s -X POST http://<pi>:9002/record/discard
```

## 責任分離（実装の地図）

| 層 | 実体 | 役割 |
| --- | --- | --- |
| ワイヤ契約（純・pytest） | `kuas_mechlab3.record_control` | リクエスト解析・レスポンス整形 |
| bag ライフサイクル（IO・DI で pytest） | `kuas_mechlab3.record_session` | `ros2 bag record` の開始/停止/破棄・採番・meta 書き出し |
| データセット配置/スキーマ（純・pytest） | `kuas_mechlab3.recording` | ディレクトリ名・`meta.json` スキーマ・ラベル |
| HTTP サーバ（ROS ノード） | `kuas_mechlab3.record_server` | HTTP 待ち受け + セッション駆動 |

CLI [`record_episodes.py`] と `record_server` は**同じ `RecordingSession` を共有**するので、ターミナルから録るのもスマホから録るのも同じ挙動になる。
