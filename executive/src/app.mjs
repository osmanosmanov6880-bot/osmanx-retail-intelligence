import {AS_OF,STORES,CATEGORIES,SIZES,SCENARIOS,AURA,CATALOG,buildDataset,scopeData,product,daysAgo,forecastTransfer,pilotForecast,FUNNEL_STAGES,funnelData,opportunityMetrics,recommendations,diagnosticPlan,MONEY,NUMBER,PERCENT,safeRatio} from './model.mjs';
import {esc,icon,lineChart,barViz,funnelMarkup,opportunityMap,sourceTag,storeName,rawTable,emptyState} from './ui.mjs';
import {exportPdf} from './pdf.mjs';
import {reconcileEvidence,planTransfer,evaluatePilot,restoreJournal,newJournalEntry,transitionJournal,journalStats,JOURNAL_VERSION,evidenceForOpportunity,journalCsv} from './r3_core.mjs';
import {renderEvidencePage,renderTransferPage,renderPilotPage,renderJournalPage} from './r3_views.mjs';
import {auditEvidence,matchDemand,discountStress,prioritizePortfolio,dossierSnapshot,dossierCsv,auditCsv,matchingCsv,portfolioCsv} from './r4_core.mjs';
import {renderTrustPage,renderMatchPage,renderMarginPage,renderPortfolioPage,renderDossierPage} from './r4_views.mjs';
import {exportDossierPdf} from './r4_dossier.mjs';
import {reviewImport,reviewedCsv,sampleCsv,retentionCohorts,cohortCsv,collectionPlan,collectionCsv,serviceHealth,serviceCsv,branchBenchmark,benchmarkCsv} from './r5_core.mjs';
import {renderR5DataRoom,renderR5Cohorts,renderR5Collection,renderR5Service,renderR5Benchmark} from './r5_views.mjs';
import {exportBranchPdf} from './r5_report.mjs';
import {inspectMapping,mapAndValidate,exportRowsCsv,traceLostDemand,analyzeReturns,designPilot,assignmentsCsv,BOARD_VERSION,restoreBoard,createBoardItem,advanceBoard,boardSummary,boardCsv,BOARD_OWNERS} from './r6_core.mjs';
import {renderR6Mapping,renderR6Demand,renderR6Returns,renderR6Pilot,renderR6Board} from './r6_views.mjs';
import {decisionEvidenceGate,gateCsv,networkRebalance,rebalanceCsv,capitalAllocation,capitalCsv,privacySimulation,anonymousPrivacyCsv,PRIVACY_LEDGER_VERSION,appendPrivacyAudit,restorePrivacyAudit,executiveBrief,briefCsv} from './r7_core.mjs';
import {renderR7Gate,renderR7Rebalance,renderR7Capital,renderR7Privacy,renderR7Brief} from './r7_views.mjs';
import {exportR7BriefPdf} from './r7_pdf.mjs';
import {R8_KINDS,emptyWorkingSet,r8Example,acceptCsv,inspectWorkingSet,salesLedger,availabilityPlan,recoveryPilot,r8OwnerBrief,ledgerCsv,availabilityCsv,recoveryCsv,r8BriefCsv,R8_AUDIT_VERSION,appendR8Audit,restoreR8Audit,r8AuditCsv} from './r8_core.mjs';
import {renderR8Intake,renderR8Ledger,renderR8Availability,renderR8Recovery,renderR8Brief} from './r8_views.mjs';
import {exportR8BriefPdf} from './r8_pdf.mjs';
import {R9_SCHEMA,r9Empty,r9Example,r9AcceptCsv,r9Reconcile,r9Settlements,r9Cases,r9Transition,r9DailyClose,r9Pack,r9ReportCsv,r9CasesCsv,r9DayCsv,r9BankCsv,r9AggregateSignoff,r9RestoreSignoffs,r9SignoffCsv} from './r9_core.mjs';
import {renderR9Vault,renderR9Matching,renderR9Bank,renderR9Exceptions,renderR9Cfo} from './r9_views.mjs';
import {exportR9Pdf} from './r9_pdf.mjs';
import {r8Csv} from './r8_core.mjs';

const MODULES=[
 ['Невидимый спрос','INVISIBLE DEMAND','Увидеть запросы, которые не стали чеками.','Запросы покупателей и связанные продажи','Запустить добровольные уведомления о размере'],
 ['Диагностика примерочных','FITTING ROOM INTELLIGENCE','Что примеряли, но не приобрели — и известно ли почему?','Наблюдения в примерочной','Протоколировать реальные причины отказа'],
 ['Реальное наличие','INVENTORY REALITY','Остаток в учёте ещё не означает доступность на полке.','Выборочные инвентаризации','Проверить спорные позиции физически'],
 ['Спасение продаж','SALES RESCUE','Покупатель ушёл, хотя товар мог быть в другом филиале.','Запросы + межфилиальные остатки','Проверить перемещение и резерв'],
 ['Эффективность витрин','STOREFRONT PERFORMANCE','Какая экспозиция связана с большей долей входов?','Агрегированный поток прохожих','Сравнить сопоставимые периоды без причинных обещаний'],
 ['Скорость помощи','SERVICE RESPONSE','Как долго покупатель ждёт ответа сотрудника?','Добровольные QR-обращения','Измерить время реакции и повторить замер'],
 ['Повторные покупки','CUSTOMER RETURN','Какая доля участников программы возвращается?','Согласованные данные лояльности','Проверить когорты и периоды'],
 ['Защита валовой прибыли','MARGIN PROTECTION','Когда скидка уменьшает валовую прибыль?','Чеки, цены, себестоимость и возвраты','Проверить скидочную политику на SKU'],
 ['Будущая коллекция','FUTURE COLLECTION','Какие намерения покупателей заслуживают проверки закупкой?','Запросы, опросы, добровольные предзаказы','Проверить ассортимент небольшим тестом'],
 ['Диагностика возвратов','RETURN DIAGNOSTICS','Какие причины возврата повторяются у моделей и размеров?','Связанные возвраты и первоначальные чеки','Сверить причины и партии поставок']
];
const svgLogo=`<span class="brand-name">OSMAN<span>X</span></span><span class="brand-sub">RETAIL INTELLIGENCE</span>`;
const NAV=[
 {label:'ОБЗОР',items:[['dashboard','Финансовые возможности','grid'],['demo','Executive Demo · 30 секунд','play'],['decisions','Решения на сегодня','bolt'],['evidence','Проверка цифр','shield'],['transfer-lab','Перемещения: расчёт','layers'],['pilot-lab','Пилотный эксперимент','chart'],['journal','Журнал решений','file'],['calculator','Финансовый симулятор','chart'],['trust-lab','Качество данных','shield'],['demand-match','Поиск размеров по сети','layers'],['margin-stress','Экономика скидок','chart'],['portfolio','Приоритеты и бюджет','target'],['dossier','Документ решений','file']]},
 {label:'ATELIER R5 · ПРОВЕРКА И РЕШЕНИЯ',items:[['data-room','Проверка CSV-выгрузки','shield'],['cohort-lab','Когорты повторных покупок','chart'],['collection-lab','План будущей коллекции','layers'],['service-lab','Протокол сервиса','target'],['branch-lab','Сравнение филиалов','shops']]},
 {label:'ATELIER R6 · ДОКАЗАТЕЛЬСТВА И ДЕЙСТВИЯ',items:[['mapping-lab','CSV: сопоставление полей','shield'],['demand-trace','Трассировка потерянных покупок','target'],['returns-risk','Возвраты: причины и риск','chart'],['pilot-design','Дизайн контролируемого пилота','layers'],['action-board','Задачи и контроль исполнения','file']]},
 {label:'ATELIER R7 · РЕШЕНИЯ С ДОКАЗАТЕЛЬСТВАМИ',items:[['evidence-gate','Качество выводов','shield'],['network-rebalance','Баланс остатков сети','layers'],['capital-lab','Капитал и ограничения','chart'],['privacy-lab','Политика данных','shield'],['executive-brief','Досье собственника','file']]},
 {label:'ATELIER R8 · ЛОКАЛЬНЫЕ ФАКТЫ',items:[['local-vault','CSV: локальная приёмка','shield'],['local-ledger','Сверка чеков и возвратов','chart'],['local-availability','Наличие и запросы','layers'],['local-recovery','Пилот по согласиям','target'],['local-brief','Отчёт собственника / CSV','file']]},
 {label:'ATELIER R9 · ПЛАТЁЖНЫЙ КОНТРОЛЬ',items:[['payment-vault','Операции и выписки CSV','shield'],['payment-match','Чеки ↔ оплаты','chart'],['bank-close','Зачисления и закрытие','layers'],['exception-room','Расхождения и разбор','target'],['cfo-report','Финансовое досье PDF','file']]},
 {label:'АНАЛИТИЧЕСКИЕ МОДУЛИ',items:MODULES.map((m,i)=>['module:'+i,`${String(i+1).padStart(2,'0')} · ${m[0]}`,i===0?'target':i===7?'chart':'layers'])},
 {label:'ВНЕДРЕНИЕ',items:[['diagnostic','Диагностика за 60 секунд','file'],['presentation','Режим переговоров','shops'],['sources','Источники и 1С','shield']]}
];
const QUESTION_DEFS=[
 {key:'stores',title:'Сколько магазинов в вашей сети?',subtitle:'Подойдёт даже один магазин.',type:'options',options:['1','2–3','4–10','Более 10']},
 {key:'category',title:'Какая категория для вас основная?',subtitle:'Она определит первую выборку для проверки.',type:'options',options:['Одежда','Обувь','Одежда и обувь','Другое']},
 {key:'accounting',title:'Как вы ведёте товарный учёт?',subtitle:'OSMANX не требует отказываться от 1С.',type:'options',options:['1С','Другая система','Таблицы','Пока нет']},
 {key:'trackSizes',title:'Фиксируете запросы на отсутствующие размеры?',subtitle:'Не продажи, а неудовлетворённый спрос.',type:'options',options:['Да','Частично','Нет']},
 {key:'refusal',title:'Выясняете причины ухода без покупки?',subtitle:'Важно отличать ответы покупателя от предположений.',type:'options',options:['Да','Иногда','Нет']},
 {key:'findAcross',title:'Быстро находите товар в другом филиале?',subtitle:'И фиксируете, состоялась ли последующая покупка?',type:'options',options:['Да','Не всегда','Нет']},
 {key:'priority',title:'Какой результат сейчас важнее?',subtitle:'Именно его предложим измерять в пилоте.',type:'options',options:['Выручка','Маржа','Ассортимент','Удержание']}
];
const cached={};
function persist(){try{localStorage.setItem('osmanx-executive-r1',JSON.stringify({decisions:state.decisionState,answers:state.answers,journal:{version:JOURNAL_VERSION,entries:state.r3Journal},r4:{match:state.r4Match,margin:state.r4Margin,portfolio:state.r4Portfolio}}));}catch{}}
function restore(){try{return JSON.parse(localStorage.getItem('osmanx-executive-r1')||'{}')}catch{return {}}}
const recovered=restore();
const state={page:'dashboard',mobileOpen:false,scenario:'balanced',period:'14',store:'all',category:'all',model:'all',size:'all',from:daysAgo(13),to:AS_OF,
 opp:'demand',funnelStage:'request',scene:0,auto:false,slideStart:0,stageStart:0,transferUnits:3,transferProbability:55,transferCost:350,
 moduleIndex:0,lastVerification:null,modelDetail:'JKT-AURA',decisionState:recovered.decisions||{},answers:recovered.answers||{},qStep:0,diagnosticDone:false,presentationPanel:'problem',
 r3Transfer:{sourceStore:'s2',destinationStore:'s1',modelId:AURA.id,size:'L',color:'Графит',units:3,probability:55,costPerUnit:350,fixedCost:0,days:14},r3TransferPlan:null,
 r3Pilot:{controlRequests:'',controlPurchases:'',unitGross:4000,pilotCost:1800},r3Journal:restoreJournal(recovered.journal),r3Selected:null,r3Measure:{},
 r4AuditStream:'sales',r4Match:{reserve:0,probability:55,transferCost:350},r4MatchFilter:'transfer',r4MatchSelected:'',
 r4Margin:{modelId:'JKT-AURA',discount:10,uplift:15,campaignCost:1500},
 r4Portfolio:{budget:15000,capacity:3,costs:{}},r4PortfolioSelected:'rescue',
 calculator:{stores:3,requestsPerStore:20,conversion:12,avgTicket:8900,costPerSale:4900,pilotCost:15000},toast:null};
if(recovered.r4&&typeof recovered.r4==='object'){
 for(const [key,obj] of [['r4Match',recovered.r4.match],['r4Margin',recovered.r4.margin],['r4Portfolio',recovered.r4.portfolio]]){
  if(obj&&typeof obj==='object'&&!Array.isArray(obj)){
   for(const k of Object.keys(state[key]))if(Object.hasOwn(obj,k)&&typeof obj[k]===(k==='modelId'?'string':k==='costs'?'object':'number')&&(k!=='costs'||(obj[k]!==null&&!Array.isArray(obj[k]))))state[key][k]=obj[k];
  }
 }
}
state.r5Data={kind:'sales',text:'',preview:null,validatedSales:[],staged:[]}; // Never persisted: file content stays in RAM only.
state.r5Cohort={weeks:4,minCohort:5};state.r5CohortSelected='';
state.r5Collection={budget:80000,cap:12,reserve:1,leadDays:21,category:'all',seasonFactor:1};state.r5CollectionSelected='';
state.r5Service={sla:120,minSamples:10};state.r5ServiceFocus='all';
state.r5Benchmark={metric:'grossProfit',minDays:7};state.r5BenchmarkFocus='s1';
state.r6Mapping={kind:'sales',text:'',mapping:{},preview:null}; // CSV never persisted or mixed with synthetic metrics.
state.r6Demand={probability:20,handling:250,minGross:0};state.r6DemandSelected='';
state.r6Returns={dimension:'model',minSales:5};state.r6ReturnsSelected='';
state.r6Pilot={baseline:12,lift:5,unitGross:4000,fixedCost:15000,costPerTreatment:50,days:14,seed:'OSMANX-001'};
state.r6Board=(()=>{try{return restoreBoard(JSON.parse(localStorage.getItem('osmanx-r6-executive-board')||'{}'))}catch{return []}})();
state.r6BoardForm={title:'',owner:'Управляющий сети',due:AS_OF,priority:'normal',outcome:''};
state.r6BoardSelected='';state.r6BoardFilter='all';
state.r7Gate={minimumRequests:10,minimumLinked:3,maxStockAgeDays:1};
state.r7Move={reserve:0,probability:55,fixedCost:300,unitCost:250,maxUnits:3,minDemand:1};state.r7MoveSelected='';
state.r7Capital={budget:12000,capacity:3,verificationCost:600,confidence:70};
state.r7Privacy={retentionDays:30,requireConsent:true};
state.r7PrivacyLedger=(()=>{try{return restorePrivacyAudit(JSON.parse(localStorage.getItem('osmanx-r7-privacy-audit')||'{}'))}catch{return []}})();

