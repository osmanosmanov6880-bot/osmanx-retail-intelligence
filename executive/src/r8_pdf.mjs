/** Browser-only one-page A4 report with embedded JPEG, no external service. */
import {encodePdf} from './pdf.mjs';
import {MONEY,NUMBER,AS_OF} from './model.mjs';
export function buildR8BriefPdf(brief,{date=AS_OF,status='needs-review'}={}){
 if(!brief?.valid)throw Error('Нельзя экспортировать непроверенный набор');
 if(typeof document==='undefined')throw Error('Для PDF необходим браузер');
 const canvas=document.createElement('canvas');canvas.width=1240;canvas.height=1754;const c=canvas.getContext('2d');if(!c)throw Error('Canvas недоступен');
 c.fillStyle='#faf8f4';c.fillRect(0,0,1240,1754);
 c.fillStyle='#0c101a';c.fillRect(0,0,1240,360);
 c.fillStyle='#bd9d71';c.fillRect(78,74,5,42);
 c.fillStyle='#f4eee3';c.font='700 30px Arial,sans-serif';c.fillText('OSMANX / RETAIL INTELLIGENCE',112,106);
 c.fillStyle='#c8ac8a';c.font='700 15px Arial,sans-serif';c.fillText('ATELIER R8   ·   VERIFIED LOCAL CSV WORKSPACE',80,167);
 c.fillStyle='#f3ebdd';c.font='500 51px Arial,sans-serif';c.fillText('Досье собственника',80,252);
 c.fillStyle='#c0bbb2';c.font='18px Arial,sans-serif';c.fillText('Дата формирования: '+date+'    |    '+(brief.example?'УЧЕБНЫЙ НАБОР CSV':'ЛОКАЛЬНЫЙ НАБОР CSV'),80,311);
 const statusLabel={'needs-review':'Требуется проверка источников','reviewed':'Проверено управляющим; требуется пилот','rejected':'Решение отклонено'}[status]||'Не определено';
 let y=414;c.fillStyle='#4b4e51';c.font='700 18px Arial,sans-serif';c.fillText('СТАТУС: '+statusLabel.toUpperCase(),80,y);y+=65;
 for(let i=0;i<brief.claims.length;i++){
  const row=brief.claims[i];c.fillStyle=i%2===0?'#f1ece4':'#faf8f4';c.fillRect(75,y-33,1090,172);
  c.fillStyle='#b08e64';c.fillRect(75,y-33,4,172);
  c.fillStyle='#78644d';c.font='600 17px Arial,sans-serif';c.fillText(String(i+1).padStart(2,'0')+' / '+row.status,100,y+3);
  c.fillStyle='#161b21';c.font='600 25px Arial,sans-serif';c.fillText(row.label,100,y+43);
  c.fillStyle='#2b3036';c.font='600 29px Arial,sans-serif';c.fillText(row.value==null?'Нет данных':(i===1||i===2||i===4?MONEY(row.value):NUMBER(row.value)),100,y+84);
  c.fillStyle='#6e7277';c.font='18px Arial,sans-serif';c.fillText(row.method.slice(0,105),100,y+120);
  y+=197;
 }
 c.fillStyle='#131821';c.font='700 22px Arial,sans-serif';c.fillText('ГРАНИЦЫ ДОСТОВЕРНОСТИ',80,y+3);
 c.fillStyle='#62666e';c.font='18px Arial,sans-serif';
 const foot=['Источник — загруженные локальные CSV, не сверенные автоматически с 1С/POS.',
 'Сценарные расчёты не подтверждают дополнительную прибыль.',
 'Покупателям не отправляются сообщения, складские операции не выполняются.',
 'Сырые строки не передаются на сервер и не включаются в этот отчёт.'];
 foot.forEach((line,i)=>c.fillText(line,80,y+43+i*32));
 c.fillStyle='#ae8d65';c.fillRect(80,1689,1080,1);
 c.fillStyle='#635f5a';c.font='16px Arial,sans-serif';c.fillText('OSMANX WORLD  ·  OFFLINE / LOCAL OBSERVATIONS / NOT A FINANCIAL AUDIT',80,1721);
 return encodePdf(canvas.toDataURL('image/jpeg',.9),canvas.width,canvas.height);
}
export function exportR8BriefPdf(brief,options){const blob=buildR8BriefPdf(brief,options);const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download='OSMANX_R8_LOCAL_EVIDENCE_BRIEF.pdf';a.click();setTimeout(()=>URL.revokeObjectURL(u),20000);return blob;}
