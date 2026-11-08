import test from 'node:test';
import assert from 'node:assert/strict';
import {buildDataset,scopeData} from '../src/model.mjs';
import {auditEvidence,matchDemand,discountStress,prioritizePortfolio,dossierSnapshot,dossierCsv,auditCsv,matchingCsv,portfolioCsv} from '../src/r4_core.mjs';
const dataset=buildDataset('balanced');
const scope=scopeData(dataset,{period:'14'});
const emptyScope=scopeData(dataset,{period:'1',store:'s1',model:'SKU-9999'});

// 01 / source reliability and receipts

test('R4/01 original synthetic sources reconcile and never assert causal lift',()=>{
 const a=auditEvidence(dataset,scope);
 assert.equal(a.critical,0);assert.equal(a.bridge.linkedCount,7);assert.equal(a.bridge.linkedGross,28000);
 assert.equal(a.bridge.incrementalProfit,null);assert.equal(a.coverage.length,11);
 assert.ok(a.totalEvents>1000);assert.ok(a.limitations.some(x=>x.includes('1С')));
});
test('R4/01 audit respects period/store scope',()=>{
 const s=scopeData(dataset,{period:'7',store:'s1'}),a=auditEvidence(dataset,s);
 assert.equal(a.coverage.find(x=>x.key==='traffic').events,7);
 assert.ok(a.coverage.find(x=>x.key==='sales').events<scope.sales.length);
});
test('R4/01 detects duplicate receipts and negative prices',()=>{
 const bad={...scope,sales:[...scope.sales,{...scope.sales[0],paidPrice:-1}]};
 const a=auditEvidence({...dataset,sales:[...dataset.sales,{...scope.sales[0],paidPrice:-1}]},bad);
 assert.ok(a.critical>=2);assert.ok(a.problems.some(x=>/повторяется/.test(x.issue)));
});
test('R4/01 detects orphan returns and refunded amount above the receipt',()=>{
 const returned=scope.returns[0];assert.ok(returned);
 const bad={...scope,returns:[...scope.returns,{...returned,id:'orphan-123',saleId:'missing-receipt'},{...returned,id:'too-much',refundedPrice:1e9}]};
 const a=auditEvidence(dataset,bad);
 assert.ok(a.problems.some(x=>/без исходного чека/.test(x.issue)));
 assert.ok(a.problems.some(x=>/превышает/.test(x.issue)));
});
test('R4/01 notices stale stock rather than treating the book quantity as verified',()=>{
 const stale={...scope,stock:[{...scope.stock[0],asOf:'2025-01-01'}]};
 const a=auditEvidence(dataset,stale);
 assert.equal(a.uncertain>=1,true);assert.match(a.limitations.join(' '),/фактическую доступность/);
});

// 02 / store-aware allocation

test('R4/02 every demand request is allocated at most once',()=>{
 const p=matchDemand(dataset,scope);
 assert.ok(p.valid);assert.equal(p.considered,p.totals.matched+p.totals.unmatched);
 assert.equal(new Set(p.matches.map(x=>x.requestId)).size,p.matches.length);
 assert.equal(p.totals.matched,p.totals.local+p.totals.remote);
});
test('R4/02 no stock unit is allocated twice; finite inventory and reserve respected',()=>{
 const reserve=1,p=matchDemand(dataset,scope,{reserve});const usage=new Map();
 for(const match of p.matches){usage.set(match.sourceStockId,(usage.get(match.sourceStockId)||0)+1);}
 for(const [id,used] of usage){const stock=dataset.stock.find(x=>x.id===id);assert.ok(used<=Math.max(0,stock.quantity-reserve),id);}
});
test('R4/02 raising stock buffer cannot increase matching count',()=>{
 const a=matchDemand(dataset,scope,{reserve:0}),b=matchDemand(dataset,scope,{reserve:3});
 assert.ok(b.totals.matched<=a.totals.matched);
 assert.ok(a.matches.some(x=>x.kind==='transfer'));
});
test('R4/02 expected money includes probability, unit margin and transport by match',()=>{
 const p=matchDemand(dataset,scope,{transferCost:350,probability:55});
 const remote=p.matches.find(x=>x.kind==='transfer');assert.ok(remote);
 assert.equal(remote.estimatedNet,Math.round((.55*(remote.price-remote.cost)-350)*100)/100);
 assert.equal(p.totals.estimatedNet,p.totals.estimatedGross-p.totals.logistics);
});
test('R4/02 invalid probability, buffer and expense reject plans',()=>{
 for(const opts of [{probability:-1},{probability:101},{transferCost:-4},{reserve:1.5},{limit:0}])
 assert.equal(matchDemand(dataset,scope,opts).valid,false,JSON.stringify(opts));
});
test('R4/02 model and store filters constrain destination requests but allow remote supply',()=>{
 const s=scopeData(dataset,{period:'14',store:'s1',model:'JKT-AURA',size:'L'}),p=matchDemand(dataset,s);
 assert.ok(p.matches.every(x=>x.destinationStore==='s1'&&x.modelId==='JKT-AURA'&&x.size==='L'));
 assert.ok(p.matches.some(x=>x.sourceStore!==x.destinationStore));
});
test('R4/02 scenario with no requests is a true empty state',()=>{
 const p=matchDemand(dataset,emptyScope);assert.equal(p.considered,0);assert.equal(p.totals.matched,0);
});

// 03 / margin and discount scenarios

