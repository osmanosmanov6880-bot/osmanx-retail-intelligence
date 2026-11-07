"""Retention operations for voluntary kiosk feedback; raw answers are removable."""
from __future__ import annotations
import sqlite3
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from backend.database import now_iso


def reward_allowance(db:sqlite3.Connection,store:sqlite3.Row) -> bool:
    """Count rewards using the store's local calendar day, never on client time."""
    limit=store['reward_daily_limit']
    if limit<=0:
        return False
    tz=ZoneInfo(store['timezone'])
    local_now=datetime.now(tz)
    start=local_now.replace(hour=0,minute=0,second=0,microsecond=0)
    end=start+timedelta(days=1)
    start_utc=start.astimezone(timezone.utc).isoformat(timespec='seconds')
    end_utc=end.astimezone(timezone.utc).isoformat(timespec='seconds')
    count=db.execute('SELECT COUNT(*) n FROM rewards WHERE store_id=? AND created_at>=? AND created_at<?',
                     (store['id'],start_utc,end_utc)).fetchone()['n']
    return count<limit


def purge_expired_feedback(db:sqlite3.Connection,*,dry_run:bool=True) -> dict:
    """Delete expired survey text and linked reward codes; no full-video/person data exists here."""
    results=[]
    for store in db.execute('SELECT id,slug,survey_retention_days FROM stores').fetchall():
        cutoff=(datetime.now(timezone.utc)-timedelta(days=store['survey_retention_days'])).isoformat(timespec='seconds')
        ids=[r['id'] for r in db.execute('SELECT id FROM surveys WHERE store_id=? AND created_at<?',(store['id'],cutoff))]
        if not dry_run and ids:
            db.execute('DELETE FROM rewards WHERE store_id=? AND survey_id IN (SELECT id FROM surveys WHERE store_id=? AND created_at<?)',
                       (store['id'],store['id'],cutoff))
            db.execute('DELETE FROM surveys WHERE store_id=? AND created_at<?',(store['id'],cutoff))
        results.append({'store':store['slug'],'eligible':len(ids),'retention_days':store['survey_retention_days']})
    if not dry_run: db.commit()
    return {'dry_run':dry_run,'stores':results,'purged':sum(x['eligible'] for x in results) if not dry_run else 0}
