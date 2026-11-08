/* OSMANX R1.0 — independently useful executive operations, real endpoints only. */
const root=document.querySelector('#experience-root');
const notices=document.querySelector('#xp-toast');
const escapeHTML=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const number=x=>new Intl.NumberFormat('ru-RU').format(Number(x||0));
const rub=x=>x==null?'—':new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:0}).format(x/100);
const short=x=>x?new Date(x).toLocaleString('ru-RU',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}):'—';
const uid=()=>crypto.randomUUID?.()||`ox-${Date.now()}-${Math.random().toString(36).slice(2)}`;
const today=()=>new Date().toISOString().slice(0,10);
const state={tab:'benchmark',slug:'central',stores:[],config:{},days:14,source:'sensor',day:today(),data:null};
const tabs=[['benchmark','01 · Филиалы'],['shifts','02 · Смены'],['service','03 · Сервис'],['pulse','04 · Опросы'],['incidents','05 · Инциденты']];
let timeout;
const button=(text,action,id='',color=false)=>`<button class="xp-button ${color?'red':''}" data-action="${action}" data-id="${escapeHTML(id)}">${escapeHTML(text)}</button>`;
const pill=(text,type='')=>`<span class="xp-pill ${type}">${escapeHTML(text)}</span>`;
const card=(title,body)=>`<section class="xp-card"><h2>${escapeHTML(title)}</h2>${body}</section>`;
const empty=(text)=>`<div class="xp-empty">${escapeHTML(text)}</div>`;
const notice=(text)=>`<div class="xp-alert">${escapeHTML(text)}</div>`;
const formField=(name,label,type='text',value='',optional=false)=>`<label>${escapeHTML(label)}<input name="${name}" type="${type}" value="${escapeHTML(value)}" ${optional?'':'required'}></label>`;
const formSelect=(name,label,opts)=>`<label>${escapeHTML(label)}<select name="${name}">${opts.map(o=>`<option value="${escapeHTML(o[0])}">${escapeHTML(o[1])}</option>`).join('')}</select></label>`;
const stat=(label,value,note)=>`<article class="xp-metric"><small>${escapeHTML(label)}</small><strong>${escapeHTML(value)}</strong><em>${escapeHTML(note)}</em></article>`;
const row=(title,details,tools='')=>`<div class="xp-row"><div><strong>${escapeHTML(title)}</strong><small>${escapeHTML(details)}</small></div><div class="xp-tools">${tools}</div></div>`;
async function api(path,{method='GET',body}={}){
 const token=sessionStorage.getItem('osmanx_admin_token');const headers={Accept:'application/json'};
 if(token)headers.Authorization=`Bearer ${token}`;
 if(body!==undefined)headers['Content-Type']='application/json';
 const response=await fetch(`/api${path}`,{method,headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
 const result=await response.json().catch(()=>({detail:'Неверный ответ сервера'}));
 if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:`Ошибка ${response.status}`);
 return result;
}
function flash(text,error=false){clearTimeout(timeout);notices.innerHTML=`<div class="xp-toast ${error?'error':''}">${escapeHTML(text)}</div>`;timeout=setTimeout(()=>notices.replaceChildren(),4500)}
function shell(){root.innerHTML=`<main class="xp-shell"><header class="xp-header"><div><div class="xp-brand">OSMAN<span>X</span></div><small>RETAIL INTELLIGENCE / EXPERIENCE OPERATIONS</small></div><nav class="xp-headlinks" aria-label="Основная навигация"><select class="xp-select" id="xp-store" aria-label="Филиал">${state.stores.map(s=>`<option value="${escapeHTML(s.slug)}" ${s.slug===state.slug?'selected':''}>${escapeHTML(s.name)}</option>`).join('')}</select><a href="/static/growth.html">Growth R1.1</a><a href="/static/evidence.html">Evidence Lab</a><a href="/">Кабинет</a></nav></header>
<section class="xp-hero"><span class="xp-kicker">EXECUTIVE / R1.0</span><h1>Управление качеством.<br>Подтверждённые действия.</h1><p>Сравнивайте филиалы по сопоставимым данным, планируйте нагрузку, измеряйте время помощи, собирайте анонимные ответы и устраняйте операционные отклонения.</p></section>
${state.config.demo?'<div class="xp-demo">ДЕМОНСТРАЦИОННЫЙ РЕЖИМ · искусственные показатели исключаются из проверяемых сравнений.</div>':''}
<div class="xp-tabs" role="tablist">${tabs.map(([id,label])=>`<button role="tab" data-tab="${id}" aria-selected="${state.tab===id}">${label}</button>`).join('')}</div><div id="xp-content" aria-live="polite"></div><footer class="xp-footer">OSMANX WORLD · Не ведётся распознавание лиц и персональное видеослежение. Сравнения — описательные, а не доказательство причинного эффекта. Публичный сервер и физическое оборудование не подключены.</footer></main>`}
async function start(){try{
 state.config=await api('/config');
 if(!state.config.demo&&!sessionStorage.getItem('osmanx_admin_token')){root.innerHTML='<main class="xp-error-page"><h1>Требуется вход</h1><p>Войдите в основной кабинет для доступа к данным компании.</p><a class="xp-button red" href="/">Открыть вход</a></main>';return}
 state.stores=await api('/admin/stores');if(!state.stores.length)throw Error('Нет доступных филиалов');
 const query=new URLSearchParams(location.search).get('store');state.slug=(state.stores.find(s=>s.slug===query)||state.stores[0]).slug;
 shell();await load();
}catch(e){root.innerHTML=`<main class="xp-error-page"><h1>Не удалось открыть систему</h1><p>${escapeHTML(e.message)}</p><a class="xp-button" href="/">Вернуться к входу</a></main>`}}
async function load(){const slug=encodeURIComponent(state.slug);let path;
 if(state.tab==='benchmark')path=`/admin/r10/benchmark?days=${state.days}&source_mode=${state.source}`;
 if(state.tab==='shifts')path=`/admin/r10/shifts?slug=${slug}&day=${state.day}`;
 if(state.tab==='service')path=`/admin/r10/service?slug=${slug}&days=${state.days}`;
 if(state.tab==='pulse')path=`/admin/r10/pulse?slug=${slug}`;
 if(state.tab==='incidents')path=`/admin/r10/incidents?slug=${slug}`;
 state.data=await api(path);render();}
function render(){const node=root.querySelector('#xp-content');if(!node)return;
 node.innerHTML=({benchmark:renderBenchmark,shifts:renderShifts,service:renderService,pulse:renderPulse,incidents:renderIncidents}[state.tab])();}
function renderBenchmark(){const d=state.data,complete=d.stores.filter(x=>x.comparable);
 return `<div class="xp-metrics">${stat('Филиалов с доступом',number(d.stores.length),'Учитываются только назначенные филиалы')}${stat('Можно сравнивать',number(complete.length),'Достаточно достоверных входов')}${stat('Учтено входов',number(d.stores.reduce((s,x)=>s+x.visits,0)),'Только выбранный источник')}${stat('Чеков зарегистрировано',number(d.stores.reduce((s,x)=>s+x.checks,0)),'Не уникальные покупатели')}</div>
 <div class="xp-grid"><div class="xp-stack">${card('Параметры сравнения',`<form class="xp-form" data-form="benchmark">${formSelect('days','Период',[[7,'7 дней'],[14,'14 дней'],[30,'30 дней']])}${formSelect('source','Единый источник входов',[['sensor','Автоматический датчик'],['manual','Ручной подсчёт']])}<button class="xp-button red">Сравнить филиалы</button></form>`)}${card('Методика',`<p class="xp-note">${escapeHTML(d.method)}</p><p class="xp-muted">${escapeHTML(d.warning)}</p>`)}</div>
 <div class="xp-stack">${card('Сопоставимые показатели',d.stores.length?d.stores.map(x=>row(x.name,`${x.visits} входов · ${x.checks} чеков · выручка ${rub(x.revenue_kopeks)} · средний чек ${rub(x.avg_check_kopeks)}`,pill(x.checks_per_100_visits===null?'Нет базы':x.checks_per_100_visits+' / 100',x.comparable?'good':'warning'))+x.warnings.map(notice).join('')).join(''):empty('Нет филиалов для сравнения.'))}</div></div>`;}
function renderShifts(){const d=state.data;const capacity=d.hours.reduce((s,x)=>s+x.planned_capacity,0);
 return `<div class="xp-metrics">${stat('Смены на дату',number(d.shifts.length),'Плановая нагрузка')}${stat('Сумма часовой ёмкости',number(capacity),'Возможности обслуживания')}${stat('Нагрузка по датчикам',number(d.hours.reduce((s,x)=>s+x.recorded_visitors,0)),'Без демоданных и ручного ввода')}${stat('Часов с возможным дефицитом',number(d.hours.filter(x=>x.capacity_gap>0).length),'Не оценка качества конкретных людей')}</div><div class="xp-grid"><div class="xp-stack">
 ${card('Добавить смену',`<form class="xp-form" data-form="shift">${formField('label','Название смены','text','Торговый зал')}${formField('capacity_per_hour','Плановая пропускная способность, покупателей в час','number',12)}<div class="xp-cols">${formField('start_at','Начало','datetime-local')}${formField('end_at','Окончание','datetime-local')}</div><button class="xp-button red">Создать смену</button></form>`)}${card('Дата отчёта',`<form class="xp-form" data-form="shift-day">${formField('day','Посмотреть дату','date',state.day)}<button class="xp-button">Открыть</button></form><p class="xp-muted">${escapeHTML(d.method)}</p>`)}</div>
 <div class="xp-stack">${card('Покрытие по часам',d.hours.map(x=>`<div class="xp-barrow"><span>${x.hour}:00</span><div class="xp-bar"><span style="width:${Math.min(100,x.recorded_visitors/Math.max(1,x.planned_capacity,x.recorded_visitors)*100)}%"></span></div><span>${x.recorded_visitors} / ${x.planned_capacity}</span></div>`).join('')+'<p class="xp-muted">Входы / плановая ёмкость. Отсутствие подключённых датчиков не означает нулевой спрос.</p>')}${card('Запланированные смены',d.shifts.length?d.shifts.map(x=>row(x.label,`${short(x.start_at)} — ${short(x.end_at)} · ёмкость ${x.capacity_per_hour}/час`,button('Отменить','cancel-shift',x.id))).join(''):empty('На эту дату смены ещё не запланированы.'))}</div></div>`;}
function renderService(){const d=state.data;
 return `<div class="xp-metrics">${stat('Обращений за период',number(d.total),'Кнопки вызова помощи')}${stat('Принято вовремя',d.accept_rate_percent==null?'—':d.accept_rate_percent+'%','Из обращений с временем принятия')}${stat('Решено вовремя',d.resolve_rate_percent==null?'—':d.resolve_rate_percent+'%','Из завершённых')}${stat('Ожидают дольше нормы',number(d.pending_overdue),'Нужна оперативная проверка')}</div><div class="xp-grid"><div class="xp-stack">${card('Установить стандарт',`<form class="xp-form" data-form="sla"><div class="xp-cols">${formField('accept_minutes','Принять вызов за, мин','number',d.targets.accept_minutes)}${formField('resolve_minutes','Завершить за, мин','number',d.targets.resolve_minutes)}</div><button class="xp-button red">Сохранить норматив</button></form>`)}${card('Интерпретация',`<p class="xp-note">P50: ${d.p50_accept_minutes??'—'} мин · P90: ${d.p90_accept_minutes??'—'} мин.</p><p class="xp-muted">Отсчёт начинается при нажатии кнопки помощи. Это измерение процесса, не оценка личности покупателя.</p>`)}</div><div>${card('Последние обращения',d.recent.length?d.recent.map(x=>row('Обращение №'+x.id,`${x.category} · статус ${x.status} · ожидание ${x.wait_seconds==null?'не принято':Math.round(x.wait_seconds/60)+' мин.'}`,pill(x.accept_overdue?'Нарушен норматив':'В срок',x.accept_overdue?'warning':'good'))).join(''):empty('Нет зафиксированных обращений за выбранный период.'))}</div></div>`;}
function renderPulse(){const d=state.data;
 return `<div class="xp-metrics">${stat('Всего опросов',number(d.items.length),'Короткие анонимные кампании')}${stat('Действующих',number(d.items.filter(x=>x.active).length),'Только один на филиал')}${stat('Ответов',number(d.items.reduce((s,x)=>s+x.responses,0)),'Сумма зарегистрированных выборов')}${stat('Привязка терминала',d.paired_kiosk?'Есть':'Нет','Без неё опрос недоступен')}</div><div class="xp-grid"><div class="xp-stack">${card('Создать короткий опрос',`<form class="xp-form" data-form="pulse">${formField('title','Название для руководителя','text','Почему не купили?')}${formField('question','Вопрос на выходе','text','Чего вам сегодня не хватило?')}<label>Варианты (каждый с новой строки, 2–5)<textarea name="options" required>Нужного размера\nПодходящей модели\nУдобной цены\nПомощи консультанта</textarea></label><button class="xp-button red">Создать опрос</button></form>`)}${card('Терминал на выходе',`<div class="xp-help">Опрос доступен только после привязки планшета. Секрет передаётся в адресной строке после символа # и не отправляется серверу при открытии страницы. Сохраните его только на доверенном терминале.</div><p class="xp-muted">Открыть оболочку: <a href="/static/pulse.html?store=${encodeURIComponent(state.slug)}" target="_blank" rel="noreferrer">/static/pulse.html?store=${escapeHTML(state.slug)}</a></p>`)}</div><div class="xp-stack">${card('Кампании',d.items.length?d.items.map(x=>{const options=x.options;const counts=x.counts;const mx=Math.max(1,...Object.values(counts));return `<div class="xp-row"><div><strong>${escapeHTML(x.title)}</strong><small>${escapeHTML(x.question)} · ${x.responses} ответов</small></div><div class="xp-tools">${pill(x.active?'Активен':'Отключён',x.active?'good':'')}${button(x.active?'Отключить':'Запустить',x.active?'disable-pulse':'activate-pulse',x.id,!x.active)}</div></div>${options.map((label,i)=>`<div class="xp-barrow"><span>${i+1}</span><div class="xp-bar"><span style="width:${Math.round((counts[String(i)]||0)/mx*100)}%"></span></div><span>${counts[String(i)]||0}</span></div><div class="xp-muted">${escapeHTML(label)}</div>`).join('')}`}).join(''):empty('Создайте первую короткую анкету для выхода из магазина.'))}${card('Ограничения',`<p class="xp-muted">${escapeHTML(d.privacy)} Опрашиваются только добровольные участники. Отсутствие ответов не означает отсутствие проблем. Скидка автоматически не выдаётся.</p>`)}</div></div>`;}
function renderIncidents(){const d=state.data;
 return `<div class="xp-metrics">${stat('Инцидентов в журнале',number(d.items.length),'Сохранены с аудиторским следом')}${stat('Новых',number(d.items.filter(x=>x.status==='new').length),'Требуют признания проблемы')}${stat('В работе',number(d.items.filter(x=>x.status==='acknowledged').length),'Указано объяснение')}${stat('Сигналов сейчас',number(d.signals.length),'Автоматически выявленные условия')}</div><div class="xp-grid"><div class="xp-stack">${card('Проверка отклонений',`<p class="xp-muted">Проверяются три ситуации: отсутствие товарных строк в чеках, просроченные задачи и ожидание помощи дольше норматива. Пустой список — не гарантия отсутствия проблем.</p>${button('Повторно проверить','scan','',true)}${d.signals.map(x=>notice(x.title+': '+x.evidence)).join('')}`)}${card('Как действовать',`<p class="xp-note">1. Подтвердите, что сигнал требует проверки.<br>2. При необходимости создайте задачу в существующем центре задач.<br>3. Закройте инцидент с конкретным объяснением. История остаётся.</p>`)}</div><div>${card('Журнал и ответственные действия',d.items.length?d.items.map(x=>row(x.title,`${x.evidence} · ${short(x.created_at)} · статус ${x.status}${x.task_id?' · задача #'+x.task_id:''}`,x.status==='new'?button('Принять','ack-incident',x.id,true):x.status==='acknowledged'?button('Закрыть','close-incident',x.id,true):pill('Закрыт','good'))).join(''):empty('Пока нет зарегистрированных инцидентов. Проведите проверку.'))}</div></div>`;}
root.addEventListener('change',async e=>{if(e.target.id==='xp-store'){state.slug=e.target.value;try{await load()}catch(err){flash(err.message,true)}}});
root.addEventListener('click',async e=>{
 const nav=e.target.closest('[data-tab]');if(nav){state.tab=nav.dataset.tab;root.querySelectorAll('[data-tab]').forEach(x=>x.setAttribute('aria-selected',String(x===nav)));try{await load()}catch(err){flash(err.message,true)}return}
 const btn=e.target.closest('[data-action]');if(!btn)return;const action=btn.dataset.action,id=Number(btn.dataset.id||0);btn.disabled=true;
 try{
  if(action==='cancel-shift'){await api(`/admin/r10/shifts/${id}/cancel`,{method:'POST'});flash('Смена отменена')}
  if(action==='activate-pulse'){await api(`/admin/r10/pulse/${id}/activate?slug=${encodeURIComponent(state.slug)}`,{method:'POST'});flash('Опрос включён для привязанного терминала')}
  if(action==='disable-pulse'){await api(`/admin/r10/pulse/${id}/disable?slug=${encodeURIComponent(state.slug)}`,{method:'POST'});flash('Опрос отключён')}
  if(action==='scan'){const d=await api(`/admin/r10/incidents/scan?slug=${encodeURIComponent(state.slug)}`,{method:'POST'});flash(`Выявлено ${d.detected} сигналов · новых записей ${d.created}`)}
  if(action==='ack-incident'||action==='close-incident'){
    const note=prompt('Кратко опишите проверку и действие (не менее 10 символов)');if(note===null)return;
    const task=action==='ack-incident'&&confirm('Создать задачу в центре директора для этого инцидента?');
    await api(`/admin/r10/incidents/${id}`,{method:'PATCH',body:{status:action==='ack-incident'?'acknowledged':'resolved',note,make_task:task}});flash('Статус инцидента сохранён');
  }
  await load();
 }catch(err){flash(err.message,true)}finally{btn.disabled=false}
});
root.addEventListener('submit',async e=>{
 const form=e.target.closest('[data-form]');if(!form)return;e.preventDefault();const type=form.dataset.form;
 const data=Object.fromEntries(new FormData(form).entries());const btn=form.querySelector('button[type=submit],button:not([type])');if(btn)btn.disabled=true;
 try{
  if(type==='benchmark'){state.days=Number(data.days);state.source=data.source}
  if(type==='shift-day'){state.day=data.day}
  if(type==='sla'){await api('/admin/r10/service/targets',{method:'PUT',body:{slug:state.slug,accept_minutes:Number(data.accept_minutes),resolve_minutes:Number(data.resolve_minutes)}});flash('Норматив обслуживания сохранён')}
  if(type==='shift'){await api('/admin/r10/shifts',{method:'POST',body:{slug:state.slug,label:data.label,capacity_per_hour:Number(data.capacity_per_hour),start_at:new Date(data.start_at).toISOString(),end_at:new Date(data.end_at).toISOString(),request_id:uid()}});state.day=data.start_at.slice(0,10);flash('Смена создана')}
  if(type==='pulse'){await api('/admin/r10/pulse',{method:'POST',body:{slug:state.slug,title:data.title,question:data.question,options:data.options.split(/\r?\n/).map(x=>x.trim()).filter(Boolean)}});flash('Опрос создан; активируйте его после привязки планшета')}
  await load();
 }catch(err){flash(err.message,true)}finally{if(btn)btn.disabled=false}
});
start();
