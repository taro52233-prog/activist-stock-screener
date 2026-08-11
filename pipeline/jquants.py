"""J-Quants API：認証（refresh→id token）と財務・上場情報の取得。

無料プランはデータが約12週間遅延するが、四半期更新の財務指標には許容範囲。
株価は別途 prices.py で日次終値を取るため、ここでは財務・発行株数・配当のみ扱う。
"""
from __future__ import annotations

from typing import Optional

import requests

from config import (
    JQUANTS_AUTH_REFRESH,
    JQUANTS_AUTH_USER,
    JQUANTS_LISTED_INFO,
    JQUANTS_STATEMENTS,
    Secrets,
)
from schema import Fundamentals

_TIMEOUT = 30


class JQuantsClient:
    def __init__(self, secrets: Secrets):
        self._secrets = secrets
        self._id_token: Optional[str] = None
        self._session = requests.Session()

    # -- 認証 --------------------------------------------------------------
    def authenticate(self) -> None:
        refresh = self._secrets.jquants_refresh_token
        if not refresh:
            refresh = self._get_refresh_token()
        self._id_token = self._get_id_token(refresh)

    def _get_refresh_token(self) -> str:
        r = self._session.post(
            JQUANTS_AUTH_USER,
            json={
                "mailaddress": self._secrets.jquants_mail,
                "password": self._secrets.jquants_password,
            },
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        token = r.json().get("refreshToken")
        if not token:
            raise RuntimeError("J-Quants: refreshToken を取得できませんでした")
        return token

    def _get_id_token(self, refresh_token: str) -> str:
        r = self._session.post(
            JQUANTS_AUTH_REFRESH,
            params={"refreshtoken": refresh_token},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        token = r.json().get("idToken")
        if not token:
            raise RuntimeError("J-Quants: idToken を取得できませんでした")
        return token

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._id_token}"}

    # -- 上場情報 ----------------------------------------------------------
    def listed_info(self) -> dict[str, dict]:
        """全上場銘柄の情報を {4桁コード: info} で返す。"""
        r = self._session.get(JQUANTS_LISTED_INFO, headers=self._headers, timeout=_TIMEOUT)
        r.raise_for_status()
        out: dict[str, dict] = {}
        for info in r.json().get("info", []) or []:
            code = _code4(str(info.get("Code") or ""))
            if code:
                out[code] = info
        return out

    # -- 財務 --------------------------------------------------------------
    def statements(self, code: str) -> list[dict]:
        r = self._session.get(
            JQUANTS_STATEMENTS,
            headers=self._headers,
            params={"code": code},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("statements", []) or []

    def fundamentals(self, code: str) -> Fundamentals:
        """最新の（必要フィールドが揃った）開示から Fundamentals を作る。"""
        stmts = self.statements(code)
        if not stmts:
            return Fundamentals(jquants_stale=True)
        # 開示日でソートし、新しい方から採用
        stmts.sort(key=lambda s: str(s.get("DisclosedDate") or ""), reverse=True)
        latest = stmts[0]
        return _statement_to_fundamentals(latest)


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------
def _code4(code: str) -> str:
    if len(code) == 5 and code.endswith("0"):
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
        equity=_f(s, "Equity"),
        shares_out=_f(
            s,
            "NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock",
            "NumberOfIssuedSharesAtEndOfFiscalYearIncludingTreasuryStock",
        ),
        treasury=_f(
            s,
            "NumberOfTreasuryStockAtTheEndOfFiscalYear",
            "NumberOfTreasuryStockAtEndOfFiscalYear",
        ),
        dps_result=_f(s, "ResultDividendPerShareAnnual"),
        dps_forecast=_f(s, "ForecastDividendPerShareAnnual", "NextYearForecastDividendPerShareAnnual"),
        eps=_f(s, "EarningsPerShare"),
        bps=_f(s, "BookValuePerShare"),
        cash=_f(s, "CashAndEquivalents"),
        interest_debt=None,  # 無料プランの statements には無いことが多い
        retained_earnings=_f(s, "RetainedEarnings"),
        statement_date=str(s.get("DisclosedDate") or s.get("CurrentPeriodEndDate") or "") or None,
        jquants_stale=True,
    )
