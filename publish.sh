#!/bin/sh
# Refresh docs/data.json from the bot and push it, only when it changed. Run after every bot check.
set -e
cd "$(dirname "$0")"
python3 export.py docs/data.json >/dev/null
cp docs/data.json app/data.json
python3 export_bots.py docs/bots.json >/dev/null  # Бот-трейдинг tab (auto-trader Freqtrade DBs)
cp docs/bots.json app/bots.json
git add docs/data.json app/data.json docs/bots.json app/bots.json history.json
if git diff --cached --quiet; then echo "publish: no change"; exit 0; fi
git commit -qm "data: $(date -u +%Y-%m-%dT%H:%MZ)"
git pull -q --rebase --autostash origin main  # remote may have Pages commits; local WIP from editing sessions is set aside and restored
git push -q origin main
echo "publish: pushed"
