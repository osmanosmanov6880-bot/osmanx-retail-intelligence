import {MONEY,NUMBER,PERCENT,product,STORES,FUNNEL_STAGES,funnelData,opportunityMetrics} from './model.mjs';
export const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const icon=(name,size=18)=>{
 const p={
  grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  arrow:'<path d="M5 12h14m-7-7 7 7-7 7"/>',
  chevron:'<path d="m9 18 6-6-6-6"/>',
  left:'<path d="m15 18-6-6 6-6"/>',
  activity:'<path d="M3 12h4l3-7 4 14 3-7h4"/>',
  target:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  chart:'<path d="M3 3v18h18M7 16l4-4 3 2 6-8"/>',
  layers:'<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M8 8h8M8 12h8M8 16h5"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  shield:'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m8 12 3 3 5-6"/>',
  shops:'<path d="M3 10 5 3h14l2 7v11H3zM3 10h18M8 21v-7h8v7"/>',
  dots:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  play:'<path d="m8 5 12 7-12 7z"/>',
  pause:'<path d="M8 5v14M16 5v14"/>',
  download:'<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  bolt:'<path d="M13 2 4 14h7l-1 8 10-12h-7z"/>',
  menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
  close:'<path d="M5 5l14 14M19 5 5 19"/>',
  check:'<path d="m4 12 5 5L20 6"/>',
  search:'<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>',
  file:'<path d="M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h7"/>',
  info:'<circle cx="12" cy="12" r="10"/><path d="M12 10v7M12 7h.01"/>',
  scatter:'<circle cx="5" cy="17" r="2"/><circle cx="9" cy="7" r="2"/><circle cx="17" cy="13" r="2"/><circle cx="20" cy="5" r="2"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
  settings:'<path d="M4 7h16M4 17h16M9 4v6M15 14v6"/>',
  people:'<path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  trend:'<path d="M3 17 9 11l4 4 8-8M15 7h6v6"/>'
 };return `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round">${p[name]||p.grid}</svg>`;
};
export function lineChart(values,{height=190,price=false}={}) {
 const w=780,h=height,pad=16;let min=Math.min(...values,0),max=Math.max(...values,1);if(max===min)max=min+1;
 const points=values.map((v,i)=>[pad+(i/Math.max(1,values.length-1))*(w-2*pad),h-pad-(v-min)/(max-min)*(h-2*pad)]);
 const path=points.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
 const area=path+` L${w-pad} ${h} L${pad} ${h} Z`;
 const lines=[.25,.5,.75].map(x=>`<path d="M${pad} ${h*x}H${w-pad}" stroke="#26384a" stroke-dasharray="3 8"/>`).join('');
 const title=price?`Пик ${MONEY(max)}`:`Пик ${NUMBER(max)}`;
 return `<div class="line-chart" role="img" aria-label="Динамика: ${values.length} периодов; ${title}"><svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><defs><linearGradient id="linefill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#55dcc2" stop-opacity=".23"/><stop offset="1" stop-color="#55dcc2" stop-opacity="0"/></linearGradient></defs>${lines}<path d="${area}" fill="url(#linefill)"/><path d="${path}" stroke="#67e7c9" stroke-width="3" fill="none" stroke-linejoin="round" stroke-linecap="round"/></svg></div>`;
}
export function barViz(rows,maxHeight=180) {
 const max=Math.max(1,...rows.map(x=>x.value));
 return `<div class="mini-bars" style="height:${maxHeight}px">${rows.map((x,i)=>`<button title="${esc(x.label)}: ${NUMBER(x.value)}" class="bar-wrap" data-action="select-bar" data-id="${esc(x.id??i)}" type="button"><div class="mini-bar" style="height:${Math.max(3,x.value/max*100)}%"></div><span>${esc(x.label)}</span></button>`).join('')}</div>`;
}
export function funnelMarkup(scope,active='request',prefix='') {
 const values=funnelData(scope);const total=values[0]||1;
 return `<div class="funnel-visual">${FUNNEL_STAGES.map((st,i)=>`<button type="button" class="funnel-row ${st.id===active?'is-active':''}" data-action="funnel-stage" data-stage="${st.id}">
  <span class="funnel-order">0${i+1}</span><span class="funnel-body"><span class="funnel-label">${st.name}</span><span class="funnel-track"><span style="width:${values[i]/total*100}%"></span></span></span><b>${NUMBER(values[i])}</b>${icon('chevron',16)}
 </button>`).join('')}</div><p class="funnel-detail">${esc(FUNNEL_STAGES.find(s=>s.id===active)?.hint||'')} · ${values[0]?PERCENT(values[3]/values[0]):'—'} от запросов дошли до покупки</p>`;
}
export function opportunityMap(scope,selected) {
 const opportunities=opportunityMetrics(scope);
 const max=Math.max(1,...opportunities.filter(x=>x.estimate!=null).map(x=>x.estimate));
 return `<div class="opportunity-visual"><div class="opportunity-head"><span>КОММЕРЧЕСКИЕ СИГНАЛЫ</span><span>РАСЧЁТНЫЙ ПОТЕНЦИАЛ</span></div>${opportunities.map(o=>`<button type="button" class="opp-row ${selected===o.id?'selected':''}" data-action="opp-select" data-id="${o.id}">
   <span class="opp-label"><i class="opp-dot"></i><span>${esc(o.label)}<small>${NUMBER(o.count)} сигналов · ${esc(o.uncertainty)}</small></span></span><span class="opp-measure"><span class="opp-back"><span style="width:${o.estimate===null?0:Math.max(4,o.estimate/max*100)}%"></span></span><strong>${o.estimate===null?'—':MONEY(o.estimate)}</strong></span>
 </button>`).join('')}</div>`;
}
export function sourceTag(type='Факт'){return `<span class="source-tag ${type==='Факт'?'factual':type==='Оценка'?'estimate':type==='Гипотеза'?'hypothesis':'forecast'}">${esc(type)}</span>`;}
export function storeName(id){return STORES.find(s=>s.id===id)?.short||id;}
export function emptyState(text='Для текущих фильтров наблюдений нет.'){return `<div class="empty-state">${icon('info',19)}<span>${esc(text)}</span></div>`;}
export function rawTable(rows,headers){return rows.length?`<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${esc(h[0])}</th>`).join('')}</tr></thead><tbody>${rows.slice(0,16).map(row=>`<tr>${headers.map((h)=>`<td>${esc(typeof h[1]==='function'?h[1](row):row[h[1]])}</td>`).join('')}</tr>`).join('')}</tbody></table>${rows.length>16?`<p class="small muted pad-bottom">Показаны 16 из ${NUMBER(rows.length)} событий. Фильтры уточняют выборку.</p>`:''}</div>`:emptyState();}
