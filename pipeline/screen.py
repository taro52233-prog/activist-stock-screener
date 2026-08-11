"""スクリーニングの決定論的コア：派生指標の計算・4フィルター・合成スコア。

このモジュールは外部通信を一切行わない純関数の集まり。tests/ でオフライン検証する。
"""
from __future__ import annotations

import unicodedata
from typing import Optional

from config import Thresholds, Weights
from schema import Candidate, Derived, Fundamentals, PriceInfo


# ---------------------------------------------------------------------------
# 小さなユーティリティ
# ---------------------------------------------------------------------------
def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def normalize_name(s: str) -> str:
    """NFKC正規化＋小文字化＋空白/記号の除去（ファンド名照合用）。"""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.lower()
    for ch in (" ", "　", "\t", ".", ",", "・", "、", "。", "-", "(", ")", "（", "）"):
        s = s.replace(ch, "")
    return s


def match_activist(filer_name: str, known: list[dict]) -> tuple[bool, str, int]:
    """提出者名を既知アクティビスト一覧と照合。

    returns: (is_known, display_name, weight_bonus)
    """
    target = normalize_name(filer_name)
    if not target:
        return False, "", 0
    for entry in known:
        for alias in entry.get("aliases", []):
            if normalize_name(alias) and normalize_name(alias) in target:
                return True, entry.get("name", alias), int(entry.get("weight_bonus", 0))
    return False, "", 0


# ---------------------------------------------------------------------------
# 派生指標
# ---------------------------------------------------------------------------
def compute_derived(
    price: PriceInfo,
    f: Fundamentals,
    est_acq_price: Optional[float],
    acq_price_method: str,
) -> Derived:
    """終値と財務から時価総額・PBR・利回り・配当性向・ネットキャッシュ等を計算。

    値が欠損している指標は None のまま残す（部分的なデータでも動く）。
    """
    d = Derived(est_acq_price=est_acq_price, acq_price_method=acq_price_method)
    close = price.close

    shares_ex_treasury = None
    if f.shares_out is not None:
        treasury = f.treasury or 0.0
        shares_ex_treasury = max(f.shares_out - treasury, 0.0)

    # 時価総額
    if close is not None and shares_ex_treasury:
        d.market_cap = close * shares_ex_treasury

    # PBR = 時価総額 / 純資産（純資産が無ければ price/BPS で代替）
    if d.market_cap is not None and f.equity:
        d.pbr = d.market_cap / f.equity
    elif close is not None and f.bps:
        d.pbr = close / f.bps

    # 配当利回り = 実績DPS / 終値（実績が無ければ予想を使用）
    dps = f.dps_result if f.dps_result is not None else f.dps_forecast
    if close and dps is not None:
        d.dividend_yield = dps / close

    # 配当性向 = DPS / EPS
    if dps is not None and f.eps:
        d.payout_ratio = dps / f.eps if f.eps != 0 else None

    # ネットキャッシュ = 現金 - 有利子負債（無ければ利益剰余金で代理）
    if f.cash is not None:
        d.net_cash = f.cash - (f.interest_debt or 0.0)
    elif f.retained_earnings is not None:
        d.net_cash = f.retained_earnings
    if d.net_cash is not None and d.market_cap:
        d.net_cash_to_mktcap = d.net_cash / d.market_cap

    # 取得単価からの乖離
    if close is not None and est_acq_price:
        d.deviation_from_acq = (close - est_acq_price) / est_acq_price

    return d


