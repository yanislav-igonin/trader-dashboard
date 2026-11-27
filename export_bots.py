#!/usr/bin/env python3
"""Export the Freqtrade bots' sqlite DBs (auto-trader) into docs/bots.json for the "Бот-трейдинг" tab.
Read-only on the DBs. Totals are over all trades; the JSON keeps only the latest RECENT closed trades and CURVE points.
Behaviour changes (auto-trader docs/changes.json) go into each bot's feed among its trades, like the agent tab.
Run: python3 export_bots.py [out]   (default docs/bots.json)
     python3 export_bots.py --check (self-check, writes nothing)"""
import json, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path

AT = Path.home() / "Documents/Private/auto-trader"
# one entry per bot; add more exchanges/bots here
BOTS = [
    {"name": "bybit-ema", "exchange": "Bybit USDT perp", "mode": "demo", "strategy": "EmaRsiScalp v2: EMA 9/21 cross with the 1h trend (EMA50/200, ADX>20), ATR take profit 2x / stop 1x, maker limits", "start": 25.0, "db": AT / "user_data/tradesv3-ema-demo.sqlite"},
    {"name": "bybit-bb", "exchange": "Bybit USDT perp", "mode": "demo", "strategy": "BbRsiMaker v2: 1h Bollinger + RSI mean reversion in a range (ADX<20) with the EMA200 trend, exit at the mid, ATR stop", "start": 25.0, "db": AT / "user_data/tradesv3-bb-demo.sqlite"},
]
CHANGES = AT / "docs/changes.json"  # [{bot, version, at, title, what, why, oos}], one per behaviour change
OUT = Path(__file__).with_name("docs") / "bots.json"
RECENT, CURVE = 200, 400  # shortcut: caps instead of paging, move to a backend when trades > 1000 (ticket #222)


def iso(s):
    return (s or "")[:16].replace(" ", "T") + "Z" if s else ""


def version(changes, opened):
    """The behaviour version a trade was opened under: the last change at or before its open time."""
    return max((c["version"] for c in changes if c["at"] <= opened), default=0)


def feed(closed, changes):
    """Latest trades and every behaviour change as one timeline, newest first. A change row sits below the trades
    opened under it, so a trade opened under v1 that closed after v2 shipped still sits below the v2 row."""
    trs = [{"type": "trade", "version": version(changes, iso(r["open_date"])), "coin": r["pair"].split("/")[0],
            "side": "short" if r["is_short"] else "long", "entry": r["open_rate"], "exit": r["close_rate"],
            "pnl": round(r["close_profit_abs"] or 0, 4), "at": iso(r["close_date"]), "why": r["exit_reason"] or ""}
           for r in closed[-RECENT:]]
    chs = []
    for c in changes:
        mine = [t for t in closed if version(changes, iso(t["open_date"])) == c["version"]]
        pnl = sum(t["close_profit_abs"] or 0 for t in mine)
        what = c["what"] + (" Почему: " + c["why"] if c.get("why") else "") + (" Бэктест: " + c["oos"] if c.get("oos") else "")
        chs.append({"type": "change", "version": c["version"], "at": c["at"], "title": c["title"], "what": what,
                    "trades": len(mine), "wins": sum((t["close_profit_abs"] or 0) > 0 for t in mine), "pnl": round(pnl, 4)})
    return sorted(trs + chs, key=lambda x: (x["version"], x["type"] == "trade", x["at"]), reverse=True)


def summarize(bot, rows, changes=()):
    """rows: dicts from the trades table, closed and open. changes: this bot's entries from changes.json."""
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
            "version": max((c["version"] for c in changes), default=0),
            "shown": min(len(closed), RECENT), "feed": feed(closed, changes)}


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
    assert s["curve"][-1]["v"] == 25.5 and s["feed"][0]["pnl"] == -0.5 and s["feed"][0]["side"] == "long", s
    assert summarize(BOTS[0], [])["trades"] == 0
    # v2 shipped at 10:02: trade 1 (opened 10:01) is v1 though it closed after v2, so it sits below the v2 row
    chs = [{"version": 1, "at": "2026-11-26T09:00Z", "title": "a", "what": "x"},
           {"version": 2, "at": "2026-11-26T10:02Z", "title": "b", "what": "y", "why": "z", "oos": "pf 1.2"}]
    s = summarize(BOTS[0], [t(1, 1.0), t(2, -0.5), t(3, 0, 1)], chs)
    assert [(x["type"], x["version"]) for x in s["feed"]] == [("trade", 2), ("change", 2), ("trade", 1), ("change", 1)], s["feed"]
    assert (s["version"], s["feed"][1]["trades"], s["feed"][1]["pnl"], s["feed"][3]["wins"]) == (2, 1, -0.5, 1), s["feed"]
    assert s["feed"][1]["what"] == "y Почему: z Бэктест: pf 1.2" and s["feed"][0]["coin"] == "SOL", s["feed"]
    print("check ok")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
        sys.exit()
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    changes = json.loads(CHANGES.read_text()) if CHANGES.exists() else []
    data = {"bots": [summarize(b, read(b["db"]), [c for c in changes if c["bot"] == b["name"]]) for b in BOTS]}
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(out, sum(b["trades"] for b in data["bots"]), "trades")
