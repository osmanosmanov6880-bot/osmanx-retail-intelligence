/** OSMANX ATELIER R7 — decision assurance, network stock, bounded capital,
 * privacy simulation, and source-linked executive brief. All data synthetic.
 * These pure functions NEVER write to POS, warehouse, or 1C.
 */
import {AS_OF,STORES,product} from './model.mjs';
import {exportRowsCsv} from './r6_core.mjs';

const r7_finite=n=>typeof n==='number'&&Number.isFinite(n);
const r7_nonneg=n=>r7_finite(n)&&n>=0;
const r7_whole=n=>Number.isSafeInteger(n)&&n>=0;
const r7_inRange=(n,min,max)=>r7_finite(n)&&n>=min&&n<=max;
const r7_dayMs=86400000;
const r7_parseDay=value=>{
 if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;
 const t=Date.parse(value+'T12:00:00Z');return Number.isFinite(t)&&new Date(t).toISOString().slice(0,10)===value?t:null;
};
const r7_age=(date,now=AS_OF)=>{const a=r7_parseDay(date),b=r7_parseDay(now);return a===null||b===null?Infinity:Math.max(0,Math.round((b-a)/r7_dayMs));};
const r7_sum=(arr,fn)=>arr.reduce((t,r)=>t+fn(r),0);
const r7_unique=arr=>[...new Set(arr.filter(Boolean))];
const r7_round=n=>Math.round((n+Number.EPSILON)*100)/100;
const r7_csvSafeRows=rows=>exportRowsCsv(rows);
const r7_stockKey=(store,model,size,color)=>[store,model,size,color].join('|');
const r7_skuKey=(model,size,color)=>[model,size,color].join('|');

