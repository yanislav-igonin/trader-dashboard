#!/bin/sh
# Rebuild the site into docs/ (only needed when app/trader.declare changes).
# Needs the Declare toolchain cloned at $DECLARE (default ~/Documents/Private/declarelang).
set -e
cd "$(dirname "$0")"
DECLARE="${DECLARE:-$HOME/Documents/Private/declarelang}"
python3 export.py --check
python3 export.py
(cd "$DECLARE" && npx declarec "$OLDPWD/app/trader.declare" -o "$OLDPWD/docs")
echo trader.h0b0.dev > docs/CNAME
