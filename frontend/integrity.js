/* OSMANX R1.4 Integrity Center: every action invokes the authenticated API. */
const root=document.querySelector('#integrity-app');
const toast=document.querySelector('#integrity-toast');
const state={tab:'board',slug:'central',days:7,stores:[],data:{}};
const escapeHtml=v=>String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
const fmt=v=>new Intl.NumberFormat('ru-RU').format(Number(v)||0);
const rub=v=>new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB'}).format((Number(v)||0)/100);
const label={matched:'Совпало',missing:'Не найдено',amount_conflict:'Расхождение',
             pending:'Ожидает',reviewed:'Проверено',rejected:'Отклонено',
             open:'Открыт',acknowledged:'В работе',resolved:'Закрыт'};
const tabs=[['board','Директор'],['inbox','Очередь кассы'],['reconciliation','Сверка'],['gifts','Расходы'],['incidents','Отклонения']];
function notify(message){toast.textContent=message;setTimeout(()=>toast.textContent='',4500)}
async function api(path,{method='GET',body}={}){
  const headers={Accept:'application/json'};
  const token=sessionStorage.getItem('osmanx_admin_token');
  if(token)headers.Authorization=`Bearer ${token}`;
  if(body!==undefined)headers['Content-Type']='application/json';
  const res=await fetch(`/api${path}`,{method,headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
  const value=await res.json().catch(()=>({detail:'Не удалось прочитать ответ сервера'}));
  if(!res.ok)throw Error(typeof value.detail==='string'?value.detail:`HTTP ${res.status}`);
  return value;
}
const row=(title,sub,action='')=>`<div class="row"><div><strong>${escapeHtml(title)}</strong><small>${escapeHtml(sub)}</small></div>${action}</div>`;
const card=(title,inner)=>`<section class="card"><h2>${escapeHtml(title)}</h2>${inner}</section>`;
const form=(title,body,submit)=>card(title,`<form id="form-main">${body}<button class="btn primary" type="submit">${submit}</button></form>`);
const kpi=(title,value)=>`<div class="kpi"><small>${escapeHtml(title)}</small><strong>${escapeHtml(value)}</strong></div>`;
const field=(title,name,placeholder='',type='text',required=true)=>`<label>${escapeHtml(title)}<input name="${name}" type="${type}" placeholder="${escapeHtml(placeholder)}" ${required?'required':''}></label>`;
function linkCsv(path,labelText){return `<button class="btn ghost" data-export="${escapeHtml(path)}">${escapeHtml(labelText)}</button>`}
async function downloadCsv(path){
 const headers={Accept:'text/csv'};
 const token=sessionStorage.getItem('osmanx_admin_token');
 if(token)headers.Authorization=`Bearer ${token}`;
 const res=await fetch(path,{headers,cache:'no-store'});
 if(!res.ok)throw Error(`CSV export: HTTP ${res.status}`);
 const blob=await res.blob();
 const url=URL.createObjectURL(blob);
 const anchor=document.createElement('a');anchor.href=url;
 anchor.download=path.includes('reconciliation')?'osmanx-reconciliation.csv':'osmanx-integrity.csv';
 document.body.append(anchor);anchor.click();anchor.remove();
 setTimeout(()=>URL.revokeObjectURL(url),3000);
}
function shell(){
 root.innerHTML=`<header><div><div class="brand">OSMAN<span>X</span></div><div class="meta">RETAIL INTELLIGENCE / R1.4</div></div><a href="/">Основной кабинет</a></header>
 <main><section class="hero"><div><div class="eyebrow">INTEGRITY CENTER</div><h1>Данные под контролем.</h1><p>Сверка кассовых событий, подтверждения вручённых подарков и разбор отклонений без выдуманных финансовых результатов.</p></div>
 <select id="branch" class="store">${state.stores.map(s=>`<option value="${escapeHtml(s.slug)}" ${s.slug===state.slug?'selected':''}>${escapeHtml(s.name)}</option>`).join('')}</select></section>
 <nav class="tabs" role="tablist">${tabs.map(([id,title])=>`<button role="tab" data-tab="${id}" aria-selected="${id===state.tab}">${title}</button>`).join('')}</nav>
 <div id="content"></div><footer>OSMANX WORLD · Сверка не инициирует оплату, не меняет остатки и не запускает кассу. Операционные расходы не являются аудитом прибыли.</footer></main>`;
 root.querySelector('#branch').onchange=e=>{state.slug=e.target.value;refresh()};
 root.querySelectorAll('[data-tab]').forEach(x=>x.onclick=()=>{state.tab=x.dataset.tab;refresh()});
}
async function renderBoard(target,slug){
 const x=await api(`/admin/r14/board?slug=${slug}&days=${state.days}`);
 target.innerHTML=`<div class="grid">${kpi('Чеков в базе',fmt(x.receipts))}${kpi('Выручка по чекам',rub(x.revenue_kopeks))}${kpi('Учтённые подарки*',rub(x.gift_cost_kopeks))}${kpi('Непроверенные события',fmt(x.inbox_pending))}</div>
 <div class="body-grid">${card('Качество данных',`${row('Совпали с чеками',fmt(x.reconciliation.matched))}${row('Не найдено в кассе',fmt(x.reconciliation.missing))}${row('Расхождение суммы',fmt(x.reconciliation.amount_conflicts))}${(x.warnings||[]).map(w=>`<p class="warning">${escapeHtml(w)}</p>`).join('')||'<p class="status">Новых предупреждений нет</p>'}`)}
 ${card('Доказательность',`${row('Бонус с актом и купоном',fmt(x.gift_evidence.linked))}${row('Ручная запись, требует проверки',fmt(x.gift_evidence.manual))}${row('Отменённые записи',fmt(x.gift_evidence.reversed))}${row('Открытые инциденты',fmt(x.incidents.open))}<p class="info">${escapeHtml(x.source_note)}</p><label>Период<select id="days">${[1,7,14,30,90].map(d=>`<option ${state.days===d?'selected':''} value="${d}">${d} дней</option>`).join('')}</select></label>${linkCsv(`/api/admin/r14/board/export.csv?slug=${slug}&days=${state.days}`,'CSV отчёт')}`)}</div>`;
 target.querySelector('#days').onchange=e=>{state.days=Number(e.target.value);refresh()};
}
async function renderInbox(target,slug){
 const x=await api(`/admin/r14/inbox?slug=${slug}`);
 target.innerHTML=`<div class="body-grid">${card('События из источников',x.items.map(it=>row(`${it.kind==='receipt'?'Чек':'Остаток'} · ${it.external_id}`,`${it.source} · ${label[it.status]||it.status}`,it.status==='pending'?`<div class="buttons"><button class="btn" data-review="${it.id}" data-status="reviewed">Проверить</button><button class="btn ghost" data-review="${it.id}" data-status="rejected">Отклонить</button></div>`:'')).join('')||'<p class="empty">Пакетов нет</p>')}
 ${form('Зарегистрировать событие',`${field('Источник','source','manual')}${field('Внешний номер','external_id','receipt-001')}<label>Тип<select name="kind"><option value="receipt">Чек</option><option value="stock">Остаток</option></select></label><label>Обезличенные данные JSON<textarea name="payload" required>{"amount_kopeks":100000,"occurred_at":"2026-11-08T10:00:00+00:00"}</textarea></label>`,'Добавить в очередь')}</div>`;
 target.querySelector('input[name=source]').value='manual';
 target.querySelector('#form-main').onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.target));try{d.payload=JSON.parse(d.payload);await api('/admin/r14/inbox',{method:'POST',body:{...d,slug:state.slug}});notify('Событие добавлено');refresh()}catch(err){notify(err.message)}};
 target.querySelectorAll('[data-review]').forEach(button=>button.onclick=async()=>{
   const note=prompt('Основание проверки события (от 3 символов):','Проверено по журналу кассы');if(note===null)return;
   try{await api(`/admin/r14/inbox/${button.dataset.review}/review`,{method:'POST',body:{status:button.dataset.status,note}});notify('Решение записано');refresh()}catch(err){notify(err.message)}
 });
}
async function renderReconciliation(target,slug){
 const [summary,details]=await Promise.all([api(`/admin/r14/reconciliation?slug=${slug}&days=${state.days}`),api(`/admin/r14/reconciliation/items?slug=${slug}&days=${state.days}`)]);
 target.innerHTML=`<div class="grid">${kpi('Всего сообщений',fmt(summary.total))}${kpi('Сверено',fmt(summary.matched))}${kpi('Не найдено',fmt(summary.missing))}${kpi('Конфликты',fmt(summary.amount_conflicts))}</div>
 <div class="body-grid">${card('Реестр расхождений',`${details.items.filter(it=>it.comparison!=='matched').map(it=>row(`${it.external_id} · ${label[it.comparison]}`,`${it.source} · ожидается ${rub(it.expected_kopeks)} · в базе ${it.recorded_kopeks===null?'нет':rub(it.recorded_kopeks)}`)).join('')||'<p class="status">В полученных событиях расхождений нет</p>'}<p class="info">${escapeHtml(details.truncated?'Отображаются только первые 200 событий':'Сравнение выполнено по всем событиям периода')}</p>`)}
 ${card('Методика',`<p>${escapeHtml(summary.note)}</p><p class="info">Внешний номер и сумма сравниваются с существующей записью чека. Не найденные продажи не добавляются автоматически.</p>${linkCsv(`/api/admin/r14/reconciliation/export.csv?slug=${slug}&days=${state.days}`,'Скачать сверку CSV')}`)}</div>`;
}
async function renderGifts(target,slug){
 const x=await api(`/admin/r14/gifts?slug=${slug}`);
 target.innerHTML=`<div class="body-grid">${card('Подтверждённые расходы',x.items.map(it=>row(`${it.campaign} · ${rub(it.cost_kopeks)}`,`${it.reference} · ${it.status} · ${it.claim_id?'связано с купоном':'ручная запись'}`,it.status==='confirmed'?`<button class="btn ghost" data-reverse="${it.id}">Сторнировать</button>`:'')).join('')||'<p class="empty">Записей нет</p>')}
 ${form('Учёт подарка',`${field('Документ выдачи','reference')}${field('Название кампании','campaign')}${field('Фактическая стоимость в копейках','cost_kopeks','','number')}${field('ID проверенного купона (необязательно)','coupon_claim_id','','number',false)}<label>Основание<textarea name="note" required></textarea></label>`,'Зафиксировать')}</div>`;
 target.querySelector('#form-main').onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.target));try{await api('/admin/r14/gifts',{method:'POST',body:{...d,slug:state.slug,cost_kopeks:Number(d.cost_kopeks),coupon_claim_id:d.coupon_claim_id?Number(d.coupon_claim_id):null}});notify('Запись о расходе сохранена');refresh()}catch(err){notify(err.message)}};
 target.querySelectorAll('[data-reverse]').forEach(button=>button.onclick=async()=>{const reason=prompt('Причина сторно (не менее 5 символов):');if(reason===null)return;try{await api(`/admin/r14/gifts/${button.dataset.reverse}/reverse?reason=${encodeURIComponent(reason)}`,{method:'POST'});notify('Запись сторнирована');refresh()}catch(err){notify(err.message)}});
}
async function renderIncidents(target,slug){
 const x=await api(`/admin/r14/incidents?slug=${slug}`);
 target.innerHTML=`<div class="body-grid">${card('Журнал отклонений',x.items.map(it=>row(it.title,`${it.severity} · ${label[it.status]||it.status}`,`<div class="buttons"><button class="btn ghost" data-history="${it.id}">История</button>${it.status==='resolved'?'':`<button class="btn" data-incident="${it.id}" data-status="${it.status==='open'?'acknowledged':'resolved'}">${it.status==='open'?'Принять':'Закрыть'}</button>`}</div>`)).join('')||'<p class="empty">Отклонений пока нет</p>')}
 ${card('Поиск отклонений',`<p>Проверка очереди, сверки чеков и подтверждения подарков. Повторный сигнал возвращает закрытый инцидент в работу.</p><button class="btn primary" id="sync">Найти отклонения</button><div id="history-result" aria-live="polite"></div>`)}</div>`;
 target.querySelector('#sync').onclick=async()=>{try{await api(`/admin/r14/incidents/sync?slug=${slug}`,{method:'POST'});notify('Сигналы проверены');refresh()}catch(err){notify(err.message)}};
 target.querySelectorAll('[data-incident]').forEach(button=>button.onclick=async()=>{
   const note=prompt('Какие действия выполнены? (от 5 символов):','Рассмотрено ответственным сотрудником');if(note===null)return;
   try{await api(`/admin/r14/incidents/${button.dataset.incident}`,{method:'POST',body:{status:button.dataset.status,note}});notify('Действие сохранено');refresh()}catch(err){notify(err.message)}
 });
 target.querySelectorAll('[data-history]').forEach(button=>button.onclick=async()=>{try{
   const h=await api(`/admin/r14/incidents/${button.dataset.history}/history`);
   const targetHistory=target.querySelector('#history-result');
   targetHistory.innerHTML=`<h3>История</h3>${h.items.map(it=>row(`${it.previous_status||'—'} → ${it.next_status}`,`${it.evidence} · ${it.recorded_at}`)).join('')}`;
 }catch(err){notify(err.message)}});
}
async function refresh(){shell();const target=root.querySelector('#content'),slug=encodeURIComponent(state.slug);
 try{if(state.tab==='board')await renderBoard(target,slug);
 else if(state.tab==='inbox')await renderInbox(target,slug);
 else if(state.tab==='reconciliation')await renderReconciliation(target,slug);
 else if(state.tab==='gifts')await renderGifts(target,slug);
 else if(state.tab==='incidents')await renderIncidents(target,slug);
 target.querySelectorAll('[data-export]').forEach(b=>b.onclick=async()=>{try{await downloadCsv(b.dataset.export)}catch(err){notify(err.message)}});
 }catch(err){target.innerHTML=`<div class="warning">${escapeHtml(err.message)}. Проверьте вход в кабинет директора.</div>`}}
async function start(){try{const res=await api('/admin/stores');state.stores=Array.isArray(res)?res:(res.items||res.stores||[]);if(state.stores.length&&!state.stores.some(x=>x.slug===state.slug))state.slug=state.stores[0].slug}catch{}refresh()}
start();
