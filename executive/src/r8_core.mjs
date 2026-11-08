/** ATELIER R8 — five auditable operational decision engines.
 * All inputs are synthetic. This file has no UI, network calls or side effects.
 * Source evidence is read from observed events; uncertain financial assumptions
 * are never passed off as proved incrementality.
 */
import {AS_OF,STORES,product} from './model.mjs';
import {safeCsv} from './r5_core.mjs';

const r8_sum=(rows,fn)=>rows.reduce((a,x)=>a+fn(x),0);
const r8_day=s=>Number.isFinite(Date.parse(String(s)+'T12:00:00Z'));
const r8_shift=(iso,days)=>{const d=new Date(iso+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+days);return d.toISOString().slice(0,10)};
const r8_days=(a,b)=>Math.round((Date.parse(b+'T12:00:00Z')-Date.parse(a+'T12:00:00Z'))/86400000)+1;
const r8_range=(v,min,max,int=false)=>typeof v==='number'&&Number.isFinite(v)&&v>=min&&v<=max&&(!int||Number.isInteger(v));
const r8_round=v=>Math.round(v*100)/100;
const r8_hash=s=>{let h=2166136261;for(const ch of String(s))h=Math.imul(h^ch.charCodeAt(0),16777619)>>>0;return h>>>0};
const r8_store=id=>STORES.find(x=>x.id===id)?.name||id;
const r8_matches=(x,filter={})=>(!filter.store||filter.store==='all'||filter.store===x.storeId)&&(!filter.category||filter.category==='all'||product(x.modelId).category===filter.category)&&(!filter.model||filter.model==='all'||filter.model===x.modelId)&&(!filter.size||filter.size==='all'||filter.size===x.size);
const r8_sorted=(values,limit=30)=>[...new Set(values)].sort().slice(0,limit);
const r8_empty=(errors)=>({valid:false,errors,rows:[],daily:[],sizes:[],approved:[],evidenceIds:[],total:0,observed:0,rate:null,delta:null,previousTotal:0,previousRate:null,comparable:false,days:0,totalEvents:0,breaches:0,extraStaff:0,cost:0,eligible:0,holdout:0,treatment:0,experimentFeasible:false,net:0,n:0,baselineGrossProfit:0,baseNet:0,breakEven:null,operatingCost:0,spent:0,units:0,shortage:0,hasOpportunity:false,disclaimer:'Сначала исправьте недопустимые параметры.'});
export const R8_RELEASE='R8';

