# AI Trader: $50 experiment

Live: https://trader.h0b0.dev

An AI agent trades BTC and ETH perpetuals with $50 on its own and logs every check.
This is the public dashboard for it, written in [Declare](https://github.com/davidtemkin/declarelang).

- `app/trader.declare`: the dashboard source.
- `export.py`: turns the bot's `state.json` + `journal.md` into `data.json`.
- `build.sh`: compiles the site into `docs/` with `declarec` (GitHub Pages serves `docs/`).
- `publish.sh`: refreshes `docs/data.json` and pushes it; the bot runs it after each check.
