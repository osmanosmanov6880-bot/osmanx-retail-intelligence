/** R8 five accessible, linked decision rooms. Every R8 value is from a local CSV working set. */
import {esc,icon} from './ui.mjs';
import {AS_OF,MONEY,NUMBER} from './model.mjs';
import {R8_KINDS,R8_LABELS,inspectWorkingSet,salesLedger,availabilityPlan,recoveryPilot,r8OwnerBrief} from './r8_core.mjs';
const r8_e=v=>esc(String(v??'')), r8_n=v=>Number.isFinite(v)?NUMBER(v):'—', r8_m=v=>Number.isFinite(v)?MONEY(v):'—';
const r8_head=(i,k,title,description)=>`<section class="r8-head r7-head"><div class="r7-serial"><span>OSMANX ATELIER</span><span>LOCAL DATA / R8</span><span>${i} / 05</span></div><p class="r7-eyebrow">${r8_e(k)}</p><h1>${title}</h1><p class="r7-sub">${r8_e(description)}</p></section>`;
const r8_stamp=(ws)=>`<div class="r8-origin" role="status">${icon('shield',16)} <b>${r8_e(inspectWorkingSet(ws).source)}</b> <span>Файлы остаются только в памяти браузера. Демонстрационные показатели не изменяются.</span></div>`;
const r8_stat=(title,value,sub='')=>`<article class="r8-stat"><span>${r8_e(title)}</span><strong>${r8_e(value)}</strong><small>${r8_e(sub)}</small></article>`;
const r8_stats=x=>`<section class="r8-stats" aria-label="Ключевые показатели">${x.join('')}</section>`;
const r8_panel=(title,content,aside='')=>`<section class="r8-panel"><header><h2>${r8_e(title)}</h2>${aside}</header>${content}</section>`;
const r8_row=(title,value)=>`<div class="r8-row"><span>${r8_e(title)}</span><b>${r8_e(value)}</b></div>`;
const r8_note=x=>`<p class="r8-note">${icon('info',15)} ${r8_e(x)}</p>`;
const r8_btn=(act,label,style='',disabled=false)=>`<button type="button" class="r8-button ${style}" data-action="${r8_e(act)}" ${disabled?'disabled':''}>${r8_e(label)} ${icon('arrow',16)}</button>`;
const r8_field=(id,label,value,{min=0,max=1000000,step=1}={})=>`<label class="r8-field"><span>${r8_e(label)}</span><input aria-label="${r8_e(label)}" data-r8-field="${r8_e(id)}" type="number" inputmode="decimal" min="${min}" max="${max}" step="${step}" value="${r8_e(value)}"/></label>`;
const r8_select=(id,label,value,values)=>`<label class="r8-field"><span>${r8_e(label)}</span><select aria-label="${r8_e(label)}" data-r8-field="${r8_e(id)}">${values.map(([v,t])=>`<option value="${r8_e(v)}" ${String(value)===String(v)?'selected':''}>${r8_e(t)}</option>`).join('')}</select></label>`;
const r8_notices=xs=>xs?.length?`<div class="r8-errors" role="alert">${xs.map(x=>`<p>${r8_e(x)}</p>`).join('')}</div>`:'';
const r8_tbody=(headers,records)=>`<div class="r8-table-scroll"><table class="r8-table"><thead><tr>${headers.map(x=>`<th>${r8_e(x)}</th>`).join('')}</tr></thead><tbody>${records.length?records.map(r=>`<tr>${r.map(c=>`<td>${r8_e(c)}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${headers.length}">Данных пока нет</td></tr>`}</tbody></table></div>`;
const r8_tabs=items=>`<div class="r8-switch" role="group">${items.map(([id,label,active])=>`<button class="${active?'selected':''}" data-action="r8-kind" data-value="${r8_e(id)}" type="button">${r8_e(label)}</button>`).join('')}</div>`;
function r8_stores(ws){return [['all','Все филиалы'],...[...new Set(ws.sales.map(x=>x.storeId))].sort().map(id=>[id,id])];}
export function renderR8Intake(ws,form){const check=inspectWorkingSet(ws);const kind=form.kind;
 return r8_head('01','LOCAL SOURCE VAULT','Ваши файлы. <em>Ваши факты.</em>','Загружайте локальные обезличенные выгрузки. Не нужно соединять 1С с интернетом или заменять действующий учёт.')+r8_stamp(ws)+
 r8_stats(Object.keys(R8_KINDS).map(k=>r8_stat(R8_LABELS[k],r8_n(check.counts[k]),ws.origin[k]==='example'?'Учебный пример':ws.origin[k]==='local'?'Локальный CSV':'Не загружено')))+
 `<div class="r8-columns">${r8_panel('Загрузка и проверка',r8_tabs(Object.keys(R8_KINDS).map(k=>[k,R8_LABELS[k],kind===k]))+
 `<p class="r8-note">Формат заголовка: <code>${r8_e(R8_KINDS[kind].join('; '))}</code></p><label class="r8-upload">CSV-файл с компьютера / телефона<input data-r8-file type="file" accept=".csv,text/csv,text/plain" aria-label="Выбрать CSV"/></label><label class="r8-field r8-textarea"><span>Или вставьте CSV вручную</span><textarea spellcheck="false" data-r8-text rows="7" placeholder="${r8_e(R8_KINDS[kind].join(';'))}">${r8_e(form.text)}</textarea></label>`+
 `<div class="r8-actions">${r8_btn('r8-accept','Проверить и принять','primary')}${r8_btn('r8-sample-one','Пример файла')}${r8_btn('r8-sample-all','Загрузить учебный набор')}</div>`+
 r8_notices(form.errors)+r8_note('Каждая новая таблица принимается целиком. При ошибке старый проверенный набор остаётся неизменным.')+
 r8_btn('r8-clear','Очистить рабочий набор','muted'))}
 ${r8_panel('Контракт безопасности',`<div class="r8-rule-list">${[
 ['Без персональных данных','Не используем имена, телефоны, email, адреса и идентификаторы покупателей. Неизвестные столбцы блокируются.'],
 ['Без тихой подмены','Локальный CSV не смешивается с 300 демо-SKU и не меняет исходные графики.'],
 ['Сверка связей','Возвраты не превышают чек; запрос на покупку связан с правильными SKU/размером/магазином.'],
 ['Только в памяти','Сырые строки исчезают при закрытии или перезагрузке страницы. Лишь обезличенный итог можно сохранить отдельно.']
 ].map(([a,b])=>`<article><strong>${r8_e(a)}</strong><p>${r8_e(b)}</p></article>`).join('')}</div>`+
 r8_notices(check.errors)+check.notes.map(r8_note).join('')+`<div class="r8-status">Версия локального набора <strong>${r8_n(check.version)}</strong> · Строк принято <strong>${r8_n(Object.values(check.counts).reduce((a,b)=>a+b,0))}</strong></div>`)}
 </div><p class="r8-end">LOCAL ONLY / НЕ ЯВЛЯЕТСЯ ПОДКЛЮЧЕНИЕМ К 1С ИЛИ POS</p>`;
}
export function renderR8Ledger(ws,params){const a=salesLedger(ws,params),c=inspectWorkingSet(ws);
 return r8_head('02','VERIFIED CASHFLOW','Прибыль начинается <em>с чека.</em>','Сверяем оплату, себестоимость и частичные возвраты. Числа строятся только из принятых локальных CSV.')+r8_stamp(ws)+
 r8_stats([r8_stat('Чеков',a.valid?r8_n(a.sales):'—','Уникальные ID'),r8_stat('Чистая выручка',a.valid?r8_m(a.netRevenue):'—','Выручка − возвраты'),r8_stat('Валовая прибыль',a.valid?r8_m(a.gross):'—','После восстановления себестоимости'),r8_stat('Возвратов',a.valid?r8_n(a.returns):'—','Проверены ссылки на чеки')])+
 r8_panel('Сверка филиалов',`<div class="r8-controls">${r8_select('ledgerStore','Выберите филиал',params.store,r8_stores(ws))}</div>`+r8_notices(a.errors)+
 r8_tbody(['Филиал','Чеки','Единицы','Возвраты','Чистая выручка','Валовая прибыль'],(a.byStore||[]).map(x=>[x.storeId,r8_n(x.receipts),r8_n(x.units),r8_n(x.returns),r8_m(x.netRevenue),r8_m(x.gross)]))+
 `<div class="r8-ledger">${r8_row('Оплачено',r8_m(a.revenue))}${r8_row('Возврат денег',r8_m(a.refund))}${r8_row('Себестоимость продаж',r8_m(a.cost))}${r8_row('Восстановленная себестоимость',r8_m(a.restoredCost))}${r8_row('Итоговая валовая прибыль',r8_m(a.gross))}</div>`+
 `<div class="r8-actions">${r8_btn('r8-ledger-csv','Скачать сверку CSV','primary',!a.valid)}</div>`+
 r8_note(a.valid?a.claim:'Сначала примите хотя бы одну таблицу чеков и, при необходимости, возвраты.'));
}
export function renderR8Availability(ws,params){const a=availabilityPlan(ws,params);
 return r8_head('03','AVAILABILITY ENGINE','Не потерять запрос. <em>Проверить наличие.</em>','Сопоставляем неудовлетворённый запрос с текущим остатком другого филиала. Ни один товар и запрос не распределяются дважды.')+r8_stamp(ws)+
 r8_stats([r8_stat('Не закрытых запросов',r8_n(a.gapCount),'Нет связанного чека и наличия в магазине'),r8_stat('Сценарных маршрутов',r8_n(a.routes?.length),'Пока без резерва товара'),r8_stat('Результат после затрат',r8_m(a.net),'Гипотеза, не прирост'),r8_stat('Маржа неизвестна',r8_n(a.unknownMargin),'Нет чеков для оценки SKU')])+
 r8_panel('Ограничения сценария',`<div class="r8-controls">${r8_field('moveReserve','Резерв источника, шт.',params.reserve,{max:10000})}${r8_field('moveProbability','Вероятность покупки, %',params.probability,{max:100})}${r8_field('moveFixed','Фиксированная логистика, ₽',params.fixedCost,{max:1000000,step:50})}${r8_field('moveUnit','Логистика за единицу, ₽',params.unitCost,{max:1000000,step:50})}</div>`+r8_notices(a.errors)+
 r8_tbody(['Запрос','Точка спроса','Источник','Артикул / размер','Нетто сценария','Статус'],(a.routes||[]).slice(0,40).map(x=>[x.requestId,x.storeId,x.fromStoreId,x.sku+' / '+x.size,r8_m(x.net),x.consent?'Есть согласие':'Нет согласия']))+
 `<div class="r8-actions">${r8_btn('r8-move-csv','Маршруты в CSV','primary',!a.valid)}${r8_btn('r8-move-task','Поставить задачу проверки','',!(a.routes?.length))}</div>`+
 r8_note(a.disclaimer||'Доступность и прогноз не подтверждены.')+((a.latestStockDate&&a.latestStockDate!==AS_OF)?r8_notices(['Снимок на '+a.latestStockDate+' устарел — перемещения заблокированы.']):''));
}
export function renderR8Recovery(ws,params){const p=recoveryPilot(ws,params);
 return r8_head('04','CONSENT-SAFE TEST','Покупателя можно вернуть. <em>Но сначала проверить.</em>','Только обращения с согласием и без связанного чека. Фиксируем контрольную группу; сообщения система не отправляет.')+r8_stamp(ws)+
 r8_stats([r8_stat('Допустимых обращений',r8_n(p.candidates),'Это события, не люди'),r8_stat('Тестовая группа',r8_n(p.test?.length),'Согласие есть'),r8_stat('Контроль',r8_n(p.control?.length),'Никакого контакта'),r8_stat('Сценарный результат',r8_m(p.expectedNet),'Не доказанная прибыль')])+
 r8_panel('Правила контролируемого пилота',`<div class="r8-controls">${r8_field('testShare','Доля теста, %',params.testShare,{min:1,max:99})}${r8_field('lift','Предполагаемый прирост, п.п.',params.lift,{max:100})}${r8_field('notificationCost','Цена обработки запроса, ₽',params.notificationCost,{max:1000000})}${r8_field('fixedCost','Расходы на пилот, ₽',params.fixedCost,{max:1000000})}${r8_field('maxInvites','Максимум обращений',params.maxInvites,{max:1500})}<label class="r8-field"><span>Ключ распределения</span><input data-r8-field="pilotSeed" maxlength="32" value="${r8_e(params.seed)}"/></label></div>`+r8_notices(p.errors)+
 `<div class="r8-ledger">${r8_row('Согласий без покупки',r8_n(p.candidates))}${r8_row('Отсечены (нет согласия или уже покупка)',r8_n(p.excluded))}${r8_row('Расходы',r8_m(p.cost))}${r8_row('Ожидаемая валовая маржа до расходов',r8_m(p.expectedGross))}${r8_row('Достаточность выборки',p.goodSample?'Не менее 20 обращений на группу':'Недостаточно для уверенного сравнения')}</div>`+
 r8_tbody(['Обращение','Филиал','SKU / размер','Группа'],[...(p.test||[]).slice(0,5),...(p.control||[]).slice(0,5)].map(x=>[x.requestId,x.storeId,x.sku+' / '+x.size,x.arm==='test'?'Тест':'Контроль']))+
 `<div class="r8-actions">${r8_btn('r8-pilot-csv','Выгрузить распределение','primary',!p.valid)}${r8_btn('r8-pilot-task','Зафиксировать пилот','',!(p.candidates>0))}</div>`+
 r8_note(p.disclaimer||'Пока нет согласованных данных и чека — оценка не производится.'));
}
export function renderR8Brief(ws,options,history){const b=r8OwnerBrief(ws,options,history),check=inspectWorkingSet(ws);
 return r8_head('05','DIRECTOR SIGN-OFF','Решение без иллюзий. <em>Доказательства рядом.</em>','Пять утверждений с типом источника, формулой и ограничениями. Сохранение только агрегата, без сырого CSV.')+r8_stamp(ws)+
 r8_stats([r8_stat('Принятых источников',r8_n(b.sourceTypes.length),'Из четырёх типов CSV'),r8_stat('Утверждений',r8_n(b.claims.length),'С разделением факта и сценария'),r8_stat('Решений в истории',r8_n(history.length),'Агрегаты в браузере'),r8_stat('Готовность',check.valid?'Формально':'Нужна сверка','Не аудиторское заключение')])+
 `<div class="r8-columns">${r8_panel('Пять проверяемых утверждений',`<div class="r8-claims">${b.claims.map((x,i)=>`<article><div><span>0${i+1}</span><b>${r8_e(x.status)}</b></div><h3>${r8_e(x.label)}</h3><strong>${x.value==null?'Нет данных':r8_n(x.value)+(i>0&&[1,2,4].includes(i)?' ₽':'')}</strong><p>${r8_e(x.method)}</p></article>`).join('')}</div>`+r8_notices(b.errors)+r8_note(b.disclaimer))}
 ${r8_panel('Управленческое решение',`${r8_select('briefStatus','Решение управляющего',options.status||'needs-review',[['needs-review','Проверить источник'],['reviewed','Изучено, требуется пилот'],['rejected','Не принимать решение']])}`+
 `<div class="r8-actions">${r8_btn('r8-brief-save','Зафиксировать проверку','primary',!b.valid)}${r8_btn('r8-brief-pdf','Скачать PDF','',!b.valid)}${r8_btn('r8-brief-csv','CSV с формулами','',!b.valid)}${r8_btn('r8-audit-csv','Экспорт журнала','',!history.length)}</div>`+
 `<p class="r8-note">После обновления страницы сырые CSV исчезнут. В журнале остаются только пять агрегированных показателей, статус и контрольная сумма. Контрольная сумма не является цифровой подписью.</p>`+
 r8_tbody(['№','Дата','Решение','Чеков','Валовая прибыль','Контроль'],history.slice().reverse().slice(0,12).map(x=>[x.seq,x.date,x.status,r8_n(x.receiptCount),r8_m(x.gross),x.fingerprint]))+
 `${r8_btn('r8-audit-clear','Очистить локальную историю','muted',!history.length)}`)}</div>`;
}
