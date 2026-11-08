/**
 * ATELIER R3 · auditable evidence, stock-constrained planning and pilot decisions.
 * Everything is local and synthetic. No action here mutates inventory, sends mail or books a sale.
 */
import {AS_OF,STORES,AURA,product,forecastTransfer,safeRatio} from './model.mjs';

const moneyRound=n=>Math.round((n+Number.EPSILON)*100)/100;
const finite=n=>typeof n==='number'&&Number.isFinite(n);
const nonneg=n=>finite(n)&&n>=0;
const count=n=>Number.isSafeInteger(n)&&n>=0;
const clip=(n,min,max)=>Math.min(max,Math.max(min,n));
const sumR3=(xs,fn)=>xs.reduce((a,x)=>a+fn(x),0);

/** A transparent accounting bridge from scoped event IDs to financial totals. */
export function reconcileEvidence(dataset,scope){
 const salesById=new Map(dataset.sales.map(x=>[x.id,x]));
 const requestsById=new Map(dataset.requests.map(x=>[x.id,x]));
 const issues=[];
 const originalReturnIds=new Set();
 const entries=[];
 for(const sale of scope.sales){
  if(!nonneg(sale.paidPrice)||!nonneg(sale.cost))issues.push(`Чек ${sale.id}: ошибочная цена или себестоимость`);
  entries.push({id:sale.id,date:sale.date,storeId:sale.storeId,kind:'Продажа',sourceId:sale.originRequestId||null,
   revenue:sale.paidPrice,cogs:sale.cost,gross:sale.paidPrice-sale.cost});
 }
 for(const ret of scope.returns){
  const source=salesById.get(ret.saleId);
  if(!source)issues.push(`Возврат ${ret.id}: отсутствует исходный чек`);
  else if(source.modelId!==ret.modelId||source.storeId!==ret.storeId||source.size!==ret.size)issues.push(`Возврат ${ret.id}: расхождение с чеком`);
  if(originalReturnIds.has(ret.saleId))issues.push(`Повторный возврат чека ${ret.saleId}`);
  originalReturnIds.add(ret.saleId);
  if(!nonneg(ret.refundedPrice)||!nonneg(ret.reversedCost))issues.push(`Возврат ${ret.id}: ошибочная сумма`);
  entries.push({id:ret.id,date:ret.date,storeId:ret.storeId,kind:'Возврат',sourceId:ret.saleId,
   revenue:-ret.refundedPrice,cogs:-ret.reversedCost,gross:-ret.refundedPrice+ret.reversedCost});
 }
 const linked=[];
 for(const req of scope.requests.filter(x=>x.purchased)){
  const sale=salesById.get(req.saleId);
  if(!sale||sale.originRequestId!==req.id||sale.modelId!==req.modelId||sale.storeId!==req.storeId||sale.size!==req.size){
   issues.push(`Запрос ${req.id}: нет согласованного связанного чека`);continue;
  }
  if(sale.date<req.date)issues.push(`Запрос ${req.id}: покупка раньше обращения`);
  linked.push({requestId:req.id,saleId:sale.id,date:sale.date,modelId:sale.modelId,storeId:sale.storeId,size:sale.size,
   revenue:sale.paidPrice,cost:sale.cost,gross:sale.paidPrice-sale.cost});
 }
 const revenue=moneyRound(sumR3(entries,x=>x.revenue));
 const cogs=moneyRound(sumR3(entries,x=>x.cogs));
 const gross=moneyRound(sumR3(entries,x=>x.gross));
 const matchesTotals=Math.abs(scope.totals.revenue-revenue)<.01&&Math.abs(scope.totals.costOfGoods-cogs)<.01&&Math.abs(scope.totals.grossProfit-gross)<.01;
 if(!matchesTotals)issues.push('Сумма реестра отличается от итогов финансовой модели');
 const linkedGross=moneyRound(sumR3(linked,x=>x.gross));
 const referencedReceipts=linked.filter(x=>scope.sales.some(s=>s.id===x.saleId));
 return {revenue,cogs,gross,linked,linkedGross,linkedInPeriodGross:moneyRound(sumR3(referencedReceipts,x=>x.gross)),
  linkedCount:linked.length,entries:entries.sort((a,b)=>b.date.localeCompare(a.date)||a.id.localeCompare(b.id)),
  issues,hasDiscrepancy:issues.length>0,checks:{totals:matchesTotals,returnLinks:!issues.some(x=>x.includes('Возврат')),requestLinks:!issues.some(x=>x.includes('Запрос'))},
  evidenceCount:scope.requests.length+scope.sales.length+scope.returns.length,
  incrementalProfit:null,
  disclaimer:'Валовая прибыль по связанным продажам не доказывает, что покупки не произошли бы без системы.'};
}

