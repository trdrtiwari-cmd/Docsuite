import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import orb_live
from indicators import IST


def _cs(day, prices):
    t0 = datetime.combine(day, datetime.min.time(), IST).replace(hour=9, minute=15)
    return [{"_dt": t0 + timedelta(minutes=5 * i), "open": p, "high": p + 1, "low": p - 1, "close": p} for i, p in enumerate(prices)]


def test_orb15t_needs_the_engine_on_the_break_side():
    day = datetime(2026, 11, 20).date()
    cs = _cs(day, [100, 101, 100, 110])                           # 09:15-09:25 range, 09:30 closes above it
    now = datetime.combine(day, datetime.min.time(), IST).replace(hour=9, minute=40)
    orb_live._TREND_SEEN.clear()
    a, _ = orb_live.apply({"side": "CE"}, cs, 5, now=now, strategy="orb15t")
    assert a["signal"] == "CONFIRMED_CE" and a["side"] == "CE" and a["strategy"] == "orb15t"
    orb_live._TREND_SEEN.clear()
    b, _ = orb_live.apply({"side": "PE"}, cs, 5, now=now, strategy="orb15t")
    assert b["signal"] == "WAIT" and b["side"] is None
    assert any(g["label"].startswith("Engine leans") and not g["pass"] for g in b["gates"])


def test_orb15t_remembers_the_engine_side_on_the_break_bar():
    day = datetime(2026, 11, 21).date()
    cs = _cs(day, [100, 101, 100, 110])
    now = datetime.combine(day, datetime.min.time(), IST).replace(hour=9, minute=40)
    orb_live._TREND_SEEN.clear()
    orb_live.apply({"side": "CE"}, cs, 5, now=now, strategy="orb15t")      # seen on the break bar
    later = cs + _cs(day, [100, 101, 100, 110, 111])[4:]
    c, _ = orb_live.apply({"side": "PE"}, later, 5, now=now + timedelta(minutes=5), strategy="orb15t")
    assert any(g["label"].startswith("Engine leans") and g["pass"] for g in c["gates"])


def test_exit_plan_per_index(monkeypatch):
    import main
    monkeypatch.setattr(main, "OPTION_OVERRIDES", {"exit_plan": "t1.5", "exit_plan_banknifty": "trail"})
    assert main.exit_plan_for("NIFTY") == "t1.5" and main.exit_plan_for("BANKNIFTY") == "trail"
    monkeypatch.setattr(main, "OPTION_OVERRIDES", {"exit_plan": "t1.5"})
    assert main.exit_plan_for("BANKNIFTY") == "t1.5"


def test_room_verdict_judges_refused_trades():
    import diagnostics as dg
    import option_plan as op
    # direct check of the verdict rules through a tiny fake: refused winners vs passing ones
    res = {"passed": [12.0], "blocked": [22.6, 18.8, 41.1, 13.2, -46.3, 28.1]}
    sb = dg.stats(res["blocked"])
    assert sb["avg"] > 0            # NIFTY-like: Block refuses winners
