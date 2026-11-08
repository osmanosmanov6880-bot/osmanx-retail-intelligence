/**
 * OSMANX ATELIER R4 — five evidence-led decision workflows, pure and deterministic.
 * All inputs are synthetic. Calculations are *scenarios*, never proven incremental profit.
 */
import {AS_OF, STORES, CATEGORIES, product, safeRatio} from './model.mjs';
import {reconcileEvidence} from './r3_core.mjs';

const r4Sum=(xs,fn)=>xs.reduce((v,x)=>v+fn(x),0);
const r4Finite=n=>typeof n==='number'&&Number.isFinite(n);
const r4Nonneg=n=>r4Finite(n)&&n>=0;
const r4Natural=n=>Number.isSafeInteger(n)&&n>=0;
const r4Clip=(x,lo,hi)=>Math.max(lo,Math.min(hi,x));
const r4Round=n=>Math.round((n+Number.EPSILON)*100)/100;
const r4Streams=[
 ['sales','Чеки','Синтетический POS / схема выгрузки'],['returns','Возвраты','Синтетический возвратный документ'],
 ['requests','Невидимый спрос','Добровольное обращение'],['stock','Остатки','Синтетический учётный снимок'],
 ['fittings','Примерочные','Ручная фиксация'],['assistance','Обращения за помощью','QR-событие'],
 ['traffic','Поток','Агрегированный счётчик'],['audits','Сверки наличия','Выборочная инвентаризация'],
 ['transfers','Перемещения','Учётная операция'],['preorders','Предзаказы','Добровольная заявка'],
 ['preferences','Пожелания','Опрос']
];
const r4DateValid=d=>typeof d==='string'&&/^\d{4}-\d\d-\d\d$/.test(d)&&!Number.isNaN(Date.parse(d+'T12:00:00Z'))&&new Date(d+'T12:00:00Z').toISOString().slice(0,10)===d&&d<=AS_OF;
const r4EventDate=(x,k)=>k==='stock'?x.asOf:x.date;

