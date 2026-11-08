/** Quiet luxury decision assurance rooms R7: semantic HTML, all output escaped. */
import {esc,icon} from './ui.mjs';
import {AS_OF,STORES,MONEY,NUMBER} from './model.mjs';
import {decisionEvidenceGate,networkRebalance,capitalAllocation,privacySimulation,executiveBrief} from './r7_core.mjs';
const r7_e=x=>esc(String(x??''));
const r7_m=x=>MONEY(x??0);
const r7_n=x=>NUMBER(x??0);
const r7_stamp='<p class="r7-demo-r7_stamp">ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ · НЕ РЕАЛЬНАЯ ИНТЕГРАЦИЯ</p>';
const r7_head=(number,eyebrow,title,sub)=>`<section class="r7-r7_head"><div class="r7-serial"><span>OSMANX</span><span>ATELIER / R7</span><span>${number} / 05</span></div><p class="r7-eyebrow">${r7_e(eyebrow)}</p><h1>${title}</h1><p class="r7-sub">${r7_e(sub)}</p></section>`;
const r7_stat=(name,value,sub='',tone='')=>`<div class="r7-r7_stat ${tone}"><span>${r7_e(name)}</span><strong>${r7_e(value)}</strong><small>${r7_e(sub)}</small></div>`;
const r7_notes=lines=>`<div class="r7-r7_notes">${lines.map(x=>`<p>${icon('shield',15)}${r7_e(x)}</p>`).join('')}</div>`;
const r7_pane=(title,inner,extra='')=>`<section class="r7-r7_pane ${extra}"><div class="r7-r7_pane-heading"><h2>${r7_e(title)}</h2></div>${inner}</section>`;
const r7_field=(key,label,value,config={})=>`<label class="r7-r7_field"><span>${r7_e(label)}</span><input data-r7-r7_field="${r7_e(key)}" inputmode="decimal" type="number" min="${config.min??0}" max="${config.max??1000000}" step="${config.step??1}" value="${r7_e(value)}" /></label>`;
const r7_select=(key,label,value,options)=>`<label class="r7-r7_field"><span>${r7_e(label)}</span><r7_select data-r7-r7_field="${r7_e(key)}">${options.map(([v,t])=>`<option value="${r7_e(v)}" ${String(v)===String(value)?'selected':''}>${r7_e(t)}</option>`).join('')}</r7_select></label>`;
const r7_btn=(action,label,disabled=false,cls='')=>`<button type="button" class="r7-r7_btn ${cls}" data-action="${action}" ${disabled?'disabled':''}>${r7_e(label)} ${icon('arrow',16)}</button>`;
const r7_evidence=ids=>`<div class="r7-r7_evidence"><span>ИСТОЧНИКИ</span><div>${(ids||[]).slice(0,9).map(x=>`<code>${r7_e(x)}</code>`).join('')||'<em>Нет привязанных событий</em>'}</div></div>`;
const r7_banners=(r7_banners=[])=>`<div class="r7-alerts">${r7_banners.map(x=>`<p>${r7_e(x)}</p>`).join('')}</div>`;
const r7_fmtStore=id=>STORES.find(s=>s.id===id)?.short||id;
const r7_badge=(text,kind='muted')=>`<span class="r7-r7_badge ${kind}">${r7_e(text)}</span>`;
const r7_errors=r=>r.valid?'':r7_banners(r.errors);
const r7_actionGroup=(buttons)=>`<div class="r7-actions">${buttons.join('')}</div>`;

