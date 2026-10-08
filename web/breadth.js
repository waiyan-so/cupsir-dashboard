/*
 * Presentation layer for the market breadth cards, the sector and COT tabs and
 * the ratio pairs under the sectors (each: a list with the charts beside it, or
 * the sortable comparison table).
 *
 * Everything drawn here comes from the `meta` block of the JSON files: which
 * indicators exist, where each one appears, how a value is formatted, which
 * chart to draw and every piece of wording. This file therefore names no
 * indicator, no threshold and no indicator copy - adding an indicator to
 * config/indicators.json needs no change here.
 *
 * It calculates nothing. The only work done is sorting and number formatting.
 * Loaded after app.js and uses its load(), cls() and esc().
 */
(function () {
  'use strict';

  const LOAD_ERROR = '資料暫時未能載入';
  const CHART_HEIGHT = 240;
  const AXIS = '#94a3b8';
  const GRID = '#1f2c42';
  const SURFACE = '#0f1a2c';
  // Line colours in fixed order (validated for colour-blind separation on the chart surface).
  // The green / yellow / red of the page are reserved for states and are not used for lines.
  const SERIES_COLORS = ['#3987e5', '#d95926', '#199e70', '#c98500'];
  const NAME_COLUMN = '__name';
  const GROUP_COLUMN = '__group';
  const VIEWS = ['list', 'table'];
  const VIEW_STORAGE_PREFIX = 'cupsir-dashboard.view.';

  const $ = (sel, root) => (root || document).querySelector(sel);
  const warned = new Set();
  function warnOnce(kind, name) {
    const key = `${kind}:${name}`;
    if (!warned.has(key)) { warned.add(key); console.warn(`[breadth] unknown ${kind} "${name}": ${kind === 'format' ? 'showing the raw value' : 'skipped'}`); }
  }

  // The view last chosen on a tab is kept in this browser, so a reload opens the same one.
  // Storage can be unavailable (private window, blocked site data): then nothing is
  // remembered and the tab opens in its default view, as if no choice had been made.
  function storedView(name) {
    if (!name) return null;
    try {
      const value = window.localStorage.getItem(VIEW_STORAGE_PREFIX + name);
      return VIEWS.includes(value) ? value : null;
    } catch (err) { return null; }
  }
  function storeView(name, view) {
    if (!name) return;
    try { window.localStorage.setItem(VIEW_STORAGE_PREFIX + name, view); } catch (err) { /* not remembered */ }
  }

  // ------------------------------------------------------------ formats

  const num = (v, digits) => Number(v).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const FORMATS = {
    state_chip: v => String(v).replace(/_/g, ' '),
    count: v => String(v),
    rank: v => `#${v}`,
    pct: v => `${num(v, 2)}%`,
    signed_pct: v => `${v > 0 ? '+' : ''}${num(v, 2)}%`,
    // A reading can never be at "0": the lowest of a sample is still one reading out of many.
    percentile: (v, labels) => `${Math.max(1, Math.round(v))}${labels.percentile_unit ? ' ' + labels.percentile_unit : ''}`,
    number: v => Number(v).toLocaleString('en-US', { maximumFractionDigits: 4 }),
  };

  function formatValue(format, value, labels) {
    if (value === null || value === undefined) return labels.na || 'N/A';
    const fn = FORMATS[format];
    if (!fn) { warnOnce('format', format); return String(value); }
    return fn(value, labels);
  }

  // A value of unknown kind, for the list of values in a detail panel.
  function formatPlain(value, labels) {
    if (value === null || value === undefined) return labels.na || 'N/A';
    if (typeof value === 'boolean') return (value ? labels.yes : labels.no) || String(value);
    if (typeof value === 'number') return value.toLocaleString('en-US', { maximumFractionDigits: 6 });
    return String(value);
  }

  // The envelope field `state` can be shown like any entry of `values`.
  const pick = (result, key) => (key === 'state' ? result.state : (result.values || {})[key]);
  const isOk = result => result && result.status === 'ok';
  // A result without a tone gets no colour class (cls() would turn it yellow).
  const toneClass = result => (isOk(result) && result.tone ? cls(result.tone) : '');

  function mainText(spec, result, labels) {
    if (!isOk(result)) return labels.na || 'N/A';
    return formatValue(spec.format, pick(result, spec.value_key), labels);
  }

  function secondaryText(spec, result, labels) {
    if (!isOk(result) || !spec.secondary_key) return '';
    const value = pick(result, spec.secondary_key);
    if (value === null || value === undefined) return '';
    return formatValue(spec.secondary_format || 'number', value, labels);
  }

  // ------------------------------------------------------------ charts

  const charts = [];   // { plot, box }

  function destroyChartsIn(root) {
    for (let i = charts.length - 1; i >= 0; i--) {
      if (root.contains(charts[i].box)) { charts[i].plot.destroy(); charts.splice(i, 1); }
    }
  }

  window.addEventListener('resize', () => {
    charts.forEach(c => c.plot.setSize({ width: c.box.clientWidth || 600, height: CHART_HEIGHT }));
  });

  /*
   * drawLineChart(box, series, opts)
   *   series: { xs: [unix seconds], lines: [{ label, values, width?, pointsOnly? }] }
   *   opts:   { levels?: [y values drawn as dashed lines], yRange?: [min, max], xLabel?: text,
   *             labelLevels?: write each level's value at the right end of its line }
   * Without a fixed range the y axis reaches every level, so a line is never off the chart.
   */
  function drawLineChart(box, series, opts) {
    opts = opts || {};
    const colorOf = i => SERIES_COLORS[(i - 1) % SERIES_COLORS.length];
    const isoDate = (u, v) => (v == null ? '--' : new Date(v * 1000).toISOString().slice(0, 10));
    const uSeries = [{ label: opts.xLabel || '', value: isoDate }];
    series.lines.forEach((line, i) => {
      const color = colorOf(i + 1);
      uSeries.push(line.pointsOnly
        ? { label: line.label, stroke: color, width: 0, points: { show: true, size: 11, fill: color, stroke: SURFACE, width: 2 } }
        : { label: line.label, stroke: color, width: line.width || 2, points: { show: false } });
    });
    const scales = { x: { time: true } };
    if (opts.yRange) scales.y = { range: opts.yRange };
    else if (opts.levels && opts.levels.length) {
      scales.y = { range: (u, min, max) => {
        const lo = Math.min(min, ...opts.levels), hi = Math.max(max, ...opts.levels);
        const pad = (hi - lo) * 0.05 || Math.abs(hi) * 0.05 || 1;
        return [lo - pad, hi + pad];
      } };
    }
    const plot = new uPlot({
      width: box.clientWidth || 600,
      height: CHART_HEIGHT,
      scales,
      axes: [
        { stroke: AXIS, grid: { stroke: GRID } },
        { stroke: AXIS, grid: { stroke: GRID }, size: 56 },
      ],
      series: uSeries,
      legend: { show: true, markers: { width: 2, stroke: (u, i) => colorOf(i), fill: (u, i) => (series.lines[i - 1].pointsOnly ? colorOf(i) : null) } },
      cursor: { points: { size: 7 } },
      hooks: {
        draw: [u => {
          if (!opts.levels || !opts.levels.length) return;
          const ctx = u.ctx;
          ctx.save();
          ctx.strokeStyle = 'rgba(148,163,184,0.45)';
          ctx.setLineDash([4, 4]);
          ctx.lineWidth = 1;
          opts.levels.forEach(level => {
            const y = u.valToPos(level, 'y', true);
            ctx.beginPath();
            ctx.moveTo(u.bbox.left, y);
            ctx.lineTo(u.bbox.left + u.bbox.width, y);
            ctx.stroke();
            if (opts.labelLevels) {
              ctx.fillStyle = AXIS;
              ctx.font = `${Math.round(11 * devicePixelRatio)}px sans-serif`;
              ctx.textAlign = 'right';
              ctx.fillText(String(level), u.bbox.left + u.bbox.width - 4, y - 4);
            }
          });
          ctx.restore();
        }],
      },
    }, [series.xs].concat(series.lines.map(l => l.values)), box);
    charts.push({ plot, box });
  }

  const toSeconds = date => Math.floor(new Date(date).getTime() / 1000);
  const column = (history, key) => history.map(p => (p[key] === undefined ? null : p[key]));
  const seriesLabel = (ind, key) => (ind.value_labels || {})[key] || key;

  function historyLines(ind, result, widthOf) {
    const keys = ind.detail_chart.series || [];
    return keys.map((key, i) => ({ label: seriesLabel(ind, key), values: column(result.history, key), width: widthOf(i) }));
  }

  // `extra.levels`: lines that belong to one row rather than to the indicator (a ratio pair
  // read against fixed values). They are labelled, as nothing else on the chart names them.
  function chartOptions(ind, labels, extra) {
    const own = (extra && extra.levels) || [];
    const levels = (ind.detail_chart.levels || []).concat(own);
    return { levels: levels.length ? levels : undefined, yRange: ind.detail_chart.y_range, xLabel: labels.date, labelLevels: own.length > 0 };
  }

  const CHARTS = {
    line(box, ind, result, labels, extra) {
      drawLineChart(box, { xs: result.history.map(p => toSeconds(p.date)), lines: historyLines(ind, result, () => 2) }, chartOptions(ind, labels, extra));
    },
    // First series is the price; the rest are its moving averages, drawn thinner.
    price_with_ma(box, ind, result, labels, extra) {
      drawLineChart(box, { xs: result.history.map(p => toSeconds(p.date)), lines: historyLines(ind, result, i => (i === 0 ? 2 : 1.25)) }, chartOptions(ind, labels, extra));
    },
    // The first series, plus a dot on every date listed in the result's events.
    line_with_markers(box, ind, result, labels, extra) {
      const lines = historyLines(ind, result, () => 2);
      const eventDates = new Set((result.events || []).map(e => e.date));
      const base = lines.length ? lines[0].values : [];
      lines.push({ label: ind.name_zh, pointsOnly: true, values: result.history.map((p, i) => (eventDates.has(p.date) ? base[i] : null)) });
      drawLineChart(box, { xs: result.history.map(p => toSeconds(p.date)), lines }, chartOptions(ind, labels, extra));
    },
  };

  // Called after the HTML holding `.chart-box[data-chart]` placeholders is in the page.
  function mountCharts(root, labels, lookup) {
    root.querySelectorAll('.chart-box[data-chart]').forEach(box => {
      const { ind, result, extra } = lookup(box.dataset.chart);
      const draw = CHARTS[ind.detail_chart.type];
      if (!draw) { warnOnce('chart type', ind.detail_chart.type); box.remove(); return; }
      if (typeof uPlot === 'undefined') { box.remove(); return; }   // chart library not loaded: text still shows
      draw(box, ind, result, labels, extra);
    });
  }

  // ------------------------------------------------------------ shared detail blocks

  function valuesList(ind, result, labels) {
    const names = ind.value_labels || {};
    const rows = Object.keys(names)
      .filter(key => isOk(result) && key in (result.values || {}))
      .map(key => `<div class="kv"><span>${esc(names[key])}</span><b>${esc(formatPlain(result.values[key], labels))}</b></div>`);
    return rows.length ? `<div class="kv-list">${rows.join('')}</div>` : '';
  }

  function expertView(ind, labels) {
    const items = (ind.expert_view || []).map(v => `<li>${esc(v)}</li>`).join('');
    const note = ind.disclaimer ? `<p class="muted breadth-note">${esc(ind.disclaimer)}</p>` : '';
    return `<h4>${esc(labels.expert_view_heading || '')}</h4><ul>${items}</ul>${note}`;
  }

  function chartSlot(ind, result, chartKey) {
    const hasData = ind.detail_chart && isOk(result) && (result.history || []).length > 1;
    return hasData ? `<div class="chart-box cot-chart-box" data-chart="${esc(chartKey)}"></div>` : '';
  }

  function latestDate(results) {
    const dates = results.filter(isOk).map(r => r.data_date).filter(Boolean).sort();
    return dates.length ? dates[dates.length - 1] : null;
  }

  function dataDateLine(results, labels) {
    const date = latestDate(results);
    return date ? `<p class="muted">${esc(labels.data_date || '')}：${esc(date)}</p>` : '';
  }

  /*
   * A row's reading guide (ratio pairs): what is compared, what each state usually means -
   * the current one marked - other situations worth watching, and a caveat. Every word comes
   * from the row and from meta (state_conditions, ui_labels); `state` is the row's current state.
   */
  function guideBlock(guide, meta, labels, state) {
    if (!guide) return '';
    const conditions = meta.state_conditions || {};
    const states = Object.keys(conditions).filter(s => guide.states && guide.states[s]).map(s => `
      <div class="guide-state${s === state ? ' current' : ''}">
        <div class="guide-state-head"><span class="chip">${esc(FORMATS.state_chip(s))}</span>${s === state && labels.guide_now ? `<span class="guide-now">${esc(labels.guide_now)}</span>` : ''}<span class="guide-cond">${esc(conditions[s])}</span></div>
        <div>${esc(guide.states[s])}</div>
      </div>`).join('');
    const signals = (guide.signals || []).map(item => `<li><b>${esc(item.condition)}</b><br>${esc(item.meaning)}</li>`).join('');
    return `<div class="pair-guide">
      <h4>${esc(labels.guide_heading || '')}</h4>
      ${guide.compare ? `<p class="guide-compare"><b>${esc(labels.guide_compare || '')}</b>　${esc(guide.compare)}</p>` : ''}
      ${states ? `<div class="guide-states">${states}</div>` : ''}
      ${signals ? `<h4>${esc(labels.guide_signals || '')}</h4><ul class="guide-signals">${signals}</ul>` : ''}
      ${guide.caveat ? `<p class="guide-caveat"><b>${esc(labels.guide_caveat || '')}</b>　${esc(guide.caveat)}</p>` : ''}
    </div>`;
  }

  function setTabLabels(labels) {
    document.querySelectorAll('.tab').forEach(tab => {
      const text = labels[`tab_${tab.dataset.tab}`];
      if (text) tab.textContent = text;
    });
  }

  // ------------------------------------------------------------ components

  const COMPONENTS = {
    // One small card per indicator, one line per subject. Click to open the detail below the cards.
    status_card(ind, payload) {
      const labels = payload.meta.ui_labels || {};
      const lines = ind.subjects.map(sid => {
        const subject = payload.meta.subjects.find(s => s.id === sid) || { name_zh: sid };
        const result = (payload.results[ind.id] || {})[sid];
        const secondary = secondaryText(ind, result, labels);
        return `<span class="card-row"><span>${esc(subject.name_zh)}</span><span class="card-value"><b class="${toneClass(result)}">${esc(mainText(ind, result, labels))}</b>${secondary ? `<small class="${toneClass(result)}">${esc(secondary)}</small>` : ''}</span></span>`;
      }).join('');
      return `<button class="status-card" data-id="${esc(ind.id)}"><span class="card-title">${esc(ind.name_zh)}</span>${lines}</button>`;
    },
    // One table cell per row.
    table_column(ind, row, labels) {
      const result = row.results[ind.id];
      const secondary = secondaryText(ind, result, labels);
      const title = isOk(result) ? '' : ` title="${esc(result ? result.reason : '')}"`;
      return `<td class="${toneClass(result)}"${title}>${esc(mainText(ind, result, labels))}${secondary ? `<small>${esc(secondary)}</small>` : ''}</td>`;
    },
  };

  function byComponent(indicators, component) {
    return (indicators || []).filter(ind => {
      if (!COMPONENTS[ind.component]) { warnOnce('component', ind.component); return false; }
      return ind.component === component;
    }).sort((a, b) => a.order - b.order);
  }

  // ------------------------------------------------------------ market: status cards

  function renderMarket(payload) {
    const box = $('#breadthCards');
    const labels = payload.meta.ui_labels || {};
    const inds = byComponent(payload.meta.indicators, 'status_card');
    if (!inds.length) { box.innerHTML = ''; return; }
    const all = inds.flatMap(ind => ind.subjects.map(sid => (payload.results[ind.id] || {})[sid]));
    box.innerHTML = `<div class="status-cards">${inds.map(ind => COMPONENTS.status_card(ind, payload)).join('')}</div>`
      + `<div id="breadthDetail" class="panel breadth-detail" hidden></div>${dataDateLine(all, labels)}`;

    const detail = $('#breadthDetail');
    const cards = box.querySelectorAll('.status-card');
    cards.forEach(card => card.onclick = () => {
      const wasOpen = card.classList.contains('active');
      cards.forEach(c => c.classList.remove('active'));
      destroyChartsIn(detail);
      if (wasOpen) { detail.hidden = true; detail.innerHTML = ''; return; }
      card.classList.add('active');
      const ind = inds.find(i => i.id === card.dataset.id);
      const blocks = ind.subjects.map(sid => {
        const subject = payload.meta.subjects.find(s => s.id === sid) || { name_zh: sid, ticker: '' };
        const result = (payload.results[ind.id] || {})[sid];
        return `<div class="subject-block">
          <div class="subject-head"><b>${esc(subject.name_zh)} <small class="muted-inline">${esc(subject.ticker)}</small></b><span class="chip ${toneClass(result)}">${esc(mainText(ind, result, labels))}</span></div>
          ${chartSlot(ind, result, sid)}
          ${valuesList(ind, result, labels)}
        </div>`;
      }).join('');
      detail.innerHTML = `<div class="detail-head"><div><h2>${esc(ind.name_zh)}</h2><p class="muted">${esc(ind.name)}</p></div></div>
        <div class="subject-grid">${blocks}</div>${expertView(ind, labels)}`;
      detail.hidden = false;
      mountCharts(detail, labels, sid => ({ ind, result: payload.results[ind.id][sid] }));
    });
  }

  // ------------------------------------------------------------ rows view (sector tab, COT tab)

  function sortKey(spec, ind, row) {
    const result = row.results[spec.indicator];
    if (!isOk(result)) return null;
    const value = pick(result, spec.value_key);
    if (value === null || value === undefined) return null;
    if (ind && ind.sort_order && spec.value_key === ind.value_key) {
      const position = ind.sort_order.indexOf(value);
      return position === -1 ? ind.sort_order.length : position;
    }
    return value;
  }

  // N/A rows always sink to the bottom, whatever the direction.
  function compareRows(a, b, spec, ind) {
    const x = sortKey(spec, ind, a), y = sortKey(spec, ind, b);
    if (x === null && y === null) return 0;
    if (x === null) return 1;
    if (y === null) return -1;
    const diff = typeof x === 'string' || typeof y === 'string' ? String(x).localeCompare(String(y)) : x - y;
    return spec.dir === 'desc' ? -diff : diff;
  }

  /*
   * One component for any payload with `meta.indicators` (columns) and `rows`, in two views:
   *   list  - the rows down the left (under their group titles when the payload has
   *           meta.groups), the selected row's charts stacked on the right. A row shows the
   *           values of the indicators that carry a `list` entry in the registry.
   *   table - every row against every indicator, sortable; a clicked row opens below it.
   * The two buttons that switch view appear when meta.ui_labels has both view names. The
   * view picked with them is remembered per tab (opts.remember) and used on the next load.
   *   opts: { toggle, split, table, detail, heading?: selectors; nameLabel, note, title?: keys of
   *           meta.ui_labels; remember: name under which this tab's view choice is stored }
   * Optional row fields: caption (shown under the name), tag (a small label beside it),
   * levels (extra chart lines for that row) and guide (see guideBlock).
   */
  function renderRows(payload, opts) {
    const toggleBox = $(opts.toggle), splitBox = $(opts.split), tableBox = $(opts.table), detailBox = $(opts.detail);
    const meta = payload.meta, labels = meta.ui_labels || {};
    const inds = byComponent(meta.indicators, 'table_column');
    const indById = Object.fromEntries(inds.map(i => [i.id, i]));
    const listSpecs = inds.filter(ind => ind.list).map(ind => Object.assign({ id: ind.id }, ind.list)).sort((a, b) => a.order - b.order);
    const groups = meta.groups || null;
    const groupIds = groups ? Object.keys(groups) : [];
    const caption = row => row.caption || (row.tickers || {}).subject || (row.cftc || {}).code || '';
    const tagOf = row => (row.tag ? `<span class="tag">${esc(row.tag)}</span>` : '');
    // The indicator whose main value is the row's state: the guide marks that state as current.
    const stateInd = inds.find(ind => ind.value_key === 'state');
    if (opts.heading && opts.title && labels[opts.title]) $(opts.heading).textContent = labels[opts.title];
    const defaultSort = meta.default_sort ? Object.assign({ column: meta.default_sort.indicator }, meta.default_sort) : null;
    const canSwitch = !!(toggleBox && labels.view_list && labels.view_table);
    // The list needs something to show beside each row and a way back to the table. A file
    // written before the registry had either (the page can be deployed ahead of the next
    // data refresh) opens as the table, exactly as it did before. With both views on offer,
    // the one chosen last time wins over the default (the list).
    const canList = canSwitch && listSpecs.length > 0;
    let view = canList ? (storedView(opts.remember) || 'list') : 'table';
    let sort = defaultSort;
    let openRow = null;

    function sortedRows(by) {
      const rows = payload.rows.map((row, i) => ({ row, i }));
      rows.sort((a, b) => {
        let diff = 0;
        if (by && by.column === NAME_COLUMN) {
          diff = a.row.name_zh.localeCompare(b.row.name_zh);
          if (by.dir === 'desc') diff = -diff;
        } else if (by && by.column === GROUP_COLUMN) {
          diff = groupIds.indexOf(a.row.group) - groupIds.indexOf(b.row.group);
          if (by.dir === 'desc') diff = -diff;
        } else if (by) {
          diff = compareRows(a.row, b.row, by, indById[by.indicator]);
          if (diff === 0 && meta.tie_break) diff = compareRows(a.row, b.row, meta.tie_break, indById[meta.tie_break.indicator]);
        }
        return diff || a.i - b.i;
      });
      return rows.map(r => r.row);
    }

    // `withDisclaimers`: the table view lists each indicator's disclaimer under the table.
    // The list view leaves them out here because every block already ends with its own.
    function footnotes(withDisclaimers) {
      const notes = (opts.note && labels[opts.note] ? `<p class="muted breadth-note">${esc(labels[opts.note])}</p>` : '')
        + (withDisclaimers ? [...new Set(inds.filter(ind => ind.disclaimer).map(ind => ind.disclaimer))].map(text => `<p class="muted breadth-note">${esc(text)}</p>`).join('') : '');
      const all = payload.rows.flatMap(row => inds.map(ind => row.results[ind.id]));
      return notes + dataDateLine(all, labels);
    }

    function drawToggle() {
      if (!canSwitch) return;
      const button = name => `<button data-view="${name}" class="${view === name ? 'active' : ''}">${esc(labels[`view_${name}`])}</button>`;
      toggleBox.innerHTML = button('list') + button('table');
      toggleBox.querySelectorAll('button').forEach(b => b.onclick = () => {
        if (b.dataset.view === view) return;
        setView(b.dataset.view);
        storeView(opts.remember, view);
      });
    }

    function drawTable() {
      const arrow = col => (sort && sort.column === col ? (sort.dir === 'desc' ? ' ▼' : ' ▲') : '');
      const head = `<th data-col="${NAME_COLUMN}">${esc(labels[opts.nameLabel] || '')}${arrow(NAME_COLUMN)}</th>`
        + (groups ? `<th data-col="${GROUP_COLUMN}" class="text-col">${esc(labels.group_column || '')}${arrow(GROUP_COLUMN)}</th>` : '')
        + inds.map(ind => `<th data-col="${esc(ind.id)}">${esc(ind.column_label)}${arrow(ind.id)}</th>`).join('');
      const body = sortedRows(sort).map(row => `<tr data-id="${esc(row.id)}" class="${row.id === openRow ? 'active' : ''}">
        <td>${esc(row.name_zh)}${tagOf(row)}<small>${esc(caption(row))}</small></td>
        ${groups ? `<td class="text-col">${esc(groups[row.group] || row.group || '')}</td>` : ''}
        ${inds.map(ind => COMPONENTS.table_column(ind, row, labels)).join('')}</tr>`).join('');
      tableBox.innerHTML = `<div class="table-scroll"><table class="breadth-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>${footnotes(true)}`;

      tableBox.querySelectorAll('th').forEach(th => th.onclick = () => {
        const col = th.dataset.col;
        if (sort && sort.column === col) {
          sort = Object.assign({}, sort, { dir: sort.dir === 'desc' ? 'asc' : 'desc' });
        } else if (col === NAME_COLUMN || col === GROUP_COLUMN) {
          sort = { column: col, dir: 'asc' };
        } else {
          const ind = indById[col];
          sort = { column: col, indicator: col, value_key: ind.value_key, dir: ind.sort_order ? 'asc' : 'desc' };
        }
        drawTable();
      });
      tableBox.querySelectorAll('tbody tr').forEach(tr => tr.onclick = () => {
        openRow = openRow === tr.dataset.id ? null : tr.dataset.id;
        drawTable();
        drawDetail();
      });
    }

    // The list keeps one order - the registry's default sort, otherwise the file's own - so a
    // row is always found in the same place. Sorting by other columns belongs to the table view.
    function listRows() {
      const rows = sortedRows(defaultSort);
      if (!groups) return [{ title: '', rows }];
      const sections = groupIds.map(id => ({ title: groups[id], rows: rows.filter(row => row.group === id) }));
      const ungrouped = rows.filter(row => !groupIds.includes(row.group));
      if (ungrouped.length) sections.push({ title: '', rows: ungrouped });
      return sections.filter(section => section.rows.length);
    }

    function drawList() {
      const sections = listRows();
      const ordered = sections.flatMap(section => section.rows);
      if (!ordered.some(row => row.id === openRow)) openRow = ordered.length ? ordered[0].id : null;
      const item = row => {
        const values = listSpecs.map(spec => {
          const result = row.results[spec.id];
          return `<b class="${toneClass(result)}">${esc(mainText(spec, result, labels))}</b>`;
        }).join('');
        const sub = row.caption ? `<small class="side-caption">${esc(row.caption)}</small>` : '';
        return `<button class="indicator side-item${row.id === openRow ? ' active' : ''}" data-id="${esc(row.id)}"><span>${esc(row.name_zh)}${tagOf(row)}${sub}</span><span class="side-values">${values}</span></button>`;
      };
      tableBox.innerHTML = `<div class="side-list">${sections.map(section =>
        `<section class="indicator-group">${section.title ? `<h3 class="group-title">${esc(section.title)}</h3>` : ''}${section.rows.map(item).join('')}</section>`).join('')}</div>`;
      tableBox.querySelectorAll('.side-item').forEach(b => b.onclick = () => {
        if (b.dataset.id === openRow) return;
        openRow = b.dataset.id;
        drawList();
        drawDetail();
        // On a narrow screen the charts sit under the whole list: bring them into view.
        if (detailBox.getBoundingClientRect().left <= tableBox.getBoundingClientRect().left + 1) {
          detailBox.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
    }

    function drawDetail() {
      destroyChartsIn(detailBox);
      const row = payload.rows.find(r => r.id === openRow);
      if (!row) { detailBox.innerHTML = ''; return; }
      const asList = view === 'list';
      // When every column carries the same checklist (one calculator, several lookbacks),
      // the checklist is shown once. In the table view those charts sit side by side; in the
      // list view every chart takes the full width, one under the other.
      const viewOf = ind => JSON.stringify([ind.expert_view, ind.disclaimer]);
      const sharedView = inds.length > 1 && inds.every(ind => viewOf(ind) === viewOf(inds[0]));
      const blocks = inds.map(ind => {
        const result = row.results[ind.id];
        const head = `<div class="subject-head"><b>${esc(ind.name_zh)} <small class="muted-inline">${esc(ind.name)}</small></b><span class="chip ${toneClass(result)}">${esc(mainText(ind, result, labels))}</span></div>`;
        // List view: the readings sit above their chart. Table view: below it, as before.
        const body = asList
          ? valuesList(ind, result, labels) + chartSlot(ind, result, ind.id)
          : chartSlot(ind, result, ind.id) + valuesList(ind, result, labels);
        return `<div class="subject-block${sharedView && !asList ? '' : ' stacked'}">${head}${body}${sharedView ? '' : expertView(ind, labels)}</div>`;
      }).join('');
      // A row whose own data is older than the newest in the file (one of its tickers lags)
      // says so under its name; the date line at the bottom shows only the newest date.
      const rowDate = latestDate(inds.map(ind => row.results[ind.id]));
      const fileDate = latestDate(payload.rows.flatMap(r => inds.map(ind => r.results[ind.id])));
      const lag = rowDate && fileDate && rowDate < fileDate ? `（${labels.data_date || ''}：${rowDate}）` : '';
      const subtitle = (row.caption || (row.tickers ? Object.values(row.tickers).join(' · ') : (row.cftc || {}).name || '')) + lag;
      const state = stateInd && isOk(row.results[stateInd.id]) ? row.results[stateInd.id].state : null;
      detailBox.innerHTML = `<div class="detail-head breadth-detail-head"><div><h2>${esc(row.name_zh)}${tagOf(row)}</h2><p class="muted">${esc(subtitle)}</p></div></div>`
        + (sharedView && !asList ? `<div class="subject-grid">${blocks}</div>` : blocks)
        + (sharedView ? expertView(inds[0], labels) : '')
        + guideBlock(row.guide, meta, labels, state)
        + (asList ? footnotes(false) : '');
      mountCharts(detailBox, labels, id => ({ ind: indById[id], result: row.results[id], extra: { levels: row.levels } }));
    }

    function setView(name) {
      view = name;
      if (splitBox) splitBox.classList.toggle('is-list', view === 'list');
      drawToggle();
      if (view === 'list') drawList(); else drawTable();
      drawDetail();
    }

    setView(view);
  }

  // ------------------------------------------------------------ loading

  const SOURCES = [
    { file: 'data/market_breadth.json', box: '#breadthCards', render: renderMarket },
    { file: 'data/sectors.json', box: '#sectorTable', render: p => renderRows(p, { toggle: '#sectorView', split: '#sectorSplit', table: '#sectorTable', detail: '#sectorDetail', nameLabel: 'sector_column', remember: 'sectors' }) },
    { file: 'data/cot.json', box: '#cotTable', render: p => renderRows(p, { toggle: '#cotView', split: '#cotSplit', table: '#cotTable', detail: '#cotDetail', nameLabel: 'cot_column', note: 'cot_note', remember: 'cot' }) },
    // An added section: its panel stays hidden until its file has loaded, so a page deployed
    // before the first data refresh that writes the file looks exactly as it did before.
    { file: 'data/pairs.json', box: '#pairTable', panel: '#pairPanel', render: p => renderRows(p, { toggle: '#pairView', split: '#pairSplit', table: '#pairTable', detail: '#pairDetail', heading: '#pairHeading', title: 'pair_heading', nameLabel: 'pair_column', note: 'pair_note', remember: 'pairs' }) },
  ];

  // Each file loads on its own: one failing never affects the other or the existing page.
  SOURCES.forEach(async source => {
    try {
      const payload = await load(source.file);
      setTabLabels((payload.meta || {}).ui_labels || {});
      if (source.panel) $(source.panel).hidden = false;
      source.render(payload);
    } catch (err) {
      console.warn(`[breadth] ${source.file}: ${err.message}`);
      if (source.panel) { $(source.panel).hidden = true; return; }
      const box = $(source.box);
      if (box) box.innerHTML = `<p class="muted breadth-error">${LOAD_ERROR}</p>`;
    }
  });
})();
