/** ATELIER R6 — five isolated executive decision workflows.
 * Every financial figure is a synthetic scenario or observed gross, never proven incrementality.
 * Imported CSV never changes the local demo dataset and no network APIs are called.
 */
import {AS_OF,STORES,CATALOG,product,safeRatio} from './model.mjs';
import {csvRows,reviewImport} from './r5_core.mjs';
import {wilson} from './r3_core.mjs';

const r6_kindFields={sales:['id','date','storeId','modelId','size','paidPrice','cost'],returns:['id','date','storeId','saleId','modelId','size','refundedPrice','reversedCost'],stock:['id','asOf','storeId','modelId','size','color','quantity']};
const r6_aliases={
 id:['id','ид','номер','код операции','код записи','eventid','event id','transactionid'],
 date:['date','дата','дата продажи','дата возврата','transactiondate','operationdate'],
 asOf:['asof','as of','дата остатка','дата среза','дата остатков'],
 storeId:['storeid','store id','магазин','филиал','точка','склад','store'],
 modelId:['modelid','model id','sku','артикул','код номенклатуры','номенклатура','товар'],
 size:['size','размер'],color:['color','цвет'],paidPrice:['paidprice','сумма оплаты','сумма','оплата','выручка','saleprice'],
 cost:['cost','себестоимость','закупочная цена','себестоимость продажи'],
 saleId:['saleid','id чека','чек','номер чека','чек id','receiptid'],
 refundedPrice:['refundedprice','возврат денег','сумма возврата'],
 reversedCost:['reversedcost','сторно себестоимости','возврат себестоимости'],
 quantity:['quantity','остаток','количество','qty']
};
const r6_canonicalHeader=x=>String(x??'').normalize('NFKC').trim().toLowerCase().replace(/[ _\-]+/g,' ').replace(/\s+/g,' ');
const r6_SAFE=/^[^=+@\-\t\r\n]/;
const r6_clean=x=>String(x??'').trim();
const r6_finite=x=>typeof x==='number'&&Number.isFinite(x);
const r6_nonNegative=x=>r6_finite(x)&&x>=0;
const r6_int=x=>Number.isSafeInteger(x)&&x>=0;
const r6_dateValid=x=>typeof x==='string'&&/^\d{4}-\d\d-\d\d$/.test(x)&&new Date(x+'T12:00:00Z').toISOString?.() !== undefined;
const r6_csvSafe=v=>{const s=String(v??'');return /^[\s\t\r\n]*[=+@\-]/.test(s)?"'"+s:s;};
export function exportRowsCsv(rows){return '\uFEFF'+rows.map(row=>row.map(value=>`"${r6_csvSafe(value).replace(/"/g,'""')}"`).join(',')).join('\r\n')+'\r\n';}
export function inspectMapping(text,kind='sales'){
 if(!r6_kindFields[kind])return {valid:false,kind,errors:['Неизвестный тип событий'],columns:[],mapping:{},count:0};
 let parsed;try{parsed=csvRows(text);}catch(e){return {valid:false,kind,errors:[e.message],columns:[],mapping:{},count:0};}
 const [head,...rows]=parsed.rows;
 const columns=head.map(x=>r6_clean(x));const duplicate=columns.filter((x,i)=>columns.findIndex(y=>r6_canonicalHeader(y)===r6_canonicalHeader(x))!==i);
 const mapping={};for(const field of r6_kindFields[kind]){
  const names=new Set([field,...r6_aliases[field]||[]].map(r6_canonicalHeader));
  const found=columns.find(x=>names.has(r6_canonicalHeader(x)));
  mapping[field]=found||'';
 }
 const errors=[];if(duplicate.length)errors.push('Повторяются заголовки: '+[...new Set(duplicate)].join(', '));
 if(!rows.length)errors.push('Нет строк данных');
 return {valid:!errors.length,kind,columns,mapping,count:rows.length,errors,delimiter:parsed.delimiter};
}
const r6_storeLabel=x=>{
 const s=r6_clean(x);const normalized=r6_canonicalHeader(s);const match=STORES.find(k=>r6_canonicalHeader(k.name)===normalized||r6_canonicalHeader(k.short)===normalized||k.id===normalized);
 return match?.id||s;
};
/** Preview only, atomic: invalid or ambiguous fields reject the entire mapped batch. */
export function mapAndValidate(text,kind,mapping,previousSales=[]){
 const schema=inspectMapping(text,kind),errors=[...schema.errors];
 if(!schema.valid)return {valid:false,errors,issues:[],rows:[],kind};
 const fields=r6_kindFields[kind];const selections=fields.map(f=>mapping?.[f]||'');
 if(selections.some(s=>!schema.columns.includes(s)))errors.push('Не все обязательные поля сопоставлены с существующими колонками');
 if(new Set(selections).size!==selections.length)errors.push('Одна колонка сопоставлена нескольким обязательным полям');
 if(errors.length)return {valid:false,errors,issues:[],rows:[],kind};
 const lines=csvRows(text).rows.slice(1),issues=[],converted=[];
 for(let i=0;i<lines.length;i++){
  if(lines[i].length!==schema.columns.length){issues.push({row:i+2,reason:'Нарушено число столбцов'});continue;}
  const o=Object.fromEntries(fields.map((f,k)=>[f,r6_clean(lines[i][schema.columns.indexOf(selections[k])])]));
  o.storeId=r6_storeLabel(o.storeId);
  if(!r6_SAFE.test(o.id)){issues.push({row:i+2,reason:'Опасный/пустой идентификатор события'});continue;}
  converted.push(o);
 }
 if(issues.length)return {valid:false,errors,issues,rows:[],kind};
 const normalizedCsv=exportRowsCsv([fields,...converted.map(o=>fields.map(f=>o[f]))]);
 const check=reviewImport(normalizedCsv,kind,previousSales);
 // Do not use the sanitized output of exportRowsCsv to mask unsafe source data.
 return {...check,valid:check.valid&&errors.length===0,errors:[...errors,...check.errors],issues:[...issues,...(check.issues||[])],kind,normalizedCsv:check.valid?normalizedCsv:null,columnMapping:Object.fromEntries(fields.map((f,k)=>[f,selections[k]])),sourceRows:lines.length,source:'Загруженная CSV-выгрузка в памяти браузера, без импорта'};
}

