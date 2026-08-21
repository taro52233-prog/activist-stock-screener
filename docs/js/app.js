/* 共有ユーティリティ：データ読み込み・整形・ウォッチリスト・ヘッダ描画 */
const DATA_URL = "./data/latest.json";
const LS_WATCH = "asc_watchlist";
const LS_POS = "asc_positions";
const LS_VWATCH = "asc_valuewatch";   // 監視リスト（日次取得対象にしたい任意コード）

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
const usdf = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
/* 通貨対応の価格表示（USD=$小数2桁 / JPY=整数円） */
function fmtMoney(x, currency) {
  if (x === null || x === undefined || isNaN(x)) return "—";
  return currency === "USD" ? "$" + usdf.format(x) : nf.format(Math.round(x)) + "円";
}
/* 通貨対応の大きな金額（時価総額など） */
function fmtBig(x, currency) {
  if (x === null || x === undefined || isNaN(x)) return "—";
  if (currency === "USD") {
    if (Math.abs(x) >= 1e12) return "$" + (x / 1e12).toFixed(2) + "T";
    if (Math.abs(x) >= 1e9) return "$" + (x / 1e9).toFixed(2) + "B";
    if (Math.abs(x) >= 1e6) return "$" + (x / 1e6).toFixed(1) + "M";
    return "$" + usdf.format(x);
  }
  return fmtYokuEn(x);
}
/* 英字ティッカー＝米国株 */
function isUsTicker(code) { return /^[A-Z]{1,5}(\.[A-Z]{1,2})?$/.test(normCode(code)); }

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

/* ---- 監視リスト（任意コードを日次取得対象に）----
   ブラウザ内（localStorage）に登録。実際の毎日取得に載せるには config/watchlist.txt へ反映が必要。 */
function normCode(x){ return String(x||"").replace(/[０-９]/g, d=>"0123456789"["０１２３４５６７８９".indexOf(d)]).trim().toUpperCase(); }
function getVWatch() { try { return JSON.parse(localStorage.getItem(LS_VWATCH) || "[]"); } catch { return []; } }
function isVWatched(code) { return getVWatch().includes(normCode(code)); }
function addVWatch(code) {
  code = normCode(code); if (!code) return getVWatch();
  const w = getVWatch(); if (!w.includes(code)) w.push(code);
  localStorage.setItem(LS_VWATCH, JSON.stringify(w)); return w;
}
function removeVWatch(code) {
  code = normCode(code);
  const w = getVWatch().filter(c => c !== code);
  localStorage.setItem(LS_VWATCH, JSON.stringify(w)); return w;
}

/* ---- GitHub連携（監視リストの自動反映）----
   オーナー本人のfine-grainedトークン(Contents:RW)をブラウザ内(localStorage)にだけ保存し、
   ブラウザから直接 config/watchlist.txt を更新する。トークンは他人からは見えない。 */
const LS_GH = "asc_gh_token";
const GH = { owner: "taro52233-prog", repo: "activist-stock-screener", branch: "main", path: "config/watchlist.txt" };
function getGhToken() { try { return localStorage.getItem(LS_GH) || ""; } catch { return ""; } }
function setGhToken(t) { try { localStorage.setItem(LS_GH, (t || "").trim()); } catch {} }
function clearGhToken() { try { localStorage.removeItem(LS_GH); } catch {} }
function ghConfigured() { return !!getGhToken(); }

function b64encodeUtf8(s) { return btoa(unescape(encodeURIComponent(s))); }
function b64decodeUtf8(s) { return decodeURIComponent(escape(atob((s || "").replace(/\n/g, "")))); }

async function ghApi(path, opts) {
  return fetch("https://api.github.com/" + path, Object.assign({}, opts, {
    headers: Object.assign({
      "Authorization": "Bearer " + getGhToken(),
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    }, (opts && opts.headers) || {}),
  }));
}

/* watchlist.txt の本文にコードを追加/削除（コメント行は保持） */
function applyWatchText(text, action, code) {
  code = normCode(code);
  const lines = text.split(/\r?\n/);
  const active = new Set();
  lines.forEach(l => { const t = l.split("#")[0].trim(); if (t) active.add(normCode(t)); });
  if (action === "add") {
    if (active.has(code)) return { text, changed: false };
    const sep = (text === "" || text.endsWith("\n")) ? "" : "\n";
    return { text: text + sep + `${code}   # アプリから登録\n`, changed: true };
  }
  if (!active.has(code)) return { text, changed: false };
  const kept = lines.filter(l => { const t = l.split("#")[0].trim(); return !(t && normCode(t) === code); });
  return { text: kept.join("\n"), changed: true };
}

/* GitHubの config/watchlist.txt を read-modify-write（409は1回だけ再取得して再適用） */
async function ghSyncWatch(action, code) {
  if (!ghConfigured()) return { ok: false, reason: "no-token" };
  const base = `repos/${GH.owner}/${GH.repo}/contents/${GH.path}`;
  let getR = await ghApi(base + `?ref=${GH.branch}`);
  if (getR.status === 401 || getR.status === 403) return { ok: false, reason: "auth", status: getR.status };
  let text = "", sha = undefined;
  if (getR.status === 200) { const j = await getR.json(); text = b64decodeUtf8(j.content); sha = j.sha; }
  else if (getR.status !== 404) return { ok: false, reason: "read", status: getR.status };
  for (let attempt = 0; attempt < 2; attempt++) {
    const { text: newText, changed } = applyWatchText(text, action, code);
    if (!changed) return { ok: true, changed: false };
    const body = { message: `chore: watchlist ${action} ${normCode(code)}（アプリ）`, content: b64encodeUtf8(newText), branch: GH.branch };
    if (sha) body.sha = sha;
    const putR = await ghApi(base, { method: "PUT", body: JSON.stringify(body) });
    if (putR.ok) return { ok: true, changed: true };
    if (putR.status === 409 && attempt === 0) {  // sha競合 → 最新を取り直して再適用
      const g2 = await ghApi(base + `?ref=${GH.branch}`); const j2 = await g2.json();
      text = b64decodeUtf8(j2.content); sha = j2.sha; continue;
    }
    return { ok: false, reason: "write", status: putR.status };
  }
  return { ok: false, reason: "conflict" };
}

/* UIから呼ぶ登録/解除：localStorageを更新し、トークンがあればGitHubにも自動反映 */
async function registerWatch(code) {
  addVWatch(code);
  if (ghConfigured()) return ghSyncWatch("add", code);
  return { ok: false, reason: "no-token" };
}
async function unregisterWatch(code) {
  removeVWatch(code);
  if (ghConfigured()) return ghSyncWatch("remove", code);
  return { ok: false, reason: "no-token" };
}
function ghResultMsg(r) {
  if (!r) return "";
  if (r.ok && r.changed) return "✅ GitHubに反映しました（翌営業日から自動取得）";
  if (r.ok && !r.changed) return "✅ 反映済み（変更なし）";
  if (r.reason === "no-token") return "ブラウザに保存（毎日取得に載せるには自動反映の設定を）";
  if (r.reason === "auth") return "⚠ トークンが無効/権限不足（Contents:RW・このリポジトリを許可）";
  return `⚠ 反映に失敗しました（${r.status || r.reason}）`;
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
