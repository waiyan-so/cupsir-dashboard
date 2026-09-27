async function load(path) { const r = await fetch(path); if (!r.ok) throw new Error(`Cannot load ${path}`); return r.json(); }
function cls(x) { return x === "positive" ? "positive" : (x === "negative" || x === "recession" ? "negative" : "warning"); }
function esc(v) { const d=document.createElement('div'); d.textContent=v ?? ''; return d.innerHTML; }
function renderDetail(x) {
  const history = (x.history || []).map(p => `<div class="bar-row"><span>${esc(p.date)}</span><div class="bar"><i style="width:${Math.min(Math.abs(Number(p.value)||0)*5,100)}%"></i></div><b>${esc(p.value)}</b></div>`).join('') || '<p>沒有歷史資料。</p>';
  document.querySelector('#indicatorDetail').innerHTML = `<div class="detail-head"><div><h2>${esc(x.name_zh)}</h2><p>${esc(x.name)}</p></div><div class="value ${cls(x.signal_color)}"><b>${esc(x.value)} ${esc(x.unit)}</b><span>${esc(x.signal)}</span></div></div><p>${esc(x.interpretation)}</p><h3>CupSir 建議檢查</h3><ul>${(x.checklist||[]).map(v=>`<li>${esc(v)}</li>`).join('')}</ul><h3>最近資料</h3><div class="mini-chart">${history}</div><p class="muted">資料日期：${esc(x.data_date)} · <a href="${esc(x.source_url)}" target="_blank" rel="noreferrer">${esc(x.source_name)}</a></p>`;
}
function renderList(items) {
  const box=document.querySelector('#indicatorList');
  box.innerHTML=items.map((x,i)=>`<button class="indicator ${i===0?'active':''}" data-id="${esc(x.id)}"><span>${esc(x.name_zh)}</span><small class="${cls(x.signal_color)}">${esc(x.signal)}</small></button>`).join('');
  box.querySelectorAll('button').forEach(b=>b.onclick=()=>{box.querySelectorAll('button').forEach(q=>q.classList.remove('active'));b.classList.add('active');renderDetail(items.find(x=>x.id===b.dataset.id));});
}
function renderEvents(items) { document.querySelector('#events').innerHTML=items.map(x=>`<div class="row"><b>${esc(x.date)}</b><div><strong>${esc(x.title_zh||x.title)}</strong><p>${esc(x.notes||'')}</p></div><span>${'⭐'.repeat(x.importance||1)}</span></div>`).join(''); }
function renderNews(items) { document.querySelector('#news').innerHTML=items.map(x=>`<article class="news"><a href="${esc(x.url)}" target="_blank" rel="noreferrer">${esc(x.title)}</a><small>${esc(x.source)} · ${esc(x.published_at)}</small><p>${esc(x.summary||'')}</p></article>`).join(''); }
function renderSummary(s) { document.querySelector('#summary').innerHTML=`<h3>${esc(s.headline)}</h3><p>${esc(s.macro)}</p><h3>市場情緒</h3><p>${esc(s.market_sentiment)}</p><h3>未來催化劑</h3><ul>${(s.catalysts||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul><h3>檢查清單</h3><ul>${(s.checklist||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul><p class="muted">${esc(s.disclaimer)}</p>`; }
async function init() { const [d,e,n,s]=await Promise.all([load('data/dashboard.json'),load('data/events.json'),load('data/news.json'),load('data/summary.json')]); document.querySelector('#updatedAt').textContent=`最後更新：${d.updated_at}`; const badge=document.querySelector('#overallSignal'); badge.textContent=`${d.overall_signal} · ${d.total_score}`; badge.className=`signal ${d.overall_signal==='BULLISH'?'positive':d.overall_signal==='BEARISH'?'negative':'warning'}`; renderList(d.indicators); if(d.indicators.length) renderDetail(d.indicators[0]); renderEvents(e); renderNews(n); renderSummary(s); }
init().catch(err=>document.body.insertAdjacentHTML('afterbegin',`<div class="error">${esc(err.message)}</div>`));
