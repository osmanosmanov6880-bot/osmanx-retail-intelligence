import test from 'node:test';
import assert from 'node:assert/strict';
import {AS_OF,buildDataset,scopeData} from '../src/model.mjs';
import {decisionEvidenceGate,gateCsv,networkRebalance,rebalanceCsv,capitalAllocation,capitalCsv,privacySimulation,anonymousPrivacyCsv,PRIVACY_LEDGER_VERSION,appendPrivacyAudit,restorePrivacyAudit,executiveBrief,briefCsv} from '../src/r7_core.mjs';
const data=buildDataset('balanced');
const scope=scopeData(data,{period:'14'});
const near=(a,b,delta=.00001)=>assert.ok(Math.abs(a-b)<delta,`${a} ≠ ${b}`);

test('evidence quality: baseline is ready with traceable events',()=>{
 const g=decisionEvidenceGate(data,scope);
 assert.equal(g.valid,true);assert.equal(g.ready,true);assert.equal(g.score,100);assert.equal(g.brokenReturns,0);assert.equal(g.brokenLinks,0);
 assert.equal(g.linkedCount,7);assert.equal(g.linkedGross,28000);assert.ok(g.requestCount>=60);assert.ok(g.checks.length>=5);
});
test('evidence gate: invalid assumptions are rejected',()=>{
 for(const options of [{minimumRequests:-1},{minimumLinked:1.5},{maxStockAgeDays:NaN},{maxStockAgeDays:366}])assert.equal(decisionEvidenceGate(data,scope,options).valid,false);
});
test('evidence gate: corrupted request sale reference blocks conclusions',()=>{
 const d=structuredClone(data),x=d.requests.find(r=>r.purchased);x.saleId='non-existent';
 const g=decisionEvidenceGate(d,scopeData(d,{period:'14'}));assert.equal(g.ready,false);assert.equal(g.brokenLinks,1);assert.ok(g.blockers.length);
});
test('evidence gate: duplicate sale ID blocks conclusions',()=>{
 const d=structuredClone(data);d.sales.push({...d.sales[0]});const g=decisionEvidenceGate(d,scopeData(d,{period:'14'}));assert.equal(g.ready,false);assert.ok(g.duplicateCount>0);
});
test('evidence gate: return refund larger than actual sale is rejected',()=>{
 const d=structuredClone(data);const r=d.returns.find(x=>x.date>=scope.from);assert.ok(r);
 const sale=d.sales.find(x=>x.id===r.saleId);r.refundedPrice=sale.paidPrice+1;
 const g=decisionEvidenceGate(d,scopeData(d,{period:'14'}));assert.equal(g.ready,false);assert.ok(g.brokenReturns>0);
});
test('evidence gate: stale physical-snapshot risk blocks readiness',()=>{
 const d=structuredClone(data);d.stock[0].asOf='2026-10-01';
 const g=decisionEvidenceGate(d,scopeData(d,{period:'14'}));assert.equal(g.ready,false);assert.equal(g.staleStock,1);
});
test('evidence gate: low event volume cannot be silently interpreted as evidence',()=>{
 const g=decisionEvidenceGate(data,scope,{minimumRequests:1000});assert.equal(g.ready,false);assert.match(g.blockers.join(' '),/обращений/);
});
test('evidence quality CSV is escaped and contains no machine formulas',()=>{
 const csv=gateCsv(decisionEvidenceGate(data,scope));assert.match(csv,/Уникальность/);assert.ok(csv.startsWith('\ufeff'));
});

