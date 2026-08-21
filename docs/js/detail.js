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
  if (!c){ renderRegisterPanel(code, root); return; }
  if (c.is_watchlist){ renderValueView(c, data, root); return; }

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
  const bg = buyGuide(cur, plan, anchor);   // 「いくらで買うか」の目安・現在地の判定
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
      <div class="buy-guide ${bg.cls}">
        <div class="bg-price-wrap">
          <div class="bg-k">買い目安価格</div>
          <div class="bg-price">${bg.price}</div>
          ${bg.ideal?`<div class="bg-ideal">${bg.ideal}</div>`:''}
        </div>
        <div class="bg-action-wrap">
          <div class="bg-action">${bg.action}</div>
          ${bg.sub?`<div class="bg-sub">${bg.sub}</div>`:''}
        </div>
      </div>
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
  const fair = plan && plan.fair;        // 簿価(PBR1倍)＝バリュー参考の基準線
  const lossCut = (plan && plan.slPrice != null) ? plan.slPrice : (pf != null ? pf * 0.8 : null);

  let lo = Math.min(...closes), hi = Math.max(...closes);
  if (pf != null){ lo = Math.min(lo, pf); hi = Math.max(hi, pf); }
  if (!plan || !plan.fair) { if (lossCut != null) lo = Math.min(lo, lossCut); }
  if (tpPrice != null){ hi = Math.max(hi, tpPrice); }
  if (band){ lo = Math.min(lo, band.lo); hi = Math.max(hi, band.hi); }
  if (fair != null){ lo = Math.min(lo, fair); hi = Math.max(hi, fair); }
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
  if (fair != null){
    const yv = y(fair);
    markers += `<line x1="${padL}" y1="${yv.toFixed(1)}" x2="${padL+iw}" y2="${yv.toFixed(1)}" stroke="var(--good)" stroke-width="1.5" stroke-dasharray="6 4"/>`;
    markers += `<text x="${padL+iw+6}" y="${yv.toFixed(1)}" dominant-baseline="middle" font-size="10" fill="var(--good)">簿価 ${Math.round(fair).toLocaleString()}</text>`;
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

/* 「いくらで買うか」の目安と現在地の判定（ゾーンの上=待ち／中=今／下=見送り） */
function buyGuide(cur, plan, anchor){
  const band = plan && plan.band;
  if (!band) return { cls:"bg-neutral", price:"—", ideal:"取得時株価が不明のため目安を計算できません。", action:"", sub:"" };
  const lo = band.lo, hi = band.hi;
  const price = `${fmtPrice(lo)}〜${fmtPrice(hi)}`;
  const ideal = anchor!=null ? `理想は ${fmtPrice(anchor)} 付近以下（アクティビスト取得水準）` : "";
  if (cur==null) return { cls:"bg-neutral", price, ideal, action:"現在値が取得できません。", sub:"" };
  if (cur < lo){
    return { cls:"bg-bad", price, ideal,
      action:`⚠ 現在 ${fmtPrice(cur)}：下抜け（見送りが基本）`,
      sub:`損切り水準（${fmtPrice(lo)}）を割れています。反発して ${fmtPrice(lo)} 回復まで様子見。` };
  }
  if (cur > hi){
    const down = (cur - hi) / cur;
    return { cls:"bg-warn", price, ideal,
      action:`⏳ ${fmtPrice(hi)} まで下げれば買い（現在から -${(down*100).toFixed(1)}%）`,
      sub:`現在 ${fmtPrice(cur)}。押し目 ${fmtPrice(hi)} 以下まで下がるのを待つのが基本。` };
  }
  return { cls:"bg-good", price, ideal,
    action:`✅ 今が買い目安：現在 ${fmtPrice(cur)} はゾーン内`,
    sub:`利確 ${fmtPrice(plan.tpPrice)}／損切り ${fmtPrice(plan.slPrice)} を機械的に。` };
}

function buyScoreColor(s){ return s>=80?'var(--good)':s>=60?'var(--accent)':s>=40?'var(--warn)':'var(--text-muted)'; }
function filterChip(label, ok){ return `<span class="chip ${ok?'ok':'ng'}">${ok?'✓':'—'} ${label}</span> `; }
function metric(k,v){ return `<div class="metric"><div class="k">${k}</div><div class="v">${v}</div></div>`; }
function acqMethod(m){ return { funds_div_shares:"取得資金÷株数", period_avg:"期間平均", none:"推定不可" }[m] || m || "—"; }

/* ===== 監視リスト（バリュー参考）＝アクティビスト不在の銘柄向け ===== */

/* 簿価(PBR1倍株価=BPS)を基準にした割安/割高の目安 */
function valueGuide(cur, bps, pbr){
  if (bps==null) return { cls:"bg-neutral", price:"—", ideal:"簿価(BPS)が取得できず割安判定できません。", action:"", sub:"" };
  const price = `${fmtPrice(bps)} 以下（PBR1倍）`;
  const ideal = "PBRが低いほど割安（純資産に対して株価が安い）";
  const pbrTxt = pbr!=null ? `PBR ${fmt2(pbr)}` : "PBR—";
  if (cur==null) return { cls:"bg-neutral", price, ideal, action:"現在値が取得できません。", sub:"" };
  if (cur <= bps){
    return { cls:"bg-good", price, ideal,
      action:`✅ 割安：現在 ${fmtPrice(cur)} は簿価 ${fmtPrice(bps)} 以下（${pbrTxt}）`,
      sub:`純資産より安く買える水準。PBR1倍(=${fmtPrice(bps)})までの是正余地が目安。` };
  }
  const up = (cur - bps) / cur;
  return { cls:"bg-warn", price, ideal,
    action:`⏳ 簿価 ${fmtPrice(bps)} 以下で割安（現在 ${pbrTxt}）`,
    sub:`現在 ${fmtPrice(cur)} は簿価より高い。${fmtPrice(bps)} 付近（-${(up*100).toFixed(1)}%）まで下げれば割安圏。` };
}

/* 監視リスト（バリュー参考）銘柄の詳細ビュー */
function renderValueView(c, data, root){
  const d = c.derived, f = c.fundamentals;
  const cur = c.price.close;
  const bps = (f.bps!=null) ? f.bps
    : (f.equity!=null && f.shares_out ? f.equity / f.shares_out : null);
  const vg = valueGuide(cur, bps, d.pbr);
  const plan = { band:null, tpPrice:null, slPrice:null, fair:bps };
  const onVW = isVWatched(c.code);
  const dispName = /^\(code /.test(c.name) ? `銘柄 ${c.code}` : c.name;

  root.innerHTML = `
    <a href="index.html" class="muted">← 候補一覧へ戻る</a>
    <div class="detail-head" style="margin-top:8px">
      <span class="code">${c.code}</span>
      <h1>${dispName}</h1>
      <span class="chip">監視・バリュー参考</span>
      <span class="muted">${c.market || ''}</span>
    </div>

    <div class="banner info">この銘柄は<strong>アクティビストの大量保有報告がありません</strong>。
      PBR・簿価によるバリュー参考表示です（アクティビスト追随の買いゾーンは非対象）。</div>

    <div class="card">
      <h2>株価チャートと簿価（PBR1倍）水準</h2>
      <div class="filing-summary">
        <div class="fs-item"><div class="k">現在値</div><div class="v">${fmtPrice(cur)}</div></div>
        <div class="fs-item"><div class="k">簿価(BPS)</div><div class="v">${fmtPrice(bps)}</div></div>
        <div class="fs-item"><div class="k">PBR</div><div class="v">${fmt2(d.pbr)}</div></div>
        <div class="fs-item"><div class="k">配当利回り</div><div class="v">${fmtPct(d.dividend_yield)}</div></div>
      </div>
      <div id="chart"></div>
      <div class="legend">
        <span class="lg"><span class="sw" style="background:var(--accent)"></span>株価</span>
        <span class="lg"><span class="sw dash" style="background:var(--good)"></span>簿価(PBR1倍)</span>
      </div>
    </div>

    <div class="card">
      <h2>📋 バリュー判定（割安/割高の目安）</h2>
      <div class="buy-guide ${vg.cls}">
        <div class="bg-price-wrap">
          <div class="bg-k">買い目安価格</div>
          <div class="bg-price">${vg.price}</div>
          ${vg.ideal?`<div class="bg-ideal">${vg.ideal}</div>`:''}
        </div>
        <div class="bg-action-wrap">
          <div class="bg-action">${vg.action}</div>
          ${vg.sub?`<div class="bg-sub">${vg.sub}</div>`:''}
        </div>
      </div>
      <div class="metrics">
        ${metric("PBR", fmt2(d.pbr))}
        ${metric("PBR1倍株価(簿価)", fmtPrice(bps))}
        ${metric("配当利回り", fmtPct(d.dividend_yield))}
        ${metric("時価総額", fmtYokuEn(d.market_cap))}
        ${metric("現在値", fmtPrice(cur))}
      </div>
      <p class="muted" style="font-size:.8rem;margin-top:10px">
        バリュー参考です。<strong>PBR&lt;1（株価&lt;簿価）＝純資産より安い</strong>の目安を示すもので、
        アクティビストの取得水準を基準にした買いゾーン・利確/損切りルールとは別物です。割安=必ず上がる、ではありません。
      </p>
      <div style="margin-top:10px">
        <button class="btn" id="vwBtn">${onVW ? '監視リストから外す' : '👁 監視リストに登録'}</button>
        <span class="muted" id="vwMsg" style="font-size:.8rem;margin-left:8px"></span>
      </div>
    </div>

    ${financeCard(f, d)}
  `;

  document.getElementById("chart").innerHTML = buildPriceChart(c, plan);
  const vwBtn = document.getElementById("vwBtn");
  vwBtn.addEventListener("click", ()=>{
    if (isVWatched(c.code)){ removeVWatch(c.code); vwBtn.textContent = '👁 監視リストに登録'; document.getElementById("vwMsg").textContent = '監視リストから外しました'; }
    else { addVWatch(c.code); vwBtn.textContent = '監視リストから外す'; document.getElementById("vwMsg").textContent = '登録しました（トップの監視リストに表示）'; }
  });
}

/* 未取得コード：監視リスト登録パネル */
function renderRegisterPanel(code, root){
  const onVW = isVWatched(code);
  root.innerHTML = `
    <a href="index.html" class="muted">← 候補一覧へ戻る</a>
    <div class="detail-head" style="margin-top:8px">
      <span class="code">${code || '—'}</span>
      <h1>未取得の銘柄</h1>
      <span class="chip">データなし</span>
    </div>
    <div class="card">
      <p>コード <strong>${code || '(未指定)'}</strong> は、まだ日次取得の対象になっていません。</p>
      <p class="muted" style="font-size:.9rem">
        このダッシュボードは静的サイトのため、表示できるのは<strong>毎日パイプラインが取得済みのデータだけ</strong>です。
        下のボタンでこの銘柄を<strong>監視リスト（ブラウザ保存）</strong>に登録し、
        その一覧を <code>config/watchlist.txt</code> に反映すると、翌営業日以降チャート・財務・割安判定が表示されます。
      </p>
      <div style="margin:12px 0">
        <button class="btn" id="regBtn">${onVW ? '登録済み（外す）' : '👁 監視リストに登録する'}</button>
        <span class="muted" id="regMsg" style="font-size:.85rem;margin-left:8px"></span>
      </div>
      <div id="regList"></div>
    </div>
  `;
  const regBtn = document.getElementById("regBtn");
  regBtn.addEventListener("click", ()=>{
    if (isVWatched(code)){ removeVWatch(code); regBtn.textContent='👁 監視リストに登録する'; document.getElementById("regMsg").textContent='外しました'; }
    else { addVWatch(code); regBtn.textContent='登録済み（外す）'; document.getElementById("regMsg").textContent='登録しました'; }
    drawRegList();
  });
  function drawRegList(){
    const codes = getVWatch();
    const el = document.getElementById("regList");
    if (!codes.length){ el.innerHTML=""; return; }
    el.innerHTML = `<div class="section-title" style="margin-top:6px">監視リスト（${codes.length}件）</div>
      <p class="muted" style="font-size:.82rem;margin:2px 0 8px">毎日取得に載せるには、この内容を <code>config/watchlist.txt</code> に貼り付けてコミットしてください。</p>
      <textarea readonly rows="${Math.min(8,codes.length)}" class="field" style="width:100%;font-family:monospace">${codes.join("\n")}</textarea>
      <div style="margin-top:8px"><button class="btn" id="regCopy">📋 コピー</button>
        <span class="muted" id="regCopyMsg" style="font-size:.8rem;margin-left:8px"></span></div>`;
    document.getElementById("regCopy").addEventListener("click", async ()=>{
      try { await navigator.clipboard.writeText(codes.join("\n")+"\n"); document.getElementById("regCopyMsg").textContent="コピーしました"; }
      catch { document.getElementById("regCopyMsg").textContent="上のテキストを選択してコピーしてください"; }
    });
  }
  drawRegList();
}

/* 財務・派生指標カード（アクティビスト/バリュー両ビューで共用） */
function financeCard(f, d){
  return `<div class="card">
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
    </div>`;
}
