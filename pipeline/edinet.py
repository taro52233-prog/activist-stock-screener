"""EDINET API v2：大量保有報告書の取得・フィルタ・パース。

設計方針:
  - 書類一覧JSONのメタデータ（filerName / secCode / docTypeCode / submitDateTime）を
    最も信頼できる主キーとして使う。
  - CSV(type=5, UTF-16, タブ区切り)からは「保有割合・前回割合・保有株数・取得資金」だけを
    項目名のキーワード一致でベストエフォート抽出する。要素IDはタクソノミ改定で変わりうるため
    項目名（日本語ラベル）ベースの緩いマッチにしている。
  - 取得できない項目は None のまま返す（後段は欠損に耐える）。
"""
from __future__ import annotations

import csv
import io
import re
import time
import zipfile
from datetime import date, timedelta
from typing import Optional

import requests

from config import (
    EDINET_DOC_GET,
    EDINET_DOC_LIST,
    EDINET_DOCTYPE_CHANGE,
    EDINET_DOCTYPE_HOLDING,
)
from schema import Filing

_TIMEOUT = 30
_SESSION = requests.Session()


# ---------------------------------------------------------------------------
# 日付ユーティリティ
# ---------------------------------------------------------------------------
def business_days_back(end: date, n: int) -> list[date]:
    """end を含め、直近 n 営業日（土日を除く）を新しい順で返す。"""
    days: list[date] = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:  # 0=Mon .. 4=Fri
            days.append(d)
        d -= timedelta(days=1)
    return days


