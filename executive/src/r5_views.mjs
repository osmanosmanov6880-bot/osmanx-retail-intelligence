/** R5 quiet-luxury user journeys, no synthetic amounts presented as actual uploads. */
import {STORES,CATEGORIES,MONEY,NUMBER,PERCENT} from './model.mjs';
import {esc,icon} from './ui.mjs';
import {reviewImport,retentionCohorts,collectionPlan,serviceHealth,branchBenchmark,sampleCsv} from './r5_core.mjs';

const r5Money=n=>n===null||n===undefined?'—':MONEY(n);
const r5Number=n=>n===null||n===undefined?'—':NUMBER(n);
const r5Percent=n=>n===null||n===undefined?'—':PERCENT(n);
const r5Heading=(index,kicker,title,desc)=>`<header class="r5-heading"><p class="r5-overline">OSMANX / EXECUTIVE R5 · ${index}<span>ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ</span></p><small>${esc(kicker)}</small><h1>${title}</h1><p>${esc(desc)}</p></header>`;
const r5Stat=(label,value,note='')=>`<div class="r5-stat"><span>${esc(label)}</span><strong>${value}</strong>${note?`<small>${esc(note)}</small>`:''}</div>`;
const r5Input=(field,label,value,{min=0,max=999999,step=1}={})=>`<label class="r5-control"><span>${esc(label)}</span><input type="number" data-r5-field="${field}" value="${esc(String(value??''))}" min="${min}" max="${max}" step="${step}" /></label>`;
const r5Warning=(msg)=>`<p class="r5-warning">${icon('info',16)} ${esc(msg)}</p>`;
const r5Label=(title)=>`<h2 class="r5-label">${esc(title)}</h2>`;
const r5Stamp=()=>`<p class="r5-stamp">OSMANX WORLD · PRIVATE EXECUTIVE INTELLIGENCE · НЕ ПОДКЛЮЧЕНО К 1С</p>`;
const r5Table=(heads,rows,empty='Нет данных по выбранным условиям')=>rows.length?`<div class="r5-table-wrap"><table class="r5-table"><thead><tr>${heads.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`:`<p class="r5-empty">${esc(empty)}</p>`;
const r5Td=(value)=>`<td>${esc(String(value??'—'))}</td>`;

