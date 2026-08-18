/* 個別銘柄詳細ページ：SVGで価格チャート（大量保有 提出日の縦線＋取得時水準の横線＋現在値）を描画 */
function qs(name){ return new URLSearchParams(location.search).get(name); }

(async () => {
  renderHeader("");
  const code = qs("code");
  const root = document.getElementById("content");
  let data;
  try { data = await loadData(); }
  catch(err){ root.innerHTML = `<div class="banner info">データを読み込めませんでした（${err.message}）</div>`; return; }

  const c = (data.candidates || []).find(x => x.code === code);
  document.getElementById("banner").innerHTML = sampleBanner(data);
  if (!c){ root.innerHTML = `<div class="empty">コード ${code || "(未指定)"} の銘柄が見つかりません。<br><a href="index.html">← 候補一覧へ戻る</a></div>`; return; }

  const d = c.derived, f = c.fundamentals, a = c.activist;
  const watched = isWatched(c.code);
  const pf = d.price_at_filing;           // 提出日の株価
  const dev = d.deviation_from_filing;    // 現在との差分
  const daysTracked = (a.filing_date && data.as_of_date)
    ? Math.max(0, Math.round((new Date(data.as_of_date) - new Date(a.filing_date)) / 86400000)) : null;
  const devTxt = dev==null ? "—"
    : `<span class="${dev<=0?'pl-pos':'pl-neg'}">${dev>=0?'+':''}${fmtPct(dev)}</span>`;
  const devNote = dev==null ? "" : (dev<=0
    ? "（提出時より<strong>安い</strong>＝プロと同水準以下で仕込める）"
    : "（提出時より高い）");

  // --- トレードプラン（買いゾーン／利確／損切り） ---
  const pp = (data.params && data.params.paper) ||
    { entry_floor:-0.20, entry_ceiling:0.05, take_profit:0.30, stop_loss:-0.20, max_hold_days:365 };
  const anchor = pf;
  const cur = c.price.close;
  const band = anchor!=null ? { lo: anchor*(1+pp.entry_floor), hi: anchor*(1+pp.entry_ceiling) } : null;
  const tpPrice = anchor!=null ? anchor*(1+pp.take_profit) : null;
  const slPrice = anchor!=null ? anchor*(1+pp.stop_loss) : null;
  const plan = { band, tpPrice, slPrice };
  let verdict="—", vcls="banner info", vnote="";
  if (band && cur!=null){
    if (cur < band.lo){ verdict="⚠ 買いゾーンを下抜け（-20%超）"; vcls="banner sample";
      vnote="損切り水準を割れています。押し目ではなく下落トレンドの可能性。基本は見送り。"; }
    else if (cur > band.hi){ verdict="⏳ まだ高い（押し目待ち）"; vcls="banner info";
      vnote=`提出時＋${(pp.entry_ceiling*100).toFixed(0)}%より上。${fmtPrice(band.hi)} 以下まで下がるのを待つのが基本。`; }
    else { verdict="✅ 今が買いゾーン"; vcls="banner";
      vnote="アクティビストの取得水準付近。戦略上のエントリー好機（あくまで検証中のルール）。"; }
  }
  const paperTrade = await findPaperTrade(c.code);

  root.innerHTML = `
    <a href="index.html" class="muted">← 候補一覧へ戻る</a>
    <div class="detail-head" style="margin-top:8px">
      <span class="code">${c.code}</span>
      <h1>${c.name}</h1>
      ${scoreBadge(c.signal.score)}
      ${a.is_known ? '<span class="chip known">既知アクティビスト</span>' : ''}
      ${statusChip(c.status)}
      <span class="star ${watched?'on':''}" id="starBtn" title="ウォッチリスト">${watched?'★':'☆'}</span>
      <span class="muted">${c.market || ''}</span>
    </div>

    <div class="card">
      <h2>株価チャートと大量保有のタイミング</h2>
      <div class="filing-summary">
        <div class="fs-item"><div class="k">大量保有 提出日</div><div class="v">${a.filing_date||'—'}${daysTracked!=null?` <span class="muted" style="font-size:.7rem">(${daysTracked}日前)</span>`:''}</div></div>
        <div class="fs-item"><div class="k">提出日の株価</div><div class="v">${fmtPrice(pf)}</div></div>
        <div class="fs-item"><div class="k">現在値</div><div class="v">${fmtPrice(c.price.close)}</div></div>
        <div class="fs-item"><div class="k">提出時との差</div><div class="v">${devTxt}</div></div>
      </div>
      <p class="muted" style="font-size:.85rem;margin:2px 0 12px">${dev==null?'':`現在は提出時の株価に対して ${devTxt} の位置にあります ${devNote}`}</p>
      <div id="chart"></div>
      <div class="legend">
        <span class="lg"><span class="sw" style="background:var(--accent)"></span>株価</span>
        <span class="lg"><span class="sw" style="background:var(--good);opacity:.35"></span>買いゾーン</span>
        <span class="lg"><span class="sw dash" style="background:var(--good)"></span>利確+30%</span>
        <span class="lg"><span class="sw dash" style="background:var(--warn)"></span>提出日</span>
        <span class="lg"><span class="sw dash" style="background:var(--bad)"></span>損切り-20%</span>
      </div>
    </div>

    <div class="card">
      <h2>📋 トレードプラン（この戦略のルール）</h2>
      <div class="${vcls}">現在の判定: <strong>${verdict}</strong>${vnote?` — ${vnote}`:''}</div>
      <div class="metrics">
        ${metric("買い時スコア", `<span style="color:${buyScoreColor(c.signal.buy_score||0)}">${c.signal.buy_score||0}</span><span class="muted" style="font-size:.6rem"> /100</span>`)}
        ${metric("買いゾーン", band? `${fmtPrice(band.lo)}〜${fmtPrice(band.hi)}` : '—')}
        ${metric("利確目標 (+30%)", `<span class="pl-pos">${fmtPrice(tpPrice)}</span>`)}
        ${metric("損切り (-20%)", `<span class="pl-neg">${fmtPrice(slPrice)}</span>`)}
        ${metric("現在値", fmtPrice(cur))}
        ${metric("想定保有", `〜${pp.max_hold_days}日`)}
        ${metric("ペーパー状況", paperTrade ? paperStatusLabel(paperTrade) : '未エントリー')}
      </div>
      <p class="muted" style="font-size:.8rem;margin-top:10px">
        考え方: アクティビストの取得水準付近（<strong>買いゾーン</strong>）で買い、<strong>+30%で利確</strong>／<strong>-20%で損切り</strong>／最長${pp.max_hold_days}日。
        参考成績はバックテストで勝率≈70%・期待値≈+12%だが、<strong>生存者バイアス等で楽観的な可能性</strong>があり
        <a href="paper.html">ペーパー検証</a>で実地確認中。<a href="backtest.html">検証の詳細と限界はこちら</a>。実弾の売買ではありません。
      </p>
    </div>

    <div class="card">
      <h2>判定サマリー（スコア ${c.signal.score}/100）</h2>
      <div style="margin-bottom:10px">
        ${filterChip("アクティビスト", c.signal.filters.activist)}
        ${filterChip("PBR<1", c.signal.filters.pbr_lt_1)}
        ${filterChip("キャッシュリッチ", c.signal.filters.cash_rich)}
        ${filterChip("還元余地", c.signal.filters.low_payout)}
        ${filterChip("エントリー可", c.signal.filters.entry_ok)}
      </div>
      ${subScoreBars(c.signal.subscores || {})}
      <ul class="reasons" style="margin-top:12px">${(c.signal.reasons_ja||[]).map(r=>`<li>${r}</li>`).join("") || '<li class="muted" style="background:none;border:none">該当理由なし</li>'}</ul>
    </div>

    <div class="card">
      <h2>アクティビスト情報</h2>
      <dl class="kv">
        <dt>ファンド</dt><dd>${a.fund||'—'} ${a.is_joint?'<span class="chip">共同保有</span>':''}</dd>
        <dt>保有割合</dt><dd>${fmtPct(a.holding_ratio)} ${a.prev_ratio!=null?`（前回 ${fmtPct(a.prev_ratio)}／変化 ${a.ratio_change!=null?(a.ratio_change>=0?'+':'')+fmtPct(a.ratio_change):'—'}）`:''}</dd>
        <dt>提出日</dt><dd>${a.filing_date||'—'}</dd>
        <dt>推定取得単価</dt><dd>${fmtPrice(d.est_acq_price)} <span class="muted">（${acqMethod(d.acq_price_method)}）</span></dd>
        <dt>EDINET</dt><dd>${a.doc_id?`<a href="${a.doc_url}" target="_blank" rel="noopener">書類を見る（${a.doc_id}）</a>`:'—'}</dd>
      </dl>
    </div>

    <div class="card">
      <h2>財務・派生指標</h2>
      <div class="metrics">
        ${metric("PBR", fmt2(d.pbr))}
        ${metric("配当利回り", fmtPct(d.dividend_yield))}
        ${metric("配当性向", fmtPct(d.payout_ratio))}
        ${metric("時価総額", fmtYokuEn(d.market_cap))}
        ${metric("ネットキャッシュ", fmtYokuEn(d.net_cash))}
        ${metric("NC/時価総額", fmtPct(d.net_cash_to_mktcap))}
        ${metric("純資産", fmtYokuEn(f.equity))}
        ${metric("1株純資産(BPS)", f.bps!=null?fmtPrice(f.bps):'—')}
        ${metric("1株利益(EPS)", f.eps!=null?fmtPrice(f.eps):'—')}
        ${metric("実績DPS", f.dps_result!=null?fmtPrice(f.dps_result):'—')}
      </div>
      <p class="muted" style="font-size:.8rem;margin-top:10px">
        財務は開示日 ${f.statement_date||'—'} 時点${f.jquants_stale?'（J-Quants無料枠のため最大約12週遅延）':''}。PBR・利回りは最新終値で再計算。
      </p>
    </div>
  `;

  document.getElementById("starBtn").addEventListener("click", (e)=>{
    const on = toggleWatch(c.code); e.target.textContent = on?'★':'☆'; e.target.classList.toggle('on', on);
  });

  document.getElementById("chart").innerHTML = buildPriceChart(c, plan);
})();

