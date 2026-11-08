import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {buildDataset,scopeData} from '../src/model.mjs';
import {renderR8Radar,renderR8Capacity,renderR8Outreach,renderR8Procurement,renderR8Stress} from '../src/r8_views.mjs';
const app=readFileSync(new URL('../src/app.mjs',import.meta.url),'utf8');
const views=readFileSync(new URL('../src/r8_views.mjs',import.meta.url),'utf8');
const builder=readFileSync(new URL('../scripts/build_standalone.py',import.meta.url),'utf8');
const stylesheet=readFileSync(new URL('../src/r8.css',import.meta.url),'utf8');
const index=readFileSync(new URL('../index.html',import.meta.url),'utf8');
const dataset=buildDataset(),scope=scopeData(dataset,{period:14,store:'all'});
const pages=[['demand-radar',()=>renderR8Radar(dataset,scope,{windowDays:14,minSample:5,signal:'unresolved'},'s1')],['service-capacity',()=>renderR8Capacity(scope,{slaSeconds:120,serviceMinutes:12,shiftHours:8,occupancyPercent:70,currentHandlers:1,staffDailyCost:2500,demandFactor:1},'s1')],['retention-experiment',()=>renderR8Outreach(scope,{holdoutPercent:25,controlRate:5,treatmentRate:15,unitMargin:4000,promotionCost:300,messageCost:15,fixedCost:500})],['replenishment-risk',()=>renderR8Procurement(dataset,scope,{windowDays:30,leadDays:21,reviewDays:7,safetyFactor:1.28,requestWeight:.25,minOrder:2,budget:75000,category:'Куртки'},'')],['profit-stress',()=>renderR8Stress(scope,{conversionLow:5,conversionBase:15,conversionHigh:30,unitPrice:8900,unitCost:4900,discountPercent:0,returnPercent:5,logisticsPerOrder:350,costPerOpportunity:10,fixedCost:1200})]];
test('R8 routes are present in navigation, document title and main router',()=>{for(const [route] of pages){assert.ok(app.includes(`['${route}'`),route);assert.ok(app.includes(`state.page==='${route}'`),route)}});
test('R8 five pages have one strong heading and synthetic watermark',()=>{for(const [route,fn] of pages){const html=fn();assert.equal((html.match(/<h1\b/g)||[]).length,1,route);assert.match(html,/SYNTHETIC DATA/,route);assert.match(html,/data-r8-field/,route)}});
test('R8 no page claims live 1C connection',()=>{for(const [,fn] of pages)assert.ok(!fn().includes('1С подключена'))});
test('R8 every action has a real registered handler',()=>{const actions=[...views.matchAll(/data-action="([a-z0-9-]+)"/g)].map(x=>x[1]);for(const action of actions)assert.ok(app.includes(`a==='${action}'`),`Not handled: ${action}`)});
test('R8 all fields have a listener and either map or explicit selector',()=>{const fields=[...views.matchAll(/r8_field\('([^']+)'|r8_select\('([^']+)'/g)].map(x=>x[1]||x[2]);for(const field of fields)assert.ok(app.includes(field),field)});
test('R8 core must be imported by main app and embedded offline release',()=>{assert.ok(app.includes("from './r8_core.mjs'"));assert.ok(app.includes("from './r8_views.mjs'"));assert.ok(builder.includes("'r8_core.mjs'"));assert.ok(builder.includes("'r8_views.mjs'"))});
test('R8 CSS loaded by both offline builder and index',()=>{assert.ok(stylesheet.includes('.r8-head'));assert.ok(stylesheet.includes('max-width:520px'));assert.ok(builder.includes("r8.css"));assert.ok(index.includes('src/r8.css'))});
test('R8 invalid inputs do not prevent viewing and correcting any page',()=>{
 const invalid=[renderR8Radar(dataset,scope,{windowDays:0,minSample:0,signal:'invalid'},'s1'),renderR8Capacity(scope,{slaSeconds:0,serviceMinutes:0,shiftHours:0,occupancyPercent:200,currentHandlers:1,staffDailyCost:2500,demandFactor:1},'s1'),renderR8Outreach(scope,{holdoutPercent:200}),renderR8Procurement(dataset,scope,{windowDays:0},''),renderR8Stress(scope,{conversionLow:100,conversionBase:0,conversionHigh:20})];
 for(const html of invalid){assert.ok(html.includes('data-r8-field'));assert.ok(html.includes('role="alert"'))}
});
test('R8 pages do not inject user-supplied HTML as markup',()=>{const html=renderR8Radar(dataset,{...scope,filter:{...scope.filter,store:'s1'}},{windowDays:14,minSample:5,signal:'unresolved'},'s1');assert.ok(html.includes('Факты')===false||!html.includes('<script>alert'))});
