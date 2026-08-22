/* ペーパー検証ページ：docs/data/paper.json を読み、累積成績・オープン/クローズを表示 */
(async () => {
  renderHeader("paper.html");
  let data;
  try {
    const r = await fetch("./data/paper.json", { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    data = await r.json();
  } catch (e) {
    document.getElementById("tiles").innerHTML =
      `<div class="banner info">まだ検証データがありません（日次パイプラインの初回実行後に表示されます）。</div>`;
    return;
  }
  const trades = data.trades || [];
  const open = trades.filter(t => t.status === "open");
  const closed = trades.filter(t => t.status === "closed");
  const wins = closed.filter(t => (t.ret || 0) > 0);
  const rets = closed.map(t => t.ret).filter(x => x != null);
  const winRate = closed.length ? wins.length / closed.length : null;
  const exp = rets.length ? rets.reduce((a, b) => a + b, 0) / rets.length : null;
  const avgDays = closed.length ? Math.round(closed.reduce((a, t) => a + (t.days || 0), 0) / closed.length) : null;

  // --- 検証の進捗（ゴール：クローズ50件 または 6ヶ月・早い方） ---
  const TARGET_CLOSED = 50, TARGET_MONTHS = 6;
  const entryDates = trades.map(t => t.entry_date).filter(Boolean).sort();
  const firstEntry = entryDates[0] || null;
  const nowMs = data.updated_at ? new Date(data.updated_at).getTime() : Date.now();
  const elapsedDays = firstEntry ? Math.max(0, Math.round((nowMs - new Date(firstEntry).getTime()) / 86400000)) : 0;
  const elapsedMonths = elapsedDays / 30.44;
  const doneVerify = closed.length >= TARGET_CLOSED || elapsedMonths >= TARGET_MONTHS;
  const remainCount = Math.max(0, TARGET_CLOSED - closed.length);
  const remainMonths = Math.max(0, TARGET_MONTHS - elapsedMonths);
  const pbar = (label, val, max, valTxt) => {
    const pct = Math.min(100, Math.round((val / max) * 100));
    return `<div style="margin:10px 0">
      <div style="display:flex;justify-content:space-between;font-size:.82rem;margin-bottom:4px">
        <span>${label}</span><span class="muted">${valTxt}（${pct}%）</span></div>
      <div style="height:10px;background:var(--surface-2);border-radius:6px;overflow:hidden">
        <div style="height:100%;width:${pct}%;background:${doneVerify ? 'var(--good)' : 'var(--accent)'}"></div></div>
    </div>`;
  };
  const statusLine = doneVerify
    ? `<div class="banner"><strong>✅ 判定ラインに到達</strong> — フォワードの勝率をバックテスト（約70%）と突き合わせて次の判断へ。`
      + `${closed.length < 20 ? '（ただしクローズ件数が少なめなので、件数基準の50件到達を待つのが安全です）' : ''}</div>`
    : `<div class="banner info">判定可能まで：あと <strong>${remainCount}件</strong> のクローズ、または残り <strong>約${remainMonths.toFixed(1)}ヶ月</strong>（早い方）。`
      + `<br><span class="muted" style="font-size:.85rem">※クローズ件数が少ないうちは勝率・期待値は当てになりません（20〜30件で傾向、50件でそこそこ）。</span></div>`;
  document.getElementById("progress").innerHTML = `<div class="card">
      <div class="section-title" style="margin-top:0">🎯 検証の進捗（ゴール：クローズ${TARGET_CLOSED}件 または ${TARGET_MONTHS}ヶ月・早い方）</div>
      ${pbar("決済(クローズ)件数", closed.length, TARGET_CLOSED, `${closed.length} / ${TARGET_CLOSED}件`)}
      ${pbar("経過期間", elapsedMonths, TARGET_MONTHS, `${elapsedMonths.toFixed(1)} / ${TARGET_MONTHS}ヶ月`)}
      ${statusLine}
    </div>`;

  const tile = (k, v, sub) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="sub">${sub}</div></div>`;
  const expCls = (exp || 0) > 0 ? "pl-pos" : "pl-neg";
  document.getElementById("tiles").innerHTML =
    tile("仮トレード数", trades.length, `オープン ${open.length} / クローズ ${closed.length}`) +
    tile("勝率（フォワード）", winRate == null ? "—" : fmtPct(winRate), "クローズ済みのみ") +
    tile("期待値/トレード", exp == null ? "—" : `<span class="${expCls}">${fmtPct(exp, 2)}</span>`, "決済済み平均リターン") +
    tile("平均保有日数", avgDays == null ? "—" : avgDays + "日", "エントリー→決済");

  const rlabel = { tp: '<span class="chip ok">利確</span>', sl: '<span class="chip exit">損切り</span>', time: '<span class="chip">時間切れ</span>' };

  // オープン
  const ob = document.getElementById("openBody");
  open.sort((a, b) => (b.ret || 0) - (a.ret || 0));
  ob.innerHTML = open.map(t => {
    const pl = t.ret == null ? "—" : `<span class="${t.ret >= 0 ? 'pl-pos' : 'pl-neg'}">${t.ret >= 0 ? '+' : ''}${fmtPct(t.ret)}</span>`;
    return `<tr><td class="l">${t.code} <a href="stock.html?code=${t.code}" class="muted" title="詳細">↗</a></td>
      <td class="l name">${t.name}</td><td class="l">${t.fund}</td>
      <td>${t.entry_date}</td><td>${fmtPrice(t.entry_price)}</td><td>${fmtPrice(t.last_price)}</td>
      <td>${pl}</td><td>${t.days ?? '—'}日</td></tr>`;
  }).join("");
  document.getElementById("openEmpty").innerHTML = open.length ? "" : `<div class="empty">オープン中の仮ポジションはありません。</div>`;

  // クローズ
  const cb = document.getElementById("closedBody");
  closed.sort((a, b) => (b.exit_date || "").localeCompare(a.exit_date || ""));
  cb.innerHTML = closed.map(t => {
    const pl = `<span class="${(t.ret || 0) >= 0 ? 'pl-pos' : 'pl-neg'}">${(t.ret || 0) >= 0 ? '+' : ''}${fmtPct(t.ret)}</span>`;
    return `<tr><td class="l">${t.code}</td><td class="l name">${t.name}</td><td class="l">${t.fund}</td>
      <td>${t.entry_date}</td><td>${t.exit_date}</td><td class="l">${rlabel[t.exit_reason] || t.exit_reason}</td><td>${pl}</td></tr>`;
  }).join("");
  document.getElementById("closedEmpty").innerHTML = closed.length ? "" : `<div class="empty">まだ決済済みトレードはありません（数週間〜で貯まります）。</div>`;

  if (data.updated_at) document.getElementById("footer").textContent =
    `更新 ${new Date(data.updated_at).toLocaleString("ja-JP")}／紙上検証・投資勧誘ではありません`;
})();
