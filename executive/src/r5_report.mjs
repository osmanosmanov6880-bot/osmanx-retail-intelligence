/** Executive branch scorecard, rendered entirely on-device. */
import {encodePdf} from './pdf.mjs';
import {AS_OF,MONEY,NUMBER,PERCENT} from './model.mjs';
function drawScorecard(report){
 const canvas=document.createElement('canvas');canvas.width=1240;canvas.height=1754;
 const c=canvas.getContext('2d');if(!c)throw Error('Canvas unavailable');
 const box=(x,y,w,h,fill)=>{c.fillStyle=fill;c.fillRect(x,y,w,h);};
 const text=(value,x,y,size=24,color='#272521',bold=false)=>{c.fillStyle=color;c.font=`${bold?'600':'400'} ${size}px Arial,sans-serif`;c.fillText(String(value),x,y);};
 box(0,0,1240,1754,'#f8f5f0');box(0,0,1240,330,'#181b1e');box(80,74,5,55,'#c4a078');
 text('OSMANX   /   RETAIL INTELLIGENCE',110,115,31,'#f4eadf',true);
 text('ATELIER R5 / BRANCH EVIDENCE',80,175,18,'#d6b990',true);
 c.fillStyle='#f5ebdf';c.font='400 64px Georgia,serif';c.fillText('Три филиала. Один контекст.',80,255);
 text('Демонстрационные данные  |  '+AS_OF,80,304,21,'#ded2c2');
 text('ПОКАЗАТЕЛЬ ДЛЯ СРАВНЕНИЯ',80,421,18,'#a0805e',true);
 text(report.label,80,472,31,'#2d2b28',true);
 report.ranked.forEach((row,i)=>{
  const top=530+i*238;box(80,top,1080,205,i%2===0?'#ebe6de':'#f0ece5');box(80,top,6,205,'#c3a783');
  text('0'+(i+1),105,585,30,'#a0815c');text(row.name,173,585,31,'#302a23',true);
  const value=row.value===null?'Нет измерения':report.metric==='grossProfit'?MONEY(row.value):report.metric==='margin'||report.metric==='conversion'?PERCENT(row.value):NUMBER(row.value)+(report.metric==='serviceP90'?' сек':'');
  text(value,173,650,42,'#3a3027');text(`${row.saleCount} чеков  |  ${row.requests} запросов  |  ${row.returns} возвратов`,173,695,19,'#756c62');
 });
 box(80,1282,1080,238,'#ece4d8');box(80,1282,5,238,'#a58a67');
 text('ЧТО НЕЛЬЗЯ УТВЕРЖДАТЬ ПО ЭТИМ ЦИФРАМ',103,1337,19,'#7a6148',true);
 const cautions=['Разница между филиалами не доказывает эффективность управления.',
  'Учётный чек не описывает все причины отказа от покупки.',
  'Данные синтетические. Интеграции с реальной 1С в демо нет.'];
 cautions.forEach((x,i)=>text('- '+x,103,1391+i*37,19,'#514a42'));
 box(80,1590,1080,1,'#cfc6ba');text('Период: '+report.days+' дней  |  Показатель: '+report.label,80,1634,18,'#7c6b5a');
 text('OSMANX WORLD / DEMO ONLY / NOT PROVEN INCREMENTAL PROFIT',80,1690,17,'#a68f76',true);
 return canvas;
}
export function branchPdfBlob(report){if(!report.valid)throw Error('Неверные параметры сравнения');const c=drawScorecard(report);return encodePdf(c.toDataURL('image/jpeg',.91),c.width,c.height);}
export function exportBranchPdf(report){const blob=branchPdfBlob(report),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`OSMANX_BRANCH_EVIDENCE_${AS_OF}.pdf`;a.click();setTimeout(()=>URL.revokeObjectURL(url),20000);return blob;}
