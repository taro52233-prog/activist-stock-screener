"""日次終値＋価格履歴の取得：Stooq を主、失敗時に Yahoo Finance(非公式) をフォールバック。

チャート描画のため、最新終値に加えて約1年分の日次終値の履歴も返す。
両ソースとも無料・APIキー不要。部分失敗（一部銘柄だけ取れない）を許容する。
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Optional

import requests

from config import STOOQ_CSV, YAHOO_CHART
from schema import PriceInfo

_TIMEOUT = 20
_HISTORY_DAYS = 260   # 約1年ぶんの取引日
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; activist-screener/1.0)"})


def get_price_and_history(code: str) -> tuple[PriceInfo, list[dict]]:
    """(最新終値, 履歴[{d,c}...]) を返す。取得できなければ (空PriceInfo, [])。"""
    hist = _history_from_stooq(code)
    src = "stooq"
    if not hist:
        hist = _history_from_yahoo(code)
        src = "yahoo"
    if not hist:
        return PriceInfo(), []
    last = hist[-1]
    return PriceInfo(close=last["c"], date=last["d"], source=src), hist


def get_prices_and_histories(codes: list[str]) -> dict[str, tuple[PriceInfo, list[dict]]]:
    out: dict[str, tuple[PriceInfo, list[dict]]] = {}
    for code in codes:
        try:
            out[code] = get_price_and_history(code)
        except Exception:  # noqa: BLE001 - 1銘柄失敗しても継続
            out[code] = (PriceInfo(), [])
    return out


def _history_from_stooq(code: str) -> list[dict]:
    """Stooqの日次CSV全期間から末尾約1年を [{d,c}] で返す（日付昇順）。"""
    url = STOOQ_CSV.format(sym=f"{code}.jp")
    try:
        r = _SESSION.get(url, timeout=_TIMEOUT)
        r.raise_for_status()
        text = r.text.strip()
        if not text or text.lower().startswith("<") or "no data" in text.lower():
            return []
        rows = list(csv.DictReader(io.StringIO(text)))
        out: list[dict] = []
        for row in rows:
            c = row.get("Close") or row.get("close")
            d = row.get("Date") or row.get("date")
            if c in (None, "", "N/D") or not d:
                continue
            try:
                out.append({"d": d, "c": float(c)})
            except ValueError:
                continue
        return out[-_HISTORY_DAYS:]
    except Exception:  # noqa: BLE001
        return []


def _history_from_yahoo(code: str) -> list[dict]:
    """Yahoo chart(1年・日次)から [{d,c}] を返す。"""
    url = YAHOO_CHART.format(sym=f"{code}.T")
    try:
        r = _SESSION.get(url, params={"range": "1y", "interval": "1d"}, timeout=_TIMEOUT)
        r.raise_for_status()
        result = (r.json().get("chart", {}).get("result") or [None])[0]
        if not result:
            return []
        ts = result.get("timestamp") or []
        quotes = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes = quotes.get("close") or []
        out: list[dict] = []
        for t, c in zip(ts, closes):
            if c is None:
                continue
            d = datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
            out.append({"d": d, "c": float(c)})
        return out[-_HISTORY_DAYS:]
    except Exception:  # noqa: BLE001
        return []


def price_on_or_before(history: list[dict], date_iso: str) -> Optional[dict]:
    """指定日以前で最も近い終値 {d,c} を返す。無ければ最初の点。"""
    if not history:
        return None
    chosen = None
    for row in history:
        if row["d"] <= date_iso:
            chosen = row
        else:
            break
    return chosen or history[0]


def downsample(history: list[dict], max_points: int = 150) -> list[dict]:
    """点数を max_points 以下に等間隔で間引く（末尾は必ず残す）。"""
    n = len(history)
    if n <= max_points:
        return history
    step = n / max_points
    idxs = sorted({int(i * step) for i in range(max_points)} | {n - 1})
    return [history[i] for i in idxs if i < n]