/** The gate checks referential integrity and freshness, not statistical causality. */
export function decisionEvidenceGate(dataset,scope,{minimumRequests=10,minimumLinked=3,maxStockAgeDays=1}={}){
 const errors=[];
 if(!r7_whole(minimumRequests)||minimumRequests<1||minimumRequests>5000)errors.push('Минимум запросов: 1–5000');
 if(!r7_whole(minimumLinked)||minimumLinked>1000)errors.push('Минимум связанных чеков: 0–1000');
 if(!r7_whole(maxStockAgeDays)||maxStockAgeDays>365)errors.push('Давность остатков: 0–365 дней');
 if(errors.length)return {valid:false,errors,ready:false,checks:[],blockers:[]};
 const saleIndex=new Map(),duplicateIds=[],issues=[];
 const register=(stream,rows)=>{const seen=new Set();for(const x of rows){if(seen.has(x.id))duplicateIds.push(stream+':'+x.id);seen.add(x.id);}};
 for(const [label,records] of [['sales',dataset.sales],['returns',dataset.returns],['requests',dataset.requests],['stock',dataset.stock]])register(label,records);
 for(const s of dataset.sales){if(saleIndex.has(s.id))continue;saleIndex.set(s.id,s);}
 const brokenReturns=[];const returnCount=new Map();
 for(const r of scope.returns){const s=saleIndex.get(r.saleId);returnCount.set(r.saleId,(returnCount.get(r.saleId)||0)+1);
  if(!s||r.storeId!==s.storeId||r.modelId!==s.modelId||r.size!==s.size||r.date<s.date||r.refundedPrice>s.paidPrice||r.reversedCost>s.cost)brokenReturns.push(r.id);
 }
 for(const [id,n] of returnCount)if(n>1)issues.push('Двойной возврат по чеку '+id);
 const brokenLinks=[];const purchased=scope.requests.filter(x=>x.purchased);
 for(const q of purchased){const sale=saleIndex.get(q.saleId);if(!sale||sale.originRequestId!==q.id||sale.modelId!==q.modelId||sale.size!==q.size||sale.storeId!==q.storeId)brokenLinks.push(q.id);}
 const stale=scope.stock.filter(x=>!r7_whole(x.quantity)||r7_age(x.asOf)>maxStockAgeDays).map(x=>x.id);
 const observedLinked=purchased.filter(q=>!brokenLinks.includes(q.id));
 const types=[['Чеки',scope.sales.length],['Запросы размеров',scope.requests.length],['Возвраты',scope.returns.length],['Снимки остатков',scope.stock.length],['Обращения сервиса',scope.assistance?.length||0]];
 const checks=[
  {id:'ids',name:'Уникальность идентификаторов',pass:duplicateIds.length===0,failures:duplicateIds.length,evidenceIds:duplicateIds.slice(0,12)},
  {id:'receipts',name:'Связи возвратов и чеков',pass:brokenReturns.length===0&&issues.length===0,failures:brokenReturns.length+issues.length,evidenceIds:brokenReturns.slice(0,12)},
  {id:'requests',name:'Связанные покупки по запросам',pass:brokenLinks.length===0&&observedLinked.length>=minimumLinked,failures:brokenLinks.length,evidenceIds:r7_unique([...brokenLinks,...observedLinked.map(q=>q.id)]).slice(0,12)},
  {id:'stock',name:'Актуальность учётного остатка',pass:stale.length===0&&scope.stock.length>0,failures:stale.length,evidenceIds:stale.slice(0,12)},
  {id:'sample',name:'Объём зарегистрированных обращений',pass:scope.requests.length>=minimumRequests,failures:Math.max(0,minimumRequests-scope.requests.length),evidenceIds:scope.requests.slice(0,12).map(q=>q.id)}
 ];
 const blockers=checks.filter(c=>!c.pass).map(c=>c.name);
 const score=Math.max(0,Math.round(100-25*(duplicateIds.length>0)-25*(brokenReturns.length+issues.length>0)-20*(brokenLinks.length>0)-15*(stale.length>0)-10*(scope.requests.length<minimumRequests)-5*(observedLinked.length<minimumLinked)));
 const ready=blockers.length===0;
 return {valid:true,errors:[],checks,blockers,score,ready,linkedCount:observedLinked.length,linkedGross:r7_sum(observedLinked,q=>{const s=saleIndex.get(q.saleId);return s?s.paidPrice-s.cost:0;}),requestCount:scope.requests.length,
  staleStock:stale.length,duplicateCount:duplicateIds.length,brokenLinks:brokenLinks.length,brokenReturns:brokenReturns.length,sourceCounts:types,
  evidenceIds:r7_unique([...scope.requests.slice(0,18).map(q=>q.id),...observedLinked.map(q=>q.saleId)]).slice(0,45),
  disclaimer:'Проверка внутренней согласованности не доказывает причину потерь, достоверность реального учёта или прирост прибыли.'};
}
export function gateCsv(gate){return r7_csvSafeRows([['Проверка','Статус','Ошибок','ID оснований'],...(gate.checks||[]).map(c=>[c.name,c.pass?'Пройдена':'Требует проверки',c.failures,c.evidenceIds.join(' | ')])]);}

/** Discrete inventory reallocation. No source stock is used twice; demand is counted once.
 * Stock is explicitly AS-OF (today), never historical availability.
 */
