/** ATELIER R5: local data-contract, privacy-safe reporting and decision labs.
 * No external APIs. Imported rows are intentionally isolated from demo analytics.
 */
import {AS_OF,STORES,CATALOG,scopeData,product} from './model.mjs';

const storeIds=new Set(STORES.map(x=>x.id));
const productIds=new Set(CATALOG.map(x=>x.id));
const SUM=(xs,f)=>xs.reduce((a,x)=>a+f(x),0);
const r5Finite=n=>typeof n==='number'&&Number.isFinite(n);
const money=n=>Math.round((n+Number.EPSILON)*100)/100;
const integer=(n,max)=>Number.isSafeInteger(n)&&n>=0&&n<=max;
const validDate=x=>{if(typeof x!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(x))return false;const d=new Date(x+'T12:00:00Z');return Number.isFinite(d.valueOf())&&d.toISOString().slice(0,10)===x;};
const dateMs=x=>Date.parse(x+'T12:00:00Z');
const required={
 sales:['id','date','storeId','modelId','size','paidPrice','cost'],
 returns:['id','date','storeId','saleId','modelId','size','refundedPrice','reversedCost'],
 stock:['id','asOf','storeId','modelId','size','color','quantity']
};
const numeric={sales:['paidPrice','cost'],returns:['refundedPrice','reversedCost'],stock:['quantity']};