test('rebalance: real in-memory stock, no oversell, no double-allocated request',()=>{
 const r=networkRebalance(data,scope);
 assert.equal(r.valid,true);assert.ok(r.routes.length>0);assert.ok(r.net>0);
 assert.equal(r.usedRequests.length,new Set(r.usedRequests).size);
 const sourceStock=new Map(data.stock.map(x=>[x.id,x]));
 for(const [id,moved] of Object.entries(r.movedByStock))assert.ok(moved<=sourceStock.get(id).quantity,`${id}: ${moved}`);
 for(const x of r.routes){assert.notEqual(x.sourceStore,x.destinationStore);assert.ok(x.net>0);assert.equal(x.asOf,AS_OF);assert.equal(x.evidenceIds.filter(e=>e.startsWith('req-')).length,x.units);near(x.net,x.scenarioGross-x.cost);}
 assert.equal(r.reservedUnits,r.routes.reduce((sum,row)=>sum+row.units,0));
});
test('rebalance: source reserve enforced even with multiple destinations',()=>{
 const r=networkRebalance(data,scope,{reserve:2,probability:80,fixedCost:0,unitCost:0,maxUnits:10});
 for(const [id,units] of Object.entries(r.movedByStock)){const stock=data.stock.find(x=>x.id===id);assert.ok(units<=Math.max(0,stock.quantity-2));}
});
test('rebalance: high shipping cost removes all routes rather than fake profits',()=>{
 const r=networkRebalance(data,scope,{fixedCost:10000000,unitCost:1000000});assert.equal(r.routes.length,0);assert.equal(r.net,0);
});
test('rebalance: current stock at destination must not be sold as a loss from history',()=>{
 const r=networkRebalance(data,scope);
 for(const route of r.routes){const current=data.stock.find(x=>x.storeId===route.destinationStore&&x.modelId===route.modelId&&x.size===route.size&&x.color===route.color);assert.ok(!current||current.quantity===0);}
 assert.match(r.disclaimer,/текущего|сегодняшнего/);
});
test('rebalance: zero probability produces no financially justified routes',()=>{
 const r=networkRebalance(data,scope,{probability:0});assert.equal(r.routes.length,0);
});
test('rebalance: invalid numeric input is rejected',()=>{
 for(const opt of [{reserve:-2},{maxUnits:0},{minDemand:0},{probability:101},{fixedCost:-5},{unitCost:Infinity}])assert.equal(networkRebalance(data,scope,opt).valid,false);
});
test('rebalance: current scenario changes with probability and cost',()=>{
 const lo=networkRebalance(data,scope,{probability:10}),hi=networkRebalance(data,scope,{probability:90});assert.ok(hi.net>lo.net);
 const expensive=networkRebalance(data,scope,{probability:90,unitCost:900});assert.ok(expensive.net<hi.net);
});
test('rebalance CSV contains source SKU, destination, cost, and evidence',()=>{
 const csv=rebalanceCsv(networkRebalance(data,scope));assert.ok(csv.startsWith('\ufeff'));assert.match(csv,/JKT-AURA|SKU-/);assert.match(csv,/Затраты/);
});

test('capital: 0/1 optimizer stays within all budget and capacity limits',()=>{
 const p=capitalAllocation(data,scope);
 assert.equal(p.valid,true);assert.ok(p.candidates.length>0);
 assert.ok(p.totalSpend<=p.budget);assert.ok(p.actionCount<=3);assert.ok(p.remaining>=0);
 assert.equal(p.actionCount,p.selected.length);near(p.totalSpend,p.selected.reduce((sum,x)=>sum+x.cost,0));
});
test('capital: zero budget/capacity selects nothing',()=>{
 for(const params of [{budget:0},{capacity:0},{confidence:0}]){const p=capitalAllocation(data,scope,params);assert.equal(p.selected.length,0);assert.equal(p.totalSpend,0);}
});
test('capital: impossible verification cost declines every route',()=>{
 const p=capitalAllocation(data,scope,{verificationCost:1000000,budget:4000});assert.equal(p.selected.length,0);
});
test('capital: budget relaxation cannot reduce maximum risk-adjusted score',()=>{
 const a=capitalAllocation(data,scope,{budget:3000}),b=capitalAllocation(data,scope,{budget:20000});assert.ok(b.adjustedNet>=a.adjustedNet);
});
test('capital: one request cannot be used to justify two independent selected routes',()=>{
 const p=capitalAllocation(data,scope,{budget:100000,capacity:10,confidence:100});
 const ids=p.selected.flatMap(x=>x.evidenceIds.filter(id=>id.startsWith('req-')));assert.equal(ids.length,new Set(ids).size);
});
test('capital: corrupt parameters do not create an apparently feasible plan',()=>{
 for(const options of [{budget:-1},{capacity:11},{verificationCost:-1},{confidence:101},{confidence:NaN}])assert.equal(capitalAllocation(data,scope,options).valid,false);
});
test('capital: exported rows label forecast and selection, never proven profit',()=>{
 const csv=capitalCsv(capitalAllocation(data,scope));assert.match(csv,/Консервативный эффект/);assert.match(csv,/В бюджетном сценарии/);
});