export function renderR7Gate(dataset,scope,params){
 const r=decisionEvidenceGate(dataset,scope,params);
 return r7_head('01','EVIDENCE ASSURANCE','Цифры сначала. <em>Выводы потом.</em>','Перед финансовой рекомендацией проверяем источники, связи событий и актуальность остатков.')+
 `<div class="r7-stats">${r7_stat('Готовность к пилотной проверке',r.valid?(r.ready?'Источник согласован':'Есть блокировки'):'Проверьте параметры','','r7-wide')}${r7_stat('Показатель качества',r.valid?r.score+' / 100':'—','Не доказательство достоверности учёта')}${r7_stat('Связанных чеков',r.linkedCount??'—','Проверка ID запроса и чека')}${r7_stat('Проблемных остатков',r.staleStock??'—','По возрасту снимка')}</div>`+
 r7_pane('Условия допуска',`<div class="r7-controls">${r7_field('gateRequests','Минимум запросов',params.minimumRequests,{max:5000})}${r7_field('gateLinked','Минимум связанных чеков',params.minimumLinked,{max:1000})}${r7_field('gateAge','Возраст снимка, дней',params.maxStockAgeDays,{max:365})}</div>${r7_errors(r)}`)+
 `<div class="r7-two">${r7_pane('Проверка пяти условий',r.valid?`<div class="r7-checks">${r.checks.map(x=>`<article><div>${r7_badge(x.pass?'Проверено':'Проверить',x.pass?'success':'risk')}<strong>${r7_e(x.name)}</strong></div><small>${x.failures?`Нарушений или недостающих: ${x.failures}`:'Пройдена в демоданных'}</small>${r7_evidence(x.evidenceIds)}</article>`).join('')}</div>`:'<p>Введите допустимые условия.</p>')}
 ${r7_pane('Решение о продолжении',r.valid?`<p class="r7-decision">${r.ready?'Можно проектировать ограниченный пилот.':'Финансовые выводы пока не рекомендуются.'}</p>${r.blockers.length?r7_banners(r.blockers):''}${r7_actionGroup([r7_btn('r7-gate-csv','Экспорт проверки'),r7_btn('r7-gate-task','Создать задачу проверки',false,'primary')])}`:'<p>Нет результата проверки.</p>')}</div>`+
 r7_notes([r.disclaimer||'Проверка качества данных не является внешним аудитом.', 'Все события локальные и синтетические; настоящую 1С система не опрашивала.'])+r7_stamp;
}

export function renderR7Rebalance(dataset,scope,params,selectedId){
 const r=networkRebalance(dataset,scope,params),row=r.routes.find(x=>x.id===selectedId)||r.routes[0];
 return r7_head('02','NETWORK REBALANCE','Товар есть в сети. <em>Но где он нужен?</em>','Перераспределяем текущий запас, сохраняя резерв, не удваивая единицы и не выдавая прогноз за проданную вещь.')+
 `<div class="r7-stats">${r7_stat('Маршрутов для проверки',r.routes.length,'Не складские документы')}${r7_stat('Единиц в сценарии',r.reservedUnits,'Без физического списания')}${r7_stat('Валовая прибыль сценария',r7_m(r.scenarioGross),'Ожидаемая, не подтверждённая')}${r7_stat('Эффект после затрат',r7_m(r.net),'Сценарный расчёт, не прирост')}</div>`+
 r7_pane('Условия сценария',`<div class="r7-controls">${r7_field('moveReserve','Резерв в источнике, шт.',params.reserve,{max:100})}${r7_field('moveProbability','Вероятность покупки, %',params.probability,{max:100})}${r7_field('moveFixed','Фиксированная логистика, ₽',params.fixedCost,{max:10000000,step:50})}${r7_field('moveUnitCost','Логистика на шт., ₽',params.unitCost,{max:1000000,step:50})}${r7_field('moveUnits','Лимит на маршрут, шт.',params.maxUnits,{min:1,max:100})}${r7_field('moveDemand','Минимум запросов',params.minDemand,{min:1,max:1000})}</div>${r7_errors(r)}`)+
 `<div class="r7-two">${r7_pane('Допустимые маршруты',r.routes.length?`<div class="r7-list">${r.routes.map(x=>`<button type="button" class="r7-choice ${row?.id===x.id?'active':''}" data-action="r7-move-r7_select" data-value="${r7_e(x.id)}"><span><b>${r7_e(r7_fmtStore(x.sourceStore))} → ${r7_e(r7_fmtStore(x.destinationStore))}</b><small>${r7_e(x.product)} · ${r7_e(x.size)} · ${r7_e(x.units)} шт.</small></span><strong>${r7_m(x.net)}</strong></button>`).join('')}</div>`:'<p>При выбранных ограничениях нет экономически допустимых перемещений.</p>')}
 ${r7_pane('Проверить конкретный маршрут',row?`<p class="r7-decision">${r7_e(row.product)} / ${r7_e(row.color)} / ${r7_e(row.size)}</p><div class="r7-ledger"><div><span>Источник</span><b>${r7_e(r7_fmtStore(row.sourceStore))}</b></div><div><span>Филиал назначения</span><b>${r7_e(r7_fmtStore(row.destinationStore))}</b></div><div><span>В сценарии</span><b>${r7_n(row.units)} шт.</b></div><div><span>Валовая маржа за штуку</span><b>${r7_m(row.unitGross)}</b></div><div><span>Расчёт</span><b>${r7_m(row.scenarioGross)} − ${r7_m(row.cost)} = ${r7_m(row.net)}</b></div></div>${r7_evidence(row.evidenceIds)}${r7_actionGroup([r7_btn('r7-move-csv','Экспорт маршрутов'),r7_btn('r7-move-task','Проверить в филиале',false,'primary')])}`:'<p>Увеличьте период или измените параметры.</p>','r7-accent')}</div>`+
 r7_notes([r.disclaimer||'Данные условные.',`Не распределено по выбранным условиям: ${r7_n(r.unserved)} сигналов, часть из них требует физической проверки.`])+r7_stamp;
}

