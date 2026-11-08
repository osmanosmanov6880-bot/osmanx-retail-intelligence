/** ATELIER R3 · quiet, decision-first interfaces. All values come from r3_core, never ad copy. */
import {AS_OF,STORES,CATALOG,AURA,MONEY,NUMBER,PERCENT,opportunityMetrics} from './model.mjs';
import {esc,icon,sourceTag,storeName,rawTable,emptyState} from './ui.mjs';
import {reconcileEvidence,planTransfer,evaluatePilot,journalStats} from './r3_core.mjs';
const statusText={draft:'К проверке',running:'Измеряется',measured:'Результаты внесены',closed:'Закрыто'};
const option=(value,label,selected)=>`<option value="${esc(value)}" ${String(value)===String(selected)?'selected':''}>${esc(label)}</option>`;
const input=(field,label,value,{min=0,max=1000000,step=1,group='transfer'}={})=>`<label class="r3-field"><span>${esc(label)}</span><input data-r3-${group}="${field}" type="number" min="${min}" max="${max}" step="${step}" value="${value??''}" placeholder="Нет данных" /></label>`;
const select=(field,label,choices,value)=>`<label class="r3-field"><span>${esc(label)}</span><select data-r3-transfer="${field}">${choices.map(([v,t])=>option(v,t,value)).join('')}</select></label>`;
const header=(index,title,text)=>`<section class="r3-head"><p class="r3-overline">ATELIER / DECISION LAB ${index} <span>ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ</span></p><h1>${title}</h1><p>${text}</p></section>`;
const figure=(label,value,foot='',tone='')=>`<div class="r3-figure ${tone}"><small>${label}</small><strong>${value}</strong>${foot?`<span>${foot}</span>`:''}</div>`;
const badge=(name)=>`<span class="r3-tag">${esc(name)}</span>`;

export function renderEvidencePage(data,scope){
 const r=reconcileEvidence(data,scope),t=scope.totals;
 const register=r.entries.slice(0,16);
 return `${header('01','От цифры — <em>к первоисточнику.</em>','Каждое финансовое значение можно восстановить из синтетического реестра чеков, возвратов и связанных запросов.')}
 <section class="r3-metrics">${figure('Выручка нетто',MONEY(r.revenue),'Продажи − возвраты')}${figure('Себестоимость нетто',MONEY(r.cogs),'С учётом возвратов')}${figure('Валовая прибыль',MONEY(r.gross),'Выручка − себестоимость')}${figure('Связанные чеки',NUMBER(r.linkedCount),`${MONEY(r.linkedGross)} валовой прибыли по чекам`,'gold')}</section>
 <div class="r3-two"><article class="r3-card"><div class="r3-card-top"><p>КОНТРОЛЬ ФИНАНСОВЫХ ДАННЫХ</p>${badge(r.hasDiscrepancy?'Нужна сверка':'Сверено')}</div>
 <h2>${r.hasDiscrepancy?'Найдены несоответствия':'Формулы сходятся.'}</h2><p>Сумма строк реестра совпадает с финансовой панелью: ${r.checks.totals?'да':'нет'}. Проверены связи возвратов с исходными чеками и запросов с покупками.</p>
 <div class="r3-check">${['Совпадение выручки, себестоимости и валовой прибыли','Проверка ID исходных чеков при возврате','Связь запроса и чека по модели, филиалу, размеру'].map((text,i)=>`<div><b class="${Object.values(r.checks)[i]?'ok':'warn'}">${Object.values(r.checks)[i]?'✓':'!'}</b>${text}</div>`).join('')}</div>
 ${r.issues.length?`<div class="r3-issues">${r.issues.slice(0,6).map(x=>`<p>${esc(x)}</p>`).join('')}</div>`:''}</article>
 <article class="r3-card"><div class="r3-card-top"><p>ЦЕПОЧКА ПОКУПАТЕЛЯ</p>${badge('ФАКТ ≠ ПРИРОСТ')}</div><h2>${NUMBER(scope.requests.length)} обращений → ${NUMBER(r.linkedCount)} связанных чеков</h2>
 <p>${r.disclaimer}</p><div class="r3-result-math">${MONEY(r.linkedGross)}<span>Валовая прибыль по связанным покупкам</span></div>
 <button class="r3-text-button" data-page="pilot-lab" type="button">Перейти к измерению эффекта ${icon('arrow',16)}</button></article></div>
 <section class="r3-card r3-ledger"><div class="r3-card-top"><p>РЕЕСТР СОБЫТИЙ / ПЕРИОД ${scope.from} — ${scope.to}</p>${badge(`${r.entries.length} проводок`)}</div>
 ${register.length?rawTable(register,[['Дата','date'],['Вид','kind'],['Филиал',x=>storeName(x.storeId)],['ID','id'],['Основание',x=>x.sourceId||'—'],['Выручка',x=>MONEY(x.revenue)],['Себестоимость',x=>MONEY(x.cogs)],['Валовая прибыль',x=>MONEY(x.gross)]]):emptyState()}
 <p class="r3-disclaimer">Показаны первые ${register.length} из ${r.entries.length} проводок. Источник — исключительно синтетический набор; ни одного подключения к 1С не заявлено.</p></section>`;
}

