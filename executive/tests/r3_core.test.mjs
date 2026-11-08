import test from 'node:test';
import assert from 'node:assert/strict';
import {buildDataset,scopeData,AURA,STORES} from '../src/model.mjs';
import {reconcileEvidence,planTransfer,wilson,evaluatePilot,restoreJournal,newJournalEntry,transitionJournal,journalStats,JOURNAL_VERSION} from '../src/r3_core.mjs';
const data=buildDataset('balanced');
const fourteen=scopeData(data,{period:14});

test('ATELIER R3 / synthetic ledger reconciliation derives exact net financial totals',()=>{
 const r=reconcileEvidence(data,fourteen);
 assert.deepEqual(r.issues,[]);assert.equal(r.revenue,fourteen.totals.revenue);
 assert.equal(r.cogs,fourteen.totals.costOfGoods);assert.equal(r.gross,fourteen.totals.grossProfit);
 assert.equal(r.gross,r.revenue-r.cogs);assert.equal(r.incrementalProfit,null);
});
test('ATELIER R3 / linked demand evidence resolves exact 7 SKU/store/size receipt pairs and 28,000 gross',()=>{
 const r=reconcileEvidence(data,fourteen);
 assert.equal(r.linkedCount,7);assert.equal(r.linkedGross,28000);
 assert.equal(new Set(r.linked.map(x=>x.saleId)).size,7);
 assert.ok(r.linked.every(x=>x.revenue===8900&&x.cost===4900&&x.gross===4000));
});
test('ATELIER R3 / refund dated outside sale period is still reconciled by original receipt ID',()=>{
 const r=reconcileEvidence(data,scopeData(data,{period:7}));
 assert.deepEqual(r.issues,[]);
 assert.equal(r.revenue,scopeData(data,{period:7}).totals.revenue);
});
test('ATELIER R3 / mismatch, missing sale references and stale evidence are exposed rather than silently accepted',()=>{
 const contaminated=structuredClone(data);
 const ret=contaminated.returns.find(x=>x.date>='2026-10-26');
 assert.ok(ret);ret.saleId='missing';
 const wrong=contaminated.requests[0];wrong.saleId='missing';
 const s=scopeData(contaminated,{period:14});
 const r=reconcileEvidence(contaminated,s);
 assert.ok(r.issues.some(x=>x.includes('отсутствует исходный чек')));
 assert.ok(r.issues.some(x=>x.includes('нет согласованного связанного чека')));
 assert.equal(r.checks.returnLinks,false);assert.equal(r.checks.requestLinks,false);
});
test('ATELIER R3 / stock constrained transfer is valid only with available inventory and observed demand',()=>{
 const r=planTransfer(data);
 assert.equal(r.valid,true);assert.equal(r.availableAtSource,3);
 assert.equal(r.availableAtDestination,0);assert.equal(r.demandCount,7);
 assert.equal(r.calc.net,5550);assert.equal(r.isActualTransfer,false);
 assert.ok(r.evidenceIds.every(id=>data.requests.some(e=>e.id===id)));
});
test('ATELIER R3 / transfer to same store and insufficient source stock are rejected',()=>{
 assert.ok(planTransfer(data,{sourceStore:'s1',destinationStore:'s1'}).problems.some(x=>x.includes('различаться')));
 const v=planTransfer(data,{units:4});assert.equal(v.valid,false);assert.equal(v.calc,null);
 assert.ok(v.problems.some(x=>x.includes('только 3')));
});
test('ATELIER R3 / unsupported source item, no registered demand or invalid input cannot yield money',()=>{
 for(const o of [{sourceStore:'s3',units:3},{size:'XS',color:'Песочный',units:1},{units:-1},{probability:130},{costPerUnit:-10},{modelId:'BAD-SKU'}]){
  const r=planTransfer(data,o);assert.equal(r.valid,false,JSON.stringify(o));assert.equal(r.calc,null,JSON.stringify(o));
 }
});
test('ATELIER R3 / transfer is sensitive to logistics and probability but never books a stock operation',()=>{
 const a=planTransfer(data),b=planTransfer(data,{probability:30,costPerUnit:500});
 assert.ok(b.calc.net<a.calc.net);assert.equal(a.snapshotDate,data.generatedAt);
 assert.equal(data.stock.find(x=>x.id===a.stockSourceId).quantity,3);
});
test('ATELIER R3 / Wilson confidence interval is bounded, and requires real observations',()=>{
 assert.equal(wilson(0,0),null);assert.equal(wilson(7,6),null);
 const [lower,upper]=wilson(7,60);assert.ok(lower>0&&upper<1&&lower<7/60&&upper>7/60);
});
test('ATELIER R3 / unmeasured control group never produces fictional incremental financial effect',()=>{
 const v=evaluatePilot({testRequests:60,testPurchases:7,controlRequests:null,controlPurchases:null,unitGross:4000,pilotCost:1800});
 assert.equal(v.valid,true);assert.equal(v.observedGross,28000);
 assert.equal(v.descriptiveDifference,null);assert.equal(v.incrementalProven,false);
 assert.match(v.conclusion,/Недостаточно данных/);
});
test('ATELIER R3 / descriptive control calculation shows uncertainty and never claims causal lift',()=>{
 const v=evaluatePilot({testRequests:60,testPurchases:7,controlRequests:60,controlPurchases:4,unitGross:4000,pilotCost:1800});
 assert.equal(v.delta,.05);assert.equal(v.descriptiveDifference,12000);
 assert.equal(v.descriptiveNet,10200);assert.ok(v.interval[0]<0&&v.interval[1]>0);
 assert.equal(v.incrementalProven,false);
});
test('ATELIER R3 / impossible control samples and negative assumptions are rejected',()=>{
 for(const v of [{testRequests:5,testPurchases:6},{controlRequests:4,controlPurchases:8},{pilotCost:-1},{unitGross:-500}]){
  const r=evaluatePilot({...{testRequests:60,testPurchases:7,controlRequests:60,controlPurchases:3},...v});assert.equal(r.valid,false);
 }
});
test('ATELIER R3 / journal create -> run -> measure -> close uses immutable transitions',()=>{
 const a=newJournalEntry([],{title:'Проверить размер L',evidenceIds:['req-14-010','req-14-010']});
 assert.equal(a.created.id,'PILOT-001');assert.deepEqual(a.created.evidenceIds,['req-14-010']);
 assert.equal(a.entries[0].status,'draft');
 const running=transitionJournal(a.entries,a.created.id,'running');
 assert.equal(a.entries[0].status,'draft');
 const measured=transitionJournal(running,a.created.id,'measured',{before:5,after:7,sample:60,expenses:1800});
 assert.equal(measured[0].result.delta,2);
 assert.equal(measured[0].result.incrementalityProven,false);
 assert.equal(transitionJournal(measured,a.created.id,'closed')[0].status,'closed');
 assert.deepEqual(journalStats(measured),{all:1,draft:0,running:0,measured:1,proven:0});
});
test('ATELIER R3 / journal rejects jumps, missing metrics and negative expenses',()=>{
 const a=newJournalEntry([],{title:'Проверка'});
 assert.throws(()=>transitionJournal(a.entries,a.created.id,'measured',{}),/Недопустимый/);
 const r=transitionJournal(a.entries,a.created.id,'running');
 assert.throws(()=>transitionJournal(r,a.created.id,'measured',{before:5,after:7,sample:4,expenses:100}),/корректные/);
 assert.throws(()=>transitionJournal(r,a.created.id,'measured',{before:2,after:3,sample:10,expenses:-10}),/корректные/);
});
test('ATELIER R3 / local persistence accepts only versioned, valid entries',()=>{
 const created=newJournalEntry([],{title:'Контрольный пилот'}).entries;
 assert.deepEqual(restoreJournal({version:JOURNAL_VERSION,entries:created}),created);
 assert.deepEqual(restoreJournal({version:999,entries:created}),[]);
 assert.deepEqual(restoreJournal({version:JOURNAL_VERSION,entries:[{id:'x',status:'draft',title:'bad',events:[]}]}),[]);
});
test('ATELIER R3 / three scenarios have independent source observations without cross-tenant leakage',()=>{
 const other=buildDataset('shortages');
 assert.equal(planTransfer(data).valid,true);
 assert.ok(reconcileEvidence(other,scopeData(other,{period:14})).checks.totals);
 assert.ok(scopeData(other,{period:14}).requests.length>fourteen.requests.length);
 assert.equal(STORES.length,3);assert.equal(AURA.price,8900);
});

