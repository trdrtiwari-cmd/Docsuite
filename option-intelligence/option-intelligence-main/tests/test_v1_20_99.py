import asyncio, collections, sqlite3, sys, time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main
import signal_exits as sx
from fastapi import HTTPException


def test_budget_guard_refuses_before_the_30_minute_limit():
    fam = "/test/budget30"
    now = time.time()
    main._RL_CALLS[fam] = collections.deque([now - 600] * int(main.RL_LIMITS[1800] * main.RL_LOW_SHARE))
    with pytest.raises(HTTPException) as e:                 # non-index data gives way at 90 %
        asyncio.run(main._rl_take(fam, priority=False))
    assert e.value.status_code == 429
    asyncio.run(main._rl_take(fam, priority=True))         # the index candles still get a slot
    main._RL_CALLS[fam] = collections.deque([now - 600] * int(main.RL_LIMITS[1800] * main.RL_HARD_SHARE))
    with pytest.raises(HTTPException):
        asyncio.run(main._rl_take(fam, priority=True))
    assert main.rl_counts()[fam]["self_refused_today"] == 2
    assert main.rl_counts()[fam]["rate_limited_today"] == 0    # not an Upstox 429, no pause
    assert main._RL_COOL.get(fam) is None
    main._RL_CALLS.pop(fam, None)


def test_budget_guard_per_minute():
    fam = "/test/budget60"
    now = time.time()
    main._RL_CALLS[fam] = collections.deque([now - 5] * int(main.RL_LIMITS[60] * main.RL_HARD_SHARE))
    with pytest.raises(HTTPException):
        asyncio.run(main._rl_take(fam))
    main._RL_CALLS.pop(fam, None)


def test_priority_by_instrument():
    assert main._rl_priority("https://x/v3/historical-candle/intraday/NSE_INDEX|Nifty 50/minutes/5")
    assert not main._rl_priority("https://x/v3/historical-candle/intraday/NSE_FO|12345/minutes/5")
    assert not main._rl_priority("https://x/v2/market-quote/quotes", {"instrument_key": "NSE_EQ|INE002A01018,NSE_EQ|INE040A01034"})


def test_yesterdays_429_count_is_not_reported_today():
    fam = "/test/old429"
    main._RL_CALLS[fam] = collections.deque([time.time()])
    saved = dict(main._RL_429)
    main._RL_429.clear(); main._RL_429.update({"_day": "2000-01-01", fam: 3})
    try:
        assert main.rl_counts()[fam]["rate_limited_today"] == 0
    finally:
        main._RL_429.clear(); main._RL_429.update(saved); main._RL_CALLS.pop(fam, None)


def _db(tmp_path, peak, worst):
    p = tmp_path / "s.sqlite3"
    with sqlite3.connect(p) as db:
        db.execute("CREATE TABLE signal_log (id INTEGER PRIMARY KEY, generated_at TEXT, session_date TEXT, symbol TEXT, interval INTEGER, mode TEXT, "
                   "candle_time TEXT, side TEXT, entry REAL, last_close REAL, stop_loss REAL, target REAL)")
        sx.ensure_columns(db)
        db.execute("INSERT INTO signal_log (id, session_date, symbol, side, entry, stop_loss, target, peak_points, worst_points) VALUES (1,?,?,?,?,?,?,?,?)",
                   (datetime.now(main.IST).date().isoformat(), "NIFTY", "CE", 100.0, 70.0, 160.0, peak, worst))
    return p


def test_zero_peak_and_worst_are_kept(tmp_path):
    p = _db(tmp_path, 0.0, 0.0)
    now = datetime.now(main.IST).replace(hour=10, minute=0)
    sx.settle_open_signals(p, "NIFTY", 95.0, now)          # trade went 5 pts against: the best move stays 0, not -5
    with sqlite3.connect(p) as db:
        assert db.execute("SELECT peak_points, worst_points FROM signal_log").fetchone() == (0.0, -5.0)
    sx.settle_open_signals(p, "NIFTY", 110.0, now)
    with sqlite3.connect(p) as db:
        assert db.execute("SELECT peak_points, worst_points FROM signal_log").fetchone() == (10.0, -5.0)


def test_repeated_buy_does_not_force_a_database_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "SIGNAL_LOG_DB", tmp_path / "log.sqlite3")
    main.init_signal_log()
    a = {"last_closed_bar": "2026-11-19T10:15:00+05:30", "atr": 20, "last_close": 26000, "score": 70,
         "final": {"level": "CONFIRMED", "side": "CE", "buy": {"ok": True, "summary": "BUY", "exit_plan": "trail",
                   "index": {"entry": 26000, "stop": 25970, "target": 26060, "atr": 20, "sl_atr": 1.5, "target_atr": 3, "rr": 2}, "option": {}}}}
    main._SIGNAL_LOG_DIRTY.clear(); main._SL_URGENT[0] = False
    assert main.record_signal_row("NIFTY", 5, "standard", a)
    assert main._SIGNAL_LOG_DIRTY.is_set() and main._SL_URGENT[0]
    main._SIGNAL_LOG_DIRTY.clear(); main._SL_URGENT[0] = False
    assert not main.record_signal_row("NIFTY", 5, "standard", a)      # same BUY on the next refresh: ignored
    assert not main._SIGNAL_LOG_DIRTY.is_set() and not main._SL_URGENT[0]