/** Plan never updates stock or assumes a book quantity equals physical availability. */
export function planTransfer(dataset,opts={}){
 const sourceStore=opts.sourceStore||'s2',destinationStore=opts.destinationStore||'s1';
 const modelId=opts.modelId||AURA.id,size=opts.size||'L',color=opts.color||'Графит';
 const units=Number(opts.units===undefined?3:opts.units),probability=opts.probability===null?NaN:Number(opts.probability===undefined?55:opts.probability)/100;
 const costPerUnit=Number(opts.costPerUnit===undefined?350:opts.costPerUnit),fixedCost=Number(opts.fixedCost===undefined?0:opts.fixedCost);
 const p=dataset.products.find(p=>p.id===modelId);
 const source=dataset.stock.find(x=>x.storeId===sourceStore&&x.modelId===modelId&&x.size===size&&x.color===color);
 const dest=dataset.stock.find(x=>x.storeId===destinationStore&&x.modelId===modelId&&x.size===size&&x.color===color);
 const days=Number(opts.days??14),after=new Date(`${AS_OF}T12:00:00Z`);after.setUTCDate(after.getUTCDate()-clip(days-1,0,89));
 const from=after.toISOString().slice(0,10);
 const demand=dataset.requests.filter(x=>x.date>=from&&x.storeId===destinationStore&&x.modelId===modelId&&x.size===size&&x.color===color&&!x.purchased);
 const problems=[];
 if(!p)problems.push('Модель отсутствует в каталоге');
 if(!STORES.some(x=>x.id===sourceStore)||!STORES.some(x=>x.id===destinationStore))problems.push('Неизвестный филиал');
 if(sourceStore===destinationStore)problems.push('Филиалы отправки и получения должны различаться');
 if(!count(units)||units===0)problems.push('Количество должно быть положительным целым');
 if(!nonneg(costPerUnit)||!nonneg(fixedCost))problems.push('Стоимость логистики не может быть отрицательной');
 if(!finite(probability)||probability<0||probability>1)problems.push('Вероятность покупки: от 0 до 100%');
 if(!source)problems.push('Нет учётного снимка наличия в филиале-источнике');
 if(source&&source.asOf!==AS_OF)problems.push('Снимок наличия устарел и требует обновления');
 if(source&&units>source.quantity)problems.push(`В филиале-источнике только ${source.quantity} шт. по учётному снимку`);
 if(!demand.length)problems.push('Нет зарегистрированного неудовлетворённого спроса в филиале-получателе');
 if(units>demand.length)problems.push('Единиц больше, чем наблюдаемых незавершённых запросов');
 const priced=p?forecastTransfer({units:Math.max(0,units),price:p.price,cost:p.cost,probability:clip(probability||0,0,1),costPerUnit:Math.max(0,costPerUnit||0),fixedCost:Math.max(0,fixedCost||0)}):null;
 const valid=problems.length===0;
 return {valid,problems,sourceStore,destinationStore,modelId,size,color,units,availableAtSource:source?.quantity??null,availableAtDestination:dest?.quantity??null,
  snapshotDate:source?.asOf||null,demandCount:demand.length,evidenceIds:demand.map(x=>x.id),stockSourceId:source?.id||null,
  stockDestinationId:dest?.id||null,from,calc:valid?priced:null,
  upperBoundNet:valid?units*Math.max(0,p.price-p.cost)-priced.logistics:null,
  lowerBoundNet:valid?-priced.logistics:null,
  confidence:'Низкая: доступность только по снимку, вероятность покупки задана вручную',
  action:'Проверить физическое наличие и резервы; согласовать перемещение с ответственным',
  sourceLabel:'Учётный снимок + добровольные запросы, демонстрационные данные',
  isActualTransfer:false};
}

