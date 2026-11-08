import test from 'node:test';
import assert from 'node:assert/strict';
import {AS_OF,buildDataset,scopeData} from '../src/model.mjs';
import {demandRadar,radarCsv,serviceCapacity,capacityCsv,retentionOutreach,outreachCsv,procurementRisk,procurementCsv,scenarioStress,stressCsv,R8_RELEASE} from '../src/r8_core.mjs';
const data=buildDataset(),scope=scopeData(data,{period:14,store:'all',category:'all',size:'all',model:'all'});
const withStore=(store)=>scopeData(data,{period:14,store,category:'all',size:'all',model:'all'});
const sum=(a,fn)=>a.reduce((s,x)=>s+fn(x),0);

// Temporal demand radar — no fabricated denominators or causal conclusions.
test('R8 manifest version is stable',()=>assert.equal(R8_RELEASE,'R8'));
test('radar defaults to 14 daily observations',()=>{const r=demandRadar(data,scope);assert.equal(r.days,14);assert.equal(r.daily.length,14);assert.ok(r.valid)});
test('radar totals reconcile across stores',()=>{const r=demandRadar(data,scope);assert.equal(r.total,sum(r.rows,x=>x.total));assert.equal(r.observed,sum(r.rows,x=>x.observed))});
test('radar denominator includes all requests',()=>{const r=demandRadar(data,scope);assert.equal(r.total,scope.requests.length);assert.equal(r.observed,scope.requests.filter(x=>!x.purchased&&!x.solutionFound).length)});
test('radar all signal counts every request',()=>{const r=demandRadar(data,scope,{signal:'all'});assert.equal(r.observed,r.total);assert.equal(r.rate,1)});
test('radar consented excludes buyers',()=>{const r=demandRadar(data,scope,{signal:'consented'});assert.equal(r.observed,scope.requests.filter(x=>x.consent&&!x.purchased).length)});
test('radar never uses shorter prior period as valid baseline',()=>{const s=scopeData(data,{period:90});const r=demandRadar(data,s,{windowDays:45});assert.equal(r.comparable,true);const late={...s,to:'2026-08-12',from:'2026-08-11'};const invalid=demandRadar(data,late,{windowDays:2});assert.equal(invalid.comparable,false)});
test('radar follows store scope exactly',()=>{const r=demandRadar(data,withStore('s2'));assert.equal(r.rows.length,1);assert.equal(r.rows[0].id,'s2')});
test('radar refuses zero or fractional windows',()=>{for(const days of [0,.5,46,NaN])assert.equal(demandRadar(data,scope,{windowDays:days}).valid,false)});
test('radar refuses invalid thresholds and signal types',()=>{assert.equal(demandRadar(data,scope,{minSample:0}).valid,false);assert.equal(demandRadar(data,scope,{signal:'secret'}).valid,false)});
test('radar exports real dated evidence',()=>{const r=demandRadar(data,scope),csv=radarCsv(r);assert.ok(csv.includes('Филиал'));assert.ok(csv.includes(r.from));assert.ok(csv.includes('req-14-'))});
test('radar returns no CSV for invalid plan',()=>assert.equal(radarCsv(demandRadar(data,scope,{windowDays:-1})),null));
test('radar robust with empty scoped requests',()=>{const s={...scope,filter:{store:'s1',model:'nonexistent'},requests:[]};const r=demandRadar(data,s);assert.equal(r.observed,0);assert.equal(r.total,0);assert.equal(r.rate,null)});

