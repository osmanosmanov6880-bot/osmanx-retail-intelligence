/* OSMANX R1.5 Pilot Studio. Every button uses authenticated, persisted FastAPI data. */
const root=document.querySelector('#pilot-root');
const toast=document.querySelector('#pilot-toast');
const state={slug:'central',stores:[],pilots:[],selected:null,tab:'overview',detail:null,preview:null,busy:false};
const tabs=[['overview','01. План'],['sources','02. Источники'],['daily','03. Показатели'],['actions','04. Действия'],['report','05. Отчёт']];
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt=n=>new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(Number(n)||0);
const rub=n=>new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:0}).format((Number(n)||0)/100);
const token=()=>sessionStorage.getItem('osmanx_admin_token')||'';
const newid=()=>`r15-${typeof crypto!=='undefined'&&crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
const dateISO=(delta)=>{const d=new Date();d.setHours(12,0,0,0);d.setDate(d.getDate()+delta);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`};
const tag=(text,color='')=>`<span class="tag ${color}">${esc(text)}</span>`;
function notice(txt,error=false){toast.textContent=txt;toast.className=error?'error':'';toast.style.display='block';clearTimeout(notice.timer);notice.timer=setTimeout(()=>toast.style.display='none',5000)}
async function api(path,{method='GET',body}={}){
 const headers={'Accept':'application/json'};if(token())headers.Authorization=`Bearer ${token()}`;
 if(body!==undefined)headers['Content-Type']='application/json';
 let res;try{res=await fetch(`/api/admin/r15${path}`,{method,headers,cache:'no-store',body:body===undefined?undefined:JSON.stringify(body)})}
 catch{throw Error('Сервер недоступен: проверьте локальный запуск')}const data=await res.json().catch(()=>({detail:`Ошибка HTTP ${res.status}`}));
 if(!res.ok)throw Error(typeof data.detail==='string'?data.detail:`HTTP ${res.status}`);return data;
}
async function apiRoot(path){const headers={'Accept':'application/json'};if(token())headers.Authorization=`Bearer ${token()}`;
 const res=await fetch(`/api/admin/${path}`,{headers,cache:'no-store'});if(!res.ok)throw Error('Для доступа нужен действующий вход в кабинет владельца');return res.json();}
function button(text,attrib='',kind=''){return `<button class="action ${kind}" ${attrib}>${esc(text)}</button>`}
function card(title,body){return `<section class="card"><h2>${esc(title)}</h2>${body}</section>`}
function field(text,name,value='',type='text',more=''){return `<label>${esc(text)}<input name="${name}" type="${type}" value="${esc(value)}" ${more}></label>`}
function row(text,value,desc=''){return `<div class="line"><div><strong>${esc(text)}</strong>${desc?`<small>${esc(desc)}</small>`:''}</div><div class="value">${esc(value)}</div></div>`}
function metric(text,value,details=''){return `<div class="metric"><small>${esc(text)}</small><b>${esc(value)}</b><em>${esc(details)}</em></div>`}
function errorBox(message){return `<div class="alert">${esc(message)}</div>`}
function renderShell(){root.innerHTML=`<div class="page"><header class="head"><div><div class="logo">OSMAN<span>X</span></div><div class="super">RETAIL INTELLIGENCE · PILOT STUDIO</div></div><a class="return" href="/">← Кабинет руководителя</a></header>
 <section class="hero"><div><strong class="eyebrow">THE 14-DAY BUSINESS PROOF</strong><h1>Решение должно<br><span>доказывать ценность.</span></h1><p>Прозрачный пилот: фиксируем гипотезу, источники данных, результаты по дням и реальные действия. Никаких «потерянных миллионов» без доказательств.</p></div><label class="branch">Филиал<select id="branch">${state.stores.map(x=>`<option value="${esc(x.slug)}" ${state.slug===x.slug?'selected':''}>${esc(x.name)}</option>`).join('')}</select></label></section>
 <div class="toprow"><select id="pilot-choice" aria-label="Выбранный пилот" class="pilot-select">${state.pilots.length?state.pilots.map(x=>`<option value="${x.id}" ${x.id===state.selected?'selected':''}>№${x.id} · ${esc(x.title)}</option>`).join(''):'<option value="">Пилоты ещё не созданы</option>'}</select>
 ${state.detail?tag(state.detail.pilot.status==='running'?'Работает':state.detail.pilot.status==='completed'?'Завершён':state.detail.pilot.status==='cancelled'?'Отменён':'Черновик',state.detail.pilot.status==='running'?'good':''):''}
 <a class="action ghost" href="/static/evidence.html">Архив доказательств ↗</a></div>
 <nav class="tabs" role="tablist">${tabs.map(([id,name])=>`<button role="tab" class="tab ${state.tab===id?'active':''}" aria-selected="${state.tab===id}" data-tab="${id}">${name}</button>`).join('')}</nav>
 <div id="pilot-content"></div><footer class="footer">OSMANX WORLD · Показатели отражают зарегистрированные события. Количество чеков не равно количеству уникальных покупателей. «До/после» не доказывает причинность и не является расчётом прибыли.</footer></div>`;
 root.querySelector('#branch').onchange=async e=>{state.slug=e.target.value;state.selected=null;await load()};
 root.querySelector('#pilot-choice').onchange=async e=>{state.selected=Number(e.target.value)||null;await loadSelected()};
 root.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{state.tab=b.dataset.tab;render()});
}
async function load(){try{const d=await api(`/pilots?slug=${encodeURIComponent(state.slug)}`);state.pilots=d.items;
 if(!state.pilots.some(x=>x.id===state.selected))state.selected=state.pilots[0]?.id||null;
 await loadSelected()}catch(e){notice(e.message,true);renderShell();root.querySelector('#pilot-content').innerHTML=errorBox(e.message)}}
