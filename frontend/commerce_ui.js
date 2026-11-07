/* OSMANX R0.5 — readable, anonymous and explicit retail operations. */
const fittingReason={none:'Не указано',fit:'Не подошла посадка',price:'Не подошла цена',size:'Не подошёл размер',quality:'Качество',other:'Другое'};
const returnReason={size:'Размер',fit:'Посадка',quality:'Качество',different:'Не соответствует ожиданиям',other:'Другое'};
const holdStatus={held:'Активный резерв',collected:'Выдан со склада',cancelled:'Отменён',expired:'Истёк'};
const decisionStatus={new:'Новый',testing:'Проверяем',done:'Проверено',dismissed:'Не актуально'};
const rub=(ctx,kopeks)=>ctx.money(Number(kopeks||0)/100);
const alert=(ctx,msg)=>`<div class="commerce-caution">${ctx.icon('alert',18)}<span>${ctx.esc(msg)}</span></div>`;
const actionsAllowed=ctx=>['owner','manager'].includes(ctx.state.user?.role);

export function reservationsView(ctx){
 const {state,heading,pane,icon,esc,integer,shortDate}=ctx;
 const active=state.reservations.filter(r=>r.status==='held'&&new Date(r.expires_at).getTime()>Date.now());
 return `${heading('Резервы между филиалами','Подтверждайте наличие и удерживайте размер без двойного бронирования.',
 `<button class="secondary-btn" data-nav="demand">${icon('shirt')} К незакрытым запросам</button>`)}
 <div class="content-grid">
 <div class="span-3">${ctx.cardStat('Активные резервы',integer(active.length),'layers',null,'не являются продажами')}</div>
 <div class="span-3">${ctx.cardStat('Выданы',integer(state.reservations.filter(r=>r.status==='collected').length),'bag',null,'складские выдачи')}</div>
 <div class="span-6">${pane('Как это работает',`<p class="tip">Откройте запрос в разделе «Спрос и размеры», нажмите «Найти размер», затем «Зарезервировать». Свободный остаток уменьшается немедленно. Выдача уменьшает физический остаток, но не создаёт кассовый чек.</p>`)}</div>
 <div class="span-12">${pane('Журнал резервов',state.reservations.length?`<div class="panel-overflow"><table class="list-table"><thead><tr><th>Товар</th><th>Филиал-источник</th><th>Количество</th><th>Статус</th><th>Действует до</th><th>Действия</th></tr></thead><tbody>${state.reservations.map(r=>{
 const expired=r.status==='held'&&new Date(r.expires_at).getTime()<=Date.now();
 const status=expired?'expired':r.status;
 return `<tr><td><strong>${esc(r.product)}</strong><small class="muted commerce-muted">${esc(r.size||'—')} / ${esc(r.color||'—')} · ${esc(r.sku)}</small></td>
 <td>${esc(r.source_name)}</td><td>${integer(r.quantity)} шт.</td><td><span class="status ${status==='held'?'converted':'open'}">${esc(holdStatus[status]||status)}</span></td><td>${shortDate(r.expires_at)}</td><td>${status==='held'&&actionsAllowed(ctx)?`<div class="inline-actions"><button class="secondary-btn small-btn" data-hold-action="${r.id}:collect">Выдан</button><button class="ghost-btn small-btn" data-hold-action="${r.id}:cancel">Отменить</button></div>`:'—'}</td></tr>`}).join('')}</tbody></table></div>`:ctx.miniEmpty('layers','Резервов пока нет','Найдите размер из открытого запроса и оформите первый резерв.'))}</div>
 <div class="span-12">${pane('Важно',alert(ctx,'Не выдавайте товар без фактического подтверждения сотрудника. Выдача не означает продажу; для признания продажи требуется отдельный кассовый чек.'))}</div>
 </div>`;
}

