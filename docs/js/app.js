/* 共有ユーティリティ：データ読み込み・整形・ウォッチリスト・ヘッダ描画 */
const DATA_URL = "./data/latest.json";
const LS_WATCH = "asc_watchlist";
const LS_POS = "asc_positions";

/* ---- データ ---- */
async function loadData() {
  const res = await fetch(DATA_URL, { cache: "no-store" });
  if (!res.ok) throw new Error("data fetch failed: " + res.status);
  return res.json();
}

/* ---- 整形 ---- */
const nf = new Intl.NumberFormat("ja-JP");
function fmtNum(x) { return (x === null || x === undefined || isNaN(x)) ? "—" : nf.format(Math.round(x)); }
function fmtPrice(x) { return (x === null || x === undefined || isNaN(x)) ? "—" : nf.format(Math.round(x)) + "円"; }
function fmtPct(x, digits = 1) { return (x === null || x === undefined || isNaN(x)) ? "—" : (x * 100).toFixed(digits) + "%"; }
function fmt2(x) { return (x === null || x === undefined || isNaN(x)) ? "—" : Number(x).toFixed(2); }
function fmtYokuEn(x) {
  if (x === null || x === undefined || isNaN(x)) return "—";
  if (Math.abs(x) >= 1e12) return (x / 1e12).toFixed(2) + "兆円";
  if (Math.abs(x) >= 1e8) return (x / 1e8).toFixed(1) + "億円";
  return nf.format(Math.round(x)) + "円";
}

/* スコア→色 */
function scoreColor(s) {
  if (s >= 80) return "var(--good)";
  if (s >= 60) return "var(--accent)";
  if (s >= 40) return "var(--warn)";
  return "var(--text-muted)";
}
function scoreBadge(s) {
  return `<span class="badge score-badge" style="background:${scoreColor(s)}">${s}</span>`;
}
function statusChip(status) {
  if (status === "NEW") return `<span class="chip new">NEW</span>`;
  if (status === "CHANGED") return `<span class="chip changed">更新</span>`;
  return "";
}

/* ---- ウォッチリスト ---- */
function getWatch() { try { return JSON.parse(localStorage.getItem(LS_WATCH) || "[]"); } catch { return []; } }
function isWatched(code) { return getWatch().includes(code); }
function toggleWatch(code) {
  const w = getWatch();
  const i = w.indexOf(code);
  if (i >= 0) w.splice(i, 1); else w.push(code);
  localStorage.setItem(LS_WATCH, JSON.stringify(w));
  return w.includes(code);
}

/* ---- ポジション ---- */
function getPositions() { try { return JSON.parse(localStorage.getItem(LS_POS) || "[]"); } catch { return []; } }
function savePositions(list) { localStorage.setItem(LS_POS, JSON.stringify(list)); }

/* ---- ヘッダ ---- */
function renderHeader(active) {
  const links = [
    ["index.html", "候補一覧"],
    ["positions.html", "ポジション管理"],
    ["paper.html", "ペーパー検証"],
    ["backtest.html", "バックテスト"],
  ];
  const nav = links.map(([href, label]) =>
    `<a href="${href}" class="${active === href ? "active" : ""}">${label}</a>`).join("");
  const el = document.getElementById("appbar");
  if (el) el.innerHTML = `
    <div class="appbar-inner">
      <div class="brand"><span class="logo">📈</span> アクティビスト追随スクリーナー</div>
      <nav class="nav">${nav}</nav>
    </div>`;
}

function sampleBanner(data) {
  if (data && data.sample) {
    return `<div class="banner sample">⚠ 現在は<strong>サンプル（架空）データ</strong>を表示しています。GitHub Secrets を設定し日次パイプラインが実行されると実データに置き換わります。</div>`;
  }
  return "";
}
