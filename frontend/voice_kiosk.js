/* R1.7 anonymous, version-bound touchscreen questionnaire. No personal details. */
const root=document.getElementById('voice-kiosk-root');
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fragment=(location.hash||'').slice(1),dot=fragment.indexOf('.');
const publicId=dot>0?fragment.slice(0,dot):'',secret=dot>0?fragment.slice(dot+1):'';
const state={config:null,answers:{},request_id:'',position:0,mode:'loading',error:''};
const steps=()=>state.config?.questions.filter(q=>!q.show_if||state.answers[q.show_if.question]===q.show_if.equals)||[];
const newId=()=>crypto.randomUUID?.()||'voice-'+Date.now()+'-'+Math.random().toString(36).slice(2);
async function call(path,{method='GET',body}={}){if(!publicId||!secret)throw Error('Ссылка на опрос не содержит действующего ключа');const response=await fetch('/api/voice/r17/'+encodeURIComponent(publicId)+'/'+path,{method,cache:'no-store',headers:{'Content-Type':'application/json','X-OSMANX-Voice-Key':secret},body:body?JSON.stringify(body):undefined});const data=await response.json().catch(()=>({detail:'Ошибка получения ответа'}));if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:`Ошибка ${response.status}`);return data;}
function shell(content){root.innerHTML=`<div class="kiosk-wrap"><header class="kiosk-header"><div class="brand">OSMAN<span>X</span></div><div class="eyebrow">ANONYMOUS VOICE<br>STUDIO</div></header>${content}</div>`;}
async function start(){state.mode='loading';state.answers={};state.position=0;state.request_id=newId();shell('<div class="loading"><h2>Открываем короткий опрос…</h2><p>Без регистрации и контактов</p></div>');try{state.config=await call('form');await call('open',{method:'POST',body:{request_id:state.request_id,version_hash:state.config.version_hash}});state.mode='answer';render();}catch(err){state.mode='error';state.error=err.message;render();}}
function render(){if(state.mode==='error'){shell(`<div class="thank-you"><h1>Опрос недоступен</h1><p>${esc(state.error)}</p><a class="kiosk-secondary" href="/">Главный экран</a></div>`);return;}
if(state.mode==='done'){shell(`<div class="thank-you"><div class="mark">✓</div><div class="eyebrow">СПАСИБО ЗА ВАШЕ ВРЕМЯ</div><h1>Ваше мнение<br>поможет стать лучше.</h1><p>Ответы сохранены без имени, телефона и видеозаписи. Спасибо, что помогаете магазину совершенствоваться.</p><button class="kiosk-primary" id="new-voice">Новый опрос</button></div>`);document.getElementById('new-voice').onclick=()=>start();return;}
const visible=steps();if(!visible.length){state.mode='error';state.error='Пустая анкета';render();return;}
state.position=Math.min(state.position,visible.length-1);const q=visible[state.position],value=state.answers[q.id];const percent=(100*state.position/visible.length).toFixed(1);
const choices=q.type==='choice'?`<div class="kiosk-choices">${q.options.map(o=>`<button class="kiosk-choice ${value===o.id?'active':''}" data-value="${esc(o.id)}"><span>${esc(o.label)}</span><span class="check" aria-hidden="true"></span></button>`).join('')}</div>`:
`<div class="kiosk-rating">${[1,2,3,4,5].map(n=>`<button class="kiosk-choice ${value===n?'active':''}" data-value="${n}" aria-label="Оценка ${n}">${n}</button>`).join('')}</div>`;
shell(`<div class="kiosk-progress" aria-label="Прогресс"><span style="width:${percent}%"></span></div><div class="kiosk-count">Вопрос ${state.position+1} / ${visible.length}</div><h1 class="kiosk-title">${esc(q.title)}</h1>${choices}<div class="kiosk-footer"><div class="kiosk-controls"><button class="kiosk-secondary" id="back-voice" ${state.position===0?'disabled':''}>Назад</button><button class="kiosk-primary" id="next-voice" ${value===undefined?'disabled':''}>${state.position===visible.length-1?'Отправить ответы':'Продолжить'}</button></div><div class="kiosk-note">${esc(state.config.notice)} Не все посетители участвуют в опросе: результаты нельзя считать статистикой всех покупателей.</div></div>`);
root.querySelectorAll('[data-value]').forEach(b=>b.onclick=()=>{state.answers[q.id]=q.type==='rating'?Number(b.dataset.value):b.dataset.value;
  // Remove answers that became hidden after changing an earlier choice.
  const currently=steps().map(x=>x.id);for(const id of Object.keys(state.answers)){if(!currently.includes(id))delete state.answers[id];}
  render();});
root.querySelector('#back-voice').onclick=()=>{if(state.position>0){state.position--;render();}};
root.querySelector('#next-voice').onclick=async()=>{if(state.answers[q.id]===undefined)return;const current=steps();if(state.position<current.length-1){state.position++;render();return;}
 const btn=root.querySelector('#next-voice');btn.disabled=true;btn.textContent='Отправляем…';try{await call('submit',{method:'POST',body:{request_id:state.request_id,version_hash:state.config.version_hash,answers:state.answers}});state.mode='done';render();}catch(err){btn.disabled=false;btn.textContent='Повторить';const note=root.querySelector('.kiosk-note');if(note)note.textContent=err.message;}};
}
start();
