/** Client-only R9 PDF. Uses the existing tested PDF writer; no document pixels leave the browser. */
import {encodePdf} from './pdf.mjs';
import {AS_OF} from './model.mjs';
export function buildR9Pdf(pack,{status='requires-check'}={}){
 if(!pack?.valid)throw Error('Нет проверенного отчёта R9');
 if(typeof document==='undefined')throw Error('PDF доступен в браузере');
 const canvas=document.createElement('canvas');canvas.width=1240;canvas.height=1754;
 const c=canvas.getContext('2d');if(!c)throw Error('Невозможно создать отчёт');
 c.fillStyle='#f9f7f2';c.fillRect(0,0,1240,1754);c.fillStyle='#111923';c.fillRect(0,0,1240,335);
 c.fillStyle='#bba07c';c.fillRect(84,72,5,51);
 c.fillStyle='#f4f0e6';c.font='bold 29px Arial,sans-serif';c.fillText('OSMANX  /  RETAIL INTELLIGENCE',113,104);
 c.fillStyle='#cbb493';c.font='17px Arial,sans-serif';c.fillText('ATELIER R9   /   CFO RECONCILIATION',85,164);
 c.fillStyle='#faf5eb';c.font='48px Arial,sans-serif';c.fillText('Платежи и подтверждения',85,245);
 c.fillStyle='#a8b2bf';c.font='17px Arial,sans-serif';c.fillText('Дата: '+AS_OF+'   ·   '+(pack.example?'УЧЕБНЫЕ CSV':'ЛОКАЛЬНЫЕ CSV (ИСТОЧНИК НЕ ПРОВЕРЕН)'),85,301);
 let y=385;
 for(let i=0;i<pack.claims.length;i++){
  const item=pack.claims[i];c.fillStyle=i%2?'#f4f0ea':'#ece7de';c.fillRect(80,y-30,1080,152);
  c.fillStyle='#b29b7a';c.fillRect(80,y-30,4,152);
  c.fillStyle='#715c44';c.font='bold 14px Arial,sans-serif';c.fillText(String(i+1).padStart(2,'0')+'  /  '+item.kind,103,y);
  c.fillStyle='#1d2430';c.font='23px Arial,sans-serif';c.fillText(item.label.slice(0,64),103,y+34);
  c.font='bold 27px Arial,sans-serif';const value=typeof item.value==='number'?item.value.toLocaleString('ru-RU',{maximumFractionDigits:2}):'—';c.fillText(value+(i===5?'':' ₽'),103,y+74);
  c.fillStyle='#646a70';c.font='15px Arial,sans-serif';c.fillText(item.method.slice(0,100),103,y+101);
  y+=172;
 }
 c.fillStyle='#161c24';c.font='bold 21px Arial,sans-serif';c.fillText('РЕШЕНИЕ И ГРАНИЦЫ ПОДТВЕРЖДЕНИЯ',82,1454);
 c.fillStyle='#61666c';c.font='17px Arial,sans-serif';
 const notes=[`Статус собственника: ${status}`,`Расхождений: ${pack.cases.total}, закрыто по протоколу: ${pack.cases.closed}.`,
  'Выгрузки пользователя не прошли независимую проверку подлинности.',
  'Отсутствующая строка выписки не означает доказанную недостачу.',
  'Комиссии и документы не доказывают дополнительную прибыль.'];
 notes.forEach((s,i)=>c.fillText(s.slice(0,115),85,1496+i*33));
 c.fillStyle='#c4a77c';c.fillRect(80,1702,1080,1);c.fillStyle='#686d71';c.font='14px Arial,sans-serif';c.fillText('OSMANX WORLD · LOCAL ONLY · USER-SUPPLIED SOURCES · NOT AN EXTERNAL FINANCIAL AUDIT',85,1735);
 return encodePdf(canvas.toDataURL('image/jpeg',.87),canvas.width,canvas.height);
}
export function exportR9Pdf(pack,opts){const blob=buildR9Pdf(pack,opts),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='OSMANX_R9_CFO_RECONCILIATION.pdf';link.click();setTimeout(()=>URL.revokeObjectURL(url),12000);return blob;}