/** 1. Temporal signal radar; equal-length windows, no fabricated weekday/time-of-day data. */
export function demandRadar(dataset,scope,{windowDays=14,minSample=5,signal='unresolved'}={}){
 const errors=[];
 if(!r8_range(windowDays,1,45,true))errors.push('Окно наблюдения: целое 1–45 дней');
 if(!r8_range(minSample,1,500,true))errors.push('Порог выборки: целое 1–500');
 if(!['unresolved','all','consented'].includes(signal))errors.push('Неизвестный тип сигнала');
 if(!r8_day(scope.from)||!r8_day(scope.to)||scope.from>scope.to)errors.push('Некорректный период');
 if(errors.length)return r8_empty(errors);
 const days=Math.min(windowDays,r8_days(scope.from,scope.to)),to=scope.to,from=r8_shift(to,1-days),previousTo=r8_shift(from,-1),previousFrom=r8_shift(previousTo,1-days);
 const earliest=[...dataset.traffic.map(x=>x.date)].sort()[0]||AS_OF;
 const comparable=previousFrom>=earliest;
 const chosen=(x)=>signal==='all'?true:signal==='unresolved'?(!x.purchased&&!x.solutionFound):!!x.consent&&!x.purchased;
 const events=dataset.requests.filter(x=>r8_matches(x,scope.filter)&&x.date>=previousFrom&&x.date<=to);
 const current=events.filter(x=>x.date>=from),previous=events.filter(x=>x.date>=previousFrom&&x.date<=previousTo);
 const rowFor=(storeId,list)=>{
  const some=list.filter(x=>x.storeId===storeId),selected=some.filter(chosen);
  return {total:some.length,count:selected.length,share:some.length?selected.length/some.length:null,ids:selected.map(x=>x.id)};
 };
 const rows=STORES.filter(s=>scope.filter?.store==='all'||!scope.filter?.store||scope.filter.store===s.id).map(s=>{
  const c=rowFor(s.id,current),p=rowFor(s.id,previous),adequate=c.total>=minSample&&(!comparable||p.total>=minSample);
  const delta=comparable&&adequate&&c.share!==null&&p.share!==null?c.share-p.share:null;
  return {id:s.id,name:s.name,observed:c.count,total:c.total,rate:c.share,previous:p.count,previousTotal:p.total,previousRate:comparable?p.share:null,delta,adequate,evidenceIds:c.ids.slice(0,60)};
 });
 const daily=[];
 for(let i=0;i<days;i++){
  const date=r8_shift(from,i),eventsForDay=current.filter(x=>x.date===date);
  daily.push({date,observed:eventsForDay.filter(chosen).length,total:eventsForDay.length,ids:eventsForDay.filter(chosen).map(x=>x.id)});
 }
 const total=r8_sum(rows,x=>x.total),observed=r8_sum(rows,x=>x.observed),pTotal=r8_sum(rows,x=>x.previousTotal),pObserved=r8_sum(rows,x=>x.previous);
 const sizes=[...new Set(current.map(x=>x.size))].map(size=>({size,requests:current.filter(x=>x.size===size).length,observed:current.filter(x=>x.size===size&&chosen(x)).length})).sort((a,b)=>b.observed-a.observed||a.size.localeCompare(b.size));
 return {valid:true,errors:[],from,to,previousFrom,previousTo,days,signal,comparable,rows,daily,sizes,total,observed,rate:total?observed/total:null,previousTotal:pTotal,previousObserved:pObserved,previousRate:comparable&&pTotal?pObserved/pTotal:null,
  delta:comparable&&total>=minSample&&pTotal>=minSample&&total&&pTotal?(observed/total-pObserved/pTotal):null,
  sufficient:total>=minSample,evidenceIds:r8_sorted(rows.flatMap(x=>x.evidenceIds),100),disclaimer:'Доля запросов описательная. Изменение не доказывает влияние действий магазина. Периоды одинаковой длины; сезонность и состав покупателей не выровнены.'};
}
export function radarCsv(r){if(!r.valid)return null;return safeCsv([['Филиал','Период с','По','Запросов','Сигналов','Доля','Прошлый период: запросов','Прошлый период: сигналов','Изменение доли п.п.','Выборка достаточна','ID оснований'],...r.rows.map(x=>[x.name,r.from,r.to,x.total,x.observed,x.rate??'',r.comparable?x.previousTotal:'',r.comparable?x.previous:'',x.delta===null?'':r8_round(x.delta*100),x.adequate?'Да':'Нет',x.evidenceIds.join(' | ')])]);}

/** 2. Service capacity: QR events/day, manual service-time assumptions, no inferred causality. */
export function serviceCapacity(scope,{slaSeconds=120,serviceMinutes=12,shiftHours=8,occupancyPercent=70,currentHandlers=1,staffDailyCost=2500,demandFactor=1}={}){
 const errors=[];
 for(const [key,value,min,max,int] of [['SLA',slaSeconds,10,3600,true],['Время обслуживания',serviceMinutes,1,240,false],['Смена',shiftHours,1,16,false],['Загрузка',occupancyPercent,10,95,false],['Сотрудники',currentHandlers,0,30,true],['Ставка',staffDailyCost,0,100000,false],['Коэффициент спроса',demandFactor,.5,20,false]])if(!r8_range(value,min,max,int))errors.push(`${key}: допустимый диапазон ${min}–${max}`);
 const days=r8_days(scope.from,scope.to);if(days<1||days>90)errors.push('Период должен быть 1–90 дней');
 if(errors.length)return r8_empty(errors);
 const capacityPerHandler=shiftHours*60*occupancyPercent/100/serviceMinutes;
 const rows=STORES.filter(s=>!scope.filter?.store||scope.filter.store==='all'||scope.filter.store===s.id).map(s=>{
  const events=scope.assistance.filter(x=>x.storeId===s.id),sample=events.length;
  const sorted=events.map(x=>x.responseSeconds).sort((a,b)=>a-b);
  const p90=sample?sorted[Math.ceil(sample*.9)-1]:null;
  const breached=events.filter(x=>x.responseSeconds>slaSeconds).length;
  const dailyObserved=sample/days,assumedDaily=dailyObserved*demandFactor;
  const staffNeeded=assumedDaily===0?0:Math.ceil(assumedDaily/capacityPerHandler);
  const extraStaff=Math.max(0,staffNeeded-currentHandlers);
  const cost=extraStaff*staffDailyCost*days;
  return {id:s.id,name:s.name,sample,p90,breached,rate:sample?breached/sample:null,dailyObserved,assumedDaily,capacityPerHandler,staffNeeded,extraStaff,cost,evidenceIds:events.map(x=>x.id).slice(0,60),requiresInvestigation:sample>=5&&p90>slaSeconds};
 });
 return {valid:true,errors:[],days,rows,totalEvents:r8_sum(rows,x=>x.sample),breaches:r8_sum(rows,x=>x.breached),extraStaff:r8_sum(rows,x=>x.extraStaff),cost:r8_round(r8_sum(rows,x=>x.cost)),capacityPerHandler:r8_round(capacityPerHandler),needsProcessReview:rows.some(x=>x.requiresInvestigation),evidenceIds:r8_sorted(rows.flatMap(x=>x.evidenceIds),100),
  disclaimer:'Время ответа QR — наблюдение. Длительность обслуживания и загрузка — ручные предположения. Расчёт численности не доказывает сокращения ожидания, роста продаж или потребности в найме.'};
}
export function capacityCsv(r){if(!r.valid)return null;return safeCsv([['Филиал','QR событий','p90 ответа, сек','Нарушений SLA','В день наблюдалось','В день сценарий','Пропускная способность/человек/день','Текущий штат','Нужно по модели','Дополнительный штат','Цена сценария, ₽','ID оснований'],...r.rows.map(x=>[x.name,x.sample,x.p90??'',x.breached,r8_round(x.dailyObserved),r8_round(x.assumedDaily),r8_round(x.capacityPerHandler),x.staffNeeded-x.extraStaff,x.staffNeeded,x.extraStaff,x.cost,x.evidenceIds.join(' | ')])]);}

