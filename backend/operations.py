"""Evidence-based store data quality report, scoped to one authorized store."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from backend.database import now_iso


def quality_report(db: sqlite3.Connection, store: sqlite3.Row, days: int=7) -> dict:
    store_id=store['id']
    begin=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
    recent=(datetime.now(timezone.utc)-timedelta(hours=24)).isoformat(timespec='seconds')
    def grouped(table: str) -> list[dict]:
        return [dict(row) for row in db.execute(
            f'SELECT source,COUNT(*) events,SUM(quantity) total,MAX(occurred_at) last_event FROM {table} '
            'WHERE store_id=? AND occurred_at>=? GROUP BY source ORDER BY total DESC',
            (store_id,begin))]
    visits=grouped('visits')
    sales=[dict(x) for x in db.execute('SELECT source,COUNT(*) events,COUNT(*) total,MAX(occurred_at) last_event '
                                 'FROM sales WHERE store_id=? AND occurred_at>=? GROUP BY source ORDER BY total DESC',
                                 (store_id,begin))]
    def total(items):return sum(row['total'] or 0 for row in items)
    surveys=db.execute('SELECT COUNT(*) n,MAX(created_at) recent FROM surveys WHERE store_id=? AND created_at>=?',
                       (store_id,begin)).fetchone()
    demands=db.execute("SELECT COUNT(*) n FROM demand WHERE store_id=? AND status IN ('open','located','notified')",
                       (store_id,)).fetchone()['n']
    devices=[dict(row) for row in db.execute('''SELECT d.public_id,d.name,d.kind,d.active,d.generation,
       MAX(e.received_at) last_seen,COUNT(e.id) accepted_events FROM devices d
       LEFT JOIN device_events e ON e.device_id=d.id AND e.received_at>=?
       WHERE d.store_id=? GROUP BY d.id ORDER BY d.id''',(begin,store_id))]
    pos=[dict(row) for row in db.execute('''SELECT p.public_id,p.name,p.active,p.generation,
       MAX(e.received_at) last_seen,COUNT(e.id) accepted_events FROM pos_sources p
       LEFT JOIN pos_events e ON e.source_id=p.id AND e.received_at>=?
       WHERE p.store_id=? GROUP BY p.id ORDER BY p.id''',(begin,store_id))]
    warnings=[]
    def warn(code,level,message):warnings.append({'code':code,'level':level,'message':message})
    if not visits:warn('no_visits','warning','No visitor events in selected period')
    if not sales:warn('no_sales','warning','No receipts in selected period')
    if store['traffic_mode']=='combined' and len(visits)>1:
        warn('mixed_traffic','warning','Combined traffic contains multiple sources; potential double counting')
    for device in devices:
        if device['active'] and (not device['last_seen'] or device['last_seen']<recent):
            warn('stale_sensor','warning',f"Sensor {device['name']} has no accepted event in last 24 hours")
    for source in pos:
        if source['active'] and (not source['last_seen'] or source['last_seen']<recent):
            warn('stale_pos','warning',f"POS source {source['name']} has no accepted receipt in last 24 hours")
    if total(visits) and total(sales)>total(visits):
        warn('conversion_above_100','critical','Receipt count exceeds visitor count; check accounting sources')
    if not surveys['n']:
        warn('no_surveys','info','No customer feedback in selected period')
    return {'store':store['slug'],'period_days':days,'generated_at':now_iso(),
            'visits':{'total':total(visits),'sources':visits},
            'sales':{'total':total(sales),'sources':sales},
            'surveys':{'total':surveys['n'],'last_response':surveys['recent']},
            'unresolved_demand':demands,'devices':devices,'pos_sources':pos,
            'warnings':warnings,
            'note':'Warnings signal data collection quality; they do not prove lost sales.'}
