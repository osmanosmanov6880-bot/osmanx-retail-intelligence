import test from 'node:test';
import assert from 'node:assert/strict';
import {AS_OF,buildDataset,scopeData} from '../src/model.mjs';
import {emptyWorkingSet,acceptCsv,r8Example,r8Csv} from '../src/r8_core.mjs';
import {R9_SCHEMA,R9_MAX_ROWS,r9Empty,r9Example,r9InspectCsv,r9AcceptCsv,r9Reconcile,r9Settlements,r9Cases,r9Transition,r9DailyClose,r9Pack,r9ReportCsv,r9CasesCsv,r9DayCsv,r9BankCsv,r9AggregateSignoff,r9RestoreSignoffs,r9SignoffCsv} from '../src/r9_core.mjs';
function dataset(origin='example'){
 let ws=emptyWorkingSet();for(const kind of ['sales','returns','requests','stock']){
  const result=acceptCsv(ws,kind,r8Example()[kind],{origin});assert.equal(result.accepted,true);ws=result.workspace;
 }return ws;
}
function records(ws=dataset(),origin='example'){
 let f=r9Empty(ws.version);for(const kind of ['operations','settlements']){
  const r=r9AcceptCsv(ws,f,kind,r9Example()[kind],{origin});assert.equal(r.accepted,true,r.errors?.join(';'));f=r.workspace;
 }return f;
}
const good=dataset(),paid=records();
const build=(kind,rows)=>r8Csv([R9_SCHEMA[kind],...rows]);
const op=(id='op-A',amount=8900)=>[id,'2026-11-01','store-A','capture','s-101',amount,0,'cash',''];
const settled=(amount=8720)=>[['sett-01','2026-11-02','store-A','batch-A',amount]];
function bad(kind,text,pattern=/невер|некоррект|запрещён|нужен|строк|откл|CSV/i,ws=good,f=paid,origin='example'){
 const res=r9AcceptCsv(ws,f,kind,text,{origin});assert.equal(res.accepted,false);assert.match(res.errors.join(' / '),pattern);assert.equal(res.workspace,f);
}

// 1. Atomic local importing
 test('R9 sample operations are valid and links are not duplicated',()=>{assert.equal(r9InspectCsv('operations',r9Example().operations).valid,true);assert.equal(paid.operations.length,5);});
test('R9 sample bank lines are valid incl negative refund batches',()=>{assert.equal(r9InspectCsv('settlements',r9Example().settlements).valid,true);assert.equal(paid.settlements.length,4);});
test('each imported kind increments local version atomically',()=>{assert.equal(paid.revision,2);assert.equal(paid.sourceVersion,good.version);});
test('R9 files never become part of the R8 workspace',()=>{assert.deepEqual(Object.keys(good).sort(),['sales','returns','requests','stock','origin','version'].sort());});
test('reject unknown schema kind',()=>{assert.equal(r9InspectCsv('messages','id;xx\nxx;yy').valid,false);});
test('reject wrong header order',()=>{bad('operations',r8Csv([R9_SCHEMA.operations.slice().reverse(),op()]),/Заголовок/);});
test('reject empty, huge, malformed CSV without mutating accepted data',()=>{bad('operations','',/Пустой/);bad('operations','x'.repeat(1200001),/Пустой/);bad('operations','id;date\nhi;xx',/Заголовок/);});
test('reject duplicate operation ID',()=>{bad('operations',build('operations',[op('dup-1'),op('dup-1')]),/повторный/);});
test('reject duplicate settlement ID',()=>{bad('settlements',build('settlements',[settled()[0],settled()[0]]),/повторный/);});
test('reject malformed date and impossible date',()=>{for(const date of ['2026-02-30','2026-13-01','2027-01-01','1/2/2026']){const line=op();line[1]=date;bad('operations',build('operations',[line]),/дат/);}});
test('reject CSV formula injection through ID, store or batch',()=>{for(const [idx,val] of [[0,'=1+2'],[2,'+CMD'],[8,'@HYPERLINK']]){const line=['a','2026-11-01','store-A','capture','s-101',100,1,'card','batch-A'];line[idx]=val;bad('operations',build('operations',[line]),/ID|символ|batch/);}});
test('reject illegal payment kind',()=>{const line=op();line[3]='capture-and-refund';bad('operations',build('operations',[line]),/kind/);});
test('reject missing receipt reference',()=>{const line=op();line[4]='';bad('operations',build('operations',[line]),/ссылка/);});
test('reject card without batch',()=>{const line=op();line[7]='card';bad('operations',build('operations',[line]),/batchId/);});
test('reject cash with batch',()=>{const line=op();line[8]='bank-1';bad('operations',build('operations',[line]),/cash/);});
test('reject cash fee',()=>{const line=op();line[6]=50;bad('operations',build('operations',[line]),/cash/);});
test('reject fee above payment',()=>{const line=op();line[7]='card';line[8]='b1';line[5]=100;line[6]=101;bad('operations',build('operations',[line]),/комиссия/);});
test('reject zero and negative payment',()=>{for(const sum of [0,-1]){const line=op();line[5]=sum;bad('operations',build('operations',[line]),/сумма/);}});
test('reject exponent, more than two decimals and nonnumeric amount',()=>{for(const x of ['1e4','3.14159','cat']){const line=op();line[5]=x;bad('operations',build('operations',[line]),/сумма/);}});
test('reject negative commission and fractional fee',()=>{for(const x of [-1,'0.001']){const line=op();line[6]=x;bad('operations',build('operations',[line]),/комиссия/);}});
test('reject missing settlement batch',()=>{const row=settled()[0].slice();row[3]='';bad('settlements',build('settlements',[row]),/batchId/);});
test('reject invalid settlement amount',()=>{for(const x of ['NaN','1e2','0.123']){const row=settled()[0].slice();row[4]=x;bad('settlements',build('settlements',[row]),/сумма/);}});
test('reject too many records',()=>{const many=Array.from({length:R9_MAX_ROWS+1},(_,i)=>op('id-'+i));bad('operations',build('operations',many),/1500/);});
test('reject mixture of example receipts and real operations',()=>{bad('operations',r9Example().operations,/Учебные/,good,r9Empty(good.version),'local');});
test('reject mixture of local receipts and example operations',()=>{const w=dataset('local');bad('operations',r9Example().operations,/Учебные/,w,r9Empty(w.version),'example');});
test('reject import when receipts are missing',()=>{bad('operations',r9Example().operations,/чек/i,emptyWorkingSet(),r9Empty(),'example');});
test('reject import if R8 changed and the old payment set exists',()=>{const w=structuredClone(good);w.version++;bad('operations',r9Example().operations,/изменён/,w,paid,'example');});
test('can replace accepted bank file but leave operations intact',()=>{const next=r9AcceptCsv(good,paid,'settlements',r9Example().settlements,{origin:'example'});assert.equal(next.accepted,true);assert.equal(next.workspace.operations.length,5);assert.equal(next.workspace.revision,3);});