/** 3. Retention experiment — deterministic offline split, aggregate-only export.
 * Consent in demo data covers a size notification, not blanket marketing permission.
 */
export function retentionOutreach(scope,{holdoutPercent=25,controlRate=5,treatmentRate=15,unitMargin=4000,promotionCost=300,messageCost=15,fixedCost=500}={}){
 const errors=[];
 for(const [label,v,min,max] of [['Контрольная доля',holdoutPercent,10,50],['Базовая конверсия',controlRate,0,100],['Конверсия сценария',treatmentRate,0,100],['Валовая маржа',unitMargin,0,1e6],['Стоимость бонуса',promotionCost,0,1e6],['Стоимость контакта',messageCost,0,10000],['Фиксированные затраты',fixedCost,0,1e7]])if(!r8_range(v,min,max))errors.push(`${label}: допустимо ${min}–${max}`);
 if(errors.length)return r8_empty(errors);
 const eligible=scope.requests.filter(x=>x.consent&&!x.purchased&&x.solutionFound).sort((a,b)=>r8_hash(a.id+'|OSMANX-R8-HOLDOUT')-r8_hash(b.id+'|OSMANX-R8-HOLDOUT')||a.id.localeCompare(b.id));
 const holdout=eligible.length<2?eligible.length:Math.max(1,Math.min(eligible.length-1,Math.round(eligible.length*holdoutPercent/100)));
 const holdIds=new Set(eligible.slice(0,holdout).map(x=>x.id));const treatment=eligible.length-holdout;
 const controlPurchases=holdout*controlRate/100,expectedTreatment=treatment*treatmentRate/100,incremental=treatment*(treatmentRate-controlRate)/100;
 const gross=incremental*unitMargin,bonus=expectedTreatment*promotionCost,contacts=treatment*messageCost;
 const net=gross-bonus-contacts-fixedCost;
 const rows=STORES.filter(s=>!scope.filter?.store||scope.filter.store==='all'||scope.filter.store===s.id).map(s=>{
  const all=eligible.filter(x=>x.storeId===s.id),control=all.filter(x=>holdIds.has(x.id)).length;
  return {id:s.id,name:s.name,eligible:all.length,control,treatment:all.length-control};
 });
 return {valid:true,errors:[],eligible:eligible.length,holdout,treatment,rows,expectedControl:r8_round(controlPurchases),expectedTreatment:r8_round(expectedTreatment),incrementalExpected:r8_round(incremental),gross:r8_round(gross),bonus:r8_round(bonus),contacts:r8_round(contacts),fixedCost,net:r8_round(net),experimentFeasible:eligible.length>=10&&holdout>=2&&treatment>=5,
  purposeSpecificPermissionConfirmed:false,individualIdentifiersExported:false,evidenceCount:eligible.length,
  disclaimer:'Согласие на уведомление о размере НЕ является согласием на рекламу. Это только размер групп и прогноз, отправки нет. Перед настоящим контактом требуется отдельная проверка целей и согласий. Контроль и тест пока не проводились.'};
}
export function outreachCsv(r){if(!r.valid)return null;return safeCsv([['Филиал','Допустимых событий в демо','Контроль','Тестовая группа','Ожидаемый нетто сценарий (вся сеть)','Согласие на рекламу проверено','Статус'],...r.rows.map(x=>[x.name,x.eligible,x.control,x.treatment,'','Нет',r.experimentFeasible?'Подготовка':'Недостаточная выборка']),['ВСЕГО',r.eligible,r.holdout,r.treatment,r.net,'Нет','Не отправлено']]);}