export function renderTransferPage(data,scope,values,lastPlan){
 const p=CATALOG.find(x=>x.id===values.modelId)||AURA;
 const current=planTransfer(data,values),shown=lastPlan||null;
 return `${header('02','Товар рядом. <em>Решение — нет.</em>','Проверка конкретного межфилиального перемещения. Ни складские остатки, ни резервы здесь не изменяются.')}
 <div class="r3-two r3-planner"><section class="r3-card"><div class="r3-card-top"><p>ПАРАМЕТРЫ ПЕРЕМЕЩЕНИЯ</p>${badge('ТОЛЬКО МОДЕЛЬ')}</div>
 <h2>Сначала наличие. Потом прогноз.</h2><div class="r3-fields">
 ${select('modelId','Модель',CATALOG.map(x=>[x.id,`${x.name} · ${x.category}`]),values.modelId)}
 ${select('size','Размер',['XS','S','M','L','XL'].map(x=>[x,x]),values.size)}
 ${select('color','Цвет',p.colors.map(x=>[x,x]),values.color)}
 ${select('sourceStore','Откуда',STORES.map(x=>[x.id,x.short]),values.sourceStore)}
 ${select('destinationStore','Куда',STORES.map(x=>[x.id,x.short]),values.destinationStore)}
 ${input('units','Единиц',values.units,{min:1,max:99})}
 ${input('probability','Вероятность покупки, %',values.probability,{min:0,max:100})}
 ${input('costPerUnit','Логистика за единицу, ₽',values.costPerUnit,{min:0,max:100000})}
 ${input('fixedCost','Постоянные расходы, ₽',values.fixedCost,{min:0,max:100000})}
 </div><button class="r3-main-action" data-action="r3-transfer-check" type="button">Проверить решение ${icon('arrow',18)}</button>
 <p class="r3-disclaimer">Валидация ограничивает количество учётным остатком и незакрытыми запросами. Реальную доступность подтверждает сотрудник.</p></section>
 <section class="r3-card r3-plan-result"><div class="r3-card-top"><p>ОСНОВАНИЕ / СЦЕНАРНЫЙ РАСЧЁТ</p>${badge('НЕ РЕАЛЬНАЯ ОПЕРАЦИЯ')}</div>
 <div class="r3-trio">${figure('В источнике',current.availableAtSource===null?'—':`${current.availableAtSource} шт.`,'Учётный снимок')}${figure('У получателя',current.availableAtDestination===null?'—':`${current.availableAtDestination} шт.`)}${figure('Открытые запросы',NUMBER(current.demandCount),`За ${values.days||14} дней`)}</div>
 ${shown?(shown.valid?`<div class="r3-result-math"><small>ВОЗМОЖНАЯ ЭКОНОМИКА РЕШЕНИЯ</small>${MONEY(shown.calc.net)}<span>${shown.units} × ${PERCENT(shown.calc.probability)} × ${MONEY(shown.calc.unitGross)} − ${MONEY(shown.calc.logistics)} расходов</span></div>
 <dl class="r3-definition"><div><dt>Ожидаемые продажи</dt><dd>${shown.calc.expectedSales.toFixed(2)} единицы</dd></div><div><dt>Диапазон без доказанной причинности</dt><dd>${MONEY(shown.lowerBoundNet)} … ${MONEY(shown.upperBoundNet)}</dd></div><div><dt>Источник</dt><dd>${esc(shown.stockSourceId)} · ${shown.evidenceIds.length} запроса</dd></div></dl><p class="r3-disclaimer">${esc(shown.confidence)}. Это НЕ подтверждённый прирост прибыли.</p><button class="r3-main-action" type="button" data-action="r3-transfer-save">Добавить проверку в журнал ${icon('arrow',18)}</button>`:
 `<div class="r3-alert"><h3>Решение невозможно по этим данным</h3>${shown.problems.map(x=>`<p>${esc(x)}</p>`).join('')}</div>`):`<div class="r3-dormant"><span>01 / 02</span><h3>Условия ещё не проверены.</h3><p>Проверка покажет доступное количество, следы запросов и экономику с учётом логистики.</p></div>`}
 <p class="r3-disclaimer">Снимок ${AS_OF}. Предложение о перемещении не создаёт резерв, заказ или реальную складскую проводку.</p></section></div>`;
}

