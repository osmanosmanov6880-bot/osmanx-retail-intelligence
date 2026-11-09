/* OSMANX Voice Studio kiosk R1.9 — anonymous offline recovery and signed tablet heartbeat. */
/* R1.9 offline answer queue. Contains anonymous form responses only, never terminal secrets or shopper identifiers. */
const PREFIX='osmanx:r19:queue:';
const FORM_PREFIX='osmanx:r19:form:';
const MAX_PENDING=25;
const TTL_MS=60*60*1000;
function safeParse(s,fallback){try{return JSON.parse(s)}catch{return fallback}}
function pending(publicId){
  let saved;try{saved=localStorage.getItem(PREFIX+publicId)}catch{return []}
  const items=safeParse(saved,[]);
  return Array.isArray(items)?items.filter(x=>x&&typeof x.request_id==='string'&&typeof x.created==='number'&&x.created>Date.now()-TTL_MS).slice(0,MAX_PENDING):[];
}
function storePending(publicId,item){
  const items=pending(publicId);
  if(items.some(x=>x.request_id===item.request_id))return items.length;
  if(items.length>=MAX_PENDING)throw Error('Очередь ответов заполнена. Сообщите сотруднику.');
  items.push({...item,created:Date.now()});
  try{localStorage.setItem(PREFIX+publicId,JSON.stringify(items))}catch{throw Error('На этом планшете запрещено сохранять ответы. Обратитесь к сотруднику.');}
  return items.length;
}
function replacePending(publicId,items){
  try{localStorage.setItem(PREFIX+publicId,JSON.stringify(items))}catch{}
}
function saveForm(publicId,config){
  try{localStorage.setItem(FORM_PREFIX+publicId,JSON.stringify({config,saved:Date.now()}))}catch{}
}
function cachedForm(publicId){
  let saved;try{saved=localStorage.getItem(FORM_PREFIX+publicId)}catch{return null}
  const value=safeParse(saved,null);
  return value&&Date.now()-value.saved<TTL_MS&&Array.isArray(value.config?.questions)?value.config:null;
}

