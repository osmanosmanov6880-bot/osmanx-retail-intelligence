const PALETTE=['#fb435c','#78a5f9','#9ab4d6','#ad7b9b','#72b8bd','#738096'];
export function lineChart(items){
  const width=700,height=248,left=42,right=15,top=15,bottom=28;
  const max=Math.max(1,...items.map(v=>v.visitors),...items.map(v=>v.purchases));
  const maxAxis=Math.ceil(max/25)*25;
  const px=(i)=>left+(i/Math.max(1,items.length-1))*(width-left-right);
  const py=(n)=>top+(1-n/maxAxis)*(height-top-bottom);
  const points=key=>items.map((d,i)=>`${px(i).toFixed(1)},${py(d[key]).toFixed(1)}`).join(' ');
  const grid=Array.from({length:5},(_,i)=>{const n=maxAxis*i/4;const y=py(n);return `<line x1="${left}" y1="${y}" x2="${width-right}" y2="${y}"/><text x="${left-10}" y="${y+4}" text-anchor="end">${Math.round(n)}</text>`}).join('');
  const area=`${left},${height-bottom} ${points('visitors')} ${width-right},${height-bottom}`;
  const labels=items.filter((_,i)=>i%2===0).map((d,i)=>`<text x="${px(i*2)}" y="${height-5}" fill="#8091a7" text-anchor="middle" font-size="11">${d.hour.slice(0,2)}</text>`).join('');
  return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Посетители и продажи по часам"><defs><linearGradient id="blueArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#4587e9" stop-opacity=".39"/><stop offset="100%" stop-color="#4587e9" stop-opacity="0"/></linearGradient></defs><g class="chart-grid">${grid}</g><polygon points="${area}" fill="url(#blueArea)"/><polyline class="line-a" points="${points('visitors')}"/><polyline class="line-b" points="${points('purchases')}"/>${labels}</svg>`;
}
export function barChart(items){
  const max=Math.max(1,...items.map(d=>d.visitors));
  return `<div style="display:flex;align-items:end;gap:8px;height:235px;padding:10px 5px 0;border-bottom:1px solid #334156">${items.map(v=>`<div title="${v.hour}: ${v.visitors} входов, ${v.purchases} чеков" style="display:flex;flex-direction:column;justify-content:end;align-items:center;flex:1;gap:6px;height:100%;min-width:0"><div style="height:${Math.max(2,100*v.visitors/max)}%;width:100%;max-width:36px;border-radius:5px 5px 0 0;background:linear-gradient(#5d90db,#28466a);position:relative;display:flex;align-items:flex-end;justify-content:center"><div style="background:linear-gradient(#f64b62,#912037);width:38%;height:${Math.max(0,100*v.purchases/Math.max(v.visitors,1))}%;border-radius:3px 3px 0 0"></div></div><small style="color:#889ab2;font-size:9px">${v.hour.slice(0,2)}</small></div>`).join('')}</div>`;
}
export function donut(reasons){
 const total=reasons.reduce((sum,r)=>sum+r.count,0);
 let current=0;
 const gradient=reasons.map((r,i)=>{const start=current;current+=100*r.count/Math.max(1,total);return `${PALETTE[i%PALETTE.length]} ${start.toFixed(2)}% ${current.toFixed(2)}%`}).join(',');
 const circle=total?`conic-gradient(${gradient})`:'conic-gradient(#26374c 0% 100%)';
 return `<div class="reason-wrap"><div class="donut" style="background:${circle}"><div class="donut-inner"><b>${total.toLocaleString('ru-RU')}</b><small>ответов<br>об отказах</small></div></div><div class="reason-legend">${reasons.length?reasons.map((r,i)=>`<div class="reason-row"><i class="reason-dot" style="background:${PALETTE[i%PALETTE.length]}"></i><span>${escapeTxt(r.label)}</span><b>${Math.round(r.count*100/total)}%</b></div>`).join(''):'<span class="muted">Причины пока не собраны</span>'}</div></div>`;
}
function escapeTxt(value){return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