/** Request-level evidence audit: no assumed history from an as-of-today stock snapshot. */
export function traceLostDemand(dataset,scope,{probability=20,handling=250,minGross=0}={}){
 const errors=[];if(!r6_finite(probability)||probability<0||probability>100)errors.push('Вероятность: 0–100%');
 if(!r6_nonNegative(handling))errors.push('Стоимость обработки не может быть отрицательной');
 if(!r6_nonNegative(minGross))errors.push('Минимальная маржа не может быть отрицательной');
 const sales=new Map(dataset.sales.map(s=>[s.id,s]));const stockIndex=new Map();
 for(const stock of dataset.stock){const key=[stock.modelId,stock.size,stock.color].join('|');if(!stockIndex.has(key))stockIndex.set(key,[]);stockIndex.get(key).push(stock);}
 const buckets={'confirmed':0,'solution-no-check':0,'cross-branch-now':0,'unresolved':0,'invalid-link':0};
 const rows=scope.requests.map(req=>{
  const p=dataset.products.find(x=>x.id===req.modelId);
  const sale=req.purchased?sales.get(req.saleId):null;
  const linked=Boolean(sale&&sale.originRequestId===req.id&&sale.modelId===req.modelId&&sale.size===req.size&&sale.storeId===req.storeId);
  const other=(stockIndex.get([req.modelId,req.size,req.color].join('|'))||[]).filter(s=>s.storeId!==req.storeId&&s.quantity>0&&s.asOf===AS_OF);
  const classification=req.purchased?(linked?'confirmed':'invalid-link'):req.solutionFound?'solution-no-check':other.length?'cross-branch-now':'unresolved';
  buckets[classification]++;
  const unitGross=p?p.price-p.cost:null;
  const eligible=!req.purchased&&req.consent&&unitGross!==null&&unitGross>=minGross; // no unsolicited outreach
  const grossScenario=eligible?(unitGross*probability/100-handling):null;
  return {id:req.id,date:req.date,storeId:req.storeId,modelId:req.modelId,product:p?.name||req.modelId,size:req.size,color:req.color,classification,
    stockOtherNow:other.map(s=>({storeId:s.storeId,quantity:s.quantity,stockId:s.id})),consent:!!req.consent,linkedSaleId:linked?sale.id:null,observedGross:linked?sale.paidPrice-sale.cost:null,
    grossScenario,unitGross,evidenceIds:[req.id,...(linked?[sale.id]:[]),...other.map(s=>s.id)].slice(0,12)};
 });
 const possible=rows.filter(r=>r.grossScenario!==null&&r.grossScenario>0);
 return {valid:!errors.length,errors,rows,buckets,requestCount:rows.length,linkedGross:rows.reduce((s,r)=>s+(r.observedGross||0),0),
   hypotheticalNet:possible.reduce((s,r)=>s+r.grossScenario,0),possibleCount:possible.length,negativeScenarios:rows.filter(r=>r.grossScenario!==null&&r.grossScenario<=0).length,
   incrementalProven:false,caveats:['Учетные остатки — снимок на текущую дату, а не доказательство доступности на дату обращения.',
   'Запрос без покупки не равен потерянной продаже. Оценка строится только по согласившимся незавершённым обращениям и ручным допущениям.',
   'Согласие учитывается отдельно: без него нельзя отправлять персональное уведомление.']};
}