async function loadSelected(){state.detail=null;state.preview=null;
 try{if(state.selected){const [d,p]=await Promise.all([api(`/pilots/${state.selected}`),api(`/pilots/${state.selected}/preview`)]);state.detail=d;state.preview=p;}render()}
 catch(e){notice(e.message,true);render();root.querySelector('#pilot-content').innerHTML=errorBox(e.message)}}
function render(){renderShell();const target=root.querySelector('#pilot-content');
 if(state.tab==='overview')renderOverview(target);
 if(state.tab==='sources')renderSources(target);
 if(state.tab==='daily')renderDaily(target);
 if(state.tab==='actions')renderActions(target);
 if(state.tab==='report')renderReport(target);
}
async function mutate(fn){if(state.busy)return;state.busy=true;try{await fn();await load();notice('Запись сохранена в базе')}catch(e){notice(e.message,true)}finally{state.busy=false}}
function renderOverview(target){const p=state.detail?.pilot;const v=state.preview;const create=`<div class="section-meta">НОВЫЙ ПИЛОТ</div><form id="new-pilot" class="form">
 ${field('Название проверки','title','Проверка наличия размеров','text','required minlength="5"')}
 <label>Проверяемая гипотеза<textarea name="hypothesis" required minlength="15">Если записывать отсутствующие размеры, количество чеков на 100 входов может измениться. Проверяем по фактическим данным.</textarea></label>
 <div class="input-grid"><label>Метрика<select name="metric"><option value="receipts_per_100_entries">Чеков на 100 входов</option><option value="revenue_per_entry_rub">Выручка на один вход</option><option value="feedback_per_100_entries">Ответов на 100 входов</option><option value="demand_per_100_entries">Запросов на 100 входов</option></select></label>
 <label>Источник трафика<select name="source_mode"><option value="sensor">Счётчик</option><option value="manual">Ручные записи</option><option value="all">Все источники (проверить дубли!)</option></select></label></div>
 <div class="input-grid">${field('База: от','before_start',dateISO(-28),'date','required')}${field('База: до','before_end',dateISO(-15),'date','required')}${field('Проверка: от','after_start',dateISO(-14),'date','required')}${field('Проверка: до','after_end',dateISO(-1),'date','required')}</div>
 ${field('Плановый бюджет, ₽','budget_rub','0','number','min="0" max="10000000"')}
 ${button('Создать проверку','type="submit"','primary')}</form>`;
 target.innerHTML=`<div class="grid"><div class="stack">${p?card('Текущая проверка',`${row('Гипотеза',p.hypothesis)}${row('Показатель',v?.metric_label||p.metric)}${row('Базовый период',`${p.before_start} — ${p.before_end}`)}${row('Проверка',`${p.after_start} — ${p.after_end}`)}${row('Лимит расходов',rub(p.budget_kopeks))}${p.status==='draft'?`<div style="margin-top:15px">${button('Запустить пилот','id="start-pilot"','primary')}</div>`:''}`):card('Первое действие','<p>Создай пилот с заранее выбранным показателем и двумя равными периодами. Сравниваем то, что действительно учтено в кассе и источниках посещений.</p>')}
 ${card('Правила качества',`<p>Базовый и контрольный периоды одинаковой длины. Пилот не получает статус «доказал прибыль» от одной кнопки.</p><p>Если данных мало, источники смешаны или в расчёты попала демонстрация, вывод будет отмечен как неполный.</p>`)}</div>${card('Подготовить новый пилот',create)}</div>`;
 target.querySelector('#new-pilot').onsubmit=e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.target));const body={slug:state.slug,request_id:newid(),title:d.title,hypothesis:d.hypothesis,metric:d.metric,source_mode:d.source_mode,before_start:d.before_start,before_end:d.before_end,after_start:d.after_start,after_end:d.after_end,budget_kopeks:Math.round(Number(d.budget_rub)*100)};
 mutate(async()=>{const created=await api('/pilots',{method:'POST',body});state.selected=created.id})};
 if(p?.status==='draft')target.querySelector('#start-pilot').onclick=()=>mutate(()=>api(`/pilots/${p.id}/start`,{method:'POST'}));
}
function noPilot(target){target.innerHTML=`<div class="empty">Сначала создайте пилот во вкладке «План».</div>`}
function renderSources(target){if(!state.detail)return noPilot(target);const p=state.detail.pilot;
 target.innerHTML=`<div class="grid">${card('Источники и доверие',`${(state.detail.attestations||[]).map(x=>row(({traffic:'Посещаемость',pos:'Чеки',feedback:'Опросы'})[x.category],x.status,x.note)).join('')||'<p>Проверок пока нет.</p>'}<p class="sub">Статус «проверено» ставит сотрудник — это не независимая сертификация. Смешанные источники могут удваивать посещения.</p>`)}
 ${card('Подтверждение источника',p.status==='completed'||p.status==='cancelled'?'<p>Пилот закрыт. Редактирование запрещено.</p>':`<form id="attestation" class="form"><label>Источник<select name="category"><option value="traffic">Посещения</option><option value="pos">Касса</option><option value="feedback">Опросник</option></select></label><label>Состояние<select name="status"><option value="checked">Оператор проверил</option><option value="limited">Данные неполны</option><option value="unavailable">Источник отсутствует</option></select></label><label>Как именно проверяли<textarea name="note" minlength="8" required placeholder="Например, сверили число входов с ручным подсчётом за час"></textarea></label>${button('Сохранить проверку','type="submit"','primary')}</form>`)}</div>`;
 const form=target.querySelector('#attestation');if(form)form.onsubmit=e=>{e.preventDefault();mutate(()=>api(`/pilots/${p.id}/sources`,{method:'POST',body:Object.fromEntries(new FormData(form))}))};
}
function renderDaily(target){if(!state.detail)return noPilot(target);const p=state.detail.pilot;const v=state.preview;const b=v.baseline,a=v.intervention;
 const short=x=>x===null||x===undefined?'—':fmt(x);
 target.innerHTML=`<div class="metrics">${metric('Входы · база',fmt(b.visits),'по выбранному источнику')}${metric('Входы · проверка',fmt(a.visits),'по выбранному источнику')}${metric('Чеков · проверка',fmt(a.receipts),'не уникальные покупатели')}${metric('Изменение метрики',v.delta===null?'Не определено':`${v.delta>0?'+':''}${fmt(v.delta)}`,v.status==='sufficient_to_review'?'Данных достаточно для просмотра':'Проверить качество данных')}</div>
 <div class="grid"><div class="stack">${card(v.metric_label,`${row('Базовый период',short(b.metric_value))}${row('Период проверки',short(a.metric_value))}${row('Источники входов',a.visit_sources.join(', ')||'нет')}${row('Источники чеков',a.pos_sources.join(', ')||'нет')}<p>Числа сопоставимы только при одинаковой методике и достаточной выборке.</p>`)}
 ${card('Предупреждения',v.warnings.map(x=>`<div class="alert">${esc(x)}</div>`).join('')||'<div class="alert ok">Критичных предупреждений по заданным правилам нет.</div>')}</div>
 ${card('Дневные наблюдения',`<div class="table-wrap"><table><thead><tr><th>Дата</th><th>Период</th><th class="right">Входы</th><th class="right">Чеки</th><th class="right">Ответы</th></tr></thead><tbody>${v.daily.map(x=>`<tr><td>${esc(x.day)}</td><td>${x.phase==='baseline'?'База':'Проверка'}</td><td class="right">${fmt(x.visits)}</td><td class="right">${fmt(x.receipts)}</td><td class="right">${fmt(x.surveys)}</td></tr>`).join('')}</tbody></table></div>`)}</div>`;
}
function renderActions(target){if(!state.detail)return noPilot(target);const p=state.detail.pilot;const actions=state.detail.actions||[];
 target.innerHTML=`<div class="grid">${card('Журнал внедрённых изменений',actions.map(x=>row(x.description,rub(x.cost_kopeks),`${x.category} · ${x.created_at}${x.evidence?' · '+x.evidence:''}`)).join('')||'<p>Пока нет действий. Без них завершить пилот как проверку нельзя.</p>')}
 ${card('Зафиксировать действие',p.status!=='running'?'<p>Для добавления действий сначала запустите пилот. После завершения журнал становится неизменяемым.</p>':`<form id="action-entry" class="form"><label>Категория<select name="category"><option value="assortment">Ассортимент</option><option value="service">Обслуживание</option><option value="staffing">Смены персонала</option><option value="promotion">Промоакция</option><option value="operations">Операционные процессы</option></select></label><label>Что действительно изменили<textarea name="description" minlength="12" required placeholder="Например, добавили таблицу запросов недостающих размеров на кассе"></textarea></label><div class="input-grid">${field('Подтверждённые расходы, ₽','cost_rub','0','number','min="0"')}${field('Ссылка или номер документа','evidence','','text')}</div>${button('Записать действие','type="submit"','primary')}</form>`)}</div>`;
 const form=target.querySelector('#action-entry');if(form)form.onsubmit=e=>{e.preventDefault();const d=Object.fromEntries(new FormData(form));mutate(()=>api(`/pilots/${p.id}/actions`,{method:'POST',body:{request_id:newid(),category:d.category,description:d.description,cost_kopeks:Math.round(Number(d.cost_rub)*100),evidence:d.evidence}}))};
}
async function exportCsv(pilotId){const headers={Accept:'text/csv'};if(token())headers.Authorization=`Bearer ${token()}`;
 const resp=await fetch(`/api/admin/r15/pilots/${pilotId}/snapshot.csv`,{headers,cache:'no-store'});
 if(!resp.ok)throw Error(`Скачать CSV не удалось: ${resp.status}`);
 const url=URL.createObjectURL(await resp.blob());const anchor=document.createElement('a');anchor.href=url;anchor.download='osmanx-pilot-report.csv';document.body.append(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),3000)}
