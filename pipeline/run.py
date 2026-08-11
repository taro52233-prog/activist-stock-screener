"""日次パイプラインのエントリポイント。

  EDINET(大量保有) → アクティビスト判定 → J-Quants(財務) → 終値 → 派生指標 → スコア
  → 前回差分 → docs/data/latest.json 出力 → Chatwork通知

使い方:
  python pipeline/run.py                     # 本番（今日・全処理）
  python pipeline/run.py --date 2026-08-10   # 対象日を指定
  python pipeline/run.py --dry-run           # 書き込み/通知せず要約のみ
  python pipeline/run.py --no-notify         # 通知だけ抑止
  python pipeline/run.py --codes 7203,6758   # EDINETを使わず指定コードだけ処理(検証用)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import config as cfg
from config import load_config, load_known_activists
from schema import ActivistExit, Candidate, PriceInfo, build_output
import screen
import diff as diffmod

JST = timezone(timedelta(hours=9))
DASHBOARD_URL = "https://taro52233-prog.github.io/activist-stock-screener/"


def jst_today() -> date:
    return datetime.now(JST).date()


# ---------------------------------------------------------------------------
# アクティビスト候補の構築
# ---------------------------------------------------------------------------
def build_candidates_from_edinet(conf, known) -> tuple[list[Candidate], list[ActivistExit], list[str]]:
    import edinet
    th = conf.thresholds
    warnings: list[str] = []

    target = jst_today()
    filings, w = edinet.collect_recent_filings(
        conf.secrets.edinet_api_key, target, th.lookback_business_days, fetch_bodies=True
    )
    warnings.extend(w)

    # sec_code ごとにまとめ、代表ファンドを選ぶ
    by_code: dict[str, list] = {}
    for f in filings:
        if not f.sec_code:
            continue
        by_code.setdefault(f.sec_code, []).append(f)

    candidates: list[Candidate] = []
    exits: list[ActivistExit] = []

    for code, group in by_code.items():
        # 各ファイリングに既知判定を付与
        annotated = []
        for f in group:
            is_known, disp, bonus = screen.match_activist(f.filer_name, known)
            annotated.append((f, is_known, disp, bonus))

        # 撤退検出：既知アクティビストの変更報告で5%割れ
        for f, is_known, disp, bonus in annotated:
            if is_known and f.holding_ratio is not None and f.holding_ratio < th.holding_min:
                exits.append(ActivistExit(
                    code=code, name=f.issuer_name, fund=disp,
                    prev_ratio=f.prev_ratio, new_ratio=f.holding_ratio,
                    filing_date=f.submit_datetime[:10], doc_id=f.doc_id,
                    doc_url=cfg.EDINET_VIEW_URL,
                ))

        # 代表選定：既知>weight>保有割合 の順
        annotated.sort(
            key=lambda t: (t[1], t[3], (t[0].holding_ratio or 0)), reverse=True
        )
        rep_f, is_known, disp, bonus = annotated[0]
        # 代表が5%割れ（撤退）ならロング候補には出さない
        if rep_f.holding_ratio is not None and rep_f.holding_ratio < th.holding_min:
            continue

        cand = Candidate(code=code, name=rep_f.issuer_name)
        cand.fund = disp or rep_f.filer_name
        cand.is_known_activist = is_known
        cand.holding_ratio = rep_f.holding_ratio
        cand.prev_ratio = rep_f.prev_ratio
        if rep_f.holding_ratio is not None and rep_f.prev_ratio is not None:
            cand.ratio_change = rep_f.holding_ratio - rep_f.prev_ratio
        cand.is_joint = rep_f.is_joint
        cand.filing_date = rep_f.submit_datetime[:10]
        cand.doc_id = rep_f.doc_id
        cand.doc_url = cfg.EDINET_VIEW_URL
        cand._acq_funds = rep_f.acq_funds       # type: ignore[attr-defined]
        cand._shares_held = rep_f.shares_held    # type: ignore[attr-defined]
        cand._bonus = bonus                      # type: ignore[attr-defined]
        candidates.append(cand)

    return candidates, exits, warnings


def build_candidates_from_codes(codes: list[str]) -> list[Candidate]:
    """--codes 指定時：EDINETを使わずダミーのアクティビスト情報で候補化（検証用）。"""
    out = []
    for code in codes:
        c = Candidate(code=code, name=f"(code {code})")
        c.fund = "テスト保有主体"
        c.is_known_activist = False
        c.holding_ratio = 0.06
        c._acq_funds = None       # type: ignore[attr-defined]
        c._shares_held = None     # type: ignore[attr-defined]
        c._bonus = 0              # type: ignore[attr-defined]
        out.append(c)
    return out


# ---------------------------------------------------------------------------
# 財務・株価・スコアの付与
# ---------------------------------------------------------------------------
def enrich_and_score(candidates: list[Candidate], conf, warnings: list[str]) -> None:
    th, w = conf.thresholds, conf.weights
    codes = [c.code for c in candidates]

    # J-Quants 財務
    fundamentals: dict = {}
    listed: dict = {}
    if conf.secrets.has_jquants and codes:
        try:
            from jquants import JQuantsClient
            jq = JQuantsClient(conf.secrets)
            jq.authenticate()
            listed = jq.listed_info()
            for code in codes:
                try:
                    fundamentals[code] = jq.fundamentals(code)
                except Exception as e:  # noqa: BLE001
                    warnings.append(f"J-Quants財務取得失敗 {code}: {e}")
        except Exception as e:  # noqa: BLE001
            warnings.append(f"J-Quants認証失敗: {e}")

    # 株価
    prices: dict = {}
    if codes:
        try:
            from prices import get_prices
            prices = get_prices(codes)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"株価取得失敗: {e}")

    for c in candidates:
        if c.code in fundamentals:
            c.fundamentals = fundamentals[c.code]
        info = listed.get(c.code, {})
        if info:
            c.name = info.get("CompanyName") or c.name
            c.market = info.get("MarketCodeName") or info.get("MarketCode") or c.market
        c.price = prices.get(c.code, PriceInfo())

        est, method = screen.estimate_acq_price(
            getattr(c, "_shares_held", None), getattr(c, "_acq_funds", None)
        )
        c.derived = screen.compute_derived(c.price, c.fundamentals, est, method)
        screen.score_candidate(c, w, th, known_bonus=getattr(c, "_bonus", 0))


# ---------------------------------------------------------------------------
# 出力
# ---------------------------------------------------------------------------
def write_outputs(conf, as_of: date, candidates: list[Candidate], exits, warnings) -> dict:
    generated_at = datetime.now(timezone.utc).isoformat()
    candidates.sort(key=lambda c: c.signal.score, reverse=True)
    out = build_output(
        generated_at=generated_at,
        as_of_date=as_of.isoformat(),
        params=conf.public_params(),
        candidates=candidates,
        activist_exits=exits,
        warnings=warnings,
    )
    cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    with open(cfg.DATA_DIR / "latest.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    with open(cfg.HISTORY_DIR / f"{as_of.isoformat()}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


def print_summary(out: dict) -> None:
    cands = out["candidates"]
    print(f"[summary] as_of={out['as_of_date']} candidates={len(cands)} "
          f"exits={len(out['activist_exits'])} warnings={len(out['warnings'])}")
    for c in cands[:15]:
        act = c["activist"]
        print(f"  [{c['signal']['score']:>3}] {c['status']:<9} {c['code']} {c['name']} "
              f"| {act['fund']} {(act['holding_ratio'] or 0) * 100:.1f}% "
              f"| PBR={_fmt(c['derived']['pbr'])}")
    for wmsg in out["warnings"][:10]:
        print("  ! " + wmsg)


def _fmt(x) -> str:
    return f"{x:.2f}" if isinstance(x, (int, float)) else "-"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="アクティビスト追随スクリーニング日次パイプライン")
    p.add_argument("--date", help="対象日 YYYY-MM-DD（既定: JSTの今日）")
    p.add_argument("--dry-run", action="store_true", help="書き込み/通知せず要約のみ")
    p.add_argument("--no-notify", action="store_true", help="Chatwork通知を抑止")
    p.add_argument("--codes", help="カンマ区切りコードのみ処理（EDINET不使用・検証用）")
    args = p.parse_args(argv)

    conf = load_config()
    known = load_known_activists()
    as_of = date.fromisoformat(args.date) if args.date else jst_today()
    warnings: list[str] = []
    exits: list[ActivistExit] = []

    if args.codes:
        candidates = build_candidates_from_codes([c.strip() for c in args.codes.split(",") if c.strip()])
    elif conf.secrets.has_edinet:
        candidates, exits, w = build_candidates_from_edinet(conf, known)
        warnings.extend(w)
    else:
        warnings.append("EDINET_API_KEY 未設定のため候補ゼロ（--codes で検証可能）")
        candidates = []

    enrich_and_score(candidates, conf, warnings)

    # 差分（前回スナップショット）
    previous = diffmod.load_previous(cfg.HISTORY_DIR, exclude_date=as_of.isoformat())
    diffmod.annotate_status(candidates, previous)

    if args.dry_run:
        out = build_output(
            generated_at=datetime.now(timezone.utc).isoformat(),
            as_of_date=as_of.isoformat(), params=conf.public_params(),
            candidates=sorted(candidates, key=lambda c: c.signal.score, reverse=True),
            activist_exits=exits, warnings=warnings,
        )
        print_summary(out)
        print("[dry-run] ファイル書き込み・通知は行いません")
        return 0

    out = write_outputs(conf, as_of, candidates, exits, warnings)
    print_summary(out)

    if not args.no_notify:
        from notify import build_message, post_chatwork
        nc = diffmod.new_or_changed(candidates)
        msg = build_message(as_of.isoformat(), nc, exits, conf.thresholds, DASHBOARD_URL)
        if msg:
            ok, detail = post_chatwork(conf.secrets, msg)
            print("[chatwork] " + detail)
        else:
            print("[chatwork] 通知対象なし")

    return 0


if __name__ == "__main__":
    sys.exit(main())