/** Return denominator = receipts sold in the selected cohort; returns are traced through AS_OF.
 * Right censoring remains visible. We never claim a batch defect without batch/source evidence.
 */
export function analyzeReturns(dataset,scope,{dimension='model',minSales=5}={}){
 const errors=[];if(!['model','size','store'].includes(dimension))errors.push('Неизвестная группировка');
 if(!r6_int(minSales)||minSales<1||minSales>10000)errors.push('Минимум чеков: от 1 до 10000');
 if(errors.length)return {valid:false,errors,rows:[],sufficient:0};
 const groups=new Map();const sourceSales=new Map(scope.sales.map(s=>[s.id,s]));const allReturns=new Map();
 for(const ret of dataset.returns){if(ret.date>AS_OF)continue;if(!allReturns.has(ret.saleId))allReturns.set(ret.saleId,[]);allReturns.get(ret.saleId).push(ret);}
 const invalid=[];
 for(const sale of scope.sales){
  const key=dimension==='model'?sale.modelId:dimension==='size'?sale.size:sale.storeId;
  if(!groups.has(key))groups.set(key,{key,receipts:0,returned:0,refunded:0,reverseCost:0,ids:[],reasonCounts:new Map(),firstDate:sale.date});
  const g=groups.get(key);g.receipts++;g.ids.push(sale.id);if(sale.date<g.firstDate)g.firstDate=sale.date;
  const matched=(allReturns.get(sale.id)||[]).filter(ret=>ret.storeId===sale.storeId&&ret.modelId===sale.modelId&&ret.size===sale.size&&ret.date>=sale.date);
  if(matched.length>1)invalid.push('Несколько возвратов к '+sale.id);
  if(matched.length){g.returned++;const r=matched[0];g.refunded+=r.refundedPrice;g.reverseCost+=r.reversedCost;g.ids.push(r.id);g.reasonCounts.set(r.reason||'Причина неизвестна',(g.reasonCounts.get(r.reason||'Причина неизвестна')||0)+1);}
 }
 const rows=[...groups.values()].map(g=>({key:g.key,label:dimension==='model'?(dataset.products.find(x=>x.id===g.key)?.name||g.key):dimension==='store'?(STORES.find(s=>s.id===g.key)?.name||g.key):g.key,
  receipts:g.receipts,returned:g.returned,rate:safeRatio(g.returned,g.receipts),interval:wilson(g.returned,g.receipts),observedGrossReversed:g.refunded-g.reverseCost,
  reasons:[...g.reasonCounts.entries()].sort((a,b)=>b[1]-a[1]).map(([name,count])=>({name,count})),sufficient:g.receipts>=minSales,ids:g.ids.slice(0,35),firstDate:g.firstDate})).sort((a,b)=>(b.sufficient-a.sufficient)||((b.rate??0)-(a.rate??0))||b.receipts-a.receipts);
 const youngest=scope.sales.filter(s=>(Date.parse(AS_OF)-Date.parse(s.date))<14*86400000).length;
 return {valid:true,errors:invalid,rows,sufficient:rows.filter(r=>r.sufficient).length,receipts:scope.sales.length,returns:rows.reduce((s,r)=>s+r.returned,0),
  observedGrossReversed:rows.reduce((s,r)=>s+r.observedGrossReversed,0),youngest,causalityProven:false,
  caveats:['Знаменатель — чеки выбранной когорты продаж; возвраты связаны с ними до даты отчёта, даже если произошли позже выбранного периода.',
   'Новые чеки ещё не прошли полное окно возможного возврата. Интервалы Wilson показывают неопределённость доли, но не причину.',
   'Партии поставок отсутствуют в демоданных; дефект партии автоматически не диагностируется.']};
}

