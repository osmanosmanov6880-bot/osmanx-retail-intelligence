/** Accessible, editorial R4 decision screens. All texts are honest about demo-data origin. */
import {STORES,CATALOG,AS_OF,MONEY,NUMBER,PERCENT} from './model.mjs';
import {esc,icon,emptyState} from './ui.mjs';
import {auditEvidence,matchDemand,discountStress,prioritizePortfolio,dossierSnapshot} from './r4_core.mjs';

const fmt=n=>n===null||n===undefined?'—':MONEY(n);
const label=(value)=>String(value??'—');
const heading=(n,kicker,title,lead)=>`<header class="r4-heading"><p class="r4-overline">OSMANX / ATELIER R4 · ${n}<span>ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ</span></p><p class="r4-kicker">${kicker}</p><h1>${title}</h1><p>${lead}</p></header>`;
const stat=(name,value,hint='')=>`<div class="r4-stat"><span>${name}</span><strong>${value}</strong>${hint?`<small>${hint}</small>`:''}</div>`;
const heading2=(title,kicker='')=>`<div class="r4-caption"><small>${kicker}</small><h2>${title}</h2></div>`;
const r4Input=(name,title,value,{min=0,max=999999,step=1}={})=>`<label class="r4-input"><span>${esc(title)}</span><input type="number" inputmode="decimal" data-r4-field="${name}" min="${min}" max="${max}" step="${step}" value="${esc(value)}" /></label>`;
const scar=()=>`<p class="r4-fine">Все оценки являются гипотезами на искусственных событиях. Операции с реальными запасами, 1С и покупателями не выполняются.</p>`;
const noData=t=>`<div class="r4-no-data">${icon('info',19)} ${esc(t)}</div>`;