// R8 raw CSV tables are RAM-only: never put them in localStorage or legacy demo state.
state.r8Workspace=emptyWorkingSet();
state.r8Form={kind:'sales',text:'',errors:[],origin:'local'};
state.r8Ledger={store:'all'};
state.r8Move={reserve:0,probability:70,fixedCost:100,unitCost:100,maxRoutes:30};
state.r8Pilot={testShare:50,lift:5,notificationCost:25,fixedCost:500,maxInvites:100,seed:'OSMANX-R8'};
state.r8Brief={store:'all',status:'needs-review'};
state.r8Audit=(()=>{try{return restoreR8Audit(JSON.parse(localStorage.getItem('osmanx-r8-aggregate-audit')||'{}'))}catch{return []}})();
// R9: imported bank/payment rows and triage remain in memory. Only aggregate signoffs persist.
state.r9Files=r9Empty(state.r8Workspace.version);
state.r9Form={kind:'operations',text:'',errors:[],origin:'local'};
state.r9Options={maxLagDays:3,selected:'',reason:'',evidenceId:'',status:'requires-check'};
state.r9Triage={};
state.r9Signoffs=(()=>{try{return r9RestoreSignoffs(JSON.parse(localStorage.getItem('osmanx-r9-aggregate-signoffs')||'{}'))}catch{return []}})();
let data=buildDataset('balanced'),timer=null;
const root=document.getElementById('app');
const scoped=()=>scopeData(data,{period:state.period,from:state.from,to:state.to,store:state.store,category:state.category,model:state.model,size:state.size});
const demoScope=()=>scopeData(data,{period:14});
function pageTitle(){return state.page==='dashboard'?'Финансовые возможности сети':state.page==='demo'?'Executive Demo':state.page==='decisions'?'Решения на сегодня':state.page==='evidence'?'Аудит показателей':state.page==='transfer-lab'?'Проверка перемещения':state.page==='pilot-lab'?'Проверка пилота':state.page==='journal'?'Журнал решений':state.page==='trust-lab'?'Качество данных':state.page==='demand-match'?'Совпадения спроса':state.page==='margin-stress'?'Экономика скидок':state.page==='portfolio'?'Портфель проверок':state.page==='dossier'?'Досье для собственника':state.page==='data-room'?'Проверка CSV':state.page==='cohort-lab'?'Повторные покупки':state.page==='collection-lab'?'Будущая коллекция':state.page==='service-lab'?'Протокол сервиса':state.page==='branch-lab'?'Сравнение филиалов':state.page==='mapping-lab'?'Сопоставление CSV':state.page==='demand-trace'?'Трассировка спроса':state.page==='returns-risk'?'Диагностика возвратов':state.page==='pilot-design'?'Дизайн пилота':state.page==='action-board'?'Контроль исполнения':state.page==='evidence-gate'?'Готовность доказательств':state.page==='network-rebalance'?'Баланс остатков сети':state.page==='capital-lab'?'Распределение капитала':state.page==='privacy-lab'?'Политика данных':state.page==='executive-brief'?'Досье собственника':state.page==='local-vault'?'Локальные CSV':state.page==='local-ledger'?'Сверка чеков и возвратов':state.page==='local-availability'?'Наличие и запросы':state.page==='local-recovery'?'Контрольная группа':state.page==='payment-vault'?'Реестр оплат и банка':state.page==='payment-match'?'Сверка платёжных документов':state.page==='bank-close'?'Зачисления и касса':state.page==='exception-room'?'Контроль исключений':state.page==='cfo-report'?'Финансовое досье CFO':state.page==='local-brief'?'Досье локальных фактов':state.page==='calculator'?'Финансовый симулятор':state.page==='diagnostic'?'Диагностика бизнеса':state.page==='presentation'?'Презентационный режим':state.page==='sources'?'Источники данных':state.page.startsWith('module:')?MODULES[state.moduleIndex][0]:'Обзор';}
function optionList(options,value){return options.map(([v,l])=>`<option value="${esc(v)}" ${value===v?'selected':''}>${esc(l)}</option>`).join('');}
function renderSidebar(){return `<aside class="sidebar ${state.mobileOpen?'is-open':''}" aria-label="Полная навигация" aria-hidden="${state.mobileOpen?'false':'true'}">
 <div class="drawer-top"><div class="brand"><div class="brand-mark"><span></span><span></span></div><div>${svgLogo}</div></div><button type="button" class="drawer-close" data-action="toggle-menu" aria-label="Закрыть разделы">${icon('close',23)}</button></div>
 <p class="drawer-intro">ATELIER / ИНСТРУМЕНТЫ РЕШЕНИЙ</p>
 <nav class="sidebar-nav" aria-label="Разделы приложения">${NAV.map(group=>`<div class="nav-group"><p class="nav-group-title">${group.label}</p>${group.items.map(([id,label,ico])=>`<button type="button" data-page="${id}" class="nav-link ${state.page===id?'active':''}" tabindex="${state.mobileOpen?'0':'-1'}">${icon(ico,17)}<span>${esc(label)}</span>${state.page===id?'<i></i>':''}</button>`).join('')}</div>`).join('')}</nav>
 <div class="sidebar-bottom"><div class="demo-source"><span class="demo-mini-dot"></span>Демонстрационные данные</div><p>OSMANX WORLD · EXECUTIVE SYSTEM</p></div>
 </aside>${state.mobileOpen?'<button type="button" data-action="toggle-menu" class="mobile-backdrop" aria-label="Закрыть меню"></button>':''}`;}
function activeSourceLabel(){
 const isR9=['payment-vault','payment-match','bank-close','exception-room','cfo-report'].includes(state.page);
 const isR8=['local-vault','local-ledger','local-availability','local-recovery','local-brief'].includes(state.page);
 if(isR9||isR8){const source=inspectWorkingSet(state.r8Workspace);return source.counts.sales>0?(source.example?'УЧЕБНЫЕ CSV (НЕ ДАННЫЕ БИЗНЕСА)':'ЛОКАЛЬНЫЕ CSV (ИСТОЧНИК НЕ ПРОВЕРЕН)'):'ЛОКАЛЬНЫЕ CSV НЕ ЗАГРУЖЕНЫ';}
 return 'ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ';
}
function renderTopbar(){return `<header class="topbar">
 <div class="topbar-left"><button type="button" class="mobile-menu nav-trigger" data-action="toggle-menu" aria-label="Открыть все разделы" aria-expanded="${state.mobileOpen}">${icon('menu',23)}</button><button type="button" class="header-brand" data-page="dashboard"><span class="header-x">X</span><span class="header-brand-text"><b>OSMANX</b><small>RETAIL INTELLIGENCE</small></span></button><span class="header-rule"></span><nav class="header-nav" aria-label="Главная навигация"><button class="${state.page==='dashboard'?'on':''}" data-page="dashboard" type="button">Обзор</button><button class="${state.page==='demo'?'on':''}" data-page="demo" type="button">30 секунд</button><button class="${state.page==='decisions'?'on':''}" data-page="decisions" type="button">Решения</button><button class="${state.page.startsWith('module:')?'on':''}" data-page="module:0" type="button">Аналитика</button></nav></div>
 <div class="topbar-right"><span class="global-demo"><i></i> ${activeSourceLabel()}</span><select class="scenario-select" aria-label="Сценарий демонстрационной сети" data-field="scenario">${optionList(SCENARIOS.map(x=>[x.id,x.name]),state.scenario)}</select><button class="top-demo-btn" type="button" data-page="diagnostic">Проверить магазин ${icon('arrow',15)}</button></div>
 </header>`;}
function renderFilters(){return `<div class="filters">
 <div class="segmented" role="group" aria-label="Период">${[['1','Сегодня'],['7','7 дней'],['14','14 дней'],['30','30 дней'],['90','90 дней'],['custom','Период']].map(([n,v])=>`<button type="button" data-action="period" data-value="${n}" class="${state.period===n?'active':''}">${v}</button>`).join('')}</div>
 ${state.period==='custom'?`<label class="small-field">С <input type="date" data-field="from" value="${state.from}" max="${AS_OF}" /></label><label class="small-field">По <input type="date" data-field="to" value="${state.to}" max="${AS_OF}" /></label>`:''}
 <select aria-label="Филиал" data-field="store">${optionList([['all','Вся сеть'],...STORES.map(x=>[x.id,x.short])],state.store)}</select>
 <select aria-label="Категория" data-field="category">${optionList([['all','Все категории'],...CATEGORIES.map(c=>[c,c])],state.category)}</select>
 <select aria-label="Размер" data-field="size">${optionList([['all','Все размеры'],...SIZES.map(s=>[s,s])],state.size)}</select>
 <select aria-label="Модель" data-field="model" class="model-select">${optionList([['all','Все модели'],...CATALOG.filter(p=>state.category==='all'||p.category===state.category).map(p=>[p.id,p.name])],state.model)}</select>
 </div>`;}
