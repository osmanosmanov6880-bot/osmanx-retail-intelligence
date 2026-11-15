"""Non-destructive backup recovery drill for OSMANX SQLite.

python -m scripts.r23_recovery_drill --backup /data/backups/retail-xxx.sqlite3
python -m scripts.r23_recovery_drill --backup /data/backups/retail-xxx.sqlite3 --record

Only restores into a disposable temporary directory. Never touches the live DB.
--record writes a 0600 manifest alongside the backup for owner-only readiness UI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.backup_db import inspect_backup, restore_backup


def digest_file(path:Path)->str:
    d=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            d.update(block)
    return d.hexdigest()


def _schema_and_counts(path: Path)->dict:
    """Compare SQL schema and all actual row counts, never reading customer data into report."""
    with sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True) as db:
        schema=[(row[0],row[1]) for row in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        sizes={}
        logical=hashlib.sha256()
        for name,_ in schema:
            quoted='"'+name.replace('"','""')+'"'
            count=0
            logical.update((name+'\n').encode('utf-8'))
            for row in db.execute(f'SELECT * FROM {quoted}'):
                # Include all SQLite cell values (including BLOBs); do not export rows.
                converted=[{'blob_hex':v.hex()} if isinstance(v,bytes) else v for v in row]
                logical.update((json.dumps(converted,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8'))
                count+=1
            sizes[name]=count
    return {'schema_hash':hashlib.sha256(json.dumps(schema,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest(),
            'row_counts':sizes,'logical_sha':logical.hexdigest()}


def run_drill(backup:Path,record:bool=False)->dict:
    if backup.is_symlink():raise ValueError('Symlink backup is forbidden')
    backup=backup.resolve(strict=True)
    if not backup.name.startswith('retail-') or backup.suffix!='.sqlite3':
        raise ValueError('Use a named retail-*.sqlite3 backup only')
    manifest=backup.with_suffix('.json')
    if not manifest.is_file():raise ValueError('Backup manifest is required')
    info=inspect_backup(backup)
    saved=json.loads(manifest.read_text(encoding='utf-8'))
    if saved.get('sha256')!=info['sha256']:
        raise ValueError('Manifest SHA-256 mismatch; refusing recovery drill')
    reference=_schema_and_counts(backup)
    with tempfile.TemporaryDirectory(prefix='osmanx-r23-recovery-') as temp:
        restored=Path(temp)/'restored.sqlite3'
        restore_backup(backup,restored,confirm=True)
        replay=inspect_backup(restored)
        comparable=_schema_and_counts(restored)
        if comparable!=reference:
            raise ValueError('Restored schema or row counts differ from source backup')
        # A SQLite backup API may update file metadata; compare logical structure,
        # and report the real restored bytes digest separately.
        restored_file_sha=replay['sha256']
    report={'ok':True,'backup_sha':info['sha256'],'restored_sha':restored_file_sha,
            'logical_matches':True,'logical_sha':reference['logical_sha'],'schema_sha':reference['schema_hash'],
            'table_count':len(reference['row_counts']),'checked_at':datetime.now(timezone.utc).isoformat(),
            'description':'Schema and per-table row counts matched after an actual temporary SQLite restore; no production DB was altered.'}
    if record:
        target=backup.with_suffix('.drill.json')
        if target.is_symlink():raise ValueError('Drill manifest target is a symlink')
        tmp=target.with_name(target.name+'.tmp-'+os.urandom(6).hex())
        try:
            fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as output:
                json.dump(report,output,ensure_ascii=False,indent=2)
                output.flush();os.fsync(output.fileno())
            os.replace(tmp,target)
        finally:tmp.unlink(missing_ok=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup',required=True,type=Path)
    parser.add_argument('--record',action='store_true',help='Write reviewed drill receipt next to the backup')
    opts=parser.parse_args()
    print(json.dumps(run_drill(opts.backup,opts.record),indent=2,ensure_ascii=False))

if __name__=='__main__':main()
