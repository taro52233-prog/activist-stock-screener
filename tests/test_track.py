"""track.py（追跡継続ストア）のオフライン検証。"""
import os
import sys
from dataclasses import dataclass
from datetime import date
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))

import screen          # noqa: E402
import track           # noqa: E402


@dataclass
class FakeFiling:
    sec_code: str
    filer_name: str
    issuer_name: str
    submit_datetime: str
    holding_ratio: Optional[float] = None
    prev_ratio: Optional[float] = None
    shares_held: Optional[float] = None
    acq_funds: Optional[float] = None
    shares_outstanding: Optional[float] = None
    is_joint: bool = False
    doc_id: str = "S100X"


KNOWN = [{"name": "オアシス", "aliases": ["Oasis", "オアシス"], "weight_bonus": 10}]


def _store():
    return {"updated_at": "", "entries": {}}


def test_merge_adds_new_entry():
    store = _store()
    f = FakeFiling("2413", "Oasis Japan", "エムスリー", "2026-08-10T15:00",
                   holding_ratio=0.05, shares_held=1000, acq_funds=1_639_000)
    exits = track.merge_filings(store, [f], KNOWN, date(2026, 8, 11),
                                screen.match_activist, screen.estimate_acq_price, 0.05)
    assert exits == []
    e = store["entries"]["2413::オアシス"]
    assert e["is_known"] and e["anchor_filing_date"] == "2026-08-10"
    assert e["est_acq_price"] == 1639.0 and e["anchor_price"] is None


def test_anchor_and_ratio_update_but_anchor_fixed():
    store = _store()
    f1 = FakeFiling("2413", "Oasis", "エムスリー", "2026-08-10T00:00", holding_ratio=0.05)
    track.merge_filings(store, [f1], KNOWN, date(2026, 8, 11),
                        screen.match_activist, screen.estimate_acq_price, 0.05)
    store["entries"]["2413::オアシス"]["anchor_price"] = 1500.0  # 確定済みを模擬
    # 変更報告で比率上昇・提出日も新しいが、アンカーは固定のまま
    f2 = FakeFiling("2413", "Oasis", "エムスリー", "2026-08-20T00:00", holding_ratio=0.07, prev_ratio=0.05)
    track.merge_filings(store, [f2], KNOWN, date(2026, 8, 21),
                        screen.match_activist, screen.estimate_acq_price, 0.05)
    e = store["entries"]["2413::オアシス"]
    assert e["holding_ratio"] == 0.07
    assert e["anchor_filing_date"] == "2026-08-10" and e["anchor_price"] == 1500.0


def test_exit_detected_and_removed():
    store = _store()
    f1 = FakeFiling("2413", "Oasis", "エムスリー", "2026-08-10T00:00", holding_ratio=0.06)
    track.merge_filings(store, [f1], KNOWN, date(2026, 8, 11),
                        screen.match_activist, screen.estimate_acq_price, 0.05)
    # 5%割れの変更報告 → 撤退
    f2 = FakeFiling("2413", "Oasis", "エムスリー", "2026-08-20T00:00", holding_ratio=0.04, prev_ratio=0.06)
    exits = track.merge_filings(store, [f2], KNOWN, date(2026, 8, 21),
                                screen.match_activist, screen.estimate_acq_price, 0.05)
    assert len(exits) == 1 and exits[0]["new_ratio"] == 0.04
    track.expire(store, date(2026, 8, 21), 90)
    assert "2413::オアシス" not in store["entries"]


def test_expire_after_tracking_days():
    store = _store()
    f = FakeFiling("6302", "一般ファンド", "住友重機", "2026-01-01T00:00", holding_ratio=0.06)
    track.merge_filings(store, [f], KNOWN, date(2026, 1, 2),
                        screen.match_activist, screen.estimate_acq_price, 0.05)
    track.expire(store, date(2026, 8, 11), 90)   # 90日超過
    assert store["entries"] == {}


def test_active_prioritizes_known_and_caps():
    store = _store()
    fs = [
        FakeFiling("1001", "Oasis", "A", "2026-08-01T00:00", holding_ratio=0.06),
        FakeFiling("1002", "一般", "B", "2026-08-10T00:00", holding_ratio=0.06),
        FakeFiling("1003", "一般", "C", "2026-08-05T00:00", holding_ratio=0.06),
    ]
    track.merge_filings(store, fs, KNOWN, date(2026, 8, 11),
                        screen.match_activist, screen.estimate_acq_price, 0.05)
    active = track.active_entries(store, max_tracked=2)
    assert len(active) == 2
    assert active[0]["code"] == "1001"   # 既知が先頭