export function renderR5DataRoom(state){
 const r=state.preview;const k=state.kind;
 const names={sales:'Продажи',returns:'Возвраты',stock:'Учётные остатки'};
 return `${r5Heading('01','LOCAL DATA CONTRACT','Данные должны <em>выдержать проверку.</em>','Проверьте локальную CSV-выгрузку до пилота. Файл не отправляется в сеть и не меняет цифры демонстрационного кабинета.')}
 <section class="r5-stats">${r5Stat('Статус пакета',r?(r.valid?'Проверен':'Есть ошибки'):'Не проверен','Не означает импорт в 1С')}${r5Stat('Проверено строк',r?r5Number(r.inspected||0):'—')}${r5Stat('Ошибок и пропусков',r?r5Number((r.issues?.length||0)+(r.errors?.length||0)):'—')}${r5Stat('Локальный набор чеков',r5Number(state.validatedSales?.length||0),'Только в памяти вкладки')}</section>
 <div class="r5-grid"><section class="r5-panel">${r5Label('Просмотр и проверка выгрузки')}
 <label class="r5-control"><span>Вид документа</span><select data-r5-field="kind">${Object.entries(names).map(([key,label])=>`<option value="${key}" ${k===key?'selected':''}>${label}</option>`).join('')}</select></label>
 <label class="r5-control r5-upload"><span>Выберите CSV с устройства (не более 1,2 МБ)</span><input type="file" data-r5-file accept=".csv,text/csv" aria-label="Загрузить CSV" /></label>
 <label class="r5-control"><span>Или вставьте текст CSV — UTF-8, разделитель ; либо ,</span><textarea data-r5-text rows="8" spellcheck="false" placeholder="id;date;storeId;modelId;size;paidPrice;cost">${esc(state.text||'')}</textarea></label>
 <div class="r5-actions"><button type="button" class="r5-outline" data-action="r5-sample">Пример ${esc(names[k])}</button><button type="button" class="r5-primary" data-action="r5-review">Проверить файл</button><button type="button" class="r5-quiet-btn" data-action="r5-clear">Очистить</button></div>
 <p class="r5-small">Колонки и идентификаторы обязательны. Импорт возвращается отклонённым целиком при любой некорректной строке. Чувствительные персональные данные не нужны.</p></section>
 <section class="r5-panel r5-panel-focus">${r5Label('Протокол приёмки')}
 ${r?`<div class="r5-big ${r.valid?'':'r5-risk'}">${r.valid?'PASS':'REVIEW'}</div><p>${r.valid?'Структура проверена. Файл не присоединён к демонстрационным показателям.':'Исправьте проблемы; подтверждение и экспорт результата заблокированы.'}</p>
 ${r.errors?.map(x=>r5Warning(x)).join('')||''}${r.issues?.slice(0,10).map(x=>`<div class="r5-evidence"><code>#${esc(String(x.row))} · ${esc(x.id||'')}</code><span>${esc(x.reason)}</span></div>`).join('')||''}
 ${r.valid?`<div class="r5-rule"><span>Валовая прибыль по импортированным чекам</span><b>${r.kind==='sales'?r5Money(r.totals.gross):'Не применяется'}</b></div><button class="r5-primary" type="button" data-action="r5-stage">Сохранить для проверки в этой вкладке</button><button class="r5-outline" type="button" data-action="r5-export">Скачать нормализованный CSV</button>`:''}`:
 `<div class="r5-big">—</div><p>Добавьте файл или воспользуйтесь образцом. Здесь появится построчный протокол.</p>`}
 <div class="r5-separator"></div><p class="r5-small">Для проверки возврата сначала проверьте и сохраните его исходный чек. Схемы совместимы с подготовленным экспортом учётной системы, но автоматической интеграции с 1С нет.</p></section></div>${r5Stamp()}`;
}
export function renderR5Cohorts(dataset,scope,opts,selectedStart){
 const result=retentionCohorts(dataset,scope,opts),selected=result.cohorts.find(x=>x.start===selectedStart)||result.cohorts[0];
 return `${r5Heading('02','RETENTION EVIDENCE','Возвращаются ли <em>ваши покупатели?</em>','Когорты участников программы лояльности. Учитываются только не возвращённые чеками покупки и завершённые недели наблюдений.')}
 <section class="r5-stats">${r5Stat('Участников с покупками',r5Number(result.members))}${r5Stat('Кассовых записей в выборке',r5Number(result.sourceReceipts))}${r5Stat('Повтор на следующей неделе',r5Percent(result.weekOne),'Описательная метрика')}${r5Stat('Исключённые возвращённые чеки',r5Number(result.excludedReturns))}</section>
 <section class="r5-toolbar">${r5Input('cohortWeeks','Недель после первой покупки',opts.weeks,{min:1,max:8})}${r5Input('cohortMin','Минимум участников',opts.minCohort,{min:1,max:1000})}<button type="button" class="r5-outline" data-action="r5-cohort-csv">Скачать когорты CSV</button></section>
 <div class="r5-grid"><section class="r5-panel">${r5Label('Тепловая карта повторных покупок')}
 ${r5Table(['Неделя первой покупки','Людей',...Array.from({length:opts.weeks},(_,i)=>'+'+(i+1)+' нед.')],result.cohorts.map(c=>`<tr class="r5-click-row ${selected?.start===c.start?'is-active':''}" data-r5-cohort="${c.start}" tabindex="0"><td><button type="button" data-action="r5-cohort-select" data-value="${c.start}">${esc(c.start)}</button></td><td>${c.customers}</td>${c.periods.map(x=>`<td class="${x.rate===null?'r5-future':x.rate>.25?'r5-strong':'r5-weak'}">${x.rate===null?'—':r5Percent(x.rate)}</td>`).join('')}</tr>`),'Не хватает связанных чеков для когорт')}
 <p class="r5-small">«—» означает, что неделя ещё не завершена, а не нулевую возвращаемость.</p></section>
 <section class="r5-panel r5-panel-focus">${r5Label('Разбор выбранной когорты')}
 ${selected?`<div class="r5-big">${r5Number(selected.customers)}<small>участников</small></div><div class="r5-rule"><span>Неделя</span><b>${selected.start}</b></div><div class="r5-rule"><span>Надёжность</span><b>${esc(selected.status)}</b></div><div class="r5-rule"><span>Чеков-оснований</span><b>${r5Number(selected.firstReceiptIds.length)} из первой выборки</b></div><div class="r5-evidence"><span>Примеры ID</span><code>${esc(selected.firstReceiptIds.join(', '))}</code></div>`:'<p>Недостаточно связанных событий.</p>'}
 ${result.limitations.map(r5Warning).join('')}<button type="button" class="r5-primary" data-action="r5-cohort-journal" ${!selected?'disabled':''}>Добавить пилот удержания в журнал</button></section></div>${r5Stamp()}`;
}
export function renderR5Collection(dataset,scope,opts,selectedKey){
 const plan=collectionPlan(dataset,scope,opts);
 const selected=plan.rows.find(x=>x.key===selectedKey)||plan.rows[0];
 return `${r5Heading('03','FUTURE COLLECTION','Закупать осмысленно. <em>Не наугад.</em>','Сигналы запросов, предзаказов, оплаченных задатков и прошлых продаж превращаются в ограниченный бюджетом план для проверки.')}
 ${plan.valid?`<section class="r5-stats">${r5Stat('Предложено единиц',r5Number(plan.units))}${r5Stat('Стоимость закупочного сценария',r5Money(plan.spent))}${r5Stat('Бюджет остаётся',r5Money(plan.remaining))}${r5Stat('Не покрыто по сценарию',r5Number(plan.unmet),'Не гарантированный спрос')}</section>`:''}
 <section class="r5-toolbar">${r5Input('collectionBudget','Бюджет, ₽',opts.budget,{min:0,max:1e9,step:1000})}${r5Input('collectionCap','Лимит единиц',opts.cap,{min:0,max:150})}${r5Input('collectionReserve','Неприкосновенный остаток',opts.reserve,{min:0,max:100})}${r5Input('collectionLead','Поставка, дней',opts.leadDays,{min:0,max:365})}${r5Input('collectionFactor','Сезонный коэффициент',opts.seasonFactor,{min:.25,max:3,step:.05})}<label class="r5-control"><span>Категория</span><select data-r5-field="collectionCategory">${['all',...CATEGORIES].map(c=>`<option value="${c}" ${opts.category===c?'selected':''}>${c==='all'?'Все':esc(c)}</option>`).join('')}</select></label></section>
 ${!plan.valid?`<section class="r5-panel">${plan.errors.map(r5Warning).join('')}</section>`:`<div class="r5-grid"><section class="r5-panel">${r5Label('SKU и размеры для проверки')}
 <div class="r5-row-list">${plan.rows.slice(0,20).map(x=>`<button type="button" class="r5-select ${selected?.key===x.key?'is-active':''}" data-action="r5-collection-open" data-value="${esc(x.key)}"><span><b>${esc(x.product)} · ${esc(x.size)} · ${esc(x.storeId)}</b><small>${x.requests} запросов · ${x.preorders} заявок · остаток ${x.stock}</small></span><span><b>${x.orderUnits} ед.</b><small>${r5Money(x.plannedCost)}</small></span></button>`).join('')}</div><button type="button" class="r5-outline" data-action="r5-collection-csv">Выгрузить закупочный сценарий CSV</button></section>
 <section class="r5-panel r5-panel-focus">${r5Label('Экономика выбранного размера')}
 ${selected?`<div class="r5-big">${r5Number(selected.orderUnits)}<small>ед. к проверке</small></div>
 <div class="r5-rule"><span>Модель и размер</span><b>${esc(selected.product)} / ${esc(selected.size)}</b></div><div class="r5-rule"><span>Филиал</span><b>${esc(selected.storeId)}</b></div><div class="r5-rule"><span>Запросов без покупки</span><b>${selected.requests}</b></div><div class="r5-rule"><span>Предзаказов / с задатком</span><b>${selected.preorders} / ${selected.deposits}</b></div><div class="r5-rule"><span>Учётный остаток, графит</span><b>${selected.stock} ед.</b></div><div class="r5-rule"><span>Цена закупки за единицу</span><b>${r5Money(selected.cost)}</b></div><div class="r5-rule"><span>Стоимость сценария</span><b>${r5Money(selected.plannedCost)}</b></div><div class="r5-rule"><span>Уверенность</span><b>${esc(selected.confidence)}</b></div><div class="r5-evidence"><code>${esc(selected.ids.slice(0,8).join(' · '))}</code></div>
 <button type="button" class="r5-primary" data-action="r5-collection-journal" ${selected.orderUnits<1?'disabled':''}>Создать задачу на проверку закупки</button>`:'<p>Нет оснований для расчёта.</p>'}
 ${plan.warnings.map(r5Warning).join('')}</section></div>`}${r5Stamp()}`;
}
export function renderR5Service(scope,opts,focus){
 const r=serviceHealth(scope,opts),selected=r.byStore.find(x=>x.storeId===focus)||r.all;
 return `${r5Heading('04','SERVICE RESPONSE','Скорость помощи. <em>Без домыслов.</em>','Измеряем добровольные обращения за помощью и зафиксированные причины отказа после примерки. Не приписываем задержкам непроверенные потери продаж.')}
 ${r.valid?`<section class="r5-stats">${r5Stat('QR-обращений',r5Number(r.all.requests))}${r5Stat('Медиана ответа',r.all.p50===null?'—':r.all.p50+' сек')}${r5Stat('90-й процентиль',r.all.p90===null?'—':r.all.p90+' сек')}${r5Stat('Дольше норматива',r5Percent(r.all.breachRate))}</section>`:''}
 <section class="r5-toolbar">${r5Input('serviceSla','Норматив ответа, секунд',opts.sla,{min:1,max:7200})}${r5Input('serviceMin','Минимум наблюдений',opts.minSamples,{min:1,max:1000})}<button type="button" class="r5-outline" data-action="r5-service-csv" ${!r.valid?'disabled':''}>Отчёт по филиалам CSV</button></section>
 ${!r.valid?`<section class="r5-panel">${r.errors.map(r5Warning).join('')}</section>`:`<div class="r5-grid"><section class="r5-panel">${r5Label('Контроль по филиалам')}
 <div class="r5-row-list">${r.byStore.map(x=>`<button type="button" class="r5-select ${selected.storeId===x.storeId?'is-active':''}" data-action="r5-service-open" data-value="${x.storeId}"><span><b>${esc(STORES.find(s=>s.id===x.storeId).name)}</b><small>${x.requests} событий · ${x.adequate?'описательная выборка':'недостаточно событий'}</small></span><span><b>${x.p90===null?'—':x.p90+' сек'}</b><small>p90 времени ответа</small></span></button>`).join('')}</div></section>
 <section class="r5-panel r5-panel-focus">${r5Label('Причины и исполнение')}
 <div class="r5-big">${selected.p90===null?'—':selected.p90}<small>секунд, p90</small></div>
 <div class="r5-rule"><span>Выше SLA</span><b>${r5Number(selected.breaches)} из ${r5Number(selected.sample)}</b></div><div class="r5-rule"><span>Завершённые обращения</span><b>${r5Percent(selected.resolutionRate)}</b></div><div class="r5-rule"><span>Примерок без покупки</span><b>${r5Number(selected.notPurchased)}</b></div><div class="r5-rule"><span>Названа причина отказа</span><b>${r5Number(selected.reasoned)}</b></div><div class="r5-rule"><span>Причина неизвестна</span><b>${r5Number(selected.unknownReasons)}</b></div>
 ${selected.reasons.slice(0,3).map(x=>`<div class="r5-rule"><span>${esc(x.reason)}</span><b>${x.count}</b></div>`).join('')}
 <div class="r5-evidence"><code>${esc(selected.evidenceIds.join(' · ')||'Нет превышений')}</code></div>
 ${selected.adequate?`<button type="button" class="r5-primary" data-action="r5-service-journal">Создать проверку стандарта сервиса</button>`:r5Warning('Недостаточно событий для устойчивого описательного сравнения.')}
 ${r.limitations.map(r5Warning).join('')}</section></div>`}${r5Stamp()}`;
}
export function renderR5Benchmark(dataset,scope,opts,focus){
 const r=branchBenchmark(dataset,scope,opts),selected=r.rows.find(x=>x.id===focus)||r.rows[0];
 const max=r.rows.length?Math.max(...r.rows.map(x=>Math.max(0,x.value||0)),.001):1;
 const showMetric=x=>x.value===null?'—':opts.metric==='grossProfit'?r5Money(x.value):opts.metric==='margin'||opts.metric==='conversion'?r5Percent(x.value):opts.metric==='unmetPer100'?x.value.toFixed(1):r5Number(x.value)+' сек';
 const metrics={grossProfit:'Валовая прибыль',margin:'Валовая маржа',conversion:'Конверсия входящих',unmetPer100:'Запросы без покупки / 100 визитов',serviceP90:'p90 ответа'};
 return `${r5Heading('05','BRANCH BENCHMARK','Три филиала. <em>Одна система вопросов.</em>','Сравнение на одинаковом периоде, с раскрытием знаменателя и ограничений. Рейтинг не доказывает качество управления.')}
 <section class="r5-stats">${r5Stat('Филиалов',r5Number(r.rows.length))}${r5Stat('Дней сопоставления',r5Number(r.days))}${r5Stat('Качество сравнения',r.comparable?'Достаточно':'Проверить','Порог выборки — настраивается')}${r5Stat('Показатель',esc(metrics[opts.metric]||'—'))}</section>
 <section class="r5-toolbar"><label class="r5-control"><span>Метрика</span><select data-r5-field="benchmarkMetric">${Object.entries(metrics).map(([key,name])=>`<option value="${key}" ${opts.metric===key?'selected':''}>${esc(name)}</option>`).join('')}</select></label>${r5Input('benchmarkMinDays','Минимум дней',opts.minDays,{min:1,max:90})}<button type="button" class="r5-outline" data-action="r5-benchmark-csv">CSV с ID событий</button><button type="button" class="r5-outline" data-action="r5-benchmark-pdf">PDF для собственника</button></section>
 <div class="r5-grid"><section class="r5-panel">${r5Label('Сопоставление филиалов')}
 <div class="r5-bars">${r.ranked.map((x,i)=>`<button type="button" class="r5-branch ${selected?.id===x.id?'is-active':''}" data-action="r5-benchmark-open" data-value="${x.id}"><span class="r5-branch-head"><span>0${i+1} · ${esc(x.name)}</span><b>${showMetric(x)}</b></span><span class="r5-track"><i style="width:${x.value===null?'0':Math.max(3,Math.min(100,Math.abs(x.value)/max*100)).toFixed(1)}%"></i></span><small>${r5Number(x.saleCount)} чеков · ${r5Number(x.requests)} запросов · ${x.adequate?'достаточно':'неполная выборка'}</small></button>`).join('')}</div></section>
 <section class="r5-panel r5-panel-focus">${r5Label('Доказательства выбранного филиала')}
 ${selected?`<div class="r5-big">${showMetric(selected)}</div><div class="r5-rule"><span>Выручка</span><b>${r5Money(selected.revenue)}</b></div><div class="r5-rule"><span>Валовая прибыль</span><b>${r5Money(selected.grossProfit)}</b></div><div class="r5-rule"><span>Входов по счётчику</span><b>${r5Number(selected.visits)}</b></div><div class="r5-rule"><span>Чеков / возвратов</span><b>${selected.saleCount} / ${selected.returns}</b></div><div class="r5-rule"><span>p90 помощи</span><b>${selected.metrics.serviceP90??'—'} сек</b></div>
 <div class="r5-evidence"><span>ID исходных событий</span><code>${esc(selected.evidenceIds.join(' · '))}</code></div>
 <div class="r5-actions"><button type="button" class="r5-primary" data-action="r5-benchmark-drill">Открыть кабинет филиала</button><button type="button" class="r5-outline" data-action="r5-benchmark-journal">Запланировать проверку</button></div>`:'<p>Нет данных.</p>'}
 ${r.caveats.map(r5Warning).join('')}</section></div>${r5Stamp()}`;
}
