"""pipeline/paper.py（フォワード・ペーパー検証）のオフライン検証。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))

from config import PaperParams          # noqa: E402
from schema import Candidate, Derived, PriceInfo  # noqa: E402
import paper                            # noqa: E402


def cand(code, close, dev, anchor=1000.0, fund="オアシス", name="銘柄"):
    c = Candidate(code=code, name=name)
    c.fund = fund
    c.filing_date = "2026-06-01"
    c.price = PriceInfo(close=close)
    c.derived = Derived(price_at_filing=anchor, deviation_from_filing=dev)
    return c


def store():
    return {"updated_at": "", "params": {}, "trades": []}


def test_entry_within_band():
    s = store()
    ne, nx = paper.update(s, [cand("2413", 1000, 0.0)], PaperParams(), "2026-08-01")
    assert len(ne) == 1 and len(nx) == 0
    assert s["trades"][0]["status"] == "open" and s["trades"][0]["entry_price"] == 1000


def test_no_entry_outside_band():
    s = store()
    # dev -0.5 は暴落し切り（floor -0.20 未満）→ 除外
    ne, _ = paper.update(s, [cand("1", 500, -0.5)], PaperParams(), "2026-08-01")
    # dev +0.2 は高すぎ（ceiling 0.05 超）→ 除外
    ne2, _ = paper.update(s, [cand("2", 1200, 0.2)], PaperParams(), "2026-08-01")
    assert ne == [] and ne2 == [] and s["trades"] == []


def test_no_double_entry():
    s = store()
    paper.update(s, [cand("2413", 1000, 0.0)], PaperParams(), "2026-08-01")
    ne, _ = paper.update(s, [cand("2413", 990, -0.01)], PaperParams(), "2026-08-02")
    assert ne == [] and len(s["trades"]) == 1


def test_take_profit_exit():
    s = store()
    paper.update(s, [cand("2413", 1000, 0.0)], PaperParams(), "2026-08-01")
    _, nx = paper.update(s, [cand("2413", 1300, 0.3, anchor=1000)], PaperParams(), "2026-08-20")
    assert len(nx) == 1 and s["trades"][0]["exit_reason"] == "tp"
    assert abs(s["trades"][0]["ret"] - 0.30) < 1e-9


def test_stop_loss_exit():
    s = store()
    paper.update(s, [cand("2413", 1000, 0.0)], PaperParams(), "2026-08-01")
    _, nx = paper.update(s, [cand("2413", 800, -0.2)], PaperParams(), "2026-08-20")
    assert len(nx) == 1 and s["trades"][0]["exit_reason"] == "sl"


def test_time_exit():
    s = store()
    paper.update(s, [cand("2413", 1000, 0.0)], PaperParams(), "2026-01-01")
    _, nx = paper.update(s, [cand("2413", 1010, 0.01)], PaperParams(max_hold_days=365), "2027-01-05")
    assert len(nx) == 1 and s["trades"][0]["exit_reason"] == "time"


def test_summarize():
    s = store()
    paper.update(s, [cand("a", 1000, 0.0)], PaperParams(), "2026-08-01")
    paper.update(s, [cand("a", 1300, 0.3)], PaperParams(), "2026-08-20")   # tp win
    paper.update(s, [cand("b", 1000, 0.0)], PaperParams(), "2026-08-01")
    paper.update(s, [cand("b", 800, -0.2)], PaperParams(), "2026-08-20")   # sl loss
    su = paper.summarize(s)
    assert su["closed"] == 2 and abs(su["win_rate"] - 0.5) < 1e-9
