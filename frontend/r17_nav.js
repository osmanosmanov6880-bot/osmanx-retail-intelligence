/* R1.7: additive sidebar shortcut; does not override the existing SPA handlers. */
(()=>{if(location.pathname.startsWith('/kiosk/')||location.pathname.includes('voice_kiosk'))return;
 function attach(){const nav=document.querySelector('.sidebar .nav');if(!nav||nav.querySelector('[data-r17-shortcut]'))return;
   const link=document.createElement('a');link.href='/static/voice.html';link.className='nav-btn';
   link.dataset.r17Shortcut='1';link.innerHTML='<span style="color:#ee5b7b;font-weight:900;font-size:18px">◈</span><span>Voice Studio · Опросы</span>';nav.append(link);
 }
 const observer=new MutationObserver(attach);observer.observe(document.body,{childList:true,subtree:true});attach();
})();
