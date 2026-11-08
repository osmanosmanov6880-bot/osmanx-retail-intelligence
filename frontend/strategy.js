/* OSMANX R0.8 · Five connected operational workflows, no artificial KPIs. */
const root=document.querySelector('#strategy-root'),notify=document.querySelector('#strategy-toast');
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=x=>new Intl.NumberFormat('ru-RU').format(Number(x||0));
const rub=x=>new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:2}).format(Number(x||0)/100);
const uuid=()=>crypto.randomUUID?.()||`r08-${Date.now()}-${Math.random().toString(36).slice(2)}`;
const iso=()=>new Date().toISOString().slice(0,10);
const S={slug:'central',tab:'brief',stores:[],config:{},data:{},team:[],days:30,safety:0};
const tabs=[['brief','Отчёт директора'],['replenishment','План дозакупки'],['suppliers','Поставщики'],['fittings','Примерочные'],['tasks','Центр задач']];
let toastTimer;
function toast(s,error=false){clearTimeout(toastTimer);notify.innerHTML=`<div class="strategy-toaster ${error?'error':''}">${esc(s)}</div>`;toastTimer=setTimeout(()=>notify.innerHTML='',4300)}
async function api(url,{method='GET',body,csv=false}={}){
 const headers={Accept:csv?'text/csv':'application/json'};
 const token=sessionStorage.getItem('osmanx_admin_token');if(token)headers.Authorization='Bearer '+token;
 if(body!==undefined)headers['Content-Type']='application/json';
 const r=await fetch('/api'+url,{method,headers,body:body!==undefined?JSON.stringify(body):undefined,cache:'no-store'});
 if(csv){if(!r.ok)throw new Error('Ошибка выгрузки '+r.status);return r.blob()}
 const o=await r.json().catch(()=>({detail:'Неверный ответ сервера'}));
 if(!r.ok)throw new Error(typeof o.detail==='string'?o.detail:JSON.stringify(o.detail||'Ошибка '+r.status));return o;
}
const field=(n,label,type='text',options={})=>`<div class="strategy-field"><label for="st-${esc(n)}">${esc(label)}</label><input id="st-${esc(n)}" name="${esc(n)}" type="${type}" ${options.required===false?'':'required'} ${options.min!==undefined?`min="${options.min}"`:''} ${options.max!==undefined?`max="${options.max}"`:''} ${options.step!==undefined?`step="${options.step}"`:''} ${options.value!==undefined?`value="${esc(options.value)}"`:''} ${options.placeholder?`placeholder="${esc(options.placeholder)}"`:''}></div>`;
const select=(n,label,options)=>`<div class="strategy-field"><label>${esc(label)}</label><select name="${esc(n)}">${options.map(x=>`<option value="${esc(x.value)}">${esc(x.label)}</option>`).join('')}</select></div>`;
const card=(title,html)=>`<section class="card"><h2 class="strategy-heading">${esc(title)}</h2>${html}</section>`;
const row=(title,sub,buttons='')=>`<div class="strategy-row"><div><strong>${title}</strong><small>${sub}</small></div><div class="tools">${buttons}</div></div>`;
const empty=s=>`<div class="strategy-no-data">${esc(s)}</div>`;
const warn=lines=>(lines||[]).map(w=>`<div class="strategy-warning">${esc(w)}</div>`).join('');
const button=(label,action,id,cls='')=>`<button class="button ${cls}" data-action="${esc(action)}" data-id="${esc(id)}">${esc(label)}</button>`;
function shell(){
 root.innerHTML=`<main class="app"><header class="top"><div><div class="brand">OSMAN<span>X</span></div><div class="brandline">Retail Intelligence / Strategy R0.8</div></div><div class="toplinks">
 <select id="strategy-store" class="store-select" aria-label="Филиал">${S.stores.map(x=>`<option value="${esc(x.slug)}" ${S.slug===x.slug?'selected':''}>${esc(x.name)}</option>`).join('')}</select>
 <a class="toplink primary" href="/static/evidence.html">Evidence Lab R0.9</a><a class="toplink" href="/static/operations.html">Операционный центр</a><a class="toplink" href="/static/workflows.html">Закупки R0.6</a><a class="toplink" href="/">Кабинет</a></div></header>
 <section class="strategy-hero"><div><span class="strategy-kicker">Коммерческая стратегия / от наблюдений к решениям</span><h1>Умный магазин.<br>Измеримые действия.</h1><p>Спрос превращается в план закупок, поставки становятся проверяемыми, примерки объясняют узкие места, задачи получают ответственных, а директор видит источники каждой цифры.</p></div><div class="strategy-hero-logo">OX.</div></section>
 ${S.config.demo?'<div class="banner">ДЕМО-РЕЖИМ: цифры из искусственного набора данных, не показывайте как результаты реального магазина.</div>':''}
 <nav class="strategy-tabs" role="tablist" aria-label="Разделы стратегии">${tabs.map(([id,label])=>`<button role="tab" aria-selected="${S.tab===id}" data-tab="${id}">${label}</button>`).join('')}</nav>
 <div id="strategy-view"></div><footer class="strategy-footer">OSMANX WORLD · Оценки спроса — рекомендации, а не прогноз выручки. Данные клиента изолированы по организации и филиалу. Платные закупки и уведомления покупателям автоматически не отправляются.</footer></main>`;
}
async function reload(){
 const s=encodeURIComponent(S.slug);const q=`slug=${s}`;
 if(S.tab==='brief')S.data=await api('/admin/r08/brief?'+q);
 if(S.tab==='replenishment')S.data={preview:await api(`/admin/r08/replenishment/preview?${q}&period_days=${S.days}&safety_units=${S.safety}`),plans:await api('/admin/r08/replenishment?'+q)};
 if(S.tab==='suppliers')S.data=await api('/admin/r08/suppliers?'+q);
 if(S.tab==='fittings')S.data=await api('/admin/r08/fittings?'+q);
 if(S.tab==='tasks')S.data=await api('/admin/r08/tasks?'+q);
 render();
}
async function init(){try{
 S.config=await api('/config');
 if(!S.config.demo&&!sessionStorage.getItem('osmanx_admin_token')){root.innerHTML=`<main class="app"><section class="strategy-hero"><div><h1>Требуется вход</h1><p>Сначала войдите в административный кабинет, чтобы получить доступ к управленческим данным.</p><a class="button red" href="/">Войти</a></div></section></main>`;return}
 S.stores=await api('/admin/stores');if(!S.stores.length)throw new Error('Нет назначенных филиалов');
 const requested=new URLSearchParams(location.search).get('store');S.slug=(S.stores.find(x=>x.slug===requested)||S.stores[0]).slug;
 try{const t=await api('/admin/team');S.team=t.items||t.users||t||[]}catch{S.team=[]}
 shell();await reload();
}catch(e){root.innerHTML=`<main class="app"><div class="error"><h2>Не удалось открыть Центр стратегии</h2><p>${esc(e.message)}</p><a class="button" href="/">В кабинет</a></div></main>`}}
function render(){const view=document.querySelector('#strategy-view');if(!view)return;
 const factories={brief:brief,replenishment:replenishment,suppliers:suppliers,fittings:fittings,tasks:tasks};view.innerHTML=factories[S.tab]();}
