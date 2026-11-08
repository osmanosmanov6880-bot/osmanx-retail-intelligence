/**
 * OSMANX Retail Intelligence — deterministic, self-contained synthetic data model.
 * Accounting facts, linked receipts and demand observations are kept separate from forecasts.
 * No fake network connections or fabricated production integrations.
 */
export const AS_OF = '2026-11-08';
export const STORES = Object.freeze([
  {id:'s1', name:'Центральный', short:'Филиал №1', district:'Центр'},
  {id:'s2', name:'Галерея', short:'Филиал №2', district:'Торговая галерея'},
  {id:'s3', name:'Парк', short:'Филиал №3', district:'Южный квартал'}
]);
export const CATEGORIES = Object.freeze(['Куртки','Платья','Брюки','Обувь','Трикотаж','Рубашки']);
export const SIZES = Object.freeze(['XS','S','M','L','XL']);
export const SCENARIOS = Object.freeze([
  {id:'balanced',name:'Успешная сеть',factor:1,demand:1,service:1},
  {id:'operations',name:'Операционные сложности',factor:.88,demand:1.19,service:1.65},
  {id:'shortages',name:'Спрос выше доступности',factor:1.12,demand:1.85,service:1.08}
]);
export const MONEY = n => new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0}).format(Math.round(n||0))+' ₽';
export const NUMBER = n => new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0}).format(Math.round(n||0));
export const PERCENT = n => Number.isFinite(n) ? (n*100).toLocaleString('ru-RU',{maximumFractionDigits:1})+'%' : '—';
export const safeRatio = (a,b) => b>0 ? a/b : null;
export function daysAgo(n) { const d=new Date(AS_OF+'T12:00:00.000Z'); d.setUTCDate(d.getUTCDate()-n); return d.toISOString().slice(0,10); }
const sum = (items, key) => items.reduce((t,r)=>t+(typeof key==='function'?key(r):r[key]||0),0);
function rnd(seed) { let s=seed>>>0;return ()=>((s=(1664525*s+1013904223)>>>0)/4294967296); }
const pick=(r,arr)=>arr[Math.floor(r()*arr.length)];
const clamp=(x,min,max)=>Math.max(min,Math.min(max,x));
export function buildCatalog() {
  const names={
    'Куртки':['AURA','NORD','MISTRAL','ECHO','NOVA','ATELIER','LUMEN'],
    'Платья':['SILK','MIRA','LUNA','FORMA','ELLE','SABLE','LINE'],
    'Брюки':['BASE','AXIS','FRAME','MOTION','TAILOR','EDGE','CORE'],
    'Обувь':['VECTOR','TERRA','URBAN','MONO','PRIME','LACE','KIN'],
    'Трикотаж':['MERINO','SOFT','CLOUD','BALANCE','MOSS','KNIT','WAVE'],
    'Рубашки':['OXFORD','PURE','CLASSIC','FINE','EASY','COTTON','MODE']
  };
  const base={'Куртки':8900,'Платья':7200,'Брюки':5200,'Обувь':7400,'Трикотаж':4400,'Рубашки':5100};
  const products=[];
  for (let i=0;i<300;i++) {
    const category=CATEGORIES[i%6], catIndex=Math.floor(i/6), name=names[category][catIndex%7], isAura=i===0;
    const price=isAura?8900:base[category]+((catIndex*19)%11)*360;
    const cost=isAura?4900:Math.round(price*(.48+((catIndex*3)%13)/100)/10)*10;
    products.push({id:isAura?'JKT-AURA':`SKU-${String(i+1).padStart(3,'0')}`,code:`${category.slice(0,2).toUpperCase()}-${String(i+1).padStart(3,'0')}`,name:isAura?'AURA / technical jacket':`${name} ${String(Math.floor(catIndex/7)+1).padStart(2,'0')}`,category,price,cost,colors:isAura?['Графит','Песочный']:['Графит','Светлый']});
  }
  return products;
}
export const CATALOG=buildCatalog();
export const AURA=CATALOG[0];
const modelMap=new Map(CATALOG.map(p=>[p.id,p]));
export function product(id) {return modelMap.get(id)||AURA;}
export function buildDataset(scenarioId='balanced') {
  const scenario=SCENARIOS.find(s=>s.id===scenarioId)||SCENARIOS[0];
  const r=rnd(761102+(scenarioId==='operations'?21:scenarioId==='shortages'?89:0));
  const sales=[],returns=[],traffic=[],requests=[],fittings=[],assistance=[],stock=[],transfers=[],audits=[],decisions=[],preorders=[],preferences=[];
  const byDateAndStore=new Map();let sId=0;
  for(let d=89;d>=0;d--)for(let si=0;si<3;si++) {
    const day=daysAgo(d),store=STORES[si],weekend=new Date(day+'T12:00:00Z').getUTCDay()%6===0;
    const visitors=Math.round((138+si*27+(weekend?65:0)+Math.floor(r()*45))*scenario.factor);
    const passers=Math.round(visitors*(2.65+r()*.6));
    traffic.push({id:`foot-${day}-${store.id}`,date:day,storeId:store.id,passers,visits:visitors,variant:d%18<9?'А':'Б'});
    const tickets=Math.max(4,Math.round(visitors*(.112+(r()-.5)*.05)));
    for(let j=0;j<tickets;j++) {
      const p=CATALOG[Math.floor(Math.pow(r(),1.12)*CATALOG.length)];
      const size=pick(r,SIZES),discount=r()<.18?(r()<.7?.1:.2):0;
      const paidPrice=Math.round(p.price*(1-discount));
      const memberId=r()<.42?`loy-${String(Math.floor(r()*190)+1).padStart(3,'0')}`:null;
      const sale={id:`sale-${++sId}`,date:day,storeId:store.id,modelId:p.id,size,color:pick(r,p.colors),paidPrice,cost:p.cost,discount,memberId,originRequestId:null};
      sales.push(sale);
      const key=day+'|'+store.id;
      if(!byDateAndStore.has(key))byDateAndStore.set(key,[]);
      byDateAndStore.get(key).push(sale);
    }
  }
  // Demand funnel: 60 observed requests -> 32 available solutions -> 18 opted-in -> 7 linked purchases.
  // The seven receipts show gross profit but NOT incrementality against a counterfactual.
  for(let i=0;i<60;i++) {
    const date=daysAgo(i%14),storeId=STORES[i%3].id,size=i<29?'L':i<47?'M':pick(r,SIZES);
    const req={id:`req-14-${String(i+1).padStart(3,'0')}`,date,storeId,modelId:i<41?AURA.id:CATALOG[(i*11+2)%CATALOG.length].id,size,color:'Графит',solutionFound:i<32,consent:i<18,purchased:i<7,saleId:null,source:'Запрос покупателя (добровольно)'};
    if(i<7) {
      req.modelId=AURA.id;
      const sold={id:`rescue-${i+1}`,date,storeId,modelId:AURA.id,size,color:'Графит',paidPrice:8900,cost:4900,discount:0,memberId:null,originRequestId:req.id};
      req.saleId=sold.id;
      sales.push(sold);
    }
    requests.push(req);
  }
  for(let i=0;i<210;i++) {
    const d=14+(i%76),date=daysAgo(d),p=CATALOG[(i*17+7)%CATALOG.length];
    const found=i%5!==0,consent=found&&i%4===0;
    requests.push({id:`req-old-${i+1}`,date,storeId:STORES[i%3].id,modelId:p.id,size:SIZES[i%5],color:'Графит',solutionFound:found,consent,purchased:false,saleId:null,source:'Запрос покупателя (добровольно)'});
  }
  if(scenarioId!=='balanced') {
    // Alternative presentations contain additional *synthetic* observations, never invented receipts.
    const extra=Math.round(60*(scenario.demand-1));
    for(let i=0;i<extra;i++) {
      const p=CATALOG[(i*29+3)%300];
      requests.push({id:`req-scenario-${i}`,date:daysAgo(i%14),storeId:STORES[i%3].id,modelId:scenarioId==='shortages'?AURA.id:p.id,size:SIZES[i%5],color:'Графит',solutionFound:false,consent:false,purchased:false,saleId:null,source:'Запрос покупателя (добровольно)'});
    }
  }
  // Returns reference valid receipts and happen on or after sale date.
  for (let i=0;i<sales.length;i++) {
    const sold=sales[i];
    if(sold.originRequestId||r()>.042)continue;
    const elapsed=Math.floor((Date.parse(AS_OF)-Date.parse(sold.date))/86400000);
    const date=daysAgo(Math.max(0,elapsed-Math.floor(r()*Math.min(12,elapsed+1))));
    returns.push({id:`return-${returns.length+1}`,date,storeId:sold.storeId,saleId:sold.id,modelId:sold.modelId,size:sold.size,refundedPrice:sold.paidPrice,reversedCost:sold.cost,reason:pick(r,['Не подошёл размер','Качество','Передумал','Цвет','Повторный дефект']),source:'Зарегистрированный возврат'});
  }
  // Fitting outcomes are discrete observations, with explicitly recorded vs assumed reasons.
  for(let i=0;i<900;i++) {
    const date=daysAgo(i%90),storeId=STORES[i%3].id,p=CATALOG[(i*31+5)%300];
    const purchased=r()<.46,reason=purchased?null:pick(r,['Посадка','Цена','Нужен другой размер','Не указан','Фасон']);
    const matching=(byDateAndStore.get(date+'|'+storeId)||[]).find(s=>s.modelId===p.id);
    fittings.push({id:`fit-${i+1}`,date,storeId,modelId:p.id,size:SIZES[i%5],purchased,reason:reason==='Не указан'?null:reason,reasonType:reason==='Не указан'?'неизвестно':'со слов покупателя',saleId:purchased&&matching?matching.id:null});
  }
  for(let i=0;i<540;i++) {
    const date=daysAgo(i%90),storeId=STORES[i%3].id;
    const responseSeconds=Math.round((25+r()*170)*scenario.service*(i%9===0?2.3:1));
    assistance.push({id:`help-${i+1}`,date,storeId,modelId:CATALOG[(i*13)%300].id,requestType:pick(r,['Подбор размера','Проверка наличия','Помощь в примерочной']),responseSeconds,resolved:responseSeconds<240||r()>.3,source:'QR-запрос помощи'});
  }
  for(const p of CATALOG)for(const store of STORES)for(const size of SIZES)for(const color of p.colors) {
    let qty=Math.floor(r()*6);
    if(p.id===AURA.id&&size==='L'&&color==='Графит')qty=store.id==='s2'?3:store.id==='s1'?0:2;
    if(scenarioId==='shortages'&&store.id==='s1'&&['L','M'].includes(size))qty=Math.max(0,qty-2);
    stock.push({id:`stock-${p.id}-${store.id}-${size}-${color}`,modelId:p.id,storeId:store.id,size,color,quantity:qty,source:'Синтетический снимок остатков',asOf:AS_OF});
  }
  for(let i=0;i<120;i++) {
    const p=CATALOG[(i*23+9)%300],date=daysAgo((i*7)%90);
    transfers.push({id:`move-${i+1}`,date,modelId:p.id,size:SIZES[i%5],fromStoreId:STORES[i%3].id,toStoreId:STORES[(i+1)%3].id,quantity:1+(i%3),cost:220+(i%4)*80,status:pick(r,['Выполнено','В пути','Ожидает проверки'])});
  }
  for(let i=0;i<75;i++) {
    const item=stock[(i*117+71)%stock.length];
    audits.push({id:`audit-${i+1}`,date:daysAgo(i%90),modelId:item.modelId,storeId:item.storeId,size:item.size,expected:item.quantity,observed:Math.max(0,item.quantity+(i%2?1:-1)),status:i%3===0?'Проверено':'Требует сверки'});
  }
  // Separate voluntary preorders and preference events; neither is a completed retail sale.
  for(let i=0;i<135;i++) {
    const p=CATALOG[(i*7+31)%300];
    preorders.push({id:`pre-${i+1}`,date:daysAgo(i%90),storeId:STORES[i%3].id,modelId:p.id,size:SIZES[i%5],consent:true,depositPaid:i%8===0,status:i%4===0?'Отменён':'Ожидает',source:'Добровольный предзаказ'});
  }
  for(let i=0;i<220;i++) {
    const p=CATALOG[(i*13+5)%300];
    preferences.push({id:`pref-${i+1}`,date:daysAgo(i%90),storeId:STORES[i%3].id,modelId:p.id,size:SIZES[(i+2)%5],intent:i%3===0?'Готов рассмотреть':'Интересуется',source:'Добровольный опрос'});
  }
  // Confirmed business operation != independently proven attributable improvement.
  decisions.push({id:'act-1',name:'Уведомления о размере AURA',date:daysAgo(3),status:'Завершено',evidenceIds:requests.slice(0,7).map(x=>x.id),linkedSales:7,cost:1800});
  decisions.push({id:'act-2',name:'Проверка спорных остатков',date:daysAgo(6),status:'В работе',evidenceIds:audits.slice(0,12).map(x=>x.id),linkedSales:0,cost:950});
  return {scenarioId,scenario,products:CATALOG,stores:STORES,sales,returns,traffic,requests,fittings,assistance,stock,transfers,audits,preorders,preferences,decisions,generatedAt:AS_OF};
}
export function scopeData(data,filter={}) {
  const days=filter.period==='custom'?null:Math.max(1,Number(filter.period)||14);
  const from=days?daysAgo(days-1):(filter.from||daysAgo(13));
  const to=days?AS_OF:(filter.to||AS_OF);
  const matches=(e)=>{
    if(e.date<from||e.date>to)return false;
    if(filter.store&&filter.store!=='all'&&e.storeId!==filter.store)return false;
    if(filter.category&&filter.category!=='all'&&product(e.modelId).category!==filter.category)return false;
    if(filter.model&&filter.model!=='all'&&e.modelId!==filter.model)return false;
    if(filter.size&&filter.size!=='all'&&e.size!==filter.size)return false;
    return true;
  };
  const trafficMatches=e=>e.date>=from&&e.date<=to&&(!filter.store||filter.store==='all'||e.storeId===filter.store);
  const select=name=>data[name].filter(matches);
  const sales=select('sales'),returns=select('returns'),requests=select('requests'),fittings=select('fittings'),assistance=select('assistance'),transfers=select('transfers'),audits=select('audits'),preorders=select('preorders'),preferences=select('preferences'),traffic=data.traffic.filter(trafficMatches);
  const scopedStock=data.stock.filter(s=>(!filter.store||filter.store==='all'||s.storeId===filter.store)&&(!filter.category||filter.category==='all'||product(s.modelId).category===filter.category)&&(!filter.model||filter.model==='all'||s.modelId===filter.model)&&(!filter.size||filter.size==='all'||s.size===filter.size));
  const grossSales=sum(sales,'paidPrice'),revenue=grossSales-sum(returns,'refundedPrice');
  const costOfGoods=sum(sales,'cost')-sum(returns,'reversedCost');
  const grossProfit=revenue-costOfGoods;
  const observedRescue=sales.filter(s=>s.originRequestId);
  const observedRescueGross=sum(observedRescue,s=>s.paidPrice-s.cost);
  const anonymousCategory=!filter.category||filter.category==='all';
  const conversionEligible=anonymousCategory&&(!filter.model||filter.model==='all')&&(!filter.size||filter.size==='all');
  const visits=conversionEligible?sum(traffic,'visits'):null;
  const conversion=visits===null?null:safeRatio(sales.length,visits);
  const consentEvents=requests.filter(e=>e.consent),purchased=requests.filter(e=>e.purchased);
  const uniqueMembers=new Set(sales.map(s=>s.memberId).filter(Boolean));
  const returningMembers=new Set(sales.filter(s=>s.memberId).map(s=>s.memberId).filter(id=>sales.filter(x=>x.memberId===id).length>1));
  const repeatShare=uniqueMembers.size?safeRatio(returningMembers.size,uniqueMembers.size):null;
  const unsoldRequests=requests.filter(e=>!e.purchased).length;
  // Potential is *scenario estimate* (not guaranteed revenue/profit, nor confirmed cost savings).
  const unfulfilled=requests.filter(e=>!e.purchased&&!e.solutionFound).length;
  const potential=unfulfilled*0.22*3500;
  const serviceRisk=assistance.filter(e=>e.responseSeconds>240).length;
  const inventoryRisk=audits.filter(e=>e.status==='Требует сверки').length;
  return {filter,from,to,sales,returns,requests,fittings,assistance,transfers,audits,preorders,preferences,stock:scopedStock,traffic,
    totals:{revenue,grossSales,costOfGoods,grossProfit,grossMargin:safeRatio(grossProfit,revenue),
      visits,conversion,unsoldRequests,confirmedRescueSales:observedRescue.length,confirmedRescueGross:observedRescueGross,
      potential,serviceRisk,inventoryRisk,repeatShare,requested:requests.length,consented:consentEvents.length,purchased:purchased.length,
      availableSolutions:requests.filter(x=>x.solutionFound).length,unitsSold:sales.length,returns:returns.length,inventoryUnits:sum(scopedStock,'quantity'),
      avgStock:sum(scopedStock,'quantity'),turnover:sum(scopedStock,'quantity')>0?sales.length/sum(scopedStock,'quantity'):null}};
}
export function forecastTransfer({units=3,price=8900,cost=4900,probability=.55,costPerUnit=350,fixedCost=0}={}) {
  const u=clamp(Number(units)||0,0,1e6),p=clamp(Number(probability)||0,0,1);
  const unitGross=(Number(price)||0)-(Number(cost)||0);
  const expectedSales=u*p;
  const gross=Math.round(expectedSales*unitGross*100)/100;
  const logistics=Math.round((u*Math.max(0,Number(costPerUnit)||0)+Math.max(0,Number(fixedCost)||0))*100)/100;
  return {units:u,probability:p,expectedSales,gross,logistics,net:gross-logistics,unitGross};
}
export function pilotForecast({stores=3,requestsPerStore=20,conversion=.12,avgTicket=8900,costPerSale=4900,pilotCost=15000}={}) {
  const potentialPurchases=Math.max(0,Number(stores))*Math.max(0,Number(requestsPerStore))*clamp(Number(conversion)||0,0,1);
  const revenue=potentialPurchases*Math.max(0,Number(avgTicket));
  const gross=potentialPurchases*(Number(avgTicket)-Number(costPerSale));
  const net=gross-Math.max(0,Number(pilotCost));
  return {potentialPurchases,revenue,gross,net,paybackRatio:pilotCost>0?gross/pilotCost:null};
}
export const FUNNEL_STAGES=[
  {id:'request',name:'Запрос размера',hint:'60 добровольных сигналов от покупателей'},
  {id:'solution',name:'Найдено решение',hint:'32 случая с возможным вариантом'},
  {id:'consent',name:'Согласие клиента',hint:'18 разрешений на уведомление'},
  {id:'purchase',name:'Покупка',hint:'7 связанных подтверждённых чеков'}
];
export function funnelData(scope) {
  return [scope.requests.length,scope.requests.filter(x=>x.solutionFound).length,scope.requests.filter(x=>x.consent).length,scope.requests.filter(x=>x.purchased).length];
}
export function opportunityMetrics(scope) {
  const t=scope.totals,marginPerSale=t.unitsSold?t.grossProfit/t.unitsSold:0;
  const fittingsLost=scope.fittings.filter(f=>!f.purchased).length;
  const inventory=scope.audits.filter(a=>a.status==='Требует сверки').length;
  const slow=scope.assistance.filter(a=>a.responseSeconds>240).length;
  return [
    {id:'demand',label:'Невидимый спрос',count:t.unsoldRequests,estimate:t.potential,uncertainty:'Оценка',source:'Запросы покупателей',action:'Запустить пилот уведомлений'},
    {id:'rescue',label:'Межфилиальные продажи',count:scope.requests.filter(x=>x.solutionFound&&!x.purchased).length,estimate:scope.requests.filter(x=>x.solutionFound&&!x.purchased).length*.18*Math.max(0,marginPerSale),uncertainty:'Прогноз',source:'Запросы + остатки',action:'Проверить доступность в филиалах'},
    {id:'fitting',label:'Примерочные',count:fittingsLost,estimate:fittingsLost*.07*Math.max(0,marginPerSale),uncertainty:'Гипотеза',source:'Фиксация примерок',action:'Изучить причины отказов'},
    {id:'stock',label:'Расхождения остатков',count:inventory,estimate:null,uncertainty:'Недостаточно данных',source:'Выборочная сверка',action:'Провести физическую проверку'},
    {id:'service',label:'Задержки помощи',count:slow,estimate:slow*.05*Math.max(0,marginPerSale),uncertainty:'Гипотеза',source:'QR-запросы',action:'Уточнить норматив ответа'},
    {id:'returns',label:'Возвраты',count:scope.returns.length,estimate:null,uncertainty:'Недостаточно данных',source:'Связанные возвраты',action:'Проверить модели с повторными жалобами'}
  ];
}
export function recommendations(scope) {
  const opp=opportunityMetrics(scope);
  return opp.sort((a,b)=>(b.count||0)-(a.count||0)).slice(0,5).map((x,i)=>({...x,priority:i+1,experiment:i===0?'14-дневный пилот, сравнение с контрольным периодом':i===1?'Сверить факт наличия и время перемещения':'Протокол наблюдений + контрольный замер'}));
}
export function diagnosticPlan(answers={}) {
  const plan=[];
  if(answers.trackSizes!=='Да')plan.push({title:'Измерить невидимый спрос',detail:'14 дней фиксировать отсутствующие размеры, модель, филиал и итог обращения — без принудительного сбора контактов.'});
  if(answers.findAcross!=='Да')plan.push({title:'Проверить межфилиальную доступность',detail:'Выбрать 10 частых запросов и замерить, удаётся ли найти и передать покупателю товар в другом филиале.'});
  if(answers.refusal!=='Да')plan.push({title:'Исследовать причины отказов',detail:'Добровольный опрос у выхода и в примерочной, отделять записанный ответ от интерпретации.'});
  if(answers.priority==='Маржа')plan.unshift({title:'Проверить экономику скидок',detail:'Сопоставить цену после скидки, себестоимость, объём и валовую прибыль по SKU.'});
  if(answers.priority==='Удержание')plan.unshift({title:'Измерить повторные покупки',detail:'С согласия участников программы лояльности построить когорты и сравнить повторы.'});
  if(answers.priority==='Ассортимент')plan.unshift({title:'Проверить сигналы следующей коллекции',detail:'Сопоставить запросы размеров, предзаказы и реальные продажи, без обещания будущего спроса.'});
  const defaults=[
    {title:'Выбрать один главный коммерческий показатель',detail:'Определить выручку, валовую прибыль или конверсию как основную метрику и выбрать исходный период.'},
    {title:'Проверить качество данных',detail:'Уточнить источники чеков, остатков и посещений. Отдельно зафиксировать пробелы.'},
    {title:'Согласовать измерение пилота',detail:'Определить стоимость внедрения, базовый период и минимальный объём подтверждённых событий.'}
  ];
  for(const d of defaults)if(plan.length<3)plan.push(d);
  return plan.slice(0,3);
}
