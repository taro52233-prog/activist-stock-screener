/* Chart.js を使ったチャート描画ヘルパ（CDNで Chart を読み込む前提） */

function cssVar(name){ return getComputedStyle(document.body).getPropertyValue(name).trim(); }

/* 価格水準：推定取得単価・現在値・-20%損切りライン を横棒で比較 */
function priceLevelsChart(canvas, { acq, current, lossCut }){
  const labels = [], data = [], colors = [];
  if (current != null){ labels.push("現在値"); data.push(current); colors.push(cssVar("--accent")); }
  if (acq != null){ labels.push("推定取得単価"); data.push(acq); colors.push(cssVar("--text-muted")); }
  if (lossCut != null){ labels.push("損切りライン(-20%)"); data.push(lossCut); colors.push(cssVar("--bad")); }
  if (!data.length) return null;
  return new Chart(canvas, {
    type: "bar",
    data: { labels, datasets: [{ data, backgroundColor: colors, borderRadius: 6, barThickness: 26 }] },
    options: {
      indexAxis: "y", responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: ctx => nf.format(Math.round(ctx.parsed.x)) + "円" } } },
      scales: {
        x: { ticks: { color: cssVar("--text-muted"), callback: v => nf.format(v) }, grid: { color: cssVar("--border") } },
        y: { ticks: { color: cssVar("--text") }, grid: { display: false } },
      },
    },
  });
}

/* シグナル・プロフィール：5サブスコアをレーダーで表示 */
function profileChart(canvas, subs){
  const labels = ["アクティビスト", "割安(PBR)", "キャッシュ", "還元余地", "エントリー"];
  const data = [subs.activist, subs.pbr, subs.cash, subs.payout, subs.entry].map(x => x ?? 0);
  const acc = cssVar("--accent");
  return new Chart(canvas, {
    type: "radar",
    data: { labels, datasets: [{ data, fill: true,
      backgroundColor: acc + "33", borderColor: acc, pointBackgroundColor: acc }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { r: {
        min: 0, max: 1, ticks: { display: false, stepSize: 0.25 },
        grid: { color: cssVar("--border") }, angleLines: { color: cssVar("--border") },
        pointLabels: { color: cssVar("--text"), font: { size: 11 } },
      } },
    },
  });
}