export function renderR7Capital(dataset,scope,params,moveParams){
 const plan=networkRebalance(dataset,scope,moveParams),p=capitalAllocation(dataset,scope,params,plan);
 return r7_head('03','CAPITAL DISCIPLINE','Не все возможности <em>стоят денег.</em>','Оптимизатор ограничивает бюджет и число параллельных проверок. Он не подменяет утверждение расходов собственником.')+
 `<div class="r7-stats">${r7_stat('Бюджет сценария',r7_m(p.budget),'Ручное допущение')}${r7_stat('Затраты выбранных проверок',r7_m(p.totalSpend),'Логистика плюс проверка')}${r7_stat('Неиспользованный бюджет',r7_m(p.remaining),'Не потраченные деньги')}${r7_stat('Эффект с дисконтом',r7_m(p.adjustedNet),'Гипотеза, не доказанная прибыль')}</div>`+
 r7_pane('Ограничения и осторожность',`<div class="r7-controls">${r7_field('capitalBudget','Бюджет проверок, ₽',params.budget,{max:100000000,step:1000})}${r7_field('capitalCapacity','Одновременно, не более',params.capacity,{max:10})}${r7_field('capitalAudit','Цена проверки, ₽/маршрут',params.verificationCost,{max:10000000,step:100})}${r7_field('capitalConfidence','Коэффициент осторожности, %',params.confidence,{max:100})}</div>${r7_errors(p)}`)+
 `<div class="r7-two">${r7_pane('Портфель сценариев',p.candidates.length?`<div class="r7-list">${p.candidates.map(x=>`<article class="r7-choice r7-static"><span>${r7_badge(p.selected.some(y=>y.id===x.id)?'В бюджете':'Не выбрано',p.selected.some(y=>y.id===x.id)?'success':'muted')}<b>${r7_e(x.title)}</b><small>Проверка: ${r7_m(x.cost)} · Валовая прибыль: ${r7_m(x.gross)}</small></span><strong>${r7_m(x.adjustedNet)}</strong></article>`).join('')}</div>`:'<p>Нет допустимых маршрутов. Измените экономические допущения в разделе перемещений.</p>')}
 ${r7_pane('Что решает оптимизатор',`<p class="r7-decision">${p.selected.length?`${p.selected.length} сценария в бюджете`:'Ни один сценарий не проходит ограничения'}</p><p>Перебираются допустимые сочетания без повторного учёта заявки и запасов. Показатель эффективности — прогноз после консервативного дисконта.</p>${p.selected.length?r7_evidence(p.sourceRequestIds):''}${r7_actionGroup([r7_btn('r7-capital-csv','Экспорт портфеля',!p.valid),r7_btn('r7-capital-task','Зафиксировать бюджетный пилот',!p.selected.length,'primary')])}${r7_notes(['Это не фактическое распределение капитала и не автоматический заказ товара.'])}`,'r7-accent')}</div>`+
 r7_notes([p.disclaimer||'Потенциальная прибыль требует проверки на реальной выборке.'])+r7_stamp;
}

