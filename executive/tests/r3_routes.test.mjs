import test from 'node:test';
import assert from 'node:assert/strict';
const listeners={};const storage=new Map();
const root={innerHTML:'',addEventListener:(k,fn)=>listeners[k]=fn,querySelector:()=>null};
globalThis.document={getElementById:()=>root,title:'',activeElement:null};
globalThis.window={scrollTo:()=>{}};
globalThis.localStorage={getItem:(k)=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)};
await import('../src/app.mjs');
const state=window.__OSMANX_DIAGNOSTICS__;
function click(ds){listeners.click({target:{closest:()=>({dataset:ds,disabled:false,title:''})}});}
function change(ds,value){listeners.change({target:{matches:(selector)=>{if(selector==='[data-r3-transfer]')return 'r3Transfer' in ds;if(selector==='[data-r3-pilot]')return 'r3Pilot' in ds;if(selector==='[data-r3-measure]')return 'r3Measure' in ds;return false;},dataset:ds,value}});}

test('ATELIER R3 / all decision labs have complete, visible screens and no fake integrations',()=>{
 for(const page of ['evidence','transfer-lab','pilot-lab','journal']){
  state.navigate(page);
  assert.match(root.innerHTML,/ATELIER \/ DECISION LAB/);
  assert.match(root.innerHTML,/ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ/);
  assert.match(root.innerHTML,/OSMANX/);
 }
});
test('ATELIER R3 / finance evidence has transparent ledger and amount from linked receipts',()=>{
 state.navigate('evidence');assert.match(root.innerHTML,/От цифры/);assert.match(root.innerHTML,/РЕЕСТР СОБЫТИЙ/);
 assert.match(root.innerHTML,/28\s*000/);assert.equal(state.reconciliation.issues.length,0);
});
test('ATELIER R3 / planner rejects over-allocation, then validates 3 units and creates a local-only record',()=>{
 state.navigate('transfer-lab');
 change({r3Transfer:'units'},4);click({action:'r3-transfer-check'});
 assert.match(root.innerHTML,/Решение невозможно/);
 change({r3Transfer:'units'},3);click({action:'r3-transfer-check'});
 assert.match(root.innerHTML,/5\s*550/);
 const before=state.journal.all;
 click({action:'r3-transfer-save'});
 assert.equal(state.state.page,'journal');assert.equal(state.journal.all,before+1);
 assert.match(root.innerHTML,/Проверить перемещение/);
 assert.ok(storage.has('osmanx-executive-r1'));
});
test('ATELIER R3 / journal workflow guards invalid measurements and never claims proven uplift',()=>{
 state.navigate('journal');
 click({action:'r3-journal-progress',id:'PILOT-001'});
 assert.match(root.innerHTML,/РЕЗУЛЬТАТ|ВОПРОС|К проверке|Покупок до/);
 click({action:'r3-journal-measure',id:'PILOT-001'});
 assert.match(root.innerHTML,/нужны корректные показатели/);
 for(const [k,v] of [['before','4'],['after','6'],['sample','10'],['expenses','500']])change({r3Measure:k},v);
 click({action:'r3-journal-measure',id:'PILOT-001'});
 assert.match(root.innerHTML,/без контрольной группы/i);
 assert.equal(state.journal.measured,1);
 click({action:'r3-journal-close',id:'PILOT-001'});
 assert.match(root.innerHTML,/Закрыто/);
});
test('ATELIER R3 / pilot comparing manually entered controls remains explicitly non-causal',()=>{
 state.navigate('pilot-lab');
 assert.match(root.innerHTML,/Недостаточно данных для финансового вывода/);
 change({r3Pilot:'controlRequests'},'60');
 change({r3Pilot:'controlPurchases'},'4');
 assert.match(root.innerHTML,/Сравнение описательное/);
 assert.match(root.innerHTML,/95% интервал неопределённости/);
 click({action:'r3-pilot-save'});
 assert.equal(state.state.page,'journal');assert.equal(state.journal.all,2);
});
test('ATELIER R3 / dashboard links to decision labs without exposing navigation drawer',()=>{
 state.navigate('dashboard');
 for(const route of ['evidence','transfer-lab','pilot-lab','journal'])assert.match(root.innerHTML,new RegExp(`data-page="${route}"`));
 assert.match(root.innerHTML,/aria-hidden="true"/);
});
