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
def build_candidates_tracked(conf, known, filings, window_days) -> tuple[list[Candidate], dict, list[ActivistExit], list[str]]:
    """提出リストを永続ストアにマージし、追跡中の全銘柄を候補化する。"""
    import track
    th = conf.thresholds
    warnings: list[str] = []
    today = jst_today()

    store = track.load()
    exit_dicts = track.merge_filings(
        store, filings, known, today,
        screen.match_activist, screen.estimate_acq_price, th.holding_min,
    )
    track.expire(store, today, window_days)
    active = track.active_entries(store, th.max_tracked)

    exits = [ActivistExit(
        code=e["code"], name=e["name"], fund=e["fund"], prev_ratio=e.get("prev_ratio"),
        new_ratio=e.get("new_ratio"), filing_date=e.get("filing_date", ""),
        doc_id=e.get("doc_id", ""), doc_url=cfg.EDINET_VIEW_URL,
    ) for e in exit_dicts]

    candidates: list[Candidate] = []
    for e in active:
        c = Candidate(code=e["code"], name=e.get("name") or f"(code {e['code']})")
        c.fund = e["fund"]
        c.is_known_activist = bool(e.get("is_known"))
        c.holding_ratio = e.get("holding_ratio")
        c.prev_ratio = e.get("prev_ratio")
        if c.holding_ratio is not None and c.prev_ratio is not None:
            c.ratio_change = c.holding_ratio - c.prev_ratio
        c.is_joint = bool(e.get("is_joint"))
        c.filing_date = e.get("anchor_filing_date", "")
        c.doc_id = e.get("doc_id", "")
        c.doc_url = cfg.EDINET_VIEW_URL
        c._entry = e                                     # type: ignore[attr-defined]
        c._bonus = e.get("bonus", 0)                     # type: ignore[attr-defined]
        c._est_acq = e.get("est_acq_price")              # type: ignore[attr-defined]
        c._acq_method = e.get("acq_method", "none")      # type: ignore[attr-defined]
        c._edinet_shares_out = e.get("shares_out_edinet")  # type: ignore[attr-defined]
        candidates.append(c)

    print(f"[track] 追跡中 {len(active)}件（提出 {len(filings)}件を反映・窓 {window_days}日）")
    return candidates, store, exits, warnings


