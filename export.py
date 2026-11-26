#!/usr/bin/env python3
"""Export walt-trader state.json + journal.md + trades.json + changes.json into data.json for app/trader.declare.
Read-only on the sources. trades.json (the Wallet API ledger) is authoritative; history.json is only a fallback
for when it is missing.
Run: python3 export.py [out]   (writes app/data.json, or the given path)
     python3 export.py --check (self-check of the parsers, writes nothing)"""
import json, re, sys
from pathlib import Path

SRC = Path.home() / "Documents/Private/walt-trader"
OUT = Path(__file__).with_name("app") / "data.json"
# fallback only: closed trades accumulated from state.json, used when trades.json is missing
HISTORY = Path(__file__).with_name("history.json")
LINE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) UTC\b")
EQUITY = re.compile(r"Equity[^0-9\n]{0,25}?(\d+(?:\.\d+)?)")
WHY = {"stop_loss": "stop loss", "take_profit": "take profit", "close": "closed by the bot", "open": "still open"}


def equity_points(text):
    """One point per journal line that has a time and an Equity number; others are skipped."""
    pts = []
    for line in text.splitlines():
        m, e = LINE.match(line), EQUITY.search(line)
        if m and e:
            pts.append({"t": f"{m[1]}T{m[2]}Z", "v": float(e[1])})
    return sorted(pts, key=lambda p: p["t"])


def trades(last_closed):
    """Fallback: the closed-trade tail in state.json (no side, kind or rules version there)."""
    out = [{"order": t.get("order"), "coin": coin, "side": "", "kind": "trend", "version": 0, "entry": t.get("entry"),
            "exit": t.get("exit"), "pnl": t.get("pnl_net", t.get("pnl", 0)), "at": t.get("at", ""), "why": t.get("why", "")}
           for coin, ts in (last_closed or {}).items() for t in ts]
    return sorted(out, key=lambda t: t["at"], reverse=True)


def ledger_trades(ledger):
    """ledger = walt-trader/trades.json (tools/ledger.py); open trades are left out (they are in positions)."""
    out = [{"coin": t["coin"], "side": t["side"], "kind": t["kind"], "version": t["version"] or 0,
            "entry": t["entry"], "exit": t["exit"], "pnl": round(t["net"], 2), "at": t["closed"],
            "why": WHY.get(t["why"], t["why"])} for t in ledger if t["net"] is not None]
    return sorted(out, key=lambda t: t["at"], reverse=True)


def changes(chs, trs):
    """Each rule change with what the trades opened under it made."""
    out = []
    for c in chs:
        mine = [t for t in trs if t["version"] == c["version"]]
        out.append({"version": c["version"], "at": c["at"], "title": c["title"], "what": c["what"],
                    "trades": len(mine), "wins": sum(t["pnl"] > 0 for t in mine), "pnl": round(sum(t["pnl"] for t in mine), 2)})
    return sorted(out, key=lambda c: c["at"], reverse=True)


def feed(trs, chs):
    """Trades and rule changes in one list, newest first, grouped by rules version: each change row heads the trades
    opened under it (a trade opened under v4 but closed after v5 still sits under v4)."""
    items = [{"type": "trade", **t} for t in trs] + [{"type": "change", **c} for c in chs]
    return sorted(items, key=lambda x: (x["version"], x["type"] == "change", x["at"]), reverse=True)


def merge(history, fresh):
    """History plus the trades state.json shows now, one per order (or coin+time), newest first."""
    key = lambda t: t.get("order") or f"{t['coin']}@{t['at']}"
    by = {key(t): t for t in history}
    by.update((key(t), t) for t in fresh)
    return sorted(by.values(), key=lambda t: t["at"], reverse=True)


def positions(raw):
    # shortcut: position shape is unknown (none open so far); list form so the dashboard can type and replicate it
    def pick(v, *keys):
        return next((v[k] for k in keys if isinstance(v, dict) and v.get(k) is not None), None)
    return [{"coin": k, "side": str(pick(v, "side", "direction") or ""),
             "entry": pick(v, "entry", "entry_price", "entryPrice")} for k, v in (raw or {}).items()]


def build(state, journal, history=(), ledger=None, chs=()):
    """ledger (trades.json) wins when given; otherwise history plus state.json's tail."""
    trs = ledger_trades(ledger) if ledger is not None else [
        {"side": "", "kind": "trend", "version": 0, **{k: v for k, v in t.items() if k != "order"}}
        for t in merge(history, trades(state.get("last_closed")))]  # old history rows lack side/kind/version
    cs = changes(chs, trs)
    return {"status": state.get("status", "?"), "startEquity": state.get("start_equity", 50),
            "lastCheck": state.get("last_check", ""), "prices": state.get("last_prices", {}),
            "positions": positions(state.get("positions")), "equity": equity_points(journal),
            "trades": trs, "changes": cs, "feed": feed(trs, cs)}