/** Audit scoped data without mistaking a book-stock snapshot for physical availability. */
export function auditEvidence(dataset,scope){
 const problems=[],coverage=[];
 const globalSales=new Map(dataset.sales.map(x=>[x.id,x]));
 const catalogIds=new Set(dataset.products.map(x=>x.id));
 const globallyReturned=new Set();
 const linkedRequests=new Set();
 for(const [key,label,source] of r4Streams){
  const events=key==='stock'?scope.stock:scope[key]||[];
  const ids=new Set();let gaps=0,errors=0;
  for(const x of events){
   const mark=(issue,severity='error')=>{problems.push({id:String(x.id||'—'),stream:key,label,issue,severity});if(severity==='error')errors++;else gaps++;};
   if(!x.id||ids.has(x.id))mark('Отсутствует или повторяется идентификатор');
   if(x.id)ids.add(x.id);
   if(!r4DateValid(r4EventDate(x,key)))mark('Некорректная дата события');
   if(x.storeId&&!STORES.some(s=>s.id===x.storeId))mark('Неизвестный филиал');
   if(x.modelId&&!catalogIds.has(x.modelId))mark('Товар не найден в каталоге');
   if(key==='sales'&&(!r4Nonneg(x.paidPrice)||!r4Nonneg(x.cost)))mark('Невалидная цена или себестоимость');
   if(key==='stock'&&(!r4Natural(x.quantity)||!x.modelId||!x.storeId))mark('Остаток не является целым неотрицательным количеством');
   if(key==='stock'&&x.asOf!==AS_OF)mark('Учётный снимок не на дату демонстрации','gap');
   if(key==='returns'){
    const sold=globalSales.get(x.saleId);
    if(!sold)mark('Возврат без исходного чека');
    else{
     if(sold.date>x.date)mark('Возврат датирован раньше продажи');
     if(sold.storeId!==x.storeId||sold.modelId!==x.modelId)mark('SKU или филиал не совпадает с чеком');
     if(x.refundedPrice>sold.paidPrice||x.reversedCost>sold.cost)mark('Сумма возврата превышает исходную сумму');
    }
    if(globallyReturned.has(x.saleId))mark('Повторное сторнирование одного чека');
    globallyReturned.add(x.saleId);
   }
   if(key==='requests'){
    if(x.consent&&!x.solutionFound)mark('Согласие без отмеченного найденного решения','gap');
    if(x.purchased){
     const sold=globalSales.get(x.saleId);
     if(!sold||sold.originRequestId!==x.id||sold.modelId!==x.modelId||sold.size!==x.size||sold.storeId!==x.storeId)mark('Покупка не связана с согласованным чеком');
     else if(sold.date<x.date)mark('Продажа раньше обращения');
     if(linkedRequests.has(x.saleId))mark('Один чек связан с несколькими покупками');
     linkedRequests.add(x.saleId);
    }
   }
   if(key==='traffic'&&(!r4Natural(x.visits)||!r4Natural(x.passers)||x.visits>x.passers))mark('Показания счётчика противоречивы');
   if(key==='assistance'&&(!r4Nonneg(x.responseSeconds)||typeof x.resolved!=='boolean'))mark('Неизвестна длительность или завершение обращения');
  }
  coverage.push({key,label,source,events:events.length,errors,gaps,ids:[...ids].slice(0,4),
   status:events.length===0?'Нет событий':errors?'Есть ошибки':gaps?'Требует уточнения':'Структура проверена'});
 }
 const bridge=reconcileEvidence(dataset,scope);
 for(const issue of bridge.issues)problems.push({id:'LEDGER',stream:'sales',label:'Чеки и связи',issue,severity:'error'});
 return {coverage,problems,critical:problems.filter(x=>x.severity==='error').length,uncertain:problems.filter(x=>x.severity==='gap').length,
  totalEvents:r4Sum(coverage,x=>x.events),bridge,
  limitations:['Все данные синтетические; настоящие интеграции с POS/1С отсутствуют.',
   'Остаток в учётном снимке не подтверждает фактическую доступность на полке.',
   'События не устанавливают причинность или доказанный прирост прибыли.'],
  usableForDescriptiveReporting:!problems.some(x=>x.severity==='error')};
}