function renderHeading(title,eyebrow,description,buttons=''){return `<section class="page-heading"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p class="heading-sub">${description}</p></div>${buttons?`<div class="heading-actions">${buttons}</div>`:''}</section>`;}
function renderKpi(label,value,extra,type='neutral',sub=''){return `<article class="kpi-card"><div class="kpi-top"><span>${esc(label)}</span><span class="tiny-status ${type}">${type==='up'?icon('trend',14):type==='risk'?icon('activity',14):icon('dots',14)}</span></div><div class="kpi-value">${value}</div><div class="kpi-foot">${extra}${sub?`<small>${sub}</small>`:''}</div></article>`;}
function scopeHint(s){return `Период ${s.from.split('-').reverse().join('.')}–${s.to.split('-').reverse().join('.')} · ${s.filter.store==='all'?'3 филиала':esc(storeName(s.filter.store))}`;}
function dailySeries(sc){const m=new Map();for(const e of sc.sales)m.set(e.date,(m.get(e.date)||0)+e.paidPrice);for(const e of sc.returns)m.set(e.date,(m.get(e.date)||0)-e.refundedPrice);let days=[];const end=new Date(sc.to+'T12:00:00Z'),begin=new Date(sc.from+'T12:00:00Z');for(let d=new Date(begin);d<=end;d.setUTCDate(d.getUTCDate()+1))days.push({date:d.toISOString().slice(0,10),value:(m.get(d.toISOString().slice(0,10))||0)});return days;}
function renderDashboard(){const s=scoped(),t=s.totals,opps=opportunityMetrics(s),chosen=opps.find(o=>o.id===state.opp)||opps[0],series=dailySeries(s);
 return `<section class="luxury-hero" aria-labelledby="luxury-main-title"><div class="luxury-copy"><div class="luxury-kicker"><span class="kicker-line"></span> PRIVATE EXECUTIVE INTELLIGENCE <span>01 / 05</span></div><p class="luxury-page-name">Финансовые возможности вашей сети</p><h1 id="luxury-main-title">Вы знаете, сколько<br>заработали.<br><em>А сколько могли?</em></h1><p class="luxury-lead">Некоторые продажи не попадают в отчёт.<br>Мы покажем, где искать скрытый спрос — и как проверять его в деньгах.</p><div class="luxury-actions"><button class="luxury-primary" data-page="demo" type="button"><span class="button-play">${icon('play',16)}</span><span>Показать за 30 секунд</span>${icon('arrow',18)}</button><button class="luxury-secondary" data-page="diagnostic" type="button">Проверить мой магазин ${icon('arrow',17)}</button></div><div class="luxury-proofline"><span><b>03</b> филиала</span><i></i><span><b>300</b> моделей</span><i></i><span><b>90</b> дней данных</span></div></div><div class="luxury-visual"><div class="luxury-photo" aria-hidden="true"></div><div class="visual-micro">ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ <span>№ 001</span></div><div class="visual-signal"><p class="micro-gold">НАБЛЮДАЕМЫЙ СИГНАЛ</p><strong>${NUMBER(t.requested)} <span>запросов</span></strong><p>на отсутствующие размеры и модели</p><div class="visual-signal-line"></div><div class="signal-foot"><span>${NUMBER(t.confirmedRescueSales)} связанных покупок</span><button data-page="module:0" type="button" aria-label="Изучить невидимый спрос">${icon('arrow',18)}</button></div></div><span class="visual-caption">СТРУКТУРА СПРОСА · 14-ДНЕВНЫЙ ДЕМОНСТРАЦИОННЫЙ СРЕЗ</span></div></section>
 <section class="luxury-verdict" aria-label="Первое финансовое заключение"><div class="verdict-lead"><p class="micro-gold">THE BUSINESS REVELATION</p><h2>Не ещё один отчёт.<br><em>Следующее решение.</em></h2></div><div class="verdict-item"><p>Валовая прибыль по связанным чекам <span class="verdict-status">ФАКТ</span></p><strong>${MONEY(t.confirmedRescueGross)}</strong><small>Семь покупок в полном демосрезе; не доказанный прирост</small></div><div class="verdict-item"><p>Потенциал для проверки <span class="verdict-status subdued">ОЦЕНКА</span></p><strong>${MONEY(t.potential)}</strong><small>Сценарное допущение, требует проверки</small></div><div class="verdict-item"><p>Требуют решения</p><strong>${NUMBER(t.requested-t.confirmedRescueSales)}</strong><small>Запросы без связанной покупки; не потерянные чеки</small></div></section>
 <section class="luxury-section-intro"><div><p class="eyebrow">DEMO DATA / 03 STORES</p><h2>От общей картины — <em>к конкретному действию.</em></h2></div><button data-page="presentation" type="button" class="luxury-quiet-link">Открыть режим переговоров ${icon('arrow',17)}</button></section>
 <div class="luxury-filters"><div class="filter-head"><span>ПЕРИОД / ФИЛИАЛ / АССОРТИМЕНТ</span><span>${esc(scopeHint(s))}</span></div>${renderFilters()}</div>
 <section class="kpi-grid">${renderKpi('Выручка (нетто)',MONEY(t.revenue),'Продажи за период с учётом возвратов')}${renderKpi('Валовая прибыль',MONEY(t.grossProfit),'Нетто-выручка минус себестоимость','up')}${renderKpi('Конверсия посещений',PERCENT(t.conversion),t.conversion===null?'Нет корректной базы для выбранной SKU-группы':'Чеки / агрегированные посещения')}${renderKpi('Повторные покупки',PERCENT(t.repeatShare),'Доля в разрешённой выборке лояльности')}</section>
 <section class="double-grid lower-section"><div class="panel map-panel"><div class="section-title"><div><p class="eyebrow">RETAIL OPPORTUNITY MAP</p><h2>Карта возможностей</h2><p>Один сигнал — одно основание — одно управленческое действие.</p></div><button type="button" class="icon-btn" data-page="decisions" title="Открыть решения" aria-label="Открыть решения">${icon('arrow',18)}</button></div>${opportunityMap(s,state.opp)}<div class="opportunity-info"><div><p class="mini-label">ВЫБРАННЫЙ СИГНАЛ · ${esc(chosen.uncertainty)}</p><h3>${esc(chosen.label)}</h3><p>Источник: ${esc(chosen.source)}. ${NUMBER(chosen.count)} наблюдений. Это ещё не доказанные потери.</p></div><button class="btn-small" type="button" data-page="decisions">${esc(chosen.action)} ${icon('chevron',14)}</button></div></div>
 <div class="panel trend-panel"><div class="section-title"><div><p class="eyebrow">FINANCIAL MOVEMENT</p><h2>Фактическая динамика</h2><p>Выручка из синтетического реестра чеков и возвратов.</p></div><span class="small-badge">${series.length} дней</span></div><div class="chart-big-number">${MONEY(t.revenue)} <small>нетто</small></div>${lineChart(series.map(x=>x.value),{height:184,price:true})}<div class="chart-axis"><span>${s.from.split('-').reverse().slice(0,2).join('.')}</span><span>${s.to.split('-').reverse().slice(0,2).join('.')}</span></div><div class="metrics-stack"><div><span>Себестоимость</span><b>${MONEY(t.costOfGoods)}</b></div><div><span>Валовая маржинальность</span><b>${PERCENT(t.grossMargin)}</b></div><div><span>Сигналы задержки помощи</span><b>${NUMBER(t.serviceRisk)} событий</b></div></div></div></section>
 <section class="r3-bridges" aria-label="Инструменты проверки коммерческих решений"><button data-page="evidence" type="button"><span>01 / ПРОВЕРКА ЦИФР</span><strong>От показателя к чеку</strong>${icon('arrow',17)}</button><button data-page="transfer-lab" type="button"><span>02 / ЛОГИСТИКА</span><strong>Проверить перемещение</strong>${icon('arrow',17)}</button><button data-page="pilot-lab" type="button"><span>03 / ИЗМЕРЕНИЕ</span><strong>Проверить эффект пилота</strong>${icon('arrow',17)}</button><button data-page="journal" type="button"><span>04 / ИСПОЛНЕНИЕ</span><strong>Журнал решений</strong>${icon('arrow',17)}</button></section>
 <section class="r4-dashboard-links" aria-label="Следующие этапы проверки"><div><small>EXECUTIVE EVIDENCE / R4</small><h2>Возможности, которые <em>стоит проверить.</em></h2></div><nav aria-label="Лаборатории решений">${[['trust-lab','Качество данных'],['demand-match','Найти размер'],['margin-stress','Цена и маржа'],['portfolio','Приоритеты'],['dossier','Отчёт PDF']].map(([page,name],i)=>`<button type="button" data-page="${page}"><span>0${i+5}</span>${name}${icon('arrow',15)}</button>`).join('')}</nav></section>
 <section class="luxury-next"><div><p class="micro-gold">THE NEXT MOVE</p><h2>Проверим на вашей сети.</h2><p>Не заменяя 1С. Без обещаний прибыли. С измеримой гипотезой и сроком.</p></div><button class="luxury-primary" data-page="diagnostic" type="button">Начать диагностику ${icon('arrow',18)}</button></section>
 <div class="footer-source">${sourceTag('Факт')} ${scopeHint(s)}. Все сведения синтетические; оценки и гипотезы не равны предотвращённым убыткам.</div>`;
}
function renderStepHeader(){const labels=['Вопрос','Спрос','Проблема','Решение','Проверка'];return `<div class="demo-stepper">${labels.map((l,i)=>`<button type="button" class="demo-step ${i===state.scene?'current':i<state.scene?'done':''}" data-action="scene" data-value="${i}"><span class="step-num">0${i+1}</span><span>${l}</span><i></i></button>`).join('')}</div>`;}
function sceneOne(sc){const t=sc.totals;return `<div class="scene-one"><div class="scene-lead"><p class="overline"><i></i> ОСНОВНОЙ КОММЕРЧЕСКИЙ ВОПРОС</p><h2>Ваш магазин продаёт.<br><em>Но что происходит с покупками,</em><br>которые не состоялись?</h2><p>Первые деньги в отчёте — уже состоявшиеся покупки. Остальное требует измерения и проверки.</p></div><div class="scene-kpis"><div class="scene-big-kpi"><span>Валовая прибыль по связанным продажам</span><strong>${MONEY(t.confirmedRescueGross)}</strong>${sourceTag('Факт')}<small>Без доказательства, что все продажи дополнительные</small></div><div><span>Потенциал к проверке</span><strong>${MONEY(t.potential)}</strong>${sourceTag('Оценка')}</div><div><span>Наблюдаемых запросов</span><strong>${NUMBER(t.requested)}</strong>${sourceTag('Факт')}</div></div></div>`;}
function sceneTwo(sc){const vals=funnelData(sc),t=sc.totals;return `<div class="scene-two"><div class="scene-left"><p class="overline"><i></i> СЦЕНА 02 / НЕВИДИМЫЙ СПРОС</p><h2>${NUMBER(vals[0])} запросов на размер. <em>${NUMBER(vals[3])} связаны с последующими чеками.</em></h2><p>14 дней, три магазина, добровольные обращения. Откройте любую ступень воронки.</p><div class="formula-box"><span>ПРОВЕРЯЕМАЯ ФОРМУЛА</span><strong>${NUMBER(t.confirmedRescueSales)} × (8 900 − 4 900) = <i>${MONEY(t.confirmedRescueGross)}</i></strong><small>Валовая прибыль по ${NUMBER(t.confirmedRescueSales)} подтверждённым чекам. Это не доказанная дополнительная прибыль.</small></div></div><div class="scene-right panel">${funnelMarkup(sc,state.funnelStage)}<div class="micro-stat"><span>Переход «запрос → покупка»</span><b>${PERCENT(safeRatio(vals[3],vals[0]))}</b></div></div></div>`;}
function sceneThree(sc){const jacketRequests=sc.requests.filter(e=>e.modelId===AURA.id),l=jacketRequests.filter(e=>e.size==='L'),stock=data.stock.filter(x=>x.modelId===AURA.id&&x.size==='L'&&x.color==='Графит');return `<div class="scene-three"><div class="scene-left"><p class="overline"><i></i> СЦЕНА 03 / ГДЕ ТЕРЯЕТСЯ СПРОС</p><h2>Нужный размер отсутствует здесь.<br><em>Но есть в другом филиале.</em></h2><p>Пример: техническая куртка AURA, графит. Связаны запросы размера, модель товара и снимок остатков сети.</p><div class="jacket-spec"><div class="jacket-silhouette">${jacketSvg()}</div><div><p class="mini-label">МОДЕЛЬ · JKT-AURA</p><h3>AURA / technical jacket</h3><span>Графит · Размер L · Цена ${MONEY(AURA.price)}</span><b>${NUMBER(l.length)} запросов размера L за 14 дней</b></div></div></div><div class="scene-right"><div class="panel stock-panel"><div class="section-title"><div><p class="eyebrow">LIVE SNAPSHOT · SYNTHETIC</p><h3>Доступность размера L</h3></div><span class="small-badge">Снимок ${AS_OF}</span></div>${STORES.map(store=>{const s=stock.find(x=>x.storeId===store.id);return `<div class="stock-row"><span class="stock-name">${store.short}<small>${store.name}</small></span><span class="stock-pips">${Array.from({length:4},(_,i)=>`<i class="${i<(s?.quantity||0)?'filled':''}"></i>`).join('')}</span><b class="${s?.quantity?'mint':'red'}">${s?.quantity||0} шт.</b></div>`}).join('')}<p class="stock-note">Наличие по снимку требует подтверждения сотрудником перед резервом или перемещением.</p></div><div class="scene-insight">${icon('target',19)} <span>Клиент в филиале №1 может не знать, что размер есть в филиале №2.</span></div></div></div>`;}
function jacketSvg(){return `<svg width="126" height="148" viewBox="0 0 126 148" fill="none" aria-label="Схематичный силуэт куртки"><path d="m40 17 15 6h16l15-6 18 16 18 48-16 9-13-22v65H32V68L19 90 4 81 22 33z" fill="#273648" stroke="#688599" stroke-width="1.5"/><path d="M55 23 63 44l8-21M63 44v89M32 72l-6 61M93 72l7 61" stroke="#8ba7b8" stroke-opacity=".55"/><path d="M55 24 49 18l-8 7 22 29 22-29-8-7-6 6" fill="#192939" stroke="#607888"/><path d="M76 70h10v8H76z" fill="#445f72"/></svg>`;}
function sceneFour(){const stockCount=data.stock.find(x=>x.modelId===AURA.id&&x.size==='L'&&x.color==='Графит'&&x.storeId==='s2')?.quantity||0;const f=forecastTransfer({units:state.transferUnits,probability:state.transferProbability/100,costPerUnit:state.transferCost});return `<div class="scene-four"><div class="scene-left"><p class="overline"><i></i> СЦЕНА 04 / РЕШЕНИЕ, А НЕ ОТЧЁТ</p><h2>Переместить <em>${state.transferUnits} ${state.transferUnits===1?'единицу':'единицы'}</em><br>размера L из филиала №2.</h2><p>Сценарий, а не автоматическое распоряжение складу. Вероятность покупки неизвестна — измените её сами.</p><div class="assumption-fields"><label>Количество <select data-field="transferUnits">${[1,2,3].map(n=>`<option value="${n}" ${state.transferUnits===n?'selected':''}>${n} из ${stockCount}</option>`).join('')}</select></label><label>Вероятность покупки <span class="slider-value">${state.transferProbability}%</span><input type="range" min="5" max="95" step="5" data-field="transferProbability" value="${state.transferProbability}"/></label><label>Перемещение / единица <span>${MONEY(state.transferCost)}</span><input type="range" min="0" max="1200" step="50" data-field="transferCost" value="${state.transferCost}"/></label></div></div><div class="scene-right"><div class="panel projection-panel"><p class="eyebrow">WHAT-IF · НЕ ФАКТ</p><span>Ожидаемый эффект после логистики</span><strong class="projection-amount ${f.net<0?'red':''}">${MONEY(f.net)}</strong><div class="projection-bars"><div><span>Ожидаемая валовая прибыль</span><b>${MONEY(f.gross)}</b></div><div><span>Стоимость перемещения</span><b>− ${MONEY(f.logistics)}</b></div><div><span>Ожидаемые продажи</span><b>${f.expectedSales.toLocaleString('ru-RU',{maximumFractionDigits:2})} ед.</b></div></div><div class="projection-caveat">Основание: 3 ед. в филиале №2, валовая прибыль 4 000 ₽/шт. Уверенность: низкая до пилота и проверки доступности.</div><button class="btn-primary full" data-action="verify-transfer" type="button">Проверить расчёт ${icon('arrow',16)}</button>${state.lastVerification?`<div class="verified-scenario" role="status"><b>Расчёт проверен</b><span>Стоимость логистики учтена: ${MONEY(state.lastVerification.logistics)}. Прогноз: ${MONEY(state.lastVerification.net)} при вероятности ${state.transferProbability}%.</span><small>Это моделирование, не команда складу и не доказанный результат.</small></div>`:''}</div></div></div>`;}
function sceneFive(){return `<div class="scene-five"><div class="closing-mark">OX / INTELLIGENCE</div><p class="overline"><i></i> СЦЕНА 05 / ОТ ДЕМОНСТРАЦИИ К ВАШЕМУ БИЗНЕСУ</p><h2>Это демонстрационные данные.<br><em>А что происходит в ваших магазинах?</em></h2><p>Не обещаем рост прибыли. Предлагаем определить, каких данных не хватает, и провести ограниченную проверку.</p><div class="scene-final-actions"><button class="btn-primary large" type="button" data-page="diagnostic">Проверить мой магазин ${icon('arrow',18)}</button><button class="btn-outline large" type="button" data-page="module:0">Изучить 10 источников прибыли</button></div><span class="bottom-quote">1С остаётся учётной системой. OSMANX помогает дополнять события и проверять управленческие гипотезы.</span></div>`;}
function renderDemo(){const s=demoScope(),scenes=[sceneOne,sceneTwo,sceneThree,sceneFour,sceneFive];return `<section class="demo-page"><div class="demo-topline"><div><p class="eyebrow">EXECUTIVE DEMO / 30 SECONDS</p><h1>30 секунд, чтобы увидеть <em>невидимое.</em></h1></div><div class="demo-controls"><button type="button" class="btn-outline" data-action="restart-demo">${icon('left',15)} С начала</button><button type="button" class="btn-primary" data-action="toggle-auto">${icon(state.auto?'pause':'play',16)} ${state.auto?'Пауза':'Автопоказ'}</button></div></div>
 ${renderStepHeader()}<div class="demo-screen"><div class="scene-counter">${String(state.scene+1).padStart(2,'0')} / 05 <span>•</span> ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ</div>${scenes[state.scene](s)}<div class="scene-bottom"><span>Ключевой принцип: факт ≠ оценка ≠ гипотеза ≠ прогноз</span><div class="scene-nav"><button type="button" data-action="prev-scene" ${state.scene===0?'disabled':''}>${icon('left',17)} Назад</button><button type="button" data-action="next-scene">${state.scene===4?'Повторить':'Далее'} ${icon('arrow',17)}</button></div></div></div><div class="demo-progress"><span id="demo-progress-fill" style="width:${100*DURATIONS.slice(0,state.scene).reduce((a,b)=>a+b,0)/30000}%"></span></div>
 <div class="demo-footnote"><span>0–5 сек · Вопрос</span><span>5–11 сек · Спрос</span><span>11–18 сек · Проблема</span><span>18–25 сек · Решение</span><span>25–30 сек · Проверка</span></div></section>`;}
