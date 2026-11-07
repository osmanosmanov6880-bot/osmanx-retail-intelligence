"""R0.4 acceptance: self-service security, paired kiosks, signed POS and operations."""
from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def site(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE','0')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','bootstrap-super-secret-2026')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local')
    monkeypatch.setenv('OSMANX_SESSION_SECRET','session-master-secret-super-long-123456789')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET','device-master-secret-super-long-123456789')
    import backend.database as db
    import backend.app as api
    importlib.reload(db)
    importlib.reload(api)
    with TestClient(api.app) as client:
        token=client.post('/api/auth/login',json={'email':'owner@osmanx.local','password':'bootstrap-super-secret-2026'}).json()['token']
        yield client,{'Authorization':'Bearer '+token},db,tmp_path


def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')


def send_pos(client,source,secret,receipts,timestamp=None,raw=None):
    stamp=str(int(time.time()) if timestamp is None else timestamp)
    raw=raw or json.dumps({'receipts':receipts},separators=(',',':')).encode()
    sig=hmac.new(secret.encode(),stamp.encode()+b'\n'+source.encode()+b'\n'+raw,hashlib.sha256).hexdigest()
    return client.post('/api/ingest/pos',content=raw,headers={
        'X-OSMANX-Source':source,'X-OSMANX-Timestamp':stamp,'X-OSMANX-Signature':sig,
        'Content-Type':'application/json'})


def test_password_change_revokes_old_token_and_can_sign_out_everywhere(site):
    client,old,_,_=site
    assert client.get('/api/ready').json()['status']=='ready'
    assert client.post('/api/auth/change-password',headers=old,json={'current_password':'wrong',
                      'new_password':'a-much-better-password'}).status_code==401
    response=client.post('/api/auth/change-password',headers=old,json={
        'current_password':'bootstrap-super-secret-2026','new_password':'much-better-password-2026!'})
    assert response.status_code==200,response.text
    new={'Authorization':'Bearer '+response.json()['token']}
    assert client.get('/api/admin/me',headers=old).status_code==401
    assert client.get('/api/admin/me',headers=new).status_code==200
    assert client.post('/api/auth/login',json={'password':'bootstrap-super-secret-2026'}).status_code==401
    assert client.post('/api/auth/login',json={'password':'much-better-password-2026!'}).status_code==200
    assert client.post('/api/auth/logout-all',headers=new).status_code==200
    assert client.get('/api/admin/me',headers=new).status_code==401
    logs=client.post('/api/auth/login',json={'password':'much-better-password-2026!'}).json()
    assert logs['token']
    headers=client.get('/api/ready').headers
    assert headers['referrer-policy']=='no-referrer'
    assert headers['x-content-type-options']=='nosniff'


def test_kiosk_pairing_rotation_and_public_fallback(site):
    client,root,_,_=site
    payload={'rating':4,'purchased':False,'reason':'size','request_id':'kiosk-first-unique-identifier'}
    assert client.post('/api/public/survey/central',json=payload).status_code==201
    paired=client.post('/api/admin/kiosks/central/rotate',headers=root).json()
    assert len(paired['token'])>=40
    assert client.get('/api/public/store/central').json()['kiosk_required'] is True
    assert client.post('/api/public/survey/central',json={**payload,'request_id':'kiosk-second-unique-id'}).status_code==401
    headers={'X-OSMANX-Kiosk':paired['token']}
    good={**payload,'request_id':'kiosk-third-unique-identifier'}
    assert client.post('/api/public/survey/central',json=good,headers=headers).status_code==201
    assert client.post('/api/public/survey/central',json=good,headers=headers).json()['duplicate'] is True
    refreshed=client.post('/api/admin/kiosks/central/rotate',headers=root).json()
    assert refreshed['generation']==2
    assert client.post('/api/public/survey/central',json={**payload,'request_id':'kiosk-rotated-unique-id'},headers=headers).status_code==401
    assert client.post('/api/public/survey/central',json={**payload,'request_id':'kiosk-rotated-unique-id'},headers={'X-OSMANX-Kiosk':refreshed['token']}).status_code==201
    assert client.delete('/api/admin/kiosks/central',headers=root).status_code==200
    assert client.get('/api/public/store/central').json()['kiosk_required'] is False
    assert client.post('/api/public/survey/central',json={**payload,'request_id':'kiosk-unpaired-unique-id'}).status_code==201


def test_kiosk_and_pos_scoped_by_org(site):
    client,root,db_module,_=site
    from scripts.provision_tenant import provision
    with db_module.connect() as db:
        provision(db,slug='studio',name='Studio',store_slug='studio-main',email='studio@test.example',password='studio-pass-2026-strong')
    other_token=client.post('/api/auth/login',json={'email':'studio@test.example','password':'studio-pass-2026-strong'}).json()['token']
    other={'Authorization':'Bearer '+other_token}
    assert client.post('/api/admin/kiosks/central/rotate',headers=other).status_code==404
    assert client.post('/api/admin/pos/sources',headers=other,json={'slug':'central','name':'Unknown store POS'}).status_code==404
    assert client.get('/api/admin/pos/sources?slug=central',headers=other).status_code==404
    assert client.get('/api/admin/operations/quality?slug=central',headers=other).status_code==404
    assert client.post('/api/admin/kiosks/studio-main/rotate',headers=other).status_code==200
    assert client.post('/api/public/survey/central',json={'rating':4,'purchased':True}).status_code==201
    assert client.post('/api/public/survey/studio-main',json={'rating':4,'purchased':True}).status_code==401
    assert client.get('/api/admin/operations/quality?slug=studio-main',headers=root).status_code==404


