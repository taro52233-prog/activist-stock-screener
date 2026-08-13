"""backtest/simulate.py のオフライン検証（合成価格）。"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backtest"))

from simulate import Params, simulate_one, summarize  # noqa: E402


def hist(closes, start="2024-01-01"):
    d0 = date.fromisoformat(start)
    return [{"d": (d0 + timedelta(days=i)).isoformat(), "c": float(c)} for i, c in enumerate(closes)]


def anchor(h):
    return h[0]["d"], h[0]["c"]


def test_take_profit():
    h = hist([100, 100, 130])
    p = Params(entry_threshold=0.0, take_profit=0.30, stop_loss=-0.20, cost=0.0)
    t = simulate_one(h, "1", "オアシス", *anchor(h), p)
    assert t.entered and t.exit_reason == "tp"
    assert abs(t.ret - 0.30) < 1e-9


def test_stop_loss_with_cost():
    h = hist([100, 100, 80])
    p = Params(entry_threshold=0.0, stop_loss=-0.20, cost=0.003)
    t = simulate_one(h, "1", "f", *anchor(h), p)
    assert t.exit_reason == "sl"
    assert abs(t.ret - (-0.20 - 0.003)) < 1e-9


def test_no_entry_when_price_never_dips():
    h = hist([100, 150, 160])
    p = Params(entry_threshold=0.0)
    t = simulate_one(h, "1", "f", *anchor(h), p)
    assert not t.entered and t.exit_reason == "no_entry" and t.ret == 0.0


def test_time_stop():
    h = hist([100, 100, 105, 105, 105, 105])
    p = Params(entry_threshold=0.0, take_profit=0.30, stop_loss=-0.20, max_hold=2, cost=0.0)
    t = simulate_one(h, "1", "f", *anchor(h), p)
    assert t.exit_reason == "time"
    assert abs(t.ret - 0.05) < 1e-9


def test_eod_open():
    h = hist([100, 100, 105])
    p = Params(entry_threshold=0.0, max_hold=250)
    t = simulate_one(h, "1", "f", *anchor(h), p)
    assert t.entered and t.exit_reason == "eod" and not t.closed


def test_entry_threshold_below_filing():
    # -10%閾値: 終値が90以下になって初めてエントリー
    h = hist([100, 95, 88, 130])
    p = Params(entry_threshold=-0.10, take_profit=0.30, cost=0.0)
    t = simulate_one(h, "1", "f", *anchor(h), p)
    assert t.entered and t.entry_price == 88.0 and t.exit_reason == "tp"


def test_summarize_basic():
    trades = [
        simulate_one(hist([100, 100, 130]), "a", "f", "2024-01-01", 100, Params(cost=0.0)),  # tp +0.30
        simulate_one(hist([100, 100, 80]), "b", "f", "2024-01-01", 100, Params(cost=0.0)),   # sl -0.20
        simulate_one(hist([100, 150, 160]), "c", "f", "2024-01-01", 100, Params()),          # no_entry
    ]
    s = summarize(trades)
    assert s["signals"] == 3 and s["entered"] == 2 and s["closed"] == 2 and s["no_entry"] == 1
    assert abs(s["win_rate"] - 0.5) < 1e-9
    assert abs(s["expectancy"] - 0.05) < 1e-9   # (0.30 + -0.20)/2