function brief(){const d=S.data;return `<div class="strategy-statline"><div class="strategy-stat"><small>Посетители</small><b>${num(d.visitors)}</b><em>Отмечены датчиком или вручную</em></div><div class="strategy-stat"><small>Покупки</small><b>${num(d.purchases)}</b><em>По зарегистрированным чекам</em></div><div class="strategy-stat"><small>Выручка</small><b>${rub(d.revenue_kopeks)}</b><em>Не является прибылью</em></div><div class="strategy-stat"><small>Конверсия</small><b>${d.conversion_percent===null?'—':d.conversion_percent+'%'}</b><em>Сопоставляйте источники</em></div></div>
 <div class="strategy-grid"><div class="stack">${card('Зафиксировать отчёт',`<p class="strategy-muted">Дневной снимок сохраняется один раз и не меняется задним числом. Можно скачать CSV.</p><div class="strategy-form">${field('day','Отчётный день','date',{value:d.day})}<div class="strategy-actions">${button('Сохранить снимок','snapshot','', 'red')}${button('Скачать CSV','csv','')}</div></div>`)}${card('Потоки данных',`${Object.entries(d.visitor_sources).map(([name,count])=>row(esc(name),num(count)+' посещений')).join('')||empty('За этот день нет событий потока')}${warn(d.warnings)}`)}</div>
 <div class="stack">${card('Что требует действий',`${row('Открытые запросы на товар',num(d.open_demand)+' случаев')}${row('Необработанные вызовы продавца',num(d.open_assistance)+' обращений')}${row('Перемещения в пути',num(d.in_transit_transfers)+' документов')}${row('Новые задачи',num(d.tasks.open||0)+' задач')}${row('В работе',num(d.tasks.in_progress||0)+' задач')}<p class="strategy-muted">Эти показатели описывают зарегистрированные события, но не мотивы каждого покупателя.</p>`)}${card('История сохранённых отчётов',`<div class="strategy-actions">${button('Загрузить архив','snapshots','')}</div><div id="snapshot-history" class="strategy-muted">Архив появится после запроса.</div>`)}</div></div>`}