/** Wilson interval for a proportion; used for uncertainty, not causal inference. */
export function wilson(successes,total,z=1.96){
 if(!count(total)||!count(successes)||total===0||successes>total)return null;
 const p=successes/total,den=1+z*z/total;
 const mid=(p+z*z/(2*total))/den;
 const term=z*Math.sqrt((p*(1-p)+z*z/(4*total))/total)/den;
 return [clip(mid-term,0,1),clip(mid+term,0,1)];
}
/** Manual pilot analysis: no control group means no estimated incremental lift. */
export function evaluatePilot({testRequests=0,testPurchases=0,controlRequests=null,controlPurchases=null,
  unitGross=4000,pilotCost=0}={}){
 const errors=[];
 if(!count(testRequests)||!count(testPurchases)||testPurchases>testRequests)errors.push('Некорректное количество обращений или покупок пилота');
 const controlPresent=controlRequests!==null&&controlRequests!==''&&controlPurchases!==null&&controlPurchases!=='';
 if(controlPresent&&(!count(controlRequests)||!count(controlPurchases)||controlPurchases>controlRequests))errors.push('Некорректные контрольные события');
 if(!nonneg(unitGross)||!nonneg(pilotCost))errors.push('Укажите неотрицательную валовую прибыль на единицу и расходы');
 if(errors.length)return {valid:false,errors,conclusion:'Нельзя оценить по некорректным данным'};
 const testRate=safeRatio(testPurchases,testRequests),testCI=wilson(testPurchases,testRequests);
 const controlRate=controlPresent?safeRatio(controlPurchases,controlRequests):null;
 const controlCI=controlPresent?wilson(controlPurchases,controlRequests):null;
 const comparable=controlPresent&&testCI!==null&&controlCI!==null;
 const delta=comparable?testRate-controlRate:null;
 const observedGross=testPurchases*unitGross;
 const descriptiveDifference=comparable?delta*testRequests*unitGross:null;
 const interval=comparable?[(testCI[0]-controlCI[1])*testRequests*unitGross,(testCI[1]-controlCI[0])*testRequests*unitGross]:null;
 return {valid:true,errors:[],testRequests,testPurchases,testRate,testCI,controlPresent,controlRate,controlCI,
  delta,observedGross,pilotCost,descriptiveDifference,descriptiveNet:comparable?descriptiveDifference-pilotCost:null,
  interval,incrementalProven:false,confidence:!comparable?'Нет полноценной контрольной выборки':'Оценка неопределённости (Wilson 95%) — не доказательство причинности',
  conclusion:!comparable?'Недостаточно данных для расчёта сравнительного финансового эффекта':'Сравнение описательное: группы могли отличаться, причинность не установлена.'};
}

