import asyncio, sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import option_plan as op

SR = {"resistances": [{"price": 25015.0, "strength": "Strong", "basis": "Day H"}], "supports": []}


def test_block_mode_refuses_when_the_level_is_close():
    p = op.profit_plan("CE", 25000.0, 20.0, SR, None, None, 1.5, 20, 3.0, {"min_rr": 1.5, "room_mode": "block"})
    room = p["checks"][0]
    assert room["label"].startswith("Room to the target") and not room["pass"]
    assert p["index"]["reward_pts"] < 20                       # target pulled in before the level


def test_warn_mode_shows_the_level_but_keeps_the_plan_target():
    p = op.profit_plan("CE", 25000.0, 20.0, SR, None, None, 1.5, 20, 3.0, {"min_rr": 1.5, "room_mode": "warn"})
    room = p["checks"][0]
    assert room["pass"] and room.get("info") and "25,015.00" in room["detail"] and "would have blocked" in room["detail"]
    assert p["index"]["reward_pts"] == 60.0 and p["index"]["room_mode"] == "warn"
    assert p["index"]["level_room_atr"] is not None


def test_room_mode_setting_per_index(monkeypatch):
    import main
    monkeypatch.setattr(main, "OPTION_OVERRIDES", {"room_nifty": "warn"})
    assert main.room_mode("NIFTY") == "warn" and main.room_mode("BANKNIFTY") == "block"
    monkeypatch.setattr(main, "OPTION_OVERRIDES", {"room_nifty": "bogus"})
    assert main.room_mode("NIFTY") == "block"


def test_room_whatif_reports_both_modes_and_room_buckets():
    import diagnostics as dg
    from indicators import IST
    t0 = datetime(2026, 11, 19, 9, 15, tzinfo=IST)
    cs = []
    px = 25000.0
    for i in range(400):                                      # a few sessions of a gentle zig-zag uptrend
        day = i // 75
        t = t0 + timedelta(days=day, minutes=5 * (i % 75))
        px += (3 if i % 7 < 4 else -2)
        cs.append({"_dt": t, "open": px - 1, "high": px + 4, "low": px - 4, "close": px, "volume": 0})
    rows = [{"i": i, "side": "CE", "atr": 10.0, "day": cs[i]["_dt"].date().isoformat(), "hhmm": cs[i]["_dt"].strftime("%H:%M"),
             "strat": {dg.TRAIL_NAME: 5.0}} for i in (160, 240, 320)]
    res = dg.profit_room_whatif(cs, rows, 5, "NIFTY", {"cfg": {"min_rr": 1.5}, "sl_atr": 1.5, "min_sl": 20, "tgt_atr": 3.0, "room_mode": "warn"})
    assert res["live_mode"] == "warn" and res["warn_all"]["n"] == 3
    assert "room_verdict" in res and isinstance(res["by_room"], list)