function renderReport(target){if(!state.detail)return noPilot(target);const p=state.detail.pilot;const v=state.preview;
 target.innerHTML=`<div class="grid">${card('Финансовая прозрачность',`${row('Плановый бюджет',rub(v.planned_budget_kopeks))}${row('Зарегистрированные расходы',rub(v.actual_logged_cost_kopeks))}${row('Достоверность наблюдения',v.status==='sufficient_to_review'?'Можно рассматривать':'Вывод не подтверждён')}${row('Проверяемый KPI',v.metric_label)}<p>Таблица отражает зарегистрированные расходы, но не проводит банковскую сверку и не вычисляет чистую прибыль.</p>`)}
 ${card('Решение о продолжении',p.status==='completed'||p.status==='cancelled'?`<p>Пилот завершён. Итог сохранён неизменяемым снимком.</p>${button('Проверить итоговый снимок','id="check-snapshot"')}${button('Экспортировать CSV','id="download-snapshot"')}`:p.status==='running'?`<form class="form" id="close-form"><label>Решение<select name="decision"><option value="completed">Завершить проверку</option><option value="cancelled">Отменить пилот</option></select></label><label>Обоснование<textarea name="note" required minlength="12" placeholder="Какие выводы подтверждены, а какие остаются неопределёнными"></textarea></label><p>Завершить как проверку можно только после полного периода и при наличии записанного действия. Отмена фиксируется отдельно.</p>${button('Зафиксировать решение','type="submit"','primary')}</form>`:'<p>Сначала запустите пилот во вкладке «План».</p>')}</div>
 ${card('Ограничения результата',`<p>${esc(v.methodology)}</p>${v.warnings.slice(0,10).map(x=>`<div class="alert">${esc(x)}</div>`).join('')||'<div class="alert ok">Дополнительных предупреждений нет.</div>'}`)}`;
 const form=target.querySelector('#close-form');if(form)form.onsubmit=e=>{e.preventDefault();mutate(()=>api(`/pilots/${p.id}/close`,{method:'POST',body:Object.fromEntries(new FormData(form))}))};
 const verify=target.querySelector('#check-snapshot');if(verify)verify.onclick=async()=>{try{const result=await api(`/pilots/${p.id}/snapshot`);notice(`SHA-256 подтверждён: ${result.sha256.slice(0,18)}…`)}catch(e){notice(e.message,true)}};
 const download=target.querySelector('#download-snapshot');if(download)download.onclick=async()=>{try{await exportCsv(p.id)}catch(e){notice(e.message,true)}};
}
(async()=>{try{const found=await apiRoot('stores');state.stores=Array.isArray(found)?found:(found.items||found.stores||[]);
 if(state.stores.length)state.slug=state.stores[0].slug;
 await load()}catch(e){root.innerHTML=`<div class="page"><header class="head"><div class="logo">OSMAN<span>X</span></div><a class="return" href="/">← Кабинет руководителя</a></header>${card('Требуется вход',`<p>${esc(e.message)}. Откройте основной кабинет, войдите в свой аккаунт и затем откройте Pilot Studio.</p>`)}</div>`}})();
