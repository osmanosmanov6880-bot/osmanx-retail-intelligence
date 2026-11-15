"""R2.3 isolated SQLite security audits: no mocks for query or digest semantics."""
from __future__ import annotations
import hashlib
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.r23_core import authorization_findings,evidence_findings,integrity_report,sha_text


def schema():
    db=sqlite3.connect(':memory:')
    db.row_factory=sqlite3.Row
    db.executescript('''
    CREATE TABLE organizations(id INTEGER PRIMARY KEY,name TEXT);
    CREATE TABLE stores(id INTEGER PRIMARY KEY,slug TEXT,organization_id INTEGER);
    CREATE TABLE users(id INTEGER PRIMARY KEY,organization_id INTEGER,role TEXT,active INTEGER);
    CREATE TABLE user_store_access(user_id INTEGER,store_id INTEGER);
    CREATE TABLE devices(id INTEGER PRIMARY KEY,store_id INTEGER,organization_id INTEGER);
    CREATE TABLE readiness_days_r20(id INTEGER PRIMARY KEY,organization_id INTEGER,store_id INTEGER,status TEXT,requested_by INTEGER,reviewed_by INTEGER);
    CREATE TABLE readiness_reviews_r20(readiness_id INTEGER,payload_json TEXT,payload_sha TEXT,reviewer_id INTEGER);
    CREATE TABLE pilots_r15(id INTEGER PRIMARY KEY,organization_id INTEGER,store_id INTEGER,status TEXT);
    CREATE TABLE assurance_pilot_starts_r21(pilot_id INTEGER,organization_id INTEGER,store_id INTEGER,preflight_json TEXT,preflight_sha TEXT);
    CREATE TABLE rollout_waves_r22(id INTEGER PRIMARY KEY,organization_id INTEGER);
    CREATE TABLE rollout_sites_r22(wave_id INTEGER,store_id INTEGER);
    CREATE TABLE rollout_stage_proofs_r22(id INTEGER PRIMARY KEY,wave_id INTEGER,stage INTEGER,payload_json TEXT,payload_sha TEXT);
    INSERT INTO organizations VALUES(1,'OSMANX'),(2,'other');
    INSERT INTO stores VALUES(1,'central',1),(2,'other-store',2);
    INSERT INTO users VALUES(1,1,'owner',1),(2,2,'owner',1);
    INSERT INTO user_store_access VALUES(1,1);
    INSERT INTO devices VALUES(1,1,1);
    ''')
    return db


def test_empty_clean_report_no_false_positive():
    db=schema();report=integrity_report(db,1,1)
    assert report['status']=='no_detected_integrity_faults'
    assert report['blocking']==0


def test_detect_cross_tenant_staff_and_device():
    db=schema();db.execute('INSERT INTO user_store_access VALUES(2,1)')
    db.execute('INSERT INTO devices VALUES(3,1,2)')
    items=authorization_findings(db,1,1)
    assert {x['code'] for x in items}=={'cross_org_grant','cross_org_device'}
    assert all('email' not in str(v) for v in items)


def test_readiness_snapshot_tamper_and_review_conflict():
    db=schema();db.execute("INSERT INTO readiness_days_r20 VALUES(10,1,1,'reviewed',1,1)")
    db.execute("INSERT INTO readiness_reviews_r20 VALUES(10,?,?,1)",('real','wrong'))
    codes={x['code'] for x in evidence_findings(db,1,1)}
    assert codes=={'readiness_tampered','readiness_self_review'}


def test_orphan_running_pilot_blocks_and_draft_does_not():
    db=schema();db.execute("INSERT INTO pilots_r15 VALUES(2,1,1,'draft'),(3,1,1,'running')")
    issues=evidence_findings(db,1,1)
    assert [(x['code'],x['subject']) for x in issues]==[('pilot_missing_start_proof','3')]


def test_valid_start_proof_and_rollout_stage_hash():
    db=schema();db.execute("INSERT INTO pilots_r15 VALUES(9,1,1,'running')")
    db.execute('INSERT INTO assurance_pilot_starts_r21 VALUES(?,?,?,?,?)',
               (9,1,1,'real',sha_text('real')))
    db.execute('INSERT INTO rollout_waves_r22 VALUES(8,1)')
    db.execute('INSERT INTO rollout_sites_r22 VALUES(8,1)')
    db.execute('INSERT INTO rollout_stage_proofs_r22 VALUES(14,8,1,?,?)',('actual',sha_text('actual')))
    assert evidence_findings(db,1,1)==[]
    db.execute("UPDATE rollout_stage_proofs_r22 SET payload_json='altered' WHERE id=14")
    assert any(x['code']=='stage_tampered' for x in evidence_findings(db,1,1))


def test_foreign_store_hidden_for_current_tenant():
    db=schema();db.execute("INSERT INTO pilots_r15 VALUES(22,2,2,'running')")
    db.execute("INSERT INTO readiness_days_r20 VALUES(12,2,2,'reviewed',1,2)")
    report=integrity_report(db,1,1)
    assert report['blocking']==0


def test_different_organization_store_not_accepted():
    db=schema()
    try:integrity_report(db,1,2)
    except ValueError:pass
    else:raise AssertionError('Cross-organization store was accepted')