test('privacy: counts reconcile, no IDs in aggregate CSV',()=>{
 const p=privacySimulation(data,scope);assert.equal(p.valid,true);assert.equal(p.retained+p.discarded,p.total);assert.equal(p.aggregates.reduce((sum,x)=>sum+x.events,0),p.total);
 const csv=anonymousPrivacyCsv(p);assert.ok(csv.startsWith('\ufeff'));assert.doesNotMatch(csv,/req-14-|pre-\d|sale-\d|member-\d|@gmail/);
});
test('privacy: shorter retention cannot increase retained events',()=>{
 const a=privacySimulation(data,scope,{retentionDays:1}),b=privacySimulation(data,scope,{retentionDays:90});assert.ok(a.retained<=b.retained);
});
test('privacy: requiring consent never increases eligible records',()=>{
 const a=privacySimulation(data,scope,{retentionDays:90,requireConsent:true}),b=privacySimulation(data,scope,{retentionDays:90,requireConsent:false});assert.ok(a.retained<=b.retained);
});
test('privacy: invalid settings rejected',()=>{
 for(const options of [{retentionDays:0},{retentionDays:1000},{retentionDays:1.5},{requireConsent:'yes'}])assert.equal(privacySimulation(data,scope,options).valid,false);
});
test('privacy: no mutation of underlying dataset even after preview',()=>{
 const original=JSON.stringify(data.requests.slice(0,5));privacySimulation(data,scope,{retentionDays:1});assert.equal(JSON.stringify(data.requests.slice(0,5)),original);
});
test('privacy: audit ledger only stores counts and restores',()=>{
 const p=privacySimulation(data,scope),one=appendPrivacyAudit([],p),two=appendPrivacyAudit(one,p);
 assert.equal(two.length,2);assert.deepEqual(restorePrivacyAudit({version:PRIVACY_LEDGER_VERSION,entries:two}),two);
 const txt=JSON.stringify(two);assert.doesNotMatch(txt,/req-|pre-|memberId|saleId/);
});
test('privacy: tampered ledger must not be accepted as legitimate',()=>{
 const x=appendPrivacyAudit([],privacySimulation(data,scope));x[0].retained=999;
 assert.deepEqual(restorePrivacyAudit({version:PRIVACY_LEDGER_VERSION,entries:x}),[]);
});
test('privacy: provenance and no-real-deletion warning are mandatory',()=>{
 const v=privacySimulation(data,scope);assert.match(v.disclaimer,/синтетическ|песочниц/);assert.equal(v.demoOnly,true);
});

test('brief: five statements with clear evidence status and method',()=>{
 const b=executiveBrief(data,scope);assert.equal(b.valid,true);assert.equal(b.statements.length,5);
 assert.ok(b.statements.every(x=>x.epistemic&&x.method&&x.evidenceIds));assert.ok(b.nextActions.length===3);
 assert.match(b.disclaimer,/Демонстрационные/);assert.equal(b.statements.find(x=>x.id==='gross').value,scope.totals.grossProfit);
});
test('brief: observed and forecast values never share fact status',()=>{
 const b=executiveBrief(data,scope);
 assert.equal(b.statements.find(x=>x.id==='network').epistemic,'ПРОГНОЗ');assert.equal(b.statements.find(x=>x.id==='budget').epistemic,'ГИПОТЕЗА');
});
test('brief: exact scope follows period and store filters',()=>{
 const b=executiveBrief(data,scope),smaller=scopeData(data,{period:'7',store:'s1'}),b2=executiveBrief(data,smaller);
 assert.equal(b2.period.from,smaller.from);assert.equal(b2.statements.find(x=>x.id==='revenue').value,smaller.totals.revenue);
 assert.notEqual(b.statements.find(x=>x.id==='revenue').value,b2.statements.find(x=>x.id==='revenue').value);
});
test('brief: corrupted referential evidence is labeled not verified',()=>{
 const d=structuredClone(data);d.requests.find(x=>x.purchased).saleId='missing';const b=executiveBrief(d,scopeData(d,{period:'14'}));
 assert.equal(b.gate.ready,false);assert.equal(b.statements.find(x=>x.id==='linked').epistemic,'ТРЕБУЕТ ПРОВЕРКИ');
});
test('brief: CSV is A4-report source snapshot with key evidence',()=>{
 const csv=briefCsv(executiveBrief(data,scope));assert.match(csv,/ФАКТ ДЕМО/);assert.match(csv,/ГИПОТЕЗА/);assert.match(csv,/ID оснований/);
});