/** Cross-store matching with a per-SKU inventory budget, no double-allocation. */
export function matchDemand(dataset,scope,options={}){
 const reserve=options.reserve===null?NaN:Number(options.reserve??0),probability=(options.probability===null?NaN:Number(options.probability??55))/100,
  transferCost=options.transferCost===null?NaN:Number(options.transferCost??350),limit=Number(options.limit??250);
 const errors=[];
 if(!r4Natural(reserve)||reserve>1000)errors.push('Резерв должен быть целым числом от 0 до 1000');
 if(!r4Finite(probability)||probability<0||probability>1)errors.push('Вероятность должна быть от 0 до 100%');
 if(!r4Nonneg(transferCost)||transferCost>1000000)errors.push('Затраты на перемещение должны быть неотрицательны');
 if(!r4Natural(limit)||limit<1||limit>2000)errors.push('Ограничение обращений: от 1 до 2000');
 if(errors.length)return {valid:false,errors,matches:[],unmatched:[],totals:null};
 const stock=new Map(dataset.stock.map(x=>[`${x.storeId}|${x.modelId}|${x.size}|${x.color}`,{
  ...x,remaining:Math.max(0,x.quantity-reserve)}]));
 const matches=[],unmatched=[],requests=[...scope.requests].filter(x=>!x.purchased)
  .sort((a,b)=>a.date.localeCompare(b.date)||a.id.localeCompare(b.id)).slice(0,limit);
 for(const request of requests){
  const p=dataset.products.find(x=>x.id===request.modelId);
  if(!p){unmatched.push({requestId:request.id,reason:'Нет модели в каталоге'});continue;}
  const key=s=>`${s.id}|${request.modelId}|${request.size}|${request.color}`;
  const local=STORES.find(x=>x.id===request.storeId),localStock=stock.get(key(local||{id:'unknown'}));
  let source=null,kind=null;
  if(localStock?.remaining>0&&localStock.asOf===AS_OF){source=localStock;kind='local';}
  else{
   const remote=STORES.filter(x=>x.id!==request.storeId).map(x=>stock.get(key(x)))
    .filter(x=>x&&x.remaining>0&&x.asOf===AS_OF).sort((a,b)=>b.remaining-a.remaining||a.storeId.localeCompare(b.storeId));
   source=remote[0]||null;kind='transfer';
  }
  if(!source){unmatched.push({requestId:request.id,reason:'Нет доступных единиц по учётному снимку с заданным резервом'});continue;}
  source.remaining--;
  const logistics=kind==='transfer'?transferCost:0;
  const unitGross=p.price-p.cost;
  matches.push({requestId:request.id,date:request.date,modelId:p.id,model:p.name,size:request.size,color:request.color,
   destinationStore:request.storeId,sourceStore:source.storeId,sourceStockId:source.id,kind,
   estimatedGross:r4Round(probability*unitGross),estimatedNet:r4Round(probability*unitGross-logistics),
   logistics,probability,price:p.price,cost:p.cost,
   sourceStatus:'Учётный снимок; обязательна физическая проверка'});
 }
 const locals=matches.filter(x=>x.kind==='local'),transfers=matches.filter(x=>x.kind==='transfer');
 return {valid:true,errors:[],matches,unmatched,considered:requests.length,totalEligible:scope.requests.filter(x=>!x.purchased).length,
  reserve,probability,transferCost,totals:{matched:matches.length,local:locals.length,remote:transfers.length,unmatched:unmatched.length,
   estimatedGross:r4Round(r4Sum(matches,x=>x.estimatedGross)),logistics:r4Round(r4Sum(matches,x=>x.logistics)),
   estimatedNet:r4Round(r4Sum(matches,x=>x.estimatedNet))},
  assumptions:'Сценарный расчёт на учётных снимках и добровольных запросах. Не резервирует товар и не доказывает дополнительные продажи.'};
}