export function fittingsView(ctx){
 const {state,heading,pane,icon,integer,esc,shortDate}=ctx;const d=state.fittings||{products:[],reasons:[],recent:[]};
 const trials=d.products.reduce((s,v)=>s+v.trials,0),sales=d.products.reduce((s,v)=>s+v.purchases,0);
 return `${heading('Аналитика примерочных','Какие вещи примеряют, но не покупают. Только обезличенные агрегаты.',actionsAllowed(ctx)?`<button class="primary-btn" data-dialog="fitting">${icon('plus')} Записать примерки</button>`:'')}
 <div class="content-grid">
 <div class="span-3">${ctx.cardStat('Примерки',integer(trials),'shirt',null,'по журналу')}</div>
 <div class="span-3">${ctx.cardStat('Покупки после примерок',integer(sales),'bag',null,'по наблюдениям')}</div>
 <div class="span-3">${ctx.cardStat('Доля покупок',trials?((100*sales/trials).toFixed(1)+'%'):'—','target',null,'в рамках журнала')}</div>
 <div class="span-3">${ctx.cardStat('Моделей',integer(d.products.length),'layers',null,'в выборке')}</div>
 <div class="span-8">${pane('Примерки по моделям',d.products.length?`<div class="panel-overflow"><table class="list-table"><thead><tr><th>Товар / размер</th><th>Примерки</th><th>Покупки</th><th>Доля</th></tr></thead><tbody>${d.products.map(r=>`<tr><td><strong>${esc(r.product)}</strong><small class="commerce-muted muted">Размер ${esc(r.size||'—')}</small></td><td>${integer(r.trials)}</td><td>${integer(r.purchases)}</td><td><span class="commerce-highlight">${String(r.purchase_rate).replace('.',',')}%</span></td></tr>`).join('')}</tbody></table></div>`:ctx.miniEmpty('shirt','Нет наблюдений','Сотрудник может внести итоги примерок без записи персональных данных.'))}</div>
 <div class="span-4">${pane('Причины (по группам наблюдений)',d.reasons.length?d.reasons.map(r=>`<div class="quality-line"><span>${esc(fittingReason[r.reason]||r.reason)}</span><b>${integer(r.count)}</b></div>`).join(''):'<p class="tip">Причины пока не собраны.</p>')}</div>
 <div class="span-12">${pane('Методология',alert(ctx,'Это отдельный журнал наблюдений персонала, не видеораспознавание и не сквозной трекинг покупателей. Возможны неполные записи; доля покупок относится только к учтённым примеркам.'))}</div>
 </div>`;
}

export function returnsView(ctx){
 const {state,heading,pane,icon,integer,esc,shortDate}=ctx;const r=state.returns||{total:{quantity:0,amount_kopeks:0},reasons:[],recent:[]};
 return `${heading('Возвраты и причины','Проверяйте причины возвратов по чекам — не смешивая их с текущими продажами.',actionsAllowed(ctx)?`<button class="primary-btn" data-dialog="return">${icon('plus')} Зафиксировать возврат</button>`:'')}
 <div class="content-grid">
 <div class="span-4">${ctx.cardStat('Возвратов',integer(r.total.quantity),'layers',null,'за период')}</div>
 <div class="span-4">${ctx.cardStat('Сумма возвратов',rub(ctx,r.total.amount_kopeks),'tag',null,'по журналу')}</div>
 <div class="span-4">${ctx.cardStat('Причин',integer(r.reasons.length),'clipboard',null,'наблюдаемых категорий')}</div>
 <div class="span-5">${pane('Структура причин',r.reasons.length?r.reasons.map(x=>`<div class="quality-line"><span>${esc(returnReason[x.reason]||x.reason)}</span><b>${integer(x.quantity)} / ${rub(ctx,x.amount_kopeks)}</b></div>`).join(''):ctx.miniEmpty('clipboard','Нет возвратов','Добавьте возвращённый товар с номером существующего чека.'))}</div>
 <div class="span-7">${pane('Журнал',r.recent.length?`<div class="panel-overflow"><table class="list-table"><thead><tr><th>Дата</th><th>Чек</th><th>Товар</th><th>Причина</th><th>Сумма</th></tr></thead><tbody>${r.recent.map(x=>`<tr><td>${shortDate(x.created_at)}</td><td>№${x.sale_id}</td><td>${esc(x.item_description)}</td><td>${esc(returnReason[x.reason]||x.reason)}</td><td>${rub(ctx,x.amount_kopeks)}</td></tr>`).join('')}</tbody></table></div>`:'<p class="tip">Пока ничего не зарегистрировано.</p>')}</div>
 <div class="span-12">${pane('Ограничения учёта',alert(ctx,'Сумма возвратов не может превышать сумму чека. Возвраты не изменяют чек и не инициируют возврат средств в банке или кассе. Без построчной кассовой интеграции конкретный SKU чека не подтверждается автоматически.'))}</div>
 </div>`;
}

