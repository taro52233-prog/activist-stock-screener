"""J-Quants API V2（無料プラン）：APIキー（x-api-key）認証で財務サマリーを取得。

無料プランで財務が取れるのは /v2/fins/summary のみ（/listed/info や /fins/statements は403）。
summary のフィールドは略称（Eq=純資産, BPS, EPS, ShOutFY=発行済株式数, TrShFY=自己株,
DivFY=配当, PayoutRatioAnn=配当性向, CashEq=現金 等）。
"""
from __future__ import annotations

import os
from typing import Optional

import requests

from config import JQUANTS_SUMMARY, Secrets
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

    def listed_info(self) -> dict[str, dict]:
        """無料プランでは /listed/info が使えないため空を返す（社名はEDINET由来を使用）。"""
        return {}

    def _get(self, url: str, params: Optional[dict] = None) -> dict:
        r = self._session.get(url, headers=self._headers, params=params or {}, timeout=_TIMEOUT)
        if r.status_code != 200:
            raise RuntimeError(f"J-Quants {url.split('/v2/')[-1]} {r.status_code}: {r.text[:200]}")
        return r.json()

    def summary(self, code: str) -> list[dict]:
        data = self._get(JQUANTS_SUMMARY, params={"code": code})
        rows = data.get("data") or data.get("summary") or []
        if _DEBUG and rows and not self._debugged:
            self._debugged = True
            print(f"[jq-debug] summary[{code}] keys:", sorted(rows[0].keys()))
        return rows

    def fundamentals(self, code: str) -> Fundamentals:
        rows = self.summary(code)
        if not rows:
            return Fundamentals(jquants_stale=True)
        # 開示日(DiscDate)で新しい順に
        rows.sort(key=lambda s: str(s.get("DiscDate") or ""), reverse=True)
        return _summary_to_fundamentals(rows[0])


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------
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


def _summary_to_fundamentals(s: dict) -> Fundamentals:
    """V2 /fins/summary の略称フィールドを Fundamentals にマップ。"""
    return Fundamentals(
        equity=_f(s, "Eq", "ShEq", "NCEq"),                 # 純資産（自己資本）
        shares_out=_f(s, "ShOutFY"),                        # 期末発行済株式数
        treasury=_f(s, "TrShFY"),                           # 期末自己株式数
        dps_result=_f(s, "DivFY", "DivAnn", "DivTotalAnn"),  # 実績1株配当（年間）
        dps_forecast=_f(s, "FDivFY", "FDivAnn", "NxFDivFY"),  # 予想1株配当
        eps=_f(s, "EPS", "NCEPS"),
        bps=_f(s, "BPS", "NCBPS"),
        cash=_f(s, "CashEq"),                               # 現金及び現金同等物
        interest_debt=None,
        retained_earnings=None,
        statement_date=str(s.get("DiscDate") or s.get("CurFYEn") or "") or None,
        jquants_stale=True,
    )
