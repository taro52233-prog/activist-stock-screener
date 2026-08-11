/* 個別銘柄詳細ページのロジック */
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
  const lossCut = c.price.close != null ? c.price.close * 0.8 : null;
  const watched = isWatched(c.code);

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
      <h2>判定サマリー（スコア ${c.signal.score}/100）</h2>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px" class="detail-cols">
        <div style="min-height:220px"><canvas id="profile"></canvas></div>
        <div>
          <div style="margin-bottom:10px">
            ${filterChip("アクティビスト", c.signal.filters.activist)}
            ${filterChip("PBR<1", c.signal.filters.pbr_lt_1)}
            ${filterChip("キャッシュリッチ", c.signal.filters.cash_rich)}
            ${filterChip("還元余地", c.signal.filters.low_payout)}
            ${filterChip("エントリー可", c.signal.filters.entry_ok)}
          </div>
          <ul class="reasons">${(c.signal.reasons_ja||[]).map(r=>`<li>${r}</li>`).join("") || '<li class="muted" style="background:none;border:none">該当理由なし</li>'}</ul>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>株価水準とエントリー</h2>
      <div style="height:180px"><canvas id="levels"></canvas></div>
      <p class="muted" style="font-size:.82rem;margin-top:8px">
        現在値 ${fmtPrice(c.price.close)}（${c.price.date||'—'}／${c.price.source||'—'}）・
        推定取得単価 ${fmtPrice(d.est_acq_price)}（${acqMethod(d.acq_price_method)}）・
        損切りライン ${fmtPrice(lossCut)}
      </p>
    </div>

    <div class="card">
      <h2>アクティビスト情報</h2>
      <dl class="kv">
        <dt>ファンド</dt><dd>${a.fund||'—'} ${a.is_joint?'<span class="chip">共同保有</span>':''}</dd>
        <dt>保有割合</dt><dd>${fmtPct(a.holding_ratio)} ${a.prev_ratio!=null?`（前回 ${fmtPct(a.prev_ratio)}／変化 ${a.ratio_change!=null?(a.ratio_change>=0?'+':'')+fmtPct(a.ratio_change):'—'}）`:''}</dd>
        <dt>提出日</dt><dd>${a.filing_date||'—'}</dd>
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

  if (window.Chart){
    profileChart(document.getElementById("profile"), c.signal.subscores || {});
    priceLevelsChart(document.getElementById("levels"), { acq: d.est_acq_price, current: c.price.close, lossCut });
  }
})();

function filterChip(label, ok){ return `<span class="chip ${ok?'ok':'ng'}">${ok?'✓':'—'} ${label}</span> `; }
function metric(k,v){ return `<div class="metric"><div class="k">${k}</div><div class="v">${v}</div></div>`; }
function acqMethod(m){ return { funds_div_shares:"取得資金÷株数", period_avg:"期間平均", none:"推定不可" }[m] || m || "—"; }
