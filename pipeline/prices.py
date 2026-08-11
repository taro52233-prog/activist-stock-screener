"""日次終値の取得：Stooq を主、失敗時に Yahoo Finance(非公式) をフォールバック。

J-Quants無料枠の株価は約12週間遅延するため、エントリー判定に使えるだけの
「現在に近い終値」をここで確保する。両ソースとも無料・APIキー不要。
部分失敗（一部銘柄だけ取れない）を許容する設計。
"""
from __future__ import annotations

import csv
import io
from typing import Optional

import requests

from config import STOOQ_CSV, YAHOO_CHART
from schema import PriceInfo

_TIMEOUT = 20
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; activist-screener/1.0)"})


def get_price(code: str) -> PriceInfo:
    """4桁コードの最新終値を返す。取得できなければ close=None。"""
    info = _from_stooq(code)
    if info.close is not None:
        return info
    return _from_yahoo(code)


def get_prices(codes: list[str]) -> dict[str, PriceInfo]:
    out: dict[str, PriceInfo] = {}
    for code in codes:
        try:
            out[code] = get_price(code)
        except Exception:  # noqa: BLE001 - 1銘柄失敗しても継続
            out[code] = PriceInfo()
    return out


def _from_stooq(code: str) -> PriceInfo:
    sym = f"{code}.jp"
    url = STOOQ_CSV.format(sym=sym)
    try:
        r = _SESSION.get(url, timeout=_TIMEOUT)
        r.raise_for_status()
        text = r.text.strip()
        if not text or text.lower().startswith("<") or "no data" in text.lower():
            return PriceInfo()
        reader = list(csv.DictReader(io.StringIO(text)))
        if not reader:
            return PriceInfo()
        last = reader[-1]
        close = last.get("Close") or last.get("close")
        d = last.get("Date") or last.get("date")
        if close in (None, "", "N/D"):
            return PriceInfo()
        return PriceInfo(close=float(close), date=d, source="stooq")
    except Exception:  # noqa: BLE001
        return PriceInfo()


def _from_yahoo(code: str) -> PriceInfo:
    sym = f"{code}.T"
    url = YAHOO_CHART.format(sym=sym)
    try:
        r = _SESSION.get(url, params={"range": "5d", "interval": "1d"}, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        result = (data.get("chart", {}).get("result") or [None])[0]
        if not result:
            return PriceInfo()
        meta = result.get("meta", {})
        close = meta.get("regularMarketPrice")
        ts = result.get("timestamp") or []
        d = None
        if ts:
            from datetime import datetime, timezone
            d = datetime.fromtimestamp(ts[-1], tz=timezone.utc).date().isoformat()
        if close is None:
            # 終値配列の最後の非nullを使う
            quotes = (result.get("indicators", {}).get("quote") or [{}])[0]
            closes = [c for c in (quotes.get("close") or []) if c is not None]
            if closes:
                close = closes[-1]
        if close is None:
            return PriceInfo()
        return PriceInfo(close=float(close), date=d, source="yahoo")
    except Exception:  # noqa: BLE001
        return PriceInfo()