def test_review_mentions_the_budget_guard():
    import monitor
    ctx = {"terminal": {"settings": {"signals_config": {}}, "upstox_usage": {"limits": {"per_min": 250, "per_30min": 1000}, "by_api": {
        "/v3/historical-candle/intraday": {"peak_share_pct": 50, "last_min": 20, "last_30min": 500, "rate_limited_today": 0, "self_refused_today": 7}}}}}
    assert any("UPSTOX BUDGET GUARD" in x and "7 call" in x for x in monitor.consistency_checks(ctx))


# ---- review data corrections (19 Nov review file) ----
def test_near_miss_uses_the_live_trailing_exit():
    import diagnostics as dg
    near = [{"gate": "Entry time window (live app)", "pnl": -24.0, "strat": {dg.TRAIL_NAME: 40.0}},
            {"gate": "Entry time window (live app)", "pnl": -24.0, "strat": {dg.TRAIL_NAME: 12.0}}]
    rep = dg.build_report([], near, {"cost": 4, "target": 30, "stop": 20})
    assert rep["ablation"][0]["avg"] == -24.0                  # the old fixed 30 / 20-point table is unchanged
    live = rep["ablation_live"][0]
    assert live["gate"] == "Entry time window (live app)" and live["avg"] == 26.0 and live["n"] == 2


def test_evaluate_adds_atr_exits_to_near_rows():
    import diagnostics as dg
    from datetime import datetime, timedelta
    t0 = datetime(2026, 11, 19, 10, 0, tzinfo=main.IST)
    cs = [{"_dt": t0 + timedelta(minutes=5 * i), "open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100.5 + i} for i in range(20)]
    rows = dg.evaluate(cs, [{"i": 2, "side": "CE", "atr": 2.0}], 5, 12, 4.0, 30, 20, atr_exits=True)
    assert dg.TRAIL_NAME in rows[0]["strat"]


def test_review_context_reports_the_live_exit_and_live_near_misses():
    import monitor
    rep = {"live_exit": {"plan": "t1.5", "avg": -5}, "live_trail": {"plan": "trail", "avg": 9},
           "confirmed": {"stats": {"avg": -24}}, "ablation": [{"gate": "g", "avg": -24, "n": 3}],
           "ablation_live": [{"gate": "g", "avg": 15, "n": 3}]}
    r = monitor.review_context("2026-11-19", "NIFTY", [], [], [], rep, [])["replay"]
    assert r["live_exit"]["plan"] == "trail" and r["fixed_exit_1_5"]["plan"] == "t1.5"
    assert r["confirmed"]["avg"] == 9 and r["near_miss_by_gate"][0]["avg"] == 15


def test_keep_check_uses_live_near_misses():
    import monitor
    rep = {"ablation_live": [{"gate": "Entry time window (live app)", "avg": 18.0, "n": 3}],
           "ablation": [{"gate": "Entry time window (live app)", "avg": -24.0, "n": 3}]}
    ctx = monitor.review_context("2026-11-19", "NIFTY", [], [], [], rep, [],
                                 [{"gate": "Entry time window 09:45–12:00, 14:30–15:00 IST", "setups": 13, "avg_points": 20.4}])
    ctx["terminal"] = {"settings": {"signals_config": {}}}
    out = monitor.consistency_checks(ctx)
    assert not any(x.startswith("KEEP 'Entry time window") for x in out)   # the old -24.0 artefact no longer says "keep"


# ---- token state stays live ----
def test_status_answers_from_the_known_token_state_without_waiting(monkeypatch):
    monkeypatch.setattr(main, "runtime_token", "tok-1")
    main.TOKEN_CHECK.update({"at": time.time() - 3600, "token": "tok-1", "state": "VALID"})     # due for a refresh
    calls = []

    async def slow_check():
        calls.append(1)
        await asyncio.sleep(5)
        return "VALID"
    monkeypatch.setattr(main, "check_token_state", slow_check)
    main._TOKEN_TASK[0] = None

    async def go():
        t0 = time.time()
        s = await main.status()
        return s, time.time() - t0
    s, took = asyncio.run(go())
    assert s["token_state"] == "VALID" and took < 0.5


def test_any_upstox_answer_updates_the_token_state(monkeypatch):
    monkeypatch.setattr(main, "runtime_token", "tok-2")
    main.TOKEN_CHECK.update({"at": 0, "token": None, "state": "UNKNOWN"})
    main._token_seen("tok-2", 200)
    assert main._token_known() == "VALID"
    main._token_seen("old-token", 401)                 # an answer for another token changes nothing
    assert main._token_known() == "VALID"
    main._token_seen("tok-2", 401)
    assert main._token_known() == "EXPIRED"
    main.TOKEN_CHECK.update({"at": 0, "token": None, "state": "UNKNOWN"})
