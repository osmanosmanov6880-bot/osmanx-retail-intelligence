"""Transparent retail KPIs. Counts are events, not unique identified customers."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from sqlite3 import Connection

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


def dashboard(db: Connection, store_id: int, days: int = 30) -> dict:
    # Day boundaries in UTC, including current day. No unique-person claim.
    end_dt = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    start_dt = end_dt - timedelta(days=days)
    prev_dt = start_dt - timedelta(days=days)
    start, end, prev = (value.isoformat(timespec="seconds") for value in (start_dt, end_dt, prev_dt))
    visitors = _aggregate(db,"visits","quantity",store_id,start,end)
    purchases = db.execute(
        "SELECT COUNT(*) AS n FROM sales WHERE store_id=? AND occurred_at>=? AND occurred_at<?",(store_id,start,end)).fetchone()["n"]
    revenue = _aggregate(db,"sales","amount_kopeks",store_id,start,end) / 100
    prev_visitors = _aggregate(db,"visits","quantity",store_id,prev,start)
    prev_purchases = db.execute("SELECT COUNT(*) AS n FROM sales WHERE store_id=? AND occurred_at>=? AND occurred_at<?",
        (store_id,prev,start)).fetchone()["n"]
    prev_revenue = _aggregate(db,"sales","amount_kopeks",store_id,prev,start) / 100

    visits_by_hour = dict(db.execute(
        "SELECT CAST(strftime('%H',occurred_at) AS INTEGER) hour, SUM(quantity) n FROM visits WHERE store_id=? AND occurred_at>=? AND occurred_at<? GROUP BY hour",
        (store_id,start,end)).fetchall())
    sales_by_hour = dict(db.execute(
        "SELECT CAST(strftime('%H',occurred_at) AS INTEGER) hour, COUNT(*) n FROM sales WHERE store_id=? AND occurred_at>=? AND occurred_at<? GROUP BY hour",
        (store_id,start,end)).fetchall())
    hourly = [{"hour": f"{hour:02}:00", "visitors":int(visits_by_hour.get(hour,0)),
               "purchases":int(sales_by_hour.get(hour,0))} for hour in range(9,22)]

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
        "SELECT id,product,size,color,status,created_at FROM demand WHERE store_id=? ORDER BY created_at DESC,id DESC LIMIT 40",(store_id,)).fetchall()]
    latest_surveys = [dict(row) for row in db.execute(
        "SELECT id,rating,purchased,reason,liked,suggestion,created_at FROM surveys WHERE store_id=? ORDER BY created_at DESC,id DESC LIMIT 30",(store_id,)).fetchall()]
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
    return {
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
