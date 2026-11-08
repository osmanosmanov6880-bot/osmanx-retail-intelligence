import test from 'node:test';
import assert from 'node:assert/strict';
import {AS_OF,buildDataset,scopeData} from '../src/model.mjs';
import {R8_KINDS,emptyWorkingSet,r8Example,r8Csv,inspectWorkingSet,acceptCsv,salesLedger,availabilityPlan,recoveryPilot,r8OwnerBrief,ledgerCsv,availabilityCsv,recoveryCsv,r8BriefCsv,R8_AUDIT_VERSION,appendR8Audit,restoreR8Audit,r8AuditCsv} from '../src/r8_core.mjs';

const example=()=>{let w=emptyWorkingSet();for(const kind of ['sales','returns','requests','stock']){const result=acceptCsv(w,kind,r8Example()[kind],{origin:'example'});assert.equal(result.accepted,true,JSON.stringify(result.errors));w=result.workspace;}return w;};
const bad=(w,k,text,matcher)=>{const outcome=acceptCsv(w,k,text);assert.equal(outcome.accepted,false);assert.strictEqual(outcome.workspace,w);if(matcher)assert.match(outcome.errors.join(' '),matcher);};
const replace=(csv,oldValue,newValue)=>csv.replace(oldValue,newValue);
const good=example();

// 1: atomic intake with strict anonymized contract
for(const kind of Object.keys(R8_KINDS))test(`accept ${kind}: atomic, typed, versioned`,()=>{
 const x=acceptCsv(emptyWorkingSet(),kind,r8Example()[kind]);
 if(kind==='returns'||kind==='requests')assert.equal(x.accepted,false);
 else{assert.equal(x.accepted,true);assert.equal(x.workspace.version,1);assert.ok(x.workspace[kind].length>0);}
});
test('four examples are linked and marked explicitly as examples',()=>{const c=inspectWorkingSet(good);assert.equal(c.valid,true);assert.equal(c.example,true);assert.equal(c.version,4);assert.equal(c.counts.sales,3);assert.equal(c.counts.returns,1);assert.equal(c.counts.requests,5);assert.equal(c.counts.stock,3);});
test('empty local dataset reports no files, not invented observed sales',()=>{const w=emptyWorkingSet();assert.match(inspectWorkingSet(w).source,/НЕ ЗАГРУЖЕНЫ/);assert.equal(salesLedger(w).valid,false);assert.equal(r8OwnerBrief(w).valid,false);});
test('normal local import with arbitrary SKU (not demo catalog)',()=>{const c=r8Csv([R8_KINDS.sales,['sale_01','2026-11-01','butik-5','FASHION-XL-500','XXL',1,12750,6100]]);const result=acceptCsv(emptyWorkingSet(),'sales',c);assert.equal(result.accepted,true);assert.equal(salesLedger(result.workspace).gross,6650);assert.equal(inspectWorkingSet(result.workspace).example,false);});
test('reject additional PII columns: phone, email, customerName',()=>{for(const suffix of ['phone','email','customerName'])bad(emptyWorkingSet(),'sales',r8Example().sales.replace('\"id\";',`\"id\";\"${suffix}\";`),/Шапка/);});
test('unknown field order rejected (no semantic guessing)',()=>{bad(emptyWorkingSet(),'sales',r8Example().sales.replace('\"revenue\";\"cost\"','\"cost\";\"revenue\"'),/Шапка/);});
test('duplicate receipt ID blocks entire batch',()=>{const t=r8Csv([R8_KINDS.sales,['s1','2026-11-01','A','AA','L',1,400,200],['s1','2026-11-02','A','AA','L',1,500,250]]);bad(emptyWorkingSet(),'sales',t,/повторный ID/);});
test('future or impossible calendar date rejects file',()=>{for(const day of ['2026-12-03','2026-02-30'])bad(emptyWorkingSet(),'sales',replace(r8Example().sales,'2026-11-01',day),/дата/);});
test('reject malformed money, precision and quantity',()=>{for(const val of ['-1','x','Infinity','1e100','NaN'])bad(emptyWorkingSet(),'sales',replace(r8Example().sales,'17800',val),/число/);for(const val of ['0','-2','2.7'])bad(emptyWorkingSet(),'sales',replace(r8Example().sales,';2;17800',';'+val+';17800'),/число/);});
test('reject unsupported formulas in SKU and store IDs',()=>{bad(emptyWorkingSet(),'sales',replace(r8Example().sales,'JKT-01','=1+1'),/sku/);bad(emptyWorkingSet(),'sales',replace(r8Example().sales,'store-A','=HYPERLINK'),/storeId/);});
test('UTF-8 BOM and semicolon/CRLF supported',()=>{const c=r8Example().sales;assert.ok(c.startsWith('\uFEFF'));assert.ok(c.includes('\r\n'));assert.equal(acceptCsv(emptyWorkingSet(),'sales',c).accepted,true);});
test('quoted cells with commas/semicolons require strict schema',()=>{const t=r8Csv([R8_KINDS.sales,['x1','2026-11-01','store-A','JKT-01','L',1,8900,4900]]);assert.equal(acceptCsv(emptyWorkingSet(),'sales',t).accepted,true);bad(emptyWorkingSet(),'sales',r8Csv([R8_KINDS.sales,['x1','2026-11-01','ABC;BAD','JKT-01','L',1,8900,4900]]),/storeId/);});
test('malformed and empty CSV cannot discard accepted state',()=>{bad(good,'sales','',/CSV|пуст/);bad(good,'sales','bad;line\n1;2',/Шапка/);assert.equal(good.sales.length,3);});
test('learner and actual CSV must not merge without explicit clear',()=>{bad(good,'sales',r8Example().sales,/смешивать/);const a=acceptCsv(emptyWorkingSet(),'sales',r8Example().sales);assert.equal(a.accepted,true);const next=acceptCsv(a.workspace,'stock',r8Example().stock,{origin:'example'});assert.equal(next.accepted,false);});
test('no raw file contents stored in workspace metadata',()=>{assert.deepEqual(Object.keys(good).sort(),['sales','returns','requests','stock','origin','version'].sort());assert.equal(JSON.stringify(good).includes('customerName'),false);});

