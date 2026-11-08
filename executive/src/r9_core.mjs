/** OSMANX ATELIER R9 — reconciliation of locally supplied payment and bank files.
 *  No network, bank API, writes to POS, or persistence of imported rows.
 *  Absence of a bank row is an evidence gap, NEVER proof of theft or lost money.
 */
import {csvRows} from './r5_core.mjs';
import {AS_OF} from './model.mjs';
import {inspectWorkingSet,salesLedger,r8Csv} from './r8_core.mjs';
export const R9_SCHEMA=Object.freeze({
 operations:['id','date','storeId','kind','referenceId','amount','fee','method','batchId'],
 settlements:['id','date','storeId','batchId','netAmount']
});
export const R9_MAX_ROWS=1500;
const r9IdOK=x=>typeof x==='string'&&/^[\p{L}\p{N}][\p{L}\p{N}_.:-]{0,59}$/u.test(x);
const r9DateOK=x=>typeof x==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(x)&&!Number.isNaN(Date.parse(x+'T12:00:00Z'))&&new Date(x+'T12:00:00Z').toISOString().slice(0,10)===x;
const r9Cents=x=>Math.round(x*100);
const r9Rub=x=>Math.round(x)/100;
const r9Sum=(arr,fn)=>arr.reduce((a,x)=>a+fn(x),0);
const r9MoneyReg=/^\d{1,10}(?:\.\d{1,2})?$/;
const r9SignedMoneyReg=/^-?\d{1,10}(?:\.\d{1,2})?$/;
const r9ValidMoney=(s,signed=false)=>typeof s==='string'&&(signed?r9SignedMoneyReg:r9MoneyReg).test(s)&&Number.isSafeInteger(r9Cents(Number(s)))&&Math.abs(Number(s))<=1e9;
const r9Unique=a=>[...new Set(a)].sort((x,y)=>x.localeCompare(y,'ru'));
const r9Digest=s=>{let h=2166136261;for(const c of String(s))h=Math.imul(h^c.charCodeAt(0),16777619)>>>0;return h.toString(16).padStart(8,'0');};
export function r9Empty(sourceVersion=0){return {operations:[],settlements:[],sourceVersion,origin:'',revision:0};}
export function r9Example(){return {
 operations:r8Csv([R9_SCHEMA.operations,
  ['op-01','2026-11-01','store-A','capture','s-101',8900,180,'card','batch-A'],
  ['op-02','2026-11-01','store-A','capture','s-101',8900,0,'cash',''],
  ['op-03','2026-11-02','store-B','capture','s-102',8900,178,'card','batch-B'],
  ['op-04','2026-11-03','store-C','capture','s-103',7000,140,'card','batch-C'],
  ['op-05','2026-11-05','store-B','refund','r-101',8900,0,'card','batch-B-ref']]),
 settlements:r8Csv([R9_SCHEMA.settlements,
  ['sett-01','2026-11-02','store-A','batch-A',8720],
  ['sett-02','2026-11-03','store-B','batch-B',8722],
  ['sett-03','2026-11-04','store-C','batch-C',6860],
  ['sett-04','2026-11-06','store-B','batch-B-ref',-8900]])
};}
export function r9InspectCsv(kind,text,{asOf=AS_OF}={}){
 if(!Object.hasOwn(R9_SCHEMA,kind))return {valid:false,rows:[],errors:['Неизвестный вид реестра']};
 if(typeof text!=='string'||!text.trim()||text.length>1200000)return {valid:false,rows:[],errors:['Пустой или слишком большой CSV (предел 1,2 МБ)']};
 let parsed;try{parsed=csvRows(text);}catch(e){return {valid:false,rows:[],errors:['CSV: '+e.message]};}
 const [header,...body]=parsed.rows||[];const fields=(header||[]).map(v=>v.trim()),expected=R9_SCHEMA[kind];
 if(fields.length!==expected.length||fields.some((v,i)=>v!==expected[i]))return {valid:false,rows:[],errors:['Заголовок должен быть: '+expected.join(';')]};
 if(!body.length||body.length>R9_MAX_ROWS)return {valid:false,rows:[],errors:['Требуется от 1 до 1500 строк']};
 const errors=[],rows=[],ids=new Set();
 for(let i=0;i<body.length;i++){
  const values=body[i],line=i+2;
  if(values.length!==fields.length){errors.push(`Строка ${line}: неверное число колонок`);continue;}
  const o=Object.fromEntries(fields.map((k,j)=>[k,values[j].trim()]));const problems=[];
  if(!r9IdOK(o.id)||ids.has(o.id))problems.push('недопустимый/повторный ID');else ids.add(o.id);
  for(const k of ['storeId','batchId','referenceId'])if(k in o&&o[k]!==''&&!r9IdOK(o[k]))problems.push(k+' содержит запрещённые символы');
  if(!r9IdOK(o.storeId))problems.push('storeId обязателен');
  if(!r9DateOK(o.date)||o.date>asOf)problems.push('неверная или будущая дата');
  if(kind==='operations'){
   if(!['capture','refund'].includes(o.kind))problems.push('kind = capture / refund');
   if(!r9IdOK(o.referenceId))problems.push('нужна ссылка на чек/возврат');
   if(!['card','cash'].includes(o.method))problems.push('method = card / cash');
   if(o.method==='card'&&!r9IdOK(o.batchId))problems.push('для card нужен batchId');
   if(o.method==='cash'&&o.batchId!=='')problems.push('cash не входит в банковский пакет');
   if(!r9ValidMoney(o.amount)||Number(o.amount)<=0)problems.push('сумма > 0, до 2 десятичных знаков');
   if(!r9ValidMoney(o.fee))problems.push('некорректная комиссия');
   if(!problems.length){o.amount=Number(o.amount);o.fee=Number(o.fee);
    if(r9Cents(o.fee)>r9Cents(o.amount))problems.push('комиссия превышает операцию');
    if(o.method==='cash'&&o.fee!==0)problems.push('комиссия cash должна быть 0');
   }
  }else{
   if(!r9IdOK(o.batchId))problems.push('нужен batchId');
   if(!r9ValidMoney(o.netAmount,true))problems.push('некорректная сумма поступления');
   if(!problems.length)o.netAmount=Number(o.netAmount);
  }
  if(problems.length)errors.push(`Строка ${line}: ${problems.join(', ')}`);else rows.push(o);
 }
 return {valid:errors.length===0,errors:errors.slice(0,30),rows:errors.length?[]:rows,inspected:body.length};
}
export function r9AcceptCsv(ws,oldSet,kind,text,{asOf=AS_OF,origin='local'}={}){
 const inspected=inspectWorkingSet(ws,{asOf});
 if(!inspected.valid||!ws.sales?.length)return {accepted:false,workspace:oldSet,errors:['Сначала примите проверенные чеки в ATELIER R8']};
 if(inspected.example&&origin!=='example'||!inspected.example&&origin!=='local')return {accepted:false,workspace:oldSet,errors:['Учебные и рабочие файлы нельзя смешивать']};
 const parsed=r9InspectCsv(kind,text,{asOf});if(!parsed.valid)return {accepted:false,workspace:oldSet,errors:parsed.errors};
 if(oldSet.sourceVersion!==ws.version&&oldSet.revision>0)return {accepted:false,workspace:oldSet,errors:['Набор R8 изменён; очистите предыдущие платёжные файлы']};
 if(oldSet.origin&&oldSet.origin!==origin)return {accepted:false,workspace:oldSet,errors:['Сначала очистите R9: источники разных типов нельзя смешивать']};
 const accepted={...oldSet,[kind]:parsed.rows,sourceVersion:ws.version,origin,revision:oldSet.revision+1};
 return {accepted:true,workspace:accepted,errors:[],inspected:parsed.inspected};
}
function issue(kind,storeId,ref,expected,observed,description,severity='review'){
 const key=r9Digest([kind,storeId,ref].join('|'));
 return {key,kind,storeId,ref,expected:r9Rub(expected),observed:r9Rub(observed),difference:r9Rub(observed-expected),description,severity};
}
export function r9Reconcile(ws,file){
 const validR8=inspectWorkingSet(ws),ledger=salesLedger(ws);
 const errors=[];
 if(!validR8.valid||!ledger.valid)errors.push('Исходные чеки или возвраты R8 не прошли проверку');
 if(!file?.operations?.length)errors.push('Нет файла операций эквайринга/кассы');
 if(file?.revision&&file.sourceVersion!==ws.version)errors.push('Версия чеков изменилась: загрузите платёжные CSV заново');
 if(file?.origin&&(validR8.example?'example':'local')!==file.origin)errors.push('Тип исходных данных не соответствует рабочему набору');
 if(errors.length)return {valid:false,errors,issues:[],rows:[],summary:null};
 const saleById=new Map(ws.sales.map(x=>[x.id,x]));
 const returnsById=new Map(ws.returns.map(x=>[x.id,x]));
 const linked=new Map(),issues=[],rows=[];
 const byKind={capture:new Map(),refund:new Map()};
 let cardCents=0,cashCents=0,refundCents=0,feesCents=0;
 for(const p of file.operations){
  const table=p.kind==='capture'?saleById:returnsById,record=table.get(p.referenceId);
  const collected=byKind[p.kind],arr=collected.get(p.referenceId)||[];arr.push(p);collected.set(p.referenceId,arr);
  if(p.kind==='capture'){if(p.method==='cash')cashCents+=r9Cents(p.amount);else cardCents+=r9Cents(p.amount);}else refundCents+=r9Cents(p.amount);
  feesCents+=r9Cents(p.fee);
  if(!record){issues.push(issue('orphan-'+p.kind,p.storeId,p.referenceId,0,r9Cents(p.amount),'Операция без документа-основания','critical'));continue;}
  const documentStore=p.kind==='refund'?(saleById.get(record.saleId)?.storeId):record.storeId;
  if(documentStore!==p.storeId)issues.push(issue('wrong-store',p.storeId,p.id,0,r9Cents(p.amount),'Филиал операции не совпадает с документом','critical'));
  if(p.date<record.date)issues.push(issue('before-document',p.storeId,p.id,0,r9Cents(p.amount),'Дата оплаты раньше даты документа','review'));
 }
 for(const [kind,records] of [['capture',ws.sales],['refund',ws.returns]]){
  for(const record of records){const ops=byKind[kind].get(record.id)||[];
   const required=r9Cents(kind==='capture'?record.revenue:record.refund),received=r9Sum(ops,x=>r9Cents(x.amount));
   const status=received===required?'matched':received<required?'short':'excess';
   rows.push({kind,storeId:record.storeId,date:record.date,ref:record.id,required:r9Rub(required),received:r9Rub(received),difference:r9Rub(received-required),status,operations:ops.length});
   if(received!==required)issues.push(issue(status+'-'+kind,record.storeId,record.id,required,received,kind==='capture'?'Расхождение суммы оплаты и чека':'Расхождение суммы возврата и документа',received>required?'critical':'review'));
  }
 }
 const sourceGrossCents=r9Cents(ledger.gross);
 const summary={documents:rows.length,matched:rows.filter(x=>x.status==='matched').length,
  expectedSales:ledger.revenue,expectedRefunds:ledger.refund,expectedNet:ledger.netRevenue,
  observedCaptures:r9Rub(cardCents+cashCents),observedRefunds:r9Rub(refundCents),fees:r9Rub(feesCents),
  observedNet:r9Rub(cardCents+cashCents-refundCents),cash:r9Rub(cashCents),card:r9Rub(cardCents),
  expectedGross:ledger.gross,observedAfterFees:r9Rub(sourceGrossCents-feesCents),
  difference:r9Rub(cardCents+cashCents-refundCents-r9Cents(ledger.netRevenue)),
  bankVerified:false,incrementalProven:false};
 return {valid:true,errors:[],issues,rows,summary,version:file.revision,example:validR8.example,origin:file.origin};
}
export function r9Settlements(ws,file,{asOf=AS_OF,maxLagDays=3}={}){
 const audit=r9Reconcile(ws,file);
 if(!audit.valid)return {valid:false,errors:audit.errors,batches:[],issues:[],totals:null};
 if(!Number.isSafeInteger(maxLagDays)||maxLagDays<0||maxLagDays>30)return {valid:false,errors:['Задержка: 0–30 суток'],batches:[],issues:[],totals:null};
 const groups=new Map(),bank=new Map(),issues=[];
 for(const p of file.operations.filter(x=>x.method==='card')){
  const key=p.storeId+'|'+p.batchId,entry=groups.get(key)||{key,storeId:p.storeId,batchId:p.batchId,expectedCents:0,count:0,first:p.date,last:p.date};
  entry.expectedCents+=(p.kind==='capture'?1:-1)*r9Cents(p.amount)-r9Cents(p.fee);entry.count++;
  entry.first=entry.first<p.date?entry.first:p.date;entry.last=entry.last>p.date?entry.last:p.date;groups.set(key,entry);
 }
 for(const s of file.settlements||[]){const key=s.storeId+'|'+s.batchId;const group=bank.get(key)||{items:[],actualCents:0};group.actualCents+=r9Cents(s.netAmount);group.items.push(s);bank.set(key,group);}
 const batches=[];
 for(const group of groups.values()){
  const settlement=bank.get(group.key);const received=settlement?.actualCents??null;
  const latest=settlement?.items.map(x=>x.date).sort().at(-1)||null;
  const lag=latest?Math.round((Date.parse(latest+'T12:00:00Z')-Date.parse(group.last+'T12:00:00Z'))/86400000):null;
  const status=received==null?'not-provided':received===group.expectedCents?'matched':received<group.expectedCents?'short':'excess';
  const row={...group,expected:r9Rub(group.expectedCents),received:received==null?null:r9Rub(received),difference:received==null?null:r9Rub(received-group.expectedCents),status,settlementDate:latest,lagDays:lag};batches.push(row);
  if(status!=='matched')issues.push(issue('settlement-'+status,group.storeId,group.batchId,group.expectedCents,received??0,received==null?'Нет подтверждающей строки выписки; не доказана недостача':'Сумма выписки отличается от суммы пакета',status==='not-provided'?'review':'critical'));
  if(lag!=null&&lag<0)issues.push(issue('settlement-before',group.storeId,group.batchId,0,0,'Дата зачисления раньше последней операции','critical'));
  else if(lag!=null&&lag>maxLagDays)issues.push(issue('settlement-delay',group.storeId,group.batchId,0,0,`Задержка зачисления ${lag} дней; проверьте банковский договор`));
 }
 for(const [key,s] of bank)if(!groups.has(key)){const row=s.items[0];issues.push(issue('unknown-batch',row.storeId,row.batchId,0,s.actualCents,'Зачисление без операций данного пакета','critical'));}
 batches.sort((a,b)=>a.key.localeCompare(b.key));
 const provided=batches.filter(x=>x.received!==null),matched=provided.filter(x=>x.status==='matched').length;
 const totals={batches:batches.length,provided:provided.length,matched,expected:r9Rub(r9Sum(batches,x=>x.expectedCents)),observed:r9Rub(r9Sum(provided,x=>r9Cents(x.received))),pending:batches.length-provided.length,verified:issues.length===0&&audit.issues.length===0&&batches.length>0&&provided.length===batches.length};
 return {valid:true,errors:[],batches,issues,totals,maxLagDays};
}
export const R9_STATUSES=Object.freeze(['new','checking','resolved','not-applicable']);
export const R9_REASONS=Object.freeze(['statement-checked','pos-corrected','time-lag-confirmed','duplicate-cleared','manual-review']);
export function r9Cases(audit,settlements,triage={}){
 if(!audit.valid||!settlements.valid)return {valid:false,items:[],total:0,closed:0};
 const items=[...audit.issues,...settlements.issues].map(x=>({...x,...(triage[x.key]||{status:'new',reason:''})}));
 return {valid:true,items,total:items.length,closed:items.filter(x=>['resolved','not-applicable'].includes(x.status)).length,critical:items.filter(x=>x.severity==='critical').length};
}
export function r9Transition(triage,known,key,nextStatus,reason='',evidenceId=''){
 if(!known?.items?.some(x=>x.key===key))throw Error('Неизвестное расхождение');
 if(!R9_STATUSES.includes(nextStatus))throw Error('Недопустимый статус');
 const previous=triage[key]?.status||'new';
 const legal={new:['checking'],checking:['resolved','not-applicable','new'],resolved:['checking'], 'not-applicable':['checking']};
 if(!legal[previous].includes(nextStatus))throw Error('Нельзя перейти из '+previous+' в '+nextStatus);
 if(['resolved','not-applicable'].includes(nextStatus)&&!R9_REASONS.includes(reason))throw Error('Для закрытия нужна классификация причины');
 if(['resolved','not-applicable'].includes(nextStatus)&&!/^[-\p{L}\p{N}_.:]{6,40}$/u.test(evidenceId))throw Error('Укажите код подтверждающего документа без персональных данных (6–40 символов)');
 return {...triage,[key]:{status:nextStatus,reason:['resolved','not-applicable'].includes(nextStatus)?reason:'',evidenceId:['resolved','not-applicable'].includes(nextStatus)?evidenceId:'',at:AS_OF}};
}
export function r9DailyClose(ws,file,audit){
 if(!audit.valid)return {valid:false,errors:audit.errors,days:[]};
 const dayMap=new Map();
 function get(store,date){const key=store+'|'+date;if(!dayMap.has(key))dayMap.set(key,{storeId:store,date,docsCents:0,eventsCents:0,feesCents:0,captures:0,refunds:0});return dayMap.get(key);}
 for(const x of ws.sales)get(x.storeId,x.date).docsCents+=r9Cents(x.revenue);
 for(const x of ws.returns){const sale=ws.sales.find(s=>s.id===x.saleId);if(sale)get(sale.storeId,x.date).docsCents-=r9Cents(x.refund);}
 for(const x of file.operations){const row=get(x.storeId,x.date);row.eventsCents+=(x.kind==='capture'?1:-1)*r9Cents(x.amount);row.feesCents+=r9Cents(x.fee);if(x.kind==='capture')row.captures++;else row.refunds++;}
 const days=[...dayMap.values()].map(x=>({storeId:x.storeId,date:x.date,documents:r9Rub(x.docsCents),events:r9Rub(x.eventsCents),fees:r9Rub(x.feesCents),netAfterFees:r9Rub(x.eventsCents-x.feesCents),timingDifference:r9Rub(x.eventsCents-x.docsCents),captures:x.captures,refunds:x.refunds})).sort((a,b)=>a.date.localeCompare(b.date)||a.storeId.localeCompare(b.storeId));
 return {valid:true,days,disclaimer:'Разница календарных дат не доказывает потери: оплаты и зачисления могут проходить в разные дни.'};
}
export function r9Pack(ws,file,triage,{maxLagDays=3}={}){
 const audit=r9Reconcile(ws,file),bank=r9Settlements(ws,file,{maxLagDays});
 if(!audit.valid||!bank.valid)return {valid:false,errors:[...audit.errors,...bank.errors],claims:[],caseSummary:null};
 const cases=r9Cases(audit,bank,triage),day=r9DailyClose(ws,file,audit);
 return {valid:true,errors:[],example:audit.example,origin:file.origin,
  claims:[{kind:'ДОКУМЕНТ',label:'Оплаченные чеки R8',value:audit.summary.expectedSales,method:'Выручка по загруженным чекам, не банковская выписка'},
   {kind:'ДОКУМЕНТ',label:'Возвраты R8',value:audit.summary.expectedRefunds,method:'Возвраты по связанным документам'},
   {kind:'ЗАПИСИ',label:'Поступления по операциям минус возвраты',value:audit.summary.observedNet,method:'Пользовательский CSV операций, без банковского подтверждения'},
   {kind:'КОМИССИЯ',label:'Комиссии операций',value:audit.summary.fees,method:'Поле fee в загруженном реестре'},
   {kind:'СЦЕНАРИЙ',label:'Валовая прибыль после комиссии',value:audit.summary.observedAfterFees,method:'Прибыль по чекам минус комиссии, при неполной сверке не подтверждена'},
   {kind:'КОНТРОЛЬ',label:'Совпавшие банковские пакеты',value:bank.totals.matched,method:'Сопоставление batchId+storeId, не проверка подлинности файла'}],
  audit,bank,cases,day,closeReady:cases.total===0&&bank.totals.verified,
  warnings:['Источники предоставлены пользователем и не подтверждают подлинность банка, 1С или POS.',
   'Расхождение по датам само по себе не означает утрату денежных средств.',
   'Результат не доказывает дополнительную прибыль или отсутствие мошенничества.']};
}
export function r9ReportCsv(pack){if(!pack.valid)throw Error('Нет сверенного отчёта');return r8Csv([
 ['Тип утверждения','Показатель','Значение','Метод'],...pack.claims.map(x=>[x.kind,x.label,x.value,x.method]),
 ['ИТОГ','Необработанных расхождений',pack.cases.total-pack.cases.closed,'Закрытые кейсы требуют документированной причины'],
 ['ИТОГ','Банковских пакетов без подтверждения',pack.bank.totals.pending,'Нет строки — не доказана недостача'],
 ['ОГРАНИЧЕНИЕ','Источники загружены пользователем','Не аудит','Никаких автоматических банковских запросов']]);}