export function renderPilotPage(data,scope,values){
 const observed=scope.requests.length,linked=scope.requests.filter(x=>x.purchased&&x.saleId).length;
 const exactEvidence=reconcileEvidence(data,scope);
 const e=evaluatePilot({testRequests:observed,testPurchases:linked,controlRequests:values.controlRequests===''?null:Number(values.controlRequests),
  controlPurchases:values.controlPurchases===''?null:Number(values.controlPurchases),unitGross:Number(values.unitGross),pilotCost:Number(values.pilotCost)});
 return `${header('03','Прибыль — <em>после проверки.</em>','Не выдаём семь чеков за прирост. Сначала сравниваем пилот с контрольной группой и показываем неопределённость.')}
 <section class="r3-metrics">${figure('Пилотные обращения',NUMBER(observed),'Из событий текущего фильтра')}${figure('Связанные покупки',NUMBER(linked),'Не доказано влияние системы')}${figure('Конверсия пилота',PERCENT(e.testRate),'Покупки / обращения')}${figure('Валовая прибыль по чекам',MONEY(exactEvidence.linkedGross),'Не равно дополнительной прибыли','gold')}</section>
 <div class="r3-two"><article class="r3-card"><div class="r3-card-top"><p>КОНТРОЛЬНАЯ ГРУППА</p>${badge('ВВОДИТСЯ ВРУЧНУЮ')}</div>
 <h2>Нужен сравнимый период.</h2><p>Без контрольных данных система не рассчитывает финансовый прирост, даже если чеки связаны с запросами.</p>
 <div class="r3-fields">${input('controlRequests','Обращений в контроле',values.controlRequests,{group:'pilot',max:100000})}${input('controlPurchases','Покупок в контроле',values.controlPurchases,{group:'pilot',max:100000})}${input('unitGross','Валовая прибыль с единицы, ₽',values.unitGross,{group:'pilot',max:1000000})}${input('pilotCost','Затраты на проверку, ₽',values.pilotCost,{group:'pilot',max:10000000})}</div>
 <p class="r3-disclaimer">Сравнивать нужно сопоставимые периоды, магазины, цены и каналы. Само по себе сравнение не доказывает причинность.</p><button type="button" data-action="r3-pilot-save" class="r3-main-action">Создать протокол пилота ${icon('arrow',18)}</button></article>
 <article class="r3-card"><div class="r3-card-top"><p>ИТОГ ПИЛОТНОГО ИЗМЕРЕНИЯ</p>${badge(e.controlPresent?'ОПИСАТЕЛЬНО':'КОНТРОЛЬ НЕ ЗАПОЛНЕН')}</div>
 <h2>${e.valid&&e.delta!==null?`Разница конверсий ${e.delta>=0?'+':''}${PERCENT(e.delta)}`:'Недостаточно данных для финансового вывода.'}</h2>
 <p>${esc(e.conclusion)}</p>${e.errors?.map(x=>`<div class="r3-error">${esc(x)}</div>`).join('')}
 <dl class="r3-definition"><div><dt>Конверсия пилота</dt><dd>${PERCENT(e.testRate)}</dd></div><div><dt>Конверсия контроля</dt><dd>${PERCENT(e.controlRate)}</dd></div><div><dt>Разница валовой прибыли по сценарию</dt><dd>${e.descriptiveDifference===null?'—':MONEY(e.descriptiveDifference)}</dd></div><div><dt>После затрат</dt><dd>${e.descriptiveNet===null?'—':MONEY(e.descriptiveNet)}</dd></div><div><dt>95% интервал неопределённости</dt><dd>${e.interval?`${MONEY(e.interval[0])} … ${MONEY(e.interval[1])}`:'—'}</dd></div></dl>
 <p class="r3-disclaimer">${esc(e.confidence||'Неизвестная неопределённость')}. Метод Wilson оценивает случайную вариацию долей, не устраняет систематические отличия групп.</p></article></div>`;
}

