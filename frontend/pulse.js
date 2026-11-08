/* Paired in-store terminal: anonymous one-tap pulse, no contact information. */
const root=document.querySelector('#pulse-root');
const esc=x=>String(x??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const slug=new URLSearchParams(location.search).get('store')||'central';
const fragment=new URLSearchParams(location.hash.slice(1));
let token=fragment.get('token')||fragment.get('access')||sessionStorage.getItem(`osmanx_pulse_token_${slug}`)||'';
if(fragment.has('token')||fragment.has('access')){sessionStorage.setItem(`osmanx_pulse_token_${slug}`,token);history.replaceState(null,'',location.pathname+location.search)}
let campaign=null;let sending=false;
const brand=()=>`<div class="pulse-top"><div><div class="pulse-brand">OSMAN<span>X</span></div><p class="pulse-store">RETAIL EXPERIENCE</p></div><div class="pulse-store">Добро пожаловать</div></div>`;
const shell=html=>root.innerHTML=`<section class="pulse-shell">${brand()}<div class="pulse-center">${html}</div><div class="pulse-bottom">Отвечать необязательно. Мы не запрашиваем имя, телефон или фотографии.<br>OSMANX RETAIL INTELLIGENCE</div></section>`;
async function api(method,path,body){const response=await fetch(`/api/public/r10/pulse/${encodeURIComponent(slug)}`,{
 method,headers:{'Content-Type':'application/json','X-OSMANX-KIOSK':token},body:body?JSON.stringify(body):undefined,cache:'no-store'});
 const data=await response.json().catch(()=>({detail:'Ошибка ответа сервера'}));if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Ошибка соединения');return data;}
function tokenForm(){shell(`<p>Терминал не привязан</p><h1>Подключите планшет</h1><p>Введите ключ, выданный руководителем магазина. Он остаётся только в памяти этого браузера на время сессии.</p><form id="pulse-key"><input class="pulse-token" type="password" name="key" minlength="20" placeholder="Ключ терминала" required><button class="xp-button red" style="width:100%;padding:18px">Подключить терминал</button></form>`)}
async function load(){if(!token){tokenForm();return}try{campaign=await api('GET');show()}catch(err){shell(`<h1>Опрос недоступен</h1><p class="pulse-error">${esc(err.message)}</p><button id="pulse-repair" class="xp-button">Сменить ключ терминала</button>`);}}
function show(){shell(`<p>${esc(campaign.store_name)} · одна короткая анкета</p><h1>${esc(campaign.question)}</h1><div class="pulse-options">${campaign.options.map((x,i)=>`<button data-choice="${i}">${esc(x)}</button>`).join('')}</div><p>Ответ займёт несколько секунд</p>`)}
root.addEventListener('submit',async e=>{if(e.target.id!=='pulse-key')return;e.preventDefault();token=new FormData(e.target).get('key').trim();sessionStorage.setItem(`osmanx_pulse_token_${slug}`,token);await load()});
root.addEventListener('click',async e=>{
 if(e.target.id==='pulse-repair'){token='';sessionStorage.removeItem(`osmanx_pulse_token_${slug}`);tokenForm();return}
 const choice=e.target.closest('[data-choice]');if(!choice||sending||!campaign)return;
 const index=Number(choice.dataset.choice);if(!Number.isInteger(index))return;sending=true;
 root.querySelectorAll('[data-choice]').forEach(x=>x.disabled=true);
 try{
  await api('POST',null,{request_id:crypto.randomUUID?.()||`ox-pulse-${Date.now()}-${Math.random().toString(36).slice(2)}`,campaign_id:campaign.campaign_id,option_index:index});
  shell('<div class="pulse-message"><h1>Спасибо за ваш ответ</h1><p>Вы помогаете нам делать магазин удобнее.</p><button id="pulse-next" class="xp-button red">Следующий посетитель</button></div>');
 }catch(err){shell(`<h1>Не удалось сохранить ответ</h1><p class="pulse-error">${esc(err.message)}</p><button class="xp-button" id="pulse-next">Вернуться к опросу</button>`)}finally{sending=false}
});
root.addEventListener('click',e=>{if(e.target.id==='pulse-next')load()});
load();
