async function load(path) { const r = await fetch(path); if (!r.ok) throw new Error(`Cannot load ${path}`); return r.json(); }
function cls(x) { return x === 'positive' ? 'positive' : (x === 'negative' || x === 'recession' ? 'negative' : 'warning'); }
function esc(v) { const d = document.createElement('div'); d.textContent = v ?? ''; return d.innerHTML; }

function embedLabel(embed) {
  if (!embed) return '未設定';
  if (embed.type === 'fred') return `FRED 圖表：${embed.target}`;
  if (embed.type === 'tradingview') return `TradingView：${embed.target}`;
  return embed.target || '未設定';
}

let cotChart = null;
// COT history is weekly (~30 points stored = ~7 months); "3 months of data" = last ~13 weeks.
const COT_CHART_WEEKS = 13;

function renderDetail(x) {
  const cotSeries = (x.history || []).slice(-COT_CHART_WEEKS);
  const isCot = x.category === 'cot' && cotSeries.length > 1 && typeof uPlot !== 'undefined';
  const history = (x.history || []).map(p => `<div class="bar-row"><span>${esc(p.date)}</span><div class="bar"><i style="width:${Math.min(Math.abs(Number(p.value) || 0) * 5, 100)}%"></i></div><b>${esc(p.value)}</b></div>`).join('') || '<p class="muted">沒有可顯示的歷史資料。</p>';
  document.querySelector('#indicatorDetail').innerHTML = `
    <div class="detail-head">
      <div><h2>${esc(x.name_zh)}</h2><p class="muted">${esc(x.name)}</p></div>
      <div class="value ${cls(x.signal_color)}"><b>${esc(x.value)} ${esc(x.unit)}</b><span>${esc(x.signal)}</span></div>
    </div>
    <p>${esc(x.interpretation)}</p>
    <h3>CupSir 建議檢查</h3>
    <ul>${(x.checklist || []).map(v => `<li>${esc(v)}</li>`).join('')}</ul>
    <h3>圖表（占位，未來功能）</h3>
    <div class="chart-placeholder">
      <span>📈</span>
      <p>${esc(embedLabel(x.embed))}</p>
      <small class="muted">互動圖表嵌入將於後續版本加入，現時先顯示右方近期數值。</small>
    </div>
    ${isCot
      ? `<h3>COT Index 走勢（近 3 個月，虛線 = 80／20 極端水平）</h3><div id="cotChartBox" class="cot-chart-box"></div>`
      : `<h3>最近數值</h3><div class="mini-chart">${history}</div>`}
    <p class="muted">資料日期：${esc(x.data_date)} · <a href="${esc(x.source_url)}" target="_blank" rel="noreferrer">${esc(x.source_name)}</a></p>
  `;
  if (cotChart) { cotChart.destroy(); cotChart = null; }
  if (isCot) drawCotChart(cotSeries);
}

function drawCotChart(series) {
  const box = document.querySelector('#cotChartBox');
  if (!box) return;
  const xs = series.map(p => Math.floor(new Date(p.date).getTime() / 1000));
  const ys = series.map(p => Number(p.value));
  const opts = {
    width: box.clientWidth || 600,
    height: 220,
    scales: { x: { time: true }, y: { range: [0, 100] } },
    axes: [
      { stroke: '#94a3b8', grid: { stroke: '#1f2c42' } },
      { stroke: '#94a3b8', grid: { stroke: '#1f2c42' }, values: (u, vals) => vals.map(v => v.toFixed(0)) },
    ],
    series: [
      {},
      { label: 'COT Index', stroke: '#60a5fa', width: 2, points: { show: true, size: 5 }, fill: 'rgba(96,165,250,0.08)' },
    ],
    legend: { show: false },
    cursor: { points: { size: 7 } },
    hooks: {
      draw: [u => {
        const ctx = u.ctx;
        ctx.save();
        ctx.strokeStyle = 'rgba(148,163,184,0.45)';
        ctx.setLineDash([4, 4]);
        ctx.lineWidth = 1;
        [80, 20].forEach(level => {
          const y = u.valToPos(level, 'y', true);
          ctx.beginPath();
          ctx.moveTo(u.bbox.left, y);
          ctx.lineTo(u.bbox.left + u.bbox.width, y);
          ctx.stroke();
        });
        ctx.restore();
      }],
    },
  };
  cotChart = new uPlot(opts, [xs, ys], box);
}

