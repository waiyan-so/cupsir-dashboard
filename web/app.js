async function load(path) { const r = await fetch(path); if (!r.ok) throw new Error(`Cannot load ${path}`); return r.json(); }
function cls(x) { return x === 'positive' ? 'positive' : (x === 'negative' || x === 'recession' ? 'negative' : 'warning'); }
function esc(v) { const d = document.createElement('div'); d.textContent = v ?? ''; return d.innerHTML; }

function embedLabel(embed) {
  if (!embed) return '未設定';
  if (embed.type === 'fred') return `FRED 圖表：${embed.target}`;
  if (embed.type === 'tradingview') return `TradingView：${embed.target}`;
  return embed.target || '未設定';
}

let detailChart = null;
// COT history is weekly (~30 points stored = ~7 months); "3 months of data" = last ~13 weeks.
const COT_CHART_WEEKS = 13;
const DETAIL_CHART_HEIGHT = 220;
const LEVEL_GUTTER = 38;        // room on the right of the plot for the level labels
const LEVEL_LABEL_GAP = 13;     // two level labels closer than this would overlap; the second is skipped

// What the chart needs beyond the history: dashed levels, for COT a fixed 0-100 axis, and
// for a series whose older points would flatten the recent ones, how many points to draw.
// A dashboard.json written before the "chart" entry existed (the page can be deployed ahead
// of the next data refresh) gets what the COT chart always drew, and plain lines elsewhere.
const COT_CHART_BEFORE_SPEC = { levels: [80, 20], y_range: [0, 100] };
function chartSpec(x) {
  const c = x.chart || (x.category === 'cot' ? COT_CHART_BEFORE_SPEC : {});
  return {
    levels: Array.isArray(c.levels) ? c.levels : [],
    yRange: Array.isArray(c.y_range) ? c.y_range : null,
    points: Number.isInteger(c.points) && c.points > 0 ? c.points : null,
  };
}

function renderDetail(x) {
  const isCot = x.category === 'cot';
  const spec = chartSpec(x);
  // The latest `points` of the history when the indicator sets it; COT keeps its 13 weeks.
  const shown = spec.points || (isCot ? COT_CHART_WEEKS : 0);
  const series = (x.history || []).slice(shown ? -shown : 0).filter(p => Number.isFinite(Number(p.value)));
  const hasChart = series.length > 1 && typeof uPlot !== 'undefined';
  const history = (x.history || []).slice(spec.points ? -spec.points : 0).map(p => `<div class="bar-row"><span>${esc(p.date)}</span><div class="bar"><i style="width:${Math.min(Math.abs(Number(p.value) || 0) * 5, 100)}%"></i></div><b>${esc(p.value)}</b></div>`).join('') || '<p class="muted">沒有可顯示的歷史資料。</p>';
  const chartTitle = isCot
    ? 'COT Index 走勢（近 3 個月，虛線 = 80／20 極端水平）'
    : `最近數值走勢${spec.levels.length ? '（虛線 = 訊號門檻）' : ''}`;
  const levelsNote = !isCot && spec.levels.length
    ? `<p class="muted">訊號門檻：${esc(spec.levels.slice().sort((a, b) => a - b).join('、'))}${x.unit ? ' ' + esc(x.unit) : ''}</p>` : '';
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
    ${hasChart
      ? `<h3>${chartTitle}</h3><div id="cotChartBox" class="cot-chart-box"></div>${levelsNote}`
      : `<h3>最近數值</h3><div class="mini-chart">${history}</div>`}
    <p class="muted">資料日期：${esc(x.data_date)} · <a href="${esc(x.source_url)}" target="_blank" rel="noreferrer">${esc(x.source_name)}</a></p>
  `;
  if (detailChart) { detailChart.destroy(); detailChart = null; }
  if (hasChart) drawDetailChart(series, spec, isCot ? 'COT Index' : x.name_zh);
}

// y axis: a fixed range when the indicator has one (COT, 0-100). Otherwise fitted to the
// data and stretched to the nearest level on each side, so the next signal level up and
// down is always in view without far-away levels flattening the line.
function detailChartRange(ys, spec) {
  if (spec.yRange) return spec.yRange;
  let lo = Math.min(...ys), hi = Math.max(...ys);
  const below = spec.levels.filter(l => l < lo), above = spec.levels.filter(l => l > hi);
  if (below.length) lo = Math.max(...below);
  if (above.length) hi = Math.min(...above);
  const pad = ((hi - lo) || Math.abs(hi) || 1) * 0.08;
  return [lo - pad, hi + pad];
}

function drawDetailChart(series, spec, label) {
  const box = document.querySelector('#cotChartBox');
  if (!box) return;
  const xs = series.map(p => Math.floor(new Date(p.date).getTime() / 1000));
  const ys = series.map(p => Number(p.value));
  const range = detailChartRange(ys, spec);
  const yAxis = { stroke: '#94a3b8', grid: { stroke: '#1f2c42' }, size: 56 };
  if (spec.yRange) yAxis.values = (u, vals) => vals.map(v => v.toFixed(0));
  const opts = {
    width: box.clientWidth || 600,
    height: DETAIL_CHART_HEIGHT,
    padding: [10, spec.levels.length ? LEVEL_GUTTER : 10, 0, 0],
    scales: { x: { time: true }, y: { range: () => range } },
    axes: [
      { stroke: '#94a3b8', grid: { stroke: '#1f2c42' } },
      yAxis,
    ],
    series: [
      { label: '日期', value: (u, v) => (v == null ? '--' : new Date(v * 1000).toISOString().slice(0, 10)) },
      // The tint under the line is only honest when the axis has a fixed floor (COT, 0-100).
      { label, stroke: '#60a5fa', width: 2, points: { show: true, size: 5 }, fill: spec.yRange ? 'rgba(96,165,250,0.08)' : undefined },
    ],
    // The legend row doubles as the hover readout: it shows the date and value under the cursor.
    legend: { show: true },
    cursor: { points: { size: 7 } },
    hooks: {
      draw: [u => {
        const ctx = u.ctx;
        const ratio = uPlot.pxRatio || window.devicePixelRatio || 1;
        ctx.save();
        ctx.strokeStyle = 'rgba(148,163,184,0.45)';
        ctx.fillStyle = '#94a3b8';
        ctx.font = `${11 * ratio}px Inter, Arial, sans-serif`;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.setLineDash([4 * ratio, 4 * ratio]);
        ctx.lineWidth = ratio;
        const right = u.bbox.left + u.bbox.width;
        let lastLabelY = null;
        spec.levels.filter(level => level >= range[0] && level <= range[1]).sort((a, b) => b - a).forEach(level => {
          const y = u.valToPos(level, 'y', true);
          ctx.beginPath();
          ctx.moveTo(u.bbox.left, y);
          ctx.lineTo(right, y);
          ctx.stroke();
          // Each line is named in the gutter beside the plot, clear of the data. When two
          // lines sit too close to label both, the lower one stays unlabelled; the note
          // under the chart lists every level.
          if (lastLabelY === null || Math.abs(y - lastLabelY) >= LEVEL_LABEL_GAP * ratio) {
            ctx.fillText(String(level), right + 5 * ratio, y);
            lastLabelY = y;
          }
        });
        ctx.restore();
      }],
    },
  };
  detailChart = new uPlot(opts, [xs, ys], box);
}

window.addEventListener('resize', () => {
  if (!detailChart) return;
  const box = document.querySelector('#cotChartBox');
  if (box) detailChart.setSize({ width: box.clientWidth || 600, height: DETAIL_CHART_HEIGHT });
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