export function networkRebalance(dataset,scope,{reserve=0,probability=55,fixedCost=300,unitCost=250,maxUnits=3,minDemand=1}={}){
 const errors=[];
 if(!r7_whole(reserve)||reserve>100)errors.push('Резерв: 0–100 шт.');
 if(!r7_inRange(probability,0,100))errors.push('Вероятность: 0–100%');
 if(!r7_nonneg(fixedCost)||fixedCost>10000000)errors.push('Фиксированные затраты: 0–10 млн ₽');
 if(!r7_nonneg(unitCost)||unitCost>1000000)errors.push('Затраты на единицу: 0–1 млн ₽');
 if(!r7_whole(maxUnits)||maxUnits<1||maxUnits>100)errors.push('Лимит перемещения: 1–100 шт.');
 if(!r7_whole(minDemand)||minDemand<1||minDemand>1000)errors.push('Спрос: минимум 1–1000 обращений');
 if(errors.length)return {valid:false,errors,routes:[],unserved:0,scenarioGross:0,cost:0,net:0};
 const stockCurrent=dataset.stock.filter(s=>s.asOf===AS_OF&&r7_whole(s.quantity));
 const snapshot=new Map(stockCurrent.map(s=>[r7_stockKey(s.storeId,s.modelId,s.size,s.color),s]));
 const available=new Map(stockCurrent.map(s=>[s.id,Math.max(0,s.quantity-reserve)]));
 const groups=new Map();
 for(const req of scope.requests.filter(x=>!x.purchased)){
  const k=r7_stockKey(req.storeId,req.modelId,req.size,req.color);
  if(!groups.has(k))groups.set(k,{key:k,storeId:req.storeId,modelId:req.modelId,size:req.size,color:req.color,ids:[],consenting:0});
  const g=groups.get(k);g.ids.push(req.id);if(req.consent)g.consenting++;
 }
 const targets=[...groups.values()].sort((a,b)=>b.ids.length-a.ids.length||a.key.localeCompare(b.key));
 const routes=[],skipped=[];const usedRequests=new Set();const movedByStock=new Map();
 for(const g of targets){
  const atDestination=snapshot.get(g.key);const p=dataset.products.find(x=>x.id===g.modelId);const margin=p?p.price-p.cost:NaN;
  if(g.ids.length<minDemand||!p||!r7_finite(margin)||margin<=0){skipped.push({key:g.key,reason:'Недостаточный спрос или нет валовой маржи',ids:g.ids});continue;}
  if(atDestination?.quantity>0){skipped.push({key:g.key,reason:'Учётный остаток уже показывает товар в филиале: нужна физическая проверка',ids:g.ids});continue;}
  let remaining=g.ids.length;
  const sources=stockCurrent.filter(x=>x.storeId!==g.storeId&&r7_skuKey(x.modelId,x.size,x.color)===r7_skuKey(g.modelId,g.size,g.color))
    .sort((a,b)=>(available.get(b.id)||0)-(available.get(a.id)||0)||a.storeId.localeCompare(b.storeId));
  for(const source of sources){
   const free=available.get(source.id)||0;
   if(free<1||remaining<1)continue;
   const units=Math.min(free,remaining,maxUnits);
   const gross=r7_round(units*margin*probability/100),cost=r7_round(fixedCost+units*unitCost),net=r7_round(gross-cost);
   if(net<=0){skipped.push({key:g.key,reason:'Недостаточный ожидаемый эффект после затрат',ids:g.ids});continue;}
   const batch=g.ids.filter(id=>!usedRequests.has(id)).slice(0,units);
   if(batch.length!==units)throw Error('Нарушена уникальность назначения заявок');
   batch.forEach(x=>usedRequests.add(x));
   available.set(source.id,free-units);movedByStock.set(source.id,(movedByStock.get(source.id)||0)+units);remaining-=units;
   routes.push({id:source.id+'|'+g.storeId,sourceStore:source.storeId,destinationStore:g.storeId,sourceStockId:source.id,modelId:g.modelId,product:p.name,size:g.size,color:g.color,units,requests:g.ids.length,consenting:g.consenting,evidenceIds:[...batch,source.id,atDestination?.id].filter(Boolean),
    unitGross:margin,scenarioGross:gross,cost,net,probability,asOf:AS_OF,incrementalProven:false});
  }
  if(remaining>0)skipped.push({key:g.key,reason:'Не все обращения покрываются экономически допустимым остатком',ids:g.ids.slice(-remaining)});
 }
 routes.sort((a,b)=>b.net-a.net||a.id.localeCompare(b.id));
 return {valid:true,errors:[],routes,skipped,unserved:r7_sum(skipped,x=>x.ids.length),reservedUnits:r7_sum(routes,x=>x.units),requestCount:scope.requests.filter(x=>!x.purchased).length,
  scenarioGross:r7_round(r7_sum(routes,x=>x.scenarioGross)),cost:r7_round(r7_sum(routes,x=>x.cost)),net:r7_round(r7_sum(routes,x=>x.net)),usedRequests:[...usedRequests],movedByStock:Object.fromEntries(movedByStock),
  disclaimer:'Это лишь условное перемещение на основании сегодняшнего учётного остатка. Оно не резервирует товар, не доказывает его физическое наличие и не гарантирует покупку.'};
}
export function rebalanceCsv(plan){return r7_csvSafeRows([['Маршрут','Артикул','Размер','Цвет','Штук','Запросов','Валовая прибыль сценарий','Затраты','Нетто сценарий','ID оснований'],...plan.routes.map(x=>[x.sourceStore+' → '+x.destinationStore,x.modelId,x.size,x.color,x.units,x.requests,x.scenarioGross,x.cost,x.net,x.evidenceIds.join(' | ')])]);}