// Staffing capacity — never converts response-time correlations into measured uplift.
test('capacity counts exactly observed QR events',()=>{const r=serviceCapacity(scope);assert.equal(r.totalEvents,scope.assistance.length)});
test('capacity per store reconciles QR events',()=>{const r=serviceCapacity(scope);assert.equal(sum(r.rows,x=>x.sample),r.totalEvents);assert.equal(sum(r.rows,x=>x.breached),r.breaches)});
test('capacity respects selected store only',()=>{const r=serviceCapacity(withStore('s1'));assert.equal(r.rows.length,1);assert.equal(r.rows[0].id,'s1')});
test('capacity never recommends staff with zero demand',()=>{const s={...scope,assistance:[]};const r=serviceCapacity(s);assert.equal(r.extraStaff,0);assert.equal(r.cost,0);assert.equal(r.rows[0].p90,null)});
test('capacity staff change cannot decrease marginal cost',()=>{const a=serviceCapacity(scope,{currentHandlers:0,demandFactor:20}),b=serviceCapacity(scope,{currentHandlers:3,demandFactor:20});assert.ok(a.cost>=b.cost)});
test('capacity higher wage cannot decrease cost',()=>{const a=serviceCapacity(scope,{currentHandlers:0,demandFactor:20,staffDailyCost:1000}),b=serviceCapacity(scope,{currentHandlers:0,demandFactor:20,staffDailyCost:4000});assert.ok(b.cost>=a.cost)});
test('capacity p90 comes from actual sorted response samples',()=>{const s={...scope,assistance:[{id:'a',storeId:'s1',responseSeconds:2},{id:'b',storeId:'s1',responseSeconds:4},{id:'c',storeId:'s1',responseSeconds:80}]};assert.equal(serviceCapacity(s).rows[0].p90,80)});
test('capacity invalid percentages and negative money are refused',()=>{for(const v of [0,100,-2])assert.equal(serviceCapacity(scope,{occupancyPercent:v}).valid,false);assert.equal(serviceCapacity(scope,{staffDailyCost:-1}).valid,false)});
test('capacity CSV exposes observed and assumed demand separately',()=>{const csv=capacityCsv(serviceCapacity(scope));assert.ok(csv.includes('В день наблюдалось'));assert.ok(csv.includes('В день сценарий'))});

// Retention — aggregate only, holdout never sent to campaign, bonus cost charges all treatment conversions.
test('outreach eligible uses strictly consented unresolved sales solutions',()=>{const r=retentionOutreach(scope);const eligible=scope.requests.filter(x=>x.consent&&!x.purchased&&x.solutionFound).length;assert.equal(r.eligible,eligible)});
test('outreach deterministic holdout and groups sum to eligible',()=>{const a=retentionOutreach(scope),b=retentionOutreach(scope);assert.deepEqual(a.rows,b.rows);assert.equal(a.treatment+a.holdout,a.eligible)});
test('outreach groups by store without disclosing IDs',()=>{const r=retentionOutreach(scope);assert.equal(sum(r.rows,x=>x.eligible),r.eligible);assert.ok(!outreachCsv(r).includes('req-old-'))});
test('outreach never marks marketing permission as verified',()=>assert.equal(retentionOutreach(scope).purposeSpecificPermissionConfirmed,false));
test('outreach no incremental benefit without conversion improvement',()=>{const r=retentionOutreach(scope,{controlRate:12,treatmentRate:12});assert.ok(r.net<=0);assert.equal(r.incrementalExpected,0)});
test('outreach bonus charged on every expected treatment purchase',()=>{const r=retentionOutreach(scope,{treatmentRate:50,promotionCost:200});assert.equal(r.bonus,r.expectedTreatment*200)});
test('outreach negative response uplift is negative, not clipped',()=>{const r=retentionOutreach(scope,{controlRate:70,treatmentRate:10});assert.ok(r.incrementalExpected<0);assert.ok(r.net<0)});
test('outreach 1 eligible event cannot give fake control experiment',()=>{const s={...scope,requests:[{id:'one',storeId:'s1',consent:true,purchased:false,solutionFound:true}]};const r=retentionOutreach(s);assert.equal(r.holdout,1);assert.equal(r.treatment,0);assert.equal(r.experimentFeasible,false)});
test('outreach without eligible events has no contacts',()=>{const s={...scope,requests:[]};const r=retentionOutreach(s);assert.equal(r.treatment,0);assert.equal(r.contacts,0);assert.equal(r.experimentFeasible,false)});
test('outreach rejects illegal budget and conversion rates',()=>{assert.equal(retentionOutreach(scope,{controlRate:110}).valid,false);assert.equal(retentionOutreach(scope,{fixedCost:-1}).valid,false)});
test('outreach CSV is aggregate and formula-safe',()=>{const csv=outreachCsv(retentionOutreach(scope));assert.ok(csv.includes('ВСЕГО'));assert.ok(!csv.includes('loy-'));assert.ok(!csv.includes('req-14-'))});