export function r9CasesCsv(cases){return r8Csv([['Хеш кейса','Филиал','Вид','План','Факт','Разница','Статус','Причина'],...cases.items.map(x=>[x.key,x.storeId,x.kind,x.expected,x.observed,x.difference,x.status,x.reason||''])]);}
export function r9DayCsv(day){return r8Csv([['Филиал','Дата','Документы, ₽','Операции, ₽','Комиссия, ₽','Операции за вычетом комиссии','Сдвиг дат, ₽'],...day.days.map(x=>[x.storeId,x.date,x.documents,x.events,x.fees,x.netAfterFees,x.timingDifference])]);}
export function r9BankCsv(bank){return r8Csv([['Филиал','Хеш пакета','Расчёт, ₽','Выписка, ₽','Разница, ₽','Срок дней','Статус'],...bank.batches.map(x=>[x.storeId,r9Digest(x.batchId),x.expected,x.received==null?'Нет подтверждения':x.received,x.difference??'',x.lagDays??'',x.status])]);}
export function r9AggregateSignoff(existing,pack,{status='reviewed'}={}){
 if(!pack?.valid)throw Error('Нет подтверждённых исходных данных');
 if(!['reviewed','requires-check','rejected'].includes(status))throw Error('Недопустимый статус решения');
 if(!Array.isArray(existing)||existing.length>=40)throw Error('Предел локального журнала — 40 решений');
 const item={seq:existing.length+1,date:AS_OF,status,docs:pack.audit.summary.documents,issues:pack.cases.total,closed:pack.cases.closed,fees:pack.audit.summary.fees,matchedBatches:pack.bank.totals.matched,previous:existing.at(-1)?.fingerprint||'00000000'};
 item.fingerprint=r9Digest(JSON.stringify(item));return [...existing,item];
}
export function r9RestoreSignoffs(raw){
 if(raw?.version!==1||!Array.isArray(raw.items)||raw.items.length>40)return [];
 const accepted=[];for(const r of raw.items){
  if(Object.keys(r).sort().join()!==['seq','date','status','docs','issues','closed','fees','matchedBatches','previous','fingerprint'].sort().join())return [];
  const x={...r};delete x.fingerprint;
  if(x.seq!==accepted.length+1||x.previous!==(accepted.at(-1)?.fingerprint||'00000000')||!['reviewed','requires-check','rejected'].includes(x.status)||x.fingerprint!==undefined||r.fingerprint!==r9Digest(JSON.stringify(x)))return [];
  if([x.docs,x.issues,x.closed,x.fees,x.matchedBatches].some(v=>typeof v!=='number'||!Number.isFinite(v)||v<0))return [];
  accepted.push(r);
 }return accepted;
}
export function r9SignoffCsv(items){return r8Csv([['№','Дата','Статус','Документы','Расхождения','Закрыто','Комиссии','Пакеты','Хеш записи'],...items.map(x=>[x.seq,x.date,x.status,x.docs,x.issues,x.closed,x.fees,x.matchedBatches,x.fingerprint])]);}
