"""screen.py の決定論コアをオフライン検証する（ネットワーク不要）。

実行: cd リポジトリ直下 && python -m pytest tests/ -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))

from config import Thresholds, Weights          # noqa: E402
from schema import Candidate, Fundamentals, PriceInfo  # noqa: E402
import screen                                    # noqa: E402


KNOWN = [
    {"name": "オアシス", "aliases": ["Oasis", "オアシス"], "weight_bonus": 10},
    {"name": "村上系", "aliases": ["シティインデックスイレブンス"], "weight_bonus": 10},
]


# -- 名前照合 ---------------------------------------------------------------
def test_match_activist_known():
    ok, name, bonus = screen.match_activist("Oasis Japan Strategic Fund Ltd.", KNOWN)
    assert ok is True and name == "オアシス" and bonus == 10


def test_match_activist_fullwidth_and_spaces():
    ok, name, _ = screen.match_activist("オアシス・マネジメント", KNOWN)
    assert ok is True and name == "オアシス"


def test_match_activist_unknown():
    ok, name, bonus = screen.match_activist("野村アセットマネジメント", KNOWN)
    assert ok is False and name == "" and bonus == 0


# -- 取得単価推定 -----------------------------------------------------------
def test_estimate_acq_price():
    price, method = screen.estimate_acq_price(1000, 1_300_000)
    assert price == 1300.0 and method == "funds_div_shares"


def test_estimate_acq_price_missing():
    price, method = screen.estimate_acq_price(None, 1_300_000)
    assert price is None and method == "none"


# -- 派生指標 ---------------------------------------------------------------
def _sample_fundamentals():
    return Fundamentals(
        equity=50_000_000_000,
        shares_out=20_000_000,
        treasury=0,
        dps_result=20.0,
        eps=80.0,
        retained_earnings=30_000_000_000,
        statement_date="2026-03-31",
    )


def test_compute_derived_core_metrics():
    price = PriceInfo(close=1000.0, date="2026-08-08", source="stooq")
    d = screen.compute_derived(price, _sample_fundamentals(), est_acq_price=1300.0,
                               acq_price_method="funds_div_shares")
    assert d.market_cap == 1000.0 * 20_000_000
    assert abs(d.pbr - 0.4) < 1e-9
    assert abs(d.dividend_yield - 0.02) < 1e-9
    assert abs(d.payout_ratio - 0.25) < 1e-9
    assert abs(d.net_cash_to_mktcap - 1.5) < 1e-9
    assert abs(d.deviation_from_acq - ((1000 - 1300) / 1300)) < 1e-9


def test_compute_derived_pbr_from_bps_fallback():
    price = PriceInfo(close=800.0)
    f = Fundamentals(bps=1600.0)  # equity/shares 不明 → price/bps
    d = screen.compute_derived(price, f, None, "none")
    assert abs(d.pbr - 0.5) < 1e-9


def test_compute_derived_handles_missing():
    d = screen.compute_derived(PriceInfo(), Fundamentals(), None, "none")
    assert d.pbr is None and d.market_cap is None and d.dividend_yield is None


# -- スコアリング -----------------------------------------------------------
def _make_candidate(known: bool):
    c = Candidate(code="1234", name="テスト会社")
    c.fund = "オアシス" if known else "一般保有主体"
    c.is_known_activist = known
    c.holding_ratio = 0.072
    c.price = PriceInfo(close=1000.0)
    c.fundamentals = _sample_fundamentals()
    c.derived = screen.compute_derived(c.price, c.fundamentals, 1300.0, "funds_div_shares")
    return c


def test_score_strong_candidate():
    c = _make_candidate(known=True)
    screen.score_candidate(c, Weights(), Thresholds(), known_bonus=10)
    assert c.signal.score >= 90
    fl = c.signal.filters
    assert fl["activist"] and fl["pbr_lt_1"] and fl["cash_rich"] and fl["low_payout"] and fl["entry_ok"]
    assert any("PBR" in r for r in c.signal.reasons_ja)


def test_score_generic_activist_lower_than_known():
    known_c = _make_candidate(known=True)
    generic_c = _make_candidate(known=False)
    screen.score_candidate(known_c, Weights(), Thresholds(), known_bonus=10)
    screen.score_candidate(generic_c, Weights(), Thresholds(), known_bonus=0)
    assert known_c.signal.score > generic_c.signal.score


def test_score_weak_candidate():
    c = Candidate(code="9999", name="割高会社")
    c.fund = ""  # アクティビスト無し
    c.price = PriceInfo(close=2000.0)
    c.fundamentals = Fundamentals(equity=1_000_000_000, shares_out=10_000_000, dps_result=60, eps=100)
    c.derived = screen.compute_derived(c.price, c.fundamentals, None, "none")
    screen.score_candidate(c, Weights(), Thresholds(), known_bonus=0)
    # PBR = 2e10/1e9 = 20 → 割高、アクティビスト無し
    assert c.signal.filters["activist"] is False
    assert c.signal.filters["pbr_lt_1"] is False
    assert c.signal.score < 30


def test_clamp():
    assert screen.clamp(1.5) == 1.0
    assert screen.clamp(-0.2) == 0.0
    assert screen.clamp(0.4) == 0.4
