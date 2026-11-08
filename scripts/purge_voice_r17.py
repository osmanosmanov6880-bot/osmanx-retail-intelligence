"""Purge anonymous Voice Studio responses and open events by store retention policy.

Usage: python -m scripts.purge_voice_r17 [--apply]
Dry-run by default. Keeps aggregated decision snapshots and audit events; those
remain separately auditable after raw anonymous observations expire.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta, timezone

from backend.database import connect
from backend.r17 import ensure_schema


def purge(db:sqlite3.Connection, *, apply:bool=False, now:datetime|None=None)->list[dict]:
    timestamp=now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:raise ValueError('now must be timezone aware')
    report=[]
    for s in db.execute('SELECT id,slug,survey_retention_days FROM stores ORDER BY id').fetchall():
        retention=max(7,min(365,int(s['survey_retention_days'])))
        cutoff=(timestamp.astimezone(timezone.utc)-timedelta(days=retention)).isoformat(timespec='seconds')
        responses=db.execute('SELECT COUNT(*) FROM voice_responses_r17 WHERE store_id=? AND submitted_at<?',(s['id'],cutoff)).fetchone()[0]
        opens=db.execute('''SELECT COUNT(*) FROM voice_opens_r17
            WHERE placement_id IN (SELECT id FROM voice_placements_r17 WHERE store_id=?) AND opened_at<?''',
            (s['id'],cutoff)).fetchone()[0]
        report.append({'store':s['slug'],'retention_days':retention,'responses':responses,'opens':opens,'cutoff':cutoff})
    if apply:
        try:
            db.execute('BEGIN IMMEDIATE')
            for row in report:
                sid=db.execute('SELECT id FROM stores WHERE slug=?',(row['store'],)).fetchone()['id']
                db.execute('DELETE FROM voice_responses_r17 WHERE store_id=? AND submitted_at<?',(sid,row['cutoff']))
                db.execute('''DELETE FROM voice_opens_r17
                  WHERE placement_id IN (SELECT id FROM voice_placements_r17 WHERE store_id=?) AND opened_at<?''',
                  (sid,row['cutoff']))
            db.commit()
        except Exception:
            db.rollback();raise
    return report


def main():
    parser=argparse.ArgumentParser(description='OSMANX Voice Studio retention cleanup (dry-run by default)')
    parser.add_argument('--apply',action='store_true',help='Permanently delete qualifying anonymous observations')
    opts=parser.parse_args()
    with connect() as db:
        ensure_schema(db)
        records=purge(db,apply=opts.apply)
    print('Applied' if opts.apply else 'Dry-run')
    for r in records:print(f"{r['store']}: responses={r['responses']} opens={r['opens']} retention={r['retention_days']}d")

if __name__=='__main__':main()
