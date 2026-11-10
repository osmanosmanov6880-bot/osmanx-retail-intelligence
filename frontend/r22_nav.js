/* R2.2: additive shortcut, does not replace the existing navigation handlers. */
(()=>{if(location.pathname.startsWith('/kiosk/')||location.pathname.includes('voice_kiosk'))return;
  function attach(){const nav=document.querySelector('.sidebar .nav');if(!nav||nav.querySelector('[data-r22-shortcut]'))return;
    const a=document.createElement('a');a.href='/static/rollout.html';a.className='nav-btn';a.dataset.r22Shortcut='1';
    const mark=document.createElement('span');mark.textContent='◇';mark.style.cssText='color:#f0526e;font-weight:900;font-size:19px';
    const label=document.createElement('span');label.textContent='Multi-Store · Внедрение';a.append(mark,label);nav.append(a);
  }
  new MutationObserver(attach).observe(document.body,{childList:true,subtree:true});attach();
})();
