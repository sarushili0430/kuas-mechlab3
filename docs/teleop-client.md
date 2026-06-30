# teleop クライアント統合ガイド（WS 接続 + カメラ `<img>` 受信）

操縦者側（ブラウザや自前クライアント）から ML3 に繋ぐ方法をまとめる。チャネルは**2 本あり、互いに独立**している:

| 向き | 何が流れるか | プロトコル | 配信元ノード | 既定エンドポイント |
| --- | --- | --- | --- | --- |
| **映像 IN**（受信） | 前後カメラの JPEG | HTTP / MJPEG（`multipart/x-mixed-replace`） | `mjpeg_server` | `http://<pi>:8080/` |
| **操縦 OUT**（送信） | ドライブ指令 `{"vx","wz"}` | WebSocket（JSON テキスト） | `teleop_server` | `ws://<pi>:9001` |

映像は `<img>` に URL を入れるだけで JS 不要、操縦は WebSocket を 1 本張って一定レートで JSON を送るだけ。両者を 1 枚の HTML にまとめれば最小のコックピットになる（[末尾の完全な例](#最小コックピット-html1-ファイル)）。

> 前提: `<pi>` は Raspberry Pi の IP（例 `192.168.1.42`）。サーバ側の起動は [README の「リモート teleop」「前後カメラ」](../README.md) を参照（`teleop_launch.py` と `cameras_launch.py`）。**認証はなく LAN 内利用が前提**。

---

## 1. カメラ映像を `<img>` で受け取る

`mjpeg_server` は各トピックを `multipart/x-mixed-replace` で配信する。これはブラウザの `<img>` がネイティブに解釈する形式なので、**`src` に stream URL を入れるだけ**でライブ映像になる（JS も canvas も不要）。

```html
<img src="http://192.168.1.42:8080/stream?topic=/front_camera/image_raw/compressed"
     alt="front camera">
<img src="http://192.168.1.42:8080/stream?topic=/rear_camera/image_raw/compressed"
     alt="rear camera">
```

### エンドポイント

| パス | 返すもの |
| --- | --- |
| `/` | 配信中の全トピックを並べた確認用 HTML（`mjpeg_server` 生成） |
| `/stream?topic=<topic>` | そのトピックの MJPEG ストリーム |

`<topic>` は `mjpeg_server` の `topics` パラメータに登録されたものだけ（既定は前後の `…/image_raw/compressed`）。**未登録のトピックは 404**。何が配信されているか分からなければ、まず `http://<pi>:8080/` を開いて確認する。

### 知っておくべき挙動・注意

- **JS から URL を差し替えてよい**: `img.src = ".../stream?topic=..."` で表示開始、`img.src = ""`（または要素削除）でそのストリームの接続が閉じる（サーバはソケット切断を検知してスレッドを解放する）。
- **`<img>` 1 個につき HTTP 接続 1 本**を張りっぱなしにする。前後 2 枚なら 2 接続。タブを閉じれば解放される。
- **フレームレート上限**は配信側の `stream_fps`（既定 15）。カメラ自体の `fps` と揃える運用。
- **CORS は不要**: `<img>` での画像表示はクロスオリジンでも許可される。コックピット HTML を Pi 以外（自分の PC や `file://`）から開いても映像は出る。
- **混在コンテンツ（mixed content）に注意**: コックピット HTML を **HTTPS** で配信すると、`http://` の `<img>` と `ws://` の WebSocket がブラウザにブロックされる。Pi 側は TLS ではないので、**コックピットは `http://` で配信するか `file://` で開く**こと。

---

## 2. teleop WebSocket に繋ぐ

`teleop_server` は WebSocket で**正規化済みのドライブ指令**を受け取り、`cmd_vel`（`geometry_msgs/Twist`）として一定レートで publish する。クライアントは WS を 1 本張って JSON テキストを送るだけ。

### 接続とメッセージ形式

```js
const ws = new WebSocket("ws://192.168.1.42:9001");
ws.onopen = () => {
  ws.send(JSON.stringify({ vx: 0.5, wz: -0.3 }));
};
```

- 1 メッセージ = JSON テキスト 1 個: `{"vx": <number>, "wz": <number>}`。
- **`vx` / `wz` は正規化軸値 [-1, 1]**。サーバが `max_linear` / `max_angular` で物理量へスケールする（既定では `vx=1.0` → 0.5 m/s、`wz=1.0` → 2.0 rad/s）。
- **符号**: `vx>0` 前進、`vx<0` 後退。`wz>0` 左旋回（反時計回り, REP-103）、`wz<0` 右旋回。
- 範囲外・`NaN`/`Infinity`・キー欠落・壊れた JSON は**サーバが黙って無視**する（直前の有効指令が維持され、やがて下記タイムアウトで 0 になる）。
- 余分なキー（`{"vx":..,"wz":..,"seq":5}` 等）は無視されるので、独自フィールドを足しても安全。

### 送り方（重要）: 「現在の目標速度」を一定レートで送り続ける

teleop は単発の命令ではなく**連続ストリーム**。`teleop_server` は受け取った最新値を `publish_rate`（既定 20Hz）で publish し続ける。クライアントも **20Hz 程度で “今の目標速度” を送り続ける**のが基本（押している間ずっと、離したら 0 を送る、を毎周期）。

```js
const RATE_HZ = 20;
setInterval(() => {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(currentAxes()));  // 例: {vx, wz}
  }
}, 1000 / RATE_HZ);
```

### 安全（3 段のフェイルセーフ）

止め忘れ・通信断でも暴走しないよう、**独立した 3 層**で必ず止まる。クライアント実装はこれらに「乗る」だけでよい:

1. **WS 切断 → 次サイクルで即 0**（最速）。タブを閉じる・ネットワーク断・`ws.close()` で停止。
2. **無入力 → `hold_timeout`（既定 0.4s）で 0 に減衰**。送信が途絶えるとサーバが目標を 0 に落とす。
3. **`mbed_driver` の `cmd_timeout`（既定 0.4s）ウォッチドッグ**（最終網）。

加えて WS 組み込みの **ping/pong**（サーバの `ping_interval`/`ping_timeout` = 各 5s）が、無応答になったクライアントを切断して 1. を発火させる。ブラウザの `WebSocket` は ping に自動応答するので、クライアント側で特別な実装は要らない。

> ⚠️ それでも安全のため、**離脱時に明示的に停止を送る**（`{"vx":0,"wz":0}`）+ **ウィンドウ非アクティブ（`blur`）でキー状態をクリア**しておくと、より速く・確実に止まる。

### 再接続

`onclose` で一定間隔の再接続を入れておくと、Wi-Fi の瞬断後も自動復帰する。再接続までの間はサーバ側が（切断検知で）停止しているので安全。

```js
function connect() {
  const ws = new WebSocket("ws://192.168.1.42:9001");
  ws.onclose = () => setTimeout(connect, 1000);  // 1s 後に再接続
  // …onopen / 送信ループの (再)セットアップ…
}
```

### 複数クライアント

初版は **last-writer-wins**（最後に届いた指令が有効）で、接続が 0 になると停止する。**同時に操縦するのは 1 台**にする運用が安全（2 つのクライアントが別々の指令を送ると取り合いになる）。

### 録画（データ取得）を同じ WS で開始・停止する

操縦と**同じ WebSocket**に、ドライブ指令とは別の **record-control メッセージ**を 1 発送るだけで、データ取得（rosbag 録画）を**操縦画面のまま**開始・終了できる（Pi 側のターミナルに触れない）。`teleop_server` がこれを正規化して `/record_cmd`（`std_msgs/String`）に中継し、`episode_recorder` ノードが **1 エピソード = 1 bag + `meta.json`** で記録する。

```js
ws.send(JSON.stringify({ record: "start", route: "route_a", operator: "koyu" }));  // 録画開始
ws.send(JSON.stringify({ record: "stop",  label: "success" }));                    // 保存（成功ラベル）
ws.send(JSON.stringify({ record: "stop",  label: "failure", notes: "外れた" }));   // 保存（失敗 + メモ）
ws.send(JSON.stringify({ record: "discard" }));                                    // 今の走行を破棄
```

| キー | 対象 | 値 | 既定 / 備考 |
| --- | --- | --- | --- |
| `record` | 全部 | `"start"` / `"stop"` / `"discard"`（大小文字無視） | 必須。これ以外は無視される |
| `route` | start | 文字列 | 任意。エピソードのルート名（省略時はノードの既定 `route_a`） |
| `operator` | start | 文字列 | 任意。操縦者名（省略時はノードの既定） |
| `label` | stop | `"success"` / `"failure"` 等 | 任意。`normalize_label` で正規化。**省略すると `unlabeled`**（黙って成功にはしない） |
| `notes` | stop | 文字列 | 任意。`meta.json` に残す自由メモ |

- **ドライブ指令とは別物**: `{"vx","wz"}` には `record` キーが無く、record メッセージには `vx`/`wz` が無いので、1 本の WS で**混ざらない**。`teleop_server` はまずドライブとして解釈し、違えば record として解釈する（どちらでもなければ従来どおり黙って無視）。
- **安全網と無関係**: record の中継は cmd_vel（Twist）と 3 層フェイルセーフに一切触れない。録画の有無に関わらず操縦の停止挙動は同じ。
- **1 本ずつ**: record は連続ストリームではなく**単発イベント**（押した時だけ送る）。ドライブの 20Hz ハートビートに混ぜない。
- **前提**: 録画には `episode_recorder` が起動済みであること（`ros2 launch kuas_mechlab3 record_launch.py`、または `start-all.sh` に同梱）。未起動なら record メッセージは中継されるが誰も受けず、何も記録されない。
- **既に録画中の `start`／非録画中の `stop`・`discard`** は recorder 側で警告ログのみ・無視（多重 bag を作らない）。WS やタブを録画中に閉じても bag は止まらない（操縦者の明示 `stop`、または recorder シャットダウン時に `unlabeled` で finalize される）。

> 同梱の [`cockpit.html`](./cockpit.html) には ［● 録画開始］［■ 成功で保存］［■ 失敗で保存］［✗ 破棄］のボタンと録画タイマーが付いており、上記メッセージをこの WS で送る。route / operator はテキスト欄で指定する。

---

## 3. ブラウザを使わない動作確認

サーバだけ立てて疎通を見るなら、依存の軽いツールで十分。

```bash
# 送信: 1 フレームだけ送る（websocat が必要）
echo '{"vx":0.5,"wz":0.0}' | websocat ws://<pi>:9001

# 受信側で cmd_vel が出ているか確認（ROS2 環境）
ros2 topic echo /cmd_vel

# 録画の遠隔制御も同じ WS。開始/停止を 1 発ずつ送り、中継トピックを確認する
echo '{"record":"start","route":"route_a"}' | websocat ws://<pi>:9001
echo '{"record":"stop","label":"success"}'  | websocat ws://<pi>:9001
ros2 topic echo /record_cmd                  # teleop_server -> episode_recorder の中継を確認

# 同梱の WASD クライアント（rclpy 非依存。操縦者 PC で直接 python でも可）
ros2 run kuas_mechlab3 teleop_ws_client --url ws://<pi>:9001

# 映像が来ているかを HTTP で確認
curl -s http://<pi>:8080/ | grep stream      # index のストリーム URL 一覧
curl -s http://<pi>:8080/stream?topic=/front_camera/image_raw/compressed --output - | head -c 64 | xxd
```

---

## 最小コックピット HTML（1 ファイル）

前後 2 カメラの `<img>` と、WASD を 20Hz で送る WebSocket を 1 枚にまとめた最小例。`PI` を Pi の IP に変えて、`http://` 配信か `file://` で開く（HTTPS は混在コンテンツでブロックされる）。フォーカスをこのページに当ててから WASD で操縦する。

> 💾 **そのまま開ける実ファイルを [`cockpit.html`](./cockpit.html) に同梱**（リポジトリ同梱の正本）。下のリストは**操縦コア部分**の説明用コピー。正本の `cockpit.html` には加えて**録画ボタン**（［● 録画開始］/［■ 成功で保存］/［■ 失敗で保存］/［✗ 破棄］と route/operator 欄、上の「録画を同じ WS で開始・停止する」を実装）が付く。実際に使うときは `cockpit.html` を開く。

```html
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>ML3 cockpit</title>
  <style>
    body { background:#111; color:#eee; font-family:sans-serif; text-align:center }
    figure { display:inline-block; margin:8px }
    img { width:48vw; max-width:640px; border:1px solid #444; background:#000 }
    #status { padding:6px; font-weight:bold }
  </style>
</head>
<body>
  <h1>ML3 cockpit</h1>
  <div id="status">WS: connecting…</div>
  <div>
    <figure><figcaption>front</figcaption><img id="front" alt="front"></figure>
    <figure><figcaption>rear</figcaption><img id="rear" alt="rear"></figure>
  </div>
  <p>このページにフォーカスして <b>W/A/S/D</b> で操縦（離すと停止）</p>

  <script>
    // --- 設定: Pi の IP に合わせる（同じ Pi で配信していなければ手で書き換え）---
    const PI = location.hostname || "192.168.1.42";
    const CAM_PORT = 8080, WS_PORT = 9001;
    const FRONT = "/front_camera/image_raw/compressed";
    const REAR  = "/rear_camera/image_raw/compressed";
    const LINEAR = 1.0, ANGULAR = 1.0, RATE_HZ = 20;  // 正規化軸の最大と送信レート

    // --- 1) カメラ: <img> に stream URL を入れるだけ ---
    front.src = `http://${PI}:${CAM_PORT}/stream?topic=${FRONT}`;
    rear.src  = `http://${PI}:${CAM_PORT}/stream?topic=${REAR}`;

    // --- 2) 入力: 押下中のキー集合から目標軸を計算 ---
    const keys = new Set();
    addEventListener("keydown", e => keys.add(e.key.toLowerCase()));
    addEventListener("keyup",   e => keys.delete(e.key.toLowerCase()));
    addEventListener("blur", () => keys.clear());   // 非アクティブで停止
    function currentAxes() {
      let vx = 0, wz = 0;
      if (keys.has("w")) vx += LINEAR;
      if (keys.has("s")) vx -= LINEAR;
      if (keys.has("a")) wz += ANGULAR;             // +wz = 左旋回 (REP-103)
      if (keys.has("d")) wz -= ANGULAR;
      return { vx, wz };
    }

    // --- 3) WebSocket: 接続 + 自動再接続 ---
    let ws = null;
    const setStatus = t => status.textContent = t;
    function connect() {
      ws = new WebSocket(`ws://${PI}:${WS_PORT}`);
      ws.onopen  = () => setStatus("WS: connected");
      ws.onclose = () => { setStatus("WS: closed — retrying…"); setTimeout(connect, 1000); };
      ws.onerror = () => ws.close();
    }
    connect();

    // --- 4) 一定レートで「今の目標速度」を送り続ける（ハートビート）---
    setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(currentAxes()));
      }
    }, 1000 / RATE_HZ);

    // --- 5) 離脱時に明示停止（サーバ側も切断で止まる）---
    addEventListener("beforeunload", () => {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ vx: 0, wz: 0 }));
    });
  </script>