// 2. Receipt to payment reconciliation
 test('split tenders, refunds and fees match original receipts',()=>{const a=r9Reconcile(good,paid);assert.equal(a.valid,true);assert.equal(a.issues.length,0);assert.equal(a.summary.documents,4);assert.equal(a.summary.matched,4);});
test('R9 is precise on money amounts and does not prove causality',()=>{const a=r9Reconcile(good,paid).summary;assert.deepEqual([a.expectedSales,a.expectedRefunds,a.expectedNet,a.observedCaptures,a.observedRefunds,a.fees,a.observedNet,a.observedAfterFees,a.difference],[33700,8900,24800,33700,8900,498,24800,11102,0]);assert.equal(a.incrementalProven,false);assert.equal(a.bankVerified,false);});
test('no operation file is not valid reconciliation',()=>{assert.equal(r9Reconcile(good,r9Empty(good.version)).valid,false);});
test('version mismatch fails closed on reconciliation',()=>{const f=structuredClone(paid);f.sourceVersion++;assert.equal(r9Reconcile(good,f).valid,false);});
test('a missing capture creates an underpayment, never a confirmed theft',()=>{const f=structuredClone(paid);f.operations=f.operations.filter(x=>x.id!=='op-01');const a=r9Reconcile(good,f);assert.equal(a.summary.difference,-8900);assert.ok(a.issues.some(x=>x.kind==='short-capture'&&x.description.includes('Расхождение')));});
test('a duplicate financial amount is detected as excess',()=>{const f=structuredClone(paid);f.operations.push({...f.operations[0],id:'op-01-b'});const a=r9Reconcile(good,f);assert.ok(a.issues.some(x=>x.kind==='excess-capture'));});
test('payment referencing nonexistent receipt is not silently counted as matched',()=>{const f=structuredClone(paid);f.operations[0].referenceId='non-existent';const a=r9Reconcile(good,f);assert.ok(a.issues.some(x=>x.kind==='orphan-capture'));assert.equal(a.summary.matched,3);});
test('wrong store on a capture flags separate issue',()=>{const f=structuredClone(paid);f.operations[0].storeId='store-C';assert.ok(r9Reconcile(good,f).issues.some(x=>x.kind==='wrong-store'));});
test('wrong store on a REFUND uses original sale store',()=>{const f=structuredClone(paid);f.operations[4].storeId='store-C';assert.ok(r9Reconcile(good,f).issues.some(x=>x.kind==='wrong-store'));});
test('a payment older than the receipt is flagged',()=>{const f=structuredClone(paid);f.operations[0].date='2026-10-28';assert.ok(r9Reconcile(good,f).issues.some(x=>x.kind==='before-document'));});
test('audit does not mutate imported ledger rows or synthetic demo scope',()=>{const before=JSON.stringify(paid),demo=buildDataset('balanced');const revenue=scopeData(demo,{period:'14'}).totals.revenue;r9Reconcile(good,paid);assert.equal(JSON.stringify(paid),before);assert.equal(scopeData(demo,{period:'14'}).totals.revenue,revenue);});

