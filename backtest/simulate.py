"""アクティビスト追随戦略のトレード・シミュレーション（純粋関数・ネット非依存）。

1シグナル（＝既知アクティビストの大量保有提出）ごとに:
  アンカー(提出日・提出日終値) → 提出後 entry_window 以内に
  「終値 ≤ アンカー×(1+entry_threshold)」で買い → TP/SL/時間切れ/データ終端で手仕舞い。

勝率だけでなく期待値・ドローダウンを見るための集計まで提供する。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, median
from typing import Optional


@dataclass
class Params:
    entry_window: int = 120        # 提出後この営業日数以内にエントリー試行
    entry_threshold: float = 0.0   # 終値 ≤ anchor×(1+threshold) で買い（0=提出時以下）
    take_profit: float = 0.30      # +30%で利確
    stop_loss: float = -0.20       # -20%で損切り
    max_hold: int = 250            # 最大保有営業日
    cost: float = 0.003            # 往復コスト（手数料＋スリッページ）


@dataclass
class Trade:
    code: str
    fund: str
    anchor_date: str
    anchor_price: float
    entered: bool = False
    entry_date: str = ""
    entry_price: float = 0.0
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = "no_entry"   # tp | sl | time | eod(open) | no_entry
    days_held: int = 0
    ret: float = 0.0                # コスト控除後リターン（未エントリーは0）

    @property
    def closed(self) -> bool:
        return self.exit_reason in ("tp", "sl", "time")


def _find_anchor_idx(history: list[dict], anchor_date: str) -> int:
    """anchor_date 以前で最も近いインデックス。無ければ0。"""
    idx = 0
    for i, p in enumerate(history):
        if p["d"] <= anchor_date:
            idx = i
        else:
            break
    return idx


def simulate_one(history: list[dict], code: str, fund: str,
                 anchor_date: str, anchor_price: float, p: Params) -> Trade:
    """1シグナルをシミュレート。history は {d,c} 昇順。"""
    t = Trade(code=code, fund=fund, anchor_date=anchor_date, anchor_price=anchor_price)
    if not history or not anchor_price:
        return t
    a = _find_anchor_idx(history, anchor_date)

    # --- エントリー探索 ---
    entry_i = None
    limit = min(a + 1 + p.entry_window, len(history))
    trigger = anchor_price * (1 + p.entry_threshold)
    for i in range(a + 1, limit):
        if history[i]["c"] <= trigger:
            entry_i = i
            break
    if entry_i is None:
        return t   # no_entry

    t.entered = True
    t.entry_date = history[entry_i]["d"]
    t.entry_price = history[entry_i]["c"]
    ep = t.entry_price
    tp_px = ep * (1 + p.take_profit)
    sl_px = ep * (1 + p.stop_loss)

    # --- エグジット探索 ---
    end = min(entry_i + 1 + p.max_hold, len(history))
    exit_i, reason = None, None
    for j in range(entry_i + 1, end):
        c = history[j]["c"]
        if c <= sl_px:
            exit_i, reason = j, "sl"; break
        if c >= tp_px:
            exit_i, reason = j, "tp"; break
    if exit_i is None:
        # 時間切れ or データ終端
        last = min(entry_i + p.max_hold, len(history) - 1)
        exit_i = last
        reason = "time" if (entry_i + p.max_hold) < len(history) else "eod"

    t.exit_date = history[exit_i]["d"]
    t.exit_price = history[exit_i]["c"]
    t.exit_reason = reason
    t.days_held = exit_i - entry_i
    t.ret = (t.exit_price / ep - 1.0) - p.cost
    return t


def simulate_all(signals: list[dict], histories: dict, p: Params) -> list[Trade]:
    """signals: [{code,fund,anchor_date,anchor_price}], histories: {code: [{d,c}]}"""
    trades = []
    for s in signals:
        hist = histories.get(s["code"]) or []
        trades.append(simulate_one(hist, s["code"], s["fund"],
                                    s["anchor_date"], s["anchor_price"], p))
    return trades


# ---------------------------------------------------------------------------
# 集計
# ---------------------------------------------------------------------------
def _max_drawdown(equity: list[float]) -> float:
    peak = equity[0] if equity else 1.0
    mdd = 0.0
    for v in equity:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return mdd


# 分割・データ異常の除外閾値：エグジット設計(TP+40%/SL-25%)を大きく超える実現損益は
# 未調整の株式分割や誤った価格行に由来する可能性が高いため異常として除外する。
ANOM_HI = 1.0    # +100%超は異常（分割による見かけ上の急騰など）
ANOM_LO = -0.6   # -60%未満は異常（分割・誤値）


def summarize(trades: list[Trade], bet_fraction: float = 0.2) -> dict:
    """closed（TP/SL/時間切れ）トレードで勝率・期待値・DD等を集計。

    分割/データ異常（|ret|が極端）を除外し、資産曲線は資金の一定割合(bet_fraction)
    ずつ賭ける前提で複利計算（1トレードで資金が尽きない・符号破綻しない）。
    """
    closed_all = [t for t in trades if t.closed]
    entered = [t for t in trades if t.entered]
    open_trades = [t for t in entered if t.exit_reason == "eod"]
    no_entry = [t for t in trades if not t.entered]

    closed = [t for t in closed_all if ANOM_LO <= t.ret <= ANOM_HI]
    anomalies = len(closed_all) - len(closed)

    rets = [t.ret for t in closed]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]

    res = {
        "signals": len(trades),
        "entered": len(entered),
        "closed": len(closed),
        "anomalies": anomalies,
        "open": len(open_trades),
        "no_entry": len(no_entry),
        "win_rate": (len(wins) / len(closed)) if closed else None,
        "avg_win": mean(wins) if wins else None,
        "avg_loss": mean(losses) if losses else None,
        "expectancy": mean(rets) if rets else None,
        "median_ret": median(rets) if rets else None,
        "profit_factor": (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else None,
        "best": max(rets) if rets else None,
        "worst": min(rets) if rets else None,
    }

    # 資産曲線：エグジット日順に、資金の bet_fraction ずつ賭けて複利（符号破綻しない）
    curve = [1.0]
    for t in sorted(closed, key=lambda x: x.exit_date):
        curve.append(curve[-1] * (1 + bet_fraction * t.ret))
    res["bet_fraction"] = bet_fraction
    res["total_return"] = (curve[-1] - 1.0) if len(curve) > 1 else None
    res["max_drawdown"] = _max_drawdown(curve) if len(curve) > 1 else None
    res["equity_curve"] = curve

    # 手仕舞い理由の内訳
    reasons: dict[str, int] = {}
    for t in closed:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
    res["exit_reasons"] = reasons
    return res


def summarize_by_fund(trades: list[Trade]) -> dict:
    by: dict[str, list] = {}
    for t in trades:
        by.setdefault(t.fund, []).append(t)
    return {fund: summarize(ts) for fund, ts in by.items()}
