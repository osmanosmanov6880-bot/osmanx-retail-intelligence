/** ATELIER R10: local-only operational intelligence on accepted R8 data.
 * Deterministic outputs; never writes raw observations, sends messages or claims causal lift.
 */
import {inspectWorkingSet,r8Csv} from './r8_core.mjs';
import {AS_OF} from './model.mjs';
const r10_sum=(arr,fn)=>arr.reduce((a,x)=>a+fn(x),0);
const r10_round=x=>Math.round((x+Number.EPSILON)*100)/100;
const r10_unique=arr=>[...new Set(arr)].sort();
const r10_validNumber=(x,min,max)=>typeof x==='number'&&Number.isFinite(x)&&x>=min&&x<=max;
const r10_working=ws=>{const result=inspectWorkingSet(ws);return {result,valid:result.valid};};
const r10_stockKey=x=>`${x.storeId}|${x.sku}|${x.size}`;
const r10_skuKey=x=>`${x.sku}|${x.size}`;
const r10_sortRows=rows=>rows.sort((a,b)=>a.key.localeCompare(b.key));
// 1. Local provenance: non-cryptographic deterministic fingerprint, not a security signature.
export function r10SourceManifest(ws){
 const {result}=r10_working(ws);const kinds=['sales','returns','requests','stock'];
 const columns=kinds.map(kind=>{const rows=Array.isArray(ws?.[kind])?ws[kind]:[];const dates=rows.map(r=>r.date||r.asOf).sort();return {kind,rows:rows.length,earliest:dates[0]||null,latest:dates.at(-1)||null,origin:ws?.origin?.[kind]||'missing'};});
 const canonical=kinds.map(k=>JSON.stringify((ws?.[k]||[]).map(x=>Object.keys(x).sort().map(key=>[key,x[key]])).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b))))).join('|');
 let hash=2166136261;for(const ch of canonical)hash=Math.imul(hash^ch.charCodeAt(0),16777619)>>>0;
 return {valid:result.valid,issues:result.errors,source:result.source,version:ws?.version||0,rows:columns,token:`R10-${hash.toString(16).padStart(8,'0')}`,total:r10_sum(columns,x=>x.rows),warning:'Отпечаток фиксирует локальную версию набора; не является криптографической подписью или подтверждением подлинности POS.'};
}
// 2. Observed demand conversion, no invented customer identities or incremental lift.
export function r10DemandFunnel(ws,{store='all'}={}){
 const {result}=r10_working(ws);if(!result.valid)return {valid:false,errors:result.errors,rows:[]};
 const requests=(ws.requests||[]).filter(x=>store==='all'||x.storeId===store);
 const saleById=new Map((ws.sales||[]).map(x=>[x.id,x]));
 const returnsBySale=new Map();for(const r of ws.returns||[]){returnsBySale.set(r.saleId,(returnsBySale.get(r.saleId)||0)+r.units);}
 const keys=r10_unique(requests.map(x=>r10_skuKey(x)));
 const rows=keys.map(key=>{const q=requests.filter(x=>r10_skuKey(x)===key),linked=q.filter(x=>x.linkedSaleId&&saleById.has(x.linkedSaleId)),consented=q.filter(x=>x.consent),unlinked=q.filter(x=>!x.linkedSaleId),returned=linked.filter(x=>returnsBySale.get(x.linkedSaleId)>0);
 return {key,requests:q.length,consented:consented.length,linked:linked.length,unlinked:unlinked.length,returned:returned.length,observedRate:q.length?r10_round(linked.length/q.length*100):null};});
 return {valid:true,rows:r10_sortRows(rows),total:{requests:requests.length,consented:r10_sum(rows,x=>x.consented),linked:r10_sum(rows,x=>x.linked),unlinked:r10_sum(rows,x=>x.unlinked),returned:r10_sum(rows,x=>x.returned)},warning:'Связанный чек — факт наблюдения, но не доказательство, что покупка вызвана уведомлением.'};
}
// 3. SKU margin contribution: gross after documented returns only. No profit extrapolation.
export function r10SkuEconomics(ws,{store='all',minUnits=1}={}){
 const {result}=r10_working(ws);if(!result.valid)return {valid:false,errors:result.errors,rows:[]};
 if(!r10_validNumber(minUnits,1,1000000)||!Number.isInteger(minUnits))return {valid:false,errors:['Минимум единиц должен быть целым числом >= 1'],rows:[]};
 const sales=(ws.sales||[]).filter(x=>store==='all'||x.storeId===store),idSale=new Map(sales.map(x=>[x.id,x]));const returns=(ws.returns||[]).filter(x=>idSale.has(x.saleId));
 const keys=r10_unique(sales.map(x=>r10_skuKey(x)));
 const rows=keys.map(key=>{const ss=sales.filter(x=>r10_skuKey(x)===key),saleIds=new Set(ss.map(x=>x.id)),rr=returns.filter(x=>saleIds.has(x.saleId));const units=r10_sum(ss,x=>x.units)-r10_sum(rr,x=>x.units),revenue=r10_round(r10_sum(ss,x=>x.revenue)-r10_sum(rr,x=>x.refund)),cost=r10_round(r10_sum(ss,x=>x.cost)-r10_sum(rr,x=>x.restoredCost));return {key,units,revenue,cost,gross:r10_round(revenue-cost),marginPct:revenue>0?r10_round((revenue-cost)/revenue*100):null,saleIds:ss.length,returns:rr.length};}).filter(x=>x.units>=minUnits).sort((a,b)=>b.gross-a.gross||a.key.localeCompare(b.key));
 const gross=r10_sum(rows,x=>x.gross);return {valid:true,rows:rows.map((x,i)=>({...x,contributionPct:gross>0?r10_round(x.gross/gross*100):null,rank:i+1})),gross:r10_round(gross),warning:'Показываются только позиции с указанным минимумом чисто проданных единиц; итог не равен обороту всей сети при фильтрации.'};
}
// 4. Coverage matrix from explicitly present CURRENT stock snapshots only.
export function r10CoverageMatrix(ws,{asOf=AS_OF,reserve=0}={}){
 const {result}=r10_working(ws);if(!result.valid)return {valid:false,errors:result.errors,rows:[]};
 if(!Number.isSafeInteger(reserve)||reserve<0||reserve>10000)return {valid:false,errors:['Резерв должен быть целым числом от 0 до 10000'],rows:[]};
 const stock=ws.stock||[],requests=ws.requests||[];
 const keys=r10_unique([...stock.map(x=>r10_stockKey(x)),...requests.map(x=>r10_stockKey(x))]);
 const rows=keys.map(key=>{const s=stock.find(x=>r10_stockKey(x)===key),q=requests.filter(x=>r10_stockKey(x)===key&&!x.linkedSaleId);const current=Boolean(s&&s.asOf===asOf);const usable=current?Math.max(0,s.quantity-reserve):null;
 return {key,unlinkedRequests:q.length,consented:q.filter(x=>x.consent).length,quantity:s?.quantity??null,snapshot:s?.asOf||null,current,available:usable,shortage:current?Math.max(0,q.length-usable):null,status:!s?'нет снимка':!current?'устаревший снимок':q.length>usable?'дефицит':'покрыт'};});
 return {valid:true,rows:r10_sortRows(rows),current:rows.filter(x=>x.current).length,unknown:rows.filter(x=>!x.current).length,warning:'Отсутствующий остаток — неизвестно, а не ноль. Прошлые обращения не подтверждают исторический остаток.'};
}
// 5. Decision packet: aggregate, local, explicit evidence status, export with no raw IDs.
export function r10DecisionPacket(ws,{store='all',reserve=0,minUnits=1}={}){
 const manifest=r10SourceManifest(ws),demand=r10DemandFunnel(ws,{store}),economics=r10SkuEconomics(ws,{store,minUnits}),coverage=r10CoverageMatrix(ws,{reserve});
 const valid=manifest.valid&&demand.valid&&economics.valid&&coverage.valid;
 const indicators=[{label:'Принятых строк',value:manifest.total,kind:'факт CSV'}, {label:'Обращений',value:demand.total?.requests??null,kind:'факт CSV'}, {label:'Связанных чеков',value:demand.total?.linked??null,kind:'факт CSV'}, {label:'Валовая прибыль выбранных SKU',value:economics.gross??null,kind:'расчёт по CSV'}, {label:'Позиций с неизвестным остатком',value:coverage.unknown??null,kind:'ограничение доказательств'}];
 const recommendations=[];
 if(valid&&coverage.rows.some(x=>x.status==='дефицит'))recommendations.push('Проверить физическую доступность дефицитных размеров и отдельно зафиксировать факт перемещения.');
 if(valid&&coverage.unknown)recommendations.push('Получить актуальный снимок остатков перед решением о резерве.');
 if(valid&&demand.total.unlinked)recommendations.push('Проверить причины отсутствия связанных чеков, не называя их потерянной выручкой.');
 if(valid&&!recommendations.length)recommendations.push('Проверить исходные данные с POS перед операционным запуском.');
 return {valid,issues:manifest.issues,manifest,demand,economics,coverage,indicators,recommendations,source:manifest.source,warning:'Этот отчёт — локальная аналитика, без фактических поручений сотрудникам, без отправки сообщений и без причинных выводов.'};
}
export function r10PacketCsv(packet){return r8Csv([['Метрика','Значение','Статус'],...packet.indicators.map(x=>[x.label,x.value==null?'неизвестно':x.value,x.kind]),['Отпечаток',packet.manifest.token,'локальный, некриптографический'],['Источник',packet.source,'не подтверждено POS']]);}