// 3. Bank batch settlement controls
 test('sample bank batches match exactly incl reversal',()=>{const b=r9Settlements(good,paid);assert.equal(b.valid,true);assert.equal(b.totals.batches,4);assert.equal(b.totals.matched,4);assert.equal(b.totals.verified,true);assert.equal(b.totals.expected,15402);assert.equal(b.totals.observed,15402);});
test('negative refund batch is legitimate when bank file explicitly confirms it',()=>{const b=r9Settlements(good,paid);assert.equal(b.batches.find(x=>x.batchId==='batch-B-ref').expected,-8900);});
test('missing bank settlement stays unverified, never counted as lost funds',()=>{const f=structuredClone(paid);f.settlements=f.settlements.filter(x=>x.batchId!=='batch-B');const b=r9Settlements(good,f);assert.equal(b.totals.pending,1);assert.equal(b.totals.verified,false);assert.ok(b.issues.some(x=>x.kind==='settlement-not-provided'&&x.description.includes('не доказана недостача')));});
test('underpaid bank settlement produces a source-labeled variance',()=>{const f=structuredClone(paid);f.settlements[0].netAmount=8600;const b=r9Settlements(good,f);assert.ok(b.issues.some(x=>x.kind==='settlement-short'));assert.equal(b.totals.verified,false);});
test('bank settlement without card batch is anomalous',()=>{const f=structuredClone(paid);f.settlements.push({id:'unmatched',date:AS_OF,storeId:'store-A',batchId:'unknown',netAmount:100});assert.ok(r9Settlements(good,f).issues.some(x=>x.kind==='unknown-batch'));});
test('delayed settlement flags contract-lag review',()=>{const f=structuredClone(paid);f.settlements[0].date='2026-11-08';assert.ok(r9Settlements(good,f,{maxLagDays:3}).issues.some(x=>x.kind==='settlement-delay'));});
test('pre-dated settlement is impossible chronology flag',()=>{const f=structuredClone(paid);f.settlements[0].date='2026-10-15';assert.ok(r9Settlements(good,f).issues.some(x=>x.kind==='settlement-before'));});
test('invalid maximum lag is rejected by bank report',()=>{for(const x of [-1,1.5,31,NaN,null])assert.equal(r9Settlements(good,paid,{maxLagDays:x}).valid,false);});
test('cash transactions never enter bank package',()=>{const b=r9Settlements(good,paid);assert.equal(b.totals.expected,15402);assert.notEqual(b.totals.expected,r9Reconcile(good,paid).summary.observedNet);});
test('daily close separates document date and transaction date',()=>{const result=r9DailyClose(good,paid,r9Reconcile(good,paid));assert.equal(result.valid,true);assert.ok(result.days.length>=4);assert.ok(result.days.some(x=>x.date==='2026-11-05'&&x.documents<0));assert.ok(result.disclaimer.includes('не доказывает потери'));});

// 4. Exception action workflow
 test('no financial inconsistencies produce no triage cases',()=>{const c=r9Cases(r9Reconcile(good,paid),r9Settlements(good,paid),{});assert.equal(c.valid,true);assert.equal(c.total,0);});