export function renderJournalPage(scope,entries,selectedId,measure={}){
 const stats=journalStats(entries),selected=entries.find(x=>x.id===selectedId)||entries[entries.length-1]||null;
 const opps=opportunityMetrics(scope);
 return `${header('04','Не отчёт. <em>Журнал решений.</em>','Каждая гипотеза проходит путь: сформирована → проверяется → измерена → закрыта. История остаётся только в этом браузере.')}
 <section class="r3-metrics">${figure('Всего проверок',NUMBER(stats.all))}${figure('Не начаты',NUMBER(stats.draft))}${figure('Идут',NUMBER(stats.running))}${figure('Измерены',NUMBER(stats.measured),'Без доказанной причинности','gold')}</section>
 <div class="r3-two"><article class="r3-card"><div class="r3-card-top"><p>НОВАЯ ПРОВЕРКА</p>${badge('ЛОКАЛЬНЫЙ ЖУРНАЛ')}</div><h2>Выберите коммерческий сигнал.</h2><div class="r3-suggestion-list">${opps.map(o=>`<button type="button" data-action="r3-journal-new" data-id="${o.id}"><span>${esc(o.label)}<small>${NUMBER(o.count)} наблюдений · ${esc(o.uncertainty)}</small></span>${icon('arrow',18)}</button>`).join('')}</div>
 <p class="r3-disclaimer">Создание записи не запускает закупку, перемещение или рассылку. Для реальной операции потребуется защищённая интеграция.</p></article>
 <article class="r3-card"><div class="r3-card-top"><p>РЕЕСТР / ${entries.length} ЗАПИСЕЙ</p>${badge('СОХРАНЕНИЕ НА УСТРОЙСТВЕ')}</div>
 ${entries.length?`<div class="r3-journal-list">${entries.map(x=>`<button type="button" data-action="r3-journal-select" data-id="${esc(x.id)}" class="${selected?.id===x.id?'active':''}"><b>${esc(x.id)}</b><span>${esc(x.title)}<small>${esc(statusText[x.status]||'План')} · ${esc(x.owner)}</small></span>${icon('chevron',16)}</button>`).join('')}</div>`:emptyState('Проверок пока нет. Добавьте одну гипотезу слева.')}</article></div>
 ${selected?`<section class="r3-card r3-journal-detail"><div class="r3-card-top"><p>${esc(selected.id)} / ${esc(statusText[selected.status])}</p>${badge('ГИПОТЕЗА, НЕ РЕШЕНИЕ К ИСПОЛНЕНИЮ')}</div><h2>${esc(selected.title)}</h2><p>Ответственный: ${esc(selected.owner)} · сценарий: ${esc(selected.scenarioId)} · оснований: ${selected.evidenceIds.length}. Все события демонстрационные.</p>
 <div class="r3-timeline">${selected.events.map(x=>`<div><span>${esc(x.at)}</span><b>${esc(x.action)}</b></div>`).join('')}</div>
 ${selected.status==='draft'?`<button class="r3-main-action" data-action="r3-journal-progress" data-id="${selected.id}" type="button">Начать измерение ${icon('arrow',17)}</button>`:''}
 ${selected.status==='running'?`<div class="r3-fields r3-measure-fields">${input('before','Покупок до',measure.before??'',{group:'measure',max:100000})}${input('after','Покупок после',measure.after??'',{group:'measure',max:100000})}${input('sample','Размер каждой выборки',measure.sample??'',{group:'measure',max:100000})}${input('expenses','Фактические расходы, ₽',measure.expenses??'',{group:'measure',max:10000000})}</div><button class="r3-main-action" data-action="r3-journal-measure" data-id="${selected.id}" type="button">Записать результат ${icon('arrow',17)}</button>`:''}
 ${selected.result?`<div class="r3-measured"><span>ФАКТЫ ИЗ РУЧНОГО ВВОДА</span><h3>${selected.result.before} → ${selected.result.after} покупок / выборка ${selected.result.sample}</h3><p>Разница ${selected.result.delta>=0?'+':''}${selected.result.delta}; расходы ${MONEY(selected.result.expenses)}.</p><p>${esc(selected.result.note)}</p></div>`:''}
 ${selected.status==='measured'?`<button class="r3-main-action" data-action="r3-journal-close" data-id="${selected.id}" type="button">Закрыть проверку ${icon('check',17)}</button>`:''}
 <button class="r3-text-button" data-action="r3-journal-export" type="button">Скачать журнал CSV ${icon('download',16)}</button></section>`:''}
 <p class="r3-disclaimer">В журнале не хранятся контакты покупателей. Локальное хранение может быть очищено браузером; CSV позволяет сделать ручную копию. Это не система исполнения реальных решений.</p>`;
}
