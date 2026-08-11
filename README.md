# 📈 アクティビスト追随スクリーナー

日本株の「アクティビスト追随（ライド・アロング）戦略」を **毎日自動でスクリーニングし、ロング（買い）のタイミングをダッシュボードで可視化**するツールです。

- **完全無料構成**（EDINET・J-Quants無料枠・Stooq/Yahoo・GitHub Actions・GitHub Pages）
- **AIの推論ではなく実データ＋ルールベース判定**（ハルシネーションを排除）
- **毎朝自動更新**（GitHub Actions cron）→ 新シグナルは **Chatwork通知**
- **ポジション管理**（-20%損切り／アクティビスト撤退の出口シグナル）

> ⚠ 本ツールは投資判断の補助情報を提供するものであり、投資勧誘・投資助言ではありません。最終判断はご自身の責任で行ってください。

---

## 戦略の考え方

エフィッシモ・オアシス・村上系・ダルトン・シルチェスター等の著名アクティビストが **5%以上の大量保有報告書** を出した銘柄のうち、次の「4つの財務フィルター」を満たすものを狙います。

1. **PBR < 1倍**（資産価値に対して割安）
2. **キャッシュリッチ**（ネットキャッシュ／余剰資金が潤沢）
3. **低い配当性向**（増配・自社株買いの余地が大きい）
4. **低い配当利回り**（還元の伸びしろがある）

さらに **現在値がアクティビストの推定取得単価と同水準〜それ以下** のタイミングでエントリーすることで、「プロが負けられない戦い」をしている水準で一緒に仕込みます。出口は **-20%の損切り**、または **アクティビストが5%を割った（撤退）** ら手仕舞いを検討します。

---

## 仕組み（アーキテクチャ）

```
毎朝07:00 JST  GitHub Actions (.github/workflows/daily.yml)
   └ python pipeline/run.py
        EDINET API      → 直近営業日の大量保有報告書を取得・パース
        J-Quants API    → 純資産/発行済株式数/配当 などの財務
        Stooq / Yahoo   → 日次終値（現在に近い株価）
        screen.py       → PBR・利回り・NC比率・取得単価乖離を計算 → 4フィルター＋スコア
        diff.py         → 前回との差分（NEW/CHANGED/撤退）
        → docs/data/latest.json を生成・コミット
        notify.py       → 新シグナルがあれば Chatwork へ投稿
   └ GitHub Pages が docs/ を配信 → ブラウザがダッシュボードを表示
```

- **データソースの使い分け**: 大量保有報告書（EDINET）は提出即日で反映。J-Quants無料枠は株価が約12週間遅延するため**財務のみ**に使い、**株価は日次終値（Stooq/Yahoo）**を併用してPBR・利回りを自前で再計算します。

---

## セットアップ手順

### 1. GitHub Pages を有効化
リポジトリ **Settings → Pages** で、Source を **Deploy from a branch**、Branch を **`main` / `/docs`** に設定します。
数分後に `https://<ユーザー名>.github.io/activist-stock-screener/` で公開されます。

### 2. Actions の書き込み権限
**Settings → Actions → General → Workflow permissions** を **Read and write permissions** にします（データの自動コミットに必要）。

### 3. 各種APIキーの取得

| シークレット名 | 取得先 | 備考 |
|---|---|---|
| `EDINET_API_KEY` | [EDINET API](https://api.edinet-fsa.go.jp/) のマイページで発行 | 大量保有報告書の取得（無料） |
| `JQUANTS_MAILADDRESS` / `JQUANTS_PASSWORD` | [J-Quants](https://jpx-jquants.com/) 無料プラン登録 | 財務データ。※`JQUANTS_REFRESH_TOKEN` を代わりに登録してもよい |
| `CHATWORK_API_TOKEN` | Chatwork → サービス連携 → APIトークン | 通知用 |
| `CHATWORK_ROOM_ID` | 通知したいチャットのURL末尾の数字 | 例: `https://www.chatwork.com/#!rid123456789` の `123456789` |

### 4. GitHub Secrets に登録
**Settings → Secrets and variables → Actions → New repository secret** で上記を登録します。

### 5. 動作確認
**Actions タブ → daily-screening → Run workflow** で手動実行。成功すると `docs/data/latest.json` が更新され、Chatworkに通知が届きます。以後は毎朝07:00 JST（平日）に自動実行されます。

> 💡 シークレット未設定でも、同梱のサンプルデータでダッシュボードの見た目を確認できます。

---

## ローカルでの実行・検証

```bash
pip install -r pipeline/requirements.txt

# 決定論コアのテスト（ネットワーク不要）
pip install pytest && python -m pytest tests/ -q

# サンプルデータ生成（ダッシュボード表示確認用・架空データ）
python pipeline/make_sample.py

# 本番パイプライン（要シークレットを環境変数に設定）
export EDINET_API_KEY=...  JQUANTS_MAILADDRESS=...  JQUANTS_PASSWORD=...
python pipeline/run.py --dry-run          # 書き込み・通知せず要約のみ
python pipeline/run.py --codes 7203,6758  # EDINET不使用・指定コードのみ（検証用）

# ダッシュボードをローカル表示
cd docs && python -m http.server 8000     # → http://localhost:8000/
```

---

## 調整できる項目

- **判定閾値・スコア重み**: `pipeline/config.py` の `Thresholds` / `Weights`（PBR上限、ネットキャッシュ比率、配当性向、損切り%、通知スコア閾値など）。
- **追跡するアクティビスト**: `config/known_activists.json`（別名・加点を自由に追加・編集）。
- **実行スケジュール**: `.github/workflows/daily.yml` の cron。

---

## リポジトリ構成

```
pipeline/   Python日次パイプライン（EDINET/J-Quants/株価/判定/差分/通知）
config/     known_activists.json（既知アクティビスト一覧）
docs/       GitHub Pages公開サイト（index/stock/positions + data/latest.json）
tests/      決定論コアのオフライン単体テスト
.github/workflows/daily.yml   毎日自動実行
```

---

## 注意事項・既知の制約

- **EDINETのパース**は大量保有報告書のCSV（XBRL由来）を項目名ベースで抽出しています。タクソノミ差異により一部項目（取得単価等）が取れない場合があり、その際は推定または欠損表示になります。
- **J-Quants無料枠は約12週間遅延**（財務は四半期更新のため許容）。株価は別ソースで最新化しています。
- **Stooq** はアクセス制限がありうるため Yahoo Finance へ自動フォールバックします。
- **ポジション情報はブラウザのlocalStorage** に保存され端末依存です。ポジション画面の「バックアップ書き出し／読み込み」でJSON保存してください。
