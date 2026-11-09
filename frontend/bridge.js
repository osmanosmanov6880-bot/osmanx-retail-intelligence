/* OSMANX R1.8 Decision Bridge: live evidence, hypotheses, pilots, tasks, executive proof. */
(()=>{'use strict';
const root=document.querySelector('#bridge-root'),toast=document.querySelector('#bridge-toast');
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const token=()=>sessionStorage.getItem('osmanx_admin_token')||'';
const id=()=>`r18-${crypto.randomUUID?.()||Date.now().toString(36)+Math.random().toString(36).slice(2)}`;
const number=v=>new Intl.NumberFormat('ru-RU').format(Number(v||0));
const state={slug:'central',tab:'signals',signals:null,board:null,selected:0,picked:0,busy:false,taskPending:null};
const tabs=[['signals','01 / Сигналы'],['hypotheses','02 / Гипотезы'],['pilot','03 / Пилоты'],['tasks','04 / Исполнение'],['board','05 / Контроль']];
const tags={candidate:'Гипотеза',investigating:'Изучается',pilot_linked:'Пилот связан',resolved:'Решено',dismissed:'Отклонено'};
const category={stock:'Наличие',assortment:'Ассортимент',service:'Обслуживание',price:'Цены',experience:'Опыт'};
const btn=(label,attrs='',css='')=>`<button class="button ${css}" ${attrs}>${esc(label)}</button>`;
const card=(title,content)=>`<section class="card"><h2>${esc(title)}</h2>${content}</section>`;
const field=(label,name,value='',type='text',extra='')=>`<label>${esc(label)}<input name="${name}" type="${type}" value="${esc(value)}" ${extra} required></label>`;
const metric=(label,value,hint)=>`<div class="metric"><small>${esc(label)}</small><strong>${esc(value)}</strong><em>${esc(hint)}</em></div>`;
const empty=(text)=>`<div class="empty">${esc(text)}</div>`;
const options=(rows,selected)=>rows.map(([id,v])=>`<option value="${esc(id)}" ${id===selected?'selected':''}>${esc(v)}</option>`).join('');
function notify(message,error=false){toast.textContent=message;toast.className=error?'error':'';toast.style.display='block';clearTimeout(notify.timer);notify.timer=setTimeout(()=>toast.style.display='none',4700)}
async function api(path,{method='GET',body,raw=false}={}){
  const headers={Accept:raw?'text/csv':'application/json'};
  if(token())headers.Authorization='Bearer '+token();
  if(body!==undefined)headers['Content-Type']='application/json';
  const res=await fetch('/api/admin/r18'+path,{method,headers,cache:'no-store',body:body===undefined?undefined:JSON.stringify(body)});
  if(raw){if(!res.ok)throw Error('Ошибка CSV '+res.status);return res.blob()}
  const obj=await res.json().catch(()=>({detail:'Ошибка ответа сервера'}));
  if(!res.ok)throw Error(typeof obj.detail==='string'?obj.detail:`HTTP ${res.status}`);
  return obj;
}
const item=()=>state.board?.items.find(x=>x.id===state.selected)||null;
const titleStatus=x=>`<span class="tag ${x.status==='resolved'?'good':x.status==='dismissed'?'red':'warn'}">${esc(tags[x.status]||x.status)}</span>`;
const warnings=x=>`<div class="notice">${x.map(esc).join(' ')}</div>`;
async function load(){const slug=encodeURIComponent(state.slug);const [signals,board]=await Promise.all([api('/signals?slug='+slug+'&days=14'),api('/board?slug='+slug)]);state.signals=signals;state.board=board;if(!state.selected&&board.items.length)state.selected=board.items[0].id;render()}
async function mutate(work,success){if(state.busy)return;state.busy=true;try{await work();await load();notify(success||'Сохранено в журнале')}catch(e){notify(e.message,true)}finally{state.busy=false}}
async function download(){try{const blob=await api('/board.csv?slug='+encodeURIComponent(state.slug),{raw:true}),url=URL.createObjectURL(blob);let a=document.createElement('a');a.href=url;a.download='osmanx-decision-bridge.csv';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500);notify('CSV скачан')}catch(e){notify(e.message,true)}}
function shell(){const b=state.board,s=state.signals;
 root.innerHTML=`<div class="page"><header class="top"><div><div class="brand">OSMAN<span>X</span></div><div class="eyebrow">RETAIL INTELLIGENCE / DECISION BRIDGE</div></div><div class="links"><a href="/static/voice.html">Voice Studio</a><a href="/static/pilot.html">Pilot Studio</a><a href="/">Главный кабинет</a></div></header>
 <section class="hero"><div><div class="eyebrow">LISTEN · VERIFY · ACT</div><h1>От ответа клиента<br><span>к решению бизнеса.</span></h1><p>Каждая гипотеза имеет источник, проверяемый снимок данных и ответственного. Пилот создаётся только после рассмотрения гипотезы — не вместо доказательства.</p></div><aside class="hero-badge"><small class="eyebrow">OSMANX / DECISION ENGINE</small><strong>R1.8</strong><small class="muted">Без вымышленных продаж</small></aside></section>
 <div class="toolbar"><label>Филиал <input id="bridge-slug" value="${esc(state.slug)}" placeholder="central" aria-label="Филиал"></label>${btn('Обновить данные','id="bridge-refresh"','ghost')}</div>
 <div class="metrics">${metric('Ответов в Voice / 14 дней',number(s?.anonymous_responses),'Добровольные анонимные ответы')}${metric('Зафиксированные гипотезы',number(b?.hypotheses),'Снимки источника с SHA-256')}${metric('Открытые задачи',number(b?.pending_tasks),'По проверяемым гипотезам')}${metric('Проблемы достоверности',number(b?.proof_alerts),'Нарушение снимков или связей')}</div>
 <nav class="tabs" role="tablist">${tabs.map(([name,label])=>`<button class="tab" role="tab" data-tab="${name}" aria-selected="${state.tab===name}">${label}</button>`).join('')}</nav>
 <main id="bridge-content">${state.tab==='signals'?signalsTab():state.tab==='hypotheses'?hypothesesTab():state.tab==='pilot'?pilotTab():state.tab==='tasks'?tasksTab():boardTab()}</main>
 <footer class="footer">OSMANX WORLD · Ответ в опросе — сигнал, не заключённая продажа. Исторические версии анкет не смешиваются. Данные пилота не доказывают причинный эффект автоматически. Публичные платежи и кассовые операции отсутствуют.</footer></div>`;
}
function signalsTab(){const signals=state.signals?.items||[];const picked=signals[state.picked]||signals[0];
return `<div class="grid">${card('Повторяющиеся ответы',`<p class="section-intro">Выбирайте подтверждённый сигнал от конкретной опубликованной версии анкеты. Для создания гипотезы необходимо минимум три ответа.</p>${signals.length?`<div class="list">${signals.map((s,i)=>`<div class="record"><div class="row wrap"><strong>${esc(s.label)}</strong><span class="tag ${s.quality==='limited'?'warn':'good'}">${number(s.support)} из ${number(s.eligible_answers)}</span></div><div class="meta">${esc(s.question)} · ${esc(s.share_pct)}% · Версия №${s.version_id}</div>${btn('Выбрать сигнал',`data-pick="${i}"`,'small '+(state.picked===i?'primary':'ghost'))}</div>`).join('')}</div>`:empty('Опросов пока недостаточно. Сначала опубликуйте анкету в Voice Studio и соберите минимум три одинаковых ответа.')}`)}
 ${card('Зафиксировать управленческую гипотезу',picked?`<form class="form" id="hypothesis-create"><div class="notice safe">Источник: ${esc(picked.label)} · ${number(picked.support)} ответов. Будет записан неизменяемый агрегированный снимок.</div>
 ${field('Гипотеза для проверки','title',`Проверить запрос покупателей: ${picked.label}`,'text','minlength="12" maxlength="180"')}
 <label>Направление<select name="category">${options(Object.entries(category),'stock')}</select></label>
 ${btn('Создать гипотезу','type="submit"','primary')}</form>`:empty('Выберите сигнал в левом списке.'))}
 ${warnings(state.signals?.warnings||[])}</div>`}
function hypothesesTab(){const rows=state.board?.items||[];const chosen=item();return `<div class="grid">
 ${card('Реестр решений',rows.length?`<div class="list">${rows.map(x=>`<div class="record"><div class="row wrap"><strong>${esc(x.title)}</strong>${titleStatus(x)}</div><div class="meta">№${x.id} · ${esc(category[x.category]||x.category)} · ${number(x.evidence.support)} ответов из ${number(x.evidence.eligible_answers)} · SHA ${x.evidence_valid?'✓':'НЕ СОВПАДАЕТ'}</div>${btn('Открыть',`data-select="${x.id}"`,'small '+(x.id===state.selected?'primary':'ghost'))}</div>`).join('')}</div>`:empty('Пока нет гипотез. Создайте первую во вкладке «Сигналы».'))}
 ${card('Карточка гипотезы',chosen?`<div class="row wrap"><strong>${esc(chosen.title)}</strong>${titleStatus(chosen)}</div><div class="notice ${chosen.evidence_valid?'safe':''}">Агрегат: ${number(chosen.evidence.support)} из ${number(chosen.evidence.eligible_answers)} · ${esc(chosen.evidence.share_pct)}%. Снимок ${chosen.evidence_valid?'не изменялся':'НАРУШЕН'}.</div>
 <div class="meta muted">${esc(chosen.evidence.warnings.join(' '))}</div>
 ${(chosen.status==='candidate'||chosen.status==='investigating'||chosen.status==='pilot_linked')?`<form id="hypothesis-state" class="form"><label>Статус<select name="status">${options(chosen.status==='candidate'?[['investigating','Начать изучение'],['dismissed','Отклонить']]:[['resolved','Решено'],['dismissed','Отклонить']],'investigating')}</select></label><label>Обоснование<textarea name="note" minlength="12" required placeholder="На основании каких действий принимается решение?"></textarea></label>${btn('Сохранить и записать в журнал','type="submit"','primary')}</form>`:'<p>Гипотеза закрыта. Её история сохраняется.</p>'}
 <a class="button ghost" href="/static/voice.html" style="display:inline-block;margin-top:15px">К источнику Voice</a>`:empty('Выберите гипотезу в левом реестре.'))}</div>`}
function pilotTab(){const x=item();let p=x?.pilot;const now=new Date();function day(offset){let d=new Date(now);d.setDate(d.getDate()+offset);return d.toISOString().slice(0,10)}
return `<div class="grid">${card('Привязка проверяемого пилота',x?`<div class="row wrap"><strong>${esc(x.title)}</strong>${titleStatus(x)}</div><div class="notice ${x.pilot?.sha_ok===false?'':'safe'}">Pilot Studio: ${esc(p?.status||'не связан')}${p?.sha_ok===false?' — повреждённый итоговый снимок':''}</div><p>Пилот не создаёт покупку или скидку. Выберите равные периоды от 7 до 30 дней и заранее объявите KPI.</p>
 ${x.pilot_id?`<div class="row"><strong>Пилот №${x.pilot_id}</strong><a class="button ghost small" href="/static/pilot.html">Открыть Pilot Studio</a></div>`:x.status!=='investigating'?empty('Сначала переведите гипотезу в статус «Изучается» во вкладке «Гипотезы».'):
 `<form id="pilot-create" class="form"><div class="field-pair"><label>Показатель<select name="metric">${options([['receipts_per_100_entries','Чеков на 100 входов'],['feedback_per_100_entries','Опросов на 100 входов'],['demand_per_100_entries','Запросов на 100 входов'],['revenue_per_entry_rub','Выручка на один вход']],'receipts_per_100_entries')}</select></label><label>Источник посещений<select name="source_mode">${options([['sensor','Датчик'],['manual','Ручной'],['all','Все источники (с предупреждением)']],'sensor')}</select></label></div>
 <div class="field-pair">${field('Начало базового периода','before_start',day(-14),'date')}${field('Конец базового периода','before_end',day(-8),'date')}${field('Начало проверки','after_start',day(-7),'date')}${field('Конец проверки','after_end',day(-1),'date')}</div>
 ${field('Лимит затрат, ₽','budget_rub','0','number','min="0" max="10000000"')}${btn('Создать черновик пилота','type="submit"','primary')}</form>`}`:empty('Выберите гипотезу во вкладке «Гипотезы».'))}
 ${card('Правила проверки',`<div class="notice">До и после — одинаковая длительность. Закрыть пилот можно только с документированным действием и после завершения периода. Сравнение не доказывает причинный эффект.</div><p>После создания черновика отдельно запустите его в Pilot Studio. Источник гипотезы и контрольная сумма остаются в Decision Bridge.</p>`)}</div>`}
function tasksTab(){const x=item();const tasks=state.tasks||[];return `<div class="grid">${card('Задачи по гипотезе',x?`<h3>${esc(x.title)}</h3><p>Ответственные, сроки и последовательная история изменений.</p>${tasks.length?`<div class="list">${tasks.map(t=>`<div class="record"><div class="row wrap"><strong>${esc(t.title)}</strong><span class="tag">${esc(t.status)}</span></div><div class="meta">Ответственный: ${esc(t.owner)} · Срок: ${esc(t.due_date)}</div>${t.status==='open'?btn('В работу',`data-task="${t.id}" data-status="working"`,'small'):t.status==='working'?btn('Завершить',`data-task="${t.id}" data-status="done"`,'small primary'):''}${state.taskPending?.id===t.id?`<form id="task-state" class="form" style="margin-top:12px"><label>Подтверждение действия<textarea name="note" minlength="12" required placeholder="Что сделали и где зафиксировали результат?"></textarea></label>${btn('Сохранить событие', 'type="submit"','primary')}</form>`:''}</div>`).join('')}</div>`:empty('Пока нет задач для этой гипотезы.')}`:empty('Выберите гипотезу на вкладке «Гипотезы».'))}
 ${card('Назначить ответственное действие',x&&x.status!=='resolved'&&x.status!=='dismissed'?`<form id="task-create" class="form">${field('Действие','title','Проверить запрос покупателей и наличие товара','text','minlength="12"')}${field('Ответственный','owner','Управляющий магазином','text','minlength="3"')}${field('Срок','due_date',new Date(Date.now()+604800000).toISOString().slice(0,10),'date')}${btn('Создать задачу','type="submit"','primary')}</form>`:empty('Назначение доступно для открытой гипотезы.'))}
 <p>Подтверждение выполнения не означает автоматически полученную прибыль или закрытую продажу.</p></div>`}
function boardTab(){let b=state.board||{};return `<div class="grid">${card('Карта управленческих решений',`<div class="list">${Object.entries(b.statuses||{}).map(([k,v])=>`<div class="row"><strong>${esc(tags[k]||k)}</strong><span class="kpi"><b>${number(v)}</b><small>гипотез</small></span></div>`).join('')}</div><div class="separator"></div><div class="row"><strong>Задачи в работе</strong><b>${number(b.pending_tasks)}</b></div><div class="row"><strong>Нарушения источников</strong><b>${number(b.proof_alerts)}</b></div><div class="buttons">${btn('Скачать CSV','id="bridge-export"','primary')}</div>`)}
 ${card('Принципы достоверности',`<div class="notice">${esc((b.warnings||[]).join(' '))}</div><p>Каждое решение содержит первичную выборку, дату фиксации, контрольную сумму, журнал действий и статус пилота.</p><p>Система проверяет целостность сохранённых записей, но не удостоверяет достоверность данных физического оборудования.</p><div class="links"><a href="/static/voice.html">Анкеты и терминалы</a><a href="/static/pilot.html">Пилоты и результаты</a></div>`)}</div>`}
function render(){shell()}
async function refreshTasks(){if(state.tab!=='tasks'||!state.selected){state.tasks=[];return}let r=await api('/hypotheses/'+state.selected);state.tasks=r.tasks||[];render()}
root.addEventListener('click',async ev=>{const el=ev.target.closest('button');if(!el)return;
if(el.dataset.tab){state.tab=el.dataset.tab;render();if(state.tab==='tasks')try{await refreshTasks()}catch(e){notify(e.message,true)}return}
if(el.dataset.pick!==undefined){state.picked=Number(el.dataset.pick);render();return}
if(el.dataset.select){state.selected=Number(el.dataset.select);render();if(state.tab==='tasks')try{await refreshTasks()}catch(e){notify(e.message,true)}return}
if(el.id==='bridge-refresh'){const slug=document.querySelector('#bridge-slug').value.trim();if(!slug)return;state.slug=slug;state.selected=0;try{await load();notify('Показатели обновлены')}catch(e){notify(e.message,true)}return}
if(el.id==='bridge-export'){await download();return}
if(el.dataset.task){state.taskPending={id:Number(el.dataset.task),status:el.dataset.status};render();return}
});
root.addEventListener('submit',async ev=>{ev.preventDefault();const form=ev.target;if(!(form instanceof HTMLFormElement))return;const data=Object.fromEntries(new FormData(form));
if(form.id==='hypothesis-create'){const s=state.signals?.items?.[state.picked];if(!s)return;
 await mutate(async()=>{const r=await api('/hypotheses',{method:'POST',body:{slug:state.slug,request_id:id(),placement_id:s.placement_id,version_id:s.version_id,question_id:s.question_id,choice:s.choice,days:14,title:data.title,category:data.category}});state.selected=r.id;state.tab='hypotheses'},'Гипотеза сохранена с источником');return}
if(form.id==='hypothesis-state'){const hid=state.selected;await mutate(()=>api('/hypotheses/'+hid+'/status',{method:'PATCH',body:{status:data.status,note:data.note}}),'Статус и история сохранены');return}
if(form.id==='pilot-create'){const hid=state.selected;let budget=Math.round(Number(data.budget_rub)*100);if(!Number.isSafeInteger(budget)){notify('Неверный бюджет',true);return}
 await mutate(()=>api('/hypotheses/'+hid+'/pilot',{method:'POST',body:{request_id:id(),metric:data.metric,source_mode:data.source_mode,before_start:data.before_start,before_end:data.before_end,after_start:data.after_start,after_end:data.after_end,budget_kopeks:budget}}),'Черновик пилота создан');return}
if(form.id==='task-state'){const pending=state.taskPending;if(!pending)return;await mutate(()=>api('/tasks/'+pending.id,{method:'PATCH',body:{status:pending.status,note:data.note}}),'Статус задачи записан');state.taskPending=null;await refreshTasks();return}
if(form.id==='task-create'){await mutate(()=>api('/hypotheses/'+state.selected+'/tasks',{method:'POST',body:{request_id:id(),title:data.title,owner:data.owner,due_date:data.due_date}}),'Задача назначена');await refreshTasks()}
});
load().catch(err=>{root.innerHTML=`<div class="page"><header class="top"><div class="brand">OSMAN<span>X</span></div><a href="/">Основной кабинет</a></header><div class="card" style="margin:40px auto;max-width:620px"><h2>Требуется доступ</h2><p>${esc(err.message)}. Войдите через главный кабинет и затем откройте Decision Bridge.</p></div></div>`;});
})();
