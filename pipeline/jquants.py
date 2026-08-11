"""J-Quants API V2：APIキー（x-api-key）認証で財務・上場情報を取得。

J-Quants は 2025/12 に V2 へ移行し、旧メール/パスワードのトークン方式は廃止（410 Gone）。
V2 はダッシュボードで発行する API キーを x-api-key ヘッダに付けるだけ。

環境変数 JQUANTS_DEBUG=1 のとき、最初の statements / listed_info の生キーをログに出す
（V2のフィールド名を実データで確認するための一時診断）。
"""
from __future__ import annotations

import os
from typing import Optional

import requests

from config import (
    JQUANTS_LISTED_INFO,
    JQUANTS_STATEMENTS,
    Secrets,
)
from schema import Fundamentals

_TIMEOUT = 30
_DEBUG = os.environ.get("JQUANTS_DEBUG", "").strip() in ("1", "true", "True")


class JQuantsClient:
    def __init__(self, secrets: Secrets):
        self._secrets = secrets
        self._session = requests.Session()
        self._debugged = False

    @property
    def _headers(self) -> dict:
        return {"x-api-key": self._secrets.jquants_api_key}

    def authenticate(self) -> None:
        """V2はAPIキー方式のため事前認証は不要。キーの存在だけ確認。"""
        if not self._secrets.jquants_api_key:
            raise RuntimeError("JQUANTS_API_KEY 未設定")

    def _get(self, url: str, params: Optional[dict] = None) -> dict:
        r = self._session.get(url, headers=self._headers, params=params or {}, timeout=_TIMEOUT)
        if r.status_code != 200:
            raise RuntimeError(f"J-Quants {url.split('/v2/')[-1]} {r.status_code}: {r.text[:200]}")
        return r.json()

    # -- 上場情報 ----------------------------------------------------------
    def listed_info(self) -> dict[str, dict]:
        data = self._get(JQUANTS_LISTED_INFO)
        rows = data.get("info") or data.get("listed_info") or data.get("data") or []
        if _DEBUG and rows:
            print("[jq-debug] listed_info keys:", sorted(rows[0].keys()))
        out: dict[str, dict] = {}
        for info in rows:
            code = _code4(str(info.get("Code") or info.get("code") or ""))
            if code:
                out[code] = info
        return out

    # -- 財務 --------------------------------------------------------------
    def statements(self, code: str) -> list[dict]:
        data = self._get(JQUANTS_STATEMENTS, params={"code": code})
        rows = (data.get("statements") or data.get("fin_statements")
                or data.get("financial_statements") or data.get("data") or [])
        if _DEBUG and rows and not self._debugged:
            self._debugged = True
            print(f"[jq-debug] statements[{code}] keys:", sorted(rows[0].keys()))
            print(f"[jq-debug] statements[{code}] sample:", {k: rows[0][k] for k in list(rows[0])[:40]})
        return rows

    def fundamentals(self, code: str) -> Fundamentals:
        stmts = self.statements(code)
        if not stmts:
            return Fundamentals(jquants_stale=True)
        stmts.sort(key=lambda s: str(s.get("DisclosedDate") or s.get("disclosed_date") or ""), reverse=True)
        return _statement_to_fundamentals(stmts[0])


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------
def _code4(code: str) -> str:
    if len(code) == 5 and code.endswith("0") and code[:-1].isdigit():
        return code[:-1]
    return code


def _f(d: dict, *keys: str) -> Optional[float]:
    """複数キー候補を順に試し、最初に数値化できた値を返す。"""
    for k in keys:
        v = d.get(k)
        if v in (None, "", "-", "－"):
            continue
        try:
            return float(str(v).replace(",", ""))
        except (ValueError, TypeError):
            continue
    return None


def _statement_to_fundamentals(s: dict) -> Fundamentals:
    return Fundamentals(
        equity=_f(s, "Equity", "equity", "NetAssets", "net_assets"),
        shares_out=_f(
            s,
            "NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock",
            "NumberOfIssuedSharesAtEndOfFiscalYearIncludingTreasuryStock",
            "number_of_issued_and_outstanding_shares",
        ),
        treasury=_f(
            s,
            "NumberOfTreasuryStockAtTheEndOfFiscalYear",
            "NumberOfTreasuryStockAtEndOfFiscalYear",
        ),
        dps_result=_f(s, "ResultDividendPerShareAnnual", "result_dividend_per_share_annual"),
        dps_forecast=_f(s, "ForecastDividendPerShareAnnual", "NextYearForecastDividendPerShareAnnual"),
        eps=_f(s, "EarningsPerShare", "earnings_per_share"),
        bps=_f(s, "BookValuePerShare", "book_value_per_share"),
        cash=_f(s, "CashAndEquivalents", "cash_and_equivalents"),
        interest_debt=None,
        retained_earnings=_f(s, "RetainedEarnings", "retained_earnings"),
        statement_date=str(s.get("DisclosedDate") or s.get("disclosed_date")
                           or s.get("CurrentPeriodEndDate") or "") or None,
        jquants_stale=True,
    )
