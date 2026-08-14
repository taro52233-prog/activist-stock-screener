"""Chatwork 通知：新規/変化のあったロング候補とアクティビスト撤退を投稿。

Chatwork API v2: POST /rooms/{room_id}/messages  ヘッダ X-ChatWorkToken, body=フォーム。
1実行1メッセージなのでレート制限には十分収まる。非200は握って警告に載せる。
"""
from __future__ import annotations

from typing import Optional

import requests

from config import CHATWORK_MESSAGES, Secrets, Thresholds
from schema import ActivistExit, Candidate

_TIMEOUT = 20


def build_message(
    as_of_date: str,
    new_changed: list[Candidate],
    exits: list[ActivistExit],
    th: Thresholds,
    dashboard_url: str = "",
    paper_entries: Optional[list] = None,
    paper_exits: Optional[list] = None,
) -> Optional[str]:
    """通知本文を組み立てる。通知対象が無ければ None。"""
    paper_entries = paper_entries or []
    paper_exits = paper_exits or []
    notable = [c for c in new_changed if c.signal.score >= th.min_score_to_notify]
    if not notable and not exits and not paper_entries and not paper_exits:
        return None

    lines: list[str] = []
    lines.append("[info][title]アクティビスト追随スクリーニング " + as_of_date + "[/title]")

    if notable:
        notable.sort(key=lambda c: c.signal.score, reverse=True)
        lines.append(f"■ 新規/変化のあるロング候補（スコア{th.min_score_to_notify}以上） {len(notable)}件")
        for c in notable:
            tag = "🆕" if c.status == "NEW" else "🔄"
            pbr = f"PBR{c.derived.pbr:.2f}" if c.derived.pbr is not None else "PBR-"
            ratio = f"{c.holding_ratio * 100:.1f}%" if c.holding_ratio is not None else "-"
            lines.append(
                f"{tag} [{c.signal.score}] {c.code} {c.name}｜{c.fund} {ratio}｜{pbr}"
            )
            if c.signal.reasons_ja:
                lines.append("　" + " / ".join(c.signal.reasons_ja[:3]))

    if exits:
        lines.append("")
        lines.append(f"■ アクティビスト撤退の可能性 {len(exits)}件（出口検討）")
        for e in exits:
            pr = f"{e.prev_ratio * 100:.1f}%" if e.prev_ratio is not None else "-"
            nr = f"{e.new_ratio * 100:.1f}%" if e.new_ratio is not None else "-"
            lines.append(f"⚠ {e.code} {e.name}｜{e.fund} {pr}→{nr}")

    if paper_entries:
        lines.append("")
        lines.append(f"🟢 新規ペーパー買いシグナル {len(paper_entries)}件（紙上・実弾なし）")
        for t in paper_entries:
            dev = t.get("dev_at_entry")
            devtxt = f"提出時比{dev * 100:+.0f}%" if dev is not None else ""
            lines.append(f"　{t['code']} {t['name']}｜{t['fund']}｜{t['entry_price']:.0f}円 {devtxt}")

    if paper_exits:
        lines.append("")
        lines.append(f"🔴 ペーパー手仕舞い {len(paper_exits)}件")
        _rlabel = {"tp": "利確", "sl": "損切り", "time": "時間切れ"}
        for t in paper_exits:
            r = t.get("ret") or 0
            lines.append(f"　{t['code']} {t['name']}｜{_rlabel.get(t.get('exit_reason'), '')} {r * 100:+.1f}%")

    if dashboard_url:
        lines.append("")
        lines.append("ダッシュボード: " + dashboard_url)
    lines.append("[/info]")
    return "\n".join(lines)


def post_chatwork(secrets: Secrets, message: str) -> tuple[bool, str]:
    """Chatworkに投稿。成功可否とメッセージを返す。"""
    if not secrets.has_chatwork:
        return False, "Chatworkのシークレット未設定のため送信スキップ"
    url = CHATWORK_MESSAGES.format(room_id=secrets.chatwork_room_id)
    try:
        r = requests.post(
            url,
            headers={"X-ChatWorkToken": secrets.chatwork_token},
            data={"body": message},
            timeout=_TIMEOUT,
        )
        if r.status_code == 200:
            return True, "Chatwork送信成功"
        return False, f"Chatwork送信失敗 status={r.status_code}: {r.text[:200]}"
    except Exception as e:  # noqa: BLE001
        return False, f"Chatwork送信例外: {e}"