// 2: exact receipts and returns
 test('gross profit uses refunded revenue and restored cost',()=>{const a=salesLedger(good);assert.deepEqual([a.revenue,a.refund,a.cost,a.restoredCost,a.netRevenue,a.gross],[33700,8900,18100,4900,24800,11600]);assert.equal(a.returns,1);});
test('branch scope retains associated returns',()=>{assert.equal(salesLedger(good,{store:'store-B'}).gross,0);assert.equal(salesLedger(good,{store:'store-A'}).gross,8000);assert.equal(salesLedger(good,{store:'store-C'}).gross,3600);});
test('partial returns can coexist if aggregate limits respected',()=>{const t=r8Csv([R8_KINDS.returns,['r1','2026-11-05','s-101',1,8900,4900],['r2','2026-11-06','s-101',1,8900,4900]]);const source=acceptCsv(emptyWorkingSet(),'sales',r8Example().sales).workspace;const r=acceptCsv(source,'returns',t);assert.equal(r.accepted,true);assert.equal(salesLedger(r.workspace).gross,7600);});
test('aggregate over-return of quantities, money and cost is blocked',()=>{const source=acceptCsv(emptyWorkingSet(),'sales',r8Example().sales).workspace;for(const t of [
 r8Csv([R8_KINDS.returns,['r1','2026-11-06','s-102',2,8900,4900]]),
 r8Csv([R8_KINDS.returns,['r1','2026-11-06','s-102',1,8900,4900],['r2','2026-11-07','s-102',1,8900,4900]]),
 r8Csv([R8_KINDS.returns,['r1','2026-11-06','s-101',1,17800,9800],['r2','2026-11-07','s-101',1,100,100]])
 ])bad(source,'returns',t,/превыш|больше|возврат/i);
});
test('return cannot precede linked receipt or point to missing receipt',()=>{const source=acceptCsv(emptyWorkingSet(),'sales',r8Example().sales).workspace;bad(source,'returns',replace(r8Example().returns,'2026-11-05','2026-10-01'),/раньше/);bad(source,'returns',replace(r8Example().returns,'s-102','fake-id'),/нет исходного/);});
test('linked request must match SKU size store and chronology',()=>{const ws=acceptCsv(emptyWorkingSet(),'sales',r8Example().sales).workspace;bad(ws,'requests',replace(r8Example().requests,'"store-B";"JKT-01";"L";"1";"s-102"','"store-C";"JKT-01";"L";"1";"s-102"'),/неверная|Чек/);bad(ws,'requests',replace(r8Example().requests,'s-102','nonexistent'),/чек не существует/);});
test('duplicate stock SKU-size-store-asOf rejected',()=>{const t=r8Csv([R8_KINDS.stock,['s1',AS_OF,'A','A','L',2],['s2',AS_OF,'A','A','L',3]]);bad(emptyWorkingSet(),'stock',t,/Дублированный остаток/);});
test('CSV output escapes formula cells while preserving real negative numbers',()=>{const c=r8Csv([['key','value'],['=1+1',-125],['+CMD',25],['@LOOKUP',5]]);assert.ok(c.includes('"\'=1+1"'));assert.ok(c.includes(';-125'));assert.ok(c.includes('"\'@LOOKUP"'));assert.ok(ledgerCsv(salesLedger(good)).startsWith('\ufeff'));});

