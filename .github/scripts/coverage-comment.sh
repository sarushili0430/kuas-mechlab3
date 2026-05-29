#!/usr/bin/env bash
# PR にカバレッジレポートをコメントする自前スクリプト（重複させず upsert する）。
# サードパーティ Action は使わず、GitHub 公式 CLI (gh) だけで投稿する。
# コメント本文の整形は coverage_md.py に分離している（整形と投稿の責任分離）。
#
# 必要な環境変数:
#   GITHUB_TOKEN       gh の認証トークン（pull-requests: write 権限が必要）
#   GITHUB_REPOSITORY  "owner/repo"（runner が自動で設定）
#   PR_NUMBER          コメント先の PR 番号
#   COVERAGE_JSON      coverage.py の JSON レポート（省略時 coverage.json）
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
coverage_json="${COVERAGE_JSON:-coverage.json}"

if [[ ! -f "${coverage_json}" ]]; then
  echo "coverage json not found: ${coverage_json}" >&2
  exit 1
fi

# coverage_md.py が本文先頭に出力する目印と一致させること（変更時は両方直す）。
marker="<!-- coverage-report -->"

# 本文の整形（JSON → Markdown）は Python 側に任せる。
body="$(python "${script_dir}/coverage_md.py" "${coverage_json}")"

# marker を含む既存コメント（前回このスクリプトが作ったもの）の ID を探す。
# --paginate と head を分けているのは、パイプ先を途中で閉じて gh が SIGPIPE で
# 落ちる（pipefail で失敗扱いになる）のを避けるため。
existing_ids="$(
  gh api --paginate "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
    --jq ".[] | select(.body | contains(\"${marker}\")) | .id"
)"
existing_id="$(printf '%s\n' "${existing_ids}" | head -n1)"

if [[ -n "${existing_id}" ]]; then
  # 既存コメントがあれば更新する（PATCH）。
  gh api --method PATCH \
    "repos/${GITHUB_REPOSITORY}/issues/comments/${existing_id}" \
    -f body="${body}" >/dev/null
  echo "Updated existing coverage comment (id=${existing_id})."
else
  # 無ければ新規作成する（POST）。
  gh api --method POST \
    "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
    -f body="${body}" >/dev/null
  echo "Created new coverage comment."
fi
