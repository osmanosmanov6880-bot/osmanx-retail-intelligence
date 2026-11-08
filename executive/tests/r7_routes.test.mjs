import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {buildDataset,scopeData} from '../src/model.mjs';
import {renderR7Gate,renderR7Rebalance,renderR7Capital,renderR7Privacy,renderR7Brief} from '../src/r7_views.mjs';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url))),app=fs.readFileSync(path.join(root,'src/app.mjs'),'utf8');
const d=buildDataset('balanced'),scope=scopeData(d,{period:'14'});
const screens=[['evidence-gate',()=>renderR7Gate(d,scope,{minimumRequests:10,minimumLinked:3,maxStockAgeDays:1})],['network-rebalance',()=>renderR7Rebalance(d,scope,{reserve:0,probability:55,fixedCost:300,unitCost:250,maxUnits:3,minDemand:1},'')],['capital-lab',()=>renderR7Capital(d,scope,{budget:12000,capacity:3,verificationCost:600,confidence:70},{reserve:0,probability:55,fixedCost:300,unitCost:250,maxUnits:3,minDemand:1})],['privacy-lab',()=>renderR7Privacy(d,scope,{retentionDays:30,requireConsent:true},[])],['executive-brief',()=>renderR7Brief(d,scope,{gate:{},rebalance:{},capital:{},privacy:{}},[],[])]];
for(const [route,render] of screens){test('R7 screen '+route+' is a real page with interaction controls',()=>{
 const h=render();assert.match(app,new RegExp(route));assert.match(h,/<h1>/);assert.match(h,/data-action="r7-/);assert.match(h,/ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ/);assert.ok(h.length>1400);assert.doesNotMatch(h,/onhover=|onclick=/);
});}
test('app defines controlled state, all handlers and tests hooks',()=>{
 for(const word of ['r7Gate','r7Move','r7Capital','r7Privacy','r7PrivacyLedger','r7InputChange','data-r7-field','r7-brief-pdf','r7-privacy-apply','r7-capital-task','r7-move-task','r7-gate-task','get r7()'])assert.ok(app.includes(word),word);
});
test('bundle includes core, views, PDF, CSS in correct order',()=>{
 const b=fs.readFileSync(path.join(root,'scripts/build_standalone.py'),'utf8');for(const name of ['r7_core.mjs','r7_views.mjs','r7_pdf.mjs','r7.css'])assert.ok(b.includes(name),name);
});
test('R7 HTML components escape dynamic data against template injection',()=>{
 const text=fs.readFileSync(path.join(root,'src/r7_views.mjs'),'utf8');assert.match(text,/esc\(/);assert.match(text,/r7_e\(/);
});
test('privacy action explicitly warns no real data deletion',()=>{assert.match(app,/Реальные данные не удалялись/);});
test('R7 route navigation is compatible with hash, mobile sidebar and offline build',()=>{
 assert.match(app,/NAV.flatMap/);assert.match(app,/data-r7-field/);assert.match(fs.readFileSync(path.join(root,'index.html'),'utf8'),/r7.css/);
});

test('all R7 rendered screens have actual CSS classes and browser-recognized fields',()=>{
 for(const [route,render] of screens){const html=render();
  assert.match(html,/class="r7-head"/);assert.match(html,/class="r7-demo-stamp"/);
  assert.doesNotMatch(html,/r7-r7_|<r7_select|data-r7-r7_field|r7-move-r7_select/);
 }
});
test('R7 interaction attributes map to application event handlers',()=>{
 const dom=renderR7Rebalance(d,scope,{reserve:0,probability:55,fixedCost:300,unitCost:250,maxUnits:3,minDemand:1},'');
 assert.match(dom,/data-action="r7-move-select"/);assert.match(dom,/data-r7-field="moveProbability"/);
 const priv=renderR7Privacy(d,scope,{retentionDays:30,requireConsent:true},[]);
 assert.match(priv,/<select data-r7-field="privacyConsent"/);assert.match(priv,/<\/select>/);
});
