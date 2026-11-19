import asyncio, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main


def test_day_peak_kept_when_the_current_share_falls():
    fam = "/test/peak"
    main._RL_CALLS.pop(fam, None); main._RL_DAY_PEAK.pop(fam, None)
    for _ in range(15):
        asyncio.run(main._rl_take(fam))
        time.sleep(0.05)
    u = main.rl_counts()[fam]
    assert u["day_peak_30min_pct"] == 1.5 and u["last_30min"] == 15
    main._RL_CALLS[fam].clear()                       # the window empties: the share now is 0, the day's peak stays
    u = main.rl_counts().get(fam)
    assert u["last_30min"] == 0 and u["day_peak_30min_pct"] == 1.5 and u["day_peak_at"]
    main._RL_CALLS.pop(fam, None); main._RL_DAY_PEAK.pop(fam, None)


def test_review_reports_an_earlier_peak():
    import monitor
    ctx = {"terminal": {"settings": {"signals_config": {}}, "upstox_usage": {"limits": {"per_min": 250, "per_30min": 1000}, "by_api": {
        "/v3/historical-candle/intraday": {"peak_share_pct": 49.1, "last_min": 22, "last_30min": 491, "rate_limited_today": 0,
                                           "day_peak_30min_pct": 85.2, "day_peak_at": "10:55"}}}}}
    out = monitor.consistency_checks(ctx)
    assert any("UPSTOX USAGE WAS HIGH" in x and "85.2%" in x and "10:55" in x for x in out)
