/** Single-page, locally generated Russian A4 PDF of R7 sourced statements. */
import {encodePdf} from './pdf.mjs';
import {MONEY} from './model.mjs';
const r7_font='Arial,"Segoe UI",sans-serif';
function r7_paint(brief){
 if(!brief?.valid||!Array.isArray(brief.statements)||brief.statements.length!==5)throw Error('Отчёт содержит непроверенные разделы');
 const c=document.createElement('canvas');c.width=1240;c.height=1754;
 const x=c.getContext('2d');if(!x)throw Error('Canvas недоступен');
 const rect=(a,b,w,h,col)=>{x.fillStyle=col;x.fillRect(a,b,w,h);};
 const txt=(s,a,b,px=20,col='#2b2928',bold=false)=>{x.fillStyle=col;x.font=`${bold?600:400} ${px}px ${r7_font}`;x.fillText(String(s??''),a,b);};
 const wrap=(value,a,b,maxWidth,px=20,col='#5b5651',line=27,max=2)=>{
  x.fillStyle=col;x.font=`400 ${px}px ${r7_font}`;
  const words=String(value).split(/\s+/);let cur='',count=0;
  for(const w of words){const next=cur?cur+' '+w:w;if(x.measureText(next).width>maxWidth&&cur){x.fillText(cur,a,b);count++;if(count===max)return b;b+=line;cur=w;}else cur=next;}
  if(cur)x.fillText(cur,a,b);return b+line;
 };
 rect(0,0,1240,1754,'#f8f6f2');rect(0,0,1240,360,'#151a21');rect(80,73,6,57,'#c8a980');
 txt('OSMANX / RETAIL INTELLIGENCE',108,113,31,'#f4ece3',true);txt('ATELIER R7 · EVIDENCE BRIEF',83,172,18,'#ccae84',true);
 txt('Финансовые выводы',82,249,56,'#efe4d7',true);txt('Только с проверяемыми источниками',83,293,23,'#dccfc0');
 txt('ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ · '+brief.asOf,83,334,16,'#c0b3a5',true);
 txt('СВОДКА НА ВЫБРАННЫЙ ПЕРИОД',83,416,20,'#987954',true);
 txt(brief.period.from+' — '+brief.period.to+'    /    Сценарий: '+brief.scenario,83,454,20,'#3d352e');
 for(let i=0;i<brief.statements.length;i++){
  const row=brief.statements[i],y=493+i*179;
  rect(83,y,1072,160,i%2===0?'#ebe7e0':'#f0ede8');rect(83,y,5,160,'#c5a47e');
  txt('0'+(i+1),105,y+33,17,'#9f805a',true);
  txt(row.label,160,y+33,23,'#252725',true);
  txt(row.epistemic,930,y+32,15,'#846d4f',true);
  txt(MONEY(row.value),159,y+85,39,'#2c2c2b',true);
  wrap(row.method,160,y+112,950,16,'#615d55',20,1);
  wrap('Основания: '+(row.evidenceIds.slice(0,3).join(', ')||'без индивидуальных ID'),160,y+143,940,13,'#847e76',17,1);
 }
 txt('ПЕРЕД РЕАЛЬНЫМ ВНЕДРЕНИЕМ',83,1445,20,'#987954',true);
 for(let i=0;i<brief.nextActions.length;i++)wrap((i+1)+'. '+brief.nextActions[i],95,1490+i*58,1040,19,'#383432',25,2);
 rect(83,1660,1072,1,'#d0c8bd');
 txt('НЕ ФИНАНСОВАЯ ГАРАНТИЯ · НЕТ ПОДКЛЮЧЕНИЯ 1С · ТОЛЬКО СИНТЕТИКА',83,1702,15,'#99846e',true);
 txt('OSMANX WORLD · CONFIDENTIAL-STYLE DEMONSTRATION',83,1731,12,'#ad9a86');
 return c;
}
export function briefPdfBlob(brief){const canvas=r7_paint(brief);return encodePdf(canvas.toDataURL('image/jpeg',.9),canvas.width,canvas.height);}
export function exportR7BriefPdf(brief){const blob=briefPdfBlob(brief),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='OSMANX_R7_EXECUTIVE_EVIDENCE.pdf';link.click();setTimeout(()=>URL.revokeObjectURL(url),15000);return blob;}