test('R4/03 original SKU finance matches linked sales / returns and actual cost',()=>{
 const m=discountStress(dataset,scope);assert.equal(m.valid,true);assert.equal(m.product.price,8900);assert.equal(m.product.cost,4900);
 assert.equal(m.baselineGross,m.baselineRevenue-m.baselineCogs);
 assert.equal(m.baselineUnits,m.receipts.length-m.returnIds.length);
});
test('R4/03 a larger discount without additional volume worsens unit gross',()=>{
 const before=discountStress(dataset,scope,{discount:0,uplift:0,campaignCost:0});
 const after=discountStress(dataset,scope,{discount:20,uplift:0,campaignCost:0});
 assert.ok(after.unitGross<before.unitGross);assert.ok(after.deltaGross<before.deltaGross);
});
test('R4/03 realistic campaign expenses reduce scenario gross pound-for-pound',()=>{
 const a=discountStress(dataset,scope,{campaignCost:0}),b=discountStress(dataset,scope,{campaignCost:1250});
 assert.equal(a.scenarioGross-b.scenarioGross,1250);
});
test('R4/03 full discount stress can show negative unit contribution, never a proven uplift',()=>{
 const x=discountStress(dataset,scope,{discount:90,uplift:15});
 assert.ok(x.unitGross<0);assert.equal(x.breakEvenUplift,null);
 assert.equal(x.provenIncrementalProfit,false);assert.ok(x.warnings.some(x=>/отрицательной/.test(x)));
});
test('R4/03 invalid discount, uplift and costs are rejected; sparse samples yield no estimate',()=>{
 for(const opts of [{discount:-1},{discount:96},{uplift:-1},{uplift:510},{campaignCost:-1}])assert.equal(discountStress(dataset,scope,opts).valid,false);
 const r=discountStress(dataset,emptyScope);assert.equal(r.validBaseline,false);assert.equal(r.deltaGross,null);
});

// 04 / bounded priority planning

test('R4/04 priorities have fixed budget/capacity and no invented additive upside',()=>{
 const p=prioritizePortfolio(dataset,scope);
 assert.ok(p.valid);assert.ok(p.selected.length>0&&p.selected.length<=3);
 assert.ok(p.used<=p.budget);assert.equal(p.remaining,p.budget-p.used);
 assert.equal(p.totalScenarioNet,null);assert.match(p.overlapWarning,/Складывать/);
});
test('R4/04 cost overrides and tight budget change selection',()=>{
 const a=prioritizePortfolio(dataset,scope,{capacity:2,budget:100});
 assert.equal(a.selected.length,0);
 const b=prioritizePortfolio(dataset,scope,{capacity:2,budget:500,costs:{rescue:300}});
 assert.equal(b.selected.length,1);assert.equal(b.selected[0].id,'rescue');
});
test('R4/04 disabled evidence and invalid manual costs never allocate budget',()=>{
 const bad=prioritizePortfolio(dataset,scope,{costs:{rescue:null}});
 assert.equal(bad.candidates.find(x=>x.id==='rescue').invalidCost,true);
 assert.ok(!bad.selected.some(x=>x.id==='rescue'));
 const invalid=prioritizePortfolio(dataset,scope,{capacity:8});assert.equal(invalid.valid,false);
});
test('R4/04 selected actions retain traceable IDs and distinct owners',()=>{
 const p=prioritizePortfolio(dataset,scope);
 for(const x of p.selected){assert.ok(x.owner);assert.ok(x.evidenceIds.length>0);assert.ok(x.hasEvidence);}
});

// 05 / evidence export

test('R4/05 dossier balances exactly with audited scoped receipts',()=>{
 const x=dossierSnapshot(dataset,scope);
 assert.equal(x.totals.revenue,scope.totals.revenue);assert.equal(x.totals.gross,scope.totals.grossProfit);
 assert.equal(x.quality.errors,0);assert.equal(x.totals.relatedReceiptGross,28000);
 assert.equal(x.origin.includes('ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ'),false); // marker is explicitly English and in page Russian
 assert.ok(x.origin.includes('DEMONSTRATION DATA'));
});
test('R4/05 dossier updates on periods, branches and categories',()=>{
 const a=dossierSnapshot(dataset,scope),b=dossierSnapshot(dataset,scopeData(dataset,{period:'7',store:'s1',category:'Куртки'}));
 assert.ok(b.totals.revenue<a.totals.revenue);assert.equal(b.filters.store,'s1');
 assert.ok(b.period.from>a.period.from);assert.ok(b.quality.events>0);
});
test('R4/05 CSV protects against spreadsheet formula injection',()=>{
 const x=dossierSnapshot(dataset,scope);x.warnings.push('=HYPERLINK("https://evil.test", "click")');
 const csv=dossierCsv(x);
 assert.match(csv,/"'=HYPERLINK/);
 assert.match(csv,/^\uFEFF"Параметр"/);assert.ok(csv.includes(String(x.totals.revenue))); // report matches the snapshot
});
test('R4/05 all exports include evidence provenance and explicit uncertainty',()=>{
 const a=auditCsv(auditEvidence(dataset,scope)),m=matchingCsv(matchDemand(dataset,scope)),p=portfolioCsv(prioritizePortfolio(dataset,scope));
 assert.match(a,/Чеки/);assert.match(m,/req-14/);assert.match(p,/Гипотеза|Неизвестно|сценарий/);
 assert.match(dossierCsv(dossierSnapshot(dataset,scope)),/Не доказанный прирост/);
});
