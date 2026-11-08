const root=document.querySelector('#help-root');
const path=location.pathname.match(/^\/assist\/([A-Za-z0-9_-]{20,150})$/);
const token=path?.[1];
let requestId=crypto.randomUUID?.()||`assist-${Date.now()}-${Math.random().toString(36).slice(2)}`;
let submitted=false;
const escapeHTML=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
if(!token){root.innerHTML='<div class="help-success"><h2>Ссылка недействительна</h2><p>Попросите актуальный QR-код у сотрудника.</p></div>'}
root.addEventListener('click',async e=>{
 const button=e.target.closest('[data-category]');if(!button||submitted||!token)return;
 submitted=true;document.querySelectorAll('[data-category]').forEach(b=>b.disabled=true);
 try{
  const response=await fetch('/api/assist/'+encodeURIComponent(token),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({category:button.dataset.category,request_id:requestId}),cache:'no-store'});
  const data=await response.json().catch(()=>({detail:'Неожиданный ответ сервера'}));
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Вызов не отправлен');
  root.innerHTML='<div class="help-success"><h2>Сотрудник получил вызов</h2><p>Оставайтесь в магазине. Если ожидание затянулось, обратитесь к персоналу напрямую.</p></div>';
 }catch(error){
  submitted=false;
  document.querySelectorAll('[data-category]').forEach(b=>b.disabled=false);
  let notice=document.querySelector('#help-error');if(!notice){notice=document.createElement('p');notice.id='help-error';notice.setAttribute('role','alert');root.append(notice)}
  notice.textContent=escapeHTML(error.message);
 }
});
