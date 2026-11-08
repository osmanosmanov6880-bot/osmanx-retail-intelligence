/** OSMANX ATELIER R8 — a strict, offline, privacy-minimizing CSV working set.
 * These are local imported observations, never part of synthetic demo totals.
 * No API calls, persistence of raw rows, phone numbers, contact details or automatic actions.
 */
import {csvRows} from './r5_core.mjs';
import {AS_OF} from './model.mjs';

export const R8_KINDS=Object.freeze({
 sales:['id','date','storeId','sku','size','units','revenue','cost'],
 returns:['id','date','saleId','units','refund','restoredCost'],
 requests:['id','date','storeId','sku','size','consent','linkedSaleId'],
 stock:['id','asOf','storeId','sku','size','quantity']
});
export const R8_LABELS=Object.freeze({sales:'Чеки',returns:'Возвраты',requests:'Запросы размера',stock:'Снимок остатков'});
const r8_MAX_ROWS=1500,r8_MAX_AMT=1000000000;
const r8_dateGood=x=>typeof x==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(x)&&!Number.isNaN(Date.parse(x+'T12:00:00Z'))&&new Date(x+'T12:00:00Z').toISOString().slice(0,10)===x;
const r8_idGood=x=>typeof x==='string'&&/^[\p{L}\p{N}][\p{L}\p{N}_.:-]{0,59}$/u.test(x);
const r8_skuGood=x=>typeof x==='string'&&/^[\p{L}\p{N}][\p{L}\p{N}_.\/-]{0,39}$/u.test(x);
const r8_sizeGood=x=>typeof x==='string'&&/^[\p{L}\p{N}][\p{L}\p{N}_.-]{0,14}$/u.test(x);
const r8_int=x=>typeof x==='number'&&Number.isSafeInteger(x)&&x>=0;
const r8_money=x=>typeof x==='number'&&Number.isFinite(x)&&x>=0&&x<=r8_MAX_AMT;
const r8_sum=(a,f)=>a.reduce((s,v)=>s+f(v),0);
const r8_round=x=>Math.round((x+Number.EPSILON)*100)/100;
const r8_hash=s=>{let h=2166136261;for(const ch of String(s))h=Math.imul(h^ch.charCodeAt(0),16777619)>>>0;return h.toString(16).padStart(8,'0');};
const r8_uniqueSorted=xs=>[...new Set(xs)].sort((a,b)=>String(a).localeCompare(String(b)));
const r8_before=(a,b)=>a.localeCompare(b)<0;
const r8_textSafe=x=>{let v=String(x??'');if(/^\s*[=+@\-\t\r]/.test(v))v="'"+v;return '"'+v.replaceAll('"','""')+'"';};
export function r8Csv(rows){return '\uFEFF'+rows.map(row=>row.map(v=>typeof v==='number'&&Number.isFinite(v)?String(v):r8_textSafe(v)).join(';')).join('\r\n')+'\r\n';}
export function emptyWorkingSet(){return {sales:[],returns:[],requests:[],stock:[],origin:{},version:0};}
export function r8Example(){return {
 sales:r8Csv([R8_KINDS.sales,['s-101','2026-11-01','store-A','JKT-01','L',2,17800,9800],['s-102','2026-11-02','store-B','JKT-01','L',1,8900,4900],['s-103','2026-11-03','store-C','DRESS-02','M',1,7000,3400]]),
 returns:r8Csv([R8_KINDS.returns,['r-101','2026-11-05','s-102',1,8900,4900]]),
 requests:r8Csv([R8_KINDS.requests,['q-101','2026-11-05','store-A','JKT-01','L','1',''],['q-102','2026-11-05','store-A','JKT-01','L','1',''],['q-103','2026-11-05','store-C','JKT-01','L','0',''],['q-104','2026-11-02','store-B','JKT-01','L','1','s-102'],['q-105','2026-11-06','store-C','JKT-01','L','1','']]),
 stock:r8Csv([R8_KINDS.stock,['stk-101','2026-11-08','store-A','JKT-01','L',0],['stk-102','2026-11-08','store-B','JKT-01','L',3],['stk-103','2026-11-08','store-C','JKT-01','L',0]])
 };
}
function r8_checkRaw(kind,text,asOf){
 const problems=[];
 if(!Object.hasOwn(R8_KINDS,kind))return {valid:false,errors:['Неизвестный тип файла'],rows:[]};
 let parsed;try{parsed=csvRows(text);}catch(e){return {valid:false,errors:[e.message],rows:[]};}
 const [header,...raw]=parsed.rows,fields=header.map(x=>x.trim());const required=R8_KINDS[kind];
 if(fields.length!==required.length||fields.some((x,i)=>x!==required[i]))problems.push('Шапка файла не соответствует договору: '+required.join('; '));
 if(raw.length>r8_MAX_ROWS)problems.push('Максимум 1500 строк');
 if(raw.length===0)problems.push('Файл должен содержать хотя бы одну строку');
 if(problems.length)return {valid:false,errors:problems,rows:[],inspected:raw.length};
 const rows=[],seen=new Set();
 for(let i=0;i<raw.length;i++){
  const cells=raw[i],row={},bad=[];if(cells.length!==fields.length){problems.push(`Строка ${i+2}: число полей не равно заголовку`);continue;}
  fields.forEach((c,j)=>row[c]=cells[j].trim());
  if(!r8_idGood(row.id)||seen.has(row.id))bad.push('некорректный или повторный ID');else seen.add(row.id);
  for(const [name,checker] of [['storeId',r8_idGood],['sku',r8_skuGood],['size',r8_sizeGood]])if(Object.hasOwn(row,name)&&!checker(row[name]))bad.push('поле '+name+' недопустимо');
  for(const key of ['date','asOf'])if(Object.hasOwn(row,key)&&(!r8_dateGood(row[key])||row[key]>asOf))bad.push('дата '+key+' невалидна или находится в будущем');
  for(const key of ['units','quantity','revenue','cost','refund','restoredCost'])if(Object.hasOwn(row,key)){
   const value=Number(row[key]);if(row[key]===''||!r8_money(value)||(['units','quantity'].includes(key)&&!r8_int(value))||(['units'].includes(key)&&value===0))bad.push('число '+key+' недопустимо');else row[key]=value;
  }
  if(Object.hasOwn(row,'consent')&&!['0','1'].includes(row.consent))bad.push('consent = 0 или 1');
  if(Object.hasOwn(row,'consent'))row.consent=row.consent==='1';
  if(Object.hasOwn(row,'linkedSaleId')&&row.linkedSaleId!==''&&!r8_idGood(row.linkedSaleId))bad.push('linkedSaleId недопустим');
  if(row.cost!=null&&row.revenue!=null&&row.cost>row.revenue)bad.push('себестоимость выше выручки — требуется ручная проверка');
  if(row.restoredCost!=null&&row.refund!=null&&row.restoredCost>row.refund)bad.push('сторно себестоимости выше возврата — требуется ручная проверка');
  if(bad.length)problems.push(`Строка ${i+2} (${row.id||'—'}): ${bad.join(', ')}`);else rows.push(row);
 }
 return {valid:problems.length===0,errors:problems.slice(0,50),rows:problems.length?[]:rows,inspected:raw.length,kind};
}
export function inspectWorkingSet(ws,{asOf=AS_OF}={}){
 const errors=[],notes=[],records={},counts={};
 for(const kind of Object.keys(R8_KINDS)){
  records[kind]=Array.isArray(ws?.[kind])?ws[kind]:[];counts[kind]=records[kind].length;
  if(records[kind].length>r8_MAX_ROWS)errors.push(`${kind}: слишком много строк`);
 }
 const sales=new Map(),linked=new Set();const byReturn=new Map();const byStock=new Set();
 for(const x of records.sales){if(sales.has(x.id))errors.push('Дубль чека '+x.id);sales.set(x.id,x);}
 for(const x of records.returns){const sale=sales.get(x.saleId);if(!sale){errors.push('Возврат '+x.id+': нет исходного чека');continue;}
  if(r8_before(x.date,sale.date))errors.push('Возврат '+x.id+': дата раньше продажи');
  const previous=byReturn.get(x.saleId)||{units:0,refund:0,restoredCost:0};previous.units+=x.units;previous.refund+=x.refund;previous.restoredCost+=x.restoredCost;byReturn.set(x.saleId,previous);
  if(previous.units>sale.units||r8_round(previous.refund)>r8_round(sale.revenue)||r8_round(previous.restoredCost)>r8_round(sale.cost))errors.push('Возвраты '+x.saleId+': больше оплаченных единиц/денег/себестоимости');
 }
 for(const x of records.requests){if(!x.linkedSaleId)continue;const sold=sales.get(x.linkedSaleId);
  if(!sold){errors.push('Запрос '+x.id+': чек не существует');continue;}
  if(linked.has(x.linkedSaleId))errors.push('Чек '+x.linkedSaleId+' привязан к нескольким запросам');linked.add(x.linkedSaleId);
  if(sold.storeId!==x.storeId||sold.sku!==x.sku||sold.size!==x.size||r8_before(sold.date,x.date))errors.push('Запрос '+x.id+': неверная связка с чеком');
 }
 for(const x of records.stock){const key=[x.asOf,x.storeId,x.sku,x.size].join('|');if(byStock.has(key))errors.push('Дублированный остаток '+key);byStock.add(key);}
 const latest=records.stock.map(x=>x.asOf).sort().at(-1)||null;
 if(latest&&latest!==asOf)notes.push('Дата остатков '+latest+' отличается от отчётной '+asOf+'; маршруты не будут рекомендованы.');
 if(records.requests.length&&!records.sales.length)notes.push('Без чеков нет достоверной оценки валовой маржи.');
 if(!records.sales.length)notes.push('Чеки ещё не загружены: финансовые выводы недоступны.');
 const sample=Object.values(ws?.origin||{}).some(x=>x==='example');
 return {valid:errors.length===0,errors:errors.slice(0,50),notes,counts,latestStockDate:latest,example:sample,source:sample?'УЧЕБНЫЙ CSV':Object.values(counts).some(x=>x>0)?'ЛОКАЛЬНЫЕ CSV (НЕ СВЕРЕНЫ С POS)':'ФАЙЛЫ НЕ ЗАГРУЖЕНЫ',version:ws?.version||0};
}
/** Atomic replace: invalid rows or broken references cannot mutate accepted datasets. */
export function acceptCsv(ws,kind,text,{asOf=AS_OF,origin='local'}={}){
 const parsed=r8_checkRaw(kind,text,asOf);
 if(!parsed.valid)return {accepted:false,errors:parsed.errors,workspace:ws,inspected:parsed.inspected||0};
 const next={...ws,[kind]:parsed.rows,origin:{...(ws.origin||{}),[kind]:origin},version:(ws.version||0)+1};
 const mixed=Object.keys(R8_KINDS).some(k=>k!==kind&&next[k].length>0&&next.origin[k]!==origin);
 if(mixed)return {accepted:false,errors:['Нельзя смешивать учебные и локальные CSV. Сначала очистите рабочий набор.'],workspace:ws,inspected:parsed.inspected};
 const check=inspectWorkingSet(next,{asOf});
 if(!check.valid)return {accepted:false,errors:check.errors,workspace:ws,inspected:parsed.inspected};
 return {accepted:true,errors:[],workspace:next,inspected:parsed.inspected,summary:check};
}
export function salesLedger(ws,{store='all'}={}){
 const check=inspectWorkingSet(ws);if(!check.valid||!ws.sales.length)return {valid:false,errors:check.errors.length?check.errors:['Нет проверенных чеков'],byStore:[],netRevenue:null,gross:null};
 const sales=ws.sales.filter(x=>store==='all'||x.storeId===store),ids=new Set(sales.map(x=>x.id));
 const returns=ws.returns.filter(x=>ids.has(x.saleId));
 const revenue=r8_round(r8_sum(sales,x=>x.revenue)),cost=r8_round(r8_sum(sales,x=>x.cost));
 const refund=r8_round(r8_sum(returns,x=>x.refund)),restoredCost=r8_round(r8_sum(returns,x=>x.restoredCost));
 const byStore=r8_uniqueSorted(sales.map(x=>x.storeId)).map(storeId=>{
  const s=sales.filter(x=>x.storeId===storeId),sid=new Set(s.map(x=>x.id)),r=returns.filter(x=>sid.has(x.saleId));
  const netRevenue=r8_round(r8_sum(s,x=>x.revenue)-r8_sum(r,x=>x.refund));
  const gross=r8_round(netRevenue-(r8_sum(s,x=>x.cost)-r8_sum(r,x=>x.restoredCost)));
  return {storeId,receipts:s.length,units:r8_sum(s,x=>x.units),returns:r.length,netRevenue,gross,evidenceIds:s.slice(0,10).map(x=>x.id)};
 });
 return {valid:true,errors:[],sales:sales.length,soldUnits:r8_sum(sales,x=>x.units),returns:returns.length,returnedUnits:r8_sum(returns,x=>x.units),revenue,cost,refund,restoredCost,netRevenue:r8_round(revenue-refund),gross:r8_round((revenue-refund)-(cost-restoredCost)),byStore,evidenceIds:sales.slice(0,15).map(x=>x.id),origin:check.source,example:check.example,claim:'НАБЛЮДАЕМО В ИМПОРТИРОВАННЫХ СТРОКАХ, НЕ АУДИТ УЧЁТА'};
}
const r8_skuKey=x=>x.sku+'|'+x.size;
export function availabilityPlan(ws,{reserve=0,probability=55,fixedCost=250,unitCost=150,maxRoutes=30}={}){
 const check=inspectWorkingSet(ws),errors=[...check.errors];
 if(!r8_int(reserve)||reserve>10000)errors.push('Резерв источника: 0–10000 шт.');
 if(!r8_money(probability)||probability>100)errors.push('Вероятность: 0–100%');
 if(!r8_money(fixedCost)||fixedCost>1000000||!r8_money(unitCost)||unitCost>1000000)errors.push('Логистика: 0–1 млн ₽');
 if(!r8_int(maxRoutes)||maxRoutes<1||maxRoutes>100)errors.push('Максимум маршрутов: 1–100');
 if(errors.length)return {valid:false,errors,routes:[],gapCount:0,net:0};
 const latest=check.latestStockDate;
 const candidates=ws.requests.filter(x=>!x.linkedSaleId);
 const stock=ws.stock.filter(x=>x.asOf===latest);
 const snap=new Map(stock.filter(x=>x.asOf===AS_OF).map(x=>[x.storeId+'|'+r8_skuKey(x),x]));
 const saleMap=new Map();for(const x of ws.sales){const key=r8_skuKey(x);const v=saleMap.get(key)||{gross:0,units:0};v.gross+=x.revenue-x.cost;v.units+=x.units;saleMap.set(key,v);}
 const current=stock.filter(x=>x.asOf===AS_OF),available=new Map(current.map(x=>[x.id,Math.max(0,x.quantity-reserve)]));
 const targets=(latest===AS_OF?candidates.filter(x=>{const local=snap.get(x.storeId+'|'+r8_skuKey(x));return local&&local.quantity===0;}):[]).sort((a,b)=>a.date.localeCompare(b.date)||a.id.localeCompare(b.id));
 const routes=[],matchedIds=new Set(),movedByStock={};
 for(const q of targets){if(routes.length>=maxRoutes)break;const costBasis=saleMap.get(r8_skuKey(q));if(!costBasis?.units)continue;
  const grossUnit=costBasis.gross/costBasis.units;
  const sources=current.filter(x=>x.storeId!==q.storeId&&r8_skuKey(x)===r8_skuKey(q)&&(available.get(x.id)||0)>0).sort((a,b)=>(available.get(b.id)||0)-(available.get(a.id)||0)||a.id.localeCompare(b.id));
  const source=sources[0];if(!source)continue;
  const expectedGross=r8_round(grossUnit*probability/100),cost=r8_round(fixedCost+unitCost),net=r8_round(expectedGross-cost);
  if(net<=0)continue;
  available.set(source.id,(available.get(source.id)||0)-1);movedByStock[source.id]=(movedByStock[source.id]||0)+1;matchedIds.add(q.id);
  routes.push({id:'r8-'+q.id,requestId:q.id,storeId:q.storeId,fromStoreId:source.storeId,sku:q.sku,size:q.size,stockId:source.id,asOf:source.asOf,consent:q.consent,expectedGross,cost,net,actualSale:false});
 }
 return {valid:true,errors:[],gapCount:latest===AS_OF&&stock.length?targets.length:null,unverified:candidates.length-targets.length,unknownMargin:targets.filter(x=>!saleMap.has(r8_skuKey(x))).length,matched:routes.length,unmatched:targets.length-routes.length,routes,net:r8_round(r8_sum(routes,x=>x.net)),movedByStock,latestStockDate:latest,stockCurrent:latest===AS_OF,incrementalProven:false,source:check.source,example:check.example,disclaimer:'Только условные маршруты по снимку остатков; товар физически не проверен и покупка не доказана. При устаревшем снимке маршруты не создаются.'};
}
export function recoveryPilot(ws,{testShare=50,lift=5,notificationCost=25,fixedCost=500,maxInvites=100,seed='OSMANX-R8'}={}){
 const check=inspectWorkingSet(ws),errors=[...check.errors];
 if(!r8_int(testShare)||testShare<1||testShare>99)errors.push('Тест: 1–99%');
 if(!r8_money(lift)||lift>100)errors.push('Допущение эффекта: 0–100 п.п.');
 if(!r8_money(notificationCost)||notificationCost>1000000||!r8_money(fixedCost)||fixedCost>1000000)errors.push('Затраты: 0–1 млн ₽');
 if(!r8_int(maxInvites)||maxInvites>1500)errors.push('Лимит приглашений: 0–1500');
 if(typeof seed!=='string'||!/^[-\p{L}\p{N}]{1,32}$/u.test(seed))errors.push('Ключ разбиения: 1–32 буквы/цифры/дефиса');
 if(errors.length)return {valid:false,errors,candidates:[],test:[],control:[],expectedNet:null};
 const prospects=ws.requests.filter(x=>x.consent&&!x.linkedSaleId).sort((a,b)=>a.id.localeCompare(b.id)).slice(0,maxInvites);
 const test=[],control=[];for(const x of prospects){const arm=(parseInt(r8_hash(seed+'|'+x.id),16)%100)<testShare?'test':'control';(arm==='test'?test:control).push({requestId:x.id,storeId:x.storeId,sku:x.sku,size:x.size,arm});}
 const ledger=salesLedger(ws),marginPerUnit=ledger.valid&&ledger.soldUnits>0?ledger.gross/Math.max(1,ledger.soldUnits-ledger.returnedUnits):null;
 const expectedGross=marginPerUnit==null?null:r8_round(test.length*lift/100*marginPerUnit),cost=r8_round(test.length*notificationCost+fixedCost);
 const goodSample=test.length>=20&&control.length>=20;
 return {valid:true,errors:[],candidates:prospects.length,test,control,excluded:ws.requests.filter(x=>!x.consent||x.linkedSaleId).length,source:check.source,example:check.example,marginPerUnit:marginPerUnit==null?null:r8_round(marginPerUnit),expectedGross,cost,expectedNet:expectedGross==null?null:r8_round(expectedGross-cost),goodSample,incrementalProven:false,disclaimer:'Разделение относится к событиям запросов, а не уникальным людям; коммуникации НЕ отправляются. Эффект — гипотеза до измерения рандомизированного пилота.'};
}
export function r8OwnerBrief(ws,{store='all',availability={},pilot={}}={},history=[]){
 const check=inspectWorkingSet(ws);const ledger=salesLedger(ws,{store});const network=availabilityPlan(ws,availability);const recovery=recoveryPilot(ws,pilot);
 const claims=[
  {label:'Чеки в импортированном CSV',value:ledger.valid?ledger.sales:null,status:'НАБЛЮДАЕМО В ФАЙЛЕ',method:'Количество ID проверенных чеков, без причинной интерпретации'},
  {label:'Чистая выручка после возвратов',value:ledger.valid?ledger.netRevenue:null,status:'НАБЛЮДАЕМО В ФАЙЛЕ',method:'Σ revenue − Σ refund'},
  {label:'Валовая прибыль по чекам',value:ledger.valid?ledger.gross:null,status:'НАБЛЮДАЕМО В ФАЙЛЕ',method:'Σ revenue − Σ refund − (Σ cost − Σ restoredCost)'},
  {label:'Незакрытые запросы размера',value:network.valid?network.gapCount:null,status:'НАБЛЮДАЕМО / СНИМОК ОСТАТКОВ',method:'Запросы без чека и без наличия в филиале назначения'},
  {label:'Потенциал проверки перемещения',value:network.valid?network.net:null,status:'ГИПОТЕЗА',method:'Σ(средняя маржа SKU × вероятность − логистика), без доказанного прироста'}
 ];
 return {valid:check.valid&&ledger.valid,errors:[...check.errors,...(ledger.errors||[])],claims,ledger,network,recovery,origin:check.source,example:check.example,sourceTypes:Object.keys(R8_KINDS).filter(k=>ws[k].length),previous:history.length,disclaimer:'Файлы не сверены с 1С/POS и могут содержать ошибки источника. Сценарные суммы не являются доказанной дополнительной прибылью. Без реальных CSV в отчёте нет финансовых фактов.'};
}
export const R8_AUDIT_VERSION=1;
export function appendR8Audit(existing,brief,{date=AS_OF,status='needs-review'}={}){
 if(!brief.valid||!['needs-review','reviewed','rejected'].includes(status))throw Error('Сначала проверьте данные и статус');
 if(existing.length>=40)throw Error('Локальная история заполнена: экспортируйте отчёт перед очисткой');
 const seq=existing.length+1,prev=existing.at(-1)?.fingerprint||'origin';
 const entry={seq,date,status,source:brief.origin,receiptCount:brief.ledger.sales,netRevenue:brief.ledger.netRevenue,gross:brief.ledger.gross,unmetRequests:brief.network.gapCount,potentialScenario:brief.network.net,prev};
 return [...existing,{...entry,fingerprint:r8_hash(JSON.stringify(entry))}];
}
export function restoreR8Audit(input){if(input?.version!==R8_AUDIT_VERSION||!Array.isArray(input.items)||input.items.length>40)return [];
 let prev='origin';const output=[];for(const r of input.items){if(!r||Object.keys(r).sort().join('|')!==['seq','date','status','source','receiptCount','netRevenue','gross','unmetRequests','potentialScenario','prev','fingerprint'].sort().join('|'))return [];
  const {fingerprint,...entry}=r;if(entry.seq!==output.length+1||entry.prev!==prev||!['needs-review','reviewed','rejected'].includes(entry.status)||fingerprint!==r8_hash(JSON.stringify(entry)))return [];
  if(![entry.receiptCount,entry.netRevenue,entry.gross,entry.unmetRequests,entry.potentialScenario].every(x=>typeof x==='number'&&Number.isFinite(x)))return [];
  output.push({...entry,fingerprint});prev=fingerprint;
 }return output;
}
export function ledgerCsv(result){return result.valid?r8Csv([['Филиал','Чеков','Продано шт.','Возвратов','Чистая выручка','Валовая прибыль'],...result.byStore.map(x=>[x.storeId,x.receipts,x.units,x.returns,x.netRevenue,x.gross])]):null;}
export function availabilityCsv(result){return result.valid?r8Csv([['Обращение','Точка спроса','Источник','SKU','Размер','Снимок остатков','Согласие','Валовая прибыль сценария','Логистика','Нетто сценария'],...result.routes.map(x=>[x.requestId,x.storeId,x.fromStoreId,x.sku,x.size,x.asOf,x.consent?'Да':'Нет',x.expectedGross,x.cost,x.net])]):null;}
export function recoveryCsv(result){return result.valid?r8Csv([['Событие','Филиал','SKU','Размер','Контрольная группа'],...result.test.map(x=>[x.requestId,x.storeId,x.sku,x.size,'Тест']),...result.control.map(x=>[x.requestId,x.storeId,x.sku,x.size,'Контроль'])]):null;}
export function r8BriefCsv(brief){return brief.valid?r8Csv([['Показатель','Значение','Статус','Формула / оговорка'],...brief.claims.map(x=>[x.label,x.value??'',x.status,x.method])]):null;}
export function r8AuditCsv(history){return r8Csv([['Номер','Дата','Решение','Источник','Чеков','Чистая выручка','Валовая прибыль','Запросов без продажи','Сценарий','Контрольная сумма'],...history.map(x=>[x.seq,x.date,x.status,x.source,x.receiptCount,x.netRevenue,x.gross,x.unmetRequests,x.potentialScenario,x.fingerprint])]);}
