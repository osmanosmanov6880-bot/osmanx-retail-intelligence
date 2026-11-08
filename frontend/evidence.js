/* OSMANX Retail Intelligence R0.9 | Evidence Lab.
 * Real API data only. Synthetic mode clearly marked. No personal tracking. */
const root=document.querySelector('#evidence-root');
const notice=document.querySelector('#evidence-toast');
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
const num=x=>new Intl.NumberFormat('ru-RU').format(Number(x||0));
const money=x=>x===null||x===undefined?'Нет достоверных данных':new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:2}).format(Number(x)/100);
const uuid=()=>crypto.randomUUID?.()||`r09-${Date.now()}-${Math.random().toString(36).slice(2)}`;
const iso=(offset=0)=>new Date(Date.now()+offset*86400000).toISOString().slice(0,10);
const state={tab:'radar',slug:'central',stores:[],config:{},data:null,days:14,financeStart:iso(-6),financeEnd:iso(),opened:null};
const tabs=[['radar','01 / Сигналы спроса'],['recoveries','02 / Возврат продаж'],['finance','03 / Финансы'],['protocols','04 / Эксперименты'],['dossiers','05 / Доказательства']];
let toastTimer;
const field=(name,label,type='text',value='',optional=false)=>`<label>${esc(label)}<input name="${esc(name)}" type="${esc(type)}" value="${esc(value)}" ${optional?'':'required'} /></label>`;
const area=(name,label,placeholder='')=>`<label>${esc(label)}<textarea name="${esc(name)}" placeholder="${esc(placeholder)}" required></textarea></label>`;
const select=(name,label,choices)=>`<label>${esc(label)}<select name="${esc(name)}">${choices.map(([id,label])=>`<option value="${esc(id)}">${esc(label)}</option>`).join('')}</select></label>`;
const button=(label,action,id='',primary=false)=>`<button type="button" class="evidence-button ${primary?'primary':''}" data-action="${esc(action)}" data-id="${esc(id)}">${esc(label)}</button>`;
const card=(title,html)=>`<section class="evidence-card"><h2>${esc(title)}</h2>${html}</section>`;
const alert=items=>(items||[]).map(t=>`<div class="evidence-alert">${esc(t)}</div>`).join('');
const empty=t=>`<div class="evidence-blank">${esc(t)}</div>`;
const metric=(label,note,value)=>`<div class="evidence-stat"><small>${esc(label)}</small><b>${value}</b><em>${esc(note)}</em></div>`;
const badge=(label,tone='')=>`<span class="evidence-pill ${tone}">${esc(label)}</span>`;
const row=(title,desc,tools='')=>`<div class="evidence-row"><div><strong>${title}</strong><small>${desc}</small></div><div class="actions">${tools}</div></div>`;
async function api(path,{method='GET',body,csv=false}={}){
 const headers={Accept:csv?'text/csv':'application/json'};
 const token=sessionStorage.getItem('osmanx_admin_token');if(token)headers.Authorization=`Bearer ${token}`;
 if(body!==undefined)headers['Content-Type']='application/json';
 const res=await fetch('/api'+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
 if(csv){if(!res.ok)throw new Error('Ошибка загрузки CSV: '+res.status);return res.blob()}
 const data=await res.json().catch(()=>({detail:'Некорректный ответ сервера'}));
 if(!res.ok)throw new Error(typeof data.detail==='string'?data.detail:'Ошибка API '+res.status);
 return data;
}
function toast(message,error=false){clearTimeout(toastTimer);notice.innerHTML=`<div class="evidence-toastbox ${error?'error':''}">${esc(message)}</div>`;toastTimer=setTimeout(()=>notice.innerHTML='',4500)}
function shell(){root.innerHTML=`<main class="app">
 <header class="top"><div><div class="brand">OSMAN<span>X</span></div><div class="brandline">Retail Intelligence · Evidence Lab R0.9</div></div>
 <div class="toplinks"><select id="lab-store" class="store-select" aria-label="Филиал">${state.stores.map(s=>`<option value="${esc(s.slug)}" ${s.slug===state.slug?'selected':''}>${esc(s.name)}</option>`).join('')}</select>
 <a href="/static/strategy.html" class="toplink primary">Центр стратегии</a><a href="/" class="toplink">Главная</a></div></header>
 <section class="evidence-intro"><div class="evidence-kicker">OSMANX / Executive Intelligence / R0.9</div><h1>Не просто цифры.<br>Проверяемые решения.</h1>
 <p>От запроса на отсутствующий размер — до подтверждённого чека и оценки эффекта. Каждая цифра имеет источник, а недостаток данных не скрывается красивым графиком.</p></section>
 ${state.config.demo?'<div class="banner">ДЕМО: данные искусственные. Не выдавать показатели за результаты реального магазина.</div>':''}
 <nav class="evidence-tabs" role="tablist" aria-label="Разделы доказательной аналитики">${tabs.map(([id,name])=>`<button role="tab" aria-selected="${state.tab===id}" data-tab="${id}">${name}</button>`).join('')}</nav>
 <div id="evidence-content"></div><footer class="evidence-footer">OSMANX WORLD · Финансовые выводы — только на основе чеков и достоверной себестоимости. Интерес покупателей не гарантирует продажи. Эксперименты показывают наблюдаемое изменение, а не доказанную причинность.</footer>
 </main>`}
async function load(){const s=encodeURIComponent(state.slug);let url='';
 if(state.tab==='radar')url=`/admin/r09/radar?slug=${s}&days=${state.days}`;
 if(state.tab==='recoveries')url=`/admin/r09/recoveries?slug=${s}`;
 if(state.tab==='finance')url=`/admin/r09/finance?slug=${s}&start=${state.financeStart}&end=${state.financeEnd}`;
 if(state.tab==='protocols')url=`/admin/r09/protocols?slug=${s}`;
 if(state.tab==='dossiers')url=`/admin/r09/dossiers?slug=${s}`;
 state.data=await api(url);render();}
async function init(){try{
 state.config=await api('/config');
 if(!state.config.demo&&!sessionStorage.getItem('osmanx_admin_token')){root.innerHTML='<main class="app"><section class="evidence-intro"><h1>Требуется вход</h1><p>Войдите в кабинет руководителя, чтобы открыть финансовые данные.</p><a class="evidence-button primary" href="/">Войти</a></section></main>';return}
 state.stores=await api('/admin/stores');if(!state.stores.length)throw new Error('Нет доступных филиалов');
 const requested=new URLSearchParams(location.search).get('store');state.slug=(state.stores.find(x=>x.slug===requested)||state.stores[0]).slug;
 shell();await load();
}catch(e){root.innerHTML=`<main class="app"><section class="evidence-intro"><h1>Не удалось загрузить Evidence Lab</h1><p>${esc(e.message)}</p><a class="evidence-button" href="/">Вернуться в кабинет</a></section></main>`}}
function render(){const target=root.querySelector('#evidence-content');if(!target)return;target.innerHTML=({radar:renderRadar,recoveries:renderRecoveries,finance:renderFinance,protocols:renderProtocols,dossiers:renderDossiers}[state.tab])()}
function renderRadar(){const d=state.data;return `<div class="evidence-stats">
 ${metric('Запросов за период','Не все превращаются в покупки',num(d.current_requests))}
 ${metric('Неуточнённых SKU','Не попадут в автоматическую закупку',num(d.ambiguous_sku_records))}
 ${metric('Требуют проверки','Запросы без свободного остатка',num(d.items.filter(x=>x.signal==='investigate').length))}
 ${metric('Уже есть в наличии','Проверить выкладку и доступность',num(d.items.filter(x=>x.signal==='stock_available').length))}</div>
 <div class="evidence-grid"><div class="evidence-stack">${card('Сравнить спрос',`<form data-form="radar" class="evidence-form">${select('days','Продолжительность двух периодов',[[7,'7 + 7 дней'],[14,'14 + 14 дней'],[30,'30 + 30 дней']])}<button class="evidence-button primary" type="submit">Обновить радар</button></form>`)}${card('Правила интерпретации',alert(d.warnings)+`<p class="evidence-muted">${esc(d.method)}</p>`)}</div><div class="evidence-stack">${card('Модели и размеры — фактические запросы',d.items.length?d.items.map(x=>row(esc(`${x.product} · ${x.size} · ${x.color}`),
  `SKU ${esc(x.sku||'не определён')} · запросы: ${x.previous} → ${x.current} · доступно здесь ${x.available_local} · в сети ${x.available_network} · в закупке ${x.open_order_units}`,
  badge((x.trend>0?'+':'')+x.trend+' запр.','')+badge(x.signal==='investigate'?'Разобрать':x.signal==='pipeline'?'В поставке':x.signal==='sku_unresolved'?'Уточнить SKU':'В наличии',x.signal==='investigate'?'red':'green'))).join(''):empty('За выбранный период неудовлетворённый спрос не зарегистрирован.'))}</div></div>`}
function renderRecoveries(){const d=state.data;return `<div class="evidence-grid"><div class="evidence-stack">${card('Создать план по запросу',`<p class="evidence-muted">Только для запроса с однозначно известным артикулом. Не создаёт продажу и не пишет клиенту.</p><form class="evidence-form" data-form="recovery">${select('demand_id','Необработанный запрос',d.candidates.map(x=>[x.id,`#${x.id} · ${x.product} · ${x.size}`]))}${select('action','Что проверяем?',[["stock_check","Наличие и выкладку"],["supplier_order","Поступление от поставщика"],["fitting_fix","Посадку / примерку"],["service_fix","Помощь консультанта"]])}<button class="evidence-button primary" type="submit" ${!d.candidates.length?'disabled':''}>Создать план</button></form>`)}${card('Критерий успеха',`<p class="evidence-muted">Операционное исправление фиксируется отдельным результатом. Для подтверждённой продажи необходим чек с соответствующим SKU, поэтому выручка не возникает из одного комментария менеджера.</p>`)}</div>
 <div class="evidence-stack">${card('Рабочие планы',d.items.length?d.items.map(x=>`<div class="evidence-row"><div><strong>№${x.id} · ${esc(x.product)} · ${esc(x.size)}</strong><small>SKU ${esc(x.sku)} · ${esc(x.action)} · ${esc(x.status)}${x.evidence?' · '+esc(x.evidence):''}</small></div><div class="actions">${x.status==='planned'?button('В работу','working',x.id):''}${['planned','working'].includes(x.status)?button('Оформить результат','edit-result',x.id,true):badge(x.outcome==='confirmed_sale'?'Продажа подтверждена':'Завершено','green')}</div></div>
 ${['planned','working'].includes(x.status)?`<form data-form="resolve" data-id="${x.id}" class="evidence-form evidence-mini" hidden>
 ${select('outcome','Результат',[["operational_fix","Операционное исправление"],["confirmed_sale","Подтверждённая покупка"]])}
 ${field('sale_id','ID кассового чека (только при продаже)','number','',true)}${area('evidence','Что подтверждает результат?','Укажите конкретное доказательство (15+ знаков)')}
 <button class="evidence-button primary" type="submit">Подтвердить результат</button></form>`:''}`).join(''):empty('Планов ещё нет. Начните с одного подтверждённого запроса.'))}</div></div>`}
function renderFinance(){const d=state.data;return `<div class="evidence-stats">
 ${metric('Чеки за период','Реально зарегистрированные операции',num(d.receipts))}
 ${metric('Сумма чеков','Без вычитания возвратов',money(d.gross_receipts_kopeks))}
 ${metric('Доля сверенных чеков','Товарные строки + себестоимость',d.cost_coverage_percent===null?'—':d.cost_coverage_percent+'%')}
 ${metric('Валовой вклад','Показывается только при полной сверке',money(d.gross_contribution_kopeks))}</div>
 <div class="evidence-grid"><div class="evidence-stack">${card('Период и методика',`<form data-form="finance" class="evidence-form"><div class="evidence-input-row">${field('start','Начало','date',state.financeStart)}${field('end','Конец','date',state.financeEnd)}</div><button class="evidence-button primary" type="submit">Сверить чеки</button></form><p class="evidence-muted">Суммы строк должны совпадать с суммой чека. Себестоимость 0 не считается подтверждённой. Запись о возврате не заменяет подтверждение банковского возврата.</p>`)}${card('Предупреждения',alert(d.warnings)||empty('Для данного набора записей предупреждений нет.'))}</div>
 <div>${card('Контроль целостности',row('Чеков с товарными строками',num(d.receipts_with_lines))+
 row('Полностью сверено',num(d.reconciled_receipts),badge('Проверено','green'))+
 row('Не прошли сверку',num(d.unmatched_receipts),badge('Требует проверки',d.unmatched_receipts?'red':''))+
 row('Расхождение суммы',num(d.amount_mismatches))+
 row('Неизвестная себестоимость',num(d.zero_cost_receipts))+
 row('Зарегистрированные возвраты',money(d.documented_returns_kopeks))+
 `<p class="evidence-muted">Сверенный вклад по части чеков: ${money(d.reconciled_contribution_kopeks)} — это не общая прибыль магазина, пока охват меньше 100%.</p>`)}</div></div>`}
function renderProtocols(){const d=state.data;const last=state.stores.filter(s=>s.slug!==state.slug);return `<div class="evidence-grid"><div class="evidence-stack">${card('Предварительно зарегистрировать эксперимент',`<p class="evidence-muted">Формулировка и интервалы фиксируются до расчёта результата. Периоды должны быть равными.</p>
 <form data-form="protocol" class="evidence-form">${field('title','Название теста','text','Новая раскладка')}
 ${area('hypothesis','Проверяемая гипотеза','Почему должно измениться число чеков на входы?')}
 ${select('metric','Показатель',[["check_rate","Чеков на 100 входов"],["receipt_per_entry","Выручка с одного входа, ₽"]])}
 ${select('source_mode','Источник входов',[["sensor","Датчик"],["manual","Ручной подсчёт"],["all","Все источники (осторожно)"]])}
 ${select('control_slug','Контрольный филиал',[["","Без контроля"],...last.map(x=>[x.slug,x.name])])}
 <div class="evidence-input-row">${field('before_start','До · начало','date',iso(-15))}${field('before_end','До · конец','date',iso(-9))}
 ${field('after_start','После · начало','date',iso(-7))}${field('after_end','После · конец','date',iso(-1))}</div>
 <button class="evidence-button primary" type="submit">Зарегистрировать эксперимент</button></form>`)}
 ${card('Методика',`<p class="evidence-muted">Сравнение показывает наблюдаемую разницу. Даже при наличии контрольного филиала причинность не доказана: учитывайте сезонность, акции, цены и погоду.</p>`)}</div>
 <div class="evidence-stack">${card('Протоколы и результаты',d.items.length?d.items.map(x=>`<div class="evidence-row"><div><strong>№${x.id} · ${esc(x.title)}</strong><small>${esc(x.hypothesis)} · ${esc(x.metric)} · ${esc(x.status)} · ${esc(x.before_start)}–${esc(x.after_end)}</small></div>
 <div class="actions">${button('Посмотреть данные','preview-protocol',x.id)}${x.status==='planned'?button('Зафиксировать','freeze-protocol',x.id,true):badge('Снимок сохранён','green')}</div></div><div id="evidence-protocol-${x.id}" class="evidence-mini evidence-muted">${x.result?`SHA ${esc(x.result_sha||'')} · ${esc(x.result.result?.verdict||'завершён')}`:''}</div>`).join(''):empty('Добавьте первый проверяемый эксперимент.'))}</div></div>`}
function renderDossiers(){const d=state.data;return `<div class="evidence-grid"><div class="evidence-stack">${card('Сформировать доказательный пакет',`<p class="evidence-muted">Фиксирует финансовую сверку, сигналы спроса, состояние кейсов и список экспериментов в одном неизменяемом JSON-снимке с SHA-256.</p>
 <form data-form="dossier" class="evidence-form"><div class="evidence-input-row">${field('start','С','date',state.financeStart)}${field('end','По','date',state.financeEnd)}</div><button class="evidence-button primary" type="submit">Сохранить отчёт</button></form>`)}
 ${card('Ограничения',`<p class="evidence-muted">Радар оценивает скользящие 14 дней, а финансовый отчёт — выбранный диапазон. Копия данных неизменяема после сохранения. Для внешнего аудита нужны исходные кассовые и складские документы.</p>`)}</div>
 <div class="evidence-stack">${card('Архив отчётов',d.items.length?d.items.map(x=>row('Пакет №'+x.id,`${esc(x.start)} — ${esc(x.end)} · SHA-256 ${esc(x.sha256.slice(0,20))}…`,button('Просмотреть','view-dossier',x.id)+button('Скачать CSV','csv-dossier',x.id,true))).join(''):empty('Снимков нет. Создайте первый отчёт.'))}<div id="evidence-dossier-preview" class="evidence-mini evidence-muted"></div></div></div>`}
root.addEventListener('change',async e=>{if(e.target.id==='lab-store'){state.slug=e.target.value;try{await load()}catch(error){toast(error.message,true)}}});
root.addEventListener('click',async e=>{
 const tab=e.target.closest('[data-tab]');if(tab){state.tab=tab.dataset.tab;root.querySelectorAll('[data-tab]').forEach(x=>x.setAttribute('aria-selected',String(x===tab)));try{await load()}catch(err){toast(err.message,true)}return}
 const b=e.target.closest('[data-action]');if(!b)return;const action=b.dataset.action,id=Number(b.dataset.id||0);
 if(action==='edit-result'){const form=root.querySelector(`[data-form=resolve][data-id="${id}"]`);if(form)form.hidden=!form.hidden;return}
 b.disabled=true;
 try{
  if(action==='working')await api(`/admin/r09/recoveries/${id}`,{method:'PATCH',body:{status:'working'}});
  else if(action==='preview-protocol'){
   const d=await api(`/admin/r09/protocols/${id}/preview`);const target=root.querySelector('#evidence-protocol-'+id);
   target.innerHTML=`<div class="evidence-muted"><strong>До:</strong> ${esc(d.before.value??'Нет данных')} · <strong>После:</strong> ${esc(d.after.value??'Нет данных')} · <strong>Разница:</strong> ${esc(d.delta??'—')}${d.difference_in_differences!==null?' · Контрольная поправка: '+esc(d.difference_in_differences):''}</div>${alert(d.warnings)}<p>${esc(d.disclaimer)}</p>`;return;
  }else if(action==='freeze-protocol'){
   const evidence=prompt('Какие реальные наблюдения подтверждают вывод? (20+ символов)');if(evidence===null)return;
   await api(`/admin/r09/protocols/${id}/evaluate`,{method:'POST',body:{evidence}});
  }else if(action==='view-dossier'){
   const d=await api(`/admin/r09/dossiers/${id}`);const p=d.payload;root.querySelector('#evidence-dossier-preview').innerHTML=`<h3>Пакет №${id}</h3><p>Чеки: ${num(p.financial_integrity.receipts)} · Спрос: ${num(p.radar.current_requests)} · Себестоимость: ${p.financial_integrity.cost_coverage_percent??'—'}% сверено</p>${alert(p.financial_integrity.warnings)}<p>SHA-256: ${esc(d.sha256)}</p>`;return;
  }else if(action==='csv-dossier'){
   const blob=await api(`/admin/r09/dossiers/${id}/export.csv`,{csv:true});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`OSMANX-evidence-${id}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),3000);return;
  }
  toast('Изменение записано');await load();
 }catch(err){toast(err.message,true)}finally{b.disabled=false}
});
root.addEventListener('submit',async e=>{
 const form=e.target.closest('form');if(!form?.dataset.form)return;e.preventDefault();const submit=form.querySelector('[type=submit]');if(submit)submit.disabled=true;
 const data=Object.fromEntries(new FormData(form));
 try{
  if(form.dataset.form==='radar'){state.days=Number(data.days);await load();return}
  if(form.dataset.form==='finance'){state.financeStart=data.start;state.financeEnd=data.end;await load();return}
  if(form.dataset.form==='recovery')await api('/admin/r09/recoveries',{method:'POST',body:{slug:state.slug,request_id:uuid(),demand_id:Number(data.demand_id),action:data.action}});
  if(form.dataset.form==='resolve')await api(`/admin/r09/recoveries/${form.dataset.id}`,{method:'PATCH',body:{status:'resolved',outcome:data.outcome,sale_id:data.sale_id?Number(data.sale_id):null,evidence:data.evidence}});
  if(form.dataset.form==='protocol')await api('/admin/r09/protocols',{method:'POST',body:{slug:state.slug,request_id:uuid(),...data,control_slug:data.control_slug||null}});
  if(form.dataset.form==='dossier')await api('/admin/r09/dossiers',{method:'POST',body:{slug:state.slug,request_id:uuid(),start:data.start,end:data.end}});
  toast('Сохранено в базе магазина');await load();
 }catch(err){toast(err.message,true)}finally{if(submit)submit.disabled=false}
});
init();
