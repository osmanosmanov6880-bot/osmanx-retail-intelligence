"""Actual SQLite snapshot-to-temporary-DB verification, no production DB writes."""
from pathlib import Path
import json
import os
import sqlite3
import sys
import tempfile
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.backup_db import make_backup
from scripts.r23_recovery_drill import run_drill


def _db(path):
    with sqlite3.connect(path) as db:
        for table in ('stores','sales','visits','users','organizations','surveys'):
            db.execute(f'CREATE TABLE {table}(id INTEGER PRIMARY KEY, text TEXT)')
            db.execute(f'INSERT INTO {table}(text) VALUES(?)',(table+' значение',))
        db.commit()


def test_restore_drill_and_manifest_are_consistent(tmp_path):
    source=tmp_path/'live.sqlite3';_db(source)
    saved=make_backup(source,tmp_path/'backups')
    original=source.read_bytes()
    tested=run_drill(saved,record=True)
    assert tested['ok'] and tested['logical_matches']
    assert tested['backup_sha'] and tested['restored_sha'] and tested['logical_sha']
    assert tested['table_count']==6
    assert saved.with_suffix('.drill.json').is_file()
    assert source.read_bytes()==original
    assert json.loads(saved.with_suffix('.drill.json').read_text())['logical_sha']==tested['logical_sha']


def test_tampered_manifest_is_denied(tmp_path):
    source=tmp_path/'live.sqlite3';_db(source)
    saved=make_backup(source,tmp_path/'backups')
    saved.with_suffix('.json').write_text('{"sha256":"false"}')
    with pytest.raises(ValueError,match='Manifest SHA-256 mismatch'):
        run_drill(saved,record=True)
    assert not saved.with_suffix('.drill.json').exists()


def test_symlink_backup_is_refused(tmp_path):
    source=tmp_path/'live.sqlite3';_db(source)
    saved=make_backup(source,tmp_path/'backups')
    shortcut=tmp_path/'retail-symlink.sqlite3';shortcut.symlink_to(saved)
    with pytest.raises(ValueError,match='Symlink'):
        run_drill(shortcut,record=False)
