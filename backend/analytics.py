"""Transparent retail KPIs. Counts are events, not unique identified customers."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlite3 import Connection

from backend.retail import observations, daily_metrics, zone_heatmap, traffic_sources, traffic_filter
from backend.commerce import matching_available

REASONS = {
    "size": "Не нашёл размер", "price": "Высокая цена",
    "assortment": "Не подошёл ассортимент", "service": "Долго ждал помощь",
    "just_looking": "Просто смотрел", "other": "Другое",
}


def _aggregate(db: Connection, table: str, metric: str, store_id: int, start: str, end: str) -> int:
    # table and metric always come from internal static call sites.
    row = db.execute(f"SELECT COALESCE(SUM({metric}),0) AS n FROM {table} WHERE store_id=? AND occurred_at>=? AND occurred_at<?",
        (store_id, start, end)).fetchone()
    return int(row["n"])


def dashboard(db: Connection, store_id: int, days: int = 30, timezone_name: str = "Europe/Moscow") -> dict:
    # Store-local calendar days; persist and query all events in UTC.
    tz = ZoneInfo(timezone_name)
    end_local = datetime.now(tz).replace(hour=0,minute=0,second=0,microsecond=0) + timedelta(days=1)
    start_local = end_local - timedelta(days=days)
    prev_local = start_local - timedelta(days=days)
    start, end, prev = (value.astimezone(timezone.utc).isoformat(timespec='seconds')
                        for value in (start_local,end_local,prev_local))
    policy=db.execute('SELECT traffic_mode FROM stores WHERE id=?',(store_id,)).fetchone()['traffic_mode']
    active_sources=traffic_sources(db,store_id,policy,start,end)
    src_where,src_args=traffic_filter(active_sources)
    visitors=db.execute('SELECT COALESCE(SUM(quantity),0) n FROM visits WHERE store_id=? AND occurred_at>=? AND occurred_at<?'+src_where,
                        (store_id,start,end,*src_args)).fetchone()['n']
    purchases = db.execute(
        "SELECT COUNT(*) AS n FROM sales WHERE store_id=? AND occurred_at>=? AND occurred_at<?",(store_id,start,end)).fetchone()["n"]
    revenue = _aggregate(db,"sales","amount_kopeks",store_id,start,end) / 100
    previous_sources=traffic_sources(db,store_id,policy,prev,start)
    prev_where,prev_args=traffic_filter(previous_sources)
    prev_visitors=db.execute('SELECT COALESCE(SUM(quantity),0) n FROM visits WHERE store_id=? AND occurred_at>=? AND occurred_at<?'+prev_where,
                             (store_id,prev,start,*prev_args)).fetchone()['n']
    prev_purchases = db.execute("SELECT COUNT(*) AS n FROM sales WHERE store_id=? AND occurred_at>=? AND occurred_at<?",
        (store_id,prev,start)).fetchone()["n"]
    prev_revenue = _aggregate(db,"sales","amount_kopeks",store_id,prev,start) / 100

    visits_by_hour = Counter()
    sales_by_hour = Counter()
    for row in db.execute('SELECT occurred_at,quantity FROM visits WHERE store_id=? AND occurred_at>=? AND occurred_at<?'+src_where,
                          (store_id,start,end,*src_args)):
        visits_by_hour[datetime.fromisoformat(row['occurred_at']).astimezone(tz).hour]+=row['quantity']
    for row in db.execute('SELECT occurred_at FROM sales WHERE store_id=? AND occurred_at>=? AND occurred_at<?',(store_id,start,end)):
        sales_by_hour[datetime.fromisoformat(row['occurred_at']).astimezone(tz).hour]+=1
    hourly = [{"hour": f"{hour:02}:00", "visitors":int(visits_by_hour[hour]),
               "purchases":int(sales_by_hour[hour])} for hour in range(9,22)]

    reasons_rows = db.execute(
        "SELECT reason, COUNT(*) n FROM surveys WHERE store_id=? AND purchased=0 AND reason<>'' AND created_at>=? AND created_at<? GROUP BY reason ORDER BY n DESC",
        (store_id,start,end)).fetchall()
    reasons = [{"key":row["reason"],"label":REASONS.get(row["reason"],row["reason"]),"count":row["n"]} for row in reasons_rows]
    responses = db.execute("SELECT COUNT(*) n, AVG(rating) rating FROM surveys WHERE store_id=? AND created_at>=? AND created_at<?",
        (store_id,start,end)).fetchone()
    signal_rows = db.execute("SELECT kind, SUM(quantity) n FROM signals WHERE store_id=? AND occurred_at>=? AND occurred_at<? GROUP BY kind",
        (store_id,start,end)).fetchall()
    signals = {row["kind"]:int(row["n"]) for row in signal_rows}
    top_demand = [dict(row) for row in db.execute(
        "SELECT product,size,color, COUNT(*) count FROM demand WHERE store_id=? AND created_at>=? AND created_at<? GROUP BY product,size,color ORDER BY count DESC LIMIT 6",
        (store_id,start,end)).fetchall()]
    latest_demand = [dict(row) for row in db.execute(
        "SELECT id,product,size,color,status,sale_id,created_at FROM demand WHERE store_id=? ORDER BY created_at DESC,id DESC LIMIT 40",(store_id,)).fetchall()]
    latest_surveys = [dict(row) for row in db.execute(
        "SELECT id,rating,purchased,reason,liked,suggestion,liked_tags,improve_tags,created_at FROM surveys WHERE store_id=? ORDER BY created_at DESC,id DESC LIMIT 30",(store_id,)).fetchall()]
    demand_status = [dict(row) for row in db.execute(
        "SELECT status,COUNT(*) n FROM demand WHERE store_id=? AND created_at>=? AND created_at<? GROUP BY status",
        (store_id,start,end)).fetchall()]
    percent = round(100*purchases/visitors,1) if visitors else 0
    past_percent = round(100*prev_purchases/prev_visitors,1) if prev_visitors else 0

    recommendations = []
    if top_demand and top_demand[0]["count"] >= 3:
        d = top_demand[0]
        recommendations.append({"severity":"high","title":"Повторяющийся запрос на отсутствующий товар",
            "text":f"За период зафиксировано {d['count']} запроса на «{d['product']}», размер {d['size']}. Проверьте остатки по филиалам и целесообразность закупки.",
            "type":"demand"})
    if reasons:
        lead = reasons[0]
        recommendations.append({"severity":"medium","title":"Наиболее частая причина отказа",
            "text":f"«{lead['label']}» — {lead['count']} ответов. Опрос показывает мнение участников, а не всех посетителей; проверьте гипотезу отдельно.",
            "type":"feedback"})
    if visitors and purchases and percent < 20:
        recommendations.append({"severity":"medium","title":"Проверить конверсию посещений",
            "text":f"По учтённым событиям конверсия {percent}%. Сверьте точность подсчёта входов и кассовых событий, затем проверьте часы и причины отказов.",
            "type":"traffic"})
    if not recommendations:
        recommendations.append({"severity":"info","title":"Начните с измеримой гипотезы",
            "text":"Собирайте посещения, продажи и причины отказов не менее 7 дней. Не делайте выводов о потерянной прибыли без проверки.",
            "type":"next"})
    evidence=observations(db,store_id,start,end)
    trend=daily_metrics(db,store_id,timezone_name,days,policy)
    verified=db.execute('SELECT COUNT(*) AS count FROM demand WHERE store_id=? AND sale_id IS NOT NULL AND created_at>=? AND created_at<?',(store_id,start,end)).fetchone()['count']
    stock_total=db.execute('SELECT COUNT(*) AS count, SUM(CASE WHEN quantity=0 THEN 1 ELSE 0 END) AS zero FROM inventory WHERE store_id=?',(store_id,)).fetchone()
    experiments=[dict(r) for r in db.execute('SELECT id,title,hypothesis,metric,baseline,result,status,notes,created_at FROM experiments WHERE store_id=? ORDER BY updated_at DESC LIMIT 25',(store_id,))]
    matches=[]
    seen=set()
    for item in latest_demand:
        key=(item['product'].casefold(),item['size'].casefold(),item['color'].casefold())
        if key in seen or len(matches)>=4: continue
        seen.add(key)
        if item['status'] in ('open','located'):
            options=matching_available(db,store_id,item['product'],item['size'],item['color'])
            if options:
                matches.append({'demand_id':item['id'],'product':item['product'],'size':item['size'],'matches':[{**m,'quantity':m['available']} for m in options[:2]]})
    if policy=='combined' and len(evidence['visits'])>1:
        evidence['warnings'].append('Режим объединения источников: возможен двойной учёт входов. Выберите основной источник.')
    evidence['traffic_mode']=policy
    evidence['selected_visit_sources']=list(active_sources) if active_sources else ['все источники']
    evidence['confidence']='requires_review' if evidence['warnings'] else 'no_obvious_conflicts'
    return {
      "timezone":timezone_name, "daily":trend,"zones":zone_heatmap(db,store_id,start,end),"sources":evidence,"verified_sales_from_demand":verified,
      "stock_count":stock_total['count'],"stock_zero":stock_total['zero'] or 0,
      "stock_matches":matches,"experiments":experiments,
      "period_days":days, "visitors":visitors, "purchases":purchases,
      "revenue":round(revenue,2),"conversion":percent,
      "avg_receipt":round(revenue/purchases,2) if purchases else 0,
      "delta_visitors":_delta(visitors,prev_visitors),"delta_purchases":_delta(purchases,prev_purchases),
      "delta_revenue":_delta(revenue,prev_revenue), "delta_conversion_pp":round(percent-past_percent,1),
      "hourly":hourly,"reasons":reasons,"surveys_count":responses["n"],
      "rating":round(responses["rating"],1) if responses["rating"] is not None else 0,
      "signals":signals,"top_demand":top_demand,"latest_demand":latest_demand,
      "latest_surveys":latest_surveys,"demand_status":demand_status,
      "recommendations":recommendations,
      "methodology": "Посетители — количество зарегистрированных входов, не уникальные люди. Покупки — количество кассовых чеков. Конверсия условная: чеки / входы. Опросы — добровольная нерепрезентативная выборка."
    }


def _delta(value: float, previous: float) -> float | None:
    return round((value/previous - 1)*100,1) if previous else None