export function pricingView(ctx){
 const {state,heading,pane,icon,integer,esc,shortDate}=ctx;const p=state.pricing||[];
 return `${heading('Скидки и валовая прибыль','Проверьте экономику акции до запуска, не обещая непроверенного роста продаж.',actionsAllowed(ctx)?`<button class="primary-btn" data-dialog="pricing">${icon('plus')} Рассчитать скидку</button>`:'')}
 <div class="content-grid"><div class="span-4">${ctx.cardStat('Расчётов',integer(p.length),'chart',null,'сохранённых сценариев')}</div>
 <div class="span-4">${ctx.cardStat('Риск убыточной цены',integer(p.filter(x=>x.unit_profit_after_kopeks<=0).length),'alert',null,'сценариев')}</div>
 <div class="span-4">${ctx.cardStat('Срок действия', 'Не прогноз','shield',null,'ручные предположения')}</div>
 <div class="span-12">${pane('Сценарии и точка безубыточности',p.length?`<div class="panel-overflow"><table class="list-table"><thead><tr><th>Товар</th><th>Цена</th><th>Скидка</th><th>Маржа за единицу</th><th>Сколько продать для сохранения маржи</th><th>Дельта при прогнозируемом объёме</th></tr></thead><tbody>${p.map(x=>`<tr><td><strong>${esc(x.title)}</strong><small class="commerce-muted muted">${esc(x.sku)}</small></td><td>${rub(ctx,x.price_kopeks)} → ${rub(ctx,x.discounted_price_kopeks)}</td><td>${String(x.discount_bps/100).replace('.',',')}%</td><td class="${x.unit_profit_after_kopeks<=0?'red':'green'}">${rub(ctx,x.unit_profit_after_kopeks)}</td><td>${x.break_even_units==null?'Недостижимо при данной цене':integer(x.break_even_units)+' шт.'}</td><td class="${x.delta_kopeks<0?'red':'green'}">${x.delta_kopeks>0?'+':''}${rub(ctx,x.delta_kopeks)}</td></tr>`).join('')}</tbody></table></div>`:ctx.miniEmpty('tag','Нет сценариев','Введите цену, себестоимость, размер скидки и предполагаемые объёмы продаж.'))}</div>
 <div class="span-12">${pane('Принцип расчёта',alert(ctx,'Сравниваются две модели валовой прибыли по введённым себестоимости и объёмам, без аренды, налогов, возвратов и других расходов. Планируемое количество продаж — гипотеза, а не результат автоматического прогноза.'))}</div>
 </div>`;
}

export function decisionsView(ctx){
 const {state,heading,pane,icon,integer,esc}=ctx;const data=state.decisions||{items:[],methodology:''};
 const counts={high:data.items.filter(x=>x.priority==='high'&&x.status!=='done').length,
              testing:data.items.filter(x=>x.status==='testing').length,
              done:data.items.filter(x=>x.status==='done').length};
 return `${heading('Центр решений','От конкретных фактов к проверяемым действиям руководителя.',`<button class="secondary-btn" data-nav="actions">${icon('sparkle')} План экспериментов</button>`)}
 <div class="content-grid"><div class="span-4">${ctx.cardStat('Требуют внимания',integer(counts.high),'alert',null,'сигналов')}</div>
 <div class="span-4">${ctx.cardStat('На проверке',integer(counts.testing),'activity',null,'гипотез')}</div>
 <div class="span-4">${ctx.cardStat('Проверено',integer(counts.done),'check',null,'решений')}</div>
 <div class="span-12">${data.items.length?data.items.map((x,index)=>pane(`${String(index+1).padStart(2,'0')}. ${x.title}`,`<div class="commerce-evidence"><div><span class="tag ${x.priority==='high'?'demo':''}">${esc(x.kind.toUpperCase())}</span><strong>${esc(x.evidence)}</strong><p>${esc(x.suggestion)}</p></div><div class="commerce-controls"><label class="muted" for="decision-${esc(x.key)}">Статус</label><select class="select" id="decision-${esc(x.key)}" data-decision-status="${esc(x.key)}" ${!actionsAllowed(ctx)?'disabled':''}>${Object.entries(decisionStatus).map(([key,label])=>`<option value="${key}" ${x.status===key?'selected':''}>${label}</option>`).join('')}</select><input class="input" data-decision-note="${esc(x.key)}" value="${esc(x.note||'')}" maxlength="1000" placeholder="Комментарий к действию" ${!actionsAllowed(ctx)?'disabled':''}/>${actionsAllowed(ctx)?`<button class="secondary-btn" data-decision-save="${esc(x.key)}">Сохранить</button>`:''}</div></div>`,'commerce-decision')).join(''):
 pane('Нет сигналов',ctx.miniEmpty('check','Данных пока недостаточно','Добавьте наблюдения или запросы на отсутствующие размеры.'))}</div>
 <div class="span-12">${pane('Ограничения',alert(ctx,data.methodology||'Рекомендации являются гипотезами и требуют проверки.'))}</div>
 </div>`;
}