function replenishment(){const {preview:p,plans}=S.data;return `<div class="strategy-grid"><div class="stack">${card('Рассчитать дозакупку',`<p class="strategy-muted">На основе неудовлетворённых запросов и доступного остатка. Формула — эвристика, а не прогноз продаж.</p><form data-form="plan" class="strategy-form"><div class="strategy-inline">${field('period_days','Дней наблюдения','number',{min:7,max:90,value:S.days})}${field('safety_units','Страховой запас','number',{min:0,max:50,value:S.safety})}</div><div class="strategy-actions"><button class="button" type="button" data-action="preview">Пересчитать</button><button class="button red" type="submit" ${!p.lines.length?'disabled':''}>Сохранить план</button></div></form>`)}${card('Прозрачность расчёта',`${row('Запросов за период',num(p.total_requests))}${row('Артикул не определён',num(p.total_unresolved))}${warn(p.warnings)}${p.unresolved.length?`<p class="strategy-muted">Неразобранные: ${p.unresolved.slice(0,5).map(x=>esc(x.product+' · '+x.reason)).join(' · ')}</p>`:''}`)}</div><div class="stack">${card('Рекомендуемые позиции',p.lines.length?p.lines.map(x=>row(esc(x.product+' · '+x.size),`SKU ${esc(x.sku)} · запросов ${x.requests} · доступно ${x.available}`,`<span class="strategy-pill good">+${x.recommended_qty} шт.</span>`)).join(''):empty('Нет подтверждённых артикулов для расчёта. Добавьте информацию о SKU в учётной системе.'))}${card('Сохранённые планы и черновики заказов',plans.items.length?plans.items.map(x=>`<div class="strategy-row"><div><strong>План №${x.id} · ${x.lines.length} позиций</strong><small>${esc(x.status)} · ${esc(x.created_at.slice(0,16))} · заказ ${x.order_id||'не оформлен'}</small></div>${x.status==='draft'?button('Оформить черновик заказа','show-order',x.id,'red'):''}</div>${x.status==='draft'?`<form class="strategy-form" hidden data-order="${x.id}">${field('supplier','Поставщик','text',{placeholder:'Компания-поставщик'})}${field('reference','Номер заказа','text',{value:'OX-R08-'+x.id})}${field('expected_date','Плановая дата','date',{required:false})}${x.lines.map(line=>field('cost_'+line.id,`Себестоимость ₽ · ${line.sku}`,'number',{min:0,step:'0.01',value:0})).join('')}<button type="submit" class="button red">Создать заказ без отправки поставщику</button></form>`:''}`).join(''):empty('Планов пока нет.'))}</div></div>`}
function suppliers(){const a=S.data.items;return `<div class="strategy-grid"><div>${card('Оценка поставщика',`<p class="strategy-muted">Субъективная оценка хранится отдельно от измеряемых сроков поставки.</p><form data-form="review" class="strategy-form">${select('supplier','Поставщик',a.map(x=>({value:x.supplier,label:x.supplier})))}${select('rating','Оценка',[1,2,3,4,5].map(x=>({value:x,label:x+' / 5'})))}${field('issue','Комментарий','text',{required:false,placeholder:'Доставка задержалась на 3 дня'})}<button class="button red" ${!a.length?'disabled':''}>Сохранить оценку</button></form>`)}${card('Методика',`<p class="strategy-muted">Сроки считаются по датам заказов и подтверждённой приёмки. Процент отображается только при ≥3 завершённых поставках с плановой датой.</p>${warn(S.data.warnings)}`)}</div><div>${card('Фактическая дисциплина поставщиков',a.length?a.map(x=>row(esc(x.supplier),`Заказов ${x.orders} · завершено ${x.received} · просрочено в работе ${x.overdue_open} · осталось ${x.outstanding_units} шт. · наблюдений ${x.samples_for_timeliness}`,
 `<span class="strategy-pill ${x.overdue_open?'alert':'good'}">${x.on_time_percent===null?'Недостаточно данных':x.on_time_percent+'% вовремя'}</span>`)+warn(x.warnings)+(x.reviews||[]).map(r=>`<p class="strategy-muted">Оценка ${r.rating}/5 · ${esc(r.issue||'Без комментария')}</p>`).join('')).join(''):empty('Сначала создайте заказ поставщику в модуле закупок.'))}</div></div>`}
