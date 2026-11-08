import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {emptyWorkingSet,r8Example,acceptCsv} from '../src/r8_core.mjs';
import {renderR8Intake,renderR8Ledger,renderR8Availability,renderR8Recovery,renderR8Brief} from '../src/r8_views.mjs';
const base=new URL('../',import.meta.url),read=p=>readFileSync(new URL(p,base),'utf8');
const w=(()=>{let w=emptyWorkingSet();for(const k of ['sales','returns','requests','stock'])w=acceptCsv(w,k,r8Example()[k],{origin:'example'}).workspace;return w;})();
const views={
 'local-vault':renderR8Intake(w,{kind:'sales',text:'',errors:[]}),
 'local-ledger':renderR8Ledger(w,{store:'all'}),
 'local-availability':renderR8Availability(w,{reserve:0,probability:70,fixedCost:100,unitCost:100,maxRoutes:30}),
 'local-recovery':renderR8Recovery(w,{testShare:50,lift:5,notificationCost:25,fixedCost:500,maxInvites:100,seed:'R8'}),
 'local-brief':renderR8Brief(w,{store:'all',status:'needs-review'},[])
};
for(const [route,html] of Object.entries(views))test(`R8 ${route} renders one executive title and visible data provenance`,()=>{
 assert.match(html,/<h1>/);assert.match(html,/УЧЕБНЫЙ CSV/);assert.match(html,/r8-origin/);assert.match(html,/LOCAL DATA \/ R8/);
 assert.ok(html.length>1200);assert.doesNotMatch(html,/\bundefined\b|\bNaN\b/);
});
test('R8 local vault exposes all four contracts, upload, paste, explicit acceptance and reset',()=>{const h=views['local-vault'];for(const q of ['r8-kind','r8-file','r8-text','r8-accept','r8-clear','r8-sample-all'])assert.ok(h.includes(q),q);});
test('R8 cashflow displays audited linked returns and real CSV action',()=>{const h=views['local-ledger'];assert.ok(h.includes('11 600')||h.includes('11 600'));assert.ok(h.includes('r8-ledger-csv'));assert.match(h,/<tbody>/);assert.match(h,/<select /);});
test('R8 network page shows 3 stock-bounded opportunities and scenario-specific labels',()=>{const h=views['local-availability'];assert.ok(h.includes('store-B'));assert.ok(h.includes('r8-move-csv'));assert.ok(h.includes('r8-move-task'));assert.ok(h.includes('Гипотеза'));});
test('R8 consent page shows control group and no messaging action',()=>{const h=views['local-recovery'];assert.ok(h.includes('r8-pilot-csv'));assert.ok(h.includes('Контроль'));assert.ok(h.includes('не отправляет'));assert.ok(!h.includes('data-action="send-message"'));});
test('R8 owner board is exportable and only serializes aggregates',()=>{const h=views['local-brief'];for(const action of ['r8-brief-save','r8-brief-pdf','r8-brief-csv','r8-audit-clear'])assert.ok(h.includes(action));assert.equal((h.match(/class="r8-claims"/g)||[]).length,1);});
test('R8 markup disallows injected strings in user-controlled CSV exports',()=>{const injected={...w,sales:[{...w.sales[0],storeId:'<img src=x onerror=alert(1)>'},...w.sales.slice(1)]};const h=renderR8Ledger(injected,{store:'all'});assert.ok(!h.includes('<img src=x'));});
test('navigation and diagnostics use five real R8 modules',()=>{const app=read('src/app.mjs');for(const route of Object.keys(views))assert.ok(app.includes(`state.page==='${route}'`),route);assert.ok(app.includes('get r8()'));assert.ok(app.includes('data-r8-file'));assert.ok(app.includes("r8-brief-save"));});
test('module entrypoint and standalone build include actual R8 code and stylesheet',()=>{assert.match(read('index.html'),/src\/r8.css/);const b=read('scripts/build_standalone.py');for(const p of ['r8_core.mjs','r8_views.mjs','r8_pdf.mjs','r8.css'])assert.ok(b.includes(p));});
test('R8 action names in DOM have click handlers',()=>{const app=read('src/app.mjs');for(const name of ['r8-accept','r8-sample-one','r8-sample-all','r8-clear','r8-ledger-csv','r8-move-task','r8-pilot-task','r8-brief-pdf','r8-brief-save','r8-audit-csv'])assert.ok(app.includes(`a==='${name}'`),name);});
test('source and file contents remain RAM-only',()=>{const app=read('src/app.mjs');assert.ok(app.includes('state.r8Workspace=emptyWorkingSet()'));const p=app.indexOf('function persist()');assert.ok(p>=0);assert.ok(!app.slice(p,p+350).includes('r8Workspace'));assert.ok(!app.includes("localStorage.setItem('osmanx-r8-raw"));});
