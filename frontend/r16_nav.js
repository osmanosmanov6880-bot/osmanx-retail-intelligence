/* Conservative shortcut: does not change existing menu event handlers. */
(function(){if(location.pathname.startsWith('/kiosk/'))return;
function attach(){const nav=document.querySelector('.sidebar .nav');if(!nav||nav.querySelector('[data-r16-shortcut]'))return;
const a=document.createElement('a');a.href='/static/command.html';a.className='nav-btn';a.dataset.r16Shortcut='1';
a.innerHTML='<span style="color:#ee5b7b;font-size:18px;font-weight:900">◆</span><span>Командный центр пилотов</span>';nav.append(a)}
const observer=new MutationObserver(attach);observer.observe(document.body,{childList:true,subtree:true});attach();
})();
