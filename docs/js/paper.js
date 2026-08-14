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
