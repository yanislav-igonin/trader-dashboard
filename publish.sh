#!/bin/sh
# Refresh docs/data.json from the bot and push it, only when it changed. Run after every bot check.
set -e
cd "$(dirname "$0")"
python3 export.py docs/data.json >/dev/null
cp docs/data.json app/data.json
git add docs/data.json app/data.json
if git diff --cached --quiet; then echo "publish: no change"; exit 0; fi
git commit -qm "data: $(date -u +%Y-%m-%dT%H:%MZ)"
git pull -q --rebase origin main  # Pages API edits (CNAME) land as commits upstream
git push -q origin main
echo "publish: pushed"