const root=document.getElementById('voice-kiosk-root');
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fragment=(location.hash||'').slice(1),dot=fragment.indexOf('.');
const publicId=dot>0?fragment.slice(0,dot):'',secret=dot>0?fragment.slice(dot+1):'';
const state={config:null,answers:{},request_id:'',position:0,mode:'loading',error:'',offline:false,queued:false,flushError:''};
const steps=()=>state.config?.questions.filter(q=>!q.show_if||state.answers[q.show_if.question]===q.show_if.equals)||[];
const newId=()=>crypto.randomUUID?.()||'voice-'+Date.now()+'-'+Math.random().toString(36).slice(2);
async function call(path,{method='GET',body,service='r17'}={}){
  if(!publicId||!secret)throw Error('Ссылка на опрос не содержит действующего ключа');
  let response;
  try{response=await fetch('/api/voice/'+service+'/'+encodeURIComponent(publicId)+'/'+path,{
    method,cache:'no-store',headers:{'Content-Type':'application/json','X-OSMANX-Voice-Key':secret},
    body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(10000)
  });}catch(e){const error=Error('Связь с сервером недоступна');error.network=true;throw error;}
  const data=await response.json().catch(()=>({detail:'Ошибка получения ответа'}));
  if(!response.ok){const error=Error(typeof data.detail==='string'?data.detail:`Ошибка ${response.status}`);error.status=response.status;error.network=response.status>=500;throw error;}
  return data;
}
const queueCount=()=>pending(publicId).length;
function shell(content){
  root.innerHTML=`<div class="kiosk-wrap"><header class="kiosk-header"><div class="brand">OSMAN<span>X</span></div><div class="eyebrow">VOICE STUDIO<br><span id="voice-connection">${state.offline?'НЕТ СВЯЗИ · ОФФЛАЙН':'ОПРОС ПОКУПАТЕЛЯ'}</span></div></header>${content}</div>`;
}
async function heartbeat(){if(!publicId||!secret||!navigator.onLine)return;
  try{await call('heartbeat',{method:'POST',service:'r19',body:{request_id:newId(),queue_depth:queueCount(),app_version:'r1.9',network_state:queueCount()?'recovering':'online'}})}catch{}
}
let flushing=false;
async function flushPending(){
  if(flushing||!navigator.onLine||!publicId)return;
  flushing=true;
  try{
    let items=pending(publicId);
    if(!items.length){replacePending(publicId,[]);return;}
    let config;
    try{config=await call('form');}catch(err){state.flushError=err.message;return;}
    const failed=[];
    for(const item of items){
      if(item.version_hash!==config.version_hash){failed.push({...item,error:'Анкета изменилась; нужна проверка сотрудника.'});continue;}
      try{
        await call('open',{method:'POST',body:{request_id:item.request_id,version_hash:item.version_hash}});
        await call('submit',{method:'POST',body:{request_id:item.request_id,version_hash:item.version_hash,answers:item.answers}});
      }catch(err){failed.push({...item,error:err.message});}
    }
    replacePending(publicId,failed);
    state.flushError=failed.length?'Часть ответов пока не удалось отправить.': '';
  }finally{flushing=false;}
}
async function start(){
  state.mode='loading';state.answers={};state.position=0;state.request_id=newId();state.offline=false;state.queued=false;
  shell('<div class="loading"><h2>Открываем короткий опрос…</h2><p>Без регистрации и контактов</p></div>');
  try{
    await flushPending();
    try{state.config=await call('form');saveForm(publicId,state.config);}
    catch(err){if(!err.network)throw err;state.config=cachedForm(publicId);if(!state.config)throw err;state.offline=true;}
    if(!state.offline){
      try{await call('open',{method:'POST',body:{request_id:state.request_id,version_hash:state.config.version_hash}});}
      catch(err){if(!err.network)throw err;state.offline=true;}
    }
    state.mode='answer';render();heartbeat();
  }catch(err){state.mode='error';state.error=err.message;render();}
}
function render(){
  if(state.mode==='error'){
    shell(`<div class="thank-you"><h1>Опрос временно недоступен</h1><p>${esc(state.error)}</p><button class="kiosk-primary" id="restart-voice">Повторить</button></div>`);
    root.querySelector('#restart-voice').onclick=start;return;
  }
  if(state.mode==='done'){
    shell(`<div class="thank-you"><div class="mark">${state.queued?'…':'✓'}</div><div class="eyebrow">СПАСИБО ЗА ВАШЕ ВРЕМЯ</div>
      <h1>${state.queued?'Ответ сохранён на планшете':'Ваше мнение поможет стать лучше'}</h1>
      <p>${state.queued?'Нет связи с сервером. Ваш анонимный ответ ещё не получен магазином; терминал попробует передать его позднее.':'Ответ успешно передан магазину. Спасибо за участие!'}<br>Ответы без имени и телефона.</p>
      <button class="kiosk-primary" id="new-voice">Новый опрос</button></div>`);
    root.querySelector('#new-voice').onclick=start;return;
  }
  const visible=steps();if(!visible.length){state.mode='error';state.error='Пустая анкета';render();return;}
  state.position=Math.min(state.position,visible.length-1);
  const q=visible[state.position],value=state.answers[q.id];
  const percent=(100*state.position/visible.length).toFixed(1);
  const choices=q.type==='choice'?`<div class="kiosk-choices">${q.options.map(o=>`<button class="kiosk-choice ${value===o.id?'active':''}" data-value="${esc(o.id)}"><span>${esc(o.label)}</span><span class="check" aria-hidden="true"></span></button>`).join('')}</div>`:
  `<div class="kiosk-rating">${[1,2,3,4,5].map(n=>`<button class="kiosk-choice ${value===n?'active':''}" data-value="${n}" aria-label="Оценка ${n}">${n}</button>`).join('')}</div>`;
  shell(`<div class="kiosk-progress" aria-label="Прогресс"><span style="width:${percent}%"></span></div>
    ${state.offline?'<p class="kiosk-offline">Нет связи: ответ будет сохранён на этом планшете, но не на сервере.</p>':''}
    <div class="kiosk-count">Вопрос ${state.position+1} / ${visible.length}</div><h1 class="kiosk-title">${esc(q.title)}</h1>${choices}
    <div class="kiosk-footer"><div class="kiosk-controls"><button class="kiosk-secondary" id="back-voice" ${state.position===0?'disabled':''}>Назад</button>
    <button class="kiosk-primary" id="next-voice" ${value===undefined?'disabled':''}>${state.position===visible.length-1?'Отправить ответы':'Продолжить'}</button></div>
    <div class="kiosk-note">${esc(state.config.notice||'Опрос анонимный и добровольный.')} Не все посетители участвуют в опросе: результаты нельзя считать статистикой всех покупателей.</div></div>`);
  root.querySelectorAll('[data-value]').forEach(b=>b.onclick=()=>{
    state.answers[q.id]=q.type==='rating'?Number(b.dataset.value):b.dataset.value;
    const nowVisible=steps().map(x=>x.id);for(const id of Object.keys(state.answers))if(!nowVisible.includes(id))delete state.answers[id];
    render();
  });
  root.querySelector('#back-voice').onclick=()=>{if(state.position>0){state.position--;render();}};
  root.querySelector('#next-voice').onclick=async()=>{
    if(state.answers[q.id]===undefined)return;
    const current=steps();if(state.position<current.length-1){state.position++;render();return;}
    const btn=root.querySelector('#next-voice');btn.disabled=true;btn.textContent='Отправляем…';
    const payload={request_id:state.request_id,version_hash:state.config.version_hash,answers:state.answers};
    try{
      if(state.offline){storePending(publicId,payload);state.queued=true;}
      else{
        try{await call('submit',{method:'POST',body:payload});}
        catch(err){if(!err.network)throw err;storePending(publicId,payload);state.queued=true;}
      }
      state.mode='done';render();heartbeat();
    }catch(err){btn.disabled=false;btn.textContent='Повторить';const note=root.querySelector('.kiosk-note');if(note)note.textContent=err.message;}
  };
}
window.addEventListener('online',()=>{flushPending().then(heartbeat).catch(()=>{});});
setInterval(()=>{heartbeat();if(navigator.onLine)flushPending();},45000);
start();