def test_signed_pos_replay_conflict_atomicity_rotation_and_revoke(site):
    client,root,_,_=site
    created=client.post('/api/admin/pos/sources',headers=root,json={'slug':'central','name':'Main cash register'})
    assert created.status_code==201,created.text
    source=created.json(); sid=source['source_id'];secret=source['secret']
    records=[{'external_id':'test-rcpt-0001','amount_rub':'1199.99','occurred_at':now()},
             {'external_id':'test-rcpt-0002','amount_rub':'2000','occurred_at':now()}]
    assert client.post('/api/ingest/pos',json={'receipts':records}).status_code==401
    assert send_pos(client,sid,'wrong-secret',records).status_code==401
    assert send_pos(client,sid,secret,records,timestamp=int(time.time())-400).status_code==401
    first=send_pos(client,sid,secret,records)
    assert first.status_code==201,first.text
    assert first.json()=={'added':2,'duplicates':0,'total':2}
    second=send_pos(client,sid,secret,records)
    assert second.status_code==201 and second.json()['duplicates']==2
    assert client.get('/api/admin/dashboard?slug=central',headers=root).json()['purchases']==2
    mixed=[{'external_id':'test-rcpt-0003','amount_rub':800,'occurred_at':now()},
           {**records[0],'amount_rub':'1234.00'}]
    assert send_pos(client,sid,secret,mixed).status_code==409
    assert client.get('/api/admin/dashboard?slug=central',headers=root).json()['purchases']==2
    assert send_pos(client,sid,secret,[{**records[0],'external_id':'test-new-0004','amount_rub':1.234}]).status_code==422
    assert send_pos(client,sid,secret,[{**records[0],'external_id':'test-new-0005','occurred_at':'2026-01-01T00:00:00Z'}]).status_code==422
    assert send_pos(client,sid,secret,[records[0],records[0]]).status_code==422
    items=client.get('/api/admin/pos/sources?slug=central',headers=root).json()
    assert len(items)==1 and items[0]['accepted_events']==2 and 'secret' not in items[0]
    rotated=client.post(f'/api/admin/pos/sources/{sid}/rotate',headers=root).json()
    assert send_pos(client,sid,secret,[{**records[0],'external_id':'test-new-0006'}]).status_code==401
    assert send_pos(client,sid,rotated['secret'],[{**records[0],'external_id':'test-new-0007'}]).status_code==201
    assert client.delete(f'/api/admin/pos/sources/{sid}',headers=root).status_code==200
    assert send_pos(client,sid,rotated['secret'],[{**records[0],'external_id':'test-new-0008'}]).status_code==401


def test_quality_monitor_observes_sources_and_stale_sensors(site):
    client,root,_,_=site
    before=client.get('/api/admin/operations/quality',headers=root)
    assert before.status_code==200,before.text
    assert any(w['code']=='no_visits' for w in before.json()['warnings'])
    client.post('/api/admin/events',headers=root,json={'slug':'central','kind':'entry','quantity':2})
    client.post('/api/admin/events',headers=root,json={'slug':'central','kind':'sale','quantity':1,'amount_rub':1500})
    source=client.post('/api/admin/pos/sources',headers=root,json={'slug':'central','name':'Stale register'}).json()
    device=client.post('/api/admin/devices',headers=root,json={'slug':'central','name':'Stale entrance','kind':'traffic'}).json()
    report=client.get('/api/admin/operations/quality?days=7',headers=root).json()
    assert report['visits']['total']==2
    assert report['sales']['total']==1
    assert {'stale_sensor','stale_pos'}.issubset({x['code'] for x in report['warnings']})
    assert report['pos_sources'][0]['public_id']==source['source_id']
    assert report['devices'][0]['public_id']==device['device_id']
    assert client.get('/api/admin/operations/quality?days=12',headers=root).status_code==422


def test_backup_integrity_and_offline_recovery(site,tmp_path):
    client,root,db_module,_=site
    from scripts.backup_db import make_backup,inspect_backup,restore_backup
    source=db_module.DB_PATH
    archive=tmp_path/'archive'
    first=make_backup(source,archive,keep=2)
    report=inspect_backup(first)
    assert report['ok'] and report['bytes']>0
    client.post('/api/admin/events',headers=root,json={'slug':'central','kind':'entry','quantity':2})
    second=make_backup(source,archive,keep=2)
    third=make_backup(source,archive,keep=2)
    assert len(list(archive.glob('retail-*.sqlite3')))==2
    assert first!=third and not first.exists()
    assert second.exists()
    restore_target=tmp_path/'restored.sqlite3'
    with pytest.raises(ValueError,match='confirm'):
        restore_backup(second,restore_target)
    restore_backup(second,restore_target,True)
    assert inspect_backup(restore_target)['ok']
    # An existing target is safely backed up before replacement.
    restore_backup(third,restore_target,True)
    assert (tmp_path/'restored.sqlite3.pre-restore').exists()
    report_file=third.with_suffix('.json')
    manifest=json.loads(report_file.read_text())
    manifest['sha256']='00000000'
    report_file.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='digest'):
        restore_backup(third,tmp_path/'tamper.sqlite3',True)