/* ペーパー検証の該当トレードを探す */
async function findPaperTrade(code){
  try {
    const r = await fetch("./data/paper.json", { cache: "no-store" });
    if (!r.ok) return null;
    const j = await r.json();
    const ts = (j.trades || []).filter(t => t.code === code);
    return ts.find(t => t.status === "open") || ts[0] || null;
  } catch { return null; }
}
function paperStatusLabel(t){
  if (t.status === "open"){
    const pl = t.ret==null ? "" : ` ${t.ret>=0?'+':''}${fmtPct(t.ret)}`;
    return `<span class="chip ok">仮保有中</span>${pl}`;
  }
  const rl = { tp:"利確", sl:"損切り", time:"時間切れ" }[t.exit_reason] || "決済";
  return `<span class="chip">${rl}</span> ${(t.ret||0)>=0?'+':''}${fmtPct(t.ret)}`;
}

/* ---- SVG 価格チャート ---- */
function buildPriceChart(c, plan){
  const hist = c.price_history || [];
  if (hist.length < 2) return `<div class="empty">価格履歴が取得できませんでした（新規上場・低流動性の銘柄など）。</div>`;

  const W = 820, H = 320, padL = 58, padR = 96, padT = 16, padB = 26;
  const iw = W - padL - padR, ih = H - padT - padB;
  const closes = hist.map(p => p.c);
  const pf = c.derived.price_at_filing;
  const filingDate = c.activist.filing_date;
  const band = plan && plan.band;
  const tpPrice = plan && plan.tpPrice;
  const lossCut = (plan && plan.slPrice != null) ? plan.slPrice : (pf != null ? pf * 0.8 : null);

  let lo = Math.min(...closes), hi = Math.max(...closes);
  if (pf != null){ lo = Math.min(lo, pf); hi = Math.max(hi, pf); }
  if (lossCut != null) lo = Math.min(lo, lossCut);
  if (tpPrice != null){ hi = Math.max(hi, tpPrice); }
  if (band){ lo = Math.min(lo, band.lo); hi = Math.max(hi, band.hi); }
  const pad = (hi - lo) * 0.08 || hi * 0.05 || 1;
  lo -= pad; hi += pad;

  const x = i => padL + (i / (hist.length - 1)) * iw;
  const y = v => padT + (1 - (v - lo) / (hi - lo)) * ih;

  // 買いゾーン(帯)を背景に描画
  let bg = "";
  if (band){
    const yhi = y(band.hi), ylo = y(band.lo);
    bg += `<rect x="${padL}" y="${yhi.toFixed(1)}" width="${iw}" height="${Math.max(0,ylo-yhi).toFixed(1)}" fill="var(--good)" opacity="0.12"/>`;
    bg += `<text x="${padL+6}" y="${(yhi+13).toFixed(1)}" font-size="10" fill="var(--good)">買いゾーン</text>`;
  }

  // 提出日に最も近いインデックス
  let fi = -1;
  if (filingDate){
    for (let i = 0; i < hist.length; i++){ if (hist[i].d <= filingDate) fi = i; else break; }
  }

  const linePts = hist.map((p, i) => `${x(i).toFixed(1)},${y(p.c).toFixed(1)}`).join(" ");
  const areaPts = `${padL},${(padT+ih).toFixed(1)} ${linePts} ${(padL+iw).toFixed(1)},${(padT+ih).toFixed(1)}`;

  // Yグリッド（4本）
  let grid = "";
  for (let g = 0; g <= 4; g++){
    const val = lo + (hi - lo) * g / 4;
    const yy = y(val);
    grid += `<line x1="${padL}" y1="${yy.toFixed(1)}" x2="${padL+iw}" y2="${yy.toFixed(1)}" stroke="var(--border)" stroke-width="1"/>`;
    grid += `<text x="${padL-8}" y="${yy.toFixed(1)}" text-anchor="end" dominant-baseline="middle" font-size="11" fill="var(--text-muted)">${Math.round(val).toLocaleString()}</text>`;
  }

  // X軸ラベル（最初・提出日・最後）
  let xlab = "";
  const mkX = (i, txt, anchor) => `<text x="${x(i).toFixed(1)}" y="${H-8}" text-anchor="${anchor}" font-size="11" fill="var(--text-muted)">${txt}</text>`;
  if (hist.length){
    xlab += mkX(0, hist[0].d.slice(0,7), "start");
    xlab += mkX(hist.length-1, hist[hist.length-1].d.slice(0,7), "end");
  }

  // 提出日の横線・縦線
  let markers = "";
  if (pf != null){
    const yl = y(pf);
    markers += `<line x1="${padL}" y1="${yl.toFixed(1)}" x2="${padL+iw}" y2="${yl.toFixed(1)}" stroke="var(--text-muted)" stroke-width="1.5" stroke-dasharray="5 4"/>`;
    markers += `<text x="${padL+iw+6}" y="${yl.toFixed(1)}" dominant-baseline="middle" font-size="11" fill="var(--text-muted)">取得時 ${Math.round(pf).toLocaleString()}</text>`;
  }
  if (lossCut != null){
    const yc = y(lossCut);
    markers += `<line x1="${padL}" y1="${yc.toFixed(1)}" x2="${padL+iw}" y2="${yc.toFixed(1)}" stroke="var(--bad)" stroke-width="1.2" stroke-dasharray="3 4" opacity="0.8"/>`;
    markers += `<text x="${padL+iw+6}" y="${yc.toFixed(1)}" dominant-baseline="middle" font-size="10" fill="var(--bad)">損切り ${Math.round(lossCut).toLocaleString()}</text>`;
  }
  if (tpPrice != null){
    const yt = y(tpPrice);
    markers += `<line x1="${padL}" y1="${yt.toFixed(1)}" x2="${padL+iw}" y2="${yt.toFixed(1)}" stroke="var(--good)" stroke-width="1.5" stroke-dasharray="6 4"/>`;
    markers += `<text x="${padL+iw+6}" y="${yt.toFixed(1)}" dominant-baseline="middle" font-size="10" fill="var(--good)">利確 ${Math.round(tpPrice).toLocaleString()}</text>`;
  }
  if (fi >= 0){
    const xf = x(fi);
    markers += `<line x1="${xf.toFixed(1)}" y1="${padT}" x2="${xf.toFixed(1)}" y2="${padT+ih}" stroke="var(--warn)" stroke-width="1.5" stroke-dasharray="5 4"/>`;
    markers += `<circle cx="${xf.toFixed(1)}" cy="${y(hist[fi].c).toFixed(1)}" r="4" fill="var(--warn)"/>`;
    markers += `<text x="${xf.toFixed(1)}" y="${padT-2}" text-anchor="middle" font-size="10" fill="var(--warn)">大量保有</text>`;
  }

  // 現在値の点
  const lastX = x(hist.length-1), lastY = y(closes[closes.length-1]);
  markers += `<circle cx="${lastX.toFixed(1)}" cy="${lastY.toFixed(1)}" r="4.5" fill="var(--accent)"/>`;
  markers += `<text x="${(lastX-6).toFixed(1)}" y="${(lastY-8).toFixed(1)}" text-anchor="end" font-size="11" font-weight="700" fill="var(--accent)">現在 ${Math.round(closes[closes.length-1]).toLocaleString()}</text>`;

  return `<div class="chart-scroll"><svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" role="img" aria-label="株価チャート">
    <defs><linearGradient id="ar" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="var(--accent)" stop-opacity="0.18"/>
      <stop offset="1" stop-color="var(--accent)" stop-opacity="0"/>
    </linearGradient></defs>
    ${grid}
    ${bg}
    <polygon points="${areaPts}" fill="url(#ar)"/>
    <polyline points="${linePts}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round"/>
    ${markers}
    ${xlab}
  </svg></div>`;
}

/* ---- サブスコア横棒 ---- */
function subScoreBars(subs){
  const rows = [
    ["アクティビスト", subs.activist], ["割安(PBR)", subs.pbr], ["キャッシュ", subs.cash],
    ["還元余地", subs.payout], ["エントリー", subs.entry],
  ];
  return `<div class="bars">${rows.map(([label,v])=>{
    const pct = Math.round((v??0)*100);
    return `<div class="bar-row"><span class="bl">${label}</span>
      <span class="bt"><span class="bf" style="width:${pct}%"></span></span>
      <span class="bv">${pct}</span></div>`;
  }).join("")}</div>`;
}

function buyScoreColor(s){ return s>=80?'var(--good)':s>=60?'var(--accent)':s>=40?'var(--warn)':'var(--text-muted)'; }
function filterChip(label, ok){ return `<span class="chip ${ok?'ok':'ng'}">${ok?'✓':'—'} ${label}</span> `; }
function metric(k,v){ return `<div class="metric"><div class="k">${k}</div><div class="v">${v}</div></div>`; }
function acqMethod(m){ return { funds_div_shares:"取得資金÷株数", period_avg:"期間平均", none:"推定不可" }[m] || m || "—"; }