</body>
</html>
```

> ゲームパッドにするなら `currentAxes()` を [Gamepad API](https://developer.mozilla.org/docs/Web/API/Gamepad_API) で `navigator.getGamepads()[0].axes` から作るだけ（送信ループはそのまま）。スティック値はすでに [-1, 1] なので `vx`/`wz` にそのまま使える（必要なら `deadzone` はサーバ側でも効く）。

---

## トラブルシュート

| 症状 | 切り分け |
| --- | --- |
| 映像が出ない | `http://<pi>:8080/` を直接開く → 出なければカメラ側（device / `ros2 topic hz`）。出るなら HTML の `PI`/topic/混在コンテンツ（HTTPS）を疑う |
| 映像は出るが動かない | `ros2 topic echo /cmd_vel` で Twist が出ているか。出ていなければ WS 未接続（`#status`）か `PI`/ポート 9001。出ているのに動かないなら driver 側（[README のラズパイ bring-up](../README.md)） |
| すぐ止まる / カクつく | 送信レートが低い（< ~3Hz だと `hold_timeout` 0.4s に間に合わない）。20Hz で送り続けているか確認 |
| 旋回が逆 | クライアントではなく driver の `turn_sign`（[README 参照](../README.md)）で調整 |
| HTTPS ページでブロック | コックピットを `http://` か `file://` で開く（Pi は TLS 非対応） |

> ブラウザから ROS の全トピック（テレメトリ等）を直接触りたくなったら、`teleop_server` の代わりに標準の `rosbridge_suite` + roslibjs に寄せる選択肢もある（README の「代替」注記）。