/** SKU-level discount stress test — no demand elasticity is inferred from correlation. */
export function discountStress(dataset,scope,options={}){
 const modelId=options.modelId||'JKT-AURA',discount=(options.discount===null?NaN:Number(options.discount??10))/100,
  uplift=(options.uplift===null?NaN:Number(options.uplift??15))/100,campaignCost=options.campaignCost===null?NaN:Number(options.campaignCost??1500);
 const p=dataset.products.find(x=>x.id===modelId),errors=[];
 if(!p)errors.push('Неизвестная модель');
 if(!r4Finite(discount)||discount<0||discount>.95)errors.push('Скидка должна быть от 0 до 95%');
 if(!r4Finite(uplift)||uplift<0||uplift>5)errors.push('Изменение количества: от 0 до 500%');
 if(!r4Nonneg(campaignCost)||campaignCost>1e9)errors.push('Некорректные расходы на кампанию');
 if(errors.length)return {valid:false,errors,modelId};
 const sales=scope.sales.filter(x=>x.modelId===modelId);
 const returns=scope.returns.filter(x=>x.modelId===modelId);
 const returned=new Set(returns.map(x=>x.saleId));
 // The period may contain returns from a sale before the period. Keep gross exact;
 // do not manufacture a baseline unit count when it is <= 0.
 const baselineUnits=sales.length-returns.length;
 const baselineRevenue=r4Round(r4Sum(sales,x=>x.paidPrice)-r4Sum(returns,x=>x.refundedPrice));
 const baselineCogs=r4Round(r4Sum(sales,x=>x.cost)-r4Sum(returns,x=>x.reversedCost));
 const baselineGross=r4Round(baselineRevenue-baselineCogs);
 const validBaseline=baselineUnits>0;
 const newPrice=r4Round(p.price*(1-discount)),unitGross=r4Round(newPrice-p.cost);
 const estimatedUnits=validBaseline?baselineUnits*(1+uplift):null;
 const scenarioGross=validBaseline?r4Round(estimatedUnits*unitGross-campaignCost):null;
 const deltaGross=scenarioGross===null?null:r4Round(scenarioGross-baselineGross);
 const breakEvenUplift=validBaseline&&unitGross>0?r4Round(((baselineGross+campaignCost)/(baselineUnits*unitGross)-1)*100):null;
 const noUplift=validBaseline?r4Round(baselineUnits*unitGross-campaignCost-baselineGross):null;
 return {valid:true,modelId,product:p,baselineUnits,baselineRevenue,baselineCogs,baselineGross,receipts:sales.map(x=>x.id),
  returnIds:returns.map(x=>x.id),validBaseline,newPrice,unitGross,discount,uplift,campaignCost,estimatedUnits,scenarioGross,
  deltaGross,breakEvenUplift,noUplift,errors:[],
  warnings:[!validBaseline?'Недостаточно чистых продаж в периоде для сценарного вывода.':null,
   unitGross<=0?'Скидка приводит к нулевой или отрицательной валовой прибыли с единицы.':null,
   'Предположение о приросте объёма вводится вручную. Цена не доказывает эластичность спроса.',
   'В сценарии неизменны себестоимость и структура возвратов. Реальный эффект необходимо измерить пилотом.'].filter(Boolean),
  provenIncrementalProfit:false};
}