export function renderR7Privacy(dataset,scope,params,ledger){
 const p=privacySimulation(dataset,scope,params);
 return r7_head('04','PRIVACY LAB','Данные клиентов. <em>Только необходимые.</em>','Моделируем согласие, срок хранения и обезличенный экспорт на локальных синтетических событиях. Без отправки в сеть.')+
 `<div class="r7-stats">${r7_stat('Добровольных событий',r7_n(p.total),'Запросы и предзаказы')}${r7_stat('Допустимы по политике',r7_n(p.retained),'Только в симуляции')}${r7_stat('Исключаются',r7_n(p.discarded),'Срок и отсутствие согласия')}${r7_stat('Записей в локальном журнале',r7_n(ledger.length),'Без личных данных')}</div>`+
 r7_pane('Правила песочницы',`<div class="r7-controls">${r7_field('privacyRetention','Срок хранения, дней',params.retentionDays,{min:1,max:365})}${r7_select('privacyConsent','Персональное согласие',params.requireConsent?'required':'any',[['required','Требовать'],['any','Показать режим без согласия']])}</div>${r7_errors(p)}${r7_actionGroup([r7_btn('r7-privacy-preview','Пересчитать политику'),r7_btn('r7-privacy-apply','Зафиксировать симуляцию',!p.valid,'primary'),r7_btn('r7-privacy-csv','Экспорт агрегатов',!p.valid)])}`)+
 `<div class="r7-two">${r7_pane('Что исключается',`<div class="r7-ledger"><div><span>Истёк срок хранения</span><b>${r7_n(p.expired)}</b></div><div><span>Нет согласия (без двойного счёта)</span><b>${r7_n(p.noConsent)}</b></div><div><span>Всего исключено</span><b>${r7_n(p.discarded)}</b></div><div><span>Выгрузка</span><b>Только агрегаты</b></div></div>${r7_notes([p.disclaimer||'Выгрузка обезличена.'])}`)}
 ${r7_pane('История симуляций',ledger.length?`<div class="r7-list">${ledger.slice().reverse().slice(0,8).map(x=>`<article class="r7-choice r7-static"><span><b>Проверка #${x.seq} · ${r7_e(x.date)}</b><small>${r7_e(x.scenario)} / хранение ${x.retentionDays} дней / исключено ${x.discarded}</small></span>${r7_badge(x.fingerprint,'muted')}</article>`).join('')}</div>`:'<p>Журнал пуст. Зафиксируйте результат симуляции, чтобы проверить повторное открытие.</p>')}</div>`+
 r7_notes(['Это НЕ удаление реальных персональных данных и НЕ юридическая сертификация.','Ни телефоны, ни имена, ни идентификаторы клиентов не включаются в агрегированный CSV.'])+r7_stamp;
}

export function renderR7Brief(dataset,scope,params,board,privacyLedger){
 const b=executiveBrief(dataset,scope,{...params,board});
 return r7_head('05','EXECUTIVE EVIDENCE BRIEF','Одна страница. <em>Пять проверяемых утверждений.</em>','Короткое досье собственника с источниками, формулами и границами достоверности — без обещаний роста прибыли.')+
 `<div class="r7-stats">${r7_stat('Выводов с источниками',r7_n(b.statements.length),'Все выводы имеют статус')}${r7_stat('Качество данных',b.gate.ready?'Готово к пилоту':'Нужна проверка','Не внешний аудит')}${r7_stat('Предложений по перемещению',r7_n(b.network.routes.length),'Только сценарии')}${r7_stat('Открытых задач',r7_n(b.openTasks),'Локальный журнал')}</div>`+
 `<div class="r7-two">${r7_pane('Финансовые утверждения',`<div class="r7-claims">${b.statements.map(x=>`<article><div>${r7_badge(x.epistemic,x.epistemic.startsWith('ФАКТ')?'success':'muted')}<h3>${r7_e(x.label)}</h3></div><strong>${r7_m(x.value)}</strong><p>${r7_e(x.method)}</p>${r7_evidence(x.evidenceIds)}</article>`).join('')}</div>`)}
 ${r7_pane('Что делать собственнику',`<p class="r7-decision">Сначала доказательства. Затем действие.</p><div class="r7-next">${b.nextActions.map((x,i)=>`<p><span>0${i+1}</span>${r7_e(x)}</p>`).join('')}</div><div class="r7-ledger"><div><span>Период</span><b>${r7_e(scope.from)} — ${r7_e(scope.to)}</b></div><div><span>Филиалы</span><b>${r7_e(scope.filter.store==='all'?'Вся сеть':r7_fmtStore(scope.filter.store))}</b></div><div><span>Журнал симуляций приватности</span><b>${r7_n(privacyLedger.length)}</b></div></div>${r7_actionGroup([r7_btn('r7-brief-pdf','Сформировать PDF',!b.valid,'primary'),r7_btn('r7-brief-csv','Экспорт CSV',!b.valid),r7_btn('r7-brief-task','Назначить следующий шаг')])}`,'r7-accent')}</div>`+
 r7_notes([b.disclaimer, 'Отчёт не содержит загруженный CSV-файл и не содержит реальных личных данных.'])+r7_stamp;
}
