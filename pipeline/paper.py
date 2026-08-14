"""フォワード・ペーパー検証（実弾なし）。

追跡中の候補を毎日評価し、提出時株価(アンカー)近辺の帯に入った銘柄を
「その日の終値で仮に買った」ものとして記録。以後、+TP/-SL/時間切れで仮決済する。
実際の売買は一切行わない。永続ファイル docs/data/paper.json に蓄積する。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

import config as cfg
from config import PaperParams


def _path() -> Path:
    return cfg.DATA_DIR / "paper.json"


def load(path: Optional[Path] = None) -> dict:
    path = path or _path()
    if not path.exists():
        return {"updated_at": "", "params": {}, "trades": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("trades", [])
        return data
    except (OSError, json.JSONDecodeError):
        return {"updated_at": "", "params": {}, "trades": []}


def save(store: dict, updated_at: str, params: PaperParams, path: Optional[Path] = None) -> None:
    path = path or _path()
    store["updated_at"] = updated_at
    store["params"] = vars(params)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def _key(code: str, fund: str) -> str:
    return f"{code}::{fund}"


def _days_between(a: str, b: str) -> int:
    try:
        return (date.fromisoformat(b) - date.fromisoformat(a)).days
    except ValueError:
        return 0


def update(store: dict, candidates: list, params: PaperParams, today: str) -> tuple[list, list]:
    """候補を評価し、新規エントリーと新規エグジットを記録。

    candidates: latest の Candidate（code/name/fund/price.close/derived.price_at_filing/
                derived.deviation_from_filing を参照）。
    returns: (new_entries, new_exits) それぞれ trade dict のリスト。
    """
    trades = store["trades"]
    by_key = {_key(t["code"], t["fund"]): t for t in trades}
    new_entries: list = []
    new_exits: list = []

    # --- 既存オープン取引の決済判定 ---
    latest_close = {}  # code -> 今日の終値
    for c in candidates:
        if c.price.close is not None:
            latest_close[c.code] = c.price.close

    for t in trades:
        if t["status"] != "open":
            continue
        close = latest_close.get(t["code"])
        if close is None:
            continue
        ep = t["entry_price"]
        t["last_price"] = close
        t["ret"] = close / ep - 1.0
        t["days"] = _days_between(t["entry_date"], today)
        reason = None
        if close <= ep * (1 + params.stop_loss):
            reason = "sl"
        elif close >= ep * (1 + params.take_profit):
            reason = "tp"
        elif t["days"] >= params.max_hold_days:
            reason = "time"
        if reason:
            t["status"] = "closed"
            t["exit_date"] = today
            t["exit_price"] = close
            t["exit_reason"] = reason
            new_exits.append(t)

    # --- 新規エントリー判定（未取引・帯に入った初回） ---
    for c in candidates:
        k = _key(c.code, c.fund)
        if k in by_key:
            continue  # 既にエントリー済み（1銘柄1回）
        dev = c.derived.deviation_from_filing
        close = c.price.close
        if dev is None or close is None:
            continue
        if params.entry_floor <= dev <= params.entry_ceiling:
            trade = {
                "code": c.code, "name": c.name, "fund": c.fund,
                "anchor_date": c.filing_date, "anchor_price": c.derived.price_at_filing,
                "entry_date": today, "entry_price": close,
                "status": "open", "last_price": close, "ret": 0.0, "days": 0,
                "exit_date": "", "exit_price": None, "exit_reason": "",
                "dev_at_entry": dev,
            }
            trades.append(trade)
            by_key[k] = trade
            new_entries.append(trade)

    return new_entries, new_exits


# ---------------------------------------------------------------------------
# 集計（ダッシュボード/通知用）
# ---------------------------------------------------------------------------
def summarize(store: dict) -> dict:
    trades = store["trades"]
    closed = [t for t in trades if t["status"] == "closed"]
    open_ = [t for t in trades if t["status"] == "open"]
    wins = [t for t in closed if (t.get("ret") or 0) > 0]
    rets = [t["ret"] for t in closed if t.get("ret") is not None]
    return {
        "total": len(trades),
        "open": len(open_),
        "closed": len(closed),
        "win_rate": (len(wins) / len(closed)) if closed else None,
        "expectancy": (sum(rets) / len(rets)) if rets else None,
        "avg_days": (sum(t.get("days", 0) for t in closed) / len(closed)) if closed else None,
    }