const PORTFOLIO_CATALOG=[
 ['rescue','Проверить доступность размеров','Управляющий сети',6200,'demand'],
 ['inventory','Сверить спорные остатки','Руководитель склада',2400,'inventory'],
 ['fitting','Измерить причины отказов','Руководитель магазина',3400,'service'],
 ['margin','Проверить скидки на AURA','Коммерческий директор',3800,'margin'],
 ['service','Измерить задержки консультантов','Управляющий магазина',3000,'service'],
 ['retention','Проверить повторные визиты','CRM-менеджер',4200,'retention'],
 ['returns','Изучить причины возвратов','Категорийный менеджер',2500,'returns']
];
/** Capital and capacity planning: scores rank *experiments*, not proven earnings. */
export function prioritizePortfolio(dataset,scope,options={}){
 const capacity=options.capacity===null?NaN:Number(options.capacity??3),budget=options.budget===null?NaN:Number(options.budget??15000),
  costs=options.costs||{};
 const errors=[];
 if(!r4Natural(capacity)||capacity>7)errors.push('Можно выбрать от 0 до 7 проверок');
 if(!r4Nonneg(budget)||budget>1e9)errors.push('Бюджет не может быть отрицательным');
 if(errors.length)return {valid:false,errors,selected:[],candidates:[]};
 const demand=matchDemand(dataset,scope,{reserve:1,probability:55,transferCost:350});
 const margin=discountStress(dataset,scope,{modelId:'JKT-AURA',discount:10,uplift:15,campaignCost:1500});
 const counts={rescue:demand.totals?.remote||0,inventory:scope.audits.filter(x=>x.status==='Требует сверки').length,
  fitting:scope.fittings.filter(x=>!x.purchased).length,margin:scope.sales.filter(x=>x.modelId==='JKT-AURA').length,
  service:scope.assistance.filter(x=>x.responseSeconds>240).length,
  retention:new Set(scope.sales.map(x=>x.memberId).filter(Boolean)).size,returns:scope.returns.length};
 const candidates=PORTFOLIO_CATALOG.map(([id,title,owner,defaultCost,overlapGroup])=>{
  const c=costs[id]===undefined?defaultCost:costs[id]===null?NaN:Number(costs[id]),invalidCost=!r4Nonneg(c)||c>1e8;
  const sample=counts[id]||0;
  const hasModel=id==='rescue'?demand.totals.remote>0:id==='margin'?margin.validBaseline:sample>0;
  const estimate=id==='rescue'?r4Round(r4Sum(demand.matches.filter(x=>x.kind==='transfer'),x=>x.estimatedNet)):id==='margin'?margin.deltaGross:null;
  const evidenceIds=id==='rescue'?demand.matches.filter(x=>x.kind==='transfer').slice(0,12).map(x=>x.requestId):
   id==='inventory'?scope.audits.filter(x=>x.status==='Требует сверки').slice(0,12).map(x=>x.id):
   id==='fitting'?scope.fittings.filter(x=>!x.purchased).slice(0,12).map(x=>x.id):
   id==='service'?scope.assistance.filter(x=>x.responseSeconds>240).slice(0,12).map(x=>x.id):
   id==='returns'?scope.returns.slice(0,12).map(x=>x.id):
   scope.sales.filter(x=>id==='margin'?x.modelId==='JKT-AURA':!!x.memberId).slice(0,12).map(x=>x.id);
  const score=hasModel&&!invalidCost?Math.round(r4Clip(15+Math.log1p(sample)*11+(id==='rescue'&&estimate>0?26:id==='margin'&&estimate>0?10:0)-c/1800,0,100)):0;
  return {id,title,owner,overlapGroup,cost:c,invalidCost,hasEvidence:hasModel,observations:sample,evidenceIds,score,
   scenarioNet:estimate,confidence:'Гипотеза: эффект ещё не подтверждён',measurement:id==='rescue'?'Найденный товар → последующий чек':id==='margin'?'Валовая прибыль на SKU до/после':'Сопоставимый показатель до/после и контроль',
   status:!hasModel?'Недостаточно событий':invalidCost?'Некорректная стоимость':'Готово к пилотной проверке'};
 }).sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id));
 let left=budget;
 const selected=[];
 for(const row of candidates){
  if(!row.hasEvidence||row.invalidCost||selected.length>=capacity||row.cost>left)continue;
  selected.push(row);left-=row.cost;
 }
 return {valid:true,errors:[],budget,capacity,used:r4Round(budget-left),remaining:r4Round(left),candidates,selected,
  totalScenarioNet:null,overlapWarning:'Финансовые оценки пересекаются по клиентам и гипотезам. Складывать их нельзя.',
  conclusion:selected.length?'Приоритет — измерить эффект этих проверок. Решения не исполнены.':'Для выбранного бюджета и фильтров нет выполнимых проверок.'};
}

