"""R1.0 anonymous pulse retention cleanup, dry-run by default.

Uses each store's existing survey_retention_days (7-365). Run with --apply to
physically remove raw per-response events. Aggregated campaign answer totals
are derived on query; expired answers disappear from totals after cleanup.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timedelta,timezone
from backend.database import connect

def purge(apply:bool=False)->dict:
    deleted=0;by_store=[]
    with connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pulse_responses_r10'").fetchone():
            return {'total':0,'stores':[],'applied':False}
        stores=db.execute('SELECT id,slug,survey_retention_days FROM stores').fetchall()
        if apply:db.execute('BEGIN IMMEDIATE')
        try:
            for store in stores:
                days=max(7,min(365,int(store['survey_retention_days'] or 90)))
                cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
                count=db.execute('SELECT COUNT(*) FROM pulse_responses_r10 WHERE store_id=? AND created_at<?',
                                 (store['id'],cutoff)).fetchone()[0]
                if count and apply:db.execute('DELETE FROM pulse_responses_r10 WHERE store_id=? AND created_at<?',(store['id'],cutoff))
                deleted+=count
                by_store.append({'slug':store['slug'],'retention_days':days,'eligible':count})
            if apply:db.commit()
        except Exception:
            db.rollback();raise
    return {'total':deleted,'stores':by_store,'applied':apply}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Delete expired responses (otherwise dry-run)')
    args=parser.parse_args()
    import json
    print(json.dumps(purge(args.apply),ensure_ascii=False,indent=2))