# ---------------------------------------------------------------------------
# フィルター＋スコアリング
# ---------------------------------------------------------------------------
def score_candidate(
    c: Candidate,
    weights: Weights,
    th: Thresholds,
    known_bonus: int = 0,
) -> None:
    """Candidate に signal（filters/subscores/score/reasons_ja）を書き込む。破壊的。"""
    d = c.derived
    filters: dict[str, bool] = {}
    subs: dict[str, float] = {}
    reasons: list[str] = []

    # 1) アクティビスト存在
    activist_present = bool(c.fund)
    filters["activist"] = activist_present
    if activist_present:
        subs["activist"] = 1.0 if c.is_known_activist else 0.6
        if c.holding_ratio is not None:
            reasons.append(f"{c.fund}が{c.holding_ratio * 100:.1f}%保有"
                           + ("（既知アクティビスト）" if c.is_known_activist else "（5%超の大量保有）"))
        else:
            reasons.append(f"{c.fund}が大量保有")
    else:
        subs["activist"] = 0.0

    # 2) PBR < 1.0
    if d.pbr is not None:
        filters["pbr_lt_1"] = d.pbr < th.pbr_max
        span = max(th.pbr_max - th.pbr_full_score_at, 1e-9)
        subs["pbr"] = clamp((th.pbr_max - d.pbr) / span)
        if d.pbr < th.pbr_max:
            reasons.append(f"PBR {d.pbr:.2f}（1.0未満・資産価値に対して割安）")
    else:
        filters["pbr_lt_1"] = False
        subs["pbr"] = 0.0

    # 3) キャッシュリッチ
    if d.net_cash_to_mktcap is not None:
        filters["cash_rich"] = d.net_cash_to_mktcap >= th.net_cash_ratio_min
        span = max(th.net_cash_full_at - 0.0, 1e-9)
        subs["cash"] = clamp(d.net_cash_to_mktcap / span)
        if d.net_cash_to_mktcap >= th.net_cash_ratio_min:
            reasons.append(f"ネットキャッシュが時価総額の{d.net_cash_to_mktcap * 100:.0f}%（余剰資金潤沢）")
    else:
        filters["cash_rich"] = False
        subs["cash"] = 0.0

    # 4) 低配当性向 / 低利回り（還元余地）
    payout_ok = d.payout_ratio is not None and d.payout_ratio < th.payout_max
    yield_ok = d.dividend_yield is not None and d.dividend_yield < th.yield_max
    filters["low_payout"] = bool(payout_ok or yield_ok)
    payout_sub = 0.0
    if d.payout_ratio is not None:
        payout_sub = clamp((th.payout_max - d.payout_ratio) / max(th.payout_max, 1e-9))
    yield_sub = 0.0
    if d.dividend_yield is not None:
        yield_sub = clamp((th.yield_max - d.dividend_yield) / max(th.yield_max, 1e-9))
    subs["payout"] = max(payout_sub, yield_sub)
    if payout_ok:
        reasons.append(f"配当性向{d.payout_ratio * 100:.0f}%（増配・自社株買いの余地大）")
    elif yield_ok:
        reasons.append(f"配当利回り{d.dividend_yield * 100:.1f}%（還元の伸びしろ）")

    # 5) エントリー水準（現値 <= 推定取得単価 * (1+許容乖離)）
    if d.deviation_from_acq is not None:
        filters["entry_ok"] = d.deviation_from_acq <= th.entry_deviation_max
        # 取得単価を下回るほど高スコア（-20%で満点、+許容ラインで0）
        subs["entry"] = clamp((th.entry_deviation_max - d.deviation_from_acq) / 0.25)
        if d.deviation_from_acq <= 0:
            reasons.append(f"現値が推定取得単価を{abs(d.deviation_from_acq) * 100:.0f}%下回る（プロと同水準以下で仕込める）")
        elif d.deviation_from_acq <= th.entry_deviation_max:
            reasons.append(f"現値が推定取得単価とほぼ同水準（+{d.deviation_from_acq * 100:.0f}%）")
    else:
        filters["entry_ok"] = False
        subs["entry"] = 0.0

    # 合成スコア（0-100）＋ 既知アクティビスト加点
    base = (
        weights.activist * subs["activist"]
        + weights.pbr * subs["pbr"]
        + weights.cash * subs["cash"]
        + weights.payout * subs["payout"]
        + weights.entry * subs["entry"]
    )
    score = base * 100.0
    if c.is_known_activist:
        score += known_bonus
    c.signal.score = int(round(clamp(score, 0.0, 100.0)))
    c.signal.filters = filters
    c.signal.subscores = {k: round(v, 3) for k, v in subs.items()}
    c.signal.reasons_ja = reasons


def estimate_acq_price(filing_shares: Optional[float], acq_funds: Optional[float]) -> tuple[Optional[float], str]:
    """取得資金 ÷ 取得株数 で推定取得単価を出す。欠損時は (None, 'none')。"""
    if filing_shares and acq_funds and filing_shares > 0:
        return acq_funds / filing_shares, "funds_div_shares"
    return None, "none"