function metric(label,value,caption,status){return `<div class="module-stat"><span>${label}</span><strong>${value}</strong><small>${caption}</small>${status?sourceTag(status):''}</div>`;}
function countsBy(items,key){const m=new Map();items.forEach(x=>m.set(x[key]??'Не указан',(m.get(x[key]??'Не указан')||0)+1));return [...m].sort((a,b)=>b[1]-a[1]).slice(0,7).map(([label,value])=>({label:String(label),value}));}
function stepCards(source,cost,decision,result){return `<div class="five-step-grid">${[['01','СИГНАЛ',source],['02','ДОКАЗАТЕЛЬСТВА','Данные ниже, доступен просмотр конкретных событий'],['03','ФИНАНСОВЫЙ ВЫВОД',cost],['04','РЕШЕНИЕ',decision],['05','РЕЗУЛЬТАТ',result]].map(([n,title,desc])=>`<div class="method-step"><span>${n} / ${title}</span><p>${desc}</p></div>`).join('')}</div>`;}
function moduleContent(index,s){const t=s.totals,margin=t.unitsSold?t.grossProfit/t.unitsSold:0,catFilter=state.category==='all'?'все категории':state.category;
 if(index===0)return {stats:[metric('Запросы',NUMBER(s.requests.length),'Фиксированные события','Факт'),metric('Найдено решение',NUMBER(s.requests.filter(x=>x.solutionFound).length),'По записям продавцов','Факт'),metric('Подписались на уведомление',NUMBER(s.requests.filter(x=>x.consent).length),'Добровольное согласие','Факт'),metric('Чек после запроса',NUMBER(t.confirmedRescueSales),MONEY(t.confirmedRescueGross)+' валовой прибыли','Факт')],
  viz:funnelMarkup(s,state.funnelStage),detail:rawTable(s.requests,[['Дата','date'],['Филиал',x=>storeName(x.storeId)],['Модель',x=>product(x.modelId).name],['Размер','size'],['Решение',x=>x.solutionFound?'Найдено':'Не найдено'],['Покупка',x=>x.purchased?'Подтверждена':'Нет']]), finance:`${MONEY(t.confirmedRescueGross)} валовой прибыли в связанных чеках; прирост относительно обычного сценария не доказан.`,result:'Отслеживать согласия, найденные варианты, покупки и отдельную контрольную группу.'};
 if(index===1){const lose=s.fittings.filter(x=>!x.purchased);return {stats:[metric('Примерки',NUMBER(s.fittings.length),'Факт наблюдения','Факт'),metric('Без покупки',NUMBER(lose.length),'Без приписывания причин','Факт'),metric('Конверсия примерок',PERCENT(safeRatio(s.fittings.filter(x=>x.purchased).length,s.fittings.length)),'Не равно конверсии визитов','Факт'),metric('Указана причина',NUMBER(lose.filter(x=>x.reason).length),'Незаполненные причины отдельно','Факт')],viz:`<h3>Зафиксированные причины отказов</h3>${barViz(countsBy(lose,'reason'),180)}<p class="fine-note">Причины фиксировались со слов посетителя. Незаполненная причина не заменяется догадкой системы.</p>`,detail:rawTable(s.fittings,[['Дата','date'],['Филиал',x=>storeName(x.storeId)],['Модель',x=>product(x.modelId).name],['Размер','size'],['Исход',x=>x.purchased?'Покупка':'Без покупки'],['Причина',x=>x.reason||'Не установлена']]),finance:'Не подтверждён: нет измеренной причинной связи между примеркой, консультацией и дополнительной покупкой.',result:'Измерить долю ответов по причинам и повторить сравнение в контрольной группе.'};}
 if(index===2){const flagged=s.audits.filter(x=>x.status!=='Проверено');return {stats:[metric('SKU × филиал × размер',NUMBER(s.stock.length),'Снимок остатков','Факт'),metric('Остаток, единиц',NUMBER(t.inventoryUnits),'По данным текущего снимка','Факт'),metric('Спорных сверок',NUMBER(flagged.length),'Требуется физическая проверка','Факт'),metric('Денежные потери','Не установлены','Нет подтверждённого факта несостоявшихся продаж')],viz:`<div class="evidence-flag"><span class="risk-flag">${icon('info',18)} Проверка</span><h3>Учётный остаток ≠ физическая доступность</h3><p>Уточните место хранения, наличие резерва и фактическую доступность каждой спорной позиции.</p></div>`,detail:rawTable(s.audits,[['Дата','date'],['Модель',x=>product(x.modelId).name],['Филиал',x=>storeName(x.storeId)],['Размер','size'],['Учёт','expected'],['Факт','observed'],['Статус','status']]),finance:'Недостаточно данных для расчёта стоимости проблемы: нужны подтверждённая сверка и события отказа от покупки.',result:'Протоколировать расхождения и повторные проверки в том же магазине.'};}
 if(index===3){const found=s.requests.filter(x=>x.solutionFound);return {stats:[metric('Запросы с решением',NUMBER(found.length),'Не все превратились в чек','Факт'),metric('Связанные покупки',NUMBER(t.confirmedRescueSales),'Чеки с ID обращения','Факт'),metric('Перемещения',NUMBER(s.transfers.length),'Все зарегистрированные статусы','Факт'),metric('Ожидаемый эффект',MONEY(forecastTransfer({units:state.transferUnits,probability:state.transferProbability/100,costPerUnit:state.transferCost}).net),'Сценарная модель','Прогноз')],viz:sceneFour(),detail:rawTable(s.transfers,[['Дата','date'],['Модель',x=>product(x.modelId).name],['Откуда',x=>storeName(x.fromStoreId)],['Куда',x=>storeName(x.toStoreId)],['Количество','quantity'],['Статус','status']]),finance:'Реальный прирост нужно сравнить с контрольным периодом; резерв и перемещение сами по себе не продажа.',result:'Проверить успешность резерва, доставку, чек, расходы на перемещение и возврат.'};}
 if(index===4){const arr=s.traffic;const a=arr.filter(x=>x.variant==='А'),b=arr.filter(x=>x.variant==='Б');const conv=(rows)=>safeRatio(rows.reduce((z,x)=>z+x.visits,0),rows.reduce((z,x)=>z+x.passers,0));return {stats:[metric('Прохожие',NUMBER(arr.reduce((x,y)=>x+y.passers,0)),'Агрегированные наблюдения','Факт'),metric('Входы',NUMBER(arr.reduce((x,y)=>x+y.visits,0)),'Агрегированные наблюдения','Факт'),metric('Вариант А',PERCENT(conv(a)),'Входы / прохожие','Факт'),metric('Вариант Б',PERCENT(conv(b)),'Входы / прохожие','Факт')],viz:`<div class="compare-variants"><div><span>ВАРИАНТ A</span><strong>${PERCENT(conv(a))}</strong><div class="variant-track"><i style="width:${(conv(a)||0)*200}%"></i></div></div><div><span>ВАРИАНТ Б</span><strong>${PERCENT(conv(b))}</strong><div class="variant-track"><i style="width:${(conv(b)||0)*200}%"></i></div></div></div><p class="fine-note">Разница между вариантами может объясняться погодой, сезоном и днями недели. Причинность не установлена.</p>`,detail:rawTable(arr,[['Дата','date'],['Филиал',x=>storeName(x.storeId)],['Вариант','variant'],['Прохожие','passers'],['Входы','visits'],['Доля входов',x=>PERCENT(safeRatio(x.visits,x.passers))]]),finance:'Увеличение валовой прибыли от изменения витрины не рассчитано: нет рандомизации и достоверной причинной оценки.',result:'Сопоставить дни недели, погоду, акции и предварительно заданные критерии эксперимента.'};}
 if(index===5){const late=s.assistance.filter(x=>x.responseSeconds>240),times=s.assistance.map(x=>x.responseSeconds).sort((a,b)=>a-b);const median=times.length?times[Math.floor(times.length/2)]:null;return {stats:[metric('Просьбы о помощи',NUMBER(s.assistance.length),'Только добровольные QR-события','Факт'),metric('Медиана ответа',median===null?'—':NUMBER(median)+' c','Время реакции','Факт'),metric('Более 4 минут',NUMBER(late.length),'Порог диагностики 240 секунд','Факт'),metric('Доказанная потеря','Не установлена','Неизвестно, привела ли задержка к отказу')],viz:`<h3>Типы обращений</h3>${barViz(countsBy(s.assistance,'requestType'),190)}<p class="fine-note">Время измеряется по событиям системы, а не по персональному слежению за покупателями.</p>`,detail:rawTable(s.assistance,[['Дата','date'],['Филиал',x=>storeName(x.storeId)],['Запрос','requestType'],['Ожидание, сек','responseSeconds'],['Результат',x=>x.resolved?'Завершено':'Не завершено']]),finance:'Корреляция времени ответа и конверсии не доказывает причину. Нет достаточных данных для точной суммы убытка.',result:'Установить SLA, измерить долю обращений в срок и отследить повторный замер.'};}
 if(index===6){const members=new Map();s.sales.filter(x=>x.memberId).forEach(x=>members.set(x.memberId,(members.get(x.memberId)||0)+1));const repeats=[...members.values()].filter(x=>x>1).length;return {stats:[metric('Участники с чеками',NUMBER(members.size),'Участники программы лояльности','Факт'),metric('Покупали повторно',NUMBER(repeats),'Не все покупатели сети','Факт'),metric('Доля повторных',PERCENT(t.repeatShare),'По наблюдаемой выборке','Факт'),metric('Выручка участников',MONEY(s.sales.filter(x=>x.memberId).reduce((a,x)=>a+x.paidPrice,0)),'До возвратов','Факт')],viz:`<div class="loyalty-circles"><div class="loyalty-donut" style="--share:${((t.repeatShare||0)*100).toFixed(1)}%"><span>${PERCENT(t.repeatShare)}</span></div><div><h3>Ограниченная когорта</h3><p>Мы видим только тех, кто добровольно участвует в программе лояльности. Остальных посетителей автоматически не идентифицируем.</p></div></div>`,detail:rawTable([...members].map(([id,count])=>({id,count})).sort((a,b)=>b.count-a.count),[['Псевдоним участника','id'],['Покупок за период','count']]),finance:'Невозможно вывести дополнительную прибыль без базовой группы и затрат на удержание.',result:'Измерить повторы по когортам регистрации и сравнить динамику контрольных групп.'};}
 if(index===7){const discounted=s.sales.filter(x=>x.discount),income=s.sales.reduce((a,x)=>a+x.paidPrice,0),full=s.sales.reduce((a,x)=>a+product(x.modelId).price,0);return {stats:[metric('Выручка после возвратов',MONEY(t.revenue),'По синтетическим чекам','Факт'),metric('Валовая прибыль',MONEY(t.grossProfit),'Выручка − себестоимость','Факт'),metric('Скидочных продаж',NUMBER(discounted.length),'В выбранной выборке','Факт'),metric('Сумма скидок',MONEY(full-income),'Разница с базовой ценой','Факт')],viz:`<div class="margin-waterfall"><div><span>Валовые продажи</span><b>${MONEY(t.grossSales)}</b></div><div><span>Возвраты</span><b>− ${MONEY(s.returns.reduce((a,x)=>a+x.refundedPrice,0))}</b></div><div><span>Себестоимость</span><b>− ${MONEY(t.costOfGoods)}</b></div><div class="last"><span>Валовая прибыль</span><b>${MONEY(t.grossProfit)}</b></div></div><p class="fine-note">Сумма скидок — не автоматически потерянная прибыль: без скидки часть покупок могла не состояться.</p>`,detail:rawTable(s.sales.filter(x=>x.discount),[['Дата','date'],['Модель',x=>product(x.modelId).name],['Цена, ₽','paidPrice'],['Себестоимость, ₽','cost'],['Скидка',x=>PERCENT(x.discount)]]),finance:'Рассчитана фактическая валовая прибыль. Эффект отмены скидок — гипотеза, зависящая от эластичности спроса.',result:'Проводить ограниченные ценовые эксперименты с контролем объёма и валовой прибыли.'};}
 if(index===8){const sizeRows=countsBy([...s.requests,...s.preorders],'size');return {stats:[metric('Запросы размеров',NUMBER(s.requests.length),'Сигнал спроса','Факт'),metric('Добровольные предзаказы',NUMBER(s.preorders.length),'Не равно продажам','Факт'),metric('Из них с задатком',NUMBER(s.preorders.filter(x=>x.depositPaid).length),'Синтетические события','Факт'),metric('Опросы предпочтений',NUMBER(s.preferences.length),'Добровольные ответы','Факт')],viz:`<h3>Спрос по размерам</h3>${barViz(sizeRows,188)}<p class="fine-note">Намерение купить и предзаказ сами по себе не подтверждают будущую выручку.</p>`,detail:rawTable(s.preorders,[['Дата','date'],['Филиал',x=>storeName(x.storeId)],['Модель',x=>product(x.modelId).name],['Размер','size'],['Задаток',x=>x.depositPaid?'Зафиксирован':'Нет'],['Статус','status']]),finance:'Недостаточно данных для уверенной закупочной прибыли: требуются конверсия намерений и риск непроданного остатка.',result:'Выбрать короткую коллекцию для теста, ограничить закупку и измерить выкуп.'};}
 if(index===9){const returnValue=s.returns.reduce((a,x)=>a+x.refundedPrice,0);return {stats:[metric('Возвраты',NUMBER(s.returns.length),'Связаны с исходными чеками','Факт'),metric('Возвращённая выручка',MONEY(returnValue),'Сумма возвратов','Факт'),metric('Доля по количеству',PERCENT(safeRatio(s.returns.length,s.sales.length)),'Ориентир: продажи текущего периода','Оценка'),metric('Повторяющиеся причины',NUMBER(countsBy(s.returns,'reason').length),'Группы причин','Факт')],viz:`<h3>Причины оформленных возвратов</h3>${barViz(countsBy(s.returns,'reason'),185)}<p class="fine-note">Доля по количеству — ориентир, так как возврат в периоде может относиться к более ранней продаже.</p>`,detail:rawTable(s.returns,[['Дата','date'],['Филиал',x=>storeName(x.storeId)],['Модель',x=>product(x.modelId).name],['Размер','size'],['Сумма, ₽','refundedPrice'],['Причина','reason']]),finance:'Размер возврата отражён в нетто-выручке; из причины возврата нельзя автоматически вывести предотвращаемую потерю.',result:'Сверить размерные сетки, партии и сообщения о дефектах, затем повторно измерить частоту.'};}
}
function renderModule(index){const m=MODULES[index],s=scoped(),content=moduleContent(index,s);return `${renderHeading(m[0],`ANALYTICS / MODULE ${String(index+1).padStart(2,'0')}`,m[2],`<button class="btn-outline" data-page="presentation" type="button">${icon('play',16)} Показать владельцу</button><button class="btn-primary" data-action="track-decision" data-decision="${index}" type="button">${icon('check',16)} ${state.decisionState[index]?'План зафиксирован':'Взять в проверку'}</button>`)}${renderFilters()}
 <div class="module-alert"><span class="module-alpha">${m[1]}</span><p>Сигнал → Доказательства → Финансовый расчёт → Решение → Результат</p><span class="synthetic-text">Демонстрационные данные</span></div>
 <section class="module-stat-grid">${content.stats.join('')}</section>
 <section class="double-grid module-main"><div class="panel"><div class="section-title"><div><p class="eyebrow">DEEP DIVE / EVIDENCE</p><h2>Что показывают наблюдения</h2></div>${sourceTag('Факт')}</div>${content.viz}</div><div class="panel"><div class="section-title"><div><p class="eyebrow">DIRECTOR'S ACTION</p><h2>Решение и измерение</h2></div>${icon('target',20)}</div><div class="recommendation-detail"><span>КОНКРЕТНОЕ СЛЕДУЮЩЕЕ ДЕЙСТВИЕ</span><h3>${m[4]}</h3><p>${content.finance}</p><div class="decision-cost"><span>Источники данных</span><b>${m[3]}</b></div><div class="decision-cost"><span>Что измерять</span><b>${content.result}</b></div><div class="fine-note">${state.decisionState[index]?`План внесён в список решений · ${state.decisionState[index]}`:'Это предложение проверить гипотезу, не команда выполнить изменение.'}</div><button class="btn-primary full" type="button" data-action="track-decision" data-decision="${index}">${state.decisionState[index]?'Обновить план проверки':'Добавить в план проверки'} ${icon('arrow',15)}</button></div></div></section>
 ${stepCards(`${content.stats[0].match(/<strong>(.*?)<\/strong>/)?.[1]||'—'} наблюдений из выбранной выборки`,content.finance,m[4],content.result)}
 <section class="panel data-table-panel"><div class="section-title"><div><p class="eyebrow">EVENT LEDGER / SOURCE OF TRUTH</p><h2>Исходные события</h2><p>Не агрегированные обещания: даты, филиалы, модели и статусы.</p></div><span class="small-badge">${s.from} — ${s.to}</span></div>${content.detail}</section>
 <div class="module-pagination"><button data-page="module:${(index+9)%10}" type="button">${icon('left',16)} ${MODULES[(index+9)%10][0]}</button><span>${index+1} / 10</span><button data-page="module:${(index+1)%10}" type="button">${MODULES[(index+1)%10][0]} ${icon('arrow',16)}</button></div>`;}