/** 0/1 capital allocation: candidates have r7_unique, non-overlapping request IDs;
 * route costs include independent audit spend. Risk discounts are never labeled FACT.
 */
export function capitalAllocation(dataset,scope,params={},inputPlan=null){
 const {budget=12000,capacity=3,verificationCost=600,confidence=70}=params;
 const errors=[];
 if(!r7_nonneg(budget)||budget>100000000)errors.push('Бюджет: 0–100 млн ₽');
 if(!r7_whole(capacity)||capacity>10)errors.push('Одновременных решений: 0–10');
 if(!r7_nonneg(verificationCost)||verificationCost>10000000)errors.push('Стоимость проверки: 0–10 млн ₽');
 if(!r7_inRange(confidence,0,100))errors.push('Консервативность: 0–100%');
 const network=inputPlan||networkRebalance(dataset,scope,{});
 if(!network.valid)errors.push(...network.errors);
 if(errors.length)return {valid:false,errors,candidates:[],selected:[],totalSpend:0};
 const candidates=network.routes.slice(0,12).map((x,i)=>{
  const spend=r7_round(x.cost+verificationCost),adjustedGross=r7_round(x.scenarioGross*confidence/100),adjustedNet=r7_round(adjustedGross-spend);
  return {id:'route-'+i,routeId:x.id,title:`Проверить ${x.modelId} ${x.size}: ${x.sourceStore} → ${x.destinationStore}`,
   cost:spend,gross:x.scenarioGross,adjustedGross,adjustedNet,nominalNet:r7_round(x.scenarioGross-spend),evidenceIds:x.evidenceIds,
   requestCount:x.units,eligible:adjustedNet>0&&spend<=budget,why:adjustedNet<=0?'Консервативный сценарий ниже стоимости':spend>budget?'Превышает бюджет':'Допущение для проверки'};
 });
 let best={score:0,spend:0,mask:0,count:0};const n=candidates.length;
 for(let mask=1;mask<2**n;mask++){
  let count=0,spend=0,score=0;for(let i=0;i<n;i++)if(mask&(1<<i)){count++;spend+=candidates[i].cost;score+=candidates[i].adjustedNet;}
  if(count>capacity||spend>budget||score<=0)continue;
  if(score>best.score+0.001||(Math.abs(score-best.score)<0.001&&(spend<best.spend-0.001||Math.abs(spend-best.spend)<0.001&&mask<best.mask))){best={score:r7_round(score),spend:r7_round(spend),mask,count};}
 }
 const selected=candidates.filter((x,i)=>Boolean(best.mask&(1<<i)));
 const selectedIds=r7_unique(selected.flatMap(x=>x.evidenceIds.filter(id=>String(id).startsWith('req-'))));
 return {valid:true,errors:[],candidates,selected,rejected:candidates.filter(x=>!selected.includes(x)),budget,remaining:r7_round(budget-best.spend),totalSpend:best.spend,adjustedNet:best.score,
  nominalGross:r7_round(r7_sum(selected,x=>x.gross)),confidence,actionCount:best.count,sourceRequestIds:selectedIds,incrementalProven:false,
  disclaimer:'Оптимизация перебирает не более 12 независимых маршрутов; эффект консервативно дисконтирован, не подтверждён экспериментом и не является дополнительной чистой прибылью.'};
}
export function capitalCsv(plan){return r7_csvSafeRows([['ID','Решение','Стоимость','Валовая прибыль сценария','Консервативный эффект','Рекомендация','ID оснований'],...plan.candidates.map(x=>[x.id,x.title,x.cost,x.gross,x.adjustedNet,plan.selected.some(y=>y.id===x.id)?'В бюджетном сценарии':'Не выбрано',x.evidenceIds.join(' | ')])]);}

