/* Additive R2.3 navigation shortcut, no override of primary SPA router. */
(()=>{
  if(location.pathname.startsWith('/kiosk/')||location.pathname.includes('voice_kiosk'))return;
  function attach(){
    const nav=document.querySelector('.sidebar .nav');
    if(!nav||nav.querySelector('[data-r23-shortcut]'))return;
    const a=document.createElement('a');a.href='/static/security.html';a.className='nav-btn';a.dataset.r23Shortcut='1';
    const symbol=document.createElement('span');symbol.textContent='◇';symbol.style.cssText='color:#ef637f;font-weight:900;font-size:19px';
    const label=document.createElement('span');label.textContent='Security Center · R2.3';a.append(symbol,label);nav.append(a);
  }
  new MutationObserver(attach).observe(document.body,{childList:true,subtree:true});attach();
})();
