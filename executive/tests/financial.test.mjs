import test from 'node:test';
import assert from 'node:assert/strict';
import {AS_OF,STORES,SIZES,CATALOG,AURA,buildCatalog,buildDataset,scopeData,product,daysAgo,funnelData,forecastTransfer,pilotForecast,diagnosticPlan,opportunityMetrics,safeRatio} from '../src/model.mjs';
const data=buildDataset('balanced');
const last14=scopeData(data,{period:14});
test('catalog contains exactly 300 linked distinct product models',()=>{
 assert.equal(CATALOG.length,300);assert.equal(new Set(CATALOG.map(p=>p.id)).size,300);assert.equal(AURA.price,8900);assert.equal(AURA.cost,4900);
 assert.ok(CATALOG.every(p=>p.cost>0&&p.price>p.cost&&p.colors.length>=2));
});
test('90 days, 3 stores, all event IDs and model refs valid',()=>{
 assert.equal(data.stores.length,3);assert.equal(data.traffic.length,270);
 assert.equal(new Set(data.traffic.map(x=>x.date)).size,90);
 const ids=new Set(CATALOG.map(p=>p.id));const stores=new Set(STORES.map(s=>s.id));
 for(const name of ['sales','returns','requests','fittings','assistance','stock','transfers','audits','preorders','preferences']) {
  assert.ok(data[name].length>0,name);
  const ev=data[name];assert.equal(new Set(ev.map(x=>x.id)).size,ev.length,name+' IDs');
  for(const row of ev){assert.ok(row.date?row.date<=AS_OF:true,name+' date');assert.ok(ids.has(row.modelId),name+' model');assert.ok(stores.has(row.storeId||row.fromStoreId),name+' store');}
 }
 assert.equal(data.stock.length,300*3*5*2);
});
test('verified funnel in default synthetic 14 days is precisely 60 / 32 / 18 / 7',()=>{
 assert.deepEqual(funnelData(last14),[60,32,18,7]);
 assert.equal(last14.totals.confirmedRescueSales,7);
 assert.equal(last14.totals.confirmedRescueGross,28000);
});
test('7 linked receipts have exact sale values 8,900 / cost 4,900',()=>{
 const linked=data.sales.filter(x=>x.originRequestId);
 assert.equal(linked.length,7);
 for(const sale of linked){assert.equal(sale.paidPrice,8900);assert.equal(sale.cost,4900);assert.ok(data.requests.some(q=>q.id===sale.originRequestId&&q.saleId===sale.id&&q.purchased));}
});
test('sales and returns have correct date order and valid original receipts',()=>{
 const receipts=new Map(data.sales.map(s=>[s.id,s]));
 for(const row of data.returns){const src=receipts.get(row.saleId);assert.ok(src);assert.ok(row.date>=src.date);assert.equal(row.refundedPrice,src.paidPrice);assert.equal(row.reversedCost,src.cost);}
});
test('net revenue and gross margin reconcile against individual event ledger',()=>{
 const netSales=last14.sales.reduce((s,e)=>s+e.paidPrice,0);
 const refunded=last14.returns.reduce((s,e)=>s+e.refundedPrice,0);
 const totalCost=last14.sales.reduce((s,e)=>s+e.cost,0)-last14.returns.reduce((s,e)=>s+e.reversedCost,0);
 assert.equal(last14.totals.revenue,netSales-refunded);
 assert.equal(last14.totals.costOfGoods,totalCost);
 assert.equal(last14.totals.grossProfit,last14.totals.revenue-totalCost);
 assert.equal(last14.totals.grossMargin,last14.totals.grossProfit/last14.totals.revenue);
});
test('date filters and store filters reduce scoped events coherently',()=>{
 const full=scopeData(data,{period:90}),today=scopeData(data,{period:1}),s1=scopeData(data,{period:14,store:'s1'});
 assert.ok(full.sales.length>last14.sales.length);assert.ok(last14.sales.length>today.sales.length);
 assert.ok(s1.sales.every(x=>x.storeId==='s1'));assert.ok(s1.requests.every(x=>x.storeId==='s1'));
 assert.ok(s1.totals.revenue<last14.totals.revenue);
 assert.equal(today.from,AS_OF);assert.equal(today.to,AS_OF);
});
test('product and size filters refuse fabricated visitation conversion',()=>{
 const filtered=scopeData(data,{period:14,category:'Куртки',size:'L'});
 assert.equal(filtered.totals.visits,null);assert.equal(filtered.totals.conversion,null);
 assert.ok(filtered.sales.every(x=>product(x.modelId).category==='Куртки'&&x.size==='L'));
});
test('stock physical availability has required transfer 3 L jacket units',()=>{
 const target=(storeId)=>data.stock.find(x=>x.modelId===AURA.id&&x.storeId===storeId&&x.size==='L'&&x.color==='Графит')?.quantity;
 assert.equal(target('s1'),0);assert.equal(target('s2'),3);
});
test('transfer scenario expected economics: 3 * .55 * 4000 - 3 * 350 = 5550',()=>{
 const f=forecastTransfer({units:3,probability:.55,price:8900,cost:4900,costPerUnit:350});
 assert.ok(Math.abs(f.expectedSales-1.65)<1e-10);assert.equal(f.gross,6600);assert.equal(f.logistics,1050);assert.equal(f.net,5550);
});
test('transfer scenario clamps invalid probability, logistics are never negative',()=>{
 const f=forecastTransfer({units:2,probability:100,price:2000,cost:1000,costPerUnit:-10});
 assert.equal(f.expectedSales,2);assert.equal(f.logistics,0);assert.equal(f.net,2000);
});
test('pilot forecast separates gross revenue, gross profit and pilot expense',()=>{
 const f=pilotForecast({stores:3,requestsPerStore:20,conversion:.12,avgTicket:8900,costPerSale:4900,pilotCost:15000});
 assert.ok(Math.abs(f.potentialPurchases-7.2)<1e-10);assert.equal(Math.round(f.revenue),64080);
 assert.equal(Math.round(f.gross),28800);assert.equal(Math.round(f.net),13800);
 assert.ok(Math.abs(f.paybackRatio-1.92)<1e-10);
});
test('pilot forecast handles absent or zero resources correctly',()=>{
 const f=pilotForecast({stores:0,requestsPerStore:0,conversion:.1,pilotCost:0});
 assert.equal(f.revenue,0);assert.equal(f.gross,0);assert.equal(f.paybackRatio,null);
});
test('date arithmetic is anchored and deterministic',()=>{
 assert.equal(daysAgo(0),AS_OF);assert.equal(daysAgo(13),'2026-10-26');assert.equal(daysAgo(89),'2026-08-11');
});
test('different scenarios preserve referential integrity and change observed demand',()=>{
 const shortage=scopeData(buildDataset('shortages'),{period:14});
 const operations=scopeData(buildDataset('operations'),{period:14});
 assert.ok(shortage.totals.requested>last14.totals.requested);
 assert.ok(operations.totals.requested>last14.totals.requested);
 assert.ok(shortage.totals.revenue!==last14.totals.revenue);
});
test('opportunity map never presents unsupported inventory money as fact',()=>{
 const map=opportunityMetrics(last14);
 assert.equal(map.length,6);assert.equal(map.find(x=>x.id==='stock').estimate,null);
 assert.ok(map.find(x=>x.id==='demand').estimate>=0);
});
test('diagnostic is a three-step check plan, not a manufactured conclusion',()=>{
 const p=diagnosticPlan({trackSizes:'Нет',findAcross:'Нет',refusal:'Нет'});
 assert.equal(p.length,3);assert.ok(p.every(x=>x.title&&x.detail));
 assert.equal(diagnosticPlan({trackSizes:'Да',findAcross:'Да',refusal:'Да'}).length,3);
});
test('safe ratio uses null when denominator has no support',()=>{
 assert.equal(safeRatio(0,0),null);assert.equal(safeRatio(2,4),.5);
});
