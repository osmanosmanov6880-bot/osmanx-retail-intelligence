import {api,setToken,hasToken} from './api.js';
import {icon} from './icons.js';
import {lineChart,barChart,donut} from './charts.js';

const root=document.querySelector('#app');
const toastTarget=document.querySelector('#toast');
const money=n=>new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0}).format(Number(n||0))+' ₽';
const integer=n=>new Intl.NumberFormat('ru-RU').format(Number(n||0));
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const shortDate=s=>{try{return new Date(s).toLocaleDateString('ru-RU',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}catch{return '—'}};
const reasonLabels={size:'Не нашёл нужный размер',price:'Высокая цена',assortment:'Не подошёл ассортимент',service:'Не дождался помощи',just_looking:'Просто смотрел',other:'Другое'};
const statusLabels={open:'Открыт',located:'Найден',notified:'Уведомлён',converted:'Купил',closed:'Закрыт'};
const menu=[{id:'overview',label:'Главная',ico:'home'},{id:'traffic',label:'Посетители',ico:'users'},{id:'demand',label:'Спрос и размеры',ico:'shirt'},{id:'feedback',label:'Опросы и отзывы',ico:'clipboard'},{id:'actions',label:'Рекомендации',ico:'sparkle'},{id:'integrations',label:'Интеграции',ico:'plug'},{id:'settings',label:'Настройки',ico:'settings'}];
const state={config:null,stores:[],store:null,data:null,slug:'central',days:30,page:'overview',menuOpen:false,kioskStep:0,kiosk:{rating:0,purchased:null,reason:'',liked:'',suggestion:''},error:'',loading:false};
let toastTimeout;
function toast(message,isError=false){clearTimeout(toastTimeout);toastTarget.innerHTML=`<div class="toast-content ${isError?'toast-error':''}">${esc(message)}</div>`;toastTimeout=setTimeout(()=>toastTarget.innerHTML='',4400)}
const featureTag=()=>state.config?.demo?'<span class="tag demo">● ДЕМО · пример данных</span>':'<span class="tag">● Рабочие данные</span>';
function navHtml(){return menu.map(m=>`<button class="nav-btn ${state.page===m.id?'active':''}" data-nav="${m.id}" ${state.page===m.id?'aria-current="page"':''}>${icon(m.ico)}<span>${m.label}</span></button>`).join('')}
function cardStat(label,value,ico,delta,meta='',emphasis=false){const positive=delta==null?'neutral':delta<0?'down':'';const deltaText=delta==null?'Нет сравнения':`${delta>0?'+':''}${String(delta).replace('.',',')}${label==='Конверсия'?' п.п.':'%'}`;return `<div class="panel kpi"><div class="kpi-icon"><span>${esc(label)}</span>${icon(ico)}</div><div class="kpi-value monospace ${emphasis?'emphasis':''}">${esc(value)}</div><div class="kpi-meta"><span class="delta ${positive}">${esc(deltaText)}</span><span class="muted">${esc(meta)}</span></div></div>`}
function pane(title,content,opts=''){return `<section class="panel ${opts}"><div class="panel-body"><div class="panel-head"><h2 class="panel-title">${esc(title)}</h2></div>${content}</div></section>`}
function heading(title,subtitle,actions=''){return `<div class="page-heading"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="heading-right">${actions}</div></div>`}
function miniEmpty(ico,title,description){return `<div class="empty">${icon(ico,36)}<strong>${esc(title)}</strong><p>${esc(description)}</p></div>`}
function deltaText(value){return value===null||value===undefined?'Недостаточно данных':`${value>0?'+':''}${value.toString().replace('.',',')}% к предыдущему периоду`}

async function init(){
  const kioskPath=location.pathname.match(/^\/kiosk(?:\/([\w-]+))?\/?$/);
  try{
    state.config=await api('/config');
    if(kioskPath){state.page='kiosk';state.slug=kioskPath[1]||'central';state.store=await api(`/public/store/${encodeURIComponent(state.slug)}`);render();return}
    if(state.config.demo||hasToken())await refresh();else renderLogin();
  }catch(e){state.error=e.message;renderError()}
}
async function refresh(){
  try{
    state.loading=true;
    if(!state.stores.length)state.stores=await api('/admin/stores',{auth:true});
    if(!state.stores.some(s=>s.slug===state.slug))state.slug=state.stores[0]?.slug||'central';
    state.store=state.stores.find(s=>s.slug===state.slug)||null;
    state.data=await api(`/admin/dashboard?slug=${encodeURIComponent(state.slug)}&days=${state.days}`,{auth:true});
    state.loading=false;render();
  }catch(e){state.loading=false;state.error=e.message;if(e.message.includes('Требуется вход')||e.message.includes('Сессия'))renderLogin();else renderError()}
}
function renderError(){root.innerHTML=`<div class="login-shell"><div class="panel login-card"><div class="brand">OSMAN<span>X</span></div><div class="brand-sub">RETAIL INTELLIGENCE</div><h1>Не удалось открыть приложение</h1><p>${esc(state.error)}</p><button class="primary-btn" data-action="retry">Повторить ${icon('arrow')}</button><p class="muted">Для локального запуска: <code>OSMANX_DEMO_MODE=1 uvicorn backend.app:app</code></p></div></div>`}
function renderLogin(){root.innerHTML=`<main class="login-shell"><form id="login-form" class="panel login-card"><div class="brand">OSMAN<span>X</span></div><div class="brand-sub">RETAIL INTELLIGENCE</div><h1>Вход в кабинет</h1><p>Защищённый доступ к аналитике магазина. Опросник для покупателей работает по отдельной публичной ссылке.</p><div class="field"><label for="admin-pass">Пароль администратора</label><input required autofocus type="password" id="admin-pass" name="password" class="input" autocomplete="current-password" placeholder="Введите пароль"/></div><button type="submit" class="primary-btn" style="width:100%;margin-top:18px">Войти в систему ${icon('arrow')}</button><p><a class="muted" href="/kiosk/central">Открыть публичный терминал опросов</a></p></form></main>`}
function render(){
  if(state.page==='kiosk'){renderKiosk();return}
  if(!state.data){renderError();return}
  document.title='OSMANX · Retail Intelligence';
  document.body.className='app-body';
  root.innerHTML=`<div class="shell">
    <aside class="sidebar ${state.menuOpen?'open':''}"><div class="logo-panel"><div class="brand">OSMAN<span>X</span></div><div class="brand-sub">RETAIL INTELLIGENCE</div></div><div class="side-tag">Рабочая область</div><nav class="nav">${navHtml()}</nav><div class="side-bottom"><div class="connection"><i class="dot"></i> ${state.config.demo?'Демо-среда':'Сервер подключён'}</div><small>© 2026 OSMANX WORLD</small></div></aside>
    <main class="main"><header class="topbar"><div class="top-left"><button class="icon-btn mobile-menu" data-action="menu" aria-label="Открыть меню">${icon('menu')}</button><div class="store-pill">${icon('store',17)}<select id="select-store" aria-label="Выбрать магазин">${state.stores.map(s=>`<option value="${esc(s.slug)}" ${s.slug===state.slug?'selected':''}>${esc(s.name)}</option>`).join('')}</select></div></div><div class="top-right">${featureTag()}<button class="date-pill ${state.days===7?'active':''}" data-days="7">7 дней</button><button class="date-pill ${state.days===30?'active':''}" data-days="30">30 дней</button><button class="icon-btn" title="Открыть опросник" data-action="open-kiosk">${icon('smartphone')}</button><div class="user-pill">OX</div></div></header>${pageHtml()}<footer class="muted" style="padding-top:25px;font-size:10px;line-height:1.7">OSMANX Retail Intelligence · ${esc(state.data.methodology)}</footer></main>
    <nav class="mobile-bottom" aria-label="Быстрая навигация">${[{id:'overview',label:'Главная',ico:'home'},{id:'traffic',label:'Поток',ico:'users'},{id:'demand',label:'Спрос',ico:'shirt'},{id:'feedback',label:'Отзывы',ico:'message'},{id:'actions',label:'Решения',ico:'sparkle'}].map(m=>`<button data-nav="${m.id}" class="${state.page===m.id?'active':''}">${icon(m.ico)}${m.label}</button>`).join('')}</nav>
    <dialog id="entry-dialog"></dialog>
  </div>`;
  if(state.menuOpen){const aside=document.querySelector('.sidebar');aside?.addEventListener('mouseleave',()=>{if(innerWidth>890)return;state.menuOpen=false;aside.classList.remove('open')},{once:true})}
}
function pageHtml(){switch(state.page){case'overview':return overview();case'traffic':return traffic();case'demand':return demand();case'feedback':return feedback();case'actions':return actions();case'integrations':return integrations();case'settings':return settings();default:return overview()}}
function overview(){const d=state.data;
return `${heading('Обзор бизнеса','Понимайте спрос. Находите точки роста. Принимайте решения на основе данных.',`<button class="secondary-btn" data-action="open-kiosk">${icon('smartphone')} Экран опроса</button><button class="primary-btn" data-dialog="demand">${icon('plus')} Записать запрос</button>`)}
<div class="hero-ribbon"><div><strong>Принимайте решения на основе подтверждённых фактов</strong><p>Причины отказов — гипотезы, пока не проверены данными и экспериментами.</p></div><button class="btn-link" data-nav="actions">Перейти к рекомендациям →</button></div>
<div class="content-grid">
 <div class="span-3">${cardStat('Посетители',integer(d.visitors),'users',d.delta_visitors,'входов')}</div>
 <div class="span-3">${cardStat('Покупки',integer(d.purchases),'bag',d.delta_purchases,'чеков')}</div>
 <div class="span-3">${cardStat('Конверсия',d.conversion.toString().replace('.',',')+'%','target',d.delta_conversion_pp,'чеков / входов')}</div>
 <div class="span-3">${cardStat('Выручка',money(d.revenue),'chart',d.delta_revenue,'по чекам',true)}</div>
 <div class="span-7">${pane('Посещаемость и покупки по часам',`<div class="legend"><span><b class="blue-dot"></b> Входы</span><span><b class="red-dot"></b> Покупки</span></div>${lineChart(d.hourly)}<p class="tip" style="margin-top:10px">Суммы событий по часам за ${d.period_days} дней.</p>`)}</div>
 <div class="span-5">${pane('Почему не совершили покупку?',donut(d.reasons)+`<div class="card-help">Данные добровольных опросов; не все покупатели отвечают.</div>`)}</div>
 <div class="span-6">${pane('Самый частый неудовлетворённый спрос',topDemand(d.top_demand,4))}</div>
 <div class="span-6">${pane('Рекомендации по действиям',recs(d.recommendations,3))}</div>
 <div class="span-7">${pane('События пути покупателя',funnel(d))}</div>
 <div class="span-5">${pane('Качество обратной связи',`<div class="metrics-row"><div class="micro-card"><span>Опросы</span><b>${integer(d.surveys_count)}</b></div><div class="micro-card"><span>Средняя оценка</span><b>${d.rating?d.rating.toString().replace('.',','):'—'} / 5</b></div><div class="micro-card"><span>Новые запросы</span><b>${integer(d.top_demand.reduce((a,v)=>a+v.count,0))}+</b></div></div><div class="separated"><a class="secondary-btn" href="/kiosk/${encodeURIComponent(state.slug)}" target="_blank" rel="noopener">${icon('smartphone')} Открыть терминал</a></div>`)}</div>
</div>`}
function topDemand(items,limit=6){return items.length?`<div class="demand-list">${items.slice(0,limit).map(d=>`<div class="demand-item"><div class="product-box">${icon('shirt')}</div><div class="demand-main"><strong>${esc(d.product)}</strong><small>Размер ${esc(d.size||'не указан')} · ${esc(d.color||'без цвета')}</small></div><div><div class="count monospace">${integer(d.count)}</div><small class="muted">запросов</small></div></div>`).join('')}</div>`:miniEmpty('shirt','Пока нет запросов','Добавьте первый запрос на отсутствующий товар или размер.')}
function recs(items,limit=6){return `<div class="rec-list">${items.slice(0,limit).map(r=>`<article class="rec-item"><div class="rec-symbol">${icon(r.type==='demand'?'shirt':r.type==='feedback'?'message':r.type==='traffic'?'chart':'sparkle')}</div><div><strong>${esc(r.title)}</strong><p>${esc(r.text)}</p></div></article>`).join('')}</div>`}
function funnel(d){const stages=[{text:'Вошли в магазин',value:d.visitors},{text:'События интереса',value:d.signals.interest||0},{text:'Примерки (события)',value:d.signals.fitting||0},{text:'Кассовые чеки',value:d.purchases}];return `<div class="funnel">${stages.map(s=>`<div class="funnel-step"><span>${esc(s.text)}</span><span>${integer(s.value)}</span></div>`).join('')}</div><p class="tip" style="margin-top:16px">Этапы могут фиксироваться разными источниками и не связаны с конкретными людьми. Диаграмма не является сквозной воронкой.</p>`}
function traffic(){const d=state.data;return `${heading('Посетители и конверсия','Движение по часам без распознавания лиц и скрытого слежения.',`<button class="primary-btn" data-dialog="entry">${icon('plus')} Добавить событие</button>`)}<div class="content-grid"><div class="span-3">${cardStat('Входы',integer(d.visitors),'users',d.delta_visitors)}</div><div class="span-3">${cardStat('Покупки',integer(d.purchases),'bag',d.delta_purchases)}</div><div class="span-3">${cardStat('Конверсия',d.conversion+'%','target',d.delta_conversion_pp)}</div><div class="span-3">${cardStat('Средний чек',money(d.avg_receipt),'tag',null)}</div><div class="span-8">${pane('Поток по часам',`<div class="legend"><span><b class="blue-dot"></b> Входы</span><span><b class="red-dot"></b> Покупки</span></div>${barChart(d.hourly)}<p class="tip" style="margin-top:15px">События за ${d.period_days} дней. Ручной ввод и подключённые источники суммируются.</p>`)}</div><div class="span-4">${pane('Как начать подсчёт',`<div class="info-stack"><div class="info-line"><span>1. Входы</span><b>Ручной ввод / датчик</b></div><div class="info-line"><span>2. Чеки</span><b>Ручной ввод / импорт</b></div><div class="info-line"><span>3. Причины</span><b>Опрос на выходе</b></div></div><div class="separated"><button class="secondary-btn" data-dialog="entry">${icon('plus')} Зафиксировать вход</button></div><div class="separated note">Без счётчика можно вручную добавлять события. Для точной конверсии нужны сопоставимые данные входов и чеков.</div>`)}</div><div class="span-12">${pane('Быстрый ввод событий',`<div class="inline-actions"><button class="secondary-btn" data-quick="entry">${icon('users')} +1 вход</button><button class="secondary-btn" data-dialog="sale">${icon('bag')} Новая продажа</button><button class="secondary-btn" data-quick="interest">${icon('heart')} Интерес</button><button class="secondary-btn" data-quick="fitting">${icon('shirt')} Примерка</button></div>`)}</div></div>`}
function demand(){const d=state.data;const list=d.latest_demand;return `${heading('Невидимый спрос','Регистрируйте то, чего не было в наличии: размер, цвет, модель.',`<button class="primary-btn" data-dialog="demand">${icon('plus')} Новый запрос</button>`)}<div class="content-grid"><div class="span-5">${pane('Самые востребованные отсутствующие позиции',topDemand(d.top_demand,6))}</div><div class="span-7">${pane('Почему это важно',`<div class="rec-list"><article class="rec-item"><div class="rec-symbol">${icon('target')}</div><div><strong>1С показывает проданное, а не все несостоявшиеся покупки</strong><p>Фиксируйте обращения и измеряйте, сколько удалось удовлетворить через другой филиал или новую поставку.</p></div></article><article class="rec-item"><div class="rec-symbol">${icon('shield')}</div><div><strong>Запрос ≠ гарантированная продажа</strong><p>Оценивайте подтверждённый спрос и последующие покупки. Не называйте каждый запрос упущенной выручкой.</p></div></article></div>`)}</div><div class="span-12">${pane('Журнал запросов',list.length?`<div class="panel-overflow"><table class="list-table"><thead><tr><th>Товар</th><th>Размер</th><th>Цвет</th><th>Когда</th><th>Статус</th></tr></thead><tbody>${list.map(r=>`<tr><td><strong>${esc(r.product)}</strong></td><td>${esc(r.size||'—')}</td><td>${esc(r.color||'—')}</td><td>${shortDate(r.created_at)}</td><td><select class="select" style="width:130px;padding:7px" data-demand-id="${r.id}" aria-label="Статус запроса">${Object.entries(statusLabels).map(([key,label])=>`<option value="${key}" ${r.status===key?'selected':''}>${label}</option>`).join('')}</select></td></tr>`).join('')}</tbody></table></div>`:miniEmpty('shirt','Нет запросов','Добавьте первый интерес к отсутствующему товару.'))}</div></div>`}
function feedback(){const d=state.data;return `${heading('Опросы и обратная связь','Добровольные ответы покупателей в одном кабинете.',`<button class="primary-btn" data-action="open-kiosk">${icon('smartphone')} Открыть терминал</button>`)}<div class="content-grid"><div class="span-3">${cardStat('Получено ответов',integer(d.surveys_count),'clipboard',null)}</div><div class="span-3">${cardStat('Средняя оценка',(d.rating||0).toString().replace('.',',')+'/5','star',null)}</div><div class="span-6">${pane('Популярные причины ухода',donut(d.reasons))}</div><div class="span-12">${pane('Последние ответы',d.latest_surveys.length?`<div class="panel-overflow"><table class="list-table"><thead><tr><th>Дата</th><th>Оценка</th><th>Покупка</th><th>Причина</th><th>Что понравилось</th><th>Предложение</th></tr></thead><tbody>${d.latest_surveys.map(s=>`<tr><td class="nowrap">${shortDate(s.created_at)}</td><td class="nowrap"><span class="red">${'★'.repeat(s.rating)}</span></td><td>${s.purchased?'Да':'Нет'}</td><td>${esc(reasonLabels[s.reason]||'—')}</td><td>${esc(s.liked||'—')}</td><td>${esc(s.suggestion||'—')}</td></tr>`).join('')}</tbody></table></div>`:miniEmpty('message','Ещё нет отзывов','Попросите первых покупателей заполнить короткий опрос.'))}</div><div class="span-12"><div class="note">Скидки и подарки не выдаются автоматически. Текст поощрения на терминале настраивается владельцем, реальные промокоды требуют подключения кассы и проверки условий акции.</div></div></div>`}
function actions(){const d=state.data;return `${heading('Рекомендации и решения','Правила диагностики на основе измерений. Никаких выдуманных прогнозов.',`<button class="secondary-btn" data-nav="demand">${icon('shirt')} Проверить спрос</button>`)}<div class="content-grid"><div class="span-7">${pane('Гипотезы, которые стоит проверить',recs(d.recommendations)+`<div class="separated note">Рекомендации основаны на простых проверяемых правилах, а не на модели, которая гарантирует рост продаж.</div>`)}</div><div class="span-5">${pane('Сценарий роста выручки',`<div class="form-card"><p class="tip">Это математическая модель, не прогноз. Проверьте влияние на прибыль после учёта затрат и маржи.</p><div class="field"><label for="scenario-pp">Прирост конверсии, процентных пунктов</label><input id="scenario-pp" type="range" min="0" max="10" step="0.5" value="2" style="width:100%;accent-color:#f43856"/><b id="scenario-pp-label">2 п.п.</b></div><div class="field"><label for="scenario-margin">Валовая маржа, %</label><input id="scenario-margin" type="number" value="45" min="1" max="100" step="1" class="input"/></div><div class="micro-card"><span>Условная доп. выручка за ${d.period_days} дней</span><b id="scenario-revenue">—</b></div><div class="micro-card"><span>Условная доп. валовая прибыль до затрат</span><b id="scenario-profit">—</b></div></div>`)}</div><div class="span-12">${pane('Что измерять перед платным пилотом',`<div class="metrics-row"><div class="micro-card"><span>Неделя 1</span><b>База</b><span>Собрать входы, чеки и опросы</span></div><div class="micro-card"><span>Неделя 2</span><b>Гипотеза</b><span>Проверить одну причину отказов</span></div><div class="micro-card"><span>Результат</span><b>Решение</b><span>Сравнить конверсию и прибыль</span></div></div>`)}</div></div>`}
function integrations(){return `${heading('Интеграции','Честные статусы подключений: сначала данные, затем автоматизация.')}
<div class="content-grid"><div class="span-6">${pane('Доступные способы ввода',`<div class="info-stack"><div class="integration-item"><div class="integration-logo">${icon('users')}</div><div><strong>Ручная регистрация входов</strong><p>Уже работает через интерфейс.</p></div><span class="status converted">Активно</span></div><div class="integration-item"><div class="integration-logo">${icon('clipboard')}</div><div><strong>Терминал опросов</strong><p>Самостоятельная страница для планшета у выхода.</p></div><span class="status converted">Активно</span></div><div class="integration-item"><div class="integration-logo">${icon('database')}</div><div><strong>Импорт чеков через JSON</strong><p>Рабочий API с защитой от повторного импорта.</p></div><span class="status converted">Активно</span></div></div>`)}</div><div class="span-6">${pane('Следующие интеграции',`<div class="info-stack"><div class="integration-item"><div class="integration-logo">${icon('camera')}</div><div><strong>Счётчик входов / камера</strong><p>Серверный API готов; реальный счётчик нужно подключить и откалибровать.</p></div><span class="status open">Не подключён</span></div><div class="integration-item"><div class="integration-logo">${icon('layers')}</div><div><strong>1С и кассовые системы</strong><p>Есть импорт чеков; прямой синхронизации с вашей кассой пока нет.</p></div><span class="status open">Не подключён</span></div><div class="integration-item"><div class="integration-logo">${icon('smartphone')}</div><div><strong>Покупательское приложение</strong><p>Потребуются согласование функций, лояльность и отдельная интеграция.</p></div><span class="status open">Не подключено</span></div></div>`)}</div><div class="span-12">${pane('Пример импорта кассовых продаж',`<p class="tip">Вставьте JSON-массив чеков. Каждый чек должен иметь уникальный идентификатор в системе-источнике.</p><form id="import-form" class="form-card" style="margin-top:15px"><div class="field"><label for="pos-json">Продажи (JSON)</label><textarea id="pos-json" name="records" class="textarea" rows="5" spellcheck="false" placeholder='[{"external_id":"receipt-001","amount_rub":5490,"occurred_at":"2026-11-08T12:00:00Z"}]' required></textarea></div><div><button class="primary-btn" type="submit">${icon('download')} Импортировать чеки</button></div></form><div class="separated"><span class="section-label">API счётчика</span><pre class="code">POST /api/ingest/traffic\nX-OSMANX-Ingest-Key: &lt;приватный ключ&gt;\n{ "slug": "${esc(state.slug)}", "quantity": 1, "external_id": "sensor-123", "occurred_at": "2026-11-08T12:00:00Z" }</pre><p class="tip">Для настоящего датчика нужен HTTPS, приватный ключ и настройка устройства. В демо данные синтетические.</p></div>`)}</div></div>`}
function settings(){const s=state.store||{};return `${heading('Настройки магазина','Название филиала и сообщение для терминала опросов.')}
<div class="content-grid"><div class="span-7">${pane('Карточка магазина',`<form id="store-form" class="form-card"><div class="field"><label for="store-name">Название</label><input class="input" id="store-name" name="name" value="${esc(s.name)}" maxlength="100" required/></div><div class="field"><label for="store-subtitle">Подзаголовок</label><input class="input" id="store-subtitle" name="subtitle" value="${esc(s.subtitle)}" maxlength="150" /></div><div class="field"><label for="store-incentive">Сообщение о бонусе после опроса (необязательно)</label><input class="input" id="store-incentive" name="incentive" value="${esc(s.incentive)}" maxlength="160" placeholder="Например: узнайте у продавца о бонусах"/></div><div><button type="submit" class="primary-btn">${icon('check')} Сохранить изменения</button></div></form>`)}</div><div class="span-5">${pane('Публичная ссылка на опрос',`<p class="tip">Откройте адрес на планшете и включите полноэкранный режим браузера.</p><div class="code" style="margin:14px 0" id="kiosk-url">${esc(location.origin+'/kiosk/'+state.slug)}</div><div class="inline-actions"><button class="secondary-btn" data-action="copy-kiosk">${icon('link')} Скопировать</button><button class="secondary-btn" data-action="open-kiosk">${icon('smartphone')} Открыть</button></div><div class="separated note">Для публичного использования включите HTTPS, установите администраторский пароль и ограничьте доступ к панели. Деморежим не предназначен для открытого интернета.</div>`)}</div>${!state.config.demo?`<div class="span-12">${pane('Управление сессией',`<button class="ghost-btn" data-action="logout">${icon('logout')} Выйти из кабинета</button>`)}</div>`:''}</div>`}
function renderKiosk(){
  document.title='OSMANX · Ваше мнение';
  document.body.className='kiosk-body';
  const s=state.store||{name:'Магазин',subtitle:'',incentive:''};
  const k=state.kiosk;
  const step=state.kioskStep;
  let body='',bottom='';
  if(step===0){
    body=`<span class="eyebrow">Всего несколько секунд</span><h2 style="margin-top:16px">Помогите нам<br>стать лучше</h2><p>Ваш отзыв поможет магазину улучшить ассортимент и обслуживание. Никакой регистрации не требуется.</p><div class="kiosk-options"><div class="kiosk-option" style="pointer-events:none">${icon('clock')}Быстро и удобно</div><div class="kiosk-option" style="pointer-events:none">${icon('shield')}Без персональных данных</div></div>`;
    bottom=`<button class="primary-btn" data-kiosk="start">Начать опрос ${icon('arrow')}</button>`;
  }else if(step===1){
    body=`<span class="eyebrow">Вопрос 1 из 3</span><h2 style="margin-top:15px">Как прошло ваше посещение?</h2><p>Оцените общее впечатление от магазина.</p><div class="stars" role="group" aria-label="Оценка от одного до пяти"><button class="star ${k.rating>=1?'selected':''}" data-rating="1" aria-label="1 из 5">★</button><button class="star ${k.rating>=2?'selected':''}" data-rating="2" aria-label="2 из 5">★</button><button class="star ${k.rating>=3?'selected':''}" data-rating="3" aria-label="3 из 5">★</button><button class="star ${k.rating>=4?'selected':''}" data-rating="4" aria-label="4 из 5">★</button><button class="star ${k.rating>=5?'selected':''}" data-rating="5" aria-label="5 из 5">★</button></div><div style="display:flex;justify-content:space-between;color:#8b9caf;font-size:11px;margin-top:12px"><span>Не понравилось</span><span>Отлично</span></div>`;
    bottom=`<button class="secondary-btn" data-kiosk="back">Назад</button><button class="primary-btn" data-kiosk="next" ${!k.rating?'disabled':''}>Продолжить ${icon('arrow')}</button>`;
  }else if(step===2){
    body=`<span class="eyebrow">Вопрос 2 из 3</span><h2 style="margin-top:15px">Удалось найти то, что искали?</h2><p>Подскажите, совершили ли вы покупку сегодня?</p><div class="kiosk-options"><button class="kiosk-option ${k.purchased===true?'selected':''}" data-purchased="yes">${icon('bag')} Да, я купил(а)</button><button class="kiosk-option ${k.purchased===false?'selected':''}" data-purchased="no">${icon('cross')} Нет, без покупки</button></div>${k.purchased===false?`<span class="kiosk-label">Что повлияло на решение?</span><div class="kiosk-options" style="margin-top:8px">${Object.entries(reasonLabels).map(([key,label])=>`<button class="kiosk-option ${k.reason===key?'selected':''}" style="min-height:65px" data-reason="${key}">${esc(label)}</button>`).join('')}</div>`:''}`;
    bottom=`<button class="secondary-btn" data-kiosk="back">Назад</button><button class="primary-btn" data-kiosk="next" ${k.purchased===null||(k.purchased===false&&!k.reason)?'disabled':''}>Продолжить ${icon('arrow')}</button>`;
  }else if(step===3){
    body=`<span class="eyebrow">Вопрос 3 из 3</span><h2 style="margin-top:15px">Что нам улучшить?</h2><p>Ваш ответ поможет принимать решения о товарах и сервисе. Этот шаг необязателен.</p><form id="kiosk-form"><label class="kiosk-label" for="liked">Что понравилось?</label><input id="liked" class="input kiosk-input" maxlength="100" name="liked" value="${esc(k.liked)}" placeholder="Например, атмосфера и выбор"/><label class="kiosk-label" for="suggestion">Что добавить или изменить?</label><textarea id="suggestion" class="textarea kiosk-input" maxlength="400" rows="4" name="suggestion" placeholder="Например, больше размеров XL">${esc(k.suggestion)}</textarea><div class="kiosk-buttons" style="margin-top:22px"><button class="secondary-btn" type="button" data-kiosk="back">Назад</button><button class="primary-btn" type="submit" id="kiosk-submit">Отправить отзыв ${icon('send')}</button></div></form>`;
  }else{
    body=`<div class="kiosk-thanks"><div class="thank-icon">${icon('check',45)}</div><span class="eyebrow">Ответ получен</span><h2 style="margin-top:14px">Спасибо!</h2><p>Ваше мнение помогает нам делать ассортимент и обслуживание лучше.</p>${s.incentive?`<div class="kiosk-incentive">${icon('gift',22)}<div style="margin-top:9px">${esc(s.incentive)}</div></div>`:''}</div>`;
    bottom=`<button class="primary-btn" data-kiosk="restart">Новый опрос ${icon('arrow')}</button>`;
  }
  root.innerHTML=`<div class="kiosk-shell"><section class="kiosk-visual"><div class="kiosk-brand"><div class="brand">OSMAN<span>X</span></div><div class="brand-sub">RETAIL INTELLIGENCE</div></div><div class="kiosk-orb"></div><div class="kiosk-visual-body"><div class="eyebrow">ВАШЕ МНЕНИЕ ИМЕЕТ ЗНАЧЕНИЕ</div><h1>Ваш опыт.<br><span class="red">Наши решения.</span></h1><p>Несколько секунд обратной связи помогают нам понимать, какие товары и сервис действительно нужны покупателям.</p></div><div class="kiosk-visual-foot"><span>ПРОСТО</span><span>БЫСТРО</span><span>АНОНИМНО</span></div></section><main class="kiosk-right"><div class="kiosk-card"><header class="kiosk-card-top"><div><div class="brand" style="font-size:24px">OSMAN<span>X</span></div><div class="brand-sub" style="font-size:8px">RETAIL INTELLIGENCE</div></div><span class="kiosk-store">${esc(s.name)}</span></header><div class="progress"><div style="width:${step===0?0:step===4?100:step*33.33}%"></div></div><div class="kiosk-card-body" style="${step===4?'display:flex':''}">${body}</div>${step!==3?`<footer class="kiosk-buttons">${bottom}</footer>`:''}<p style="text-align:center;font-size:10px;color:#687b94;margin-top:18px">Опрос добровольный · Ваше имя не требуется</p></div></main></div>`;
}
function openDialog(type){const dialog=document.getElementById('entry-dialog');if(!dialog)return;
 let title='',body='';
 if(type==='demand'){
 title='Новый запрос покупателя';body=`<form id="demand-form" class="dialog-body"><p class="dialog-note">Сохраняйте фактические обращения, даже если покупка не состоялась.</p><div class="field"><label>Название товара</label><input class="input" name="product" required minlength="2" maxlength="120" placeholder="Куртка демисезонная" autofocus/></div><div class="field-row"><div class="field"><label>Размер</label><input class="input" name="size" maxlength="30" placeholder="XL"/></div><div class="field"><label>Цвет</label><input class="input" name="color" maxlength="50" placeholder="Чёрный"/></div></div><button type="submit" class="primary-btn">${icon('check')} Сохранить запрос</button></form>`;
 }else{
 const isSale=type==='sale';title=isSale?'Зарегистрировать покупку':'Новое событие посетителя';body=`<form id="event-form" class="dialog-body"><p class="dialog-note">Данные вручную добавятся к показателям магазина. Избегайте двойного учёта при подключённом датчике или кассе.</p><div class="field"><label>Тип события</label><select class="select" name="kind" id="event-kind"><option value="entry" ${isSale?'':'selected'}>Посетитель вошёл</option><option value="sale" ${isSale?'selected':''}>Покупка / чек</option><option value="interest">Интерес к товару</option><option value="fitting">Примерка</option></select></div><div class="field"><label>Количество (для покупок — 1 чек)</label><input class="input" type="number" name="quantity" min="1" max="500" value="1" required/></div><div class="field"><label>Сумма чека, ₽ (для продаж)</label><input class="input" type="number" name="amount_rub" min="0" max="20000000" step="0.01" value="0" /></div><button type="submit" class="primary-btn">${icon('check')} Добавить событие</button></form>`;
 }
 dialog.innerHTML=`<div class="dialog-head"><h2>${esc(title)}</h2><button class="dialog-x" type="button" data-action="close-dialog" aria-label="Закрыть">×</button></div>${body}`;dialog.showModal();
}
function updateScenario(){const pp=Number(document.getElementById('scenario-pp')?.value||2),margin=Number(document.getElementById('scenario-margin')?.value||45);const label=document.getElementById('scenario-pp-label');const revenue=document.getElementById('scenario-revenue');const profit=document.getElementById('scenario-profit');if(!label||!revenue||!profit)return;label.textContent=`${pp.toString().replace('.',',')} п.п.`;const d=state.data;const potential=d.visitors*pp/100*d.avg_receipt;revenue.textContent=money(potential);profit.textContent=money(potential*Math.min(100,Math.max(0,margin))/100)}
async function handleClick(event){
 const button=event.target.closest('button,[data-action],[data-nav],[data-dialog],[data-days],[data-rating],[data-kiosk]');if(!button)return;
 if(button.matches('button')&&button.disabled)return;
 if(button.dataset.nav){state.page=button.dataset.nav;state.menuOpen=false;render();if(state.page==='actions')updateScenario();scrollTo({top:0,behavior:'smooth'});return}
 if(button.dataset.days){state.days=Number(button.dataset.days);await refresh();return}
 if(button.dataset.dialog){openDialog(button.dataset.dialog);return}
 if(button.dataset.rating){state.kiosk.rating=Number(button.dataset.rating);renderKiosk();return}
 if(button.dataset.purchased){state.kiosk.purchased=button.dataset.purchased==='yes';state.kiosk.reason='';renderKiosk();return}
 if(button.dataset.reason){state.kiosk.reason=button.dataset.reason;renderKiosk();return}
 if(button.dataset.kiosk){const action=button.dataset.kiosk;
    if(action==='restart'){state.kiosk={rating:0,purchased:null,reason:'',liked:'',suggestion:''};state.kioskStep=0}
    else if(action==='start')state.kioskStep=1;
    else if(action==='back')state.kioskStep=Math.max(0,state.kioskStep-1);
    else if(action==='next'){
      if(state.kioskStep===1&&!state.kiosk.rating)return;
      if(state.kioskStep===2&&(state.kiosk.purchased===null||(state.kiosk.purchased===false&&!state.kiosk.reason)))return;
      state.kioskStep=Math.min(3,state.kioskStep+1);
    }
    renderKiosk();return;
 }
 if(button.dataset.quick){try{await api('/admin/events',{method:'POST',auth:true,body:{slug:state.slug,kind:button.dataset.quick,quantity:1,amount_rub:0}});toast('Событие записано');await refresh()}catch(e){toast(e.message,true)}return}
 switch(button.dataset.action){
  case 'retry':await init();break;
  case 'menu':state.menuOpen=!state.menuOpen;render();break;
  case 'open-kiosk':window.open(`/kiosk/${encodeURIComponent(state.slug)}`,'_blank','noopener');break;
  case 'copy-kiosk':try{await navigator.clipboard.writeText(location.origin+'/kiosk/'+state.slug);toast('Ссылка скопирована')}catch{toast('Не удалось скопировать автоматически',true)}break;
  case 'close-dialog':document.querySelector('#entry-dialog')?.close();break;
  case 'logout':setToken('');state.data=null;renderLogin();break;
 }
}
async function handleSubmit(event){const form=event.target;if(!form?.id)return;event.preventDefault();const submit=form.querySelector('[type=submit]');if(submit)submit.disabled=true;
 try{
  const data=Object.fromEntries(new FormData(form));
  if(form.id==='login-form'){
    const result=await api('/auth/login',{method:'POST',body:{password:data.password}});
    setToken(result.token);state.error='';await refresh();toast('Вход выполнен');return;
  }
  if(form.id==='kiosk-form'){
    state.kiosk.liked=String(data.liked||'').trim();state.kiosk.suggestion=String(data.suggestion||'').trim();
    await api(`/public/survey/${encodeURIComponent(state.slug)}`,{method:'POST',body:{...state.kiosk}});
    state.kioskStep=4;renderKiosk();return;
  }
  if(form.id==='demand-form'){
    await api('/admin/demand',{method:'POST',auth:true,body:{slug:state.slug,product:data.product,size:data.size,color:data.color}});
    document.querySelector('#entry-dialog')?.close();toast('Запрос сохранён');await refresh();return;
  }
  if(form.id==='event-form'){
    await api('/admin/events',{method:'POST',auth:true,body:{slug:state.slug,kind:data.kind,quantity:Number(data.quantity),amount_rub:Number(data.amount_rub)}});
    document.querySelector('#entry-dialog')?.close();toast('Событие добавлено');await refresh();return;
  }
  if(form.id==='store-form'){
    await api(`/admin/store/${encodeURIComponent(state.slug)}`,{method:'PUT',auth:true,body:{name:data.name,subtitle:data.subtitle,incentive:data.incentive}});
    state.stores=[];toast('Настройки сохранены');await refresh();return;
  }
  if(form.id==='import-form'){
    let records;try{records=JSON.parse(data.records)}catch{throw new Error('Неверный формат JSON')}
    if(!Array.isArray(records))throw new Error('Ожидается массив чеков');
    const result=await api('/admin/import/pos',{method:'POST',auth:true,body:{slug:state.slug,sales:records}});
    toast(`Импортировано ${result.imported}, пропущено повторов ${result.duplicates}`);await refresh();return;
  }
 }catch(e){toast(e.message||'Ошибка операции',true)}finally{if(submit&&submit.isConnected)submit.disabled=false}
}
async function handleChange(event){const target=event.target;if(target.id==='select-store'){state.slug=target.value;await refresh()}
 if(target.dataset.demandId){try{await api(`/admin/demand/${target.dataset.demandId}`,{method:'PATCH',auth:true,body:{status:target.value}});toast('Статус обновлён');await refresh()}catch(e){toast(e.message,true)}}
 if(target.id==='scenario-pp'||target.id==='scenario-margin')updateScenario();
}
document.addEventListener('click',handleClick);
document.addEventListener('submit',handleSubmit);
document.addEventListener('change',handleChange);
document.addEventListener('input',event=>{if(event.target.id==='scenario-pp'||event.target.id==='scenario-margin')updateScenario()});
window.addEventListener('popstate',()=>{if(location.pathname.startsWith('/kiosk/'))init()});
init();