/** 4. Replenishment risk. Lead times, seasonality and service level are *assumptions*;
 * stock is an AS_OF snapshot, not historic on-hand inventory.
 */
export function procurementRisk(dataset,scope,{windowDays=30,leadDays=21,reviewDays=7,safetyFactor=1.28,requestWeight=.25,minOrder=2,budget=75000,category='Куртки'}={}){
 const errors=[];
 for(const [label,v,min,max,int] of [['История продаж',windowDays,7,90,true],['Срок поставки',leadDays,1,180,true],['Обзорный период',reviewDays,1,60,true],['Коэффициент резерва',safetyFactor,0,3,false],['Вес запросов',requestWeight,0,1,false],['Минимальная партия',minOrder,1,20,true],['Закупочный бюджет',budget,0,1e8,false]])if(!r8_range(v,min,max,int))errors.push(`${label}: ${min}–${max}`);
 if(!['all',...new Set(dataset.products.map(p=>p.category))].includes(category))errors.push('Категория вне каталога');
 if(scope.to!==AS_OF)errors.push('Текущий остаток нельзя применять к исторической дате');
 if(errors.length)return r8_empty(errors);
 const start=r8_shift(AS_OF,1-windowDays);
 const base=e=>e.date>=start&&e.date<=AS_OF&&r8_matches(e,scope.filter)&& (category==='all'||product(e.modelId).category===category);
 const sales=dataset.sales.filter(base),requests=dataset.requests.filter(x=>base(x)&&!x.purchased&&!x.solutionFound);
 const group=new Map();
 const put=(x,kind)=>{const key=[x.storeId,x.modelId,x.size,x.color].join('|');if(!group.has(key))group.set(key,{key,storeId:x.storeId,modelId:x.modelId,size:x.size,color:x.color,sold:0,unserved:0,ids:[]});const v=group.get(key);v[kind]++;v.ids.push(x.id)};
 sales.forEach(x=>put(x,'sold'));requests.forEach(x=>put(x,'unserved'));
 const stock=new Map(dataset.stock.map(x=>[[x.storeId,x.modelId,x.size,x.color].join('|'),x]));
 const rows=[...group.values()].map(g=>{
  const snap=stock.get(g.key),item=dataset.products.find(x=>x.id===g.modelId),snapshotValid=!!(snap&&snap.asOf===AS_OF&&Number.isInteger(snap.quantity)&&snap.quantity>=0),onHand=snapshotValid?snap.quantity:0;
  const observedDaily=g.sold/windowDays,assumedDaily=(g.sold+g.unserved*requestWeight)/windowDays;
  const target=Math.ceil(assumedDaily*(leadDays+reviewDays)+safetyFactor*Math.sqrt(assumedDaily*leadDays));
  const shortage=Math.max(0,target-onHand),units=snapshotValid&&shortage?Math.ceil(shortage/minOrder)*minOrder:0;
  const cost=units*(item?.cost??0),leadGap=Math.max(0,assumedDaily*leadDays-onHand);
  return {...g,product:item?.name??g.modelId,category:item?.category,onHand,snapshotValid,snapshotId:snap?.id??null,observedDaily,assumedDaily,target,shortage,units,cost,unitCost:item?.cost??0,leadGap};
 }).filter(x=>x.shortage>0).sort((a,b)=>b.leadGap-a.leadGap||b.unserved-a.unserved||a.key.localeCompare(b.key));
 let spent=0;const proposed=[];
 for(const row of rows){const approved=row.cost>0&&spent+row.cost<=budget;if(approved){spent+=row.cost;proposed.push({...row,approved:true});}else proposed.push({...row,approved:false});}
 const approved=proposed.filter(x=>x.approved);
 return {valid:true,errors:[],rows:proposed,approved,skipped:proposed.length-approved.length,missingSnapshots:proposed.filter(x=>!x.snapshotValid).length,spent:r8_round(spent),remaining:r8_round(budget-spent),units:r8_sum(approved,x=>x.units),shortage:r8_sum(rows,x=>x.shortage),budget,windowDays,leadDays,reviewDays,category,
  evidenceIds:r8_sorted(approved.flatMap(x=>x.ids),120),disclaimer:'Снимок остатков на '+AS_OF+'. Время поставки и доля невыкупленных запросов — допущения. Поставщики и закупки не подключены, модель Пуассона может не подходить для сезонной моды. Никакого заказа не создано.'};
}
export function procurementCsv(r){if(!r.valid)return null;return safeCsv([['Филиал','SKU','Размер','Цвет','Продано, шт.','Запросов без решения','Остаток сейчас','Целевой остаток','Дефицит','Минимальная партия, шт.','Единиц в сценарии','Стоимость сценария','В бюджете','ID оснований','ID снимка'],...r.rows.map(x=>[r8_store(x.storeId),x.modelId,x.size,x.color,x.sold,x.unserved,x.onHand,x.target,x.shortage,x.units,x.units,x.cost,x.approved?'Да':'Нет',x.ids.join(' | '),x.snapshotId??''])]);}