const r6_FNV_SEED=2166136261;
function r6_fnv(text){let h=r6_FNV_SEED;for(const char of text){h^=char.charCodeAt(0);h=Math.imul(h,16777619);}return h>>>0;}
/** Planning only: sample sizing assumes independent request-level randomization, an unverified assumption. */
export function designPilot(scope,{baseline=12,lift=5,unitGross=4000,fixedCost=15000,costPerTreatment=50,days=14,seed='OSMANX-001'}={}){
 const errors=[];
 if(!r6_finite(baseline)||baseline<=0||baseline>=100)errors.push('Базовая конверсия строго между 0 и 100%');
 if(!r6_finite(lift)||lift<=0||baseline+lift>=100)errors.push('Прирост должен быть положительным, сумма с базой меньше 100%');
 if(!r6_nonNegative(unitGross)||!r6_nonNegative(fixedCost)||!r6_nonNegative(costPerTreatment))errors.push('Финансовые параметры не могут быть отрицательными');
 if(!r6_int(days)||days<1||days>180)errors.push('Период: от 1 до 180 дней');
 if(typeof seed!=='string'||seed.length<3||seed.length>36||!/^[\w-]+$/.test(seed))errors.push('Код распределения: 3–36 латинских букв, цифр или дефисов');
 if(errors.length)return {valid:false,errors,assignments:[],nPerArm:null};
 const p0=baseline/100,p1=(baseline+lift)/100,pbar=(p0+p1)/2,zA=1.95996398454,zB=.84162123357;
 const nPerArm=Math.ceil(2*(zA*Math.sqrt(2*pbar*(1-pbar))+zB*Math.sqrt(p0*(1-p0)+p1*(1-p1)))**2/(p1-p0)**2);
 const requests=scope.requests.filter(x=>!x.purchased);
 const assignments=requests.map(x=>({requestId:x.id,storeId:x.storeId,date:x.date,arm:((r6_fnv(seed+'|'+x.id)>>>12)&1)===0?'test':'control'}));
 const testCount=assignments.filter(x=>x.arm==='test').length,controlCount=assignments.length-testCount;
 const samplePerDay=requests.length/Math.max(1,Math.round((Date.parse(scope.to)-Date.parse(scope.from))/86400000)+1);
 const estimatedDays=samplePerDay>0?Math.ceil(2*nPerArm/samplePerDay):null;
 const treated=nPerArm,expectedDifference=treated*(p1-p0),expectedGross=expectedDifference*unitGross;
 const estimatedCost=fixedCost+treated*costPerTreatment,expectedNet=expectedGross-estimatedCost;
 return {valid:true,errors:[],nPerArm,totalRequired:2*nPerArm,testCount,controlCount,assignments,estimatedDays,days,feasible:estimatedDays!==null&&estimatedDays<=days,
   baseline:p0,target:p1,expectedDifference,expectedGross,estimatedCost,expectedNet,breakEvenLift:unitGross>0?((estimatedCost/treated)/unitGross)*100:null,
   confidence:'План мощности: нормальная аппроксимация, α=5%, мощность≈80%, независимые события; проверка гипотезы ещё не проводилась.',
   caveats:['Один покупатель может дать несколько запросов: независимость событий пока не подтверждена.',
    'Распределение детерминировано ID обращения и кодом пилота, это не доказательство отсутствия смещения.',
    'Финансовый результат — сценарий ожидаемой разницы, не доход и не доказательство эффекта.']};
}
export function assignmentsCsv(plan){return exportRowsCsv([['ID обращения','Дата','Филиал','Группа','Исходный уровень %','Плановый прирост п.п.'],...plan.assignments.map(x=>[x.requestId,x.date,x.storeId,x.arm,Math.round(plan.baseline*100),Math.round((plan.target-plan.baseline)*100)])]);}