// 3: stock guard and unique allocations
 test('one current source stock is used no more than its quantity',()=>{const r=availabilityPlan(good,{fixedCost:100,unitCost:100,probability:70});assert.equal(r.valid,true);assert.equal(r.gapCount,4);assert.equal(r.routes.length,3);assert.equal(r.movedByStock['stk-102'],3);assert.equal(new Set(r.routes.map(x=>x.requestId)).size,3);assert.ok(r.net>0);});
test('reserving two units leaves just one route',()=>{const r=availabilityPlan(good,{reserve:2,fixedCost:10,unitCost:10});assert.equal(r.movedByStock['stk-102'],1);assert.equal(r.routes.length,1);});
test('probability zero or unaffordable logistics suppress routes',()=>{assert.equal(availabilityPlan(good,{probability:0}).routes.length,0);assert.equal(availabilityPlan(good,{fixedCost:1000000}).routes.length,0);});
test('stale snapshot disables all routes and unknown absence is not stated as fact',()=>{const ws=structuredClone(good);ws.stock.forEach(x=>x.asOf='2026-11-07');const r=availabilityPlan(ws);assert.equal(r.routes.length,0);assert.equal(r.gapCount,null);assert.equal(r.stockCurrent,false);});
test('no destination stock row means no proof of absence',()=>{const ws=structuredClone(good);ws.stock=ws.stock.filter(x=>x.storeId!=='store-C');const r=availabilityPlan(ws);assert.equal(r.routes.length,2);assert.equal(r.gapCount,2);});
test('unknown historical SKU margin cannot create transfer value',()=>{const ws=structuredClone(good);ws.sales=ws.sales.filter(x=>x.sku!=='JKT-01');ws.returns=[];ws.requests=ws.requests.filter(x=>!x.linkedSaleId);const r=availabilityPlan(ws);assert.equal(r.routes.length,0);assert.ok(r.unknownMargin>0);});
test('stock routes CSV names scenario instead of confirmed sale',()=>{const c=availabilityCsv(availabilityPlan(good));assert.match(c,/сценария/);assert.doesNotMatch(c,/Доказанная дополнительная прибыль/);});
test('scenario parameters do not mutate actual inventory',()=>{const original=JSON.stringify(good);availabilityPlan(good,{reserve:1,probability:100});assert.equal(JSON.stringify(good),original);});

// 4: consent safe pilot and deterministic holdout
 test('pilot excludes contacts without consent and linked sales',()=>{const r=recoveryPilot(good);assert.equal(r.candidates,3);assert.equal(r.excluded,2);assert.equal(r.test.length+r.control.length,3);assert.equal(r.incrementalProven,false);});
