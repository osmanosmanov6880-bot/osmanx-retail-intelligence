import test from 'node:test';
import assert from 'node:assert/strict';
const callbacks={};
const root={innerHTML:'',addEventListener:(kind,fn)=>callbacks[kind]=fn,querySelector:()=>null};
globalThis.document={getElementById:()=>root,title:'',activeElement:null};
globalThis.window={scrollTo:()=>{}};
globalThis.localStorage={getItem:()=>null,setItem:()=>{}};
await import('../src/app.mjs');
function action(d={}){callbacks.click({target:{closest:()=>({dataset:d,disabled:false,title:''})}});}
function change(field,value){callbacks.change({target:{matches:()=>true,dataset:{field},value}});}
function input(key,value){callbacks.input({target:{matches:()=>true,dataset:{calc:key},value}});}
const diagnostics=window.__OSMANX_DIAGNOSTICS__;

test('dashboard first render offers exact executive promise and visible synthetic label',()=>{
 diagnostics.navigate('dashboard');
 assert.match(root.innerHTML,/Финансовые возможности/);
 assert.match(root.innerHTML,/Некоторые продажи/);
 assert.match(root.innerHTML,/Демонстрационные данные/);
 assert.match(root.innerHTML,/28\s?000/);
 assert.match(root.innerHTML,/Карта возможностей/);
});
test('executive 30-second walkthrough mounts all 5 scenes and manual next actions work',()=>{
 diagnostics.navigate('demo');
 const scenes=['scene-one','scene-two','scene-three','scene-four','scene-five'];
 for(let i=0;i<scenes.length;i++) {
  assert.equal(diagnostics.state.scene,i);
  assert.ok(root.innerHTML.includes(scenes[i]),`${i} active scene`);
  if(i<scenes.length-1)action({action:'next-scene'});
 }
 assert.match(root.innerHTML,/Проверить мой магазин/);
 action({action:'next-scene'});assert.equal(diagnostics.state.scene,0);
});
test('all ten modules include evidence, financial explanation and action; no broken templates',()=>{
 for(let i=0;i<10;i++) {
  diagnostics.navigate('module:'+i);
  assert.match(root.innerHTML,/ANALYTICS \/ MODULE/);
  assert.match(root.innerHTML,/Что показывают наблюдения/);
  assert.match(root.innerHTML,/Решение и измерение/);
  assert.match(root.innerHTML,/Исходные события/);
  assert.match(root.innerHTML,/СИГНАЛ/);
  assert.match(root.innerHTML,/РЕЗУЛЬТАТ/);
 }
});
test('store, category and scenario filters are wired to calculations',()=>{
 diagnostics.navigate('dashboard');
 const initial=diagnostics.totals.revenue;
 change('store','s2');assert.ok(diagnostics.totals.revenue<initial);
 change('category','Куртки');assert.equal(diagnostics.totals.conversion,null);
 change('scenario','shortages');assert.equal(diagnostics.state.scenario,'shortages');
 assert.match(root.innerHTML,/Спрос выше доступности/);
});
test('financial calculator recomputes when user changes a field',()=>{
 diagnostics.navigate('calculator');
 const before=root.innerHTML.match(/Возможная валовая прибыль после пилотных затрат<\/span><strong[^>]*>(.*?)<\/strong>/)?.[1];
 input('stores','6');
 const after=root.innerHTML.match(/Возможная валовая прибыль после пилотных затрат<\/span><strong[^>]*>(.*?)<\/strong>/)?.[1];
 assert.ok(before&&after&&before!==after,{before,after});
});
test('presentation exposes financial disclaimer and route to diagnostic',()=>{
 diagnostics.navigate('presentation');
 action({action:'presentation-panel',value:'effect'});
 assert.match(root.innerHTML,/28 000/);
 assert.match(root.innerHTML,/Не доказано/);
});
test('7-question diagnostic ends in 3 prioritized checks and PDF action',()=>{
 diagnostics.navigate('diagnostic');
 for(let i=0;i<7;i++){
  const q=[['stores','2–3'],['category','Одежда'],['accounting','1С'],['trackSizes','Нет'],['refusal','Нет'],['findAcross','Нет'],['priority','Маржа']][i];
  action({action:'answer',key:q[0],value:q[1]});action({action:'next-q'});
 }
 assert.match(root.innerHTML,/ПЕРВИЧНЫЙ ПЛАН/);
 assert.equal((root.innerHTML.match(/class="plan-line"/g)||[]).length,3);
 assert.match(root.innerHTML,/Скачать отчёт PDF/);
});
test('management actions are stored as plans without fake outcome',()=>{
 diagnostics.navigate('module:0');action({action:'track-decision',decision:'0'});
 assert.match(root.innerHTML,/план проверки/);
});

test('R2 Atelier dashboard is a real interactive cinematic interface rather than a static screenshot',()=>{
 diagnostics.navigate('dashboard');
 assert.match(root.innerHTML,/class="luxury-hero"/);
 assert.match(root.innerHTML,/Вы знаете, сколько/);
 assert.match(root.innerHTML,/А сколько могли\?/);
 assert.match(root.innerHTML,/ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ/);
 assert.match(root.innerHTML,/button class="luxury-primary" data-page="demo"/);
 assert.match(root.innerHTML,/data-page="diagnostic"/);
 assert.match(root.innerHTML,/Карта возможностей/);
});

test('R2 navigation remains hidden until deliberately opened and all sections remain reachable',()=>{
 diagnostics.navigate('dashboard');
 assert.match(root.innerHTML,/aria-hidden="true"/);
 action({action:'toggle-menu'});
 assert.match(root.innerHTML,/class="sidebar is-open"/);
 assert.match(root.innerHTML,/aria-hidden="false"/);
 assert.match(root.innerHTML,/module:9/);
 action({action:'toggle-menu'});
 assert.match(root.innerHTML,/aria-hidden="true"/);
});

test('R2 changing the synthetic scenario changes the executive-demo funnel headline without claiming unchanged sales',()=>{
 diagnostics.navigate('dashboard');
 change('scenario','shortages');
 diagnostics.navigate('demo');
 action({action:'next-scene'});
 const count=Number(root.innerHTML.match(/<h2>(\d+) запросов на размер/)?.[1]);
 assert.ok(count>60,`expected elevated demand: ${count}`);
 assert.match(root.innerHTML,/Валовая прибыль по/);
 assert.match(root.innerHTML,/не доказанная дополнительная прибыль/i);
 change('scenario','balanced');
});

test('R2 finance verification is an auditable scenario, not a fake stock movement',()=>{
 diagnostics.navigate('demo');
 action({action:'scene',value:'3'});
 assert.doesNotMatch(root.innerHTML,/class="verified-scenario"/);
 action({action:'verify-transfer'});
 assert.match(root.innerHTML,/class="verified-scenario"/);
 assert.match(root.innerHTML,/5\s?550/);
 assert.match(root.innerHTML,/не команда складу/);
 change('transferUnits','2');
 assert.doesNotMatch(root.innerHTML,/class="verified-scenario"/);
});