const STATES=['draft','running','measured','closed'];
const trimmed=(x,n)=>String(x??'').replace(/[<>]/g,'').trim().slice(0,n);
export const JOURNAL_VERSION=1;
export function restoreJournal(raw){
 if(!raw||raw.version!==JOURNAL_VERSION||!Array.isArray(raw.entries))return [];
 return raw.entries.slice(0,100).filter(x=>x&&typeof x==='object'&&/^PILOT-\d{3,}$/.test(x.id)&&STATES.includes(x.status)&&typeof x.title==='string'&&x.title.length<=140&&Array.isArray(x.events))
  .map(x=>({...x,events:x.events.slice(0,40)}));
}
export function newJournalEntry(entries,{title,scenarioId='balanced',owner='Управляющий сети',type='hypothesis',evidenceIds=[]}={}){
 title=trimmed(title,120);if(!title)throw Error('Нужна формулировка проверяемой гипотезы');
 const max=entries.reduce((m,x)=>Math.max(m,Number(x.id.split('-')[1])||0),0),id=`PILOT-${String(max+1).padStart(3,'0')}`;
 const next={id,title,scenarioId,owner:trimmed(owner,80)||'Управляющий сети',type:trimmed(type,30),
  status:'draft',createdAt:AS_OF,evidenceIds:[...new Set(evidenceIds.map(x=>trimmed(x,90)))].slice(0,100),
  baseline:null,result:null,events:[{at:AS_OF,action:'Создан план проверки'}]};
 return {entries:[...entries,next],created:next};
}
export function transitionJournal(entries,id,nextStatus,payload={}){
 const index=entries.findIndex(x=>x.id===id);if(index<0)throw Error('План не найден');
 const prev=entries[index],allowed={draft:['running'],running:['measured'],measured:['closed'],closed:[]};
 if(!allowed[prev.status].includes(nextStatus))throw Error('Недопустимый переход состояния плана');
 let result=prev.result;
 if(nextStatus==='measured'){
  if(['before','after','sample','expenses'].some(k=>payload[k]===undefined||payload[k]===null||payload[k]===''))throw Error('Для результата нужны корректные показатели до/после, размер выборки и затраты');
  const b=Number(payload.before),a=Number(payload.after),n=Number(payload.sample),expenses=Number(payload.expenses);
  if([b,a,n,expenses].some(x=>!finite(x))||!count(b)||!count(a)||!count(n)||n===0||!nonneg(expenses)||b>n||a>n)throw Error('Для результата нужны корректные показатели до/после, размер выборки и затраты');
  result={before:b,after:a,sample:n,expenses,delta:a-b,incrementalityProven:false,note:'Описательное сравнение; без контрольной группы нельзя приписывать изменение системе'};
 }
 const updated={...prev,status:nextStatus,result,events:[...prev.events,{at:AS_OF,action:nextStatus==='running'?'Начата проверка':nextStatus==='measured'?'Внесены наблюдаемые результаты':'Проверка закрыта'}]};
 return entries.map((x,i)=>i===index?updated:x);
}
export function journalStats(entries){return {all:entries.length,draft:entries.filter(x=>x.status==='draft').length,running:entries.filter(x=>x.status==='running').length,measured:entries.filter(x=>x.status==='measured'||x.status==='closed').length,proven:0};}

/** Evidence lineage for the chosen opportunity — never substitute unrelated events. */
export function evidenceForOpportunity(scope,id,limit=35){
 const rules={demand:scope.requests.filter(x=>!x.purchased),rescue:scope.requests.filter(x=>x.solutionFound&&!x.purchased),fitting:scope.fittings.filter(x=>!x.purchased),stock:scope.audits.filter(x=>x.status==='Требует сверки'),service:scope.assistance.filter(x=>x.responseSeconds>240),returns:scope.returns};
 return (rules[id]||[]).slice(0,limit).map(x=>x.id);
}
/** Spreadsheet-safe export, including injection guard on user-authored fields. */
export function journalCsv(entries){
 const cell=v=>{
  let s=String(v??'').replace(/\r?\n/g,' ');
  if(/^[\s]*[=+@-]/.test(s))s="'"+s;
  return '"'+s.replace(/"/g,'""')+'"';
 };
 const rows=[['ID','Гипотеза','Статус','Ответственный','Дата','До','После','Выборка','Расходы'],...entries.map(x=>[x.id,x.title,x.status,x.owner,x.createdAt,x.result?.before,x.result?.after,x.result?.sample,x.result?.expenses])];
 return '\ufeff'+rows.map(row=>row.map(cell).join(';')).join('\r\n');
}
