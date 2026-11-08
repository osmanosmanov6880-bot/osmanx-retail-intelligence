/* OSMANX Retail Desk R1.2: five fully API-backed workflows. */
const root=document.querySelector('#desk-root'),toastNode=document.querySelector('#desk-toast');
const state={tab:'cashier',slug:'central',stores:[],data:null,lookup:null,coupon:null,days:30,loading:false};
const tabs=[['cashier','01 / Касса и карты'],['coupons','02 / Проверка бонусов'],['campaigns','03 / Контроль бюджета'],['retention','04 / Повторные покупки'],['executive','05 / Директор']];
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt=x=>new Intl.NumberFormat('ru-RU').format(Number(x)||0);
const rub=x=>x===null||x===undefined?'—':new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:2}).format(Number(x)/100);
let toastTimer;
function notify(s,failed=false){clearTimeout(toastTimer);toastNode.innerHTML=`<div class="toast ${failed?'error':''}">${esc(s)}</div>`;toastTimer=setTimeout(()=>{toastNode.innerHTML=''},4300)}
async function api(path,{method='GET',body}={}){
  const token=sessionStorage.getItem('osmanx_admin_token');
  const headers={'Accept':'application/json'};if(token)headers.Authorization='Bearer '+token;
  if(body!==undefined)headers['Content-Type']='application/json';
  const r=await fetch('/api'+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
  const result=await r.json().catch(()=>({detail:'Не удалось прочитать ответ сервера'}));
  if(!r.ok)throw Error(typeof result.detail==='string'?result.detail:`Ошибка API ${r.status}`);
  return result;
}
function card(name,html){return `<section class="panel"><h2>${esc(name)}</h2>${html}</section>`}
function metric(k,v,hint=''){return `<div class="metric"><small>${esc(k)}</small><b>${esc(v)}</b><em>${esc(hint)}</em></div>`}
function warnings(items){return (items?.length?items:[]).map(x=>`<div class="warn">${esc(x)}</div>`).join('')}
function blank(s){return `<div class="blank">${esc(s)}</div>`}
function input(key,title,placeholder='',attrs=''){return `<label>${esc(title)}<input name="${key}" placeholder="${esc(placeholder)}" required ${attrs}></label>`}
function kv(label,value,hint=''){return `<div class="item"><div><strong>${esc(label)}</strong><small>${esc(hint)}</small></div><span>${esc(value)}</span></div>`}
function drawShell(){root.innerHTML=`<main class="shell"><header class="top"><a href="/"><div class="logo">OSMAN<span>X</span></div><div class="subbrand">RETAIL INTELLIGENCE · R1.2</div></a><div class="toplinks"><select id="desk-store" aria-label="Филиал">${state.stores.map(s=>`<option value="${esc(s.slug)}" ${state.slug===s.slug?'selected':''}>${esc(s.name)}</option>`).join('')}</select><a href="/static/growth.html">Growth Intelligence</a><a href="/">Кабинет</a></div></header>
<section class="lead"><div><div class="overline">OSMANX / OPERATIONS</div><h1>Retail Desk</h1><p>Проверенные чеки, фактическая выдача бонусов, контроль бюджета и повторные покупки — без смешения реальных операций с прогнозами.</p></div><div class="edition">X.</div></section>
<nav class="nav" aria-label="Разделы">${tabs.map(([id,name])=>`<button data-tab="${id}" aria-selected="${state.tab===id}">${name}</button>`).join('')}</nav><div id="desk-content"><div class="loading">OSMAN<span>X</span><small>ЗАГРУЗКА ДАННЫХ</small></div></div><footer class="foot">OSMANX RETAIL INTELLIGENCE · Без распознавания лиц, профилирования и автоматического списания денег. Настоящие подключения 1С и кассы требуют отдельной интеграции.</footer></main>`}
function render(){let body='';
  if(state.tab==='cashier')body=cashier();
  if(state.tab==='coupons')body=coupons();
  if(state.tab==='campaigns')body=campaigns();
  if(state.tab==='retention')body=retention();
  if(state.tab==='executive')body=executive();
  document.querySelector('#desk-content').innerHTML=body;
}
function cashier(){const d=state.lookup;
 const result=d?card('Найденный чек',`<div class="list">${kv('Чек OSMANX',`№${d.sale.id}`,`${rub(d.sale.amount_kopeks)} · ${d.sale.occurred_at}`)}${kv('Источник',d.sale.source,d.sale.external_id)}${kv('Участие в лояльности',d.linked?'Уже привязан':'Не привязан')}</div>`):card('Результат поиска',blank('Введите внешний номер чека и источник, затем нажмите «Найти». Никаких фиктивных продаж система не создаёт.'));
 return `<div class="metrics">${metric('Операция','POS → OSMANX','По фактическому чеку')}${metric('Идентификация','По источнику и номеру','Без поиска по имени')}${metric('Защита','От повторной привязки','Один чек — одна карта')}${metric('Скидки','Не применяются','Интеграция с POS отдельно')}</div>
 <div class="cols"><div class="stack">${card('Найти чек',`<p class="info">Точный источник (например, <strong>retail-pos</strong>) и внешний номер из кассы. При совпадении система покажет сумму и статус.</p><form class="form" data-form="lookup">${input('source','Источник чека','retail-pos','maxlength="80"')}${input('external_id','Внешний номер чека','R-000081','maxlength="200"')}<button class="btn primary" type="submit">Найти чек</button></form>`)}${card('Привязать карту',`<p class="info">Покупатель добровольно предъявляет одноразово выданный код карты. Операцию выполняет руководитель или менеджер.</p><form class="form" data-form="link">${input('source','Источник','retail-pos')}${input('external_id','Номер чека','R-000081')}${input('member_code','Код добровольной карты','OXM-...','minlength="36" maxlength="36"')}<button class="btn primary" type="submit">Привязать подтверждённую покупку</button></form>`)}</div>
 <div class="stack">${result}${card('Только проверенные события',warnings(['Чек создаётся кассовой системой или согласованным импортом, но не этим экраном.','Повторная привязка к той же карте идемпотентна; попытка привязать другую карту блокируется.']))}</div></div>`}
function coupons(){const d=state.coupon;
 const result=d?card('Результат проверки',`<div class="list">${kv('Кампания',d.title,`ID ${d.campaign_id}`)}${kv('Состояние',d.status,`Чек: ${d.receipt_verified?'подтверждён':'не проверен'}`)}${kv('Фактически выдано',d.fulfilled?'Да, отмечено сотрудником':'Нет подтверждения')}${kv('Отменить возможно',d.can_cancel?'Да':'Нет')}${kv('Отметить вручение',d.can_attest_fulfillment?'Да':'Сначала сверить чек')}</div>`):card('Результат проверки',blank('Введите код купона OXC-… в форме слева.'));
 return `<div class="metrics">${metric('Шаг 1','Код бонуса','Проверка статуса')}${metric('Шаг 2','Чек','Сверка в Growth Intelligence')}${metric('Шаг 3','Передача подарка','Отдельная запись сотрудника')}${metric('Шаг 4','Журнал','Повтор защищён')}</div>
 <div class="cols"><div class="stack">${card('Проверить купон',`<form class="form" data-form="inspect">${input('coupon_code','Код купона','OXC-...','minlength="36" maxlength="36"')}<button class="btn primary" type="submit">Проверить статус</button></form>`)}${card('Отменить невостребованный бонус',`<p class="info">Отмена доступна только до проверки кассового чека. Резерв планового бюджета освобождается.</p><form class="form" data-form="cancel">${input('coupon_code','Код купона','OXC-...','minlength="36" maxlength="36"')}<button class="btn danger" type="submit">Отменить купон</button></form>`)}${card('Подтвердить фактическую передачу',`<form class="form" data-form="fulfill">${input('coupon_code','Код проверенного купона','OXC-...','minlength="36" maxlength="36"')}${input('proof_reference','Внутренний номер акта/передачи','GIFT-2026-010','minlength="6" maxlength="100"')}<label>Комментарий сотрудника<textarea name="note" minlength="6" maxlength="300" required placeholder="Что передано и кем подтверждено"></textarea></label><button class="btn primary" type="submit">Зафиксировать выдачу</button></form>`)}</div>
 <div class="stack">${result}${card('Правила',warnings(['Проверка купона не означает, что подарок уже вручён.','Данные о фактической выдаче — заявление сотрудника, а не автоматический сигнал кассы.','Повторная выдача с другим номером документа отклоняется.']))}<div class="actions"><a class="btn secondary" href="/static/growth.html">Оформить выдачу кода и сверку чека в R1.1</a></div></div></div>`}
function campaigns(){const d=state.data,arr=d.items||[];
 return `<div class="metrics">${metric('Кампаний',fmt(arr.length),'Выбранный филиал')}${metric('Купонов выпущено',fmt(arr.reduce((n,x)=>n+x.issued+x.redeemed+x.cancelled,0)),'За все периоды')}${metric('Физически вручено',fmt(arr.reduce((n,x)=>n+x.fulfilled,0)),'Подтверждение сотрудника')}${metric('Плановая стоимость вручённого',rub(arr.reduce((n,x)=>n+x.attested_cost_kopeks,0)),'Не банковские списания')}</div>
 <div class="cols"><div class="stack">${card('Логика бюджета',warnings(d.warnings))}${card('Управление',`<p class="info">Создавать кампании и подтверждать кассовые чеки можно в предыдущем разделе Growth Intelligence.</p><a class="btn secondary" href="/static/growth.html">Открыть управление кампаниями</a>`)}</div><div class="stack">${card('Кампании · верифицированная воронка',arr.length?arr.map(x=>`<div class="item"><div><strong>${esc(x.title)}</strong><small>Выдано ${fmt(x.issued)} · чек проверен ${fmt(x.redeemed)} · вручено ${fmt(x.fulfilled)} · отменено ${fmt(x.cancelled)}<br>Резерв ${rub(x.committed_kopeks)} из ${rub(x.budget_kopeks)} · подтверждено вручение на ${rub(x.attested_cost_kopeks)}</small></div><span class="tag ${x.unfulfilled_redeemed?'red':'good'}">${x.unfulfilled_redeemed?'Ожидает вручения':'Учтено'}</span></div>`).join(''):blank('Кампаний пока нет.'))}</div></div>`}
function retention(){const d=state.data,all=d.windows||[];
 return `<div class="metrics">${metric('Участники',fmt(d.members_with_receipts),'С привязанными чеками')}${metric('Повторные покупки',fmt(d.repeat_members),'Наблюдаемые участники')}${metric('Покрытие чеков',d.coverage_pct===null?'—':d.coverage_pct+'%','Доля всех чеков')}${metric('Чеков с картой',fmt(d.linked_receipts),'Подмножество продаж')}</div>
 <div class="cols"><div class="stack">${card('Периоды зрелости',`<div class="list">${all.map(x=>kv(`${x.days} дней`,` ${x.rate_pct===null?'—':x.rate_pct+'%'}`,`Зрелых ${x.matured} · вернулись ${x.repeated}`)).join('')}</div>`)}${card('Ограничения',warnings(d.warnings))}</div><div class="stack">${card('Первые покупки · по месяцам',d.cohorts.length?`<div class="tablewrap"><table><thead><tr><th>Месяц</th><th>Карты</th><th>Чеки</th><th>7 дней</th><th>30 дней</th><th>60 дней</th></tr></thead><tbody>${d.cohorts.map(x=>`<tr><td>${esc(x.month)}</td><td>${fmt(x.members)}</td><td>${fmt(x.receipt_count)}</td>${x.windows.map(w=>`<td>${w.rate_pct===null?'—':w.rate_pct+'%'}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:blank('Нет привязанных чеков или участия в программе.'))}</div></div>`}
function executive(){const d=state.data;const reports=d.campaigns||[];return `<div class="metrics">${metric('Выручка по чекам',rub(d.receipt_revenue_kopeks),`${d.days} дней, только зарегистрированные`)}${metric('Посетителей',fmt(d.recorded_visits),'Учитываются события источников')}${metric('Конверсия по чекам',d.receipt_conversion_pct===null?'—':d.receipt_conversion_pct+'%','Без дедупликации источников')}${metric('Незакрытые запросы',fmt(d.active_demand_requests),'Спрос ≠ упущенная прибыль')}</div>
 <div class="cols"><div class="stack">${card('Период отчёта',`<form class="form" data-form="days"><label>Последние дней<select name="days"><option value="7" ${state.days===7?'selected':''}>7</option><option value="14" ${state.days===14?'selected':''}>14</option><option value="30" ${state.days===30?'selected':''}>30</option><option value="60" ${state.days===60?'selected':''}>60</option><option value="90" ${state.days===90?'selected':''}>90</option></select></label><button type="submit" class="btn primary">Пересчитать отчёт</button><button type="button" class="btn secondary" data-action="csv">Экспорт CSV</button></form>`)}${card('Качество данных',warnings(d.warnings))}</div><div class="stack">${card('Кампании',`<div class="list">${kv('Всего',fmt(reports.length))}${kv('Планово зарезервировано',rub(reports.reduce((n,x)=>n+x.committed_kopeks,0)))}${kv('Выдача подтверждена вручную',rub(reports.reduce((n,x)=>n+x.attested_cost_kopeks,0)))}</div>`)}${card('Покупатели возвращаются',`<div class="list">${kv('Участников с чеками',fmt(d.retention.members_with_receipts))}${kv('Чеков участников',fmt(d.retention.linked_receipts))}${kv('Охват программы',d.retention.coverage_pct===null?'—':d.retention.coverage_pct+'%')}${kv('Обращения без закрытия',d.open_assistance===null?'Нет источника':fmt(d.open_assistance))}</div>`)}${card('Источник посещений',d.visits_by_source.length?d.visits_by_source.map(x=>kv(x.source,fmt(x.total))).join(''):blank('Данные посещаемости отсутствуют.'))}</div></div>`}
async function reload(){let path={
  cashier:null,coupons:null,
  campaigns:`/admin/r12/campaigns/controls?slug=${encodeURIComponent(state.slug)}`,
  retention:`/admin/r12/retention?slug=${encodeURIComponent(state.slug)}`,
  executive:`/admin/r12/executive?slug=${encodeURIComponent(state.slug)}&days=${state.days}`
}[state.tab];state.data=path?await api(path):null;render()}
async function start(){
  if(!sessionStorage.getItem('osmanx_admin_token')){root.innerHTML='<main class="shell">'+card('Требуется вход','<p class="info">Войдите в кабинет директора, затем вернитесь к Retail Desk. Без авторизации финансовые данные недоступны.</p><a href="/" class="btn primary">Войти в OSMANX</a>')+'</main>';return}
  try{
    const stores=await api('/admin/stores');state.stores=Array.isArray(stores)?stores:(stores.items||[]);
    if(!state.stores.length)throw Error('Нет доступных филиалов');
    state.slug=state.stores[0].slug;drawShell();await reload();
  }catch(e){root.innerHTML='<main class="shell">'+card('Не удалось загрузить кабинет',`<p class="info">${esc(e.message)}</p><a class="btn primary" href="/">Открыть вход</a>`)+'</main>'}
}
root.addEventListener('click',async e=>{
 const tab=e.target.closest('[data-tab]');if(tab){state.tab=tab.dataset.tab;state.lookup=null;state.coupon=null;drawShell();try{await reload()}catch(err){notify(err.message,true)}return}
 if(e.target.closest('[data-action="csv"]')){
  try{
   const token=sessionStorage.getItem('osmanx_admin_token');const q=`/api/admin/r12/executive/export?slug=${encodeURIComponent(state.slug)}&days=${state.days}`;
   const r=await fetch(q,{headers:{Authorization:'Bearer '+token},cache:'no-store'});if(!r.ok)throw Error('Ошибка экспорта');
   const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`OSMANX_${state.slug}_${state.days}_days.csv`;a.click();URL.revokeObjectURL(url);
   notify('CSV отчёт сохранён');
  }catch(err){notify(err.message,true)}
 }
});
root.addEventListener('change',async e=>{if(e.target.id==='desk-store'){state.slug=e.target.value;state.lookup=null;state.coupon=null;try{await reload()}catch(err){notify(err.message,true)}}});
root.addEventListener('submit',async e=>{
 const f=e.target.closest('[data-form]');if(!f)return;e.preventDefault();
 const body=Object.fromEntries(new FormData(f));body.slug=state.slug;
 const type=f.dataset.form,button=f.querySelector('[type="submit"]');if(button)button.disabled=true;
 try{
  if(type==='lookup'){state.lookup=await api('/admin/r12/cashier/receipt',{method:'POST',body});notify('Чек найден')}
  else if(type==='link'){const out=await api('/admin/r12/cashier/link',{method:'POST',body});state.lookup=null;notify(out.duplicate?'Чек уже был привязан к этой карте':'Чек привязан к карте')}
  else if(type==='inspect'){state.coupon=await api('/admin/r12/coupons/inspect',{method:'POST',body});notify('Купон проверен')}
  else if(type==='cancel'){const out=await api('/admin/r12/coupons/cancel',{method:'POST',body});state.coupon=null;notify(out.duplicate?'Купон уже отменён':'Купон отменён, бюджет освобождён')}
  else if(type==='fulfill'){const out=await api('/admin/r12/coupons/fulfill',{method:'POST',body});state.coupon=null;notify(out.duplicate?'Выдача уже была зафиксирована':'Передача подарка внесена в журнал')}
  else if(type==='days'){state.days=Number(body.days);await reload();notify('Период обновлён');return}
  render();
 }catch(err){notify(err.message,true)}finally{if(button)button.disabled=false}
});
start();
