/** Offline PDF writer: renders Russian text onto an A4 canvas and embeds one JPEG page.
 * No third-party package, no network requests; all answers remain in the browser.
 * This is a single-page executive diagnostic brief, not a factual financial audit.
 */
const font='"Segoe UI",Inter,Arial,sans-serif';
function wrap(ctx,text,x,y,maxWidth,lineHeight,maxLines=8) {
 const words=String(text).split(/\s+/);let line='',lines=0;
 for(const word of words){const maybe=line?line+' '+word:word;if(ctx.measureText(maybe).width>maxWidth&&line){ctx.fillText(line,x,y);y+=lineHeight;lines++;line=word;if(lines>=maxLines)return y;}else line=maybe;}
 if(line){ctx.fillText(line,x,y);y+=lineHeight;}return y;
}
function paint({answers={},plan=[],date}) {
 const canvas=document.createElement('canvas');canvas.width=1240;canvas.height=1754;
 const c=canvas.getContext('2d');if(!c)throw new Error('Canvas unavailable');
 c.fillStyle='#faf7f2';c.fillRect(0,0,1240,1754);
 c.fillStyle='#141518';c.fillRect(0,0,1240,380);
 c.fillStyle='#d8ba8e';c.fillRect(83,75,6,45);
 c.textBaseline='alphabetic';c.fillStyle='#f6efe4';c.font=`700 31px ${font}`;c.fillText('OSMANX  /  RETAIL INTELLIGENCE',110,106);
 c.fillStyle='#e2c8a1';c.font=`700 15px ${font}`;c.fillText('EXECUTIVE DIAGNOSTIC · ИНДИВИДУАЛЬНЫЙ ПЛАН ПРОВЕРКИ',84,158);
 c.fillStyle='#f7f0e6';c.font=`600 53px ${font}`;wrap(c,'Три направления для проверки коммерческих возможностей',84,235,1060,65,3);
 c.fillStyle='#c5b9a9';c.font=`20px ${font}`;c.fillText('Демонстрационная методика · '+date,84,347);
 let y=460;
 c.fillStyle='#26211c';c.font=`700 26px ${font}`;c.fillText('РЕКОМЕНДОВАННЫЕ ШАГИ',84,y);y+=53;
 for(let i=0;i<plan.length;i++){
  const p=plan[i];c.fillStyle='#f0ebe3';c.fillRect(84,y-24,1072,170);c.fillStyle='#bd9469';c.fillRect(84,y-24,5,170);
  c.fillStyle='#a78054';c.font=`700 21px ${font}`;c.fillText(`0${i+1}`,112,y+6);
  c.fillStyle='#33271b';c.font=`700 27px ${font}`;c.fillText(p.title,180,y+6);
  c.fillStyle='#62584c';c.font=`20px ${font}`;wrap(c,p.detail,180,y+49,905,31,3);
  y+=201;
 }
 y+=25;c.fillStyle='#3a3028';c.font=`700 25px ${font}`;c.fillText('ОТВЕТЫ НА ДИАГНОСТИКУ',84,y);y+=35;
 const labels={'stores':'Магазины','category':'Основная категория','accounting':'Система учёта','trackSizes':'Учёт отсутствующих размеров','refusal':'Причины отказов','findAcross':'Доступность соседних филиалов','priority':'Приоритет'};
 for(const [key,label] of Object.entries(labels)){
  c.fillStyle='#887d70';c.font=`19px ${font}`;c.fillText(label,84,y);
  c.fillStyle='#392c23';c.font=`600 20px ${font}`;c.fillText(String(answers[key]||'Не отвечено'),620,y);y+=48;
 }
 c.fillStyle='#a28f79';c.fillRect(84,1620,1070,1);
 c.fillStyle='#706b65';c.font=`18px ${font}`;wrap(c,'Это план измерения, а не диагноз и не прогноз прибыли. До внедрения необходимы проверка источников, пилот, контрольная группа и согласование обработки данных.',84,1666,1045,28,3);
 c.fillStyle='#bea17d';c.font=`700 14px ${font}`;c.fillText('OSMANX WORLD  ·  DEMONSTRATION DATA',84,1720);
 return canvas;
}
function encodePdf(jpegData,w,h){
 const decoder=atob(jpegData.split(',')[1]);const jpg=new Uint8Array(decoder.length);for(let i=0;i<decoder.length;i++)jpg[i]=decoder.charCodeAt(i);
 const encoder=new TextEncoder();const chunks=[];let length=0;const offsets=[0];
 const append=part=>{const bytes=typeof part==='string'?encoder.encode(part):part;chunks.push(bytes);length+=bytes.length;};
 const object=(id,body)=>{offsets[id]=length;append(`${id} 0 obj\n${body}\nendobj\n`);};
 append('%PDF-1.4\n%PDF generated offline by OSMANX\n');
 object(1,'<< /Type /Catalog /Pages 2 0 R >>');
 object(2,'<< /Type /Pages /Kids [3 0 R] /Count 1 >>');
 object(3,'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /ProcSet [/PDF /ImageC] /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>');
 offsets[4]=length;append(`4 0 obj\n<< /Type /XObject /Subtype /Image /Width ${w} /Height ${h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpg.length} >>\nstream\n`);append(jpg);append('\nendstream\nendobj\n');
 const content='q\n595 0 0 842 0 0 cm\n/Im0 Do\nQ\n';
 object(5,`<< /Length ${encoder.encode(content).length} >>\nstream\n${content}endstream`);
 const xref=length;append('xref\n0 6\n0000000000 65535 f \n');for(let i=1;i<=5;i++)append(String(offsets[i]).padStart(10,'0')+' 00000 n \n');
 append(`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`);
 const out=new Uint8Array(length);let cursor=0;for(const c of chunks){out.set(c,cursor);cursor+=c.length;}return new Blob([out],{type:'application/pdf'});
}
export function exportPdf(info){const canvas=paint(info);const blob=encodePdf(canvas.toDataURL('image/jpeg',.92),canvas.width,canvas.height);const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='OSMANX_Retail_Executive_Diagnostic.pdf';a.click();setTimeout(()=>URL.revokeObjectURL(url),20000);return blob;}