function renderDecisions(){const s=scoped(), rec=recommendations(s),dataArr=[...rec];return `${renderHeading('Что бы я изменил <em>сегодня</em>','DECISION INTELLIGENCE · 10','Только проверяемые приоритеты. Там, где данных недостаточно, система не придумывает денежный эффект.',`<button class="btn-primary" data-page="diagnostic" type="button">Начать диагностику ${icon('arrow',16)}</button>`)}${renderFilters()}<div class="decisions-list">${dataArr.map((o,i)=>`<article class="decision-card"><div class="priority-number">0${i+1}</div><div class="decision-body"><p class="eyebrow">${esc(o.source)} / ${esc(o.uncertainty)}</p><h2>${esc(o.action)}</h2><p>${NUMBER(o.count)} наблюдений → ${esc(o.experiment)}.</p><div class="decision-tags"><span>Ответственный: управляющий филиалом</span><span>Измерение: до / после + контроль</span></div>${state.decisionState['opp-'+o.id]?`<p class="decision-saved">${icon('check',14)} Внесено в план · ${state.decisionState['opp-'+o.id]}</p>`:''}</div><div class="decision-side"><span>СЦЕНАРНЫЙ ЭФФЕКТ</span><strong>${o.estimate==null?'Недостаточно данных':MONEY(o.estimate)}</strong><small>${esc(o.uncertainty)} · расходы на внедрение нужно уточнить</small><button type="button" class="btn-small" data-action="track-opp" data-id="${o.id}">${state.decisionState['opp-'+o.id]?'Обновить':'В план'} ${icon('arrow',15)}</button></div></article>`).join('')}</div><div class="footer-source">Прогноз не может считаться финансовым фактом до измерения результата. Степень уверенности зависит от качества источников.</div>`;}
function numberInput(key,label,suffix='',min=0,max=10000000){const val=state.calculator[key];return `<label class="calc-input"><span>${label}</span><div><input aria-label="${esc(label)}" type="number" min="${min}" max="${max}" step="${key==='conversion'?1:1}" data-calc="${key}" value="${val}"/><b>${suffix}</b></div></label>`;}
function renderCalculator(){const c=state.calculator,f=pilotForecast({...c,conversion:c.conversion/100});return `${renderHeading('Возможность — <em>не обещание.</em>','FINANCIAL MODEL / WHAT-IF','Собственник меняет параметры. Все результаты пересчитываются из его предположений.',`<button class="btn-outline" type="button" data-action="reset-calc">Сбросить параметры</button>`)}<div class="calculation-layout"><div class="panel calculator-input-panel"><p class="eyebrow">ВХОДНЫЕ ПРЕДПОЛОЖЕНИЯ</p><h2>Настройте вашу сеть</h2><div class="calc-fields">${numberInput('stores','Магазины','шт.',1,1000)}${numberInput('requestsPerStore','Запросов в период на магазин','шт.',0,100000)}${numberInput('conversion','Конверсия обращений в покупку','%',0,100)}${numberInput('avgTicket','Средняя цена продажи','₽',0,10000000)}${numberInput('costPerSale','Себестоимость единицы','₽',0,10000000)}${numberInput('pilotCost','Стоимость пилота','₽',0,100000000)}</div><p class="fine-note">Неизмеренные параметры — ваши допущения. Исходный сценарий не означает достижимый результат.</p></div><div class="projection-summary"><p class="eyebrow">СЦЕНАРНЫЙ РАСЧЁТ</p><span>Возможная валовая прибыль после пилотных затрат</span><strong class="${f.net<0?'red':''}">${MONEY(f.net)}</strong><div class="summary-divider"></div><div class="summary-row"><span>Потенциальных покупок</span><b>${f.potentialPurchases.toLocaleString('ru-RU',{maximumFractionDigits:1})}</b></div><div class="summary-row"><span>Выручка по сценарию</span><b>${MONEY(f.revenue)}</b></div><div class="summary-row"><span>Валовая прибыль</span><b>${MONEY(f.gross)}</b></div><div class="summary-row"><span>Расходы на пилот</span><b>− ${MONEY(c.pilotCost)}</b></div><div class="summary-row highlighted"><span>Покрытие затрат пилота</span><b>${f.paybackRatio===null?'—':f.paybackRatio.toFixed(2)+'×'}</b></div><div class="warning-note">${icon('info',17)} Не учтены налоги, дополнительные операционные расходы и покупки, которые произошли бы без системы.</div><button class="btn-primary full" type="button" data-page="diagnostic">Подготовить план измерения ${icon('arrow',16)}</button></div></div>`;}
function renderDiagnostic(){const q=QUESTION_DEFS[state.qStep],plan=diagnosticPlan(state.answers);return `${renderHeading('Начните с <em>проверки.</em>','60-SECOND DIAGNOSTIC','Семь вопросов. Никаких выдуманных диагнозов и обязательной регистрации.',`<button class="btn-outline" type="button" data-page="demo">Вернуться к демо</button>`)}<div class="diagnostic-frame">${!state.diagnosticDone?`<div class="diagnostic-form"><div class="diagnostic-top"><p>ВОПРОС ${String(state.qStep+1).padStart(2,'0')} / 07</p><div class="diag-progress">${QUESTION_DEFS.map((_,i)=>`<i class="${i<=state.qStep?'on':''}"></i>`).join('')}</div></div><h2>${q.title}</h2><p>${q.subtitle}</p><div class="diag-options">${q.options.map(x=>`<button type="button" class="diag-option ${state.answers[q.key]===x?'selected':''}" data-action="answer" data-key="${q.key}" data-value="${esc(x)}"><span class="radio-dot"></span>${esc(x)} ${state.answers[q.key]===x?icon('check',18):''}</button>`).join('')}</div><div class="diag-actions"><button class="btn-outline" type="button" data-action="prev-q" ${state.qStep===0?'disabled':''}>${icon('left',15)} Назад</button><button class="btn-primary" type="button" data-action="next-q" ${!state.answers[q.key]?'disabled':''}>${state.qStep===6?'Составить план':'Следующий вопрос'} ${icon('arrow',16)}</button></div></div>`:`<div class="diagnostic-result"><div class="result-icon">${icon('check',26)}</div><p class="eyebrow">ПЕРВИЧНЫЙ ПЛАН ПРОВЕРКИ ГОТОВ</p><h2>Три направления, которые стоит проверить <em>в вашей сети.</em></h2><p>Это индивидуальный план сбора доказательств, а не диагноз и не обещание прибыли.</p><div class="plan-list">${plan.map((p,i)=>`<div class="plan-line"><span>0${i+1}</span><div><h3>${p.title}</h3><p>${p.detail}</p></div></div>`).join('')}</div><div class="result-actions"><button class="btn-primary" type="button" data-action="pdf">${icon('download',16)} Скачать отчёт PDF</button><button class="btn-outline" type="button" data-action="restart-diagnostic">Пройти заново</button></div><p class="fine-note">В отчёте сохраняются только выбранные ответы и рекомендации; данные не отправляются на сервер.</p></div>`}</div>`;}
function renderPresentation(){const scene={problem:['Какие покупки не состоялись?','60 запросов размера за 14 дней — факт наблюдений, а не 60 гарантированно потерянных продаж.','Доказательство: обращения покупателей с моделью, размером, датой и филиалом.'],effect:['Деньги с проверяемым происхождением','28 000 ₽ — валовая прибыль по 7 чекам, связанным с обращениями.','Формула: 7 × (8 900 − 4 900). Не доказано, что без системы покупатели не приобрели бы товар.'],implementation:['Начать можно без замены 1С','Нужны выгрузка SKU и остатков, фиксация обращений, правила согласия покупателей и контрольные критерии пилота.','Рекомендация: пилот 14 дней, замерить реальные запросы, найденные товары, чеки, логистику и расходы.']}[state.presentationPanel];return `<section class="presentation"><div class="presentation-top"><span>OSMANX / EXECUTIVE PRESENTATION</span><span>Демонстрационные данные</span></div><div class="presentation-body"><p class="eyebrow">ПРЕЗЕНТАЦИЯ ДЛЯ СОБСТВЕННИКА</p><h1>${scene[0]}</h1><p class="presentation-explain">${scene[1]}</p><div class="presentation-number">${state.presentationPanel==='effect'?'28 000 ₽':state.presentationPanel==='problem'?'60':'14 дней'}<small>${state.presentationPanel==='effect'?'ВАЛОВАЯ ПРИБЫЛЬ ПО 7 ЧЕКАМ':state.presentationPanel==='problem'?'ЗАПРОСОВ НА РАЗМЕР':'ПИЛОТ С ИЗМЕРИМЫМИ КРИТЕРИЯМИ'}</small></div><p class="presentation-proof">${scene[2]}</p></div><div class="presentation-footer"><div class="presentation-actions"><button class="${state.presentationPanel==='problem'?'selected':''}" data-action="presentation-panel" data-value="problem" type="button">Показать причину</button><button class="${state.presentationPanel==='effect'?'selected':''}" data-action="presentation-panel" data-value="effect" type="button">Финансовый эффект</button><button class="${state.presentationPanel==='implementation'?'selected':''}" data-action="presentation-panel" data-value="implementation" type="button">Что нужно для внедрения</button></div><button class="btn-primary" type="button" data-page="diagnostic">Начать диагностику ${icon('arrow',16)}</button></div></section>`;}
function renderSources(){const rows=[
 ['Выручка, чек, SKU, цена и себестоимость','Учёт / POS / 1С','Да, при корректной выгрузке','Факт по документам'],
 ['Остатки филиалов и межфилиальные документы','Учёт / 1С','Да, требуется сверка','Факт учёта'],
 ['Запрос отсутствующего размера','Дополнительное событие магазина','Не всегда','Факт обращения'],
 ['Примерка и озвученная причина отказа','Добровольная фиксация','Не всегда','Факт / неизвестно'],
 ['Согласие на уведомления','Отдельное согласие покупателя','Нет без фиксации согласия','Факт согласия'],
 ['Повторные покупки','Чеки + разрешённая лояльность','При наличии идентификатора','Наблюдаемая когорта'],
 ['Витрина → вход в магазин','Агрегированные счётчики','При наличии счётчиков','Корреляция'],
 ['Продажа произошла благодаря системе','Контролируемый пилот / сравнение','Нельзя автоматически','Гипотеза до проверки']
];return `${renderHeading('1С остаётся. <em>Добавляются вопросы.</em>','DATA ORIGINS / TRUST','Учётная система может быть источником фактов. OSMANX объединяет их с новыми событиями и помогает проверить решения.')}<section class="panel source-panel"><div class="section-title"><div><p class="eyebrow">DATA SOURCE MATRIX</p><h2>Что откуда действительно известно</h2></div>${icon('shield',23)}</div><div class="table-scroll"><table><thead><tr><th>Показатель</th><th>Источник</th><th>Можно получить из учёта?</th><th>Качество вывода</th></tr></thead><tbody>${rows.map(r=>`<tr>${r.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div><div class="integration-note">${icon('lock',19)} <div><strong>1С не подключена в этой демонстрации.</strong><p>Здесь нет фиктивных API, имитации реальных синхронизаций или пользовательских коммерческих данных. Для подключения нужны согласование формата выгрузки, права и контроль качества.</p></div></div></section><section class="source-cards"><div><p class="eyebrow">ФАКТ</p><h3>Подтверждаемое событие</h3><p>Чек, зарегистрированный запрос, физическая сверка, возврат или согласие.</p></div><div><p class="eyebrow">ОЦЕНКА</p><h3>Модель с параметрами</h3><p>Считаем сумму и раскрываем допущения, но не называем предотвращённым убытком.</p></div><div><p class="eyebrow">ГИПОТЕЗА</p><h3>Вопрос для пилота</h3><p>Проверяем причинность контролируемым измерением и отслеживанием расходов.</p></div></section>`;}
function renderFooter(){return `<footer class="app-footer"><span>© OSMANX WORLD · RETAIL INTELLIGENCE / EXECUTIVE EDITION</span><span>${activeSourceLabel()} · По состоянию на ${AS_OF}</span></footer>`;}
function render(){root.innerHTML=`${renderSidebar()}<div class="workspace"><a href="#osmanx-main" class="r3-skip">Перейти к содержимому</a>${renderTopbar()}<main id="osmanx-main" class="main-content" tabindex="-1">${state.page==='dashboard'?renderDashboard():state.page==='demo'?renderDemo():state.page.startsWith('module:')?renderModule(state.moduleIndex):state.page==='decisions'?renderDecisions():state.page==='calculator'?renderCalculator():state.page==='diagnostic'?renderDiagnostic():state.page==='presentation'?renderPresentation():state.page==='evidence'?renderEvidencePage(data,scoped()):state.page==='transfer-lab'?renderTransferPage(data,scoped(),state.r3Transfer,state.r3TransferPlan):state.page==='pilot-lab'?renderPilotPage(data,scoped(),state.r3Pilot):state.page==='journal'?renderJournalPage(scoped(),state.r3Journal,state.r3Selected,state.r3Measure):state.page==='trust-lab'?renderTrustPage(data,scoped(),state.r4AuditStream):state.page==='demand-match'?renderMatchPage(data,scoped(),state.r4Match,state.r4MatchFilter,state.r4MatchSelected):state.page==='margin-stress'?renderMarginPage(data,scoped(),state.r4Margin):state.page==='portfolio'?renderPortfolioPage(data,scoped(),state.r4Portfolio,state.r4PortfolioSelected):state.page==='dossier'?renderDossierPage(data,scoped(),state.r4Portfolio):state.page==='data-room'?renderR5DataRoom(state.r5Data):state.page==='cohort-lab'?renderR5Cohorts(data,scoped(),state.r5Cohort,state.r5CohortSelected):state.page==='collection-lab'?renderR5Collection(data,scoped(),state.r5Collection,state.r5CollectionSelected):state.page==='service-lab'?renderR5Service(scoped(),state.r5Service,state.r5ServiceFocus):state.page==='branch-lab'?renderR5Benchmark(data,scoped(),state.r5Benchmark,state.r5BenchmarkFocus):state.page==='mapping-lab'?renderR6Mapping(state.r6Mapping):state.page==='demand-trace'?renderR6Demand(data,scoped(),state.r6Demand,state.r6DemandSelected):state.page==='returns-risk'?renderR6Returns(data,scoped(),state.r6Returns,state.r6ReturnsSelected):state.page==='pilot-design'?renderR6Pilot(scoped(),state.r6Pilot):state.page==='action-board'?renderR6Board(state.r6Board,state.scenario,state.r6BoardForm,state.r6BoardSelected,state.r6BoardFilter):state.page==='evidence-gate'?renderR7Gate(data,scoped(),state.r7Gate):state.page==='network-rebalance'?renderR7Rebalance(data,scoped(),state.r7Move,state.r7MoveSelected):state.page==='capital-lab'?renderR7Capital(data,scoped(),state.r7Capital,state.r7Move):state.page==='privacy-lab'?renderR7Privacy(data,scoped(),state.r7Privacy,state.r7PrivacyLedger):state.page==='executive-brief'?renderR7Brief(data,scoped(),{gate:state.r7Gate,rebalance:state.r7Move,capital:state.r7Capital,privacy:state.r7Privacy},state.r6Board,state.r7PrivacyLedger):state.page==='local-vault'?renderR8Intake(state.r8Workspace,state.r8Form):state.page==='local-ledger'?renderR8Ledger(state.r8Workspace,state.r8Ledger):state.page==='local-availability'?renderR8Availability(state.r8Workspace,state.r8Move):state.page==='local-recovery'?renderR8Recovery(state.r8Workspace,state.r8Pilot):state.page==='local-brief'?renderR8Brief(state.r8Workspace,{...state.r8Brief,availability:state.r8Move,pilot:state.r8Pilot},state.r8Audit):state.page==='payment-vault'?renderR9Vault(state.r8Workspace,state.r9Files,state.r9Form):state.page==='payment-match'?renderR9Matching(state.r8Workspace,state.r9Files):state.page==='bank-close'?renderR9Bank(state.r8Workspace,state.r9Files,state.r9Options):state.page==='exception-room'?renderR9Exceptions(state.r8Workspace,state.r9Files,state.r9Options,state.r9Triage):state.page==='cfo-report'?renderR9Cfo(state.r8Workspace,state.r9Files,state.r9Options,state.r9Triage,state.r9Signoffs):renderSources()}</main>${state.page==='presentation'?'':renderFooter()}</div>${state.toast?`<div class="toast" role="status">${icon('check',17)} ${esc(state.toast)}<button data-action="dismiss-toast" aria-label="Закрыть" type="button">${icon('close',15)}</button></div>`:''}`;document.title=`${pageTitle()} — OSMANX Retail Intelligence`;}
function stopAuto(){state.auto=false;if(timer){clearInterval(timer);timer=null;}}
const DURATIONS=[5000,6000,7000,7000,5000];
function startAuto(){stopAuto();state.auto=true;state.stageStart=performance.now();timer=setInterval(()=>{const elapsed=performance.now()-state.stageStart;const progress=(DURATIONS.slice(0,state.scene).reduce((a,b)=>a+b,0)+Math.min(elapsed,DURATIONS[state.scene]))/30000;const el=document.getElementById('demo-progress-fill');if(el)el.style.width=`${(100*progress).toFixed(2)}%`;if(elapsed>=DURATIONS[state.scene]){if(state.scene===4){stopAuto();render();}else{state.scene++;state.stageStart=performance.now();render();}}},75);render();}
function goto(page){stopAuto();state.page=page;state.mobileOpen=false;state.lastVerification=null;if(page.startsWith('module:')){state.moduleIndex=Number(page.split(':')[1])||0;state.page='module:'+state.moduleIndex;}if(page==='demo')state.scene=0;render();if(window.location&&window.location.hash!=='#'+page)window.location.hash='#'+page;window.scrollTo?.({top:0,behavior:'instant'});}
function sceneChange(n){const wasPlaying=state.auto;stopAuto();state.scene=Math.max(0,Math.min(4,n));render();if(wasPlaying)startAuto();}
function toast(message){state.toast=message;render();}
function r4DownloadCsv(name,contents){
 const blob=new Blob([contents],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');
 a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),15000);
}
function r4AddJournal(title,type,ids){
 const j=newJournalEntry(state.r3Journal,{title,scenarioId:state.scenario,type,evidenceIds:[...new Set(ids.filter(Boolean))].slice(0,80)});
 state.r3Journal=j.entries;state.r3Selected=j.created.id;persist();goto('journal');
}
function r6SaveBoard(){try{localStorage.setItem('osmanx-r6-executive-board',JSON.stringify({version:BOARD_VERSION,items:state.r6Board}));return true;}catch(e){state.toast='Локальное сохранение недоступно: '+e.message;return false;}}
function r6Create(title,type,evidenceIds=[]){
 try{const next=createBoardItem(state.r6Board,{title,owner:'Управляющий филиалом',due:AS_OF,evidenceIds:evidenceIds.filter(Boolean).slice(0,50),scenario:state.scenario,type});
  state.r6Board=next.items;state.r6BoardSelected=next.created.id;state.r6BoardForm.outcome='';r6SaveBoard();goto('action-board');}
 catch(e){toast(e.message);}
}
function r7InputChange(element){
 const key=element.dataset.r7Field,raw=element.value,num=raw===''?null:Number(raw);
 const update=()=>{
  const target={'gateRequests':['r7Gate','minimumRequests'],'gateLinked':['r7Gate','minimumLinked'],'gateAge':['r7Gate','maxStockAgeDays'],
   'moveReserve':['r7Move','reserve'],'moveProbability':['r7Move','probability'],'moveFixed':['r7Move','fixedCost'],'moveUnitCost':['r7Move','unitCost'],
   'moveUnits':['r7Move','maxUnits'],'moveDemand':['r7Move','minDemand'],'capitalBudget':['r7Capital','budget'],'capitalCapacity':['r7Capital','capacity'],
   'capitalAudit':['r7Capital','verificationCost'],'capitalConfidence':['r7Capital','confidence'],'privacyRetention':['r7Privacy','retentionDays']}[key];
  if(key==='privacyConsent')state.r7Privacy.requireConsent=raw==='required';
  else if(target)state[target[0]][target[1]]=num;
 };
 if(element.tagName==='INPUT')preserveRerender(element,update);else{update();render();}
}
function r6InputChange(element){const key=element.dataset.r6Field,raw=element.value,n=raw===''?null:Number(raw);
 const change=()=>{
  if(key.startsWith('map:')){state.r6Mapping.mapping[key.slice(4)]=raw;state.r6Mapping.preview=null;}
  else if(key==='mappingKind'){state.r6Mapping={kind:raw,text:'',mapping:{},preview:null};}
  else if(key==='demandProbability')state.r6Demand.probability=n;
  else if(key==='demandHandling')state.r6Demand.handling=n;
  else if(key==='demandMinGross')state.r6Demand.minGross=n;
  else if(key==='returnDimension'){state.r6Returns.dimension=raw;state.r6ReturnsSelected='';}
  else if(key==='returnMin')state.r6Returns.minSales=n;
  else if(key==='pilotBaseline')state.r6Pilot.baseline=n;
  else if(key==='pilotLift')state.r6Pilot.lift=n;
  else if(key==='pilotUnitGross')state.r6Pilot.unitGross=n;
  else if(key==='pilotFixed')state.r6Pilot.fixedCost=n;
  else if(key==='pilotPerRequest')state.r6Pilot.costPerTreatment=n;
  else if(key==='pilotDays')state.r6Pilot.days=n;
  else if(key==='pilotSeed')state.r6Pilot.seed=raw;
  else if(key==='boardOwner')state.r6BoardForm.owner=raw;
  else if(key==='boardFilter'){state.r6BoardFilter=raw;state.r6BoardSelected='';}
 };
 if(element.tagName==='INPUT')preserveRerender(element,change);else{change();render();}
}
function handleClick(event){const target=event.target.closest('button[data-action],button[data-page]');if(!target||target.disabled)return;
 if(target.dataset.page){goto(target.dataset.page);return;}
 const a=target.dataset.action,value=target.dataset.value;
 if(a==='r9-examples'){
  let next=emptyWorkingSet(),err='';for(const kind of ['sales','returns','requests','stock']){const result=acceptCsv(next,kind,r8Example()[kind],{origin:'example'});if(!result.accepted){err=result.errors.join('; ');break;}next=result.workspace;}
  if(err){toast(err);return;}let files=r9Empty(next.version);
  for(const kind of ['operations','settlements']){const result=r9AcceptCsv(next,files,kind,r9Example()[kind],{origin:'example'});if(!result.accepted){toast(result.errors.join('; '));return;}files=result.workspace;}
  state.r8Workspace=next;state.r9Files=files;state.r9Triage={};state.r9Form={kind:'operations',text:'',errors:[],origin:'local'};toast('Приняты учебные чеки, оплаты и банковские пакеты (не данные бизнеса).');
 }
 else if(a==='r9-accept'){
  const f=state.r9Form,result=r9AcceptCsv(state.r8Workspace,state.r9Files,f.kind,f.text,{origin:f.origin});
  if(!result.accepted){state.r9Form.errors=result.errors;render();return;}
  state.r9Files=result.workspace;state.r9Triage={};state.r9Form={...f,text:'',errors:[],origin:'local'};toast('Платёжный CSV принят: '+result.inspected+' строк.');
 }
 else if(a==='r9-clear'){state.r9Files=r9Empty(state.r8Workspace.version);state.r9Triage={};state.r9Form={kind:'operations',text:'',errors:[],origin:'local'};toast('Операции и выписки R9 удалены из оперативной памяти.');}
 else if(a==='r9-operations-sample'){r4DownloadCsv('OSMANX_R9_OPERATIONS_EXAMPLE.csv',r9Example().operations);}
 else if(a==='r9-settlements-sample'){r4DownloadCsv('OSMANX_R9_SETTLEMENTS_EXAMPLE.csv',r9Example().settlements);}
 else if(a==='r9-matching-csv'){
  const audit=r9Reconcile(state.r8Workspace,state.r9Files);
  if(audit.valid)r4DownloadCsv('OSMANX_R9_RECONCILIATION.csv',r8Csv([['Документ','Тип','Филиал','Необходимо','По операциям','Разница','Статус'],...audit.rows.map(x=>[x.ref,x.kind,x.storeId,x.required,x.received,x.difference,x.status])]));
 }
 else if(a==='r9-bank-csv'){const b=r9Settlements(state.r8Workspace,state.r9Files,state.r9Options);if(b.valid)r4DownloadCsv('OSMANX_R9_BANK_BATCHES.csv',r9BankCsv(b));}
 else if(a==='r9-daily-csv'){const r=r9Reconcile(state.r8Workspace,state.r9Files),d=r9DailyClose(state.r8Workspace,state.r9Files,r);if(d.valid)r4DownloadCsv('OSMANX_R9_DAY_CLOSE.csv',r9DayCsv(d));}
 else if(a==='r9-cases-csv'){const r=r9Reconcile(state.r8Workspace,state.r9Files),b=r9Settlements(state.r8Workspace,state.r9Files,state.r9Options),c=r9Cases(r,b,state.r9Triage);if(c.valid)r4DownloadCsv('OSMANX_R9_ANONYMOUS_EXCEPTIONS.csv',r9CasesCsv(c));}
 else if(['r9-triage-start','r9-triage-close','r9-triage-reset','r9-triage-reopen'].includes(a)){
  const r=r9Reconcile(state.r8Workspace,state.r9Files),b=r9Settlements(state.r8Workspace,state.r9Files,state.r9Options),c=r9Cases(r,b,state.r9Triage);
  const chosen=c.items.find(x=>x.key===state.r9Options.selected)||c.items[0];if(!chosen)return;
  try{const next=a==='r9-triage-start'||a==='r9-triage-reopen'?'checking':a==='r9-triage-close'?'resolved':'new';
   state.r9Triage=r9Transition(state.r9Triage,c,chosen.key,next,state.r9Options.reason,state.r9Options.evidenceId);state.r9Options.selected=chosen.key;state.r9Options.reason='';state.r9Options.evidenceId='';toast('Статус расхождения обновлён. Операций в банке не выполнено.');}
  catch(e){toast(e.message);}
 }
 else if(a==='r9-cfo-csv'){const p=r9Pack(state.r8Workspace,state.r9Files,state.r9Triage,state.r9Options);if(p.valid)r4DownloadCsv('OSMANX_R9_CFO_REPORT.csv',r9ReportCsv(p));}
 else if(a==='r9-cfo-pdf'){try{const p=r9Pack(state.r8Workspace,state.r9Files,state.r9Triage,state.r9Options);exportR9Pdf(p,{status:state.r9Options.status});toast('Реальный PDF сформирован локально.');}catch(e){toast(e.message);}}
 else if(a==='r9-cfo-save'){try{const p=r9Pack(state.r8Workspace,state.r9Files,state.r9Triage,state.r9Options);const items=r9AggregateSignoff(state.r9Signoffs,p,{status:state.r9Options.status});localStorage.setItem('osmanx-r9-aggregate-signoffs',JSON.stringify({version:1,items}));state.r9Signoffs=items;toast('Сохранён только агрегированный акт, не исходные строки.');}catch(e){toast('Не сохранено: '+e.message);}}
 else if(a==='r9-signoff-csv'){r4DownloadCsv('OSMANX_R9_AGGREGATE_SIGNOFFS.csv',r9SignoffCsv(state.r9Signoffs));}
 else if(a==='r9-history-clear'){state.r9Signoffs=[];try{localStorage.removeItem('osmanx-r9-aggregate-signoffs')}catch{}toast('Агрегированная история очищена.');}
 else if(a==='r8-kind'){if(!Object.hasOwn(R8_KINDS,value))return;state.r8Form={kind:value,text:'',errors:[],origin:'local'};render();}
 else if(a==='r8-sample-one'){state.r8Form.text=r8Example()[state.r8Form.kind];state.r8Form.origin='example';state.r8Form.errors=[];render();}
 else if(a==='r8-sample-all'){
  let next=emptyWorkingSet(),errors=[];for(const kind of ['sales','returns','requests','stock']){const result=acceptCsv(next,kind,r8Example()[kind],{origin:'example'});if(!result.accepted){errors=result.errors;break;}next=result.workspace;}
  if(!errors.length){state.r8Workspace=next;state.r9Files=r9Empty(next.version);state.r9Triage={};state.r8Form={kind:'sales',text:'',errors:[],origin:'local'};toast('Учебный CSV-набор принят. Это не данные вашего бизнеса.');}else{state.r8Form.errors=errors;render();}
 }
 else if(a==='r8-accept'){
  const x=state.r8Form,result=acceptCsv(state.r8Workspace,x.kind,x.text,{origin:x.origin});
  if(!result.accepted){state.r8Form.errors=result.errors;render();return;}
  state.r8Workspace=result.workspace;state.r9Files=r9Empty(result.workspace.version);state.r9Triage={};state.r8Form.errors=[];state.r8Form.text='';state.r8Form.origin='local';toast('Принято '+result.inspected+' строк; версия локального набора '+result.workspace.version+'.');
 }
 else if(a==='r8-clear'){state.r8Workspace=emptyWorkingSet();state.r9Files=r9Empty();state.r9Triage={};state.r8Form={kind:'sales',text:'',errors:[],origin:'local'};toast('Локальные исходные строки удалены из памяти. Демоданные не изменены.');}
 else if(a==='r8-ledger-csv'){const r=salesLedger(state.r8Workspace,state.r8Ledger);if(r.valid)r4DownloadCsv('OSMANX_R8_LOCAL_RECEIPTS.csv',ledgerCsv(r));}
 else if(a==='r8-move-csv'){const r=availabilityPlan(state.r8Workspace,state.r8Move);if(r.valid)r4DownloadCsv('OSMANX_R8_SCENARIO_ROUTES.csv',availabilityCsv(r));}
 else if(a==='r8-move-task'){const r=availabilityPlan(state.r8Workspace,state.r8Move);if(!r.routes?.length){toast('Нет допустимых сценариев');return;}r6Create('Проверить текущие остатки и экономику '+r.routes.length+' маршрутов локального CSV','r8-local-stock',[]);}
 else if(a==='r8-pilot-csv'){const r=recoveryPilot(state.r8Workspace,state.r8Pilot);if(r.valid)r4DownloadCsv('OSMANX_R8_CONSENT_PILOT.csv',recoveryCsv(r));}
 else if(a==='r8-pilot-task'){const r=recoveryPilot(state.r8Workspace,state.r8Pilot);if(!r.candidates){toast('Нет обращений с согласием');return;}r6Create('Утвердить контроль и тест, без автоматической отправки сообщений','r8-local-pilot',[]);}
 else if(a==='r8-brief-csv'){const r=r8OwnerBrief(state.r8Workspace,{...state.r8Brief,availability:state.r8Move,pilot:state.r8Pilot},state.r8Audit);if(r.valid)r4DownloadCsv('OSMANX_R8_LOCAL_OWNER_BRIEF.csv',r8BriefCsv(r));}
 else if(a==='r8-brief-pdf'){try{const r=r8OwnerBrief(state.r8Workspace,{...state.r8Brief,availability:state.r8Move,pilot:state.r8Pilot},state.r8Audit);exportR8BriefPdf(r,{status:state.r8Brief.status});toast('PDF сформирован локально.');}catch(err){toast('Ошибка экспорта: '+err.message);}}
 else if(a==='r8-brief-save'){
  try{const brief=r8OwnerBrief(state.r8Workspace,{...state.r8Brief,availability:state.r8Move,pilot:state.r8Pilot},state.r8Audit),next=appendR8Audit(state.r8Audit,brief,{status:state.r8Brief.status});
   localStorage.setItem('osmanx-r8-aggregate-audit',JSON.stringify({version:R8_AUDIT_VERSION,items:next}));state.r8Audit=next;toast('Сохранён только агрегированный итог, без событий и контактов.');
  }catch(err){toast('Не удалось сохранить: '+err.message);}
 }
 else if(a==='r8-audit-csv'){r4DownloadCsv('OSMANX_R8_AGGREGATE_AUDIT.csv',r8AuditCsv(state.r8Audit));}
 else if(a==='r8-audit-clear'){state.r8Audit=[];try{localStorage.removeItem('osmanx-r8-aggregate-audit');}catch{}toast('Локальная история отчётов очищена.');}
 else if(a==='r7-gate-csv'){const r=decisionEvidenceGate(data,scoped(),state.r7Gate);if(r.valid)r4DownloadCsv('OSMANX_R7_EVIDENCE_GATE.csv',gateCsv(r));}
 else if(a==='r7-gate-task'){const g=decisionEvidenceGate(data,scoped(),state.r7Gate);if(g.valid)r6Create(g.ready?'Подтвердить источники перед запуском пилота':'Исправить блокировки достоверности: '+g.blockers.join(', '),'r7-evidence',g.evidenceIds);else toast('Сначала исправьте параметры');}
 else if(a==='r7-move-select'){state.r7MoveSelected=value;render();}
 else if(a==='r7-move-csv'){const r=networkRebalance(data,scoped(),state.r7Move);if(r.valid)r4DownloadCsv('OSMANX_R7_NETWORK_REBALANCE.csv',rebalanceCsv(r));}
 else if(a==='r7-move-task'){const r=networkRebalance(data,scoped(),state.r7Move),row=r.routes.find(x=>x.id===state.r7MoveSelected)||r.routes[0];if(row)r6Create('Физически проверить '+row.product+' '+row.size+': '+row.sourceStore+' → '+row.destinationStore,'r7-rebalance',row.evidenceIds);else toast('Нет допустимого сценария');}
 else if(a==='r7-capital-csv'){const r=capitalAllocation(data,scoped(),state.r7Capital,networkRebalance(data,scoped(),state.r7Move));if(r.valid)r4DownloadCsv('OSMANX_R7_BUDGET_SCENARIOS.csv',capitalCsv(r));}
 else if(a==='r7-capital-task'){const r=capitalAllocation(data,scoped(),state.r7Capital,networkRebalance(data,scoped(),state.r7Move));if(r.selected.length)r6Create('Согласовать бюджет пилота '+r.totalSpend+' ₽ и контроль результата','r7-capital',r.sourceRequestIds);else toast('Выберите допустимый бюджетный сценарий');}
 else if(a==='r7-privacy-preview'){render();}
 else if(a==='r7-privacy-apply'){const p=privacySimulation(data,scoped(),state.r7Privacy);if(!p.valid){toast(p.errors.join('; '));return;}state.r7PrivacyLedger=appendPrivacyAudit(state.r7PrivacyLedger,p,{scenario:state.scenario});try{localStorage.setItem('osmanx-r7-privacy-audit',JSON.stringify({version:PRIVACY_LEDGER_VERSION,entries:state.r7PrivacyLedger}));}catch(err){toast('Локальное сохранение недоступно: '+err.message);return;}toast('Симуляция политики сохранена локально. Реальные данные не удалялись.');}
 else if(a==='r7-privacy-csv'){const r=privacySimulation(data,scoped(),state.r7Privacy);if(r.valid)r4DownloadCsv('OSMANX_R7_ANONYMOUS_COUNTS.csv',anonymousPrivacyCsv(r));}
 else if(a==='r7-brief-pdf'){try{const r=executiveBrief(data,scoped(),{gate:state.r7Gate,rebalance:state.r7Move,capital:state.r7Capital,privacy:state.r7Privacy,board:state.r6Board});exportR7BriefPdf(r);toast('PDF-досье сформировано локально.');}catch(err){toast('Ошибка PDF: '+err.message);}}
 else if(a==='r7-brief-csv'){const r=executiveBrief(data,scoped(),{gate:state.r7Gate,rebalance:state.r7Move,capital:state.r7Capital,privacy:state.r7Privacy,board:state.r6Board});if(r.valid)r4DownloadCsv('OSMANX_R7_EXECUTIVE_BRIEF.csv',briefCsv(r));}
 else if(a==='r7-brief-task'){const r=executiveBrief(data,scoped(),{gate:state.r7Gate,rebalance:state.r7Move,capital:state.r7Capital,privacy:state.r7Privacy,board:state.r6Board});if(r.valid)r6Create(r.nextActions[0],'r7-brief',r.gate.evidenceIds);}
 else if(a==='r6-mapping-example'){
   const k=state.r6Mapping.kind,raw=sampleCsv(k).replace(/^\uFEFF/,'');
   const aliases={id:'Номер',date:'Дата',asOf:'Дата среза',storeId:'Магазин',modelId:'Артикул',size:'Размер',paidPrice:'Сумма оплаты',cost:'Себестоимость',saleId:'Чек',refundedPrice:'Сумма возврата',reversedCost:'Сторно себестоимости',quantity:'Количество',color:'Цвет'};
   const table=raw.split(/\r?\n/).filter(Boolean).map(x=>x.split(';').map(v=>v.replace(/^"|"$/g,'')));
   table[0]=table[0].map(x=>aliases[x]||x);for(let i=1;i<table.length;i++){const storeColumn=table[0].indexOf('Магазин');if(storeColumn>=0&&table[i][storeColumn]==='s1')table[i][storeColumn]='Центральный';}
   state.r6Mapping.text=exportRowsCsv(table);state.r6Mapping.mapping=inspectMapping(state.r6Mapping.text,k).mapping;state.r6Mapping.preview=null;render();
 }
 else if(a==='r6-mapping-verify'){const x=state.r6Mapping;state.r6Mapping.preview=mapAndValidate(x.text,x.kind,x.mapping,state.r5Data.validatedSales);render();}
 else if(a==='r6-mapping-export'){const x=state.r6Mapping.preview;if(x?.valid)r4DownloadCsv('OSMANX_R6_MAPPED_'+x.kind+'.csv',x.normalizedCsv);}
 else if(a==='r6-demand-select'){state.r6DemandSelected=value;render();}
 else if(a==='r6-demand-csv'){const r=traceLostDemand(data,scoped(),state.r6Demand);if(r.valid)r4DownloadCsv('OSMANX_R6_DEMAND_TRACE.csv',exportRowsCsv([['Обращение','Дата','Филиал','Модель','Размер','Статус','Связанный чек','Валовая прибыль по чеку','Сценарная оценка','ID оснований'],...r.rows.map(x=>[x.id,x.date,x.storeId,x.modelId,x.size,x.classification,x.linkedSaleId||'',x.observedGross??'',x.grossScenario??'',x.evidenceIds.join(' | ')])]));}
 else if(a==='r6-demand-task'){const r=traceLostDemand(data,scoped(),state.r6Demand),x=r.rows.find(y=>y.id===state.r6DemandSelected)||r.rows.find(y=>y.classification!=='confirmed');if(x&&r.valid)r6Create('Сверить причину отсутствия покупки '+x.product+' / '+x.size,'r6-demand',x.evidenceIds);else toast('Нужен корректный запрос');}
 else if(a==='r6-return-select'){state.r6ReturnsSelected=value;render();}
 else if(a==='r6-returns-csv'){const r=analyzeReturns(data,scoped(),state.r6Returns);if(r.valid)r4DownloadCsv('OSMANX_R6_RETURNS.csv',exportRowsCsv([['Группа','Чеков','Возвратов','Доля','Wilson мин','Wilson макс','Сторно валовой прибыли','ID оснований'],...r.rows.map(x=>[x.label,x.receipts,x.returned,x.rate??'',x.interval?.[0]??'',x.interval?.[1]??'',x.observedGrossReversed,x.ids.join(' | ')])]));}
 else if(a==='r6-return-task'){const r=analyzeReturns(data,scoped(),state.r6Returns),x=r.rows.find(y=>y.key===state.r6ReturnsSelected)||r.rows.find(y=>y.sufficient);if(x?.sufficient)r6Create('Проверить причины возвратов '+x.label,'r6-return',x.ids);else toast('Недостаточный объём событий');}
 else if(a==='r6-pilot-csv'){const r=designPilot(scoped(),state.r6Pilot);if(r.valid)r4DownloadCsv('OSMANX_R6_PILOT_PLAN.csv',assignmentsCsv(r));}
 else if(a==='r6-pilot-task'){const r=designPilot(scoped(),state.r6Pilot);if(r.valid)r6Create('Согласовать протокол пилота: '+r.totalRequired+' обращений, '+r.days+' дней','r6-pilot',r.assignments.map(x=>x.requestId).slice(0,50));else toast('Исправьте параметры эксперимента');}
 else if(a==='r6-board-select'){state.r6BoardSelected=value;state.r6BoardForm.outcome='';render();}
 else if(a==='r6-board-export'){const s=boardSummary(state.r6Board,state.scenario);if(s.total)r4DownloadCsv('OSMANX_R6_ACTIONS.csv',boardCsv(s.list));}
 else if(a==='r6-board-create'){
  try{const r=createBoardItem(state.r6Board,{...state.r6BoardForm,scenario:state.scenario});state.r6Board=r.items;state.r6BoardSelected=r.created.id;state.r6BoardForm.title='';state.r6BoardForm.outcome='';r6SaveBoard();render();}catch(e){toast(e.message);}
 }
 else if(['r6-board-start','r6-board-review','r6-board-back','r6-board-close'].includes(a)){
  const selected=boardSummary(state.r6Board,state.scenario).list.find(x=>x.id===state.r6BoardSelected)||boardSummary(state.r6Board,state.scenario).list[0];
  if(!selected){toast('Выберите задачу');return;}
  const next={'r6-board-start':'working','r6-board-review':'review','r6-board-back':'working','r6-board-close':'closed'}[a];
  try{state.r6Board=advanceBoard(state.r6Board,selected.id,next,{outcome:state.r6BoardForm.outcome});state.r6BoardForm.outcome='';r6SaveBoard();render();}catch(e){toast(e.message);}
 }
 else if(a==='toggle-menu'){state.mobileOpen=!state.mobileOpen;render();}
 else if(a==='r3-transfer-check'){state.r3TransferPlan=planTransfer(data,state.r3Transfer);render();}
 else if(a==='r3-transfer-save'){
  const p=state.r3TransferPlan;
  if(!p?.valid){state.toast='Сначала подтвердите условия сценария';render();return;}
  const created=newJournalEntry(state.r3Journal,{title:`Проверить перемещение ${p.units} ед. ${product(p.modelId).name} ${p.size}: ${p.sourceStore} → ${p.destinationStore}`,scenarioId:state.scenario,type:'transfer',evidenceIds:[p.stockSourceId,...p.evidenceIds]});
  state.r3Journal=created.entries;state.r3Selected=created.created.id;persist();goto('journal');
 }
 else if(a==='r4-audit-stream'){state.r4AuditStream=value;render();}
 else if(a==='r4-audit-csv'){r4DownloadCsv('OSMANX_R4_DATA_QUALITY.csv',auditCsv(auditEvidence(data,scoped())));}
 else if(a==='r4-match-filter'){state.r4MatchFilter=value;render();}
 else if(a==='r4-match-open'){state.r4MatchSelected=value;render();}
 else if(a==='r4-match-csv'){r4DownloadCsv('OSMANX_R4_DEMAND_MATCH.csv',matchingCsv(matchDemand(data,scoped(),state.r4Match)));}
 else if(a==='r4-match-journal'){
  const row=matchDemand(data,scoped(),state.r4Match).matches.find(x=>x.requestId===target.dataset.id);
  if(!row){toast('Сначала проверьте источник и наличие');return;}
  r4AddJournal(`Проверить ${row.model} ${row.size}: ${row.sourceStore} → ${row.destinationStore}`,'r4-matching',[row.requestId,row.sourceStockId]);
 }
 else if(a==='r4-margin-journal'){
  const row=discountStress(data,scoped(),state.r4Margin);
  if(!row.valid||!row.validBaseline){toast('Нужны корректные продажи для проверки скидки');return;}
  r4AddJournal(`Проверить скидку ${state.r4Margin.discount}% на ${row.product.name}`,'r4-margin',[...row.receipts,...row.returnIds]);
 }
 else if(a==='r4-portfolio-open'){state.r4PortfolioSelected=value;render();}
 else if(a==='r4-portfolio-csv'){r4DownloadCsv('OSMANX_R4_PRIORITY_PORTFOLIO.csv',portfolioCsv(prioritizePortfolio(data,scoped(),state.r4Portfolio)));}
 else if(a==='r4-portfolio-journal'){
  const row=prioritizePortfolio(data,scoped(),state.r4Portfolio).candidates.find(x=>x.id===target.dataset.id);
  if(!row||!row.hasEvidence||row.invalidCost){toast('Недостаточно доказательств для пилота');return;}
  r4AddJournal(`${row.title} · ${row.owner}`,'r4-portfolio-'+row.id,row.evidenceIds);
 }
 else if(a==='r4-dossier-csv'){r4DownloadCsv('OSMANX_R4_DECISION_DOSSIER.csv',dossierCsv(dossierSnapshot(data,scoped(),state.r4Portfolio)));}
 else if(a==='r4-dossier-pdf'){try{exportDossierPdf(dossierSnapshot(data,scoped(),state.r4Portfolio));state.toast='PDF сформирован локально. Это не реальный аудит.';render();}catch(err){toast('PDF не сформирован: '+err.message);}}
 else if(a==='r5-sample'){state.r5Data.text=sampleCsv(state.r5Data.kind);state.r5Data.preview=null;render();}
 else if(a==='r5-review'){state.r5Data.preview=reviewImport(state.r5Data.text,state.r5Data.kind,state.r5Data.validatedSales);render();}
 else if(a==='r5-clear'){state.r5Data.text='';state.r5Data.preview=null;state.r5Data.validatedSales=[];state.r5Data.staged=[];render();}
 else if(a==='r5-stage'){
  const checked=state.r5Data.preview;
  if(!checked?.valid){toast('Есть ошибки проверки CSV');return;}
  if(checked.kind==='sales')state.r5Data.validatedSales=checked.rows;
  state.r5Data.staged=checked.rows;state.r5Data.text='';state.r5Data.preview=null;
  toast('Проверенный пакет сохранён только в памяти вкладки, не в 1С и не в демоаналитике.');
 }
 else if(a==='r5-export'){const r=state.r5Data.preview;if(r?.valid)r4DownloadCsv('OSMANX_R5_VALIDATED_'+r.kind+'.csv',reviewedCsv(r));}
 else if(a==='r5-cohort-select'){state.r5CohortSelected=value;render();}
 else if(a==='r5-cohort-csv'){const r=retentionCohorts(data,scoped(),state.r5Cohort);if(r.valid)r4DownloadCsv('OSMANX_R5_COHORTS.csv',cohortCsv(r));}
 else if(a==='r5-cohort-journal'){
  const r=retentionCohorts(data,scoped(),state.r5Cohort),selected=r.cohorts.find(x=>x.start===state.r5CohortSelected)||r.cohorts[0];
  if(!selected){toast('Недостаточно связанных чеков');return;}
  r4AddJournal('Проверить повторные покупки: когорта '+selected.start,'r5-retention',selected.firstReceiptIds);
 }
 else if(a==='r5-collection-open'){state.r5CollectionSelected=value;render();}
 else if(a==='r5-collection-csv'){const r=collectionPlan(data,scoped(),state.r5Collection);if(r.valid)r4DownloadCsv('OSMANX_R5_COLLECTION_PLAN.csv',collectionCsv(r));}
 else if(a==='r5-collection-journal'){
  const r=collectionPlan(data,scoped(),state.r5Collection),selected=r.rows.find(x=>x.key===state.r5CollectionSelected)||r.rows[0];
  if(!selected||selected.orderUnits<1){toast('Нет подтверждённых оснований для пилота');return;}
  r4AddJournal(`Проверить закупку ${selected.product}, ${selected.size}, ${selected.storeId}, ${selected.orderUnits} ед.`,'r5-collection',selected.ids);
 }
 else if(a==='r5-service-open'){state.r5ServiceFocus=value;render();}
 else if(a==='r5-service-csv'){const r=serviceHealth(scoped(),state.r5Service);if(r.valid)r4DownloadCsv('OSMANX_R5_SERVICE.csv',serviceCsv(r));}
 else if(a==='r5-service-journal'){
  const r=serviceHealth(scoped(),state.r5Service),selected=r.byStore.find(x=>x.storeId===state.r5ServiceFocus)||r.all;
  if(!selected?.adequate){toast('Не хватает событий для пилота');return;}
  r4AddJournal('Проверить норматив ответа '+r.sla+' сек / '+(selected.storeId==='all'?'сеть':selected.storeId),'r5-service',selected.evidenceIds.concat(selected.fittingIds));
 }
 else if(a==='r5-benchmark-open'){state.r5BenchmarkFocus=value;render();}
 else if(a==='r5-benchmark-csv'){const r=branchBenchmark(data,scoped(),state.r5Benchmark);if(r.valid)r4DownloadCsv('OSMANX_R5_BRANCHES.csv',benchmarkCsv(r));}
 else if(a==='r5-benchmark-pdf'){try{exportBranchPdf(branchBenchmark(data,scoped(),state.r5Benchmark));toast('PDF-сравнение сформировано локально.');}catch(e){toast('PDF не сформирован: '+e.message);}}
 else if(a==='r5-benchmark-drill'){state.store=state.r5BenchmarkFocus;goto('dashboard');}
 else if(a==='r5-benchmark-journal'){
  const r=branchBenchmark(data,scoped(),state.r5Benchmark),selected=r.rows.find(x=>x.id===state.r5BenchmarkFocus)||r.rows[0];
  if(!selected?.evidenceIds.length){toast('Недостаточно событий');return;}
  r4AddJournal('Проверить различия филиала '+selected.name+': '+r.label,'r5-branch',selected.evidenceIds);
 }
 else if(a==='r3-pilot-save'){
  const r=evaluatePilot({testRequests:scoped().requests.length,testPurchases:scoped().requests.filter(x=>x.purchased&&x.saleId).length,controlRequests:state.r3Pilot.controlRequests===''?null:Number(state.r3Pilot.controlRequests),controlPurchases:state.r3Pilot.controlPurchases===''?null:Number(state.r3Pilot.controlPurchases),unitGross:Number(state.r3Pilot.unitGross),pilotCost:Number(state.r3Pilot.pilotCost)});
  if(!r.valid){state.toast=r.errors.join('; ');render();return;}
  const created=newJournalEntry(state.r3Journal,{title:'Пилот: запрос размера → подтверждённый чек',scenarioId:state.scenario,type:'pilot',evidenceIds:scoped().requests.slice(0,90).map(x=>x.id)});
  state.r3Journal=created.entries;state.r3Selected=created.created.id;persist();goto('journal');
 }
 else if(a==='r3-journal-new'){
  const item=opportunityMetrics(scoped()).find(x=>x.id===target.dataset.id);
  if(!item)return;
  const created=newJournalEntry(state.r3Journal,{title:item.action,scenarioId:state.scenario,type:item.id,evidenceIds:evidenceForOpportunity(scoped(),item.id)});
  state.r3Journal=created.entries;state.r3Selected=created.created.id;persist();render();
 }
 else if(a==='r3-journal-select'){state.r3Selected=target.dataset.id;state.r3Measure={};render();}
 else if(['r3-journal-progress','r3-journal-measure','r3-journal-close'].includes(a)){
  try{state.r3Journal=transitionJournal(state.r3Journal,target.dataset.id,a==='r3-journal-progress'?'running':a==='r3-journal-measure'?'measured':'closed',state.r3Measure);state.r3Measure={};persist();render();}
  catch(error){state.toast=error.message;render();}
 }
 else if(a==='r3-journal-export'){
  const blob=new Blob([journalCsv(state.r3Journal)],{type:'text/csv;charset=utf-8'});
  const url=URL.createObjectURL(blob),anchor=document.createElement('a');
  anchor.href=url;anchor.download='OSMANX_ATELIER_DEMO_JOURNAL.csv';anchor.click();
  setTimeout(()=>URL.revokeObjectURL(url),0);
 }
 else if(a==='period'){state.period=value;render();}
 else if(a==='opp-select'){state.opp=target.dataset.id;render();}
 else if(a==='scene'){sceneChange(Number(value));}
 else if(a==='next-scene'){sceneChange(state.scene===4?0:state.scene+1);}
 else if(a==='prev-scene'){sceneChange(state.scene-1);}
 else if(a==='restart-demo'){sceneChange(0);}
 else if(a==='toggle-auto'){if(state.auto){stopAuto();render();}else startAuto();}
 else if(a==='funnel-stage'){state.funnelStage=target.dataset.stage;render();}
 else if(a==='verify-transfer'){state.lastVerification=forecastTransfer({units:state.transferUnits,probability:state.transferProbability/100,costPerUnit:state.transferCost});render();}
 else if(a==='track-decision'){state.decisionState[target.dataset.decision]=AS_OF;persist();state.toast='Добавлено в план проверки. Финансовый результат ещё не измерен.';render();}
 else if(a==='track-opp'){state.decisionState['opp-'+target.dataset.id]=AS_OF;persist();state.toast='Гипотеза добавлена в план проверки.';render();}
 else if(a==='answer'){state.answers[target.dataset.key]=value;persist();render();}
 else if(a==='next-q'){const q=QUESTION_DEFS[state.qStep];if(!state.answers[q.key])return;if(state.qStep===6)state.diagnosticDone=true;else state.qStep++;render();}
 else if(a==='prev-q'){state.qStep=Math.max(0,state.qStep-1);render();}
 else if(a==='restart-diagnostic'){state.answers={};state.qStep=0;state.diagnosticDone=false;persist();render();}
 else if(a==='pdf'){exportPdf({answers:state.answers,plan:diagnosticPlan(state.answers),date:AS_OF});state.toast='PDF-отчёт подготовлен к сохранению';render();}
 else if(a==='presentation-panel'){state.presentationPanel=value;render();}
 else if(a==='reset-calc'){state.calculator={stores:3,requestsPerStore:20,conversion:12,avgTicket:8900,costPerSale:4900,pilotCost:15000};render();}
 else if(a==='dismiss-toast'){state.toast=null;render();}
 else if(a==='select-bar'){state.toast='Столбец: '+(target.title||'события');render();}
}
function r9InputChange(element){const key=element.dataset.r9Field,value=element.value;
 const change=()=>{
  if(key==='kind'){state.r9Form={kind:value,text:'',errors:[],origin:'local'};return;}
  if(key==='selected'){state.r9Options.selected=value;state.r9Options.reason='';state.r9Options.evidenceId='';return;}
  if(key==='reason'||key==='status'||key==='evidenceId'){state.r9Options[key]=value;return;}
  if(key==='maxLagDays')state.r9Options.maxLagDays=value===''?null:Number(value);
 };
 if(element.tagName==='INPUT')preserveRerender(element,change);else{change();render();}
}
function r8InputChange(element){
 const key=element.dataset.r8Field,raw=element.value;
 const change=()=>{
  if(key==='ledgerStore'){state.r8Ledger.store=raw;return;}
  if(key==='briefStatus'){state.r8Brief.status=raw;return;}
  if(key==='pilotSeed'){state.r8Pilot.seed=raw;return;}
  const n=raw===''?null:Number(raw);
  if(key==='moveReserve')state.r8Move.reserve=n;
  else if(key==='moveProbability')state.r8Move.probability=n;
  else if(key==='moveFixed')state.r8Move.fixedCost=n;
  else if(key==='moveUnit')state.r8Move.unitCost=n;
  else if(['testShare','lift','notificationCost','fixedCost','maxInvites'].includes(key))state.r8Pilot[key]=n;
 };
 if(element.tagName==='INPUT')preserveRerender(element,change);else{change();render();}
}
function preserveRerender(element,fn){const active=document.activeElement===element,selector=element.dataset.calc?`[data-calc="${element.dataset.calc}"]`:element.dataset.r3Pilot?`[data-r3-pilot="${element.dataset.r3Pilot}"]`:element.dataset.r4Field?`[data-r4-field="${element.dataset.r4Field}"]`:element.dataset.r5Field?`[data-r5-field="${element.dataset.r5Field}"]`:element.dataset.r6Field?`[data-r6-field="${element.dataset.r6Field}"]`:element.dataset.r7Field?`[data-r7-field="${element.dataset.r7Field}"]`:element.dataset.r8Field?`[data-r8-field="${element.dataset.r8Field}"]`:element.dataset.r9Field?`[data-r9-field="${element.dataset.r9Field}"]`:`[data-field="${element.dataset.field}"]`;let start=null,end=null;try{start=element.selectionStart;end=element.selectionEnd}catch{}fn();render();if(active){const replacement=root.querySelector(selector);if(replacement){replacement.focus();try{if(start!=null)replacement.setSelectionRange(start,end)}catch{}}}}
function handleField(element){const f=element.dataset.field;
 if(f){if(f==='scenario'){state.scenario=element.value;data=buildDataset(element.value);state.opp='demand';state.funnelStage='request';state.r3TransferPlan=null;state.page='dashboard';render();return;}
  if(['period','store','category','model','size','from','to'].includes(f)){state[f]=element.value;if(f==='category')state.model='all';if(f==='from'&&state.from>state.to)state.to=state.from;if(f==='to'&&state.to<state.from)state.from=state.to;render();return;}
  if(['transferUnits','transferProbability','transferCost'].includes(f)){state[f]=Number(element.value);state.lastVerification=null;render();return;}}
 if(element.dataset.calc){const k=element.dataset.calc;const raw=Number(element.value);preserveRerender(element,()=>{state.calculator[k]=Number.isFinite(raw)?raw:0});}
}
function r4UpdateField(element){
 const key=element.dataset.r4Field,raw=element.value;
 const changes=()=>{
  if(['reserve','probability','transferCost'].includes(key))state.r4Match[key]=raw===''?null:Number(raw);
  else if(['discount','uplift','campaignCost'].includes(key))state.r4Margin[key]=raw===''?null:Number(raw);
  else if(key==='modelId')state.r4Margin.modelId=raw;
  else if(key==='capacity'||key==='budget')state.r4Portfolio[key]=raw===''?null:Number(raw);
  else if(key==='selectedCost')state.r4Portfolio.costs[state.r4PortfolioSelected]=raw===''?null:Number(raw);
  persist();
 };
 if(element.tagName==='INPUT')preserveRerender(element,changes);else{changes();render();}
}
function r5UpdateField(element){
 const k=element.dataset.r5Field,value=element.value,number=value===''?null:Number(value);
 const change=()=>{
  if(k==='kind'){state.r5Data.kind=value;state.r5Data.preview=null;}
  else if(k==='cohortWeeks')state.r5Cohort.weeks=number;
  else if(k==='cohortMin')state.r5Cohort.minCohort=number;
  else if(k==='collectionBudget')state.r5Collection.budget=number;
  else if(k==='collectionCap')state.r5Collection.cap=number;
  else if(k==='collectionReserve')state.r5Collection.reserve=number;
  else if(k==='collectionLead')state.r5Collection.leadDays=number;
  else if(k==='collectionFactor')state.r5Collection.seasonFactor=number;
  else if(k==='collectionCategory')state.r5Collection.category=value;
  else if(k==='serviceSla')state.r5Service.sla=number;
  else if(k==='serviceMin')state.r5Service.minSamples=number;
  else if(k==='benchmarkMetric')state.r5Benchmark.metric=value;
  else if(k==='benchmarkMinDays')state.r5Benchmark.minDays=number;
 };
 if(element.tagName==='INPUT')preserveRerender(element,change);else{change();render();}
}
root.addEventListener('click',handleClick);
root.addEventListener('change',e=>{
 if(e.target.matches('[data-field]'))handleField(e.target);
 else if(e.target.matches('[data-r3-transfer]')){
  const key=e.target.dataset.r3Transfer;state.r3Transfer[key]=['units','probability','costPerUnit','fixedCost','days'].includes(key)?(e.target.value===''?null:Number(e.target.value)):e.target.value;
  if(key==='modelId'){state.r3Transfer.color=product(e.target.value).colors[0];}
  state.r3TransferPlan=null;render();
 }else if(e.target.matches('[data-r3-pilot]')){const key=e.target.dataset.r3Pilot;state.r3Pilot[key]=e.target.value;render();}
 else if(e.target.matches('[data-r3-measure]')){state.r3Measure[e.target.dataset.r3Measure]=e.target.value;}
 else if(e.target.matches('[data-r4-field]')){r4UpdateField(e.target);}else if(e.target.matches('[data-r5-field]')){r5UpdateField(e.target);}else if(e.target.matches('[data-r6-field]')){r6InputChange(e.target);}else if(e.target.matches('[data-r7-field]')){r7InputChange(e.target);}else if(e.target.matches('[data-r8-field]')){r8InputChange(e.target);}else if(e.target.matches('[data-r9-field]')){r9InputChange(e.target);}else if(e.target.matches('[data-r9-file]')){const file=e.target.files?.[0];if(!file)return;if(file.size>1200000){state.r9Form.errors=['CSV превышает 1,2 МБ'];render();return;}file.text().then(t=>{state.r9Form.text=t;state.r9Form.origin='local';state.r9Form.errors=[];render();}).catch(err=>toast('CSV не прочитан: '+err.message));}else if(e.target.matches('[data-r8-file]')){const file=e.target.files?.[0];if(!file)return;if(file.size>1200000){state.r8Form.errors=['CSV превышает 1,2 МБ'];render();return;}file.text().then(text=>{state.r8Form.text=text;state.r8Form.origin='local';state.r8Form.errors=[];render();}).catch(err=>toast('CSV не прочитан: '+err.message));}else if(e.target.matches('[data-r6-form]')){state.r6BoardForm[e.target.dataset.r6Form]=e.target.value;}else if(e.target.matches('[data-r6-file]')){
  const file=e.target.files?.[0];if(!file)return;if(file.size>1200000){state.r6Mapping.preview={valid:false,errors:['Размер файла превышает 1,2 МБ'],issues:[],rows:[]};render();return;}
  file.text().then(t=>{state.r6Mapping.text=t;state.r6Mapping.mapping=inspectMapping(t,state.r6Mapping.kind).mapping;state.r6Mapping.preview=null;render();}).catch(err=>toast('CSV не прочитан: '+err.message));
 }else if(e.target.matches('[data-r5-file]')){
  const file=e.target.files?.[0];if(!file)return;if(file.size>1200000){state.r5Data.preview={valid:false,errors:['Файл больше 1,2 МБ'],issues:[],inspected:0};render();return;}
  file.text().then(t=>{state.r5Data.text=t;state.r5Data.preview=null;render();}).catch(err=>toast('Файл не прочитан: '+err.message));
 }
});
root.addEventListener('input',e=>{
 if(e.target.matches('[data-calc]'))handleField(e.target);
 else if(e.target.matches('[data-r3-pilot]')){
  const element=e.target,key=element.dataset.r3Pilot,value=element.value;
  preserveRerender(element,()=>{state.r3Pilot[key]=value;});
 }
 else if(e.target.matches('[data-r4-field]')&&e.target.tagName==='INPUT'){r4UpdateField(e.target);}else if(e.target.matches('[data-r5-field]')&&e.target.tagName==='INPUT'){r5UpdateField(e.target);}else if(e.target.matches('[data-r6-field]')&&e.target.tagName==='INPUT'){r6InputChange(e.target);}else if(e.target.matches('[data-r7-field]')&&e.target.tagName==='INPUT'){r7InputChange(e.target);}else if(e.target.matches('[data-r8-field]')&&e.target.tagName==='INPUT'){r8InputChange(e.target);}else if(e.target.matches('[data-r9-field]')&&e.target.tagName==='INPUT'){r9InputChange(e.target);}else if(e.target.matches('[data-r9-text]')){state.r9Form.text=e.target.value;const accept=root.querySelector('[data-action="r9-accept"]');if(accept)accept.disabled=!state.r9Form.text.trim()||!state.r8Workspace.sales.length;}else if(e.target.matches('[data-r8-text]')){state.r8Form.text=e.target.value;}else if(e.target.matches('[data-r6-form]')){state.r6BoardForm[e.target.dataset.r6Form]=e.target.value;}else if(e.target.matches('[data-r6-text]')){state.r6Mapping.text=e.target.value;state.r6Mapping.preview=null;state.r6Mapping.mapping=inspectMapping(state.r6Mapping.text,state.r6Mapping.kind).mapping;}else if(e.target.matches('[data-r5-text]')){state.r5Data.text=e.target.value;state.r5Data.preview=null;}
});
// Expose *read-only* deterministic verification hooks to browser smoke tests.
if(window.addEventListener){window.addEventListener('keydown',event=>{if(state.page==='demo'&&['ArrowRight','ArrowLeft',' '].includes(event.key)&&!['INPUT','SELECT','TEXTAREA'].includes(event.target?.tagName)){event.preventDefault();if(event.key===' ')state.auto?stopAuto():startAuto();else sceneChange(state.scene+(event.key==='ArrowRight'?1:-1));if(event.key===' '&&!state.auto)render();}if(event.key==='Escape'&&state.mobileOpen){state.mobileOpen=false;render();}});window.addEventListener('hashchange',()=>{const next=decodeURIComponent(window.location.hash.slice(1));if(next&&next!==state.page&&(NAV.flatMap(x=>x.items).some(([id])=>id===next)||next==='sources'))goto(next);});}
if(window.location?.hash){const route=decodeURIComponent(window.location.hash.slice(1));if(NAV.flatMap(x=>x.items).some(([id])=>id===route)){state.page=route;if(route.startsWith('module:'))state.moduleIndex=Number(route.split(':')[1])||0;}}
window.__OSMANX_DIAGNOSTICS__={get state(){return {page:state.page,scene:state.scene,scenario:state.scenario}},get totals(){return scoped().totals},get dataset(){return {products:data.products.length,days:90,stores:data.stores.length}},get journal(){return journalStats(state.r3Journal)},get pilot(){return {...state.r3Pilot}},get r4(){return {audit:auditEvidence(data,scoped()).critical,match:matchDemand(data,scoped(),state.r4Match).totals,margin:discountStress(data,scoped(),state.r4Margin).deltaGross,portfolio:prioritizePortfolio(data,scoped(),state.r4Portfolio).selected.map(x=>x.id)}},get r5(){const scope=scoped();const c=collectionPlan(data,scope,state.r5Collection),s=serviceHealth(scope,state.r5Service),b=branchBenchmark(data,scope,state.r5Benchmark),h=retentionCohorts(data,scope,state.r5Cohort);return {import:state.r5Data.preview?.valid??null,cohortMembers:h.members,collection:{valid:c.valid,units:c.units,spent:c.spent},service:{valid:s.valid,p90:s.all?.p90},benchmark:{valid:b.valid,metric:b.metric,values:b.rows.map(x=>x.value)}};},get reconciliation(){const r=reconcileEvidence(data,scoped());return {issues:r.issues,linkedCount:r.linkedCount,linkedGross:r.linkedGross}},
 get r6(){const a=traceLostDemand(data,scoped(),state.r6Demand),b=analyzeReturns(data,scoped(),state.r6Returns),c=designPilot(scoped(),state.r6Pilot),d=boardSummary(state.r6Board,state.scenario);return {mapped:state.r6Mapping.preview?.valid??null,demand:{count:a.requestCount,linked:a.buckets.confirmed,net:a.hypotheticalNet},returns:{receipts:b.receipts,returned:b.returns},pilot:{valid:c.valid,needed:c.totalRequired,feasible:c.feasible},board:{total:d.total,open:d.open,closed:d.closed},revenue:scoped().totals.revenue}},get r7(){const s=scoped(),g=decisionEvidenceGate(data,s,state.r7Gate),n=networkRebalance(data,s,state.r7Move),p=capitalAllocation(data,s,state.r7Capital,n),v=privacySimulation(data,s,state.r7Privacy),b=executiveBrief(data,s,{gate:state.r7Gate,rebalance:state.r7Move,capital:state.r7Capital,privacy:state.r7Privacy,board:state.r6Board});return {gate:{ready:g.ready,score:g.score,blockers:g.blockers},network:{routes:n.routes.length,units:n.reservedUnits,net:n.net,unserved:n.unserved},capital:{selected:p.selected.length,spent:p.totalSpend,net:p.adjustedNet},privacy:{retained:v.retained,discarded:v.discarded,entries:state.r7PrivacyLedger.length},brief:{claims:b.statements.length,valid:b.valid}};},get r8(){const w=state.r8Workspace,check=inspectWorkingSet(w),ledger=salesLedger(w),net=availabilityPlan(w,state.r8Move),pilot=recoveryPilot(w,state.r8Pilot);return {counts:check.counts,version:check.version,example:check.example,valid:check.valid,origin:check.source,ledger:{receipts:ledger.sales,net:ledger.netRevenue,gross:ledger.gross},availability:{routes:net.routes?.length,matched:net.matched,net:net.net,moved:net.movedByStock},pilot:{test:pilot.test?.length,control:pilot.control?.length,candidates:pilot.candidates,net:pilot.expectedNet},audit:state.r8Audit.length};},get r9(){const a=r9Reconcile(state.r8Workspace,state.r9Files),b=r9Settlements(state.r8Workspace,state.r9Files,state.r9Options),c=r9Cases(a,b,state.r9Triage);return {valid:a.valid,records:state.r9Files.operations.length,settlements:state.r9Files.settlements.length,matched:a.summary?.matched??0,delta:a.summary?.difference??null,bankVerified:b.totals?.verified??false,batches:b.totals?.batches??0,exceptions:c.total,closed:c.closed,signoffs:state.r9Signoffs.length,sourceVersion:state.r9Files.sourceVersion};},navigate:goto};
render();
