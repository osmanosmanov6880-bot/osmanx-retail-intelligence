"""Offline CLI for consistent SQLite backups and verified offline restore.

Usage: python -m scripts.backup_db backup --destination /safe/backups --keep 7
       python -m scripts.backup_db verify --file /safe/backups/retail-xxx.sqlite3
       python -m scripts.backup_db restore --file /safe/backups/retail-xxx.sqlite3 --confirm-offline
For restore, stop the application first; the command will refuse if it can
acquire no exclusive lock on the current DB or on the backup target.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime,timezone
from pathlib import Path

from backend.database import DB_PATH


def inspect_backup(path: Path) -> dict:
    if not path.is_file():raise ValueError('Backup file not found')
    connection=sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True)
    try:
        integrity=connection.execute('PRAGMA integrity_check').fetchone()[0]
        foreign_keys=connection.execute('PRAGMA foreign_key_check').fetchall()
        expected={'stores','sales','visits','users','organizations','surveys'}
        tables={x[0] for x in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if integrity!='ok' or foreign_keys or not expected.issubset(tables):
            raise ValueError('SQLite backup integrity, foreign keys or schema check failed')
        sha=hashlib.sha256()
        with path.open('rb') as source:
            for block in iter(lambda:source.read(1024*1024),b''):
                sha.update(block)
        return {'ok':True,'bytes':path.stat().st_size,
                'sha256':sha.hexdigest(),'tables':len(tables)}
    finally:connection.close()


def make_backup(source: Path, destination: Path, keep: int=7) -> Path:
    if keep<1 or keep>365:raise ValueError('Retention must be 1..365')
    destination.mkdir(parents=True,exist_ok=True)
    os.chmod(destination,0o700)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target=destination/f'retail-{stamp}-{os.urandom(3).hex()}.sqlite3'
    fd,temp_name=tempfile.mkstemp(prefix='.tmp-retail-',suffix='.sqlite3',dir=destination)
    os.close(fd)
    temp=Path(temp_name)
    try:
        os.chmod(temp,0o600)
        read=sqlite3.connect(f'file:{source.as_posix()}?mode=ro',uri=True)
        try:
            with sqlite3.connect(temp) as write:read.backup(write)
        finally:read.close()
        report=inspect_backup(temp)
        os.replace(temp,target)
        manifest=target.with_suffix('.json')
        manifest.write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),**report},indent=2),encoding='utf-8')
        os.chmod(manifest,0o600)
        old=sorted(destination.glob('retail-*.sqlite3'),reverse=True)
        for obsolete in old[keep:]:
            obsolete.unlink()
            obsolete.with_suffix('.json').unlink(missing_ok=True)
        return target
    finally:temp.unlink(missing_ok=True)


def restore_backup(backup: Path,target: Path,confirm: bool=False) -> None:
    if not confirm:raise ValueError('Pass --confirm-offline after stopping all application workers')
    report=inspect_backup(backup)
    manifest=backup.with_suffix('.json')
    if manifest.is_file():
        expected=json.loads(manifest.read_text(encoding='utf-8'))['sha256']
        if expected!=report['sha256']:raise ValueError('Backup digest mismatch')
    if target.is_file():
        current=sqlite3.connect(target,timeout=0.25)
        try:
            current.execute('BEGIN EXCLUSIVE')
            current.execute('ROLLBACK')
        except sqlite3.OperationalError as exc:raise ValueError('Database is busy; stop the application') from exc
        finally:current.close()
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,temp_name=tempfile.mkstemp(prefix='.restore-',suffix='.sqlite3',dir=target.parent)
    os.close(fd)
    tmp=Path(temp_name)
    try:
        os.chmod(tmp,0o600)
        read=sqlite3.connect(f'file:{backup.as_posix()}?mode=ro',uri=True)
        try:
            with sqlite3.connect(tmp) as write:read.backup(write)
        finally:read.close()
        inspect_backup(tmp)
        if target.exists():
            safety=target.with_name(target.name+'.pre-restore')
            if safety.exists():raise ValueError('Remove or archive the previous .pre-restore safety copy')
            # A consistent SQLite snapshot is essential if the existing DB uses WAL.
            old=sqlite3.connect(target,timeout=0.25)
            try:
                with sqlite3.connect(safety) as safety_db:
                    old.backup(safety_db)
            finally:old.close()
            os.chmod(safety,0o600)
            inspect_backup(safety)
            for suffix in ('-wal','-shm'):
                Path(str(target)+suffix).unlink(missing_ok=True)
        os.replace(tmp,target)
    finally:tmp.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='action',required=True)
    backup=subs.add_parser('backup');backup.add_argument('--destination',type=Path,required=True)
    backup.add_argument('--keep',type=int,default=7)
    check=subs.add_parser('verify');check.add_argument('--file',type=Path,required=True)
    restore=subs.add_parser('restore');restore.add_argument('--file',type=Path,required=True)
    restore.add_argument('--confirm-offline',action='store_true')
    args=parser.parse_args()
    if args.action=='backup':print(make_backup(DB_PATH,args.destination,args.keep))
    elif args.action=='verify':print(json.dumps(inspect_backup(args.file),indent=2))
    else:restore_backup(args.file,DB_PATH,args.confirm_offline);print('Restore complete; restart one app worker')

if __name__=='__main__':main()