export function renderTrustPage(data,scope,stream='sales'){
 const audit=auditEvidence(data,scope),selected=audit.coverage.find(x=>x.key===stream)||audit.coverage[0];
 const issues=audit.problems.filter(x=>x.stream===selected.key);
 return `${heading('01','SIGNAL QUALITY','Насколько <em>достоверны</em> цифры?','Проверка идентификаторов, связей, дат и финансовой сверки. Качество структуры не означает подключение реальных источников.')}
 <section class="r4-stats">${stat('Событий в текущем срезе',NUMBER(audit.totalEvents))}${stat('Структурных ошибок',NUMBER(audit.critical),audit.critical?'Требует исправления':'Не обнаружено')}${stat('Сигналов с ограничениями',NUMBER(audit.uncertain))}${stat('Связанные чеки',NUMBER(audit.bridge.linkedCount),`${fmt(audit.bridge.linkedGross)} валовой прибыли`)}</section>
 <div class="r4-columns"><section class="r4-panel">${heading2('Реестр источников','ИСТОЧНИК → КАЧЕСТВО')}
 <div class="r4-source-list">${audit.coverage.map(x=>`<button type="button" class="r4-source ${selected.key===x.key?'active':''}" data-action="r4-audit-stream" data-value="${x.key}"><span><strong>${esc(x.label)}</strong><small>${esc(x.source)}</small></span><span><b>${NUMBER(x.events)}</b><small>${esc(x.status)}</small></span>${icon('chevron',16)}</button>`).join('')}</div><button class="r4-outline" type="button" data-action="r4-audit-csv">Скачать результаты проверки · CSV ${icon('download',16)}</button></section>
 <section class="r4-panel r4-panel-focus">${heading2(esc(selected.label),'ПРОИСХОЖДЕНИЕ / ТЕКУЩИЙ ПОТОК')}
 <div class="r4-feature-num">${NUMBER(selected.events)}<span> записей</span></div><p>Источник: ${esc(selected.source)}. ${selected.errors?`${selected.errors} ошибочных связей требуют разбирательства.`:'Формат событий проверен.'}</p>
 <div class="r4-rule"><span>Ошибки связей</span><b>${NUMBER(selected.errors)}</b></div><div class="r4-rule"><span>Неполные признаки</span><b>${NUMBER(selected.gaps)}</b></div>
 ${issues.length?`<div class="r4-issues">${issues.slice(0,8).map(x=>`<div><code>${esc(x.id)}</code><p>${esc(x.issue)}</p></div>`).join('')}</div>`:`<div class="r4-quiet"><span>01 / ПРОВЕРЕНО</span><p>В этом срезе не выявлено структурных расхождений. Это не подтверждает физические запасы или причинный эффект.</p></div>`}
 <div class="r4-footnotes">${audit.limitations.map(x=>`<p>${esc(x)}</p>`).join('')}</div></section></div>${scar()}`;
}
export function renderMatchPage(data,scope,values,filter='transfer',selectedId=''){
 const plan=matchDemand(data,scope,values);
 if(!plan.valid)return `${heading('02','DEMAND MATCHING','Проверьте <em>параметры.</em>','Исправьте условия сценарного расчёта.')}
 <section class="r4-toolbar">${r4Input('reserve','Резерв, шт.',values.reserve,{min:0,max:15})}${r4Input('probability','Вероятность, %',values.probability,{min:0,max:100})}${r4Input('transferCost','Логистика, ₽',values.transferCost,{min:0,max:100000})}</section><section class="r4-panel">${plan.errors.map(x=>`<p class="r4-error">${esc(x)}</p>`).join('')}</section>`;
 const shown=filter==='local'?plan.matches.filter(x=>x.kind==='local'):filter==='transfer'?plan.matches.filter(x=>x.kind==='transfer'):filter==='unmatched'?plan.unmatched:plan.matches;
 const visibleMatches=shown.filter(x=>!x.reason);
 const active=visibleMatches.find(x=>x.requestId===selectedId)||visibleMatches[0]||null;
 return `${heading('02','DEMAND MATCHING','Продажа, которой <em>поможем состояться?</em>','Проверяем реальные связи SKU, размера и филиала; сценарий не резервирует товар и не обещает покупку.')}
 <section class="r4-stats">${stat('Незакрытые запросы',NUMBER(plan.considered))}${stat('Найдено по снимку',NUMBER(plan.totals.matched))}${stat('Между филиалами',NUMBER(plan.totals.remote))}${stat('Экономика · сценарий',fmt(plan.totals.estimatedNet),'До физической проверки')}</section>
 <section class="r4-toolbar">${r4Input('reserve','Оставить на полке, шт.',values.reserve,{min:0,max:15})}${r4Input('probability','Допущение покупки, %',values.probability,{min:0,max:100})}${r4Input('transferCost','Логистика, ₽ / ед.',values.transferCost,{min:0,max:100000})}<button class="r4-outline" type="button" data-action="r4-match-csv">Выгрузить распределение ${icon('download',16)}</button></section>
 <div class="r4-columns"><section class="r4-panel">${heading2('Очередь подтверждений','ЗАПРОС → ТОВАР → ФИЛИАЛ')}
 <div class="r4-segments" role="group" aria-label="Состав совпадений">${[['transfer','Перемещения'],['local','Есть в филиале'],['all','Все'],['unmatched','Нет варианта']].map(([key,txt])=>`<button class="${filter===key?'active':''}" data-action="r4-match-filter" data-value="${key}" type="button">${txt}</button>`).join('')}</div>
 <div class="r4-stack">${shown.slice(0,18).map(x=>x.reason?`<div class="r4-no-match"><code>${esc(x.requestId)}</code><span>${esc(x.reason)}</span></div>`:`<button type="button" class="r4-case ${active?.requestId===x.requestId?'active':''}" data-action="r4-match-open" data-value="${esc(x.requestId)}"><span><b>${esc(x.model)}</b><small>${esc(x.size)} · ${esc(x.color)} · ${esc(x.requestId)}</small></span><span>${esc(x.sourceStore)} → ${esc(x.destinationStore)}<small>${x.kind==='local'?'Проверить полку':'Перемещение · проверка'}</small></span>${icon('arrow',16)}</button>`).join('')||noData('Для этого фильтра подходящих запросов нет.')}</div></section>
 <section class="r4-panel r4-panel-focus">${active?`${heading2('Проверить физическое наличие','КОНКРЕТНЫЙ ЗАПРОС')}<div class="r4-product"><p>${esc(active.requestId)} / ${esc(active.modelId)}</p><h3>${esc(active.model)}</h3><span>${esc(active.size)} · ${esc(active.color)}</span></div>
 ${stat('Сценарная валовая прибыль, после логистики',fmt(active.estimatedNet),`P = ${Math.round(active.probability*100)}% · ${fmt(active.logistics)} расходов`)}
 <div class="r4-rule"><span>Источник / снимок</span><b>${esc(active.sourceStore)} · ${esc(active.sourceStockId)}</b></div>
 <div class="r4-rule"><span>Назначение</span><b>${esc(active.destinationStore)}</b></div><div class="r4-rule"><span>Доступность</span><b>Не подтверждена физически</b></div>
 <button class="r4-primary" type="button" data-action="r4-match-journal" data-id="${esc(active.requestId)}">Создать проверку в журнале ${icon('arrow',16)}</button>`:noData('Нужен спрос и учётный остаток для решения.')}
 ${scar()}</section></div>`;
}
export function renderMarginPage(data,scope,values){
 const result=discountStress(data,scope,values);
 const popular=[...new Set(scope.sales.map(s=>s.modelId))].slice(0,300).sort((a,b)=>scope.sales.filter(x=>x.modelId===b).length-scope.sales.filter(x=>x.modelId===a).length).slice(0,30);
 const choices=[values.modelId,...popular].filter((x,i,a)=>x&&a.indexOf(x)===i);
 return `${heading('03','MARGIN DEFENCE','Скидка продаёт. <em>А прибыль?</em>','Вычисляем порог безубыточности по чекам. Прирост спроса — только введённое допущение, не прогноз модели.')}
 <section class="r4-toolbar"><label class="r4-input"><span>Модель</span><select data-r4-field="modelId">${choices.map(id=>`<option value="${esc(id)}" ${result.modelId===id?'selected':''}>${esc(data.products.find(x=>x.id===id)?.name||id)}</option>`).join('')}</select></label>${r4Input('discount','Новая скидка, %',values.discount,{min:0,max:95})}${r4Input('uplift','Рост объёма · гипотеза, %',values.uplift,{min:0,max:500})}${r4Input('campaignCost','Расходы на тест, ₽',values.campaignCost,{min:0,max:1e8})}</section>
 ${!result.valid?`<section class="r4-panel">${result.errors.map(x=>`<p class="r4-error">${esc(x)}</p>`).join('')}</section>`:`<section class="r4-stats">${stat('Чистые покупки · факт',NUMBER(result.baselineUnits))}${stat('Валовая прибыль · факт',fmt(result.baselineGross))}${stat('Сценарная прибыль',fmt(result.scenarioGross),'После расходов на тест')}${stat('Изменение · гипотеза',fmt(result.deltaGross),'Никакой причинной гарантии')}</section>
 <div class="r4-columns"><section class="r4-panel">${heading2('Контроль экономики','ТРИ КОНТРОЛЬНЫЕ ФОРМУЛЫ')}
 <div class="r4-rule"><span>Цена после скидки</span><b>${fmt(result.newPrice)}</b></div><div class="r4-rule"><span>Себестоимость</span><b>${fmt(result.product.cost)}</b></div><div class="r4-rule"><span>Валовая прибыль / единицу</span><b>${fmt(result.unitGross)}</b></div><div class="r4-rule"><span>Чистые продажи по чекам</span><b>${NUMBER(result.baselineUnits)}</b></div>
 <div class="r4-rule"><span>Без роста продаж</span><b>${fmt(result.noUplift)}</b></div><div class="r4-rule"><span>Минимальное изменение объёма</span><b>${result.breakEvenUplift===null?'Не вычисляется':`${Math.max(-100,result.breakEvenUplift)}%`}</b></div>
 <button type="button" class="r4-primary" data-action="r4-margin-journal" ${!result.validBaseline?'disabled':''}>Проверить скидку в пилоте ${icon('arrow',16)}</button></section>
 <section class="r4-panel r4-panel-focus">${heading2('Риск изменения цены','НЕ ПРЕДСКАЗАНИЕ СПРОСА')}
 <div class="r4-feature-num ${result.deltaGross!==null&&result.deltaGross<0?'r4-negative':''}">${fmt(result.deltaGross)}</div>
 <p>Разница валовой прибыли в сценарии с указанным ростом покупок и расходами. Не реальный денежный результат.</p>
 <div class="r4-sensitivity"><div><span>При неизменном объёме</span><b>${fmt(result.noUplift)}</b></div><div><span>При ручном допущении +${values.uplift}%</span><b>${fmt(result.deltaGross)}</b></div></div>
 ${result.warnings.map(x=>`<p class="r4-warning">${esc(x)}</p>`).join('')}</section></div>`}${scar()}`;
}
export function renderPortfolioPage(data,scope,values,activeId){
 const plan=prioritizePortfolio(data,scope,values);
 if(!plan.valid)return `${heading('04','EXECUTION PRIORITIES','Исправьте <em>ограничения.</em>','Бюджет и число проверок должны быть корректными.')}
 <section class="r4-toolbar">${r4Input('budget','Бюджет, ₽',values.budget,{min:0,max:1e8})}${r4Input('capacity','Количество проверок',values.capacity,{min:0,max:7})}</section><section class="r4-panel">${plan.errors.map(x=>`<p class="r4-error">${esc(x)}</p>`).join('')}</section>`;
 const active=plan.candidates.find(x=>x.id===activeId)||plan.candidates[0];
 return `${heading('04','EXECUTION PRIORITIES','Не десять графиков. <em>Три решения.</em>','Сопоставляем наблюдаемые сигналы, стоимость проверки и доступный бюджет. Рейтинг не доказывает прибыль.')}
 <section class="r4-stats">${stat('Вариантов для проверки',NUMBER(plan.candidates.length))}${stat('Отобрано на пилот',NUMBER(plan.selected.length))}${stat('Бюджет',fmt(plan.budget))}${stat('Резерв',fmt(plan.remaining),'Не израсходован')}</section>
 <section class="r4-toolbar">${r4Input('budget','Бюджет на проверки, ₽',values.budget,{min:0,max:10000000,step:500})}${r4Input('capacity','Максимум проверок',values.capacity,{min:0,max:7})}<button type="button" class="r4-outline" data-action="r4-portfolio-csv">Выгрузить план CSV ${icon('download',16)}</button></section>
 <div class="r4-columns"><section class="r4-panel">${heading2('Список возможностей','СИГНАЛ / СТОИМОСТЬ / СТАТУС')}
 <div class="r4-stack">${plan.candidates.map(x=>`<button type="button" class="r4-case ${active.id===x.id?'active':''}" data-action="r4-portfolio-open" data-value="${x.id}"><span><b>${esc(x.title)}</b><small>${NUMBER(x.observations)} событий · ${esc(x.status)}</small></span><span><b>${fmt(x.cost)}</b><small>${plan.selected.some(s=>s.id===x.id)?'В плане':'Не выбран'}</small></span>${icon('arrow',16)}</button>`).join('')}</div></section>
 <section class="r4-panel r4-panel-focus">${heading2('Следующее действие','ПРОТОКОЛ ДЛЯ СОБСТВЕННИКА')}<div class="r4-feature-num">${NUMBER(active.observations)}<span> сигналов</span></div><h3 class="r4-small-title">${esc(active.title)}</h3>
 <div class="r4-rule"><span>Исполнитель</span><b>${esc(active.owner)}</b></div><div class="r4-rule"><span>Стоимость проверки</span><b>${fmt(active.cost)}</b></div><div class="r4-rule"><span>Критерий результата</span><b>${esc(active.measurement)}</b></div><div class="r4-rule"><span>Денежный эффект</span><b>${active.scenarioNet===null?'Недостаточно данных':`${fmt(active.scenarioNet)} · сценарий`}</b></div>
 ${r4Input('selectedCost','Изменить стоимость выбранной проверки, ₽',active.cost,{min:0,max:10000000,step:100})}
 <button type="button" class="r4-primary" data-action="r4-portfolio-journal" data-id="${active.id}" ${!active.hasEvidence||active.invalidCost?'disabled':''}>Добавить проверку в журнал ${icon('arrow',16)}</button><p class="r4-warning">${esc(plan.overlapWarning)}</p></section></div>${scar()}`;
}
export function renderDossierPage(data,scope,settings){
 const doc=dossierSnapshot(data,scope,settings);
 return `${heading('05','DECISION DOSSIER','Документ. <em>Не обещание.</em>','Зафиксированный срез: от источников и чеков до гипотез. Финансовые показатели воспроизводимы из выбранного периода.')}
 <section class="r4-stats">${stat('Выручка',fmt(doc.totals.revenue),'По синтетическим чекам')}${stat('Валовая прибыль',fmt(doc.totals.gross))}${stat('Связанные чеки',NUMBER(doc.totals.relatedReceipts),fmt(doc.totals.relatedReceiptGross))}${stat('Ошибки связей',NUMBER(doc.quality.errors))}</section>
 <div class="r4-columns"><section class="r4-panel r4-document">${heading2('Executive evidence brief','OSMANX WORLD · PRIVATE EXECUTIVE INTELLIGENCE')}<p class="r4-doc-stamp">ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ · ${AS_OF}</p>
 <h3>Что проверить в вашей сети</h3>
 ${doc.priorities.length?`<div class="r4-brief-list">${doc.priorities.map((x,i)=>`<div><span>0${i+1}</span><div><b>${esc(x.title)}</b><small>${esc(x.owner)} · ${NUMBER(x.observations)} событий · бюджет ${fmt(x.cost)}</small></div></div>`).join('')}</div>`:noData('Нужны данные и доступный бюджет, чтобы сформировать порядок проверок.')}
 <div class="r4-rule"><span>Период</span><b>${esc(doc.period.from)} — ${esc(doc.period.to)}</b></div>
 <div class="r4-rule"><span>Обращения без покупки</span><b>${NUMBER(doc.totals.unfulfilledRequests)}</b></div>
 <div class="r4-rule"><span>Возможные межфилиальные варианты</span><b>${NUMBER(doc.matching.remote)}</b></div>
 <div class="r4-doc-buttons"><button class="r4-primary" type="button" data-action="r4-dossier-pdf">Скачать PDF ${icon('download',16)}</button><button class="r4-outline" type="button" data-action="r4-dossier-csv">CSV + ID источников ${icon('download',16)}</button></div></section>
 <section class="r4-panel r4-panel-focus">${heading2('Границы доказательств','ФАКТ / ГИПОТЕЗА')}
 <div class="r4-feature-num">${NUMBER(doc.sampleEvidence.length)}<span> ID оснований</span></div>
 <div class="r4-evidence-ids">${doc.sampleEvidence.slice(0,12).map(x=>`<code>${esc(x)}</code>`).join('')}</div>
 <p class="r4-warning">Данные искусственные; к реальной 1С интеграция не выполнена.</p>
 ${doc.warnings.map(x=>`<p class="r4-muted-line">${esc(x)}</p>`).join('')}</section></div>${scar()}`;
}
