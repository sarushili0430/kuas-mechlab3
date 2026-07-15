# 競技当日ランブック / Competition-day runbook

競技会場での **電源投入 → 動作確認 → トラブル対応** の手順。今季の実機ブリングアップで
実際に使ったコマンドをそのまま並べてある。

> **認証情報(SSH パスワード・競技 WiFi のパスワード等)はこの公開リポジトリには書かない。**
> `<ROBOT_IP>` `<user>` はチームの私的メモの値に読み替えること。
>
> 前提: `scripts/install-services.sh` 済みで、`kuas-mechlab3.service`(ロボット一式)と
> `ml3-cockpit.service`(操縦 UI 配信)が enable されている。電源を入れるだけでスタックは
> 自動起動する。`ROS_DOMAIN_ID` はチーム番号に合わせる(既定 11)。

## 0. ネットワーク
- ロボットと操縦 PC を同じネットワーク(競技 WiFi。SSID/パスワードは運営/チームの私的メモ)に接続。
- 操縦 PC から `ping <ROBOT_IP>` が通ること。

## 1. 電源投入 → 自動起動の確認
```bash
ssh <user>@<ROBOT_IP>
source /opt/ros/humble/setup.bash && export ROS_DOMAIN_ID=11

# サービスが両方 active か
systemctl is-active kuas-mechlab3 ml3-cockpit          # → active / active

# ノードが 8 つ・重複なしか(重複 = 二重起動のサイン)
ros2 node list | sort
#   front_camera, rear_camera, mbed_driver, mjpeg_server,
#   record_server, teleop_server, traffic_light_node, led_indicator
ros2 node list | sort | uniq -d                        # 何も出なければ OK
```

## 2. カメラ確認
```bash
ros2 topic hz /front_camera/image_raw/compressed       # ~20Hz 出れば OK
ros2 topic hz /rear_camera/image_raw/compressed        # ~20Hz

# 前後が入れ替わって見える(前カメラに操縦者が映る等)なら by-path を確認
./scripts/detect-cameras.sh
#   → front=USB ポート 1.4 / rear=ポート 1.3。
#     unit の FRONT_DEVICE/REAR_DEVICE を直して再起動(/dev/videoN は毎起動で入れ替わる)
```

## 3. 操縦 UI(コックピット)
- 操縦 PC のブラウザで `http://<ROBOT_IP>:8000/` を開く。
- 前後カメラ映像 + WASD 走行 + 矢印キー アーム(↑↓ = 肘, ←→ = 肩)+ LED on/off。
- 接続ピルが緑(WS 接続 OK)になること。ならなければ Host 欄に `<ROBOT_IP>` を入れて「適用」。

## 4. 信号機タスク(#9)の確認
```bash
# 緑の信号機を前カメラに見せる
ros2 topic echo /traffic_light_topic
#   緑 → 11Green(バリアが開く文字列) / 赤 → 11Red / 黄 → 11Yellow
#   何も無し → 無出力(フェイルセーフ:検出したときだけ publish)
```
- 検出中は機体の LED が点灯する(`led_indicator`。**緑のときだけ ON**、赤/黄・光を外すと OFF)。

## 5. トラブル対応
| 症状 | 対処 |
|------|------|
| カメラ 0Hz / 前後入れ替わり | `detect-cameras.sh` で by-path 確認 → 下記クリーン再起動 |
| ノード重複 / rear が出ない | 二重起動。競合ユニット(旧 `ml3-ros` 等)を `sudo systemctl disable --now <unit>` → 再起動 |
| UI がつながらない | `:8000`(UI)と `:9001`(WS)が開いているか、Host 欄が `<ROBOT_IP>` か |
| 信号機が無反応 | 前カメラが本当に前を映しているか(`detect-cameras.sh`)、信号機がフレームを十分占めているか |

### クリーン再起動
```bash
sudo systemctl stop kuas-mechlab3
# 取りこぼしプロセスを掃除(不完全な停止で重複が残るのを防ぐ)
pkill -f 'start-all.sh|ros2 launch|lib/kuas_mechlab3/|mjpeg_server|camera_node' || true
sudo systemctl start kuas-mechlab3
sleep 30    # 立ち上がり待ち → 手順 1〜2 を再確認
```

## 6. 終了
```bash
sudo systemctl stop kuas-mechlab3 ml3-cockpit
sudo shutdown -h now
```