const r4CsvSafe=x=>{const s=String(x??'');const escaped=/^[\s\uFEFF]*[=+@\-]/.test(s)?"'"+s:s;return '"'+escaped.replace(/"/g,'""')+'"';};
export function dossierSnapshot(dataset,scope,options={}){
 const audit=auditEvidence(dataset,scope),matching=matchDemand(dataset,scope,{reserve:1}),
  portfolio=prioritizePortfolio(dataset,scope,options);
 const fields=['store','category','model','size','period'];
 const filters=Object.fromEntries(fields.map(k=>[k,String(scope.filter[k]??'all')]));
 const ledger=audit.bridge;
 return {schema:1,asOf:AS_OF,origin:'OSMANX · DEMONSTRATION DATA / НЕ РЕАЛЬНЫЙ АУДИТ',scenario:dataset.scenarioId,
  filters,period:{from:scope.from,to:scope.to},totals:{revenue:ledger.revenue,cogs:ledger.cogs,gross:ledger.gross,
   relatedReceipts:ledger.linkedCount,relatedReceiptGross:ledger.linkedGross,unfulfilledRequests:scope.requests.filter(x=>!x.purchased).length},
  quality:{events:audit.totalEvents,errors:audit.critical,gaps:audit.uncertain,integrity:audit.usableForDescriptiveReporting},
  matching:{considered:matching.considered,local:matching.totals.local,remote:matching.totals.remote,unmatched:matching.totals.unmatched,
   scenarioNet:matching.totals.estimatedNet},
  priorities:portfolio.selected.map(x=>({id:x.id,title:x.title,cost:x.cost,owner:x.owner,observations:x.observations,evidenceIds:x.evidenceIds})),
  sampleEvidence:[...new Set([...ledger.linked.slice(0,7).map(x=>x.saleId),...matching.matches.slice(0,12).map(x=>x.requestId)])].slice(0,19),
  warnings:['Синтетические данные и учётные снимки; 1С не подключена.',
   'Валовая прибыль по связанным чекам не доказывает прирост прибыли.',
   'Сценарные оценки и пилоты не являются доказательством причинности.','Физический остаток, резервы и затраты требуется подтвердить.']};
}
export function dossierCsv(snapshot){
 const rows=[['Параметр','Значение','Тип'],['Источник',snapshot.origin,'Демо'],['Дата',snapshot.asOf,'Факт генерации'],
  ['Сценарий',snapshot.scenario,'Демо'],['Филиал',snapshot.filters.store,'Фильтр'],['Период',`${snapshot.period.from} — ${snapshot.period.to}`,'Фильтр'],
  ['Выручка',snapshot.totals.revenue,'Факт синтетических чеков'],['Себестоимость',snapshot.totals.cogs,'Факт синтетических чеков'],
  ['Валовая прибыль',snapshot.totals.gross,'Факт синтетических чеков'],['Валовая прибыль связанных чеков',snapshot.totals.relatedReceiptGross,'Не доказанный прирост'],
  ['Недостатки связей',snapshot.quality.errors,'Аудит'],['Запросы без связанного чека',snapshot.totals.unfulfilledRequests,'Факт обращений'],
  ['Сценарные совпадения',snapshot.matching.remote,'Нужна физическая сверка']];
 for(const p of snapshot.priorities)rows.push([`Пилот ${p.id}`,`${p.title} / ${p.owner} / ${p.cost} ₽`,'Гипотеза']);
 for(const id of snapshot.sampleEvidence)rows.push(['ID основания',id,'Синтетический источник']);
 for(const warning of snapshot.warnings)rows.push(['Ограничение',warning,'Предупреждение']);
 return '\uFEFF'+rows.map(r=>r.map(r4CsvSafe).join(';')).join('\r\n')+'\r\n';
}

/** Safe, Excel-compatible exports; formula-like cells are escaped. */
const r4AsCsv=rows=>'\uFEFF'+rows.map(r=>r.map(r4CsvSafe).join(';')).join('\r\n')+'\r\n';
export function auditCsv(audit){return r4AsCsv([['Источник','Событий','Ошибок','Пробелов','Статус'],...audit.coverage.map(x=>[x.label,x.events,x.errors,x.gaps,x.status]),
  ['ИД','Поток','Тип','Описание'],...audit.problems.map(x=>[x.id,x.label,x.severity,x.issue])]);}
export function matchingCsv(plan){return r4AsCsv([['Запрос','Дата','Модель','Размер','Откуда','Куда','Тип','Снимок','Оценка (не факт), ₽'],
  ...plan.matches.map(x=>[x.requestId,x.date,x.model,x.size,x.sourceStore,x.destinationStore,x.kind,x.sourceStockId,x.estimatedNet]),
  ...plan.unmatched.map(x=>[x.requestId,'','','','','','нет варианта',x.reason,''])]);}
export function portfolioCsv(portfolio){return r4AsCsv([['Приоритет','Описание','Оснований','Бюджет, ₽','Ответственный','Статус','Денежный сценарий (не доказан), ₽'],
  ...portfolio.candidates.map(x=>[x.id,x.title,x.observations,x.cost,x.owner,x.status,x.scenarioNet??'Неизвестно'])]);}
