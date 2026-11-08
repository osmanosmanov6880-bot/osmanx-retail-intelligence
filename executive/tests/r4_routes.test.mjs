import test from 'node:test';
import assert from 'node:assert/strict';
const listeners={},storage=new Map();
const root={innerHTML:'',addEventListener:(key,fn)=>{listeners[key]=fn;},querySelector:()=>null};
globalThis.document={getElementById:()=>root,title:'',activeElement:null};
globalThis.window={scrollTo:()=>{}};
globalThis.localStorage={getItem:(k)=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)};
await import('../src/app.mjs');
const diagnostics=window.__OSMANX_DIAGNOSTICS__;
function click(values){listeners.click({target:{closest:()=>({dataset:values,disabled:false,title:''})}});}
function enter(field,value){const target={dataset:{r4Field:field},tagName:'INPUT',value,matches:(query)=>query==='[data-r4-field]'};listeners.input({target});}

test('R4/01 all five full interactive route screens render distinct content',()=>{
 for(const [path,word] of [['trust-lab','SIGNAL QUALITY'],['demand-match','DEMAND MATCHING'],['margin-stress','MARGIN DEFENCE'],['portfolio','EXECUTION PRIORITIES'],['dossier','DECISION DOSSIER']]){
  diagnostics.navigate(path);assert.match(root.innerHTML,new RegExp(word));
  assert.match(root.innerHTML,/ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ/);
 }
});
test('R4/02 dashboard links to each new decision workflow',()=>{
 diagnostics.navigate('dashboard');
 for(const page of ['trust-lab','demand-match','margin-stress','portfolio','dossier'])assert.ok(root.innerHTML.includes(`data-page="${page}"`));
});
test('R4/03 trust audit can drill into request stream',()=>{
 diagnostics.navigate('trust-lab');click({action:'r4-audit-stream',value:'requests'});
 assert.match(root.innerHTML,/Запросы покупателей|Невидимый спрос/);
 assert.ok(root.innerHTML.includes('r4-source active'));
 assert.equal(diagnostics.r4.audit,0);
});
test('R4/04 stock buffer scenarios rerender immediately and remain editable on invalid input',()=>{
 diagnostics.navigate('demand-match');
 const before=diagnostics.r4.match.matched;
 enter('reserve','1');const after=diagnostics.r4.match.matched;
 assert.ok(after<=before);
 enter('reserve','-1');assert.match(root.innerHTML,/Резерв должен быть/);
 assert.match(root.innerHTML,/data-r4-field="reserve"/);
 enter('reserve','0');assert.equal(diagnostics.r4.match.matched,before);
});
test('R4/05 store allocation opens a request, saves a traceable journal entry',()=>{
 diagnostics.navigate('demand-match');
 const match=diagnostics.r4.match;assert.ok(match.remote>0);
 const m=root.innerHTML.match(/data-action="r4-match-journal" data-id="([^"]+)"/);assert.ok(m);
 const before=diagnostics.journal.all;
 click({action:'r4-match-journal',id:m[1]});
 assert.equal(diagnostics.state.page,'journal');assert.equal(diagnostics.journal.all,before+1);
 assert.ok(storage.get('osmanx-executive-r1').includes('r4-matching'));
});
test('R4/06 margin controls change scenario but not observed receipts',()=>{
 diagnostics.navigate('margin-stress');
 const old=diagnostics.r4.margin;
 enter('discount','40');
 assert.ok(diagnostics.r4.margin<old);
 assert.match(root.innerHTML,/Изменение · гипотеза/);
});
test('R4/07 portfolio capacity and budget constrain shortlist; input updates are reactive',()=>{
 diagnostics.navigate('portfolio');
 enter('capacity','1');assert.ok(diagnostics.r4.portfolio.length<=1);
 enter('budget','0');assert.equal(diagnostics.r4.portfolio.length,0);
 enter('budget','15000');enter('capacity','3');
 assert.ok(diagnostics.r4.portfolio.length<=3);
});
test('R4/08 a priority is actionable but only creates a pilot journal item',()=>{
 diagnostics.navigate('portfolio');
 const match=root.innerHTML.match(/data-action="r4-portfolio-journal" data-id="([^"]+)"/);assert.ok(match);
 const before=diagnostics.journal.all;
 click({action:'r4-portfolio-journal',id:match[1]});
 assert.equal(diagnostics.state.page,'journal');assert.equal(diagnostics.journal.all,before+1);
});
test('R4/09 dossier reflects current scenario and retained journal, not fabricated integrations',()=>{
 diagnostics.navigate('dossier');assert.match(root.innerHTML,/ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ/);
 assert.match(root.innerHTML,/Скачать PDF/);assert.match(root.innerHTML,/не выполнена/);
 assert.equal(diagnostics.journal.all,2);
});
