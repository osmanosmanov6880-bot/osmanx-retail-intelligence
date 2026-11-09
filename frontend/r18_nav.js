/* R1.8: minimal navigation integration without replacing the primary SPA. */
(()=>{if(location.pathname.startsWith('/kiosk/')||location.pathname.includes('voice_kiosk'))return;
  function attach(){const nav=document.querySelector('.sidebar .nav');if(!nav||nav.querySelector('[data-r18-shortcut]'))return;
    const a=document.createElement('a');a.href='/static/bridge.html';a.className='nav-btn';
    a.dataset.r18Shortcut='1';
    const emblem=document.createElement('span');emblem.textContent='◇';emblem.style.cssText='color:#ef4d69;font-size:20px;font-weight:900';
    const title=document.createElement('span');title.textContent='Decision Bridge · Решения';
    a.append(emblem,title);nav.append(a);
  }
  new MutationObserver(attach).observe(document.body,{childList:true,subtree:true});attach();
})();
