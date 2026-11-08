/** Offline one-page A4 executive evidence sheet, generated on-device only. */
import {encodePdf} from './pdf.mjs';
import {MONEY,NUMBER} from './model.mjs';
const ff='"Segoe UI",Arial,sans-serif';
const serif='Georgia,serif';
function text(ctx,str,x,y,{color='#302b25',size=22,bold=false,max=1000}={}){
 ctx.fillStyle=color;ctx.font=`${bold?'600':'400'} ${size}px ${ff}`;
 const content=String(str??'');
 if(ctx.measureText(content).width>max){
  let value=content;while(value.length>3&&ctx.measureText(value+'…').width>max)value=value.slice(0,-1);
  ctx.fillText(value+'…',x,y);
 } else ctx.fillText(content,x,y);
}
function rect(ctx,x,y,w,h,fill){ctx.fillStyle=fill;ctx.fillRect(x,y,w,h);}
function rule(ctx,y){rect(ctx,83,y,1070,1,'#d7d0c4');}
function paintDossier(snapshot){
 const canvas=document.createElement('canvas');canvas.width=1240;canvas.height=1754;
 const c=canvas.getContext('2d');if(!c)throw Error('Canvas rendering unavailable');
 rect(c,0,0,1240,1754,'#f8f5ef');rect(c,0,0,1240,337,'#191b1c');
 rect(c,83,77,6,43,'#c3a075');text(c,'OSMANX   /   RETAIL INTELLIGENCE',110,110,{color:'#f5eadd',size:30,bold:true});
 text(c,'ATELIER / DECISION DOSSIER · DEMONSTRATION DATA',83,168,{color:'#c8a77d',size:17,bold:true});
 c.fillStyle='#eee0cc';c.font=`400 66px ${serif}`;c.fillText('Что проверять в вашей сети',83,244);
 text(c,`Синтетический срез · ${snapshot.asOf} · ${snapshot.period.from} — ${snapshot.period.to}`,83,295,{color:'#d7c8b7',size:21});
 text(c,'ФИНАНСОВЫЙ СРЕЗ  /  ФАКТЫ ДЕМО-ЧЕКОВ',83,417,{color:'#8f7150',size:20,bold:true});
 const financial=[['ВЫРУЧКА',MONEY(snapshot.totals.revenue)],['ВАЛОВАЯ ПРИБЫЛЬ',MONEY(snapshot.totals.gross)],
  ['ЧЕКОВ ПО ЗАПРОСАМ',NUMBER(snapshot.totals.relatedReceipts)],['ПРИБЫЛЬ ПО СВЯЗАННЫМ ЧЕКАМ',MONEY(snapshot.totals.relatedReceiptGross)]];
 financial.forEach(([title,value],i)=>{const col=i%2,row=Math.floor(i/2),x=83+col*555,y=456+row*165;
  rect(c,x,y,527,144,'#ece8e1');rect(c,x,y,4,144,'#b6976d');
  text(c,title,x+24,y+36,{color:'#7e7162',size:16,bold:true,max:470});
  c.fillStyle='#22201c';c.font=`400 45px ${serif}`;c.fillText(value,x+24,y+102);
 });
 text(c,'ЧТО ПРОВЕРИТЬ   /   ПРИОРИТЕТЫ ДЛЯ ПИЛОТА',83,845,{color:'#8f7150',size:20,bold:true});
 const priorities=snapshot.priorities.slice(0,3);
 if(!priorities.length)text(c,'Нет рекомендованных пилотов при текущем бюджете.',83,914,{color:'#594d3f',size:22});
 priorities.forEach((p,i)=>{const y=901+i*137;rule(c,y-20);
  c.fillStyle='#ad8862';c.font=`400 34px ${serif}`;c.fillText(`0${i+1}`,83,y+26);
  text(c,p.title,163,y+20,{size:25,bold:true,max:890});
  text(c,`${p.owner}  ·  ${NUMBER(p.observations)} наблюдений  ·  стоимость проверки ${MONEY(p.cost)}`,163,y+57,{size:19,color:'#7d7062',max:890});
  text(c,`ID оснований: ${p.evidenceIds.slice(0,4).join(' · ')||'не указаны'}`,163,y+88,{size:17,color:'#9a8b7b',max:880});
 });
 const warningY=1342;rect(c,83,warningY,1070,204,'#eee7dc');rect(c,83,warningY,5,204,'#ad8d67');
 text(c,'ВАЖНЫЕ ОГРАНИЧЕНИЯ',109,warningY+42,{size:20,bold:true,color:'#7b6042'});
 const warnings=[
  'Демонстрационные данные. Реальная 1С, касса и склады не подключены.',
  'Валовая прибыль по связанным чекам НЕ является доказанным приростом.',
  'Сценарии и сравнения не устанавливают причинность без пилота.'
 ];warnings.forEach((w,i)=>text(c,`•  ${w}`,109,warningY+82+i*32,{size:18,color:'#504c45',max:970}));
 rule(c,1621);
 text(c,`ПРОВЕРКА СВЯЗЕЙ: ${snapshot.quality.errors} ошибок   ·   НАБЛЮДЕНИЙ: ${NUMBER(snapshot.quality.events)}`,83,1661,{size:17,color:'#7d6a57'});
 text(c,'OSMANX WORLD   /   EXECUTIVE INTELLIGENCE  ·  NO REAL CUSTOMER DATA',83,1700,{size:17,color:'#a48f74',bold:true});
 return canvas;
}
export function dossierPdfBlob(snapshot){const canvas=paintDossier(snapshot);return encodePdf(canvas.toDataURL('image/jpeg',.92),canvas.width,canvas.height);}
export function exportDossierPdf(snapshot){
 const blob=dossierPdfBlob(snapshot),url=URL.createObjectURL(blob),a=document.createElement('a');
 a.href=url;a.download=`OSMANX_ATELIER_EVIDENCE_${snapshot.asOf}.pdf`;a.click();
 setTimeout(()=>URL.revokeObjectURL(url),20000);return blob;
}