/** 5. Three non-causal counterfactuals for unresolved demand; same opportunity cohort. */
export function scenarioStress(scope,{conversionLow=5,conversionBase=15,conversionHigh=30,unitPrice=8900,unitCost=4900,discountPercent=0,returnPercent=5,logisticsPerOrder=350,costPerOpportunity=10,fixedCost=1200}={}){
 const errors=[];
 for(const [label,v,min,max] of [['Конверсия мин',conversionLow,0,100],['Конверсия базовая',conversionBase,0,100],['Конверсия макс',conversionHigh,0,100],['Цена',unitPrice,0,1e7],['Себестоимость',unitCost,0,1e7],['Скидка',discountPercent,0,90],['Возвраты',returnPercent,0,100],['Логистика',logisticsPerOrder,0,1e6],['Проверка запроса',costPerOpportunity,0,1e6],['Запуск',fixedCost,0,1e8]])if(!r8_range(v,min,max))errors.push(`${label}: ${min}–${max}`);
 if(conversionLow>conversionBase||conversionBase>conversionHigh)errors.push('Условия: минимум ≤ база ≤ максимум');
 if(errors.length)return r8_empty(errors);
 const opportunities=scope.requests.filter(x=>!x.purchased&&!x.solutionFound),n=opportunities.length;
 const saleGross=unitPrice*(1-discountPercent/100)-unitCost,perOrderAfterReturns=saleGross*(1-returnPercent/100)-logisticsPerOrder;
 const operatingCost=n*costPerOpportunity+fixedCost;
 const rows=[['conservative','Осторожный',conversionLow],['base','Базовый',conversionBase],['optimistic','Верхний',conversionHigh]].map(([id,label,rate])=>{
  const orders=n*rate/100,profit=orders*perOrderAfterReturns-operatingCost;
  return {id,label,rate,orders:r8_round(orders),net:r8_round(profit),gross:r8_round(orders*saleGross),returnCost:r8_round(orders*saleGross*returnPercent/100),logistics:r8_round(orders*logisticsPerOrder)};
 });
 const breakEven=n>0&&perOrderAfterReturns>0?operatingCost/(n*perOrderAfterReturns)*100:null;
 return {valid:true,errors:[],n,rows,baselineGrossProfit:scope.totals.grossProfit,observedRevenue:scope.totals.revenue,perOrderAfterReturns:r8_round(perOrderAfterReturns),operatingCost:r8_round(operatingCost),breakEven,breakEvenReachable:breakEven!==null&&breakEven<=100,hasOpportunity:n>0,baseNet:rows[1].net,downsideNet:rows[0].net,evidenceIds:opportunities.slice(0,75).map(x=>x.id),
  disclaimer:'Потенциальное изменение прибыли смоделировано для одних и тех же обращений без найденного решения. Не прибавлять к отчётной прибыли: нет контроля, фактических конверсий и измеренного эффекта. Стоимости и возвраты — предположения.'};
}
export function stressCsv(r){if(!r.valid)return null;return safeCsv([['Тип','Конверсия %','Ожидаемые покупки','Гипотетический результат ₽','Затраты запуска и проверки ₽','Порог окупаемости %','ID обращений'],...r.rows.map(x=>[x.label,x.rate,x.orders,x.net,r.operatingCost,r.breakEven===null?'':r8_round(r.breakEven),r.evidenceIds.join(' | ')])]);}
