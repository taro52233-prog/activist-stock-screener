"""米国株の財務サマリーを Yahoo Finance(非公式) から取得する。

米国株はEDINET/J-Quants（日本専用）の対象外なので、監視リスト（バリュー参考）向けに
Yahoo の quoteSummary から BPS(簿価)・発行済株式数・EPS・配当を取得する。APIキー不要。
Yahooはcrumb（トークン）を要求するため、クッキー取得→crumb取得の順で用意する。
取得できない銘柄は株価チャートのみ（財務欠損）に自然縮退する。
"""
from __future__ import annotations

from typing import Optional

import requests

from config import YAHOO_CRUMB, YAHOO_QUOTESUMMARY
from schema import Fundamentals

_TIMEOUT = 20
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
})
_crumb: Optional[str] = None


def _ensure_crumb() -> Optional[str]:
    """クッキーを確立してからcrumbを1回取得し、以後は使い回す。"""
    global _crumb
    if _crumb:
        return _crumb
    for warm in ("https://fc.yahoo.com", "https://finance.yahoo.com/quote/AAPL"):
        try:
            _SESSION.get(warm, timeout=_TIMEOUT)
        except Exception:  # noqa: BLE001
            pass
    try:
        r = _SESSION.get(YAHOO_CRUMB, timeout=_TIMEOUT)
        if r.status_code == 200 and r.text and "<" not in r.text and len(r.text) < 40:
            _crumb = r.text.strip()
    except Exception:  # noqa: BLE001
        pass
    return _crumb


def _raw(d: dict, key: str) -> Optional[float]:
    v = d.get(key)
    if isinstance(v, dict):
        v = v.get("raw")
    return float(v) if isinstance(v, (int, float)) else None


def us_fundamentals(ticker: str) -> Fundamentals:
    """Yahoo quoteSummary から Fundamentals を組み立てる。取得不可は例外。"""
    crumb = _ensure_crumb()
    params = {"modules": "defaultKeyStatistics,summaryDetail,price"}
    if crumb:
        params["crumb"] = crumb
    url = YAHOO_QUOTESUMMARY.format(sym=ticker.upper())
    r = _SESSION.get(url, params=params, timeout=_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"Yahoo quoteSummary {r.status_code}: {r.text[:120]}")
    res = (r.json().get("quoteSummary", {}).get("result") or [None])[0]
    if not res:
        raise RuntimeError("Yahoo quoteSummary 空応答")
    return summary_to_fundamentals(res)


def summary_to_fundamentals(res: dict) -> Fundamentals:
    """quoteSummaryのresult(1件)を Fundamentals にマップ（テスト可能な純関数）。"""
    dks = res.get("defaultKeyStatistics", {}) or {}
    sd = res.get("summaryDetail", {}) or {}
    bps = _raw(dks, "bookValue")
    shares = _raw(dks, "sharesOutstanding")
    eps = _raw(dks, "trailingEps")
    dps = _raw(sd, "dividendRate")
    equity = bps * shares if (bps and shares) else None
    return Fundamentals(
        equity=equity,
        shares_out=shares,
        treasury=0.0,
        dps_result=dps,
        eps=eps,
        bps=bps,
        cash=None,
        statement_date=None,
        jquants_stale=False,
    )