test('pilot assignments are deterministic for a fixed seed',()=>{const x=recoveryPilot(good),y=recoveryPilot(good);assert.deepEqual(x.test,y.test);assert.deepEqual(x.control,y.control);});
test('invalid assumptions reject program',()=>{for(const param of [{testShare:0},{testShare:100},{lift:101},{notificationCost:-1},{maxInvites:1.2},{seed:'a;bad'}])assert.equal(recoveryPilot(good,param).valid,false);});
test('zero uplift cannot be shown as realized profit',()=>{const r=recoveryPilot(good,{lift:0});assert.equal(r.expectedGross,0);assert.ok(r.expectedNet<0);});
test('pilot holdout CSV exports only consented, unpurchased request IDs',()=>{const r=recoveryPilot(good),csv=recoveryCsv(r);assert.ok(csv.includes('q-101'));assert.ok(!csv.includes('q-103'));assert.ok(!csv.includes('q-104'));});
test('no receipts → pilot effect unavailable, not invented',()=>{const w=structuredClone(good);w.sales=[];w.returns=[];w.requests=w.requests.filter(x=>!x.linkedSaleId);const r=recoveryPilot(w);assert.equal(r.expectedGross,null);assert.equal(r.expectedNet,null);});

// 5: source-labelled director signoff and aggregate-only history
 test('director brief exposes five source-labelled claims without inventing incrementality',()=>{const b=r8OwnerBrief(good);assert.equal(b.valid,true);assert.equal(b.claims.length,5);assert.equal(b.claims[2].value,11600);assert.equal(b.claims[4].status,'ГИПОТЕЗА');assert.equal(b.example,true);});
test('owner brief CSV and audit CSV contain no customer contacts',()=>{const b=r8OwnerBrief(good);const csv=r8BriefCsv(b);assert.ok(csv.includes('Валовая прибыль'));assert.ok(!csv.includes('телефон'));assert.ok(!csv.includes('q-101'));});
test('signoff needs accepted receipts and no errors',()=>{assert.equal(r8OwnerBrief(emptyWorkingSet()).valid,false);assert.throws(()=>appendR8Audit([],r8OwnerBrief(emptyWorkingSet())),/проверьте/);});
test('aggregate chain survives restore and rejects tampering',()=>{const a=appendR8Audit([],r8OwnerBrief(good)),b=appendR8Audit(a,r8OwnerBrief(good),{status:'reviewed'});assert.equal(restoreR8Audit({version:R8_AUDIT_VERSION,items:b}).length,2);const changed=structuredClone(b);changed[0].gross+=1;assert.deepEqual(restoreR8Audit({version:R8_AUDIT_VERSION,items:changed}),[]);const reversed=b.slice().reverse();assert.deepEqual(restoreR8Audit({version:R8_AUDIT_VERSION,items:reversed}),[]);});
test('only aggregate evidence remains in saved history (no receipt/request IDs)',()=>{const a=appendR8Audit([],r8OwnerBrief(good));const csv=r8AuditCsv(a);assert.ok(csv.includes('Контрольная сумма'));assert.ok(!JSON.stringify(a).includes('q-101'));assert.ok(!JSON.stringify(a).includes('s-101'));assert.ok(!csv.includes('JKT-01'));});
test('history schema fails closed for wrong version or extra keys',()=>{const a=appendR8Audit([],r8OwnerBrief(good));assert.deepEqual(restoreR8Audit({version:2,items:a}),[]);const extra=structuredClone(a);extra[0].phone='123';assert.deepEqual(restoreR8Audit({version:R8_AUDIT_VERSION,items:extra}),[]);});
test('all real and demo dataset references remain unchanged',()=>{const demo=buildDataset('balanced');const before=scopeData(demo,{period:'14'}).totals.revenue;const raw=JSON.stringify(good);r8OwnerBrief(good);recoveryPilot(good);salesLedger(good);assert.equal(JSON.stringify(good),raw);assert.equal(scopeData(demo,{period:'14'}).totals.revenue,before);});