test('ATELIER R3 / each opportunity carries event IDs only from its own source stream',async()=>{
 const {evidenceForOpportunity}=await import('../src/r3_core.mjs');
 for(const [id,source] of [['demand','req-'],['rescue','req-'],['fitting','fit-'],['stock','audit-'],['service','help-'],['returns','return-']]){
  const ids=evidenceForOpportunity(fourteen,id);assert.ok(ids.every(x=>x.startsWith(source)),[id,ids]);
  assert.ok(ids.length<=35);
 }
});
test('ATELIER R3 / CSV encodes quotes, newlines, and Excel formula payloads as inert text',async()=>{
 const {journalCsv}=await import('../src/r3_core.mjs');
 const record=newJournalEntry([],{title:'=HYPERLINK("evil","x")'}).entries;
 const csv=journalCsv(record);
 assert.ok(csv.startsWith('\ufeff'));
 assert.match(csv,/"'=HYPERLINK\(""evil"",""x""\)"/);
 assert.ok(csv.includes('PILOT-001'));
});
test('ATELIER R3 / missing measurement is rejected even if blank strings cast to zero',()=>{
 const a=newJournalEntry([],{title:'Проверка'});
 const r=transitionJournal(a.entries,a.created.id,'running');
 assert.throws(()=>transitionJournal(r,a.created.id,'measured',{before:'',after:'0',sample:'10',expenses:''}),/корректные/);
});
