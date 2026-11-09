/* OSMANX R1.9: additive link in existing dynamic sidebar. */
(()=>{if(location.pathname.startsWith('/kiosk/')||location.pathname.includes('voice_kiosk'))return;
function mount(){const nav=document.querySelector('.sidebar .nav');if(!nav||nav.querySelector('[data-r19-shortcut]'))return;
  const a=document.createElement('a');a.href='/static/field.html';a.className='nav-btn';a.dataset.r19Shortcut='1';
  const marker=document.createElement('span');marker.textContent='◉';marker.style.cssText='font-size:18px;color:#e94f73;font-weight:900';
  const label=document.createElement('span');label.textContent='Field Operations · Терминалы';a.append(marker,label);nav.append(a);
}
new MutationObserver(mount).observe(document.body,{childList:true,subtree:true});mount();
})();
