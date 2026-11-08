// Non-invasive navigation enhancement. The existing SPA owns its nav markup.
const link='/static/workflows.html';
function addShortcut(){
 if(location.pathname.startsWith('/kiosk/'))return;
 const nav=document.querySelector('.sidebar .nav');
 if(nav&&!nav.querySelector('.r06-nav')){
  const a=document.createElement('a');a.className='nav-btn r06-nav';
  a.href=link;a.innerHTML='<span style="color:#fb5c73;font-size:19px;font-weight:900">↗</span><span>Центр закупок и решений</span>';
  nav.append(a);
  const b=document.createElement('a');b.className='nav-btn r07-nav';b.href='/static/operations.html';
  b.innerHTML='<span style="color:#fb5c73;font-size:19px;font-weight:900">◇</span><span>Контроль магазина</span>';nav.append(b);
 }
 const top=document.querySelector('.main .topbar .top-right');
 if(top&&!top.querySelector('.r06-shortcut')){
  const a=document.createElement('a');a.className='r06-shortcut';a.href=link;
  a.title='Переход к закупкам и экономике';a.setAttribute('aria-label','Центр закупок и решений');
  a.innerHTML='↗ <span>Закупки и решения</span>';top.insertAdjacentElement('afterbegin',a);
 }
}
const style=document.createElement('style');style.textContent='.r06-shortcut{display:inline-flex;align-items:center;gap:8px;min-height:39px;padding:9px 12px;border:1px solid #704255;border-radius:10px;background:#351c2b;color:#f9d3dd;font-size:11px;font-weight:800}.r06-shortcut:hover{background:#602638}@media(max-width:1200px){.r06-shortcut span{display:none}}@media(max-width:550px){.r06-shortcut{padding:8px;min-height:36px}}';document.head.append(style);
const observer=new MutationObserver(addShortcut);
observer.observe(document.body,{childList:true,subtree:true});addShortcut();
