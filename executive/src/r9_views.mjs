/** ATELIER R9 / quiet-luxury editorial finance views. Escapes all CSV-derived text. */
import {R9_SCHEMA,r9Reconcile,r9Settlements,r9Cases,r9DailyClose,r9Pack} from './r9_core.mjs';
import {inspectWorkingSet} from './r8_core.mjs';
const r9e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const r9n=n=>n==null?'—':Number(n).toLocaleString('ru-RU',{maximumFractionDigits:2});
const r9m=n=>n==null?'Нет подтверждения':r9n(n)+' ₽';
const r9head=(n,eyebrow,title,subtitle)=>`<section class="r9-intro"><div class="r9-index">R9 / ${n} — EXECUTIVE CONTROL</div><p class="eyebrow">${r9e(eyebrow)}</p><h1>${title}</h1><p class="r9-subtitle">${r9e(subtitle)}</p></section>`;
const r9badge=(label,kind='neutral')=>`<span class="r9-badge r9-${kind}">${r9e(label)}</span>`;
const r9btn=(action,label,variant='secondary',disabled=false)=>`<button type="button" class="r9-btn ${variant}" data-action="${action}" ${disabled?'disabled':''}>${r9e(label)}</button>`;
const r9box=(title,content,caption='')=>`<section class="r9-box"><header><h2>${r9e(title)}</h2>${caption?`<small>${r9e(caption)}</small>`:''}</header>${content}</section>`;
const r9line=(label,value)=>`<div class="r9-line"><span>${r9e(label)}</span><b>${r9e(value)}</b></div>`;
const r9stats=rows=>`<div class="r9-stats">${rows.map(([label,value,caption])=>`<div class="r9-stat"><small>${r9e(label)}</small><strong>${r9e(value)}</strong><span>${r9e(caption||'')}</span></div>`).join('')}</div>`;
const r9notice=(text,isBad=false)=>`<div class="r9-notice ${isBad?'bad':''}">${r9e(text)}</div>`;
const r9issues=messages=>messages.length?`<div role="alert" class="r9-errors">${messages.slice(0,7).map(m=>`<p>${r9e(m)}</p>`).join('')}</div>`:'';
const r9table=(labels,rows)=>`<div class="r9-table-wrap"><table class="r9-table"><thead><tr>${labels.map(x=>`<th>${r9e(x)}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map(r=>`<tr>${r.map(x=>`<td>${r9e(x)}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${labels.length}" class="r9-empty">Данных для этой таблицы пока нет</td></tr>`}</tbody></table></div>`;
const r9_field=(key,label,value,{min=0,max=30,step=1}={})=>`<label class="r9-field"><span>${r9e(label)}</span><input type="number" data-r9-field="${key}" value="${value}" min="${min}" max="${max}" step="${step}" /></label>`;
const r9_select=(key,label,value,items)=>`<label class="r9-field"><span>${r9e(label)}</span><select data-r9-field="${key}">${items.map(([v,t])=>`<option value="${r9e(v)}" ${value===v?'selected':''}>${r9e(t)}</option>`).join('')}</select></label>`;
const stamp=(ws,file)=>{const s=inspectWorkingSet(ws);return `<div class="r9-stamp">${r9badge('Локально, без API')}${r9badge(s.example?'УЧЕБНЫЙ CSV':s.counts.sales?'ФАЙЛЫ ПОЛЬЗОВАТЕЛЯ':'НЕТ ПРИНЯТОГО CSV',s.example?'warn':'neutral')}${r9badge(file.revision?'Версия '+file.revision:'Нет принятого реестра')}${r9badge('Синтетические цифры не смешиваются','warn')}</div>`;};

export function renderR9Vault(ws,file,form){const s=inspectWorkingSet(ws),count=file.operations.length+file.settlements.length;
 return r9head('01','PAYMENT DATA ROOM','Оплаты. <em>Только подтверждаемые строки.</em>','Импорт операций кассы/эквайринга и реестра банковских зачислений. Никаких запросов в банк: содержимое файлов предоставляете вы.')+stamp(ws,file)+
 r9stats([['Чеков в R8',r9n(s.counts.sales),'Требуются до загрузки'],['Платёжных операций',r9n(file.operations.length),'Оплата и возврат'],['Зачислений',r9n(file.settlements.length),'Пакеты по batchId'],['Сырой CSV после обновления','0 файлов','RAM-only, без localStorage']])+
 `<div class="r9-grid">${r9box('Импорт с атомарной проверкой',
 r9_select('kind','Файл для загрузки',form.kind,[['operations','Операции кассы и эквайринга'],['settlements','Банковские зачисления']])+`<label class="r9-file"><span>Выберите локальный CSV (до 1,2 МБ)</span><input type="file" accept=".csv,text/csv" data-r9-file aria-label="Загрузить CSV R9" /></label>`+
 `<label class="r9-field"><span>Или вставьте строки CSV</span><textarea rows="8" data-r9-text spellcheck="false" placeholder="id;date;storeId;...">${r9e(form.text)}</textarea></label>`+
 `<p class="r9-mini">Ожидаемые столбцы: <code>${r9e(R9_SCHEMA[form.kind].join(';'))}</code></p>`+r9issues(form.errors)+
 `<div class="r9-actions">${r9btn('r9-accept','Проверить и принять','primary',!form.text.trim()||!s.counts.sales)}${r9btn('r9-examples','Загрузить учебный комплект')}${r9btn('r9-clear','Очистить реестры','muted',!count)}</div>`+
 r9notice('Старые данные остаются нетронутыми, если хотя бы одна строка ошибочна. При изменении чеков R8 платёжные файлы сбрасываются.'))}
 ${r9box('Договор источников',`<div class="r9-contract"><p><b>OPERATIONS</b> — каждая операция со ссылкой на чек или документ возврата. Частичные оплаты поддерживаются. Суммы всегда положительные, тип определяет знак.</p><p><b>SETTLEMENTS</b> — строки фактического зачисления по storeId и batchId. Сумма может быть отрицательной при возврате средств.</p><p><b>COMMISSION</b> — комиссия по операции, не включённая в выручку. Для наличных должна равняться нулю.</p><p><b>Согласование</b> — совпадение CSV не доказывает подлинность банковского документа или отсутствие мошенничества.</p></div>`+
 r9table(['Источник','Строки','Версия'],[['Чеки R8',r9n(s.counts.sales),s.version],['Возвраты R8',r9n(s.counts.returns),s.version],['Платёжные операции',r9n(file.operations.length),file.revision],['Зачисления банка',r9n(file.settlements.length),file.revision]])+
 `<div class="r9-actions">${r9btn('r9-operations-sample','Шаблон операций CSV')}${r9btn('r9-settlements-sample','Шаблон зачислений CSV')}</div>`,'LOCAL SOURCE CONTRACT')}</div>`;
}
export function renderR9Matching(ws,file){const r=r9Reconcile(ws,file);
 return r9head('02','DOCUMENT MATCHING','Чек ≠ поступление. <em>Проверим связь.</em>','Каждая оплата сопоставляется с документом продажи, каждый возврат — с подтверждённым возвратным документом. Несоответствия остаются видимыми.')+stamp(ws,file)+r9issues(r.errors)+
 (r.valid?r9stats([['Чеков и возвратов',r9n(r.summary.documents),'Документы R8'],['Совпали по суммам',r9n(r.summary.matched),'Проверка с разделением оплат'],['Операций после возвратов',r9m(r.summary.observedNet),'Пользовательский файл'],['Разница с документами',r9m(r.summary.difference),'Не является автоматическим убытком']])+
 `<div class="r9-grid">${r9box('Сверка по документу',r9table(['Тип','Филиал','Документ','Требуется','По операциям','Разница','Статус'],r.rows.slice(0,40).map(x=>[x.kind==='capture'?'Продажа':'Возврат',x.storeId,x.ref,r9m(x.required),r9m(x.received),r9m(x.difference),x.status==='matched'?'Совпало':x.status==='short'?'Недоплата':'Избыточная сумма']))+
 `<div class="r9-actions">${r9btn('r9-matching-csv','Скачать расхождения CSV','primary')}</div>`,'Таблица ограничена 40 документами')}
 ${r9box('Водопад денег',r9line('Продажи по документам',r9m(r.summary.expectedSales))+r9line('Возвраты по документам','− '+r9m(r.summary.expectedRefunds))+r9line('Оплаты по реестру',r9m(r.summary.observedCaptures))+r9line('Возвраты по реестру','− '+r9m(r.summary.observedRefunds))+r9line('Комиссии','− '+r9m(r.summary.fees))+`<div class="r9-major">${r9m(r.summary.observedAfterFees)}<small>Валовая прибыль по документам за вычетом комиссии; не доказанный банковский остаток</small></div>`+
 r9notice('Частичные оплаты суммируются. Операции без чеков, другая дата или другой филиал требуют проверки.'))}</div>`:
 r9box('Нет основы для сверки',r9notice('Загрузите чеки в R8 и операции в R9. Показатели не вычисляются из отсутствующих файлов.')));
}
export function renderR9Bank(ws,file,opts){const p=r9Settlements(ws,file,opts),audit=r9Reconcile(ws,file),close=r9DailyClose(ws,file,audit);
 return r9head('03','SETTLEMENT & CASH CLOSE','Платёж принят. <em>Зачислен ли пакет?</em>','Сверка эквайринговых пакетов с предоставленной выпиской; видны задержки и отличие даты продажи от даты оплаты.')+stamp(ws,file)+r9issues(p.errors)+
 (p.valid?r9stats([['Банковских пакетов',r9n(p.totals.batches),'Из операций card'],['Подтверждено по файлам',r9n(p.totals.matched),'Точное совпадение суммы'],['Без строки выписки',r9n(p.totals.pending),'Не означает потерю денег'],['Сумма пакетов, расчётная',r9m(p.totals.expected),'До внешней банковской проверки']])+
 `<div class="r9-grid">${r9box('Пакеты и зачисления',r9_field('maxLagDays','Допустимая задержка зачисления, дней',opts.maxLagDays)+
 r9table(['Филиал','Пакет','Расчёт','Выписка','Задержка','Статус'],p.batches.slice(0,40).map(x=>[x.storeId,x.batchId,r9m(x.expected),r9m(x.received),x.lagDays==null?'—':x.lagDays+' дн.',x.status==='matched'?'Совпало':x.status==='not-provided'?'Не подтверждено':'Расхождение']))+
 `<div class="r9-actions">${r9btn('r9-bank-csv','Экспорт сверки пакетов','primary')}</div>`,'Кассовые операции не относятся к банковскому пакету')}
 ${r9box('Закрытие по датам',r9table(['Дата','Филиал','Документы','Операции','Комиссии','Сдвиг по датам'],(close.days||[]).slice(0,35).map(x=>[x.date,x.storeId,r9m(x.documents),r9m(x.events),r9m(x.fees),r9m(x.timingDifference)]))+
 `<div class="r9-actions">${r9btn('r9-daily-csv','Экспорт ежедневного закрытия')}</div>`+r9notice(close.disclaimer||'Дата проведения может отличаться от даты продажи.'))}</div>`:
 r9box('Загрузка не завершена',r9notice('Нужны валидные операции и документы R8. Без банковской выгрузки статусы останутся неподтверждёнными.')));
}
export function renderR9Exceptions(ws,file,opts,triage){const a=r9Reconcile(ws,file),b=r9Settlements(ws,file,opts),c=r9Cases(a,b,triage);
 const issue=c.items.find(x=>x.key===opts.selected)||c.items[0];
 return r9head('04','EXCEPTION WORKFLOW','Расхождения — <em>в контроль, не в догадки.</em>','Каждый сигнал получает статус, проверку и документированную причину закрытия. Это локальный план работы, не банковская проводка.')+stamp(ws,file)+r9stats([['Найдено сигналов',r9n(c.total),'Сверка платежей и пакетов'],['Критичные',r9n(c.critical||0),'Требуют проверки'],['Закрыто с причиной',r9n(c.closed),'Не означает исчезновение проблемы'],['Сохранение исходных строк','Нет','Только в памяти открытой страницы']])+r9issues(a.errors)+
 `<div class="r9-grid">${r9box('Реестр исключений',r9table(['Кейс','Филиал','Тип','Разница','Статус'],c.items.slice(0,40).map(x=>[x.key,x.storeId,x.kind,r9m(x.difference),x.status]))+
 `<div class="r9-actions">${r9btn('r9-cases-csv','Экспорт обезличенных кейсов','primary',!c.valid)}</div>`,'Хеш вместо исходного номера документа')}
 ${r9box('Протокол конкретного расхождения',issue?`${r9_select('selected','Кейс',issue.key,c.items.map(x=>[x.key,x.key+' · '+x.kind+' · '+x.storeId]))}`+
 r9line('Описание',issue.description)+r9line('Ожидалось',r9m(issue.expected))+r9line('По CSV',r9m(issue.observed))+r9line('Текущий статус',issue.status)+
 `${r9_select('reason','Причина проверки',opts.reason,[['','Выберите документированную причину'],['statement-checked','Сверена выписка вручную'],['pos-corrected','Исправлено в POS вне приложения'],['time-lag-confirmed','Подтверждён временной лаг'],['duplicate-cleared','Дубль исключён по документам'],['manual-review','Проверено ответственным']])}`+
 `<label class="r9-field"><span>Код подтверждающего документа (не имя покупателя)</span><input data-r9-field="evidenceId" value="${r9e(opts.evidenceId||'')}" maxlength="40" placeholder="ACT-2026-001" /></label><div class="r9-actions">${issue.status==='new'?r9btn('r9-triage-start','Начать проверку','primary'):
 issue.status==='checking'?r9btn('r9-triage-close','Закрыть с выбранной причиной','primary',!opts.reason||!(opts.evidenceId||'').trim())+r9btn('r9-triage-reset','Вернуть в очередь'):
 r9btn('r9-triage-reopen','Открыть повторно','primary')}</div>`:
 r9notice('Нет расхождений для обработки. Внешняя независимая проверка источников всё равно требуется.'))}</div>`;
}
export function renderR9Cfo(ws,file,opts,triage,history){const pack=r9Pack(ws,file,triage,opts);
 return r9head('05','CFO CONTROL MEMORANDUM','Решение собственника. <em>С проверяемой основой.</em>','Одностраничный PDF и два вида CSV: только агрегированные результаты, явно помеченные ограничения и локальная история решения.')+stamp(ws,file)+r9issues(pack.errors)+
 (pack.valid?r9stats([['Документов',r9n(pack.audit.summary.documents),'Чеки + возвраты'],['Расхождений',r9n(pack.cases.total),'Включая пакет банка'],['Закрыто с причиной',r9n(pack.cases.closed),'Проверка персоналом'],['Банковская сверка',pack.closeReady?'По CSV совпало':'Нужна проверка','Не проверка подлинности выписки']])+
 `<div class="r9-grid">${r9box('Доказательные утверждения',`<div class="r9-claims">${pack.claims.map((x,i)=>`<article><small>0${i+1} / ${r9e(x.kind)}</small><h3>${r9e(x.label)}</h3><strong>${i===5?r9n(x.value):r9m(x.value)}</strong><p>${r9e(x.method)}</p></article>`).join('')}</div>`+
 `<div class="r9-actions">${r9btn('r9-cfo-pdf','Скачать реальный PDF','primary')}${r9btn('r9-cfo-csv','Экспорт финансового досье')}</div>`+pack.warnings.map(x=>r9notice(x)).join(''))}
 ${r9box('Статус управленческого решения',r9_select('status','Заключение',opts.status,[['requires-check','Источник требует независимой сверки'],['reviewed','Изучено, решение отложено до проверки'],['rejected','Данные отклонены']])+
 `<div class="r9-actions">${r9btn('r9-cfo-save','Сохранить агрегированный акт','primary')}${r9btn('r9-signoff-csv','История актов в CSV','',!history.length)}${r9btn('r9-history-clear','Очистить историю','muted',!history.length)}</div>`+
 r9table(['№','Дата','Решение','Расхождений','Совпавших пакетов','Хеш'],history.slice(-12).reverse().map(x=>[x.seq,x.date,x.status,x.issues,x.matchedBatches,x.fingerprint]))+
 r9notice('В журнал записываются только агрегаты, статус и некриптографическая контрольная сумма. Телефоны и исходные CSV не сохраняются.'))}</div>`:
 r9box('Досье ещё нельзя составить',r9notice('Примите проверенные чеки и платёжные операции. При неполных данных приложение не создаёт фиктивный финансовый итог.')));
}