/** Privacy sandbox: no names, phones, or contacts; synthetic identifiers are discarded.
 * This is a preview, not a real GDPR/152-FZ compliance system or backend deletion.
 */
export function privacySimulation(dataset,scope,{retentionDays=30,requireConsent=true}={}){
 const errors=[];
 if(!r7_whole(retentionDays)||retentionDays<1||retentionDays>365)errors.push('Хранение: 1–365 дней');
 if(typeof requireConsent!=='boolean')errors.push('Параметр согласия должен быть логическим');
 if(errors.length)return {valid:false,errors,aggregates:[],excluded:0};
 const voluntary=[...scope.requests.map(x=>({...x,kind:'Запрос',consent:!!x.consent})),...(scope.preorders||[]).map(x=>({...x,kind:'Предзаказ',consent:!!x.consent}))];
 const discarded=[],retained=[],anonymous=[];
 const aggregates=new Map();
 for(const e of voluntary){const expired=r7_age(e.date)>retentionDays,prohibited=requireConsent&&!e.consent;
  if(expired||prohibited){discarded.push({kind:e.kind,reason:expired?'Срок':'Нет согласия'});}else retained.push({kind:e.kind,date:e.date,storeId:e.storeId});
  const k=e.date+'|'+e.storeId+'|'+e.kind;
  if(!aggregates.has(k))aggregates.set(k,{date:e.date,storeId:e.storeId,kind:e.kind,events:0,retained:0,discarded:0});
  const a=aggregates.get(k);a.events++;if(expired||prohibited)a.discarded++;else a.retained++;
 }
 for(const a of aggregates.values())anonymous.push(a);
 anonymous.sort((a,b)=>b.date.localeCompare(a.date)||a.storeId.localeCompare(b.storeId)||a.kind.localeCompare(b.kind));
 return {valid:true,errors:[],total:voluntary.length,retained:retained.length,discarded:discarded.length,expired:discarded.filter(x=>x.reason==='Срок').length,
  noConsent:discarded.filter(x=>x.reason==='Нет согласия').length,aggregates:anonymous,
  onlyAggregates:true,policy:{retentionDays,requireConsent},demoOnly:true,
  disclaimer:'Операция существует только в синтетической песочнице браузера. Экспорт не содержит ID, контактов, чеков или индивидуальных покупательских данных.'};
}
export function anonymousPrivacyCsv(sim){if(!sim.valid)return null;return r7_csvSafeRows([['Дата','Филиал','Источник','Событий','Сохранено в песочнице','Исключено'],...sim.aggregates.map(x=>[x.date,x.storeId,x.kind,x.events,x.retained,x.discarded])]);}
const r7_integrityHash=text=>{let h=2166136261;for(const ch of text){h=Math.imul(h^ch.charCodeAt(0),16777619)>>>0;}return h.toString(16).padStart(8,'0');};
export const PRIVACY_LEDGER_VERSION=1;
/** Non-cryptographic tamper-evident hash chain; never claim it is a digital signature. */
export function appendPrivacyAudit(entries,sim,{scenario='balanced',date=AS_OF}={}){
 if(!sim.valid)throw Error('Сначала проверьте политику');
 const prev=entries.at(-1)?.fingerprint||'origin',seq=entries.length+1;
 const values={seq,scenario,date,retentionDays:sim.policy.retentionDays,consentRequired:sim.policy.requireConsent,retained:sim.retained,discarded:sim.discarded,prev};
 const fingerprint=r7_integrityHash(JSON.stringify(values));return [...entries,{...values,fingerprint}].slice(-80);
}
export function restorePrivacyAudit(input){if(!input||input.version!==PRIVACY_LEDGER_VERSION||!Array.isArray(input.entries)||input.entries.length>80)return [];
 const out=[];for(const x of input.entries){if(!x||!r7_whole(x.seq)||typeof x.scenario!=='string'||typeof x.date!=='string'||!r7_whole(x.retentionDays)||typeof x.consentRequired!=='boolean'||!r7_whole(x.retained)||!r7_whole(x.discarded)||typeof x.prev!=='string'||typeof x.fingerprint!=='string')return [];
 const vals={seq:x.seq,scenario:x.scenario,date:x.date,retentionDays:x.retentionDays,consentRequired:x.consentRequired,retained:x.retained,discarded:x.discarded,prev:x.prev};
 if(x.fingerprint!==r7_integrityHash(JSON.stringify(vals))||(out.length>0&&x.prev!==out.at(-1).fingerprint)||(out.length===0&&x.prev!=='origin'&&x.seq===1))return [];
 out.push({...vals,fingerprint:x.fingerprint});
 }return out;
}

