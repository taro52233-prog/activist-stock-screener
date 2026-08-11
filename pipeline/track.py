"""大量保有銘柄の「追跡継続」ストア。

一度アクティビストが提出した銘柄を tracking_days の間 追跡し続ける。
提出日の株価(anchor_price)は固定したまま、現在値を毎日更新して
「取得水準からどれだけ乖離したか」を育てて見えるようにする。

永続ファイル: docs/data/tracked.json （Actionsが毎日コミット）
キー: "<code>::<fund>"
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import config as cfg


def _key(code: str, fund: str) -> str:
    return f"{code}::{fund}"


def load(path: Optional[Path] = None) -> dict:
    path = path or (cfg.DATA_DIR / "tracked.json")
    if not path.exists():
        return {"updated_at": "", "entries": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("entries", {})
        return data
    except (OSError, json.JSONDecodeError):
        return {"updated_at": "", "entries": {}}


def save(store: dict, updated_at: str, path: Optional[Path] = None) -> None:
    path = path or (cfg.DATA_DIR / "tracked.json")
    store["updated_at"] = updated_at
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def merge_filings(store: dict, filings: list, known: list, today: date,
                  match_fn, est_fn, holding_min: float) -> list[dict]:
    """今日の大量保有報告をストアに反映。新規追加・比率更新・撤退検出を行う。

    match_fn(filer_name, known) -> (is_known, disp, bonus)
    est_fn(shares_held, acq_funds) -> (est_acq_price, method)
    returns: 撤退イベントのリスト（既知アクティビストが5%割れ）
    """
    entries = store["entries"]
    exits: list[dict] = []
    for f in filings:
        if not f.sec_code:
            continue
        is_known, disp, bonus = match_fn(f.filer_name, known)
        fund = disp or f.filer_name
        k = _key(f.sec_code, fund)
        filing_date = (f.submit_datetime or "")[:10]

        # 撤退（既知が5%割れ）
        if is_known and f.holding_ratio is not None and f.holding_ratio < holding_min:
            exits.append({
                "code": f.sec_code, "name": f.issuer_name, "fund": fund,
                "prev_ratio": f.prev_ratio, "new_ratio": f.holding_ratio,
                "filing_date": filing_date, "doc_id": f.doc_id,
            })
            if k in entries:
                entries[k]["exited"] = True
            continue

        est, method = est_fn(f.shares_held, f.acq_funds)
        e = entries.get(k)
        if e is None:
            entries[k] = {
                "code": f.sec_code, "name": f.issuer_name, "fund": fund,
                "is_known": is_known, "bonus": bonus,
                "anchor_filing_date": filing_date,
                "anchor_price": None,               # 後で履歴から確定
                "est_acq_price": est, "acq_method": method,
                "shares_out_edinet": f.shares_outstanding,
                "holding_ratio": f.holding_ratio, "prev_ratio": f.prev_ratio,
                "is_joint": f.is_joint, "doc_id": f.doc_id,
                "first_seen": today.isoformat(), "last_seen": today.isoformat(),
                "exited": False,
            }
        else:
            # 既存銘柄：比率などを最新化（アンカー＝初出の提出日/株価は固定）
            e["holding_ratio"] = f.holding_ratio if f.holding_ratio is not None else e.get("holding_ratio")
            e["prev_ratio"] = f.prev_ratio
            e["is_joint"] = f.is_joint
            e["doc_id"] = f.doc_id or e.get("doc_id")
            e["name"] = f.issuer_name or e.get("name")
            e["is_known"] = is_known or e.get("is_known")
            e["bonus"] = max(bonus, e.get("bonus", 0))
            if est is not None and e.get("est_acq_price") is None:
                e["est_acq_price"], e["acq_method"] = est, method
            e["last_seen"] = today.isoformat()
            e["exited"] = False
    return exits


def expire(store: dict, today: date, tracking_days: int) -> None:
    """提出から tracking_days を超えた、または撤退した銘柄を追跡から外す。"""
    entries = store["entries"]
    cutoff = today - timedelta(days=tracking_days)
    for k in list(entries.keys()):
        e = entries[k]
        if e.get("exited"):
            del entries[k]
            continue
        anchor = e.get("anchor_filing_date") or ""
        try:
            if anchor and date.fromisoformat(anchor) < cutoff:
                del entries[k]
        except ValueError:
            continue


def active_entries(store: dict, max_tracked: int) -> list[dict]:
    """追跡中エントリを優先度順（既知＞新しい）で最大 max_tracked 件返す。"""
    items = [e for e in store["entries"].values() if not e.get("exited")]
    items.sort(key=lambda e: (bool(e.get("is_known")), e.get("anchor_filing_date") or ""), reverse=True)
    return items[:max_tracked]
