/* OSMANX R0.6: five live data modules. No fake counts or hidden demo substitutions. */
const root=document.querySelector('#workflow-root');
const toastNode=document.querySelector('#workflow-toast');
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rub=x=>new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:2}).format((Number(x)||0)/100);
const num=x=>new Intl.NumberFormat('ru-RU').format(Number(x)||0);
const statusLabel={open:'Открыт',reserved:'Забронирован',ordered:'В заказе',converted:'Куплен по чеку',closed:'Закрыт',draft:'Черновик',partial:'Частично принят',received:'Поступил',cancelled:'Отменён',proposed:'Предложен',testing:'Проверяется',validated:'Подтверждён',rejected:'Отклонён'};
const status=x=>`<span class="wf-chip ${['converted','received','validated'].includes(x)?'positive':['ordered','partial','reserved','open','testing'].includes(x)?'attention':''}">${esc(statusLabel[x]||x)}</span>`;
const dayOffset=d=>{const x=new Date();x.setUTCDate(x.getUTCDate()+d);return x.toISOString().slice(0,10)};
const S={tab:'overview',config:{demo:false},stores:[],slug:'central',data:null,authorized:false,loading:false};
let toastTimer;
function toast(message,error=false){clearTimeout(toastTimer);toastNode.innerHTML=`<div class="wf-toast ${error?'error':''}">${esc(message)}</div>`;toastTimer=setTimeout(()=>toastNode.innerHTML='',5500)}
async function call(path,{method='GET',body,format='json'}={}){
 const headers={Accept:format==='csv'?'text/csv':'application/json'};
 if(body!==undefined)headers['Content-Type']='application/json';
 const token=sessionStorage.getItem('osmanx_admin_token');
 if(token)headers.Authorization=`Bearer ${token}`;
 const response=await fetch('/api'+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
 if(format==='csv'){
   if(!response.ok)throw new Error('Не удалось выгрузить отчёт (HTTP '+response.status+')');
   return await response.blob();
 }
 let data=await response.json().catch(()=>({detail:'Сервер вернул невалидный ответ'}));
 if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Ошибка HTTP '+response.status);
 return data;
}
async function reload(){
 S.data=await call('/admin/workflows/overview?slug='+encodeURIComponent(S.slug));
 render();
}
async function init(){
 try{
  S.config=await call('/config');
  if(!S.config.demo&&!sessionStorage.getItem('osmanx_admin_token')){
   root.innerHTML='<div class="wf-shell"><div class="wf-card"><h1>Требуется вход</h1><p class="wf-note">Войдите в основной кабинет OSMANX перед открытием коммерческих операций.</p><a href="/" class="wf-button red">Войти в кабинет</a></div></div>';return;
  }
  S.stores=await call('/admin/stores');
  if(!S.stores.length)throw new Error('Нет доступных филиалов. Обратитесь к владельцу организации.');
  const qp=new URLSearchParams(location.search).get('store');
  if(qp&&S.stores.some(s=>s.slug===qp))S.slug=qp;
  else S.slug=S.stores[0].slug;
  S.authorized=true;await reload();
 }catch(e){renderFailure(e)}
}
function renderFailure(error){
 root.innerHTML=`<div class="wf-shell"><div class="wf-card"><div class="wf-logo">OSMAN<span>X</span></div><h1>Не удалось получить данные</h1><p class="wf-note">${esc(error.message||String(error))}</p><a href="/" class="wf-button">Вернуться в основной кабинет</a></div></div>`;
}
function input(name,label,type='text',opts={}){
 const required=opts.required===false?'':'required';const min=opts.min!==undefined?`min="${opts.min}"`:'';
 const max=opts.max!==undefined?`max="${opts.max}"`:'';const step=opts.step!==undefined?`step="${opts.step}"`:'';
 const placeholder=opts.placeholder?`placeholder="${esc(opts.placeholder)}"`:'';
 const value=opts.value!==undefined?`value="${esc(opts.value)}"`:'';
 return `<div class="wf-field"><label for="wf-${esc(name)}">${esc(label)}</label><input class="wf-input" id="wf-${esc(name)}" name="${esc(name)}" type="${type}" ${required} ${min} ${max} ${step} ${placeholder} ${value}></div>`;
}
function select(name,label,options,selected=''){
 return `<div class="wf-field"><label for="wf-${esc(name)}">${esc(label)}</label><select name="${esc(name)}" id="wf-${esc(name)}">${options.map(o=>`<option value="${esc(o.value)}" ${String(o.value)===String(selected)?'selected':''}>${esc(o.label)}</option>`).join('')}</select></div>`;
}
function card(title,body,cls=''){return `<section class="wf-card ${cls}"><h2>${esc(title)}</h2>${body}</section>`}
function empty(label){return `<div class="wf-empty">${esc(label)}</div>`}
function row(title,subtitle='',buttons='',chip=''){
 return `<article class="wf-row"><div><strong>${title}</strong><p>${subtitle}</p></div><div class="wf-row-right">${chip}${buttons}</div></article>`;
}
function render(){
 const d=S.data;
 const tabs=[['overview','Главная'],['cases','Невидимый спрос'],['orders','Закупки и склад'],['finance','Экономика чеков'],['evaluations','Проверка решений']];
 root.innerHTML=`<main class="wf-shell">
   <header class="wf-header"><div><div class="wf-logo">OSMAN<span>X</span></div><div class="wf-sub">RETAIL INTELLIGENCE · R0.6</div></div>
    <div class="wf-header-actions"><select class="wf-select" id="wf-store" aria-label="Филиал">${S.stores.map(s=>`<option value="${esc(s.slug)}" ${s.slug===S.slug?'selected':''}>${esc(s.name)}</option>`).join('')}</select>
      ${S.config.demo?'<span class="wf-chip attention">ДЕМО · искусственные данные</span>':'<span class="wf-chip positive">Реальная база</span>'}
      <a class="wf-button red" href="/static/operations.html">Контроль магазина R0.7</a><a class="wf-button" href="/">← Основной кабинет</a></div></header>
   <section class="wf-hero"><div><span class="wf-kicker">Коммерческие операции / единая цепочка</span><h1>От спроса до<br>подтверждённой прибыли.</h1><p>Ничего не угадываем: запросы фиксируются, поставки подтверждаются, продажи сверяются с чеками, а решения проверяются на фактических показателях.</p></div>
   <div class="wf-flow">${['Запрос','Закупка','Поступление','Чек','Вывод'].map((x,i)=>`<div class="wf-flow-step"><i></i><small>${i+1}. ${x}</small></div>`).join('')}</div></section>
   <section class="wf-stats" aria-label="Ключевые показатели">
    <div class="wf-stat"><label>Новые запросы</label><strong>${num(d.kpi.unassigned_requests)}</strong><small>Ещё не взяты в работу</small></div>
    <div class="wf-stat"><label>Активные кейсы</label><strong>${num(d.kpi.open_cases)}</strong><small>Заявки на товар</small></div>
    <div class="wf-stat"><label>Ожидают поставку</label><strong>${num(d.kpi.awaiting_restock_units)}</strong><small>Штук в открытых заказах</small></div>
    <div class="wf-stat accent"><label>Документированная валовая маржа</label><strong>${rub(d.finance.documented_gross_margin_kopeks)}</strong><small>Только товарные строки чеков</small></div>
   </section>
   <nav class="wf-tabs" role="tablist" aria-label="Разделы системы">${tabs.map(([id,label])=>`<button class="wf-tab" role="tab" aria-selected="${S.tab===id}" data-tab="${id}">${label}</button>`).join('')}</nav>
   <div id="wf-view">${{overview:overview, cases:cases,orders:orders,finance:finance,evaluations:evaluations}[S.tab]()}</div>
   <footer class="wf-footer">OSMANX WORLD · Данные принадлежат организации. «Прибыль» означает документированную валовую маржу по товарным строкам, не чистую прибыль компании. Совпадение изменений с экспериментом не доказывает причинную связь.</footer>
 </main>`;
}
function overview(){
 const d=S.data;
 const notes=d.notes.length?d.notes.map(x=>`<div class="wf-alert">${esc(x)}</div>`).join(''):'<div class="wf-hint">Нет новых предупреждений по агрегированной статистике. Не забывайте проверять полноту кассовых и складских данных.</div>';
 const latest=d.evaluations.slice(0,4).map(e=>row(esc(e.decision_title),`${esc(e.metric)} · ${esc(e.before_start)} — ${esc(e.after_end)}`,
   `<span class="wf-chip">${e.before_value??'—'} → ${e.after_value??'—'}</span>`,e.warnings.length?'<span class="wf-chip attention">Есть оговорки</span>':'')).join('');
 return `<div class="wf-overview-grid">
   ${card('Что требует внимания',`${row('Неразобранные запросы',`${num(d.unassigned_demand.length)} запросов для оценки`, '<button class="wf-button" data-goto="cases">Открыть</button>')}
    ${row('Заказы поставщикам',`${num(d.kpi.orders_in_progress)} ожидают поступления`, '<button class="wf-button" data-goto="orders">Управлять</button>')}
    ${row('Неполные товарные строки',`${num(d.finance.receipts_without_items)} чеков без детализации`, '<button class="wf-button" data-goto="finance">Разнести</button>')}
    ${row('Новые измерения',`${num(d.evaluations.length)} сохранённых сравнений`, '<button class="wf-button" data-goto="evaluations">Проверить</button>')}`)}
   ${card('Финансовая дисциплина',`${metric('Выручка по разнесённым товарам',rub(d.finance.documented_revenue_kopeks))}
    ${metric('Себестоимость по разнесённым товарам',rub(d.finance.documented_cost_kopeks))}
    ${metric('Валовая маржа по разнесённым товарам',rub(d.finance.documented_gross_margin_kopeks))}
    ${metric('Возвраты магазина (общая сумма)',rub(d.finance.store_returns_kopeks))}
    <p class="wf-note">Возвраты показаны отдельно. Без товарных строк возвратов невозможно достоверно перераспределить себестоимость по SKU.</p>`)}
   ${card('Проверенные решения',latest||empty('Пока нет измерений до и после. Добавьте оценку действующего решения.'))}
   ${card('Качество данных и экспорт',`${notes}<div class="wf-label">Выгрузить проверяемые записи</div><div class="wf-header-actions">
      ${['cases','orders','sale_items','evaluations'].map((x,i)=>`<button class="wf-button" data-export="${x}">${['Запросы','Заказы','Чеки по SKU','Измерения'][i]} · CSV</button>`).join('')}
    </div><p class="wf-note">Экспорт защищён правами филиала и экранирует формулы при открытии в табличных редакторах.</p>`)}</div>`;
}
function metric(k,v){return `<div class="wf-metric-row"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`;}
function cases(){
 const d=S.data;
 const opts=d.reservations.filter(r=>r.state==='held').map(r=>({value:r.id,label:`Резерв №${r.id} · ${r.sku}`}));
 const lines=d.orders.filter(o=>!['cancelled','draft'].includes(o.status)).flatMap(o=>o.lines.map(l=>({value:l.id,label:`Заказ №${o.id} · ${l.sku} · ${o.status}`})));
 const sales=d.receipts.map(x=>({value:x.id,label:`Чек №${x.id} · ${rub(x.amount_kopeks)}`}));
 const unassigned=d.unassigned_demand.map(x=>row(`${esc(x.product)} · ${esc(x.size||'—')}`,`Цвет: ${esc(x.color||'не указан')} · Запрос №${x.id}`,
  `<button class="wf-button" data-prefill-demand="${x.id}">В работу</button>`,status(x.status))).join('');
 const working=d.cases.map(x=>row(`${esc(x.product)} · ${esc(x.size)} · ${esc(x.sku)}`,
  `Кейс №${x.id} · запрос №${x.demand_id} · ${esc(x.notes||'Без комментария')} ${x.sale_id?'· чек №'+x.sale_id:''}`,
  !['converted','closed'].includes(x.status)?`<button class="wf-button" data-case-id="${x.id}">Изменить</button>`:'',status(x.status))).join('');
 return `<div class="wf-layout">
 ${card('Взять запрос в работу',`<p class="wf-note">Укажите внутренний артикул. Запрос не считается потерянной продажей до подтверждения факта покупки.</p>
   <form class="wf-form" data-form="case-create">
    ${select('demand_id','Необработанный запрос',d.unassigned_demand.map(x=>({value:x.id,label:`№${x.id}: ${x.product} · ${x.size}`})))}
    ${input('sku','SKU / артикул товара')}
    ${input('requested_quantity','Количество, шт.','number',{value:1,min:1,max:100})}
    ${input('notes','Заметка','text',{required:false,placeholder:'Никаких персональных данных'})}
    <button class="wf-button red" type="submit" ${!d.unassigned_demand.length?'disabled':''}>Создать кейс</button>
   </form>
   <div class="wf-label">Изменить состояние кейса</div>
   <form class="wf-form" data-form="case-update">
    ${select('case_id','Кейс',d.cases.filter(x=>!['closed','converted'].includes(x.status)).map(x=>({value:x.id,label:`№${x.id}: ${x.sku} · ${x.status}`})))}
    ${select('action','Подтверждённое действие',[{value:'reserve',label:'Привязать резерв'},{value:'order',label:'Привязать заказ'},{value:'convert',label:'Подтвердить покупку по чеку'},{value:'close',label:'Закрыть без покупки'}])}
    ${select('reservation_id','Резерв',opts)}
    ${select('order_line_id','Позиция заказа поставщику',lines)}
    ${select('sale_id','Чек',sales)}
    ${input('notes','Основание / пояснение','text',{required:false})}
    <button class="wf-button" type="submit" ${!d.cases.some(x=>!['closed','converted'].includes(x.status))?'disabled':''}>Сохранить подтверждение</button>
    <p class="wf-text-help">Для статуса «Куплен» необходима соответствующая товарная строка чека. Нельзя привязать чужой чек.</p>
   </form>`)}
 ${card('Очередь спроса',`<p class="wf-note">Необработанные обращения, записанные продавцами. Отсутствие покупки не равно потере прибыли.</p>${unassigned||empty('Необработанных запросов пока нет.')}
 <h3 class="wf-label">Кейсы в работе</h3>${working||empty('Кейсы ещё не созданы.')}`)}
 </div>`;
}
function lineRow(index=1){return `<div class="wf-order-item" data-line><div class="wf-form-row">
 ${input('sku','Артикул')}${input('product','Наименование')}
 ${input('size','Размер','text',{required:false})}${input('color','Цвет','text',{required:false})}
 ${input('quantity','Количество','number',{value:1,min:1,max:10000})}${input('unit_cost_rub','Себестоимость за единицу, ₽','number',{value:'1000',min:0,step:'0.01'})}
 </div><button class="wf-button" type="button" data-remove-line>Убрать позицию</button></div>`}
function orders(){const d=S.data;
 const list=d.orders.map(o=>{
  const details=o.lines.map(l=>`<div class="wf-row"><div><strong>${esc(l.sku)} · ${esc(l.product)}</strong><p>Заказано: ${num(l.ordered_qty)} · принято: ${num(l.received_qty)} · осталось: ${num(l.ordered_qty-l.received_qty)}</p></div><strong>${rub(l.unit_cost_kopeks*l.ordered_qty)}</strong></div>`).join('');
  const open=o.lines.filter(l=>l.ordered_qty>l.received_qty);
  const form=open.length&&['ordered','partial'].includes(o.status)?`<form class="wf-receive" data-form="receive" data-order-id="${o.id}">
   <div class="wf-field"><label>Позиция для приёмки</label><select name="line_id">${open.map(l=>`<option value="${l.id}">${esc(l.sku)} · осталось ${l.ordered_qty-l.received_qty}</option>`).join('')}</select></div>
   <div class="wf-field"><label>Количество</label><input class="wf-input" name="quantity" type="number" min="1" max="10000" value="1" required></div>
   <div class="wf-field"><label>Номер накладной</label><input class="wf-input" name="external_id" type="text" minlength="3" maxlength="100" placeholder="UNIQUE-001" required></div>
   <button class="wf-button red" type="submit">Принять товар</button></form>`:'';
  return `<div class="wf-row"><div><strong>Заказ №${o.id} · ${esc(o.reference)} · ${esc(o.supplier)}</strong><p>Сумма: ${rub(o.order_total_kopeks)} · Поступило: ${rub(o.delivered_cost_kopeks)}</p></div><div class="wf-row-right">${status(o.status)}${o.status==='draft'?`<button class="wf-button" data-order-status="ordered" data-order-id="${o.id}">Отправить заказ</button>`:''}${['draft','ordered'].includes(o.status)?`<button class="wf-button" data-order-status="cancelled" data-order-id="${o.id}">Отменить</button>`:''}</div></div><div style="padding-left:12px;border-left:2px solid #30435a;margin-bottom:18px">${details}${form}</div>`;
 }).join('');
 return `<div class="wf-layout">
 ${card('Заказ поставщику',`<p class="wf-note">Черновик не списывает деньги. Фактическое поступление добавляет товар на склад только после подтверждения накладной.</p>
   <form class="wf-form" data-form="order-create">
     ${input('supplier','Поставщик')}
     ${input('reference','Номер заказа','text',{placeholder:'PO-2026-001'})}
     ${input('expected_date','Ожидаемая дата','date',{required:false})}
     <div class="wf-order-lines" id="wf-order-lines">${lineRow()}</div>
     <button type="button" class="wf-button" data-add-line>+ Добавить товар</button>
     <button type="submit" class="wf-button red">Сохранить черновик заказа</button>
   </form>`)}
 ${card('Поступления и остатки',`<p class="wf-note">Все позиции проходят транзакционную приёмку. Повтор с той же накладной не увеличивает остаток.</p>${list||empty('Заказы ещё не создавались.')}`)}
 </div>`;
}
function finance(){const d=S.data;const f=d.finance;
 const sales=d.receipts.map(r=>({value:r.id,label:`Чек №${r.id} · ${rub(r.amount_kopeks)} · свободно ${rub(r.amount_kopeks-r.allocated_kopeks)}`}));
 return `<div class="wf-layout">
 ${card('Разнести товар по настоящему чеку',`<p class="wf-note">Только чек, подтверждённый кассовой записью, позволяет учитывать проданную вещь. Себестоимость указывается по документам закупки.</p>
  <form class="wf-form" data-form="sale-item">
   ${select('sale_id','Чек',sales)}
   ${input('sku','SKU товара')}
   <div class="wf-form-row">${input('quantity','Продано, шт.','number',{value:1,min:1,max:10000})}
   ${input('unit_revenue_rub','Цена за единицу, ₽','number',{value:'5000',step:'0.01',min:0})}</div>
   ${input('unit_cost_rub','Учётная себестоимость, ₽','number',{value:'2500',step:'0.01',min:0})}
   ${input('external_id','Номер товарной строки','text',{placeholder:'receipt-123-line-1'})}
   <button class="wf-button red" type="submit" ${!sales.length?'disabled':''}>Записать строку продажи</button>
  </form>`)}
 ${card('Маржа: только подтверждённые данные',`
  ${metric('Выручка по товарным строкам',rub(f.documented_revenue_kopeks))}
  ${metric('Себестоимость товарных строк',rub(f.documented_cost_kopeks))}
  ${metric('Документированная валовая маржа',rub(f.documented_gross_margin_kopeks))}
  ${metric('Чеков без товарных строк',num(f.receipts_without_items))}
  ${metric('Возвраты по всем чекам',rub(f.store_returns_kopeks))}
  <div class="wf-hint">Это <strong>не чистая прибыль</strong> и не гарантированная экономия. Возвраты, аренда, реклама, зарплаты и налоги не распределены по SKU. Результат обновляется после сохранения подтверждённых строк.</div>
  <div class="wf-label">Последние чеки и неразнесённые суммы</div>
  ${d.receipts.slice(0,18).map(r=>row(`Чек №${r.id} · ${rub(r.amount_kopeks)}`,
    `${esc(r.source)} · ${esc(r.occurred_at)}`,`<span class="wf-chip">Не разнесено ${rub(r.amount_kopeks-r.allocated_kopeks)}</span>`)).join('')||empty('Нет подтверждённых чеков.')}`)}
 </div>`;
}
function evaluations(){const d=S.data;
 const decisions=d.decisions.map(r=>({value:r.id,label:`№${r.id} · ${r.title} (${statusLabel[r.status]||r.status})`}));
 const valueName={conversion:'Конверсия, %',visitors:'Посещения',purchases:'Чеки',revenue:'Выручка, ₽'};
 const list=d.evaluations.map(e=>{
  const max=Math.max(1,Math.abs(e.before_value||0),Math.abs(e.after_value||0));
  return `<article class="wf-row" style="display:block"><strong>${esc(e.decision_title)} · ${esc(valueName[e.metric]||e.metric)}</strong>
  <p>${esc(e.before_start)} — ${esc(e.before_end)} vs ${esc(e.after_start)} — ${esc(e.after_end)} · ${esc(e.source_mode)}</p>
  ${[['Было',e.before_value],['Стало',e.after_value]].map(([name,value])=>`<div class="wf-mini-chart"><label>${name} · ${value??'—'}</label><div class="wf-track"><i style="width:${value===null?0:Math.abs(value)/max*100}%"></i></div></div>`).join('')}
  ${e.warnings.length?e.warnings.map(w=>`<div class="wf-alert">${esc(w)}</div>`).join(''):'<span class="wf-chip positive">Без предупреждений по источникам</span>'}
  <div class="wf-note">Изменение: ${e.delta===null?'нельзя вычислить':esc(e.delta)}. Сравнение не доказывает причинную связь.</div></article>`;
 }).join('');
 return `<div class="wf-layout">
  ${card('Измерить гипотезу',`<p class="wf-note">Сравните два завершённых периода. Выберите единый способ подсчёта входов. Не называйте разницу доказанной прибылью.</p>
   <form class="wf-form" data-form="evaluate">
    ${select('experiment_id','Пилот из кабинета директора',decisions)}
    ${select('metric','Показатель',[{value:'conversion',label:'Конверсия, %'},{value:'visitors',label:'Посещения'},{value:'purchases',label:'Чеки'},{value:'revenue',label:'Выручка, ₽'}])}
    ${select('source_mode','Источник посещений',[{value:'sensor',label:'Датчик'},{value:'manual',label:'Ручной подсчёт'},{value:'combined',label:'Смешанный (с предупреждением)'}])}
    <div class="wf-dates">${input('before_start','Период ДО: начало','date',{value:dayOffset(-14)})}${input('before_end','Период ДО: конец','date',{value:dayOffset(-8)})}</div>
    <div class="wf-dates">${input('after_start','Период ПОСЛЕ: начало','date',{value:dayOffset(-7)})}${input('after_end','Период ПОСЛЕ: конец','date',{value:dayOffset(-1)})}</div>
    ${input('notes','Что менялось в работе магазина','text',{required:false})}
    <button class="wf-button red" type="submit" ${!decisions.length?'disabled':''}>Вычислить и сохранить</button>
    <p class="wf-text-help">Периоды не должны пересекаться; изменение может быть вызвано сезонностью, акциями или внешними факторами.</p>
   </form>`)}
  ${card('История сравнений',list||empty('Пока нет сохранённых сравнений. Создайте первое измерение.'))}
 </div>`;
}
async function downloadReport(dataset){
 const blob=await call(`/admin/workflows/export?slug=${encodeURIComponent(S.slug)}&dataset=${encodeURIComponent(dataset)}`,{format:'csv'});
 const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=`osmanx-${S.slug}-${dataset}.csv`;
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);
}
function dataOf(form){return Object.fromEntries(new FormData(form).entries())}
async function submit(form){
 const type=form.dataset.form;const d=dataOf(form);const slug=S.slug;
 const button=form.querySelector('[type=submit]');if(button)button.disabled=true;
 try{
  let reply;
  if(type==='case-create')reply=await call('/admin/workflows/cases',{method:'POST',body:{slug,demand_id:+d.demand_id,sku:d.sku,requested_quantity:+d.requested_quantity,notes:d.notes||''}});
  else if(type==='case-update'){
   const item={action:d.action,notes:d.notes||''};
   if(d.action==='reserve')item.reservation_id=Number(d.reservation_id)||undefined;
   if(d.action==='order')item.order_line_id=Number(d.order_line_id)||undefined;
   if(d.action==='convert')item.sale_id=Number(d.sale_id)||undefined;
   reply=await call('/admin/workflows/cases/'+encodeURIComponent(d.case_id),{method:'PATCH',body:item});
  } else if(type==='order-create'){
   const lines=[...form.querySelectorAll('[data-line]')].map(row=>{
    const get=x=>row.querySelector(`[name="${x}"]`)?.value;
    return {sku:get('sku'),product:get('product'),size:get('size'),color:get('color'),quantity:+get('quantity'),unit_cost_rub:get('unit_cost_rub')};
   });
   reply=await call('/admin/workflows/orders',{method:'POST',body:{slug,supplier:d.supplier,reference:d.reference,expected_date:d.expected_date||null,lines}});
  } else if(type==='receive'){
   reply=await call(`/admin/workflows/orders/${form.dataset.orderId}/receipts`,{method:'POST',body:{external_id:d.external_id,lines:[{line_id:+d.line_id,quantity:+d.quantity}]}});
  } else if(type==='sale-item'){
   reply=await call('/admin/workflows/sale-items',{method:'POST',body:{slug,sale_id:+d.sale_id,sku:d.sku,quantity:+d.quantity,unit_revenue_rub:d.unit_revenue_rub,unit_cost_rub:d.unit_cost_rub,external_id:d.external_id}});
  } else if(type==='evaluate'){
   reply=await call('/admin/workflows/evaluations',{method:'POST',body:{slug,experiment_id:+d.experiment_id,metric:d.metric,source_mode:d.source_mode,before_start:d.before_start,before_end:d.before_end,after_start:d.after_start,after_end:d.after_end,notes:d.notes||''}});
  }
  await reload();toast(reply?.duplicate?'Накладная уже учтена — остаток не изменился.':'Запись подтверждена и сохранена.');
 }catch(e){toast(e.message,true)}finally{if(button&&button.isConnected)button.disabled=false}
}
root.addEventListener('submit',event=>{const form=event.target.closest('[data-form]');if(!form)return;event.preventDefault();submit(form)});
root.addEventListener('change',async event=>{
 if(event.target.id==='wf-store'){
  S.slug=event.target.value;
  try{await reload()}catch(e){toast(e.message,true)}
 }
});
root.addEventListener('click',async event=>{
 const btn=event.target.closest('button,[data-goto]');if(!btn)return;
 if(btn.dataset.tab||btn.dataset.goto){S.tab=btn.dataset.tab||btn.dataset.goto;render();return}
 if(btn.dataset.addLine!==undefined){document.querySelector('#wf-order-lines')?.insertAdjacentHTML('beforeend',lineRow());return}
 if(btn.dataset.removeLine!==undefined){
  const lines=document.querySelectorAll('[data-line]');if(lines.length<=1){toast('В заказе должна остаться хотя бы одна позиция',true);return}
  btn.closest('[data-line]')?.remove();return;
 }
 if(btn.dataset.prefillDemand){S.tab='cases';render();const sel=document.querySelector('[name=demand_id]');if(sel)sel.value=btn.dataset.prefillDemand;document.querySelector('[name=sku]')?.focus();return}
 if(btn.dataset.caseId){S.tab='cases';render();const sel=document.querySelector('[name=case_id]');if(sel)sel.value=btn.dataset.caseId;document.querySelector('[name=action]')?.focus();return}
 if(btn.dataset.export){try{await downloadReport(btn.dataset.export);toast('Отчёт выгружен')}catch(e){toast(e.message,true)}return}
 if(btn.dataset.orderStatus){
  btn.disabled=true;
  try{await call(`/admin/workflows/orders/${btn.dataset.orderId}`,{method:'PATCH',body:{status:btn.dataset.orderStatus}});await reload();toast('Статус заказа обновлён')}
  catch(e){toast(e.message,true);btn.disabled=false}
 }
});
init();