def build_candidates_from_codes(codes: list[str]) -> list[Candidate]:
    """--codes 指定時：EDINETを使わずダミーのアクティビスト情報で候補化（検証用）。"""
    out = []
    for code in codes:
        c = Candidate(code=code, name=f"(code {code})")
        c.fund = "テスト保有主体"
        c.is_known_activist = False
        c.holding_ratio = 0.06
        c._entry = None           # type: ignore[attr-defined]
        c._est_acq = None         # type: ignore[attr-defined]
        c._acq_method = "none"    # type: ignore[attr-defined]
        c._edinet_shares_out = None  # type: ignore[attr-defined]
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

    # 株価＋履歴
    ph: dict = {}
    if codes:
        try:
            from prices import get_prices_and_histories
            ph = get_prices_and_histories(codes)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"株価取得失敗: {e}")

    from prices import price_on_or_before, downsample

    for c in candidates:
        if c.code in fundamentals:
            c.fundamentals = fundamentals[c.code]
        info = listed.get(c.code, {})
        if info:
            c.name = info.get("CompanyName") or c.name
            c.market = info.get("MarketCodeName") or info.get("MarketCode") or c.market

        price_info, hist = ph.get(c.code, (PriceInfo(), []))
        c.price = price_info
        c.price_history = downsample(hist, 150)

        # EDINETから得た発行済株式数を、J-Quants欠損時のフォールバックに使う
        edinet_shares = getattr(c, "_edinet_shares_out", None)
        if c.fundamentals.shares_out is None and edinet_shares:
            c.fundamentals.shares_out = edinet_shares

        c.derived = screen.compute_derived(
            c.price, c.fundamentals, getattr(c, "_est_acq", None), getattr(c, "_acq_method", "none")
        )

        # 提出日の株価（アンカー）：初回に履歴から確定し、以後は固定
        entry = getattr(c, "_entry", None)
        anchor = entry.get("anchor_price") if entry else None
        if anchor is None:
            pf = price_on_or_before(hist, c.filing_date) if (hist and c.filing_date) else None
            anchor = pf["c"] if pf else (c.price.close if c.price.close is not None else None)
            if entry is not None:
                entry["anchor_price"] = anchor        # ストアに永続化（固定）
        if anchor:
            c.derived.price_at_filing = anchor
            if c.price.close is not None:
                c.derived.deviation_from_filing = (c.price.close - anchor) / anchor

        screen.score_candidate(c, w, th, known_bonus=getattr(c, "_bonus", 0), paper=conf.paper)


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
    p.add_argument("--backfill", type=int, metavar="DAYS",
                   help="過去DAYS日分の既知アクティビスト大量保有を遡って登録（初期化用・通知抑止）")
    args = p.parse_args(argv)

    import track
    conf = load_config()
    known = load_known_activists()
    as_of = date.fromisoformat(args.date) if args.date else jst_today()
    warnings: list[str] = []
    exits: list[ActivistExit] = []
    store: dict | None = None

    if args.codes:
        candidates = build_candidates_from_codes([c.strip() for c in args.codes.split(",") if c.strip()])
    elif conf.secrets.has_edinet:
        import edinet
        if args.backfill:
            args.no_notify = True   # 初期化時は大量通知を避ける
            filings, w = edinet.backfill_known_filings(
                conf.secrets.edinet_api_key, jst_today(), args.backfill, known, screen.match_activist)
            window = max(args.backfill, conf.thresholds.tracking_days)
        else:
            filings, w = edinet.collect_recent_filings(
                conf.secrets.edinet_api_key, jst_today(),
                conf.thresholds.lookback_business_days, fetch_bodies=True)
            window = conf.thresholds.tracking_days
        warnings.extend(w)
        candidates, store, exits, w2 = build_candidates_tracked(conf, known, filings, window)
        warnings.extend(w2)
    else:
        warnings.append("EDINET_API_KEY 未設定のため候補ゼロ（--codes で検証可能）")
        candidates = []

    enrich_and_score(candidates, conf, warnings)

    # 差分（前回スナップショット）
    previous = diffmod.load_previous(cfg.HISTORY_DIR, exclude_date=as_of.isoformat())
    diffmod.annotate_status(candidates, previous)

    # フォワード・ペーパー検証（実弾なし。--codes 検証時はスキップ）
    import paper as papermod
    paper_entries: list = []
    paper_exits: list = []
    pstore = papermod.load()
    if not args.codes:
        paper_entries, paper_exits = papermod.update(pstore, candidates, conf.paper, as_of.isoformat())
        print(f"[paper] 新規エントリー {len(paper_entries)} / 手仕舞い {len(paper_exits)} "
              f"（累積 {papermod.summarize(pstore)}）")

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
    if store is not None:
        track.save(store, datetime.now(timezone.utc).isoformat())
    papermod.save(pstore, datetime.now(timezone.utc).isoformat(), conf.paper)
    print_summary(out)

    if not args.no_notify:
        from notify import build_message, post_chatwork
        nc = diffmod.new_or_changed(candidates)
        msg = build_message(as_of.isoformat(), nc, exits, conf.thresholds, DASHBOARD_URL,
                            paper_entries=paper_entries, paper_exits=paper_exits)
        if msg:
            ok, detail = post_chatwork(conf.secrets, msg)
            print("[chatwork] " + detail)
        else:
            print("[chatwork] 通知対象なし")

    return 0


if __name__ == "__main__":
    sys.exit(main())