# ---------------------------------------------------------------------------
# 書類一覧
# ---------------------------------------------------------------------------
def list_documents(api_key: str, day: date) -> list[dict]:
    """指定日に提出された書類一覧（メタデータ）を返す。"""
    params = {"date": day.isoformat(), "type": "2", "Subscription-Key": api_key}
    r = _SESSION.get(EDINET_DOC_LIST, params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data.get("results", []) or []


def filter_holding_reports(results: list[dict]) -> list[dict]:
    """大量保有報告書（350/360/370/380）だけを抜き出す。"""
    out = []
    for row in results:
        code = str(row.get("docTypeCode") or "")
        if code in EDINET_DOCTYPE_HOLDING:
            out.append(row)
    return out


# ---------------------------------------------------------------------------
# 書類本体(CSV)取得
# ---------------------------------------------------------------------------
def download_csv_rows(api_key: str, doc_id: str) -> list[dict]:
    """type=5 のZIPを取得し、中のCSV（UTF-16タブ区切り）を dict 行のリストで返す。"""
    url = EDINET_DOC_GET.format(doc_id=doc_id)
    params = {"type": "5", "Subscription-Key": api_key}
    r = _SESSION.get(url, params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    rows: list[dict] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(r.content))
    except zipfile.BadZipFile:
        return rows
    for name in zf.namelist():
        if not name.lower().endswith(".csv"):
            continue
        raw = zf.read(name)
        text = _decode_edinet_csv(raw)
        reader = csv.DictReader(io.StringIO(text), delimiter="\t")
        for row in reader:
            rows.append(row)
    return rows


def _decode_edinet_csv(raw: bytes) -> str:
    for enc in ("utf-16", "utf-16-le", "utf-8-sig", "cp932"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 値の抽出ヘルパ
# ---------------------------------------------------------------------------
_NUM_RE = re.compile(r"-?[0-9][0-9,]*\.?[0-9]*")


def _to_float(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    m = _NUM_RE.search(str(s).replace("　", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _label(row: dict) -> str:
    return str(row.get("項目名") or row.get("項目名 ") or "")


def _element(row: dict) -> str:
    return str(row.get("要素ID") or "")


def _value(row: dict) -> Optional[str]:
    v = row.get("値")
    if v in (None, "", "－", "-", "‐"):
        return None
    return v


def _find_ratio(rows: list[dict], want_prev: bool) -> Optional[float]:
    """保有割合を探す。want_prev=True なら「前回/直前」を含む項目を優先。

    値はパーセント表記(7.23)のことも小数(0.0723)のこともあるため 1 を超えたら%とみなす。
    """
    prev_kw = ("前回", "直前", "提出後", "前回報告")
    candidates: list[float] = []
    for row in rows:
        label = _label(row)
        el = _element(row)
        is_holding = ("保有割合" in label) or ("HoldingRatio" in el)
        if not is_holding:
            continue
        is_prev = any(k in label for k in prev_kw)
        if want_prev != is_prev:
            continue
        val = _to_float(_value(row))
        if val is None:
            continue
        if val > 1.0:
            val = val / 100.0
        candidates.append(val)
    if not candidates:
        return None
    # 最も妥当（0<r<=1）なものを返す
    valid = [v for v in candidates if 0 < v <= 1.0]
    return (valid or candidates)[0]


def _find_by_labels(rows: list[dict], keywords: tuple[str, ...]) -> Optional[float]:
    for row in rows:
        label = _label(row)
        if any(k in label for k in keywords):
            val = _to_float(_value(row))
            if val is not None:
                return val
    return None


# ---------------------------------------------------------------------------
# 1書類のパース
# ---------------------------------------------------------------------------
def parse_filing(meta: dict, csv_rows: list[dict]) -> Filing:
    """一覧メタ＋CSV行から Filing を組み立てる。"""
    sec = str(meta.get("secCode") or "")
    # secCode は5桁(末尾0)で来ることが多い → 4桁化
    code4 = sec[:-1] if len(sec) == 5 and sec.endswith("0") else sec
    filing = Filing(
        doc_id=str(meta.get("docID") or ""),
        doc_type_code=str(meta.get("docTypeCode") or ""),
        filer_name=str(meta.get("filerName") or ""),
        sec_code=code4,
        issuer_name=str(meta.get("issuerName") or meta.get("filerName") or ""),
        submit_datetime=str(meta.get("submitDateTime") or ""),
    )
    if csv_rows:
        filing.holding_ratio = _find_ratio(csv_rows, want_prev=False)
        if str(filing.doc_type_code) in EDINET_DOCTYPE_CHANGE:
            filing.prev_ratio = _find_ratio(csv_rows, want_prev=True)
        filing.shares_held = _find_by_labels(
            csv_rows, ("保有株券等の数", "保有株券等の総数", "株券等保有数")
        )
        filing.acq_funds = _find_by_labels(
            csv_rows, ("取得資金", "取得に要した資金", "取得のために要した資金")
        )
    return filing


# ---------------------------------------------------------------------------
# 高レベル：直近N営業日の大量保有報告書を集約
# ---------------------------------------------------------------------------
def collect_recent_filings(
    api_key: str,
    end_day: date,
    lookback_business_days: int,
    fetch_bodies: bool = True,
    sleep_sec: float = 0.3,
) -> tuple[list[Filing], list[str]]:
    """直近営業日の大量保有報告書を集める。

    returns: (filings, warnings)
    """
    warnings: list[str] = []
    metas: list[dict] = []
    for day in business_days_back(end_day, lookback_business_days):
        try:
            results = list_documents(api_key, day)
            metas.extend(filter_holding_reports(results))
        except Exception as e:  # noqa: BLE001 - 1日失敗しても継続
            warnings.append(f"EDINET一覧取得失敗 {day}: {e}")

    filings: list[Filing] = []
    for meta in metas:
        doc_id = str(meta.get("docID") or "")
        csv_rows: list[dict] = []
        if fetch_bodies and doc_id:
            try:
                csv_rows = download_csv_rows(api_key, doc_id)
                if sleep_sec:
                    time.sleep(sleep_sec)
            except Exception as e:  # noqa: BLE001
                warnings.append(f"EDINET本文取得失敗 {doc_id}: {e}")
        filings.append(parse_filing(meta, csv_rows))
    return filings, warnings
