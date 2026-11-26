#!/usr/bin/env python3
"""Export the Freqtrade bots' sqlite DBs (auto-trader) into docs/bots.json for the "Бот-трейдинг" tab.
Read-only on the DBs. Totals are over all trades; the JSON keeps only the latest RECENT closed trades and CURVE points.
Run: python3 export_bots.py [out]   (default docs/bots.json)
     python3 export_bots.py --check (self-check, writes nothing)"""
import json, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path

AT = Path.home() / "Documents/Private/auto-trader"
# one entry per bot; add more exchanges/bots here
BOTS = [
    {"name": "bybit-ema", "exchange": "Bybit USDT perp", "mode": "demo", "strategy": "EmaRsiScalp: EMA 9/21 cross + RSI, 1m, market orders", "start": 25.0, "db": AT / "user_data/tradesv3-ema-demo.sqlite"},
    {"name": "bybit-bb", "exchange": "Bybit USDT perp", "mode": "demo", "strategy": "BbRsiMaker: Bollinger + RSI mean reversion, 1m, post-only limits", "start": 25.0, "db": AT / "user_data/tradesv3-bb-demo.sqlite"},
]
OUT = Path(__file__).with_name("docs") / "bots.json"
RECENT, CURVE = 200, 400  # shortcut: caps instead of paging, move to a backend when trades > 1000 (ticket #222)


def iso(s):
    return (s or "")[:16].replace(" ", "T") + "Z" if s else ""


def summarize(bot, rows):
    """rows: dicts from the trades table, closed and open."""
    closed = sorted((r for r in rows if not r["is_open"]), key=lambda r: r["close_date"])
    pnl = sum(r["close_profit_abs"] or 0 for r in closed)
    wins = sum((r["close_profit_abs"] or 0) > 0 for r in closed)
    bal, curve = bot["start"], []
    for r in closed:
        bal += r["close_profit_abs"] or 0
        curve.append({"t": iso(r["close_date"]), "v": round(bal, 4)})
    step = max(1, len(curve) // CURVE)
    curve = curve[::step] + ([curve[-1]] if curve and (len(curve) - 1) % step else [])
    side = lambda r: "short" if r["is_short"] else "long"
    return {"name": bot["name"], "exchange": bot["exchange"], "mode": bot["mode"],
            "strategy": bot["strategy"], "start": bot["start"],
            "balance": round(bot["start"] + pnl, 2), "pnl": round(pnl, 4), "trades": len(closed), "wins": wins,
            "winRate": round(100 * wins / len(closed), 1) if closed else 0,
            "open": [{"pair": r["pair"], "side": side(r), "entry": r["open_rate"], "stake": round(r["stake_amount"], 2),
                      "at": iso(r["open_date"])} for r in rows if r["is_open"]],
            "curve": [{"t": iso(closed[0]["open_date"]), "v": bot["start"]}] + curve if curve else [],
            "recent": [{"pair": r["pair"], "side": side(r), "entry": r["open_rate"], "exit": r["close_rate"],
                        "pnl": round(r["close_profit_abs"] or 0, 4), "at": iso(r["close_date"]), "why": r["exit_reason"] or ""}
                       for r in reversed(closed[-RECENT:])]}


def read(db):
    if not db.exists():
        return []
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute("select * from trades")]
    finally:
        con.close()


def check():
    t = lambda i, p, o=0: {"pair": "SOL/USDT:USDT", "is_short": i % 2, "is_open": o, "open_rate": 1, "close_rate": 2,
                          "close_profit_abs": p, "stake_amount": 8, "open_date": f"2026-11-26 10:0{i}:00",
                          "close_date": None if o else f"2026-11-26 11:0{i}:00", "exit_reason": "roi", "strategy": "S"}
    s = summarize(BOTS[0], [t(1, 1.0), t(2, -0.5), t(3, 0, 1)])
    assert (s["trades"], s["wins"], s["winRate"], s["balance"], len(s["open"])) == (2, 1, 50.0, 25.5, 1), s
    assert s["curve"][-1]["v"] == 25.5 and s["recent"][0]["pnl"] == -0.5 and s["recent"][0]["side"] == "long", s
    assert summarize(BOTS[0], [])["trades"] == 0
    print("check ok")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
        sys.exit()
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    data = {"bots": [summarize(b, read(b["db"])) for b in BOTS]}
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(out, sum(b["trades"] for b in data["bots"]), "trades")
