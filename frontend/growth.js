/* OSMANX Growth Intelligence R1.1. Real authenticated API only; no browser-side personal profiles. */
const root=document.querySelector('#growth-root');
const toaster=document.querySelector('#growth-toast');
const state={tab:'members',slug:'central',stores:[],config:{},data:null,days:30,secret:null,effect:null};
const tabs=[['members','01 / Карты лояльности'],['receipts','02 / Чеки'],['campaigns','03 / Кампании'],['retention','04 / Повторные покупки'],['assortment','05 / Ассортимент']];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num=v=>new Intl.NumberFormat('ru-RU').format(Number(v||0));
const money=v=>v===null||v===undefined?'—':new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB'}).format(Number(v)/100);
const today=()=>new Date().toISOString().slice(0,10);
const daysFromNow=n=>new Date(Date.now()+n*86400000).toISOString().slice(0,10);
let timer;
function toast(s,isError=false){clearTimeout(timer);toaster.innerHTML=`<div class="toast ${isError?'error':''}">${esc(s)}</div>`;timer=setTimeout(()=>{toaster.innerHTML=''},4500)}
async function api(path,{method='GET',body}={}){
 const headers={'Accept':'application/json'};
 const token=sessionStorage.getItem('osmanx_admin_token');
 if(token)headers.Authorization='Bearer '+token;
 if(body!==undefined)headers['Content-Type']='application/json';
 const response=await fetch('/api'+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
 const result=await response.json().catch(()=>({detail:'Некорректный ответ сервера'}));
 if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Ошибка '+response.status);
 return result;
}
const card=(h,body)=>`<section class="card"><h2>${esc(h)}</h2>${body}</section>`;
const muted=x=>`<p class="muted">${esc(x)}</p>`;
const warning=values=>(values||[]).map(x=>`<div class="warnbox">${esc(x)}</div>`).join('');
const field=(name,label,type='text',value='',extra='')=>`<label>${esc(label)}<input name="${esc(name)}" type="${esc(type)}" value="${esc(value)}" ${extra} required /></label>`;
const button=(label,action,id='',css='')=>`<button type="button" class="btn ${css}" data-action="${esc(action)}" data-id="${esc(id)}">${esc(label)}</button>`;
const row=(title,detail,tools='')=>`<div class="row"><div><strong>${title}</strong><small>${detail}</small></div><div class="actions">${tools}</div></div>`;
const empty=s=>`<div class="blank">${esc(s)}</div>`;
const stat=(label,value,detail)=>`<div class="stat"><small>${esc(label)}</small><b>${value}</b><em>${esc(detail)}</em></div>`;
function secretBlock(){if(!state.secret)return '';
 return `<section class="codebox" aria-live="polite"><small>Одноразовая выдача · ${esc(state.secret.title)}</small><b>${esc(state.secret.code)}</b><small>Скопируйте код сейчас. Он не отображается повторно, в базе хранится только SHA-256. Не отправляйте его через общий чат сотрудников.</small></section>`;
}
function shell(){root.innerHTML=`<main class="main"><header class="top"><a href="/"><div class="brand">OSMAN<span>X</span></div><div class="eyebrow">RETAIL INTELLIGENCE / R1.1</div></a><div class="topright"><select id="growth-store" aria-label="Выбрать магазин">${state.stores.map(x=>`<option value="${esc(x.slug)}" ${state.slug===x.slug?'selected':''}>${esc(x.name)}</option>`).join('')}</select><a href="/static/experience.html">Обслуживание</a><a href="/static/evidence.html">Evidence Lab</a><a href="/static/retail_desk.html">Retail Desk</a><a href="/">Кабинет</a></div></header>
 <div class="hero"><div><span class="kicker">OSMANX / CUSTOMER & REVENUE INTELLIGENCE</span><h1>Покупатели возвращаются.<br>Решения подтверждаются.</h1><p>Добровольные карты без личных данных, привязка повторных покупок только к чекам, контролируемые бонусы и реальный сигнал об ассортименте.</p></div><div class="heroMark">OX.</div></div>
 ${state.config.demo?'<div class="demo">ДЕМО-РЕЖИМ · цифры могут быть искусственными; не показывайте их как результаты реального магазина.</div>':''}
 <nav class="nav" role="tablist">${tabs.map(([id,label])=>`<button role="tab" data-tab="${id}" aria-selected="${state.tab===id}">${label}</button>`).join('')}</nav>
 <div id="growth-content"></div><footer class="footer">OSMANX WORLD · Коды не связаны с именами или телефонами. Повторные продажи отражают только добровольных участников. Бонусы не применяются в кассовой системе автоматически. Рекомендации — гипотезы, а не прогноз дохода.</footer></main>`;}
async function init(){try{
 state.config=await api('/config');
 if(!state.config.demo&&!sessionStorage.getItem('osmanx_admin_token')){
   root.innerHTML=`<main class="main"><div class="error"><h2>Требуется вход</h2><p>Сначала войдите в кабинет OSMANX.</p><a class="btn primary" href="/">Войти</a></div></main>`;return;
 }
 const stores=await api('/admin/stores');state.stores=Array.isArray(stores)?stores:(stores.items||[]);
 if(!state.stores.length)throw new Error('Нет доступных филиалов');
 const preferred=new URLSearchParams(location.search).get('store');
 state.slug=(state.stores.find(s=>s.slug===preferred)||state.stores[0]).slug;
 shell();await reload();
}catch(err){root.innerHTML=`<main class="main"><div class="error"><h2>Не удалось открыть Growth Intelligence</h2><p>${esc(err.message)}</p><a class="btn" href="/">К кабинету</a></div></main>`}}
async function reload(){const slug=encodeURIComponent(state.slug);
 let endpoint={members:`/admin/r11/members?slug=${slug}`,receipts:`/admin/r11/receipts?slug=${slug}`,
 campaigns:`/admin/r11/campaigns?slug=${slug}`,retention:`/admin/r11/retention?slug=${slug}`,
 assortment:`/admin/r11/assortment?slug=${slug}&days=${state.days}`}[state.tab];
 state.data=await api(endpoint);render();
}
function render(){const target=document.querySelector('#growth-content');if(!target)return;
 target.innerHTML=({members:renderMembers,receipts:renderReceipts,campaigns:renderCampaigns,
 retention:renderRetention,assortment:renderAssortment}[state.tab])();
}
function renderMembers(){const d=state.data,active=d.items.filter(x=>x.status==='active').length;
 return `<div class="stats">${stat('Выданные карты',num(d.items.length),'До 200 последних записей')}${stat('Активные',num(active),'Добровольные участники')}${stat('Чеки участников',num(d.items.reduce((a,b)=>a+b.linked_receipts,0)),'По выбранному домашнему филиалу')}${stat('Личные данные','0','Имена и телефоны не нужны')}</div>
 <div class="grid"><div class="stack">${card('Выдать карту',`${muted('Покупатель должен согласиться добровольно. Карта не даёт автоматической скидки и не предусматривает рассылки.')}
 <form class="form" data-form="member"><label class="check"><input type="checkbox" name="explicit_opt_in" required />Покупатель согласился участвовать в программе лояльности.</label><button class="btn primary" type="submit">Создать карту</button></form>${secretBlock()}`)}${card('Конфиденциальность',warning([d.privacy,'При удалении карты история её привязки к покупкам очищается.']))}</div>
 <div class="stack">${card('Карты магазина',d.items.length?d.items.map(x=>row(`Карта №${x.id} · ${esc(x.home_store)}`,
 `Выдана: ${esc(x.created_at)} · чеков: ${num(x.linked_receipts)} · статус: ${x.status==='active'?'Активна':'Отозвана'}`,
 x.status==='active'?button('Отозвать','revoke',x.id,'warn'):'<span class="tag">Отозвана</span>')).join(''):empty('Карты пока не выданы'))}</div></div>`;
}
function renderReceipts(){const d=state.data;return `<div class="stats">${stat('Чеков привязано',num(d.items.length),'Последние 100 по филиалу')}${stat('Выручка этих чеков',money(d.items.reduce((n,x)=>n+x.amount_kopeks,0)),'Это не эффект программы')}${stat('Уникальных карт',num(new Set(d.items.map(x=>x.member_id)).size),'Только среди привязанных чеков')}${stat('Подтверждение','POS','Чек должен существовать')}</div>
 <div class="grid"><div class="stack">${card('Привязать покупку',`${muted('Сотрудник вводит код добровольного участника и ID уже зарегистрированного кассового чека. Чек нельзя связать с двумя картами.')}
 <form data-form="receipt" class="form">${field('member_code','Код карты','text','','placeholder="OXM-..." minlength="36" maxlength="36"')}${field('sale_id','Номер чека в OSMANX','number','','min="1"')}<button class="btn primary" type="submit">Привязать чек</button></form>`)}${card('Важно',warning([d.note]))}</div>
 <div class="stack">${card('Журнал покупок участников',d.items.length?d.items.map(x=>row(`Чек №${x.sale_id} · ${money(x.amount_kopeks)}`,`Карта №${x.member_id} · ${esc(x.occurred_at)}`)).join(''):empty('Привязанных чеков нет'))}</div></div>`;}
function campaignForm(){return `<form class="form" data-form="campaign">${field('title','Название акции','text','','minlength="3" maxlength="100"')}${field('reward_description','Описание бонуса','text','','minlength="3" maxlength="180"')}${field('unit_cost_kopeks','Стоимость одного бонуса (коп.)','number','15000','min="1"')}${field('budget_kopeks','Общий бюджет (коп.)','number','300000','min="1"')}${field('max_claims','Максимум бонусов','number','20','min="1"')}${field('min_spend_kopeks','Минимальная сумма чека (коп.)','number','50000','min="0"')}${field('starts_on','Дата начала','date',today())}${field('ends_on','Дата окончания','date',daysFromNow(14))}<button class="btn primary" type="submit">Создать кампанию</button></form>`;}
function renderCampaigns(){const d=state.data;const total=d.items.reduce((s,x)=>s+x.reserved_kopeks,0);
 return `<div class="stats">${stat('Всего кампаний',num(d.items.length),'В выбранном филиале')}${stat('Бонусов выдано',num(d.items.reduce((a,b)=>a+b.issued+b.redeemed,0)),'Лимит по бюджету')}${stat('Сверено с чеками',num(d.items.reduce((a,b)=>a+b.redeemed,0)),'Не означает выдачу бонуса')}${stat('Бюджет зарезервирован',money(total),'Плановые затраты')}</div>
 <div class="grid"><div class="stack">${card('Новая кампания',`${muted('Стоимость бонуса и бюджет указываются в копейках. Выдача и погашение подтверждаются сотрудником — реального списания денег нет.')}${campaignForm()}${secretBlock()}`)}${card('Методика',warning([d.note,'Увеличение выручки и ROI не рассчитываются без сопоставимых данных и затрат.']))}</div>
 <div class="stack">${card('Активности',d.items.length?d.items.map(x=>`<div class="row"><div><strong>${esc(x.title)}</strong><small>${esc(x.reward_description)} · ${esc(x.starts_on)} — ${esc(x.ends_on)}<br>Выдано: ${x.issued}, сверено: ${x.redeemed} · бюджет: ${money(x.reserved_kopeks)} / ${money(x.budget_kopeks)}</small></div><div class="actions">${button('Экономика','effect',x.id,'quiet')}${button(x.active?'Остановить':'Включить','toggle-campaign',x.id,x.active?'warn':'')}</div></div>
 ${state.effect&&state.effect.campaign.id===x.id?`<div class="warnbox">Чеки: ${state.effect.verified_receipts}, оборот по ним: ${money(state.effect.linked_receipt_revenue_kopeks)}. Оценка затрат на бонусы: ${money(state.effect.estimated_reward_cost_kopeks)}. ROI: не определён без доказанного прироста прибыли.</div>`:''}
 <form class="form" data-form="claim" data-id="${x.id}" style="margin:15px 0 22px;border-bottom:1px solid #364155;padding-bottom:20px">${field('member_code','Код участника для выдачи бонуса','text','','minlength="36" maxlength="36"')}<button type="submit" class="btn" ${!x.active?'disabled':''}>Выдать код бонуса</button></form>
 <form class="form" data-form="redeem" data-id="${x.id}" style="margin-bottom:22px">${field('coupon_code','Одноразовый код бонуса','text','','minlength="36" maxlength="36"')}${field('sale_id','ID подтверждённого чека','number','','min="1"')}<button type="submit" class="btn">Сверить с чеком</button></form>`).join(''):empty('Создайте первую кампанию'))}</div></div>`;
}
function renderRetention(){const d=state.data;const eligible=d.cohorts.reduce((n,r)=>n+r.matured,0),repeated=d.cohorts.reduce((n,r)=>n+r.repeat_within_30d,0);
 return `<div class="stats">${stat('Покупателей с картой',num(d.observed_members),'Наблюдаемые участники')}${stat('С повторными чеками',num(d.observed_repeat_members),'Не все покупатели магазина')}${stat('Покрытие чеков',d.coverage_percent===null?'—':d.coverage_percent+'%','Только привязанные чеки')}${stat('Повтор в течение 30 дней',eligible?Math.round(repeated*100/eligible)+'%':'—','Только зрелые когорты')}</div>
 <div class="grid"><div class="stack">${card('Как читать аналитику',warning(d.warnings))}${card('Показатели',row('Все зарегистрированные чеки',num(d.all_receipts))+row('Привязанные чеки',num(d.linked_receipts))+row('Зрелые участники',num(eligible)))}</div>
 <div class="stack">${card('Когорты первых покупок',d.cohorts.length?`<div class="tablewrap"><table class="tbl"><thead><tr><th>Месяц</th><th>Новые</th><th>Зрелые</th><th>Вернулись ≤30 дней</th><th>Доля</th></tr></thead><tbody>${d.cohorts.map(x=>`<tr><td>${esc(x.month)}</td><td>${num(x.first_buyers)}</td><td>${num(x.matured)}</td><td>${num(x.repeat_within_30d)}</td><td>${x.repeat_rate_30d_percent===null?'Недостаточно времени':x.repeat_rate_30d_percent+'%'}</td></tr>`).join('')}</tbody></table></div>`:empty('Нужны как минимум одна карта и один привязанный чек'))}</div></div>`;
}
function renderAssortment(){const d=state.data;
 return `<div class="stats">${stat('Сигналов к действию',num(d.items.length),'Проверяемые гипотезы')}${stat('Запросов без артикула',num(d.unresolved_demand),'Не будут угаданы системой')}${stat('Период',num(d.days)+' дн.','Реальные записи')}${stat('Автозакупки','0','Только подготовка решения')}</div>
 <div class="grid"><div class="stack">${card('Период исследования',`<form data-form="assortment" class="form"><label>Дней назад<select name="days"><option value="14" ${state.days===14?'selected':''}>14</option><option value="30" ${state.days===30?'selected':''}>30</option><option value="60" ${state.days===60?'selected':''}>60</option><option value="90" ${state.days===90?'selected':''}>90</option></select></label><button class="btn primary" type="submit">Проанализировать</button></form>`)}${card('Ограничения',warning(d.warnings))}</div>
 <div class="stack">${card('Возможности ассортимента',d.items.length?d.items.map(x=>row(`${esc(x.product)} · ${esc(x.size)} · ${esc(x.color)}`,
 `SKU ${esc(x.sku)} · запросов ${num(x.requests)} · продано ${num(x.sold_units)} · учётный остаток ${num(x.quantity)} · оборот по строкам чеков ${money(x.receipt_item_revenue_kopeks)}`,
 `<span class="tag ${x.signal==='check_restock'?'red':'good'}">${esc(x.action)}</span>`)).join(''):empty('При текущих критериях заметных сигналов нет. Это не означает, что ассортимент оптимален.'))}</div></div>`;
}
root.addEventListener('click',async ev=>{
 const tab=ev.target.closest('[data-tab]');if(tab){state.tab=tab.dataset.tab;state.secret=null;state.effect=null;shell();try{await reload()}catch(e){toast(e.message,true)}return}
 const btn=ev.target.closest('[data-action]');if(!btn)return;
 const action=btn.dataset.action,id=Number(btn.dataset.id);
 try{
  if(action==='revoke'){
   if(!confirm('Отозвать карту, удалить связи с чеками и очистить персональные связи в бонусах?'))return;
   await api(`/admin/r11/members/${id}`,{method:'DELETE'});state.secret=null;toast('Карта отозвана, связанные записи очищены');await reload();
  }
  if(action==='toggle-campaign'){
   const campaign=state.data.items.find(x=>x.id===id);
   await api(`/admin/r11/campaigns/${id}`,{method:'PATCH',body:{active:!campaign.active}});
   toast('Статус кампании изменён');await reload();
  }
  if(action==='effect'){
   state.effect=await api(`/admin/r11/campaigns/${id}/effect`);render();
  }
 }catch(err){toast(err.message,true)}
});
root.addEventListener('change',async e=>{if(e.target.id==='growth-store'){state.slug=e.target.value;state.secret=null;state.effect=null;try{await reload()}catch(err){toast(err.message,true)}}});
root.addEventListener('submit',async e=>{
 const form=e.target.closest('[data-form]');if(!form)return;e.preventDefault();
 const data=Object.fromEntries(new FormData(form));const kind=form.dataset.form;const id=form.dataset.id;
 const slug=state.slug;const submit=form.querySelector('[type="submit"]');if(submit)submit.disabled=true;
 try{
  if(kind==='member'){
   const out=await api('/admin/r11/members',{method:'POST',body:{slug,explicit_opt_in:data.explicit_opt_in==='on'}});
   state.secret={code:out.member_code,title:'Карта участника'};toast('Карта создана. Сохраните одноразовый код');
  }
  if(kind==='receipt'){
   await api('/admin/r11/receipts',{method:'POST',body:{member_code:data.member_code,sale_id:Number(data.sale_id)}});
   state.secret=null;toast('Чек подтверждён и привязан к карте');
  }
  if(kind==='campaign'){
   await api('/admin/r11/campaigns',{method:'POST',body:{slug,title:data.title,reward_description:data.reward_description,
    unit_cost_kopeks:Number(data.unit_cost_kopeks),budget_kopeks:Number(data.budget_kopeks),
    max_claims:Number(data.max_claims),min_spend_kopeks:Number(data.min_spend_kopeks),
    starts_on:data.starts_on,ends_on:data.ends_on}});
   state.secret=null;toast('Кампания создана');
  }
  if(kind==='claim'){
   const out=await api(`/admin/r11/campaigns/${id}/claim`,{method:'POST',body:{member_code:data.member_code}});
   state.secret={code:out.coupon_code,title:'Код бонуса'};toast('Бонус зарезервирован в рамках лимита');
  }
  if(kind==='redeem'){
   await api(`/admin/r11/campaigns/${id}/redeem`,{method:'POST',body:{coupon_code:data.coupon_code,sale_id:Number(data.sale_id)}});
   state.secret=null;toast('Бонус сверён с кассовым чеком');
  }
  if(kind==='assortment'){
   state.days=Number(data.days);state.secret=null;
  }
  await reload();
 }catch(err){toast(err.message,true)}finally{if(submit)submit.disabled=false}
});
init();