function fittings(){const d=S.data;return `<div class="strategy-grid"><div class="stack">${card('Проверка гипотезы',`<form class="strategy-form" data-form="fitting">${field('product','Модель / SKU','text',{placeholder:'COAT-XL'})}${field('size','Размер','text',{required:false,placeholder:'XL'})}${field('hypothesis','Что хотите проверить?','text',{placeholder:'Проверить посадку модели на клиентах'})}<button class="button red">Записать гипотезу</button></form>`)}${card('Реальные наблюдения',d.items.length?d.items.map(x=>row(esc(x.product+(x.size?' · '+x.size:'')),`Примерок ${x.trials} · купили ${x.purchases} · конверсия ${x.conversion_percent??'—'}% · причины ${Object.entries(x.reasons).map(([key,n])=>key+': '+n).join(', ')||'не указаны'}`,`<span class="strategy-pill ${x.signal==='needs_review'?'alert':'good'}">${x.signal==='needs_review'?'Проверить':'Наблюдение'}</span>`)).join(''):empty('Нет данных о примерках в этом филиале'))}</div><div>${card('Гипотезы и результаты проверок',d.actions.length?d.actions.map(x=>row(esc(x.product),`${esc(x.hypothesis)} · ${esc(x.status)}${x.evidence?' · '+esc(x.evidence):''}`,x.status==='open'?button('В работу','fit-start',x.id)+button('Закрыть с результатом','fit-done',x.id,'red'):x.status==='testing'?button('Закрыть с результатом','fit-done',x.id,'red'):'')).join(''):empty('Создайте гипотезу после анализа примерок.'))}<p class="strategy-muted">Опросы и примерки не отслеживают личности. Причины заполняются вручную и требуют проверки на достаточном объёме.</p></div></div>`}
function tasks(){const d=S.data;const choices=[{value:'',label:'Без назначения'},...S.team.filter(x=>x.active!==0).map(x=>({value:x.id,label:x.full_name||x.email||('Сотрудник '+x.id)}))];return `<div class="strategy-grid"><div>${card('Поставить задачу',`<form class="strategy-form" data-form="task">${field('title','Что нужно сделать?','text',{placeholder:'Проверить размер XL у поставщика'})}${select('category','Направление',[['demand','Неудовлетворённый спрос'],['supplier','Поставщик'],['fitting','Примерочные'],['service','Обслуживание'],['operations','Операции']].map(([value,label])=>({value,label})))}${select('assigned_user_id','Ответственный',choices)}${field('due_date','Срок','date',{required:false})}<button class="button red">Создать задачу</button></form>`)}${card('Правило завершения',`<p class="strategy-muted">Для отметки «Выполнено» необходим конкретный результат. Фиксируется время изменения и автор в журнале аудита.</p>`)}</div><div>${card('Задачи магазина',d.items.length?d.items.map(x=>row(esc(x.title),`${esc(x.category)} · ${x.assigned_name?esc(x.assigned_name):'Не назначена'} · срок ${x.due_date||'—'} · ${esc(x.status)} ${x.evidence?'· '+esc(x.evidence):''}`,x.status==='open'?button('Начать','task-start',x.id)+button('Выполнено','task-done',x.id,'red'):x.status==='in_progress'?button('Выполнено','task-done',x.id,'red'):'')).join(''):empty('Нет задач. Создайте первое конкретное действие.'))}</div></div>`}
root.addEventListener('change',async e=>{if(e.target.id==='strategy-store'){S.slug=e.target.value;try{await reload()}catch(x){toast(x.message,true)}}});
root.addEventListener('click',async e=>{
 const tab=e.target.closest('[data-tab]');if(tab){S.tab=tab.dataset.tab;root.querySelectorAll('[data-tab]').forEach(x=>x.setAttribute('aria-selected',String(x===tab)));try{await reload()}catch(x){toast(x.message,true)}return;}
 const b=e.target.closest('[data-action]');if(!b)return;
 const action=b.dataset.action,id=b.dataset.id;
 if(action==='show-order'){const form=root.querySelector(`[data-order="${id}"]`);if(form)form.hidden=!form.hidden;return}
 b.disabled=true;
 try{
  if(action==='preview'){const f=root.querySelector('[data-form=plan]');S.days=Number(f.elements.period_days.value);S.safety=Number(f.elements.safety_units.value);await reload();return}
  if(action==='csv'){
    const day=root.querySelector('[name=day]').value;const blob=await api(`/admin/r08/brief/export.csv?slug=${encodeURIComponent(S.slug)}&day=${day}`,{csv:true});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`OSMANX-brief-${day}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return;
  }
  if(action==='snapshot'){const day=root.querySelector('[name=day]').value;const v=await api(`/admin/r08/brief/snapshot?slug=${encodeURIComponent(S.slug)}&day=${day}`,{method:'POST'});toast(v.duplicate?'Этот день уже сохранён':'Дневной отчёт сохранён');return}
  if(action==='snapshots'){const v=await api('/admin/r08/brief/snapshots?slug='+encodeURIComponent(S.slug));root.querySelector('#snapshot-history').innerHTML=v.items.length?v.items.map(x=>`<div class="strategy-row"><strong>${esc(x.day)}</strong><small>SHA-256: ${esc(x.payload_sha256.slice(0,16))}…</small></div>`).join(''):empty('Снимков пока нет');return}
  if(action==='fit-start'||action==='fit-done'){const evidence=action==='fit-done'?prompt('Какой проверяемый результат получен? (минимум 12 символов)'):'';if(action==='fit-done'&&evidence===null)return;
   await api('/admin/r08/fittings/actions/'+id,{method:'PATCH',body:{status:action==='fit-start'?'testing':'done',evidence:evidence||''}});
  }else if(action==='task-start'||action==='task-done'){const evidence=action==='task-done'?prompt('Укажите проверяемый результат (минимум 12 символов)'):'';if(action==='task-done'&&evidence===null)return;
   await api('/admin/r08/tasks/'+id,{method:'PATCH',body:{status:action==='task-start'?'in_progress':'done',evidence:evidence||''}});
  }else return;
  toast('Изменение сохранено');await reload();
 }catch(x){toast(x.message,true)}finally{b.disabled=false}
});
root.addEventListener('submit',async e=>{
 const form=e.target.closest('form');if(!form)return;if(!form.dataset.form&&!form.dataset.order)return;e.preventDefault();const button=form.querySelector('button[type=submit]');if(button)button.disabled=true;
 const o=Object.fromEntries(new FormData(form));try{
  if(form.dataset.form==='plan'){
   S.days=Number(o.period_days);S.safety=Number(o.safety_units);
   await api('/admin/r08/replenishment',{method:'POST',body:{slug:S.slug,period_days:S.days,safety_units:S.safety,request_id:uuid()}});
  }else if(form.dataset.order){
   const plan=S.data.plans.items.find(x=>x.id===Number(form.dataset.order));
   if(!plan)throw new Error('План не найден');
   const costs=plan.lines.map(x=>({sku:x.sku,unit_cost_rub:Number(o['cost_'+x.id])}));
   await api(`/admin/r08/replenishment/${plan.id}/order`,{method:'POST',body:{supplier:o.supplier,reference:o.reference,expected_date:o.expected_date||null,costs}});
  }else if(form.dataset.form==='review'){
   await api('/admin/r08/suppliers/review',{method:'POST',body:{slug:S.slug,supplier:o.supplier,rating:Number(o.rating),issue:o.issue||''}});
  }else if(form.dataset.form==='fitting'){
   await api('/admin/r08/fittings/actions',{method:'POST',body:{slug:S.slug,product:o.product,size:o.size||'',hypothesis:o.hypothesis}});
  }else if(form.dataset.form==='task'){
   await api('/admin/r08/tasks',{method:'POST',body:{slug:S.slug,request_id:uuid(),title:o.title,category:o.category,assigned_user_id:o.assigned_user_id?Number(o.assigned_user_id):null,due_date:o.due_date||null}});
  }
  toast('Операция сохранена');await reload();
 }catch(x){toast(x.message,true)}finally{if(button)button.disabled=false}
});
init();