/** Evidence-linked, filter-respecting board brief; all labels include epistemic status. */
export function executiveBrief(dataset,scope,{gate={},rebalance={},capital={},privacy={},board=[]}={}){
 const g=decisionEvidenceGate(dataset,scope,gate),n=networkRebalance(dataset,scope,rebalance),p=capitalAllocation(dataset,scope,capital,n),v=privacySimulation(dataset,scope,privacy);
 const observedGross=scope.totals.grossProfit;
 const statements=[
  {id:'revenue',label:'Выручка нетто',value:scope.totals.revenue,unit:'₽',epistemic:'ФАКТ ДЕМО',method:'Оплаченные чеки − зарегистрированные возвраты в выбранном периоде',evidenceIds:scope.sales.slice(0,18).map(s=>s.id)},
  {id:'gross',label:'Валовая прибыль сети',value:observedGross,unit:'₽',epistemic:'ФАКТ ДЕМО',method:'Нетто-выручка − себестоимость проданных товаров с учётом возвратов',evidenceIds:scope.sales.slice(0,18).map(s=>s.id)},
  {id:'linked',label:'Валовая прибыль по связанным чекам',value:g.linkedGross,unit:'₽',epistemic:g.brokenLinks?'ТРЕБУЕТ ПРОВЕРКИ':'ФАКТ ДЕМО',method:'Чеки, в которых связь с зарегистрированным запросом согласована; не прирост прибыли',evidenceIds:g.evidenceIds},
  {id:'network',label:'Сценарный эффект перемещений',value:n.net,unit:'₽',epistemic:'ПРОГНОЗ',method:'Единицы × валовая маржа × предполагаемая вероятность − логистика; только текущие снимки остатков',evidenceIds:r7_unique(n.routes.flatMap(x=>x.evidenceIds)).slice(0,30)},
  {id:'budget',label:'Консервативный эффект выбранных проверок',value:p.adjustedNet,unit:'₽',epistemic:'ГИПОТЕЗА',method:'Ограниченный бюджетом набор сценариев после дисконта предположений',evidenceIds:p.sourceRequestIds.slice(0,30)}
 ];
 const openTasks=board.filter(x=>x.scenario===dataset.scenarioId&&x.status!=='closed').length;
 return {valid:g.valid&&n.valid&&p.valid&&v.valid,asOf:AS_OF,period:{from:scope.from,to:scope.to},scenario:dataset.scenarioId,
  gate:g,network:n,capital:p,privacy:v,openTasks,statements,
  nextActions:[g.ready?'Подтвердить источники на реальных данных перед экспериментом':'Сначала устранить блокирующие ошибки качества',
   n.routes.length?'Физически проверить остаток и согласовать возможное перемещение':'Уточнить причины отсутствия товара без финансовых обещаний',
   p.selected.length?'Утвердить ограниченный бюджет теста с контрольной группой':'Собрать больше событий или уменьшить стоимость проверки'],
  disclaimer:'Демонстрационные данные. Сценарные расчёты не подтверждают причинность и дополнительную чистую прибыль. Отчёт не является результатом интеграции с 1С.'};
}
export function briefCsv(brief){return r7_csvSafeRows([['Статус','Показатель','Рубли','Метод расчёта','ID оснований'],...brief.statements.map(x=>[x.epistemic,x.label,x.value,x.method,x.evidenceIds.join(' | ')])]);}