// Procurement — no phantom stock, MOQ and budget are enforced.
test('procurement generates non-empty bounded default recommendations',()=>{const r=procurementRisk(data,scope);assert.equal(r.valid,true);assert.ok(r.approved.length>0);assert.ok(r.spent<=r.budget)});
test('procurement cannot spend above zero budget',()=>{const r=procurementRisk(data,scope,{budget:0});assert.equal(r.units,0);assert.equal(r.spent,0)});
test('procurement requires an as-of current snapshot',()=>{const historical={...scope,to:'2026-11-01'};assert.equal(procurementRisk(data,historical).valid,false)});
test('procurement does not approve missing stock snapshots',()=>{const injected={...data,stock:data.stock.filter(x=>x.modelId!=='JKT-AURA')};const r=procurementRisk(injected,scope);assert.ok(r.rows.some(x=>x.modelId==='JKT-AURA'&&!x.snapshotValid));assert.ok(r.approved.every(x=>x.snapshotValid))});
test('procurement rejects stale stock snapshots',()=>{const injected={...data,stock:data.stock.map(x=>({...x,asOf:'2026-11-01'}))};const r=procurementRisk(injected,scope);assert.equal(r.approved.length,0)});
test('procurement validates MOQ and budget',()=>{for(const opt of [{minOrder:0},{minOrder:2.5},{budget:-1},{leadDays:181},{requestWeight:2}])assert.equal(procurementRisk(data,scope,opt).valid,false)});
test('procurement MOQ is applied to each proposed lot',()=>{const r=procurementRisk(data,scope,{minOrder:4,budget:1e7});assert.ok(r.approved.every(x=>x.units%4===0))});
test('procurement spend reconciles every approved lot',()=>{const r=procurementRisk(data,scope);assert.equal(r.spent,sum(r.approved,x=>x.cost));assert.equal(r.units,sum(r.approved,x=>x.units))});
test('procurement respects filtered category and store',()=>{const r=procurementRisk(data,withStore('s2'));assert.ok(r.rows.every(x=>x.storeId==='s2'&&x.category==='Куртки'))});
test('procurement demand weighting 0 removes speculative signals',()=>{const a=procurementRisk(data,scope,{requestWeight:0,budget:1e7}),b=procurementRisk(data,scope,{requestWeight:1,budget:1e7});assert.ok(a.shortage<=b.shortage)});
test('procurement CSV includes snapshots and does not fabricate purchases',()=>{const csv=procurementCsv(procurementRisk(data,scope));assert.ok(csv.includes('ID снимка'));assert.ok(csv.includes('В бюджете'))});

// Profit stress — no leakage into observed financial facts.
test('stress accounts only unresolved unpurchased demand',()=>{const r=scenarioStress(scope);assert.equal(r.n,scope.requests.filter(x=>!x.purchased&&!x.solutionFound).length)});
test('stress does not mutate baseline observed results',()=>{const baseline=scope.totals.grossProfit;const r=scenarioStress(scope);assert.equal(r.baselineGrossProfit,baseline);assert.equal(scope.totals.grossProfit,baseline)});
test('stress ordering of expected results follows conversion rates with positive margin',()=>{const r=scenarioStress(scope);assert.ok(r.rows[0].net<=r.rows[1].net);assert.ok(r.rows[1].net<=r.rows[2].net)});
test('stress zero demand loses launch cost but fabricates no purchases',()=>{const s={...scope,requests:[]};const r=scenarioStress(s);assert.equal(r.n,0);assert.equal(r.rows[0].orders,0);assert.equal(r.baseNet,-1200)});
test('stress equal conversions create equal outcomes',()=>{const r=scenarioStress(scope,{conversionLow:10,conversionBase:10,conversionHigh:10});assert.equal(r.rows[0].net,r.rows[1].net);assert.equal(r.rows[1].net,r.rows[2].net)});
test('stress 100 percent returns removes sales gross but not logistics',()=>{const r=scenarioStress(scope,{returnPercent:100});assert.ok(r.baseNet<0);assert.ok(r.perOrderAfterReturns<=0)});
test('stress negative unit margin means no break even',()=>{const r=scenarioStress(scope,{unitPrice:1000,unitCost:3000});assert.equal(r.breakEven,null);assert.equal(r.breakEvenReachable,false)});
test('stress larger logistics reduces expected outcome',()=>{const a=scenarioStress(scope,{logisticsPerOrder:50}),b=scenarioStress(scope,{logisticsPerOrder:1200});assert.ok(a.baseNet>b.baseNet)});
test('stress rejects nonsensical scenario ordering',()=>assert.equal(scenarioStress(scope,{conversionLow:40,conversionBase:20,conversionHigh:30}).valid,false));
test('stress rejects NaN, negative and out-of-range costs',()=>{for(const params of [{conversionLow:NaN},{fixedCost:-2},{discountPercent:91}])assert.equal(scenarioStress(scope,params).valid,false)});
test('stress CSV includes scenario not fake facts',()=>{const csv=stressCsv(scenarioStress(scope));assert.ok(csv.includes('Осторожный'));assert.ok(csv.includes('Базовый'));assert.ok(csv.includes('Верхний'))});
test('stress invalid plan has no CSV',()=>assert.equal(stressCsv(scenarioStress(scope,{unitCost:-1})),null));
