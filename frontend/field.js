/* OSMANX R1.9 — field operations, source evidence and kiosk health. */
const root=document.getElementById('field-root'),toast=document.getElementById('voice-toast');
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const token=()=>sessionStorage.getItem('osmanx_admin_token')||'';
const state={slug:'central',tab:'fleet',fleet:[],quality:[],incidents:[],days:7,selected:0,loading:false};
const tabs=[['fleet','01 / Терминалы'],['schedule','02 / Расписание'],['offline','03 / Связь и очередь'],['quality','04 / Качество'],['incidents','05 / Инциденты']];
const labels={online:'На связи',offline:'Нет связи',delayed:'Задержка',unpaired:'Не привязан',disabled:'Отключён'};
const status={open:'Открыт',acknowledged:'Принят',resolved:'Закрыт'};
const num=x=>new Intl.NumberFormat('ru-RU').format(Number(x||0));
const money=x=>new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0}).format(Number(x||0));
const metric=(name,value,hint)=>`<div class="metric"><small>${esc(name)}</small><b>${esc(value)}</b><em>${esc(hint)}</em></div>`;
const card=(title,html)=>`<section class="card"><h2>${esc(title)}</h2>${html}</section>`;
const button=(text,attrs='',style='')=>`<button class="action ${style}" ${attrs}>${esc(text)}</button>`;
const dateText=x=>x?new Date(x).toLocaleString('ru-RU'):'Нет данных';
function alertMsg(s,bad=false){toast.textContent=s;toast.className=bad?'error':'';toast.style.display='block';clearTimeout(alertMsg.timer);alertMsg.timer=setTimeout(()=>toast.style.display='none',4700)}
async function request(path,{method='GET',body}={}){
  const headers={Accept:'application/json'};if(token())headers.Authorization=`Bearer ${token()}`;
  if(body!==undefined)headers['Content-Type']='application/json';
  const r=await fetch('/api/admin/r19'+path,{method,headers,cache:'no-store',body:body===undefined?undefined:JSON.stringify(body)});
  const data=await r.json().catch(()=>({detail:'Ответ сервера недоступен'}));
  if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:`HTTP ${r.status}`);
  return data;
}
async function load(){
  const slug=encodeURIComponent(state.slug);
  const [fleet,quality,incidents]=await Promise.all([
    request('/fleet?slug='+slug),request('/quality?slug='+slug+'&days='+state.days),request('/incidents?slug='+slug)]);
  state.fleet=fleet.items;state.quality=quality.items;state.incidents=incidents.items;
  if(!state.fleet.some(x=>x.id===state.selected))state.selected=state.fleet[0]?.id||0;
  render();
}
async function commit(action,message){if(state.loading)return;state.loading=true;try{await action();await load();alertMsg(message)}catch(e){alertMsg(e.message,true)}finally{state.loading=false}}
function selectField(){return `<label>Терминал<select name="placement_id" id="placement-picker" ${state.fleet.length?'':'disabled'}>${state.fleet.map(x=>`<option value="${x.id}" ${x.id===state.selected?'selected':''}>${esc(x.name)} · ${esc(x.medium)}</option>`).join('')}</select></label>`;}
function fleetCard(p){const h=p.health,day=p.schedule;return `<article class="terminal-card" data-placement="${p.id}"><div class="terminal-head"><div><div class="eyebrow">${esc(p.medium.toUpperCase())} / #${p.id}</div><h2>${esc(p.name)}</h2><span class="field-detail">${esc(p.public_id)}</span></div><span class="field-pill ${h.state}">${esc(labels[h.state]||h.state)}</span></div>
<div class="terminal-data"><div><small>Последний сигнал</small><strong>${h.seconds_since===null?'—':h.seconds_since+' c'}</strong></div><div><small>Очередь на устройстве</small><strong>${h.queue_depth===null?'—':num(h.queue_depth)}</strong></div><div><small>Версия терминала</small><strong>${esc(h.app_version||'—')}</strong></div></div>
<div class="field-status-label"><span class="tag">${day.configured?'Расписание задано':'Без расписания'}</span><span class="tag ${day.is_open?'live':''}">${day.is_open?'Анкета открыта':'Приём закрыт'}</span><span class="small">${esc(day.timezone)} · ${esc(day.start)}–${esc(day.end)}</span></div>
<div class="field-ops">${button('Настроить график',`data-do="schedule" data-id="${p.id}"`,'ghost')}${button('История качества',`data-do="quality" data-id="${p.id}"`,'ghost')}</div></article>`;}
function fleetTab(){const on=state.fleet.filter(x=>x.health.state==='online').length;const errors=state.fleet.filter(x=>['offline','delayed'].includes(x.health.state)).length;
return `<div class="metrics">${metric('Терминалов',state.fleet.length,'В выбранном филиале')}${metric('На связи',on,'Сигнал за последние 150 секунд')}${metric('Связь нарушена',errors,'Задержка или потеря сигнала')}${metric('Ожидающих ответов',state.fleet.reduce((n,x)=>n+(x.health.queue_depth||0),0),'По последнему сообщению планшета')}</div>
${state.fleet.length?`<div class="field-grid">${state.fleet.map(fleetCard).join('')}</div>`:card('Добавьте первый терминал','<p>Создайте анкету и терминал в Voice Studio. После привязки он появится здесь.</p><a class="action primary" href="/static/voice.html">Открыть Voice Studio</a>')}
<div class="field-callout"><strong>Что именно означает «На связи»?</strong><p>Сервер получил правильный ключ терминала и свежий сигнал. Это не подтверждает, что покупатель видел опрос, а физический планшет или экран установлен в магазине.</p></div>`;}
function scheduleTab(){const p=state.fleet.find(x=>x.id===state.selected);if(!p)return card('Расписание','<p>Сначала привяжите планшет в Voice Studio.</p>');const s=p.schedule;
return `<div class="grid">${card('Часы проведения опроса',`<form id="schedule-form" class="form">${selectField()}<input type="hidden" name="revision" value="${s.revision}"><label><span>Проводить опрос</span><select name="enabled"><option value="1" ${s.enabled?'selected':''}>Да, в выбранные часы</option><option value="0" ${!s.enabled?'selected':''}>Временно остановить</option></select></label><div class="field-inputs"><label>Начало<input type="time" name="start" value="${esc(s.start)}" required></label><label>Конец<input type="time" name="end" value="${s.end==='24:00'?'23:59':esc(s.end)}" required></label></div><div class="field-days">${['Пн','Вт','Ср','Чт','Пт','Сб','Вс'].map((day,i)=>`<label class="field-day"><span>${day}</span><input type="checkbox" name="day" value="${i}" ${s.weekdays.includes(i)?'checked':''}></label>`).join('')}</div><p class="small">Часовой пояс: ${esc(s.timezone)}. Изменение расписания блокирует новые анкеты вне окна. Уже открытые опросы могут завершиться в течение срока сессии.</p>${button('Сохранить расписание','type="submit"','primary')}</form>`)}
${card('Контроль расписания',`<div class="field-readiness"><div><span>Доступность сейчас</span><b>${s.is_open?'Открыто':'Закрыто'}</b></div><div><span>Локальное время</span><b>${esc(s.local_time)}</b></div><div><span>Ревизия</span><b>${num(s.revision)}</b></div><div><span>Статус планшета</span><b>${esc(labels[p.health.state]||p.health.state)}</b></div></div><div class="field-warning">Не устанавливайте на общей стойке планшет с открытым кабинетом директора. Для покупателей используйте только QR-ссылку терминала.</div>`)}</div>`;}
function offlineTab(){const pending=state.fleet.filter(x=>(x.health.queue_depth||0)>0);
return `<div class="metrics">${metric('Устройств с очередью',pending.length,'Только последнее сообщение устройства')}${metric('Ожидают передачи',pending.reduce((a,b)=>a+b.health.queue_depth,0),'Не считать полученными ответами')}${metric('Нет сигнала',state.fleet.filter(x=>x.health.state==='offline').length,'Отсутствие heartbeat более 10 минут')}${metric('Смена ключа', 'Voice Studio','Старые ключи немедленно перестают работать')}</div>
<div class="grid">${card('Очередь без интернета',pending.length?`<div class="list">${pending.map(p=>`<div class="list-item"><strong>${esc(p.name)}</strong><div class="field-status-label"><span class="field-pill delayed">${p.health.queue_depth} не отправлены</span><span class="small">${esc(labels[p.health.state]||p.health.state)}</span></div></div>`).join('')}</div>`:'<div class="notice good">Нет сигналов о накопившихся ответах. Если планшет полностью отключён, его текущую очередь сервер увидеть не может.</div>')}
${card('Как работает восстановление',`<div class="field-callout"><strong>Ответ сохранён ≠ ответ получен сервером</strong><p>На планшете хранится только анкета и анонимные ответы. При восстановлении связи терминал повторяет открытие и отправку с тем же идентификатором. Сервер защищает от повторного подсчёта.</p></div><p class="field-steps">1. Проверьте интернет планшета и его ключ привязки.<br>2. Откройте защищённый опрос на том же устройстве.<br>3. Дождитесь передачи; просроченные или несовместимые ответы не должны засчитываться автоматически.<br>4. Для диагностики посмотрите Fleet и «Инциденты».</p><div class="field-warning">Если покупатель заполнил анкету офлайн, а терминал так и не подключился, сервер не знает об ответе. Не сообщайте владельцу, что данные уже получены.</div>`)}</div>`;}
function qualityTab(){return `<div class="row space field-panel"><div><div class="eyebrow">SOURCE QUALITY · ANONYMOUS</div><h2>Контроль качества опросов</h2></div><div class="row"><label>Период<select id="days"><option value="1" ${state.days===1?'selected':''}>1 день</option><option value="7" ${state.days===7?'selected':''}>7 дней</option><option value="14" ${state.days===14?'selected':''}>14 дней</option><option value="30" ${state.days===30?'selected':''}>30 дней</option></select></label>${button('Экспорт CSV','data-do="quality-csv"','ghost')}</div></div>
${state.quality.length?`<div class="field-grid">${state.quality.map(q=>card(q.name,`<div class="terminal-data"><div><small>Открытия</small><strong>${num(q.opens)}</strong></div><div><small>Завершения</small><strong>${num(q.responses)}</strong></div><div><small>Доля завершений</small><strong>${q.completion_pct===null?'—':q.completion_pct+'%'}</strong></div></div><div class="field-status-label"><span class="tag">Пик в минуту: ${num(q.peak_per_minute)}</span><span class="tag">Ответы менее 4 с: ${num(q.fast_responses)}</span></div>${q.warnings.map(w=>`<div class="field-warning">${esc(w)}</div>`).join('')||'<div class="notice good">Новых технических сигналов не найдено.</div>'}`)).join('')}</div>`:card('Нет данных','<p>Ответы появятся после запуска терминалов.</p>')}
<div class="field-warning">Опрос добровольный; он может быть нерепрезентативным. Даже высокий процент ответов не доказывает, что все посетители получили анкету или что выявлена причина снижения выручки.</div>`;}
function incidentTab(){return `<div class="row space field-panel"><div><div class="eyebrow">OPS CONTROL · EXCEPTIONS</div><h2>Проблемы и решения</h2></div>${button('Проверить сигналы','data-do="sync"','primary')}</div>
${state.incidents.length?`<div class="field-grid">${state.incidents.map(i=>card(i.title,`<div class="field-status-label"><span class="field-pill ${i.status==='open'?'offline':i.status==='acknowledged'?'delayed':'online'}">${esc(status[i.status]||i.status)}</span><span class="small">Терминал #${i.placement_id} · ${esc(i.signal)}</span></div><p>${esc(i.note||'Требуется проверка менеджером.')}</p><span class="field-timestamp">Обновлено: ${esc(dateText(i.updated_at))}</span>${i.status!=='resolved'?`<form class="form" data-incident="${i.id}" data-next="${i.status==='open'?'acknowledged':'resolved'}"><label>Что проверили и какое действие предприняли?<textarea name="note" required minlength="12" maxlength="500" placeholder="Факты, результат проверки, ответственное действие"></textarea></label>${button(i.status==='open'?'Принять в работу':'Отметить решённым','type="submit"','primary')}</form>`:''}${button('История',`data-do="history" data-id="${i.id}"`,'ghost')}<div class="small" id="history-${i.id}"></div>`)).join('')}</div>`:card('Проблемы не зарегистрированы','<p>Проверка анализирует потерю связи, очередь ответов, аномальные всплески и низкую долю завершения. Она не создаёт ложных результатов без сигналов.</p>')}`;}
function render(){const online=state.fleet.filter(x=>x.health.state==='online').length,inc=state.incidents.filter(x=>x.status!=='resolved').length;
root.innerHTML=`<div class="page"><header class="head"><div><div class="brand">OSMAN<span>X</span></div><div class="eyebrow">RETAIL INTELLIGENCE · FIELD OPERATIONS</div></div><div class="head-links"><a class="back" href="/static/voice.html">Voice Studio</a><a class="back" href="/">Кабинет</a></div></header>
<section class="hero field-hero"><div><div class="eyebrow">OPERATE · PROTECT · VERIFY</div><h1>Каждый терминал.<br><span>Под контролем.</span></h1><p>Работа опросных планшетов, честный учёт очереди при потере связи, расписания, качество данных и управляемые инциденты. Без распознавания лиц.</p></div><div class="hero-badge"><small>OSMANX / FIELD ENGINE</small><strong>R1.9</strong><small>${online} на связи · ${inc} открытых проблем</small></div></section>
<div class="toolbar"><label>Филиал<input id="store-slug" value="${esc(state.slug)}" placeholder="central" aria-label="Филиал"></label><div class="row"><span class="tag live">${online} на связи</span><span class="tag">${inc} проблем</span>${button('Обновить','data-do="refresh"','ghost')}</div></div>
<nav class="tabs" role="tablist">${tabs.map(([id,title])=>`<button role="tab" class="tab ${state.tab===id?'active':''}" aria-selected="${state.tab===id}" data-tab="${id}">${title}</button>`).join('')}</nav>
<main id="field-content">${state.tab==='fleet'?fleetTab():state.tab==='schedule'?scheduleTab():state.tab==='offline'?offlineTab():state.tab==='quality'?qualityTab():incidentTab()}</main>
<footer class="footer">OSMANX WORLD · Состояние устройства измерено по последнему сигналу, а не по независимой проверке оборудования. Ответы добровольны; качество выборки требует оценки.</footer></div>`;
}
root.addEventListener('click',async e=>{const el=e.target.closest('[data-do],[data-tab]');if(!el)return;
 if(el.dataset.tab){state.tab=el.dataset.tab;render();return;}
 const act=el.dataset.do,id=Number(el.dataset.id);
 if(act==='refresh')load().catch(x=>alertMsg(x.message,true));
 if(act==='schedule'){state.selected=id;state.tab='schedule';render();}
 if(act==='quality'){state.tab='quality';render();}
 if(act==='sync')commit(()=>request('/incidents/sync?slug='+encodeURIComponent(state.slug),{method:'POST'}),'Сигналы синхронизированы');
 if(act==='quality-csv')download('/quality.csv?slug='+encodeURIComponent(state.slug)+'&days='+state.days,'osmanx-field-quality.csv').catch(x=>alertMsg(x.message,true));
 if(act==='history'){try{const result=await request('/incidents/'+id+'/history');const place=root.querySelector('#history-'+id);if(place)place.textContent=result.items.map(x=>`${dateText(x.changed_at)}: ${x.previous_status} → ${x.current_status}, ${x.note}`).join(' | ')||'Нет переходов';}catch(x){alertMsg(x.message,true)}}
});
root.addEventListener('change',e=>{
 if(e.target.id==='store-slug'){state.slug=e.target.value.trim()||'central';load().catch(x=>alertMsg(x.message,true));}
 if(e.target.id==='placement-picker'){state.selected=Number(e.target.value);render();}
 if(e.target.id==='days'){state.days=Number(e.target.value);load().catch(x=>alertMsg(x.message,true));}
});
root.addEventListener('submit',e=>{e.preventDefault();const form=e.target,data=Object.fromEntries(new FormData(form));
 if(form.id==='schedule-form')commit(async()=>{
   const days=[...form.querySelectorAll('input[name="day"]:checked')].map(x=>Number(x.value));
   const requestBody={expected_revision:Number(data.revision),enabled:data.enabled==='1',weekdays:days,start:data.start,end:data.end};
   await request('/placements/'+Number(data.placement_id)+'/schedule',{method:'PUT',body:requestBody});
 },'Расписание обновлено с защитой версии');
 if(form.dataset.incident)commit(()=>request('/incidents/'+Number(form.dataset.incident),{method:'PATCH',body:{status:form.dataset.next,note:data.note}}),'История инцидента обновлена');
});
async function download(path,name){const headers={Accept:'text/csv'};if(token())headers.Authorization=`Bearer ${token()}`;
 const response=await fetch('/api/admin/r19'+path,{headers,cache:'no-store'});if(!response.ok)throw Error('Ошибка экспорта '+response.status);
 const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1800);
}
load().catch(x=>{root.innerHTML=`<div class="page"><header class="head"><div class="brand">OSMAN<span>X</span></div><a class="back" href="/">Кабинет</a></header><section class="hero"><div><div class="eyebrow">FIELD OPERATIONS · SECURED</div><h1>Требуется вход</h1><p>${esc(x.message)} Войдите через главный кабинет и откройте этот раздел снова.</p></div></section></div>`;});