def check():
    j = ("# h\n- 2026-11-19: старт. Баланс 50 USDT\n"
         "- 2026-11-26 10:09 UTC: BTC 1, ETH 2. Equity 47.76 (x)\n"
         "- 2026-11-20 01:00 UTC: Equity до входа 48.70, после ~48.60\n"
         "- 2026-11-21 02:00 UTC: Equity ~46.56. ok\n- 2026-11-22 03:00 UTC: no number here\n")
    assert equity_points(j) == [{"t": "2026-11-20T01:00Z", "v": 48.7}, {"t": "2026-11-21T02:00Z", "v": 46.56},
                                {"t": "2026-11-26T10:09Z", "v": 47.76}], equity_points(j)
    t = trades({"ETH": [{"exit": 1, "pnl_net": 0.1, "at": "2026-11-23T03:04Z", "why": "a"}],
                "BTC": [{"entry": 2, "exit": 3, "pnl": -0.5, "at": "2026-11-24T00:00Z", "why": "b"}]})
    assert [x["coin"] for x in t] == ["BTC", "ETH"] and t[0]["pnl"] == -0.5 and t[1]["entry"] is None and t[0]["version"] == 0, t
    old = [{"coin": "ETH", "at": "2026-11-20T13:49Z", "pnl": -0.06, "why": "x"}, {"order": "o1", "coin": "BTC", "at": "2026-11-23T00:00Z", "pnl": 1, "why": "old"}]
    m = merge(old, [{"order": "o1", "coin": "BTC", "at": "2026-11-23T00:00Z", "pnl": 1, "why": "new"}, {"order": "o2", "coin": "ETH", "at": "2026-11-24T00:00Z", "pnl": 2, "why": "y"}])
    assert [t["why"] for t in m] == ["y", "new", "x"], m
    assert build({}, "", old)["trades"][0] == {"side": "", "kind": "trend", "version": 0,
                                                "coin": "BTC", "at": "2026-11-23T00:00Z", "pnl": 1, "why": "old"}
    d = build({"status": "ACTIVE"}, "")
    assert d["startEquity"] == 50 and d["trades"] == [] and d["equity"] == [] and d["positions"] == [] and d["feed"] == []
    # the ledger: authoritative when present, history ignored
    led = [{"coin": "ETH", "side": "short", "kind": "trend", "version": 1, "entry": 1, "exit": 2, "net": 0.1,
            "closed": "2026-11-20T03:04Z", "why": "take_profit"},
           {"coin": "BTC", "side": "long", "kind": "trend", "version": 2, "entry": 2, "exit": 3, "net": -0.5,
            "closed": "2026-11-24T00:00Z", "why": "stop_loss"},
           {"coin": "SOL", "side": "long", "kind": "casino", "version": 2, "entry": 2, "exit": None, "net": None,
            "closed": None, "why": "open"}]
    chs = [{"version": 1, "at": "2026-11-19T00:00Z", "title": "a", "what": "x"},
           {"version": 2, "at": "2026-11-20T03:04Z", "title": "b", "what": "y"}]
    d = build({"status": "ACTIVE"}, j, old, led, chs)
    assert [t["coin"] for t in d["trades"]] == ["BTC", "ETH"] and d["trades"][0]["why"] == "stop loss", d["trades"]
    assert [(c["version"], c["trades"], c["pnl"]) for c in d["changes"]] == [(2, 1, -0.5), (1, 1, 0.1)], d["changes"]
    # the v1 trade closed at the v2 change's minute but still sits under its own v1 header
    assert [(x["type"], x["version"]) for x in d["feed"]] == [("change", 2), ("trade", 2), ("change", 1), ("trade", 1)], d["feed"]
    assert positions({"BTC": {"side": "short", "entry": 61000}}) == [{"coin": "BTC", "side": "short", "entry": 61000}]
    assert positions({"ETH": {"direction": "long", "entry_price": 1700}}) == [{"coin": "ETH", "side": "long", "entry": 1700}]
    print("check ok")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        state = json.loads((SRC / "state.json").read_text())
        read = lambda n, d: json.loads((SRC / n).read_text()) if (SRC / n).exists() else d
        ledger, history = read("trades.json", None), []
        if ledger is None:  # fallback: keep accumulating history.json from state.json
            history = merge(json.loads(HISTORY.read_text()) if HISTORY.exists() else [], trades(state.get("last_closed")))
            HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=1))
        d = build(state, (SRC / "journal.md").read_text(), history, ledger, read("changes.json", []))
        out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
        out.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        print(f"wrote {out}: {len(d['equity'])} equity points, {len(d['trades'])} trades, {len(d['changes'])} changes")