/** RFC 4180 style quoting, BOM, \n/\r\n and Excel's semicolon delimiter. */
export function csvRows(text){
 if(typeof text!=='string'||text.length>1200000)throw Error('CSV должен быть текстом до 1,2 МБ');
 const input=text.replace(/^\uFEFF/,'');const head=input.slice(0,input.indexOf('\n')===-1?input.length:input.indexOf('\n'));
 const delimiter=(head.match(/;/g)||[]).length>(head.match(/,/g)||[]).length?';':',';
 const rows=[];let row=[],field='',quoted=false,closed=false;
 for(let i=0;i<input.length;i++){
  const ch=input[i];
  if(quoted){if(ch==='"'){if(input[i+1]==='"'){field+='"';i++;}else{quoted=false;closed=true;}}else field+=ch;continue;}
  if(ch==='"'){if(field!==''||closed)throw Error('Некорректные кавычки в CSV');quoted=true;continue;}
  if(ch===delimiter||ch==='\n'||ch==='\r'){
   row.push(field);field='';closed=false;
   if(ch!==delimiter){if(row.some(v=>v.trim()!==''))rows.push(row);row=[];if(ch==='\r'&&input[i+1]==='\n')i++;}
   if(rows.length>1501)throw Error('CSV ограничен 1500 строками');continue;
  }
  if(closed&&!/\s/.test(ch))throw Error('Лишние символы после закрывающей кавычки');
  field+=ch;
 }
 if(quoted)throw Error('Не закрыта кавычка CSV');
 row.push(field);if(row.some(v=>v.trim()!==''))rows.push(row);
 if(!rows.length)throw Error('CSV пуст');
 return {delimiter,rows};
}
export function reviewImport(text,kind='sales',previousSales=[]){
 const errors=[],issues=[];
 if(!Object.hasOwn(required,kind))return {valid:false,errors:['Неизвестный тип выгрузки'],issues:[],rows:[],kind};
 let parsed;
 try{parsed=csvRows(text);}catch(e){return {valid:false,errors:[e.message],issues:[],rows:[],kind};}
 const [head,...lines]=parsed.rows,cols=head.map(x=>x.trim());
 const missing=required[kind].filter(x=>!cols.includes(x));
 const duplicateColumns=cols.filter((x,i)=>cols.indexOf(x)!==i);
 if(missing.length)errors.push('Нет столбцов: '+missing.join(', '));
 if(duplicateColumns.length)errors.push('Дубли названий столбцов: '+[...new Set(duplicateColumns)].join(', '));
 if(!lines.length)errors.push('Нет строк событий');
 if(errors.length)return {valid:false,kind,errors,issues,rows:[],columns:cols};
 const saleIndex=new Map(previousSales.map(x=>[x.id,x]));const seen=new Set();const rowItems=[];
 for(let i=0;i<lines.length;i++){
  const cells=lines[i],number=i+2,row={};
  if(cells.length!==cols.length){issues.push({row:number,reason:'Количество полей не совпадает с заголовком'});continue;}
  cols.forEach((col,j)=>{row[col]=cells[j].trim();});
  let reasons=[];
  for(const col of required[kind])if(row[col]==='')reasons.push('Пустое поле '+col);
  if(seen.has(row.id))reasons.push('Повторяется ID события');seen.add(row.id);
  if(!storeIds.has(row.storeId))reasons.push('Неизвестный филиал');
  if(!productIds.has(row.modelId))reasons.push('Нет SKU в демонстрационном справочнике');
  if(!['XS','S','M','L','XL'].includes(row.size))reasons.push('Неизвестный размер');
  const date=kind==='stock'?row.asOf:row.date;
  if(!validDate(date))reasons.push('Некорректная календарная дата');
  for(const key of numeric[kind]){
   const source=row[key],value=Number(source);
   if(source===''||!Number.isFinite(value)||value<0||value>1e9||(kind==='stock'&&!integer(value,1000000))){reasons.push('Недопустимое значение '+key);}else row[key]=value;
  }
  if(kind==='returns'){
   const sold=saleIndex.get(row.saleId);
   if(!sold)reasons.push('Возврат не связан с импортированным чеком');
   else{
    if(sold.storeId!==row.storeId||sold.modelId!==row.modelId||sold.size!==row.size)reasons.push('SKU/филиал/размер не совпадает с чеком');
    if(validDate(row.date)&&row.date<sold.date)reasons.push('Возврат раньше чека');
    if(r5Finite(row.refundedPrice)&&row.refundedPrice>sold.paidPrice)reasons.push('Возврат больше оплаты');
    if(r5Finite(row.reversedCost)&&row.reversedCost>sold.cost)reasons.push('Сторно себестоимости выше чека');
   }
  }
  if(reasons.length)issues.push({row:number,id:row.id||'—',reason:reasons.join('; ')});
  else rowItems.push(Object.fromEntries(required[kind].map(k=>[k,row[k]])));
 }
 if(kind==='returns'){
  const bySale=new Set();
  for(const x of rowItems){if(bySale.has(x.saleId))issues.push({row:'—',id:x.id,reason:'Повторное сторнирование одного чека'});bySale.add(x.saleId);}
 }
 const accepted=issues.length?[]:rowItems; // Atomic stage: any invalid row blocks the entire batch.
 const totals=kind==='sales'?{revenue:SUM(rowItems,x=>x.paidPrice),cost:SUM(rowItems,x=>x.cost),gross:SUM(rowItems,x=>x.paidPrice-x.cost)}:
  kind==='returns'?{refund:SUM(rowItems,x=>x.refundedPrice),reverseCost:SUM(rowItems,x=>x.reversedCost)}:{units:SUM(rowItems,x=>x.quantity)};
 return {kind,valid:errors.length===0&&issues.length===0,columns:cols,rows:accepted,inspected:lines.length,validRows:rowItems.length,issues,errors,totals,delimiter:parsed.delimiter,provenance:'Локальная проверка файла; не импортировано в учёт или демопоказатели'};
}
const csvCell=v=>{let s=String(v??'');if(/^[\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
export function safeCsv(rows){return '\uFEFF'+rows.map(line=>line.map(csvCell).join(';')).join('\r\n')+'\r\n';}
export function reviewedCsv(review){if(!review.valid)return null;return safeCsv([required[review.kind],...review.rows.map(row=>required[review.kind].map(k=>row[k]))]);}
export function sampleCsv(kind='sales'){
 if(kind==='stock')return safeCsv([required.stock,['stock-example','2026-11-08','s1','JKT-AURA','L','Графит',3]]);
 if(kind==='returns')return safeCsv([required.returns,['return-example','2026-11-08','s1','sale-example','JKT-AURA','L',8900,4900]]);
 return safeCsv([required.sales,['sale-example','2026-11-08','s1','JKT-AURA','L',8900,4900]]);
}

const monday=date=>{const d=new Date(date+'T12:00:00Z');d.setUTCDate(d.getUTCDate()-(d.getUTCDay()+6)%7);return d.toISOString().slice(0,10);};
const weekNext=(day,n)=>new Date(dateMs(day)+n*7*86400000).toISOString().slice(0,10);
/** First OBSERVED paid check within the active window, not lifetime customer acquisition. */
export function retentionCohorts(dataset,scope,{weeks=4,minCohort=5}={}){
 if(!integer(weeks,8)||weeks<1||!integer(minCohort,1000))return {valid:false,errors:['Недопустимые параметры когорт'],cohorts:[]};
 const returned=new Set(dataset.returns.filter(x=>x.date<=scope.to).map(x=>x.saleId));
 const paid=scope.sales.filter(x=>x.memberId&&!returned.has(x.id)).sort((a,b)=>a.date.localeCompare(b.date)||a.id.localeCompare(b.id));
 const byMember=new Map();
 for(const sale of paid){if(!byMember.has(sale.memberId))byMember.set(sale.memberId,[]);byMember.get(sale.memberId).push(sale);}
 const cohorts=new Map();
 for(const [member,sales] of byMember){const started=monday(sales[0].date);if(!cohorts.has(started))cohorts.set(started,[]);cohorts.get(started).push({id:member,sales});}
 const result=[...cohorts.entries()].sort((a,b)=>b[0].localeCompare(a[0])).slice(0,12).map(([start,people])=>{
  const periods=[];
  for(let week=1;week<=weeks;week++){
   const end=weekNext(start,week+1);const cutoff=new Date(dateMs(end)-86400000).toISOString().slice(0,10);
   if(cutoff>scope.to){periods.push({week,rate:null,count:null,complete:false});continue;}
   let count=0,ids=[];
   for(const person of people){const hit=person.sales.find(s=>monday(s.date)===weekNext(start,week));if(hit){count++;ids.push(hit.id);}}
   periods.push({week,rate:count/people.length,count,complete:true,receiptIds:ids.slice(0,12)});
  }
  return {start,customers:people.length,status:people.length>=minCohort?'Описательная когорта':'Малая выборка',periods,firstReceiptIds:people.slice(0,12).map(x=>x.sales[0].id)};
 });
 const mature=result.flatMap(c=>c.periods.filter(x=>x.complete).map(x=>({cohort:c.start,n:c.customers,count:x.count,week:x.week})));
 return {valid:true,cohorts:result,members:byMember.size,sourceReceipts:paid.length,excludedReturns:scope.sales.filter(x=>x.memberId&&returned.has(x.id)).length,
  anonymousSales:scope.sales.filter(x=>!x.memberId).length,weekOne:mature.filter(x=>x.week===1).length?SUM(mature.filter(x=>x.week===1),x=>x.count)/SUM(mature.filter(x=>x.week===1),x=>x.n):null,
  limitations:['Первое наблюдение в выбранном периоде не равно первому визиту за всю жизнь.','Когорта определяется только по синтетическим идентификаторам программы лояльности.','Будущие недели не включаются в знаменатель и показаны как незавершённые.']};
}

/** Budget-constrained collection hypothesis. Distinct event streams cannot be summed into unique buyers. */
export function collectionPlan(dataset,scope,{budget=80000,cap=12,reserve=1,leadDays=21,category='all',seasonFactor=1}={}){
 const errors=[];
 if(!r5Finite(budget)||budget<0||budget>1e9)errors.push('Бюджет от 0 до 1 млрд ₽');
 if(!integer(cap,150))errors.push('Количество единиц от 0 до 150');
 if(!integer(reserve,100))errors.push('Резерв от 0 до 100');
 if(!integer(leadDays,365))errors.push('Срок поставки от 0 до 365 дней');
 if(!r5Finite(seasonFactor)||seasonFactor<.25||seasonFactor>3)errors.push('Сезонный коэффициент от 0,25 до 3');
 if(category!=='all'&&!dataset.products.some(p=>p.category===category))errors.push('Неизвестная категория');
 if(errors.length)return {valid:false,errors,rows:[],selected:[],spent:0,remaining:0};
 const groups=new Map(),key=e=>e.storeId+'|'+e.modelId+'|'+e.size;
 const ensure=e=>{const k=key(e);if(!groups.has(k))groups.set(k,{key:k,storeId:e.storeId,modelId:e.modelId,size:e.size,color:'Графит',requests:0,preorders:0,deposits:0,preferences:0,sales:0,returns:0,stock:0,ids:[]});return groups.get(k);};
 const add=(src,field,filter=()=>true)=>{for(const e of src){if(!filter(e))continue;const p=product(e.modelId);if(category!=='all'&&p.category!==category)continue;const g=ensure(e);g[field]++;if(g.ids.length<15)g.ids.push(e.id);}};
 add(scope.requests,'requests',e=>!e.purchased);
 add(scope.preorders,'preorders',e=>e.status!=='Отменён');
 add(scope.preorders,'deposits',e=>e.status!=='Отменён'&&e.depositPaid);
 add(scope.preferences,'preferences');
 add(scope.sales,'sales');
 add(scope.returns,'returns');
 for(const e of scope.stock){const p=product(e.modelId);if(category!=='all'&&p.category!==category)continue;if(e.color==='Графит')ensure(e).stock+=e.quantity;}
 const rows=[...groups.values()].map(g=>{
  const p=product(g.modelId),netSales=Math.max(0,g.sales-g.returns);
  const weighted=g.deposits*.85+(g.preorders-g.deposits)*.35+g.requests*.28+g.preferences*.08+netSales*.06;
  const signal=Math.ceil(weighted*seasonFactor),need=Math.max(0,signal-Math.max(0,g.stock-reserve));
  const confidence=g.deposits>0||g.requests>=5?'Умеренная':g.requests>0||g.preorders>0?'Ограниченная':'Недостаточно прямых сигналов';
  const score=g.deposits*10+g.requests*4+g.preorders*3+g.preferences*.4+netSales*.1;
  return {...g,product:p.name,category:p.category,cost:p.cost,unitGross:p.price-p.cost,score,netSales,need,confidence,orderUnits:0,plannedCost:0,estimatedGross:0};
 }).filter(x=>x.requests+x.preorders+x.preferences>0).sort((a,b)=>b.score-a.score||a.key.localeCompare(b.key));
 let remaining=budget,units=0;
 for(const r of rows){if(units>=cap)break;const affordable=r.cost>0?Math.floor(remaining/r.cost):0;const qty=Math.min(r.need,affordable,cap-units);
  if(qty<=0)continue;r.orderUnits=qty;r.plannedCost=qty*r.cost;r.estimatedGross=qty*r.unitGross;remaining=money(remaining-r.plannedCost);units+=qty;}
 const selected=rows.filter(x=>x.orderUnits>0);
 return {valid:true,rows,selected,spent:money(budget-remaining),remaining,units,unmet:SUM(rows,r=>Math.max(0,r.need-r.orderUnits)),leadDays,category,
  warnings:['Сигналы из разных каналов могут относиться к одному покупателю. Это не число уникальных заказов.',
   'Остатки - только учётный снимок, не гарантированная физическая доступность.',
   'Ожидаемая валовая прибыль не учитывает нереализованный товар, возвраты, налоги и маркетинг.']};
}
export function collectionCsv(plan){return safeCsv([['SKU','Размер','Филиал','Модель','Запросы','Предзаказы','Оплаченные задатки','Пожелания','Наличие','Предлагаемые единицы','Себестоимость за ед.','Затраты сценария','Уверенность','ID оснований'],
 ...plan.rows.map(r=>[r.modelId,r.size,r.storeId,r.product,r.requests,r.preorders,r.deposits,r.preferences,r.stock,r.orderUnits,r.cost,r.plannedCost,r.confidence,r.ids.join(' | ')])]);}

function quantile(values,p){if(!values.length)return null;const a=[...values].sort((x,y)=>x-y);const pos=(a.length-1)*p,lo=Math.floor(pos),hi=Math.ceil(pos);return Math.round(a[lo]+(a[hi]-a[lo])*(pos-lo));}
export function serviceHealth(scope,{sla=120,minSamples=10}={}){
 const errors=[];
 if(!integer(sla,7200)||sla<1)errors.push('SLA должен быть от 1 до 7200 секунд');
 if(!integer(minSamples,1000)||minSamples<1)errors.push('Минимальная выборка должна быть от 1 до 1000');
 if(errors.length)return {valid:false,errors,byStore:[],all:null};
 const summarise=(events,fittings,storeId)=>{
  const measured=events.filter(e=>r5Finite(e.responseSeconds)&&e.responseSeconds>=0),lat=measured.map(e=>e.responseSeconds),breaches=measured.filter(e=>e.responseSeconds>sla);
  const notPurchased=fittings.filter(e=>!e.purchased),reasoned=notPurchased.filter(e=>e.reason&&e.reasonType==='со слов покупателя');
  const reasonCounts={};for(const e of reasoned)reasonCounts[e.reason]=(reasonCounts[e.reason]||0)+1;
  return {storeId,requests:events.length,sample:measured.length,p50:quantile(lat,.5),p90:quantile(lat,.9),breaches:breaches.length,
   breachRate:measured.length?breaches.length/measured.length:null,resolved:events.filter(e=>e.resolved).length,resolutionRate:events.length?events.filter(e=>e.resolved).length/events.length:null,
   fittingCount:fittings.length,notPurchased:notPurchased.length,reasoned:reasoned.length,unknownReasons:notPurchased.length-reasoned.length,
   reasons:Object.entries(reasonCounts).sort((a,b)=>b[1]-a[1]).map(([reason,count])=>({reason,count})),adequate:measured.length>=minSamples,
   evidenceIds:breaches.slice(0,10).map(x=>x.id),fittingIds:reasoned.slice(0,10).map(x=>x.id)};
 };
 return {valid:true,all:summarise(scope.assistance,scope.fittings,'all'),byStore:STORES.map(s=>summarise(scope.assistance.filter(x=>x.storeId===s.id),scope.fittings.filter(x=>x.storeId===s.id),s.id)),sla,minSamples,
  limitations:['Время реакции измерено по QR-обращениям, а не по всем посетителям.','Причина отказа отражена только там, где покупатель сам назвал её.','Сравнение скорости и покупки не является доказательством влияния на продажи.']};
}
export function serviceCsv(report){return safeCsv([['Филиал','Событий','p50 сек','p90 сек','Выше SLA','Разрешены','Примерки без покупки','Названа причина','Неизвестная причина','ID просрочек'],...report.byStore.map(r=>[r.storeId,r.requests,r.p50??'',r.p90??'',r.breaches,r.resolved,r.notPurchased,r.reasoned,r.unknownReasons,r.evidenceIds.join(' | ')])]);}

export const BENCHMARK_METRICS={grossProfit:'Валовая прибыль',margin:'Валовая маржа',conversion:'Конверсия визитов',unmetPer100:'Запросы без покупки / 100 визитов',serviceP90:'p90 ответа, сек'};
export function branchBenchmark(dataset,scope,{metric='grossProfit',minDays=7}={}){
 const errors=[];if(!Object.hasOwn(BENCHMARK_METRICS,metric))errors.push('Неизвестный показатель');
 if(!integer(minDays,90)||minDays<1)errors.push('Минимальная длительность от 1 до 90 дней');
 if(errors.length)return {valid:false,errors,rows:[]};
 const days=Math.round((dateMs(scope.to)-dateMs(scope.from))/86400000)+1;
 const rows=STORES.map(store=>{
  const s=scopeData(dataset,{...scope.filter,period:'custom',from:scope.from,to:scope.to,store:store.id});
  const lat=s.assistance.map(e=>e.responseSeconds).filter(x=>r5Finite(x)&&x>=0);
  const normalized=s.totals.visits===null||s.totals.visits===0?null:s.totals.unsoldRequests/s.totals.visits*100;
  const m={grossProfit:s.totals.grossProfit,margin:s.totals.grossMargin,conversion:s.totals.conversion,unmetPer100:normalized,serviceP90:quantile(lat,.9)};
  const value=m[metric];
  return {id:store.id,name:store.name,value,metrics:m,days,visits:s.totals.visits,revenue:s.totals.revenue,grossProfit:s.totals.grossProfit,
   saleCount:s.sales.length,returns:s.returns.length,requests:s.requests.length,assistance:s.assistance.length,
   evidenceIds:[...s.sales.slice(0,3).map(x=>x.id),...s.requests.slice(0,3).map(x=>x.id),...s.assistance.slice(0,3).map(x=>x.id)],
   adequate:days>=minDays&&s.sales.length>=10&&(metric==='serviceP90'?lat.length>=10:metric==='conversion'||metric==='unmetPer100'?s.totals.visits!==null&&s.totals.visits>=50:true)};
 });
 const lowerIsBetter=metric==='serviceP90'||metric==='unmetPer100';
 const ranked=[...rows].sort((a,b)=>{if(a.value===null)return 1;if(b.value===null)return -1;return (lowerIsBetter?1:-1)*(a.value-b.value);});
 return {valid:true,metric,label:BENCHMARK_METRICS[metric],rows,ranked,days,comparable:rows.every(x=>x.adequate),
  caveats:[scope.filter.category!=='all'||scope.filter.model!=='all'||scope.filter.size!=='all'?'Для товарных фильтров посещения не относятся к выбранному SKU, поэтому конверсия и запросы на 100 визитов скрываются.':null,
   'Различия между филиалами могут объясняться трафиком, ассортиментом и локальными условиями. Это не доказанная причинность.',
   'Филиалы сопоставляются по одинаковому периоду; источник — синтетические чековые и операционные события.'].filter(Boolean)};
}
export function benchmarkCsv(report){return safeCsv([['Филиал','Период, дней','Выручка','Валовая прибыль','Чеков','Возвратов','Запросов','Помощь','Выбранный показатель','Достаточно данных','ID оснований'],...report.rows.map(r=>[r.name,r.days,r.revenue,r.grossProfit,r.saleCount,r.returns,r.requests,r.assistance,r.value??'',r.adequate?'Да':'Нет',r.evidenceIds.join(' | ')])]);}

export function cohortCsv(result){return safeCsv([['Когорта','Покупателей','Надёжность',...Array.from({length:8},(_,i)=>'Неделя '+(i+1))],...result.cohorts.map(c=>[c.start,c.customers,c.status,...Array.from({length:8},(_,i)=>c.periods[i]?(c.periods[i].complete?((c.periods[i].rate*100).toFixed(1)+'%'):'Не завершена'):'')])]);}
