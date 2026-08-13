"""アクティビスト追随戦略のバックテスト（オーケストレーター＋HTMLレポート生成）。

EDINETを過去 years 年遡って既知アクティビストの大量保有を集め、各対象銘柄の全期間
株価に対して simulate を走らせ、勝率・期待値・最大ドローダウンを算出して
docs/backtest.html に保存する。

実行: python backtest/backtest.py --years 3
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))

import config as cfg                      # noqa: E402
from config import load_config, load_known_activists  # noqa: E402
import edinet                             # noqa: E402
import screen                             # noqa: E402
import prices                             # noqa: E402
from simulate import Params, simulate_all, summarize, summarize_by_fund  # noqa: E402

REPORT_PATH = cfg.REPO_ROOT / "docs" / "backtest.html"
JST = timezone(timedelta(hours=9))


def collect_signals(api_key: str, years: int, known: list) -> tuple[list[dict], list[str]]:
    """過去 years 年の既知アクティビスト提出を (code,fund) 単位で最初の1件に集約。"""
    days = int(years * 365)
    filings, warnings = edinet.backfill_known_filings(
        api_key, datetime.now(JST).date(), days, known, screen.match_activist, sleep_sec=0.1)
    earliest: dict[tuple, dict] = {}
    for f in filings:
        if not f.sec_code:
            continue
        is_known, disp, _ = screen.match_activist(f.filer_name, known)
        fund = disp or f.filer_name
        key = (f.sec_code, fund)
        adate = (f.submit_datetime or "")[:10]
        if not adate:
            continue
        if key not in earliest or adate < earliest[key]["anchor_date"]:
            earliest[key] = {"code": f.sec_code, "fund": fund, "anchor_date": adate, "anchor_price": None}
    return list(earliest.values()), warnings


def attach_anchor_prices(signals: list[dict]) -> tuple[dict, list[str]]:
    """対象コードの全期間履歴を取得し、提出日終値をアンカーに設定。"""
    warnings: list[str] = []
    codes = sorted({s["code"] for s in signals})
    histories: dict[str, list] = {}
    for code in codes:
        try:
            histories[code] = prices.get_history_full(code)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"履歴取得失敗 {code}: {e}")
            histories[code] = []
    kept = []
    for s in signals:
        h = histories.get(s["code"]) or []
        pf = prices.price_on_or_before(h, s["anchor_date"]) if h else None
        if pf:
            s["anchor_price"] = pf["c"]
            kept.append(s)
    return {"histories": histories, "signals": kept}, warnings


# ---------------------------------------------------------------------------
# レポート
# ---------------------------------------------------------------------------
def _pct(x, d=1):
    return "—" if x is None else f"{x * 100:.{d}f}%"


def _svg_equity(curve: list[float]) -> str:
    if not curve or len(curve) < 2:
        return '<div class="empty">トレードが不足しています。</div>'
    W, H, padL, padR, padT, padB = 820, 260, 52, 20, 16, 24
    iw, ih = W - padL - padR, H - padT - padB
    lo, hi = min(curve), max(curve)
    span = (hi - lo) or 1
    x = lambda i: padL + i / (len(curve) - 1) * iw
    y = lambda v: padT + (1 - (v - lo) / span) * ih
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(curve))
    grid = ""
    for g in range(5):
        val = lo + span * g / 4
        yy = y(val)
        grid += f'<line x1="{padL}" y1="{yy:.1f}" x2="{padL+iw}" y2="{yy:.1f}" stroke="var(--border)"/>'
        grid += f'<text x="{padL-6}" y="{yy:.1f}" text-anchor="end" dominant-baseline="middle" font-size="10" fill="var(--text-muted)">{val:.2f}x</text>'
    base = y(1.0)
    return (f'<div class="chart-scroll"><svg viewBox="0 0 {W} {H}" width="100%">'
            f'{grid}'
            f'<line x1="{padL}" y1="{base:.1f}" x2="{padL+iw}" y2="{base:.1f}" stroke="var(--text-muted)" stroke-dasharray="4 4"/>'
            f'<polyline points="{pts}" fill="none" stroke="var(--accent)" stroke-width="2"/>'
            f'</svg></div>')


def _tile(k, v, sub=""):
    return f'<div class="tile"><div class="k">{k}</div><div class="v">{v}</div><div class="sub">{sub}</div></div>'


def build_report(base: dict, base_params: Params, sweep: list[dict],
                 by_fund: dict, period: str, warn_count: int) -> str:
    exp = base["expectancy"]
    exp_cls = "pl-pos" if (exp or 0) > 0 else "pl-neg"
    tiles = "".join([
        _tile("対象シグナル", base["signals"], "既知アクティビストの提出(重複除く)"),
        _tile("エントリー成立", base["entered"], f'内 決済済み {base["closed"]} / 保有中 {base["open"]}'),
        _tile("勝率", _pct(base["win_rate"]), "決済済みトレード"),
        _tile("期待値/トレード", f'<span class="{exp_cls}">{_pct(exp,2)}</span>', "コスト控除後"),
        _tile("平均利益 / 平均損失", f'{_pct(base["avg_win"])} / {_pct(base["avg_loss"])}', ""),
        _tile("プロフィットファクター", "—" if base["profit_factor"] is None else f'{base["profit_factor"]:.2f}', "総利益÷総損失"),
        _tile("累積リターン", _pct(base["total_return"]), "概念的資産曲線(1銘柄ずつ複利)"),
        _tile("最大ドローダウン", _pct(base["max_drawdown"]), "資産曲線の最大下落"),
    ])

    sweep_rows = "".join(
        f'<tr><td>{_pct(s["params"]["entry_threshold"],0)}</td><td>+{int(s["params"]["take_profit"]*100)}%</td>'
        f'<td>{s["closed"]}</td><td>{_pct(s["win_rate"])}</td>'
        f'<td class="{"pl-pos" if (s["expectancy"] or 0)>0 else "pl-neg"}">{_pct(s["expectancy"],2)}</td>'
        f'<td>{_pct(s["total_return"])}</td><td>{_pct(s["max_drawdown"])}</td></tr>'
        for s in sweep)

    fund_rows = "".join(
        f'<tr><td class="l">{fund}</td><td>{d["closed"]}</td><td>{_pct(d["win_rate"])}</td>'
        f'<td class="{"pl-pos" if (d["expectancy"] or 0)>0 else "pl-neg"}">{_pct(d["expectancy"],2)}</td></tr>'
        for fund, d in sorted(by_fund.items(), key=lambda kv: (kv[1]["closed"] or 0), reverse=True)
        if d["closed"])

    reasons = base.get("exit_reasons", {})
    reason_txt = " / ".join(f'{k}:{v}' for k, v in reasons.items()) or "—"
    p = base_params

    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>バックテスト | アクティビスト追随スクリーナー</title>
<link rel="stylesheet" href="./css/styles.css"/></head>
<body>
<header class="appbar"><div class="appbar-inner">
  <div class="brand"><span class="logo">🧪</span> 戦略バックテスト</div>
  <nav class="nav"><a href="index.html">候補一覧へ戻る</a></nav>
</div></header>
<main class="wrap">
  <div class="banner sample">⚠ <strong>これは過去データに基づく検証であり、将来の成績を保証しません。</strong>
    勝率だけでなく期待値・最大ドローダウン・コストを含めて判断してください。投資勧誘ではありません。</div>

  <div class="card">
    <h2>ベースライン戦略</h2>
    <p class="muted" style="font-size:.85rem">
      既知アクティビストの大量保有提出を起点に、<strong>提出後{p.entry_window}営業日以内に終値が提出時の株価×(1{'+' if p.entry_threshold>=0 else ''}{p.entry_threshold:.0%})以下</strong>になったら買い、
      <strong>+{p.take_profit:.0%}で利確 / {p.stop_loss:.0%}で損切り / {p.max_hold}営業日で時間切れ</strong>。往復コスト{p.cost:.1%}を控除。対象期間: {period}。
    </p>
    <section class="tiles">{tiles}</section>
    <div class="section-title">概念的な資産曲線（決済トレードをエグジット日順に1銘柄ずつ複利）</div>
    {_svg_equity(base["equity_curve"])}
    <p class="muted" style="font-size:.8rem">手仕舞い内訳: {reason_txt}（tp=利確 / sl=損切り / time=時間切れ）</p>
  </div>

  <div class="card">
    <h2>感応度（パラメータを変えた場合）</h2>
    <p class="muted" style="font-size:.82rem">損切りは-20%固定。※多数の組合せから良い数字を選ぶと<strong>過剰最適化</strong>になりがちなので、突出した1マスより全体の傾向を見てください。</p>
    <div class="table-scroll"><table>
      <thead><tr><th>エントリー閾値</th><th>利確</th><th>決済数</th><th>勝率</th><th>期待値/トレード</th><th>累積</th><th>最大DD</th></tr></thead>
      <tbody>{sweep_rows}</tbody></table></div>
  </div>

  <div class="card">
    <h2>ファンド別（ベースライン）</h2>
    <div class="table-scroll"><table>
      <thead><tr><th class="l">ファンド</th><th>決済数</th><th>勝率</th><th>期待値/トレード</th></tr></thead>
      <tbody>{fund_rows}</tbody></table></div>
  </div>

  <div class="banner info">
    <strong>この結果の限界（必ずお読みください）</strong><br>
    ・サンプル数が限られ、<strong>生存者バイアス</strong>（上場廃止・株価取得不可の銘柄は除外）があります。<br>
    ・エントリーは「トリガー当日の終値」で約定と仮定（実際は翌日始値・スリッページで差が出ます）。<br>
    ・PBR等の財務フィルタは<strong>提出時点の値ではない</strong>ため本検証には未使用。<br>
    ・{warn_count}件のデータ取得警告あり（一部銘柄の履歴欠損）。<br>
    ・<strong>過去の好成績は将来を保証しません。</strong>
  </div>

  <p class="footer">生成: {datetime.now(JST).strftime('%Y-%m-%d %H:%M')} JST ／ 本ツールは投資判断の補助であり投資勧誘ではありません。</p>
</main></body></html>"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="アクティビスト追随戦略バックテスト")
    p.add_argument("--years", type=float, default=3.0)
    args = p.parse_args(argv)

    conf = load_config()
    known = load_known_activists()
    if not conf.secrets.has_edinet:
        print("EDINET_API_KEY 未設定")
        return 1

    print(f"[backtest] 過去{args.years}年の既知アクティビスト提出を収集中...")
    signals, w1 = collect_signals(conf.secrets.edinet_api_key, args.years, known)
    print(f"[backtest] シグナル {len(signals)}件。株価履歴を取得中...")
    data, w2 = attach_anchor_prices(signals)
    signals, histories = data["signals"], data["histories"]
    warn_count = len(w1) + len(w2)
    print(f"[backtest] アンカー確定 {len(signals)}件。シミュレーション...")

    base_params = Params(entry_window=120, entry_threshold=0.0, take_profit=0.30,
                         stop_loss=-0.20, max_hold=250, cost=0.003)
    base_trades = simulate_all(signals, histories, base_params)
    base = summarize(base_trades)
    by_fund = summarize_by_fund(base_trades)

    sweep = []
    for th in (0.0, -0.05, -0.10):
        for tp in (0.20, 0.30, 0.40):
            pp = Params(entry_window=120, entry_threshold=th, take_profit=tp,
                        stop_loss=-0.20, max_hold=250, cost=0.003)
            s = summarize(simulate_all(signals, histories, pp))
            s["params"] = {"entry_threshold": th, "take_profit": tp}
            sweep.append(s)

    period = f"{args.years:.0f}年"
    html = build_report(base, base_params, sweep, by_fund, period, warn_count)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[backtest] 完了: signals={base['signals']} entered={base['entered']} "
          f"closed={base['closed']} win_rate={_pct(base['win_rate'])} "
          f"expectancy={_pct(base['expectancy'],2)} total={_pct(base['total_return'])} "
          f"maxDD={_pct(base['max_drawdown'])} warnings={warn_count}")
    print(f"[backtest] レポート: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
