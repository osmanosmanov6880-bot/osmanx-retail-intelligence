/* OSMANX R2.1: additive sidebar link; never overrides existing SPA state. */
(()=>{if(location.pathname.includes('voice_kiosk'))return;
 const attach=()=>{const nav=document.querySelector('.sidebar .nav');if(!nav||nav.querySelector('[data-r21-link]'))return;
 const a=document.createElement('a');a.href='/static/assurance.html';a.className='nav-btn';a.dataset.r21Link='1';
 const symbol=document.createElement('span');symbol.textContent='◈';symbol.style.cssText='color:#ef607c;font-size:19px;font-weight:900';
 const text=document.createElement('span');text.textContent='Store Assurance · Контроль';a.append(symbol,text);nav.append(a)};
 new MutationObserver(attach).observe(document.body,{childList:true,subtree:true});attach();
})();