test('introduce anomaly produces hashed case key without contact fields',()=>{const f=structuredClone(paid);f.settlements.pop();const c=r9Cases(r9Reconcile(good,f),r9Settlements(good,f),{});assert.equal(c.total,1);assert.match(c.items[0].key,/^[0-9a-f]{8}$/);assert.ok(!JSON.stringify(c.items).includes('customerName'));});
test('new issue can advance to checking then resolved with document reference',()=>{const f=structuredClone(paid);f.settlements.pop();const c=r9Cases(r9Reconcile(good,f),r9Settlements(good,f));const id=c.items[0].key;const checking=r9Transition({},c,id,'checking');const done=r9Transition(checking,c,id,'resolved','statement-checked','ACT-2026-1');assert.equal(done[id].status,'resolved');assert.equal(r9Cases(r9Reconcile(good,f),r9Settlements(good,f),done).closed,1);});
test('cannot close case without classification and evidence document',()=>{const f=structuredClone(paid);f.settlements.pop();const c=r9Cases(r9Reconcile(good,f),r9Settlements(good,f));const id=c.items[0].key;const checking=r9Transition({},c,id,'checking');assert.throws(()=>r9Transition(checking,c,id,'resolved'),/причин/);assert.throws(()=>r9Transition(checking,c,id,'resolved','statement-checked',''),/документ/);assert.throws(()=>r9Transition(checking,c,id,'resolved','statement-checked','too@example.com'),/документ/);});
test('status machine rejects illegal transitions and unknown IDs',()=>{const f=structuredClone(paid);f.settlements.pop();const c=r9Cases(r9Reconcile(good,f),r9Settlements(good,f));const id=c.items[0].key;assert.throws(()=>r9Transition({},c,id,'resolved','statement-checked','ACT-2026-1'),/Нельзя/);assert.throws(()=>r9Transition({},c,'unknown','checking'),/Неизвестное/);assert.throws(()=>r9Transition({},c,id,'not-a-status'),/Недопустимый/);});
test('triage status does not alter payment amounts',()=>{const f=structuredClone(paid);f.settlements.pop();const before=JSON.stringify(f);const c=r9Cases(r9Reconcile(good,f),r9Settlements(good,f));r9Transition({},c,c.items[0].key,'checking');assert.equal(JSON.stringify(f),before);});

// 5. CFO one-page report and aggregate signoff
 test('CFO report contains six source-labeled claims and is local-only',()=>{const p=r9Pack(good,paid,{});assert.equal(p.valid,true);assert.equal(p.claims.length,6);assert.equal(p.closeReady,true);assert.ok(p.warnings.some(x=>x.includes('пользователем')));});
test('CFO report marks pending evidence and outstanding exceptions',()=>{const f=structuredClone(paid);f.settlements.pop();const p=r9Pack(good,f,{});assert.equal(p.closeReady,false);assert.equal(p.cases.total,1);});
test('empty files cannot generate CFO financial claims',()=>{const p=r9Pack(good,r9Empty(good.version),{});assert.equal(p.valid,false);assert.equal(p.claims.length,0);});
test('aggregated CFO CSV cannot leak receipt, payout or customer identifiers',()=>{const p=r9Pack(good,paid,{}),csv=r9ReportCsv(p);assert.ok(csv.includes('Валовая прибыль'));for(const id of ['s-101','r-101','op-01','batch-A','q-101'])assert.ok(!csv.includes(id));});
test('cash close CSV reflects real settlements dates',()=>{const p=r9Pack(good,paid,{});assert.ok(r9DayCsv(p.day).includes('2026-11-05'));assert.ok(r9BankCsv(p.bank).includes('batch')===false);});
test('case CSV strips raw receipt and refund IDs',()=>{const f=structuredClone(paid);f.operations[0].referenceId='missing-sale';const p=r9Pack(good,f,{});const csv=r9CasesCsv(p.cases);assert.ok(csv.includes('Хеш кейса'));assert.ok(!csv.includes('missing-sale'));});
test('CFO signoff records only bounded aggregate and a linked fingerprint',()=>{const p=r9Pack(good,paid,{});const a=r9AggregateSignoff([],p,{status:'requires-check'});const b=r9AggregateSignoff(a,p,{status:'reviewed'});assert.equal(b.length,2);assert.equal(r9RestoreSignoffs({version:1,items:b}).length,2);assert.equal(JSON.stringify(b).includes('s-101'),false);assert.equal(JSON.stringify(b).includes('batch-A'),false);assert.ok(r9SignoffCsv(b).includes('Комиссии'));});
test('signoff history rejects tampering, reversing, extra keys and wrong version',()=>{const p=r9Pack(good,paid,{}),a=r9AggregateSignoff([],p),b=r9AggregateSignoff(a,p);const altered=structuredClone(b);altered[0].fees+=1;assert.deepEqual(r9RestoreSignoffs({version:1,items:altered}),[]);assert.deepEqual(r9RestoreSignoffs({version:1,items:b.slice().reverse()}),[]);const extra=structuredClone(b);extra[0].customerPhone='123';assert.deepEqual(r9RestoreSignoffs({version:1,items:extra}),[]);assert.deepEqual(r9RestoreSignoffs({version:99,items:b}),[]);});
test('signoff enforces explicit status and maximum history',()=>{const p=r9Pack(good,paid,{});assert.throws(()=>r9AggregateSignoff([],p,{status:'approved-bank'}),/статус/);let history=[];for(let i=0;i<40;i++)history=r9AggregateSignoff(history,p);assert.throws(()=>r9AggregateSignoff(history,p),/40/);});
