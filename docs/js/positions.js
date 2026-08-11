/* ポジション管理：localStorage に建玉を保存し、最新データで損益・出口シグナルを計算 */

(async () => {
  renderHeader("positions.html");
  let data = null;
  try { data = await loadData(); } catch(e){ data = { candidates: [], activist_exits: [] }; }
  document.getElementById("banner").innerHTML = sampleBanner(data);

  const byCode = {};
  (data.candidates||[]).forEach(c => byCode[c.code] = c);
  const exitCodes = new Set((data.activist_exits||[]).map(e => e.code));

  const form = document.getElementById("posForm");
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const code = document.getElementById("f_code").value.trim();
    const entry = parseFloat(document.getElementById("f_entry").value);
    const shares = parseFloat(document.getElementById("f_shares").value);
    const date = document.getElementById("f_date").value;
    if (!code || isNaN(entry) || isNaN(shares)) return;
    const list = getPositions();
    list.push({ id: Date.now(), code, entry, shares, date });
    savePositions(list);
    form.reset();
    render();
  });

  document.getElementById("exportBtn").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(getPositions(), null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "positions-backup.json";
    a.click();
  });
  document.getElementById("importFile").addEventListener("change", (e) => {
    const file = e.target.files[0]; if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try { const arr = JSON.parse(reader.result); if (Array.isArray(arr)) { savePositions(arr); render(); } }
      catch { alert("読み込めませんでした（JSON形式が不正）"); }
    };
    reader.readAsText(file);
  });

  function evaluate(p){
    const c = byCode[p.code];
    const close = c ? c.price.close : null;
    const name = c ? c.name : "";
    const pl = (close != null) ? (close - p.entry) * p.shares : null;
    const plPct = (close != null && p.entry) ? (close - p.entry) / p.entry : null;
    const lossCutHit = (close != null) ? close <= p.entry * 0.8 : false;
    const activistExited = exitCodes.has(p.code) || (c && c.activist && c.activist.activist_exited);
    let signal = "保有継続", cls = "chip ok";
    if (lossCutHit) { signal = "損切り(-20%)"; cls = "chip exit"; }
    else if (activistExited) { signal = "アクティビスト撤退→手仕舞い検討"; cls = "chip exit"; }
    else if (plPct != null && plPct <= -0.15) { signal = "損切り接近"; cls = "chip changed"; }
    return { c, close, name, pl, plPct, lossCutHit, activistExited, signal, cls };
  }

  function render(){
    const list = getPositions();
    const tbody = document.getElementById("posBody");
    const empty = document.getElementById("posEmpty");
    if (!list.length){ tbody.innerHTML = ""; empty.innerHTML = `<div class="empty">建玉がありません。上のフォームから追加してください。</div>`; renderSummary([]); return; }
    empty.innerHTML = "";
    const evals = list.map(p => ({ p, ev: evaluate(p) }));
    tbody.innerHTML = evals.map(({p, ev}) => {
      const plCls = ev.pl == null ? "" : (ev.pl >= 0 ? "pl-pos" : "pl-neg");
      const plTxt = ev.pl == null ? "—" : `${ev.pl>=0?'+':''}${fmtYokuEn(ev.pl)}（${ev.plPct>=0?'+':''}${fmtPct(ev.plPct)}）`;
      return `<tr>
        <td class="l">${p.code} ${ev.c?`<a href="stock.html?code=${p.code}" class="muted" title="詳細">↗</a>`:''}</td>
        <td class="l name">${ev.name || '<span class="muted">未取得</span>'}</td>
        <td>${fmtPrice(p.entry)}</td>
        <td>${fmtNum(p.shares)}</td>
        <td>${fmtPrice(ev.close)}</td>
        <td class="${plCls}">${plTxt}</td>
        <td class="l"><span class="${ev.cls}">${ev.signal}</span></td>
        <td class="l">${p.date||'—'}</td>
        <td><button class="btn small secondary" data-del="${p.id}">削除</button></td>
      </tr>`;
    }).join("");
    tbody.querySelectorAll("[data-del]").forEach(b=>{
      b.addEventListener("click", ()=>{
        savePositions(getPositions().filter(x=>String(x.id)!==b.dataset.del));
        render();
      });
    });
    renderSummary(evals);
  }

  function renderSummary(evals){
    const total = evals.reduce((s,{ev})=> s + (ev.pl||0), 0);
    const exits = evals.filter(({ev})=>ev.lossCutHit || ev.activistExited).length;
    const cost = evals.reduce((s,{p})=> s + p.entry*p.shares, 0);
    document.getElementById("tiles").innerHTML = `
      ${tile("建玉数", evals.length, "登録中のポジション")}
      ${tile("評価損益", (total>=0?'+':'')+fmtYokuEn(total), "最新終値ベース")}
      ${tile("投資額", fmtYokuEn(cost), "取得価格×株数の合計")}
      ${tile("出口シグナル", exits, "損切り/アクティビスト撤退")}`;
  }
  function tile(k,v,sub){ return `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="sub">${sub}</div></div>`; }

  render();
  const footer = document.getElementById("footer");
  if (footer && data.as_of_date) footer.textContent = `参照データ 対象日 ${data.as_of_date}／建玉はこの端末のブラウザにのみ保存されます（バックアップ推奨）`;
})();
