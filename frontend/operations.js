/* OSMANX Retail Intelligence R0.7 — five live operational workflows. */
const root=document.querySelector('#operations-root');
const toastRoot=document.querySelector('#operations-toast');
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=n=>new Intl.NumberFormat('ru-RU').format(Number(n||0));
const money=n=>new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0}).format(Number(n||0)/100)+' ₽';
const dateStr=(delta=0)=>{const d=new Date();d.setDate(d.getDate()+delta);return d.toISOString().slice(0,10)};
const uuid=()=>crypto.randomUUID?.()||`r07-${Date.now()}-${Math.random().toString(36).slice(2)}`;
const S={tab:'brief',slug:'central',stores:[],config:{},data:null,loading:false,lastPoint:null};
const sections=[['brief','Отчёт директора'],['counts','Инвентаризация'],['transfers','Перемещения'],['assistance','Помощь покупателю'],['zones','Витрины и зоны']];
const statusNames={pending:'На проверке',applied:'Применена',cancelled:'Отменена',draft:'Черновик',shipped:'В пути',received:'Принято',open:'Ожидает',accepted:'Принят',resolved:'Завершён'};
let timer=null;
function toast(msg,error=false){clearTimeout(timer);toastRoot.innerHTML=`<div class="toast ${error?'bad':''}">${esc(msg)}</div>`;timer=setTimeout(()=>toastRoot.innerHTML='',4700)}
async function call(path,options={}){
 const headers={Accept:'application/json'};
 if(options.body!==undefined)headers['Content-Type']='application/json';
 const token=sessionStorage.getItem('osmanx_admin_token');if(token)headers.Authorization='Bearer '+token;
 const response=await fetch('/api'+path,{method:options.method||'GET',headers,body:options.body!==undefined?JSON.stringify(options.body):undefined,cache:'no-store'});
 const data=await response.json().catch(()=>({detail:'Сервер вернул некорректный ответ'}));
 if(!response.ok){const message=data.detail;throw new Error(typeof message==='string'?message:typeof message==='object'&&message?.length?message.map(x=>x.msg).join('; '):'Ошибка '+response.status)}
 return data;
}
async function downloadCSV(){
 const token=sessionStorage.getItem('osmanx_admin_token');const headers=token?{Authorization:'Bearer '+token}:{};
 const response=await fetch('/api/admin/r07/brief.csv?slug='+encodeURIComponent(S.slug),{headers,cache:'no-store'});
 if(!response.ok)throw new Error('Не удалось выгрузить отчёт');
 const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');
 a.href=url;a.download=`osmanx-${S.slug}-brief.csv`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function reload(){
 S.loading=true;
 try{
  const q='?slug='+encodeURIComponent(S.slug);
  const paths=['/admin/r07/brief','/admin/r07/stock','/admin/r07/counts','/admin/r07/transfers','/admin/r07/assistance','/admin/r07/zone-trials'];
  const d=await Promise.all(paths.map(path=>call(path+q)));
  S.data={brief:d[0],stock:d[1].items,counts:d[2].items,transfers:d[3].items,assistance:d[4],zones:d[5]};render();
 }catch(error){root.innerHTML=`<div class="error"><h2>Нет доступа к данным</h2><p>${esc(error.message)}</p><a href="/" class="button">Войти в кабинет</a></div>`}
 finally{S.loading=false}
}
async function init(){
 try{
  S.config=await call('/config');
  if(!S.config.demo&&!sessionStorage.getItem('osmanx_admin_token')){
    root.innerHTML='<div class="error"><div class="brand">OSMAN<span>X</span></div><h2>Для работы нужен вход</h2><p>Войдите в основной кабинет и вернитесь к операциям.</p><a href="/" class="button red">Войти в систему</a></div>';return;
  }
  S.stores=await call('/admin/stores');
  if(!S.stores.length)throw new Error('Нет доступных филиалов');
  const requested=new URLSearchParams(location.search).get('store');S.slug=S.stores.find(x=>x.slug===requested)?.slug||S.stores[0].slug;
  await reload();
 }catch(error){root.innerHTML=`<div class="error"><h2>Не удалось открыть приложение</h2><p>${esc(error.message)}</p><a href="/" class="button">Основной кабинет</a></div>`}
}
const field=(name,label,type='text',extra={})=>`<div class="field"><label>${esc(label)}</label><input name="${esc(name)}" type="${type}" ${extra.required===false?'':'required'} ${extra.min!==undefined?`min="${extra.min}"`:''} ${extra.max!==undefined?`max="${extra.max}"`:''} ${extra.value!==undefined?`value="${esc(extra.value)}"`:''} ${extra.step!==undefined?`step="${extra.step}"`:''} ${extra.placeholder?`placeholder="${esc(extra.placeholder)}"`:''}></div>`;
const selector=(name,label,options,placeholder='Выберите')=>`<div class="field"><label>${esc(label)}</label><select name="${esc(name)}" required>${options.length?options.map(o=>`<option value="${esc(o.value)}">${esc(o.label)}</option>`).join(''):`<option value="">${esc(placeholder)}</option>`}</select></div>`;
const card=(title,contents)=>`<section class="card"><h3 class="ct">${esc(title)}</h3>${contents}</section>`;
const empty=message=>`<div class="empty">${esc(message)}</div>`;
const tag=s=>`<span class="pill ${['received','resolved','applied'].includes(s)?'good':['pending','shipped','open'].includes(s)?'warn':''}">${esc(statusNames[s]||s)}</span>`;
const record=(title,subtitle,side='')=>`<div class="record"><div><strong>${esc(title)}</strong><small>${esc(subtitle)}</small></div><div class="record-right">${side}</div></div>`;
const button=(label,action,id,variant='')=>`<button type="button" class="button ${variant}" data-action="${esc(action)}" data-id="${esc(id)}">${esc(label)}</button>`;
function render(){
 const x=S.data,m=x.brief.metrics;const store=S.stores.find(s=>s.slug===S.slug);
 root.innerHTML=`<main class="app"><header class="top"><div><div class="brand">OSMAN<span>X</span></div><div class="brandline">RETAIL OPERATIONS · R0.7</div></div><div class="toplinks">
  <select class="store-select" id="ops-store" aria-label="Выберите филиал">${S.stores.map(st=>`<option value="${esc(st.slug)}" ${st.slug===S.slug?'selected':''}>${esc(st.name)}</option>`).join('')}</select>
  <a class="toplink" href="/static/workflows.html">Спрос и закупки</a><a class="toplink primary" href="/">Основной кабинет</a></div></header>
 <section class="hero"><div><div class="eyebrow">Контроль, точность, решение</div><h1>Операционный центр</h1><p>Работа с реальными остатками, запросами покупателей и измерениями. Без выдуманных продаж, распознавания лиц и непроверенных обещаний прибыли.</p></div><div class="hero-right"><strong>${esc(store?.name||S.slug)}</strong><small>${esc(x.brief.generated_at?.slice(0,16)||'')}</small></div></section>
 ${S.config.demo?'<div class="banner">Демонстрационный режим — искусственные данные подписаны как демо. Подключения физических устройств не симулируются.</div>':''}
 <section class="kpi-grid">
  ${kpi('Посетители / 14 дней',num(m.visitors),'По существующим событиям')}
  ${kpi('Покупки / 14 дней',num(m.sales),'Подтверждённые чеки')}
  ${kpi('Незакрытый спрос',num(m.open_demand),'Обращения покупателей')}
  ${kpi('Запросы на помощь',num(m.service_open),'Ожидают реакции')}
 </section><nav class="tabs" aria-label="Разделы операционного центра">${sections.map(([id,label])=>`<button class="tab ${S.tab===id?'active':''}" role="tab" aria-selected="${S.tab===id}" data-tab="${id}">${label}</button>`).join('')}</nav>
 <div id="ops-content">${S.tab==='brief'?brief():S.tab==='counts'?counts():S.tab==='transfers'?transfers():S.tab==='assistance'?assistance():zones()}</div>
 <footer class="footer">OSMANX RETAIL INTELLIGENCE · R0.7 · Внутренняя система. Не является доказательством причинно-следственной связи или автоматическим финансовым прогнозом.</footer></main>`;
}
function kpi(label,value,sub){return `<div class="kpi"><label>${esc(label)}</label><strong>${esc(value)}</strong><p>${esc(sub)}</p></div>`}
function brief(){const b=S.data.brief,m=b.metrics;
 const metrics=[['Выручка по чекам',money(m.revenue_kopeks)],['Конверсия (ориентир)',m.conversion_percent===null?'Нет данных':m.conversion_percent+'%'],
 ['Валовая маржа по SKU',money(m.sku_gross_margin_kopeks)],['Инвентаризации с расхождениями',num(m.counts_with_variance)],
 ['Перемещений в пути',num(m.transfers_in_transit)],['Среднее ожидание помощи',m.avg_response_seconds===null?'Нет данных':m.avg_response_seconds+' сек.'],
 ['Экспериментов с зонами',num(m.zone_experiments)]];
 return `<div class="section-head"><div><h2>Управленческая сводка</h2><p>Фактические события за последние 14 дней. Значения зависят от полноты подключённых источников.</p></div><button type="button" class="button red" data-action="csv">Экспорт CSV</button></div><div class="grid equal">
 ${card('Показатели магазина',`${metrics.map(([a,b])=>`<div class="metric"><span>${esc(a)}</span><strong>${esc(b)}</strong></div>`).join('')}<div class="disclaimer">${esc(b.disclaimer)}</div>`)}
 ${card('Что требует решения',`${b.priorities.length?b.priorities.map(p=>record(p.title,p.evidence,tag(p.priority))).join(''):empty('Сейчас нет автоматических задач по подтверждённым событиям.')}<div class="disclaimer">Система показывает основания и ограничения, а не гарантирует рост продаж.</div>`)}
 ${card('Качество данных',`${b.warnings.length?b.warnings.map(w=>`<div class="alert">${esc(w)}</div>`).join(''):empty('Критических предупреждений по доступным данным нет.')}<div class="metric"><span>Чеки</span><strong>${num(m.sales)}</strong></div><div class="metric"><span>Чеки с товарными строками</span><strong>${num(m.allocated_sales)}</strong></div>`)}
 ${card('Путь к решению',`${record('1. Проверьте фактические остатки','Инвентаризация с фиксацией расхождений',button('Открыть','nav','counts'))}${record('2. Переместите нужный товар','Передача из филиала и подтверждение приёмки',button('Открыть','nav','transfers'))}${record('3. Оцените опыт покупателей','Скорость реакции на помощь',button('Открыть','nav','assistance'))}${record('4. Сравните выкладку','А/Б периоды — без ложной причинности',button('Открыть','nav','zones'))}`)}
 </div>`;
}
function counts(){const d=S.data;let choices=d.stock.map(r=>({value:r.id,label:`${r.product} · ${r.size||'—'} · ${r.sku} (учёт ${r.quantity}, свободно ${r.available})`}));
 return `<div class="section-head"><div><h2>Инвентаризация без пересортицы</h2><p>Подсчёт → проверка расхождений → подтверждённая корректировка склада с записью в журнал.</p></div></div><div class="grid">
 ${card('Новый пересчёт',`<p class="note">Для корректировки необходима причина. Подсчёт не меняет остатки до подтверждения. Забронированные вещи нельзя списать.</p><form data-form="count" class="fields">
   ${selector('inventory_id','Товар',choices,'Нет товаров: импортируйте остатки')}
   <div class="inline">${field('observed_qty','Фактически найдено, шт.','number',{min:0,max:1000000,value:0})}${field('reason','Причина / комментарий','text',{required:false,placeholder:'Проверено на полке'})}</div>
   <div class="actions"><button class="button red" type="submit" ${!choices.length?'disabled':''}>Зафиксировать пересчёт</button></div></form>`)}
 ${card('Результаты проверки',`${d.counts.length?d.counts.map(c=>record(`Пересчёт №${c.id} · ${c.lines.length} позиций`,`Расхождение: ${c.variance_units>0?'+':''}${c.variance_units} шт. · ${c.created_at.slice(0,16)}`,`${tag(c.status)}${c.status==='pending'?button('Применить','count-apply',c.id,'green')+button('Отменить','count-cancel',c.id):''}`)).join(''):empty('Инвентаризации ещё не проводились.')}<div class="disclaimer">Если остаток изменится после подсчёта, система потребует новый пересчёт вместо перезаписи более свежих данных.</div>`)}
 ${card('Остатки, доступные для пересчёта',`${d.stock.length?d.stock.slice(0,15).map(r=>record(`${r.sku} · ${r.product}`,`Размер ${r.size||'—'} · учёт ${r.quantity} · резерв ${r.reserved} · доступно ${r.available}`)).join(''):empty('В этом филиале пока нет товаров. Начните с загрузки остатков в основном кабинете.')}`)}
 </div>`;
}
function transfers(){const d=S.data;const destinations=S.stores.filter(x=>x.slug!==S.slug).map(x=>({value:x.slug,label:x.name}));
 const inv=d.stock.map(x=>({value:x.id,label:`${x.product} · ${x.size||'—'} · ${x.sku} (доступно ${x.available})`}));
 return `<div class="section-head"><div><h2>Межфилиальные перемещения</h2><p>Товар списывается при отправке и поступает в другой филиал только после подтверждения приёмки.</p></div></div><div class="grid">
 ${card('Создать перемещение',`<p class="note">Перед отправкой система повторно проверит доступность товара и действующие резервы. Один документ нельзя применить дважды.</p><form data-form="transfer" class="fields">
  ${selector('target_slug','Филиал назначения',destinations,'Добавьте второй филиал')}${selector('inventory_id','Товар к отправке',inv,'Нет товаров в наличии')}
  ${field('quantity','Количество, шт.','number',{value:1,min:1,max:10000})}<div class="actions"><button class="button red" type="submit" ${!destinations.length||!inv.length?'disabled':''}>Создать документ</button></div></form>`)}
 ${card('Документы и маршрут товара',`${d.transfers.length?d.transfers.map(t=>record(`№${t.id} · ${t.sku} · ${t.quantity} шт.`,`${t.source_name} → ${t.target_name} · ${t.created_at.slice(0,16)}`,`${tag(t.status)}${t.status==='draft'?button('Отправить','ship',t.id,'red')+button('Отменить','cancel',t.id):''}${t.status==='shipped'?button('Принять','receive',t.id,'green'):''}`)).join(''):empty('Документов пока нет.')}<div class="disclaimer">Перемещение — не продажа. Чек учитывается отдельно после фактической покупки.</div>`)}
 </div>`;
}
function assistance(){const d=S.data.assistance;
 const names={size:'Нужен размер',help:'Нужна консультация',checkout:'Помощь с покупкой'};
 const pointInfo=S.lastPoint&&S.lastPoint.slug===S.slug?`<div class="qr-result"><strong>Ссылка для QR-кода</strong><p>Сохраните её сейчас. Повторно ключ не показывается.</p><code>${esc(S.lastPoint.url)}</code><div class="actions"><button type="button" class="button red" data-action="copy-link">Скопировать ссылку</button><a class="button" target="_blank" rel="noreferrer" href="${esc(S.lastPoint.url)}">Открыть</a></div></div>`:'';
 return `<div class="section-head"><div><h2>Помощь в примерочной и торговом зале</h2><p>Покупатель нажимает кнопку по QR. Сотрудник принимает вызов. Без камеры, имени и номера телефона.</p></div><button type="button" class="button" data-action="refresh">Обновить очередь</button></div><div class="grid">
 ${card('Точки вызова',`<form data-form="point" class="fields"><p class="note">Подключите QR-код к стойке или примерочной. Ключ создаётся случайно, в базе хранится только его хеш.</p>${field('name','Где разместить QR','text',{placeholder:'Примерочная №1'})}<div class="actions"><button type="submit" class="button red">Создать точку</button></div></form>${pointInfo}<div style="margin-top:16px">${d.points.length?d.points.map(p=>record(p.name,`Точка №${p.id} · ${p.active?'активна':'отключена'}`,`${tag(p.active?'open':'cancelled')}${p.active?button('Отключить','point-disable',p.id):''}`)).join(''):empty('Точки вызова пока не созданы.')}</div>`)}
 ${card('Очередь обращений',`${d.requests.length?d.requests.map(x=>record(`${names[x.category]||x.category} · ${x.point_name}`,`Запрос №${x.id} · ${x.created_at.slice(0,16)}`,`${tag(x.status)}${x.status==='open'?button('Принять','help-accept',x.id,'red')+button('Закрыть','help-cancel',x.id):''}${x.status==='accepted'?button('Выполнено','help-resolve',x.id,'green'):''}`)).join(''):empty('Обращений пока нет. Покупатель сможет отправить их после сканирования QR-кода.')}<div class="disclaimer">Статус фиксирует работу с вызовом. Время ответа рассчитывается по реальным отметкам и не подменяет качество консультации.</div>`)}
 </div>`;
}
function zones(){const d=S.data.zones;const choices=d.zones.map(x=>({value:x.id,label:x.name+' ('+x.code+')'}));
 const detail=d.items.map(x=>{
  const a=x.period_a.per_day,b=x.period_b.per_day,max=Math.max(a,b,1);
  return `<article class="record"><div style="width:100%"><strong>${esc(x.title)}</strong><small>А: ${esc(x.variant_a)} · B: ${esc(x.variant_b)}</small><div class="compare" style="margin-top:12px"><div><small>Период A / день</small><strong>${num(a)}</strong><div class="bar"><i style="width:${Math.max(1,a/max*100)}%"></i></div></div><div><small>Период B / день</small><strong>${num(b)}</strong><div class="bar"><i style="width:${Math.max(1,b/max*100)}%"></i></div></div></div><p class="note" style="margin-top:13px">Изменение: ${x.change_percent===null?'не рассчитано':x.change_percent+'%'} · ${esc(x.interpretation)}</p>${x.warnings.map(w=>`<div class="alert">${esc(w)}</div>`).join('')}</div></article>`;
 }).join('');
 return `<div class="section-head"><div><h2>Эксперименты с витринами и зонами</h2><p>Два периода наблюдений: сколько событий за день, насколько сопоставимы источники и чего пока нельзя утверждать.</p></div></div><div class="grid">
 ${card('Проверить новую выкладку',`<form data-form="trial" class="fields"><p class="note">Понадобятся события подключённого датчика зоны. Пустые или демонстрационные измерения явно отмечаются.</p>
  ${selector('zone_id','Зона магазина',choices,'Настройте зоны в основном кабинете')}${field('title','Название проверки','text',{placeholder:'Новая подсветка витрины'})}
  <div class="inline">${field('variant_a','Вариант A','text',{value:'Исходная выкладка'})}${field('variant_b','Вариант B','text',{value:'Новая выкладка'})}</div>
  <div class="inline">${field('a_start','A: начало','date',{value:dateStr(-13)})}${field('a_end','A: конец','date',{value:dateStr(-7)})}</div>
  <div class="inline">${field('b_start','B: начало','date',{value:dateStr(-6)})}${field('b_end','B: конец','date',{value:dateStr(0)})}</div>
  <div class="actions"><button type="submit" class="button red" ${!choices.length?'disabled':''}>Сохранить эксперимент</button></div></form>`)}
 ${card('Результаты наблюдений',`${detail||empty('Нет экспериментов. Создайте сравнение двух периодов.')}<div class="disclaimer">При отсутствии данных о прохожих нельзя измерить конверсию витрины из уличного потока. Рост событий не доказывает рост прибыли.</div>`)}
 </div>`;
}

root.addEventListener('change',e=>{
 if(e.target.id==='ops-store'){
  S.slug=e.target.value;S.lastPoint=null;reload();
 }
});
root.addEventListener('click',async e=>{
 const tab=e.target.closest('[data-tab]');if(tab){S.tab=tab.dataset.tab;render();return;}
 const btn=e.target.closest('[data-action]');if(!btn)return;
 const action=btn.dataset.action,id=btn.dataset.id;
 if(action==='nav'){S.tab=id;render();return;}
 if(action==='copy-link'){
  try{await navigator.clipboard.writeText(S.lastPoint.url);toast('Ссылка скопирована')}catch{toast('Скопируйте ссылку вручную',true)}return;
 }
 btn.disabled=true;
 try{
  if(action==='csv'){await downloadCSV();toast('Отчёт подготовлен');return;}
  if(action==='refresh'){await reload();toast('Очередь обновлена');return;}
  const paths={
   'count-apply':`/admin/r07/counts/${id}/apply`,
   'count-cancel':`/admin/r07/counts/${id}/cancel`,
   ship:`/admin/r07/transfers/${id}/ship`,receive:`/admin/r07/transfers/${id}/receive`,cancel:`/admin/r07/transfers/${id}/cancel`,
   'point-disable':`/admin/r07/assistance/points/${id}/disable`,
   'help-accept':`/admin/r07/assistance/${id}/status`,
   'help-resolve':`/admin/r07/assistance/${id}/status`,
   'help-cancel':`/admin/r07/assistance/${id}/status`
  };
  if(!paths[action])throw new Error('Неизвестная операция');
  const body=action.startsWith('help-')?{status:{'help-accept':'accepted','help-resolve':'resolved','help-cancel':'cancelled'}[action]}:undefined;
  await call(paths[action],{method:'POST',body});toast('Операция сохранена');await reload();
 }catch(error){toast(error.message,true)}finally{btn.disabled=false}
});
root.addEventListener('submit',async e=>{
 const form=e.target.closest('form[data-form]');if(!form)return;e.preventDefault();
 const kind=form.dataset.form,values=Object.fromEntries(new FormData(form));
 const submit=form.querySelector('button[type=submit]');if(submit)submit.disabled=true;
 try{
  if(kind==='count'){
   const r=await call('/admin/r07/counts',{method:'POST',body:{slug:S.slug,request_id:uuid(),lines:[{inventory_id:Number(values.inventory_id),observed_qty:Number(values.observed_qty),reason:values.reason||''}]}});
   toast('Пересчёт №'+r.id+' создан. Подтвердите применение в списке.');
  }else if(kind==='transfer'){
   const r=await call('/admin/r07/transfers',{method:'POST',body:{source_slug:S.slug,target_slug:values.target_slug,inventory_id:Number(values.inventory_id),quantity:Number(values.quantity),request_id:uuid()}});
   toast('Документ №'+r.id+' создан. Теперь отправьте товар.');
  }else if(kind==='point'){
   const r=await call('/admin/r07/assistance/points',{method:'POST',body:{slug:S.slug,name:values.name}});
   S.lastPoint={slug:S.slug,url:location.origin+r.path};toast('Точка создана. Сохраните уникальную ссылку.');
  }else if(kind==='trial'){
   const r=await call('/admin/r07/zone-trials',{method:'POST',body:{slug:S.slug,zone_id:Number(values.zone_id),title:values.title,variant_a:values.variant_a,variant_b:values.variant_b,a_start:values.a_start,a_end:values.a_end,b_start:values.b_start,b_end:values.b_end}});
   toast('Эксперимент №'+r.id+' сохранён.');
  }
  await reload();
 }catch(error){toast(error.message,true)}finally{if(submit)submit.disabled=false}
});
init();