window.addEventListener('resize', () => {
  if (!cotChart) return;
  const box = document.querySelector('#cotChartBox');
  if (box) cotChart.setSize({ width: box.clientWidth || 600, height: 220 });
});

function renderList(dashboard) {
  const items = dashboard.indicators || [];
  const order = dashboard.category_order || [...new Set(items.map(x => x.category))];
  const labels = dashboard.category_labels || {};
  const box = document.querySelector('#indicatorList');
  box.innerHTML = order.map(catId => {
    const groupItems = items.filter(x => x.category === catId);
    if (!groupItems.length) return '';
    return `<section class="indicator-group"><h3 class="group-title">${esc(labels[catId] || catId)}</h3>${groupItems.map(x => `<button class="indicator" data-id="${esc(x.id)}"><span>${esc(x.name_zh)}</span><small class="${cls(x.signal_color)}">${esc(x.signal)}</small></button>`).join('')}</section>`;
  }).join('');
  const buttons = box.querySelectorAll('.indicator');
  buttons.forEach(b => b.onclick = () => { buttons.forEach(q => q.classList.remove('active')); b.classList.add('active'); renderDetail(items.find(x => x.id === b.dataset.id)); });
  if (buttons.length) buttons[0].classList.add('active');
}

function renderEvents(items) {
  const box = document.querySelector('#events');
  if (!items.length) { box.innerHTML = '<p class="muted">未來兩周暫無已知重要事件。</p>'; return; }
  box.innerHTML = items.slice(0, 20).map(x => `<div class="row"><b>${esc(x.date)}</b><div><strong>${esc(x.title_zh || x.title)}</strong><p>${esc(x.notes || '')}</p></div><span>${'⭐'.repeat(x.importance || 1)}</span></div>`).join('');
}

function renderNews(items) {
  const box = document.querySelector('#news');
  if (!items.length) { box.innerHTML = '<p class="muted">暫無最新新聞（等待下次資料更新）。</p>'; return; }
  box.innerHTML = items.map(x => `<article class="news"><a href="${esc(x.url)}" target="_blank" rel="noreferrer">${esc(x.title)}</a><small>${esc(x.source)} · ${esc(x.published_at)}</small><p>${esc(x.summary || '')}</p></article>`).join('');
}

function renderSummary(s) {
  document.querySelector('#summary').innerHTML = `
    <h3>${esc(s.headline)}</h3>
    <p>${esc(s.macro)}</p>
    <h3>市場情緒</h3><p>${esc(s.market_sentiment)}</p>
    <h3>未來催化劑</h3><ul>${(s.catalysts || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>
    <h3>檢查清單</h3><ul>${(s.checklist || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>
    <p class="muted">${esc(s.disclaimer)}</p>
  `;
}

async function init() {
  const [d, e, n, s] = await Promise.all([
    load('data/dashboard.json'), load('data/events.json'), load('data/news.json'), load('data/summary.json')
  ]);
  document.querySelector('#updatedAt').textContent = `最後更新：${d.updated_at}`;
  const badge = document.querySelector('#overallSignal');
  badge.textContent = `${d.overall_signal} · ${d.total_score}`;
  badge.className = `signal ${d.overall_signal === 'BULLISH' ? 'positive' : d.overall_signal === 'BEARISH' ? 'negative' : 'warning'}`;
  renderList(d);
  if (d.indicators.length) renderDetail(d.indicators[0]);
  renderEvents(e);
  renderNews(n);
  renderSummary(s);
}
init().catch(err => document.body.insertAdjacentHTML('afterbegin', `<div class="error">資料讀取失敗：${esc(err.message)}</div>`));

// Tabs: each .tab button shows the .tab-panel whose id is "<data-tab>Tab" and hides the others.
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(p => { p.hidden = p.id !== `${name}Tab`; });
  // A chart inside a hidden panel has no width; let every chart re-measure now.
  window.dispatchEvent(new Event('resize'));
}
document.querySelectorAll('.tab').forEach(t => t.onclick = () => switchTab(t.dataset.tab));
