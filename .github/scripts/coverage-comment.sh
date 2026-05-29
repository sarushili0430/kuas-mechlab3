#!/usr/bin/env bash
# PR にカバレッジレポートをコメントする自前スクリプト（重複させず upsert する）。
# サードパーティ Action は使わず、GitHub 公式 CLI (gh) と jq だけで完結する。
# どちらも GitHub ホストの ubuntu runner にプリインストール済み。
#
# 必要な環境変数:
#   GITHUB_TOKEN       gh の認証トークン（pull-requests: write 権限が必要）
#   GITHUB_REPOSITORY  "owner/repo"（runner が自動で設定）
#   PR_NUMBER          コメント先の PR 番号
#   COVERAGE_FILE      pytest --cov の term 出力ファイル（省略時 pytest-coverage.txt）
set -euo pipefail

coverage_file="${COVERAGE_FILE:-pytest-coverage.txt}"

if [[ ! -f "${coverage_file}" ]]; then
  echo "coverage file not found: ${coverage_file}" >&2
  exit 1
fi

# 同じコメントを毎回更新するための目印（本文には表示されない HTML コメント）。
marker="<!-- coverage-report -->"

# term-missing 出力の TOTAL 行から全体のカバレッジ率を取り出す（無ければ n/a）。
total="$(grep -E '^TOTAL' "${coverage_file}" | grep -oE '[0-9]+%' | tail -n1 || true)"
total="${total:-n/a}"

# コメント本文を組み立てる。
body="$(cat <<EOF
${marker}
## Coverage report

**Total coverage: ${total}**

\`\`\`
$(cat "${coverage_file}")
\`\`\`
EOF
)"

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
