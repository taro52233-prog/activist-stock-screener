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


# 大量保有報告書CSVの要素ID（EDINETタクソノミ jplvh_cor / jpdei_cor 名前空間）
# ※ 診断で実データから確定した正確なID。
EL_ISSUER_NAME = "jplvh_cor:NameOfIssuer"                 # 発行者の名称＝対象銘柄名
EL_ISSUER_CODE = "jplvh_cor:SecurityCodeOfIssuer"         # 発行者の証券コード＝対象銘柄コード
EL_FILER_NAME = ("jplvh_cor:FilerNameInJapaneseDEI", "jpdei_cor:FilerNameInJapaneseDEI")  # 提出者=保有主体
EL_RATIO = "jplvh_cor:HoldingRatioOfShareCertificatesEtc"                 # 株券等保有割合(小数)
EL_PREV_RATIO = "jplvh_cor:HoldingRatioOfShareCertificatesEtcPerLastReport"  # 直前報告の保有割合
EL_SHARES_HELD = "jplvh_cor:TotalNumberOfStocksEtcHeld"                   # 保有株券等の数(総数)
EL_OUTSTANDING = "jplvh_cor:TotalNumberOfOutstandingStocksEtc"           # 発行済株式等総数
EL_FUNDS = "jplvh_cor:TotalAmountOfFundingForAcquisition"                # 取得資金合計
EL_JOINT_COUNT = "jplvh_cor:TotalNumberOfFilersAndJointHoldersCoverPage"  # 提出者及び共同保有者の総数


def _index_by_element(rows: list[dict]) -> dict[str, str]:
    """要素ID → 最初の非空値 の辞書を作る。"""
    out: dict[str, str] = {}
    for row in rows:
        el = _element(row)
        if not el or el in out:
            continue
        val = _value(row)
        if val is not None:
            out[el] = val
    return out


def _get_str(idx: dict, key) -> str:
    if isinstance(key, tuple):
        for k in key:
            if idx.get(k):
                return str(idx[k])
        return ""
    return str(idx.get(key) or "")


def _ratio_from(idx: dict, key: str) -> Optional[float]:
    val = _to_float(idx.get(key))
    if val is None:
        return None
    if val > 1.0:   # パーセント表記(例 11.34)なら小数化
        val = val / 100.0
    return val


def normalize_sec_code(code: str) -> str:
    """証券コードを4桁/4文字に正規化。5桁数字で末尾0なら1桁削る。英数字コード(例 607A)はそのまま。"""
    code = (code or "").strip()
    if len(code) == 5 and code.endswith("0") and code[:-1].isdigit():
        return code[:-1]
    return code


# ---------------------------------------------------------------------------
# 1書類のパース
# ---------------------------------------------------------------------------
def parse_filing(meta: dict, csv_rows: list[dict]) -> Filing:
    """一覧メタ＋CSV行から Filing を組み立てる。

    大量保有報告書では:
      - 提出者(filer) = 保有主体（ファンド/投資家）… メタ filerName ＋ CSVの提出者名で確定
      - 対象会社(issuer) = 実際に見るべき銘柄 … CSVの NameOfIssuer / SecurityCodeOfIssuer
    メタの secCode は「提出者の」コードなので銘柄には使わない。
    """
    filing = Filing(
        doc_id=str(meta.get("docID") or ""),
        doc_type_code=str(meta.get("docTypeCode") or ""),
        filer_name=str(meta.get("filerName") or ""),
        sec_code="",
        issuer_name="",
        submit_datetime=str(meta.get("submitDateTime") or ""),
    )
    if not csv_rows:
        return filing
    idx = _index_by_element(csv_rows)

    # 対象会社（銘柄）
    filing.sec_code = normalize_sec_code(_get_str(idx, EL_ISSUER_CODE))
    filing.issuer_name = _get_str(idx, EL_ISSUER_NAME)
    # 提出者（保有主体）… CSV表記を優先、無ければメタ
    filer_csv = _get_str(idx, EL_FILER_NAME)
    if filer_csv:
        filing.filer_name = filer_csv
    # 保有割合・前回・株数・取得資金・発行済・共同保有
    filing.holding_ratio = _ratio_from(idx, EL_RATIO)
    filing.prev_ratio = _ratio_from(idx, EL_PREV_RATIO)
    filing.shares_held = _to_float(idx.get(EL_SHARES_HELD))
    filing.shares_outstanding = _to_float(idx.get(EL_OUTSTANDING))
    filing.acq_funds = _to_float(idx.get(EL_FUNDS))
    joint = _to_float(idx.get(EL_JOINT_COUNT))
    filing.is_joint = bool(joint and joint > 1)
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
