"""前回スナップショットとの差分検出：NEW / CHANGED / UNCHANGED。

キーは code+fund。スコアが一定以上動いた、または保有割合が動いた場合を CHANGED とする。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from schema import Candidate


def _key(code: str, fund: str) -> str:
    return f"{code}::{fund}"


def load_previous(history_dir: Path, exclude_date: Optional[str] = None) -> Optional[dict]:
    """history ディレクトリから最新（exclude_date を除く）のスナップショットを読む。"""
    if not history_dir.exists():
        return None
    files = sorted(p for p in history_dir.glob("*.json"))
    files = [p for p in files if exclude_date is None or p.stem != exclude_date]
    if not files:
        return None
    try:
        with open(files[-1], encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def annotate_status(
    candidates: list[Candidate],
    previous: Optional[dict],
    score_delta: int = 5,
) -> None:
    """各 Candidate.status を NEW/CHANGED/UNCHANGED に設定する。破壊的。"""
    prev_map: dict[str, dict] = {}
    if previous:
        for c in previous.get("candidates", []):
            act = c.get("activist", {})
            prev_map[_key(c.get("code", ""), act.get("fund", ""))] = c

    for cand in candidates:
        k = _key(cand.code, cand.fund)
        prev = prev_map.get(k)
        if prev is None:
            cand.status = "NEW"
            continue
        prev_score = int(prev.get("signal", {}).get("score", 0))
        prev_ratio = prev.get("activist", {}).get("holding_ratio")
        changed = abs(cand.signal.score - prev_score) >= score_delta
        if not changed and prev_ratio is not None and cand.holding_ratio is not None:
            changed = abs(cand.holding_ratio - prev_ratio) >= 0.01
        cand.status = "CHANGED" if changed else "UNCHANGED"


def new_or_changed(candidates: list[Candidate]) -> list[Candidate]:
    return [c for c in candidates if c.status in ("NEW", "CHANGED")]
