"""デモ用サンプルデータ生成スクリプト（開発・初期表示用）。

⚠ ここで生成される数値はすべて架空のサンプルです。実データではありません。
   本番データは pipeline/run.py が EDINET / J-Quants から生成します。
   シークレット未設定でもダッシュボードの見た目を確認できるように用意しています。

実行: python pipeline/make_sample.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import config as cfg
from config import Thresholds, Weights
from schema import ActivistExit, Candidate, Fundamentals, PriceInfo, build_output
import screen
import diff as diffmod

# (code, name, market, fund, known, holding, prev, close, equity, shares, treasury, dps, eps, cash, debt, acq_price)
_ROWS = [
    ("7148", "サンプル金融HD", "プライム", "オアシス", True, 0.0721, 0.0512, 980,
     620_000_000_000, 210_000_000, 3_000_000, 22, 96, 380_000_000_000, 40_000_000_000, 1040),
    ("6band", "サンプル素材工業", "プライム", "村上系", True, 0.0655, None, 1520,
     180_000_000_000, 95_000_000, 1_500_000, 30, 140, 90_000_000_000, 12_000_000_000, 1500),
    ("3401", "サンプル化学", "プライム", "ダルトン", True, 0.0533, 0.0488, 720,
     140_000_000_000, 160_000_000, 2_000_000, 12, 70, 65_000_000_000, 20_000_000_000, 760),
    ("8raw", "サンプル商事", "スタンダード", "シルチェスター", True, 0.0512, None, 2380,
     240_000_000_000, 78_000_000, 500_000, 70, 210, 55_000_000_000, 8_000_000_000, 2300),
    ("4005", "サンプル機械", "プライム", "一般投資ファンド", False, 0.0601, None, 1180,
     95_000_000_000, 62_000_000, 0, 18, 88, 30_000_000_000, 15_000_000_000, 1150),
]

_EXITS = [
    ActivistExit(code="7208", name="サンプル自動車部品", fund="エフィッシモ",
                 prev_ratio=0.0612, new_ratio=0.0431, filing_date="2026-08-10",
                 doc_id="S100SAMPLE", doc_url=cfg.EDINET_VIEW_URL),
]


def _norm_code(code: str) -> str:
    # サンプル用のダミーコードを4桁数字に整える
    digits = "".join(ch for ch in code if ch.isdigit())
    return (digits + "0000")[:4] if digits else "0000"


def build() -> list[Candidate]:
    weights, th = Weights(), Thresholds()
    known = [{"name": "既知", "aliases": ["オアシス", "村上系", "ダルトン", "シルチェスター", "エフィッシモ"], "weight_bonus": 10}]
    out = []
    for (code, name, market, fund, is_known, hold, prev, close, equity, shares,
         treasury, dps, eps, cash, debt, acq) in _ROWS:
        c = Candidate(code=_norm_code(code), name=name, market=market)
        c.fund, c.is_known_activist = fund, is_known
        c.holding_ratio, c.prev_ratio = hold, prev
        c.ratio_change = (hold - prev) if prev is not None else None
        c.filing_date = "2026-08-08"
        c.doc_id, c.doc_url = "S100SAMPLE", cfg.EDINET_VIEW_URL
        c.price = PriceInfo(close=close, date="2026-08-08", source="sample")
        c.fundamentals = Fundamentals(
            equity=equity, shares_out=shares, treasury=treasury, dps_result=dps,
            eps=eps, cash=cash, interest_debt=debt, statement_date="2026-03-31",
        )
        c.derived = screen.compute_derived(c.price, c.fundamentals, acq, "funds_div_shares")
        bonus = 10 if is_known else 0
        screen.score_candidate(c, weights, th, known_bonus=bonus)
        out.append(c)
    return out


def main() -> None:
    from datetime import date
    as_of = date(2026, 8, 11)
    candidates = build()
    candidates.sort(key=lambda c: c.signal.score, reverse=True)
    diffmod.annotate_status(candidates, None)  # 全件NEW扱い
    out = build_output(
        generated_at=datetime.now(timezone.utc).isoformat(),
        as_of_date=as_of.isoformat(),
        params={"weights": vars(Weights()), "thresholds": vars(Thresholds())},
        candidates=candidates,
        activist_exits=_EXITS,
        warnings=["これはサンプル（架空）データです。シークレットを設定しGitHub Actionsが実行されると実データに置き換わります。"],
    )
    out["sample"] = True
    cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    with open(cfg.DATA_DIR / "latest.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    with open(cfg.HISTORY_DIR / f"{as_of.isoformat()}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"sample written: {len(candidates)} candidates, {len(_EXITS)} exits")


if __name__ == "__main__":
    main()