export const BOARD_VERSION=1;
const r6_BOARD_STATUS=['planned','working','review','closed'];
export const BOARD_OWNERS=['Управляющий сети','Управляющий филиалом','Аналитик','Мерчендайзер'];
export function restoreBoard(payload){
 if(!payload||payload.version!==BOARD_VERSION||!Array.isArray(payload.items))return [];
 return payload.items.slice(0,100).filter(x=>x&&/^ACT-\d{4,}$/.test(x.id)&&typeof x.title==='string'&&x.title.length<=150&&r6_BOARD_STATUS.includes(x.status)&&Array.isArray(x.history)&&BOARD_OWNERS.includes(x.owner)&&typeof x.due==='string'&&/^\d{4}-\d\d-\d\d$/.test(x.due))
 .map(x=>({...x,evidenceIds:(Array.isArray(x.evidenceIds)?x.evidenceIds:[]).filter(e=>typeof e==='string').slice(0,50),history:x.history.slice(-30)}));
}
export function createBoardItem(items,{title,owner='Управляющий сети',due=AS_OF,priority='normal',evidenceIds=[],scenario='balanced',type='verification'}={}){
 if(items.length>=100)throw Error('Локальный журнал ограничен 100 задачами');
 const t=r6_clean(title).slice(0,150);if(t.length<5)throw Error('Название задачи должно содержать минимум 5 символов');
 if(!BOARD_OWNERS.includes(owner))throw Error('Неизвестный исполнитель');
 if(!['normal','urgent'].includes(priority))throw Error('Некорректный приоритет');
 if(!/^\d{4}-\d{2}-\d{2}$/.test(due)||Number.isNaN(Date.parse(due+'T12:00:00Z'))||new Date(due+'T12:00:00Z').toISOString().slice(0,10)!==due)throw Error('Некорректный срок');
 if(!Array.isArray(evidenceIds)||evidenceIds.length>50||evidenceIds.some(x=>typeof x!=='string'||x.length>95))throw Error('Неправильные ссылки на события');
 const max=items.reduce((m,x)=>Math.max(m,Number(x.id.split('-')[1])||0),0);
 const entry={id:'ACT-'+String(max+1).padStart(4,'0'),title:t.replace(/[<>]/g,''),owner,due,priority,status:'planned',type,scenario,
   evidenceIds:[...new Set(evidenceIds)].slice(0,50),outcome:null,history:[{at:AS_OF,from:null,to:'planned',note:'Создан план проверки'}]};
 return {items:[...items,entry],created:entry};
}
export function advanceBoard(items,id,next,{outcome=''}={}){
 const found=items.find(x=>x.id===id);if(!found)throw Error('Задача не найдена');
 const allowed={planned:['working'],working:['review'],review:['working','closed'],closed:[]};
 if(!allowed[found.status].includes(next))throw Error('Переход статуса не разрешён');
 const reason=r6_clean(outcome).slice(0,500);
 if(next==='closed'&&reason.length<10)throw Error('Для завершения нужно заключение от 10 символов');
 const updated={...found,status:next,outcome:next==='closed'?reason:found.outcome,history:[...found.history,{at:AS_OF,from:found.status,to:next,note:next==='closed'?reason:'Изменён статус'}].slice(-30)};
 return items.map(x=>x.id===id?updated:x);
}
export function boardSummary(items,scenario='balanced',asOf=AS_OF){
 const list=items.filter(x=>x.scenario===scenario);
 return {list,total:list.length,open:list.filter(x=>x.status!=='closed').length,closed:list.filter(x=>x.status==='closed').length,
   overdue:list.filter(x=>x.status!=='closed'&&x.due<asOf).length,urgent:list.filter(x=>x.priority==='urgent'&&x.status!=='closed').length};
}
export function boardCsv(items){return exportRowsCsv([['ID','Название','Сценарий','Исполнитель','Срок','Приоритет','Статус','Итог','ID событий'],...items.map(x=>[x.id,x.title,x.scenario,x.owner,x.due,x.priority,x.status,x.outcome||'',x.evidenceIds.join(' | ')])]);}
