"""パイプライン内で受け渡すデータ構造と、latest.json 形式への変換。

外部依存を持たない純粋なデータ定義。JSONへの入出力は build_output() / candidate_to_dict() で行う。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# 生データ段階のレコード
# ---------------------------------------------------------------------------
@dataclass
class Filing:
    """EDINETの大量保有報告書 1件（パース結果）。"""
    doc_id: str
    doc_type_code: str
    filer_name: str            # 提出者（ファンド）名
    sec_code: str              # 対象会社の証券コード（4桁）
    issuer_name: str           # 対象会社名
    submit_datetime: str       # 提出日時 (ISO)
    holding_ratio: Optional[float] = None      # 今回保有割合 (0-1)
    prev_ratio: Optional[float] = None         # 変更報告書の場合の前回割合 (0-1)
    shares_held: Optional[float] = None        # 保有株券等の数
    shares_outstanding: Optional[float] = None  # 対象会社の発行済株式等総数
    acq_funds: Optional[float] = None          # 取得資金額（円）
    is_joint: bool = False


@dataclass
class Fundamentals:
    """J-Quants 由来の財務（最新開示・12週遅延の可能性あり）。"""
    equity: Optional[float] = None                 # 純資産（円）
    shares_out: Optional[float] = None             # 発行済株式数（自己株含む）
    treasury: Optional[float] = None               # 自己株式数
    dps_result: Optional[float] = None             # 実績1株配当
    dps_forecast: Optional[float] = None           # 予想1株配当
    eps: Optional[float] = None                    # 1株利益
    bps: Optional[float] = None                    # 1株純資産
    cash: Optional[float] = None                   # 現金及び現金同等物
    interest_debt: Optional[float] = None          # 有利子負債
    retained_earnings: Optional[float] = None      # 利益剰余金
    statement_date: Optional[str] = None
    jquants_stale: bool = True


@dataclass
class PriceInfo:
    close: Optional[float] = None
    date: Optional[str] = None
    source: str = ""


@dataclass
class Derived:
    market_cap: Optional[float] = None
    pbr: Optional[float] = None
    dividend_yield: Optional[float] = None
    payout_ratio: Optional[float] = None
    net_cash: Optional[float] = None
    net_cash_to_mktcap: Optional[float] = None
    est_acq_price: Optional[float] = None
    acq_price_method: str = ""       # funds_div_shares | period_avg | filing_period_price | none
    deviation_from_acq: Optional[float] = None   # (現値-取得単価)/取得単価
    price_at_filing: Optional[float] = None       # 大量保有 提出日の終値
    deviation_from_filing: Optional[float] = None  # (現値-提出日終値)/提出日終値


@dataclass
class Signal:
    score: int = 0
    filters: dict = field(default_factory=dict)   # {activist, pbr_lt_1, cash_rich, low_payout, entry_ok}
    subscores: dict = field(default_factory=dict)
    reasons_ja: list = field(default_factory=list)


@dataclass
class Candidate:
    code: str
    name: str
    market: str = ""
    price: PriceInfo = field(default_factory=PriceInfo)
    fundamentals: Fundamentals = field(default_factory=Fundamentals)
    derived: Derived = field(default_factory=Derived)
    # アクティビスト情報（代表となる最有力ファンド1件を表に出す）
    fund: str = ""
    is_known_activist: bool = False
    holding_ratio: Optional[float] = None
    prev_ratio: Optional[float] = None
    ratio_change: Optional[float] = None
    is_joint: bool = False
    filing_date: str = ""
    doc_id: str = ""
    doc_url: str = ""
    activist_exited: bool = False
    price_history: list = field(default_factory=list)  # [{d,c}...] 約1年の日次終値
    signal: Signal = field(default_factory=Signal)
    status: str = "UNCHANGED"   # NEW | CHANGED | UNCHANGED


@dataclass
class ActivistExit:
    code: str
    name: str
    fund: str
    prev_ratio: Optional[float]
    new_ratio: Optional[float]
    filing_date: str
    doc_id: str = ""
    doc_url: str = ""


def candidate_to_dict(c: Candidate) -> dict:
    return {
        "code": c.code,
        "name": c.name,
        "market": c.market,
        "price": asdict(c.price),
        "price_history": c.price_history,
        "fundamentals": asdict(c.fundamentals),
        "derived": asdict(c.derived),
        "activist": {
            "detected": bool(c.fund),
            "is_known": c.is_known_activist,
            "fund": c.fund,
            "holding_ratio": c.holding_ratio,
            "prev_ratio": c.prev_ratio,
            "ratio_change": c.ratio_change,
            "is_joint": c.is_joint,
            "est_acq_price": c.derived.est_acq_price,
            "acq_price_method": c.derived.acq_price_method,
            "filing_date": c.filing_date,
            "doc_id": c.doc_id,
            "doc_url": c.doc_url,
            "activist_exited": c.activist_exited,
        },
        "signal": {
            "score": c.signal.score,
            "filters": c.signal.filters,
            "subscores": c.signal.subscores,
            "reasons_ja": c.signal.reasons_ja,
        },
        "status": c.status,
    }


def build_output(
    generated_at: str,
    as_of_date: str,
    params: dict,
    candidates: list[Candidate],
    activist_exits: list[ActivistExit],
    warnings: list[str] | None = None,
) -> dict:
    return {
        "generated_at": generated_at,
        "as_of_date": as_of_date,
        "params": params,
        "candidates": [candidate_to_dict(c) for c in candidates],
        "activist_exits": [asdict(e) for e in activist_exits],
        "warnings": warnings or [],
    }
