#!/usr/bin/env python3
"""人間のテレオプ・デモ走行を 1 エピソードずつ rosbag に記録する（模倣学習データ収集）。

固定ルートの各走行 = 1 bag + meta.json（ルート / 操縦者 / 成功・失敗ラベル）。
ルートを走り、Enter で保存、`d` で失敗走行を破棄、これを繰り返す。記録トピックは
`/cmd_norm`（= 行動ラベル。teleop_server が出す正規化指令）+ 前後カメラ + cmd_vel /
車輪テレメトリ。AI は将来この `/cmd_norm` と同じ値を WebSocket に出すので、これが
そのまま学習ターゲットになる。

責任分離: このスクリプトは対話 I/O だけ（プロンプトとキー入力）。bag のライフサイクル
（subprocess=ros2 bag record・エピソード採番・meta.json 書き出し）は IO の
``kuas_mechlab3.record_session.RecordingSession`` が単一所有し、スマホから叩く
``record_server`` ノードと同じ実装を共有する。データセット配置とメタデータのスキーマは
純・pytest 対象の ``kuas_mechlab3.recording`` が単一所有する。

実行は ``scripts/start-record.sh``（ROS 環境を source する）経由を推奨。あるいは
install/setup.bash を既に source 済みのシェルから直接:

    python3 scripts/record_episodes.py --route route_a --operator koyu
"""

import argparse
import os
import sys
from pathlib import Path

from kuas_mechlab3.record_session import RecordingSession
from kuas_mechlab3.recording import default_topics, format_duration, normalize_label


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the recorder CLI (route / operator / output dir / topic toggles)."""
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--route", required=True, help="ルートのラベル（例: route_a）")
    p.add_argument(
        "--operator", default=os.environ.get("USER", "unknown"), help="操縦者名"
    )
    p.add_argument(
        "--out", default="datasets/raw", help="データセットのルートディレクトリ"
    )
    p.add_argument("--no-rear", action="store_true", help="後カメラを記録しない")
    p.add_argument(
        "--no-state", action="store_true", help="cmd_vel / 車輪テレメトリを記録しない"
    )
    p.add_argument("--start-index", type=int, default=1, help="エピソード番号の開始値")
    p.add_argument(
        "--storage",
        default="sqlite3",
        choices=("sqlite3", "mcap"),
        help="rosbag2 ストレージ",
    )
    return p.parse_args(argv)


def _prompt(message: str) -> str:
    """Read one line; treat EOF (piped/closed stdin) as a quit request."""
    try:
        return input(message)
    except EOFError:
        return "q"


def main(argv: list[str] | None = None) -> int:
    """Drive the interactive record / label / discard loop until the operator quits."""
    args = parse_args(argv)
    topics = default_topics(
        include_rear=not args.no_rear, include_state=not args.no_state
    )
    out_root = Path(args.out).expanduser()
    out_root.mkdir(parents=True, exist_ok=True)
    domain = os.environ.get("ROS_DOMAIN_ID")
    domain_id = int(domain) if domain and domain.isdigit() else None

    session = RecordingSession(
        out_root=out_root,
        route=args.route,
        operator=args.operator,
        topics=topics,
        storage=args.storage,
        start_index=args.start_index,
        ros_domain_id=domain_id,
    )

    print(f"録画ルート: {args.route}   操縦者: {args.operator}")
    print(f"保存先: {out_root.resolve()}")
    print(f"記録トピック: {', '.join(topics)}")
    print(
        "先に driver / cameras / teleop を起動しておくこと（別ターミナル or start-all.sh）。"
    )

    saved = 0
    try:
        while True:
            index = session.index
            if (
                _prompt(f"\nエピソード {index:03d}: [Enter]=録画開始 / q=終了 > ")
                .strip()
                .lower()
                == "q"
            ):
                break

            info = session.start()
            print(f"● 録画中 -> {info['episode']}    [Enter]=保存して停止 / d=破棄")

            action = _prompt("").strip().lower()
            if action == "d":
                dropped = session.discard()
                print(f"✗ 破棄しました（{dropped['episode']}）")
                continue

            # 走行終了の瞬間に bag を閉じる（ラベル入力の間に無駄な尾を録らない）。
            session.stop_bag()
            label = normalize_label(_prompt("  ラベル [Enter]=成功 / f=失敗 > "))
            notes = _prompt("  メモ（任意, Enter でスキップ）> ").strip()
            res = session.finalize(label=label, notes=notes)
            saved += 1
            dur = format_duration(res["duration_s"])
            print(f"✓ 保存: {res['saved']}  label={res['label']}  ({dur})")
    except KeyboardInterrupt:
        # Ctrl-C: don't lose an in-flight run -- finalise the bag and save it as
        # unlabeled so a long demo isn't thrown away (operator can relabel later).
        print("\n中断を検知。録画中なら finalize します...")
        res = session.finalize_unlabeled(notes="interrupted (Ctrl-C)")
        if res is not None:
            saved += 1
            print(f"✓ 中断保存: {res['saved']}  label={res['label']}")

    print(f"\n完了: {saved} エピソード保存（{out_root.resolve()}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
