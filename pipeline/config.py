"""集中設定モジュール。

閾値・重み・APIエンドポイント・環境変数（シークレット）の読み込みをここに集約する。
すべての数値パラメータはここで調整でき、生成される latest.json の `params` にも書き出される。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ---------------------------------------------------------------------------
# パス
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "docs" / "data"
HISTORY_DIR = DATA_DIR / "history"
CONFIG_DIR = REPO_ROOT / "config"
KNOWN_ACTIVISTS_PATH = CONFIG_DIR / "known_activists.json"
WATCHLIST_PATH = CONFIG_DIR / "watchlist.txt"

# ---------------------------------------------------------------------------
# 外部APIエンドポイント
# ---------------------------------------------------------------------------
EDINET_BASE = "https://api.edinet-fsa.go.jp/api/v2"
EDINET_DOC_LIST = EDINET_BASE + "/documents.json"
EDINET_DOC_GET = EDINET_BASE + "/documents/{doc_id}"
# EDINET 書類閲覧のWeb URL（ダッシュボードのリンク用）
EDINET_VIEW_URL = "https://disclosure2.edinet-fsa.go.jp/WEEK0010.aspx"

# J-Quants は 2025/12 に V2 へ移行。認証は x-api-key ヘッダ方式（APIキーはダッシュボードで発行）。
# 無料プランで財務が取れるのは /fins/summary（/listed/info や /fins/statements は403）。
JQUANTS_BASE = "https://api.jquants.com/v2"
JQUANTS_SUMMARY = JQUANTS_BASE + "/fins/summary"

STOOQ_CSV = "https://stooq.com/q/d/l/?s={sym}&i=d"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"

CHATWORK_MESSAGES = "https://api.chatwork.com/v2/rooms/{room_id}/messages"

# 大量保有報告書の書類種別コード（EDINET API 仕様書 書類種別コード表）
#   350: 大量保有報告書
#   360: 変更報告書（大量保有）
#   370: 訂正大量保有報告書
#   380: 訂正報告書（変更報告書に対する訂正）
EDINET_DOCTYPE_HOLDING = {"350", "360", "370", "380"}
EDINET_DOCTYPE_BASE = {"350", "370"}      # 新規＋その訂正
EDINET_DOCTYPE_CHANGE = {"360", "380"}    # 変更＋その訂正


@dataclass
class Weights:
    """ロングシグナル合成スコアの重み（合計1.0想定）。"""
    activist: float = 0.30
    pbr: float = 0.25
    cash: float = 0.20
    payout: float = 0.15
    entry: float = 0.10


@dataclass
class Thresholds:
    """判定閾値。"""
    pbr_max: float = 1.0                 # PBRがこれ未満で合格
    pbr_full_score_at: float = 0.5       # PBRがこの値以下でサブスコア満点
    holding_min: float = 0.05            # 大量保有=5%
    net_cash_ratio_min: float = 0.20     # ネットキャッシュ/時価総額 の合格ライン
    net_cash_full_at: float = 0.50       # この比率でキャッシュ・サブスコア満点
    payout_max: float = 0.30             # 配当性向がこれ未満で「還元余地大」
    yield_max: float = 0.02              # 配当利回りがこれ未満で「伸びしろ」
    entry_deviation_max: float = 0.05    # 現値が推定取得単価+5%以内ならエントリー可
    loss_cut_pct: float = -0.20          # -20%で損切りライン
    min_score_to_notify: int = 60        # Chatwork通知する最低スコア
    lookback_business_days: int = 3      # EDINET書類のさかのぼり営業日数
    tracking_days: int = 180             # 大量保有提出から何日追跡し続けるか（約6ヶ月）
    max_tracked: int = 200               # 同時に追跡する最大銘柄数（API負荷の上限）


@dataclass
class PaperParams:
    """フォワード・ペーパー検証のルール（実弾なし）。"""
    entry_floor: float = -0.20    # 提出時比がこれ以上（暴落し切った銘柄は除外）
    entry_ceiling: float = 0.05   # 提出時比がこれ以下（プロの取得水準付近）でエントリー
    take_profit: float = 0.30     # +30%で利確
    stop_loss: float = -0.20      # -20%で損切り
    max_hold_days: int = 365      # 経過日数で時間切れ


@dataclass
class Secrets:
    edinet_api_key: str = ""
    jquants_api_key: str = ""
    jquants_mail: str = ""
    jquants_password: str = ""
    jquants_refresh_token: str = ""
    chatwork_token: str = ""
    chatwork_room_id: str = ""

    @property
    def has_edinet(self) -> bool:
        return bool(self.edinet_api_key)

    @property
    def has_jquants(self) -> bool:
        return bool(self.jquants_api_key)

    @property
    def has_chatwork(self) -> bool:
        return bool(self.chatwork_token and self.chatwork_room_id)


@dataclass
class Config:
    weights: Weights = field(default_factory=Weights)
    thresholds: Thresholds = field(default_factory=Thresholds)
    paper: PaperParams = field(default_factory=PaperParams)
    secrets: Secrets = field(default_factory=Secrets)

    def public_params(self) -> dict:
        """latest.json に埋め込む公開パラメータ（シークレットは含めない）。"""
        return {
            "weights": asdict(self.weights),
            "thresholds": asdict(self.thresholds),
            "paper": asdict(self.paper),
        }


def load_secrets_from_env() -> Secrets:
    return Secrets(
        edinet_api_key=os.environ.get("EDINET_API_KEY", "").strip(),
        jquants_api_key=os.environ.get("JQUANTS_API_KEY", "").strip(),
        jquants_mail=os.environ.get("JQUANTS_MAILADDRESS", "").strip(),
        jquants_password=os.environ.get("JQUANTS_PASSWORD", "").strip(),
        jquants_refresh_token=os.environ.get("JQUANTS_REFRESH_TOKEN", "").strip(),
        chatwork_token=os.environ.get("CHATWORK_API_TOKEN", "").strip(),
        chatwork_room_id=os.environ.get("CHATWORK_ROOM_ID", "").strip(),
    )


def load_config() -> Config:
    return Config(secrets=load_secrets_from_env())


def load_known_activists() -> list[dict]:
    """known_activists.json を読み込む。存在しなければ空リスト。"""
    if not KNOWN_ACTIVISTS_PATH.exists():
        return []
    with open(KNOWN_ACTIVISTS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("activists", [])


def load_watchlist() -> list[str]:
    """config/watchlist.txt を読み込み、監視銘柄コードの一覧を返す。

    1行1コード。# 以降と空行は無視。全角→半角化と重複排除も行う。
    アクティビスト大量保有が無い銘柄でも、ここに載せれば毎日
    株価・財務・チャートを取得し「バリュー参考」として表示する。
    """
    if not WATCHLIST_PATH.exists():
        return []
    seen: list[str] = []
    with open(WATCHLIST_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            code = line.translate(str.maketrans("０１２３４５６７８９", "0123456789")).strip().upper()
            if code and code not in seen:
                seen.append(code)
    return seen
