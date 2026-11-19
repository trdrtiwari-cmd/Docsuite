import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main


def test_futures_and_options_candles_reused_for_a_minute():
    assert main.INTRA_KIND_MIN_TTL["fo"] >= 60
    assert main.INTRA_KIND_MIN_TTL["index"] == 0          # the signal's own candles stay as fresh as before
    assert main.QUOTE_TTL >= 5


def test_budget_19_nov_mix_falls_under_the_brake():
    # 19 Nov, 30 min: the API counted 829 intraday calls; by kind fo 719 (20 s reuse), index 355, stock 89, other 43
    kinds = {"fo": 719, "index": 355, "stock": 89, "other": 43}
    scale = 829 / sum(kinds.values())
    est = (kinds["fo"] * 20 / main.INTRA_KIND_MIN_TTL["fo"] + kinds["index"] + kinds["stock"] + kinds["other"]) * scale
    assert est / main.RL_LIMITS[1800] < 0.60
