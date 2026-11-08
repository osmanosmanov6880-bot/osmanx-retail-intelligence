"""Voice Studio R1.7: authorization, immutable versions, public survey, quality and actions."""
from __future__ import annotations

import importlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FORM={
 'slug':'central','request_id':'voice-create-000001','title':'Что помогло бы вам купить?',
 'questions':[
  {'id':'purchase','title':'Удалось ли сегодня совершить покупку?', 'type':'choice',
   'options':[{'id':'yes','label':'Да, купил'},{'id':'no','label':'Нет, не купил'}]},
  {'id':'reason','title':'Что помешало покупке?', 'type':'choice',
   'options':[{'id':'size','label':'Не было размера'},{'id':'price','label':'Цена'},{'id':'other','label':'Другое'}],
   'show_if':{'question':'purchase','equals':'no'}},
  {'id':'rating','title':'Оцените посещение от 1 до 5', 'type':'rating'}
 ]}

@pytest.fixture
def site(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE','0')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','bootstrap-super-secret-2026')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local')
    monkeypatch.setenv('OSMANX_SESSION_SECRET','session-master-secret-super-long-123456789')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET','device-master-secret-super-long-123456789')
    import backend.database as database
    import backend.app as api
    importlib.reload(database)
    importlib.reload(api)
    with TestClient(api.app) as client:
        login=client.post('/api/auth/login',json={'email':'owner@osmanx.local','password':'bootstrap-super-secret-2026'})
        assert login.status_code==200,login.text
        yield client,{'Authorization':'Bearer '+login.json()['token']},database


def create(site,form=None):
    client,headers,_=site
    body={**FORM,**(form or {})}
    out=client.post('/api/admin/r17/forms',json=body,headers=headers)
    assert out.status_code==201,out.text
    fid=out.json()['id']
    pub=client.post(f'/api/admin/r17/forms/{fid}/publish',headers=headers)
    assert pub.status_code==200,pub.text
    return fid,pub.json()


def place(site,form_id,medium='qr'):
    client,headers,_=site
    p=client.post('/api/admin/r17/placements',json={'form_id':form_id,'name':'Выход у кассы','medium':medium},headers=headers)
    assert p.status_code==201,p.text
    result=p.json()
    return result,{'X-OSMANX-Voice-Key':result['secret']}


def answer(site,placement,auth,request_id,answer=None):
    client,_,_=site
    url=f"/api/voice/r17/{placement['public_id']}"
    cfg=client.get(url+'/form',headers=auth).json()
    data={'request_id':request_id,'version_hash':cfg['version_hash']}
    opened=client.post(url+'/open',json=data,headers=auth)
    assert opened.status_code==201,opened.text
    a=answer or {'purchase':'no','reason':'size','rating':4}
    return client.post(url+'/submit',json={**data,'answers':a},headers=auth)


def test_reject_unauthenticated_admin_and_unknown_public_key(site):
    c,h,_=site
    assert c.get('/api/admin/r17/forms').status_code==401
    assert c.post('/api/admin/r17/forms',json=FORM).status_code==401
    f,_=create(site);p,key=place(site,f)
    url=f"/api/voice/r17/{p['public_id']}/form"
    assert c.get(url).status_code==401
    assert c.get(url,headers={'X-OSMANX-Voice-Key':'wrong'}).status_code==401
    good=c.get(url,headers=key)
    assert good.status_code==200
    assert good.json()['questions'][1]['show_if']['question']=='purchase'
    assert 'secret' not in str(good.json())


def test_invalid_question_fields_injection_and_branching(site):
    c,h,_=site
    for bad in [
      [{'id':'email','title':'Укажите почту','type':'text'},FORM['questions'][2]],
      [{**FORM['questions'][0],'unsafe':'evil'},FORM['questions'][2]],
      [FORM['questions'][0],{**FORM['questions'][1],'show_if':{'question':'reason','equals':'size'}}],
      [FORM['questions'][0],{**FORM['questions'][0]}],
    ]:
        r=c.post('/api/admin/r17/forms',json={**FORM,'questions':bad},headers=h)
        assert r.status_code==422,r.text
    f,_=create(site);p,key=place(site,f)
    bad=answer(site,p,key,'voice-unexpected-001',{'purchase':'yes','reason':'size','rating':5})
    assert bad.status_code==422
    good=answer(site,p,key,'voice-accepted-001',{'purchase':'yes','rating':5})
    assert good.status_code==201,good.text
    injection=answer(site,p,key,'voice-injection-001',{'purchase':'no','reason':'size','rating':5,'phone':'123'})
    assert injection.status_code==422


def test_create_and_publish_idempotency_and_edit_lock(site):
    c,h,_=site
    f,v=create(site)
    duplicate=c.post('/api/admin/r17/forms',json=FORM,headers=h)
    assert duplicate.status_code==201 and duplicate.json()['duplicate']
    conflict=c.post('/api/admin/r17/forms',json={**FORM,'title':'Новый заголовок!'},headers=h)
    assert conflict.status_code==409
    again=c.post(f'/api/admin/r17/forms/{f}/publish',headers=h)
    assert again.json()['duplicate'] and again.json()['revision']==1
    before=c.get('/api/admin/r17/forms',headers=h).json()['items'][0]
    edit={**FORM,'expected_draft_hash':before['draft_hash'],'title':'Новый опрос магазина','questions':FORM['questions']+[
      {'id':'service','title':'Как вам работа консультантов?', 'type':'rating'}]}
    stale=c.patch(f'/api/admin/r17/forms/{f}',json={**edit,'expected_draft_hash':'0'*64},headers=h)
    assert stale.status_code==409
    edited=c.patch(f'/api/admin/r17/forms/{f}',json=edit,headers=h)
    assert edited.status_code==200
    versions=c.get(f'/api/admin/r17/forms/{f}/versions',headers=h).json()['items']
    assert len(versions)==1
    release=c.post(f'/api/admin/r17/forms/{f}/publish',headers=h)
    assert release.status_code==200 and release.json()['revision']==2
    versions=c.get(f'/api/admin/r17/forms/{f}/versions',headers=h).json()['items']
    assert len(versions)==2 and len(versions[1]['questions'])==3
    assert c.post(f'/api/admin/r17/forms/{f}/archive',headers=h).status_code==200
    assert c.post(f'/api/admin/r17/forms/{f}/publish',headers=h).status_code==409


def test_public_idempotency_conflict_and_missing_open(site):
    c,h,_=site;f,_=create(site);p,key=place(site,f)
    code=p['public_id'];cfg=c.get(f'/api/voice/r17/{code}/form',headers=key).json()
    payload={'request_id':'voice-session-000001','version_hash':cfg['version_hash'],'answers':{'purchase':'no','reason':'price','rating':3}}
    assert c.post(f'/api/voice/r17/{code}/submit',json=payload,headers=key).status_code==409
    first=answer(site,p,key,'voice-session-000001',payload['answers'])
    assert first.status_code==201 and not first.json()['duplicate']
    again=c.post(f'/api/voice/r17/{code}/submit',json=payload,headers=key)
    assert again.status_code==201 and again.json()['duplicate']
    diff=c.post(f'/api/voice/r17/{code}/submit',json={**payload,'answers':{'purchase':'yes','rating':4}},headers=key)
    assert diff.status_code==409


def test_public_rotation_disable_and_version_change(site):
    c,h,_=site;f,_=create(site);p,key=place(site,f)
    base=f"/api/voice/r17/{p['public_id']}"
    old=c.get(base+'/form',headers=key).json()
    rotation=c.post(f"/api/admin/r17/placements/{p['id']}/rotate",headers=h)
    assert rotation.status_code==200
    new={'X-OSMANX-Voice-Key':rotation.json()['secret']}
    assert c.get(base+'/form',headers=key).status_code==401
    assert c.get(base+'/form',headers=new).status_code==200
    draft=c.get('/api/admin/r17/forms',headers=h).json()['items'][0]
    edit=c.patch(f'/api/admin/r17/forms/{f}',headers=h,json={
      'expected_draft_hash':draft['draft_hash'],'title':'Новый вопрос после публикации',
      'questions':FORM['questions']+[{'id':'other_rating','title':'Оцените ассортимент', 'type':'rating'}]})
    assert edit.status_code==200
    c.post(f'/api/admin/r17/forms/{f}/publish',headers=h)
    assert c.post(base+'/open',headers=new,json={'request_id':'new-version-session-01',
        'version_hash':old['version_hash']}).status_code==409
    assert c.post(f"/api/admin/r17/placements/{p['id']}/disable",headers=h).status_code==200
    assert c.get(base+'/form',headers=new).status_code==404


def test_insights_are_counts_not_inferred_sales_and_csv(site):
    c,h,db=site;f,_=create(site);p,key=place(site,f)
    for i in range(4):
        r=answer(site,p,key,f'voice-insight-request-{i+1:04}',{'purchase':'no','reason':'size','rating':3})
        assert r.status_code==201,r.text
    r=answer(site,p,key,'voice-insight-request-0200',{'purchase':'yes','rating':5})
    assert r.status_code==201
    results=c.get('/api/admin/r17/insights?days=14',headers=h)
    assert results.status_code==200,results.text
    body=results.json()
    assert body['responses']==5 and body['opens']==5
    assert body['placements'][0]['completion_per_open_pct']==100.0
    reason=next(x for x in body['questions'] if x['question_id']=='reason')
    assert reason['responses']==4 and reason['counts'][0]['code']=='size'
    assert 'нерепрезентативными' in str(body['warnings'])
    csv=c.get('/api/admin/r17/insights.csv',headers=h)
    assert csv.status_code==200 and 'text/csv' in csv.headers['content-type']
    assert 'Не было размера' in csv.text
    assert c.get('/api/admin/r17/insights?days=91',headers=h).status_code==422


def test_evidence_action_minimum_and_state_history(site):
    c,h,db=site;f,_=create(site);p,key=place(site,f)
    action={'slug':'central','request_id':'voice-decision-000001','placement_id':p['id'],
            'question_id':'reason','choice':'size','action_type':'stock',
            'title':'Проверить доступность XL и подготовить дозакупку'}
    assert c.post('/api/admin/r17/actions',headers=h,json=action).status_code==409
    for i in range(3):
        assert answer(site,p,key,f'voice-action-response-{i:04}').status_code==201
    first=c.post('/api/admin/r17/actions',headers=h,json=action)
    assert first.status_code==201,first.text
    aid=first.json()['id']; assert first.json()['evidence']['support']==3
    again=c.post('/api/admin/r17/actions',headers=h,json=action)
    assert again.status_code==201 and again.json()['duplicate']
    assert c.post('/api/admin/r17/actions',headers=h,json={**action,'choice':'price'}).status_code==409
    assert c.patch(f'/api/admin/r17/actions/{aid}',headers=h,json={'status':'implemented','note':'Сразу завершили'}).status_code==409
    assert c.patch(f'/api/admin/r17/actions/{aid}',headers=h,json={'status':'investigating','note':'Проверили наличие размеров по складам'}).status_code==200
    assert c.patch(f'/api/admin/r17/actions/{aid}',headers=h,json={'status':'implemented','note':'Подтвердили обновление выкладки актом'}).status_code==200
    assert c.patch(f'/api/admin/r17/actions/{aid}',headers=h,json={'status':'dismissed','note':'Передумали закрывать'}).status_code==409
    history=c.get(f'/api/admin/r17/actions/{aid}/history',headers=h)
    assert len(history.json()['items'])==2


def test_cross_tenant_isolation_and_role_restrictions(site):
    c,h,db=site;f,_=create(site);p,key=place(site,f)
    from backend.security import hash_password
    with db.connect() as conn:
        now=datetime.now(timezone.utc).isoformat()
        conn.execute('INSERT INTO organizations(slug,name,created_at) VALUES(?,?,?)',('otherorg','Другая организация',now))
        other=conn.execute("SELECT id FROM organizations WHERE slug='otherorg'").fetchone()['id']
        conn.execute('INSERT INTO stores(slug,name,created_at,organization_id) VALUES(?,?,?,?)',('elsewhere','Другой магазин',now,other))
        conn.execute('INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                     (other,'other@osmanx.local',hash_password('valid-super-secret-2026'),'owner',now))
        conn.execute('INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                     (1,'readonly@osmanx.local',hash_password('readonly-super-secret-2026'),'viewer',now))
        conn.execute("INSERT INTO user_store_access(user_id,store_id) VALUES((SELECT id FROM users WHERE email='readonly@osmanx.local'),(SELECT id FROM stores WHERE slug='central'))")
        conn.commit()
    def login(email,password):
        x=c.post('/api/auth/login',json={'email':email,'password':password})
        assert x.status_code==200,x.text
        return {'Authorization':'Bearer '+x.json()['token']}
    foreign=login('other@osmanx.local','valid-super-secret-2026')
    viewer=login('readonly@osmanx.local','readonly-super-secret-2026')
    assert c.get('/api/admin/r17/forms?slug=central',headers=foreign).status_code==404
    assert c.get('/api/admin/r17/placements?slug=central',headers=foreign).status_code==404
    assert c.post(f'/api/admin/r17/forms/{f}/publish',headers=foreign).status_code==404
    assert c.get('/api/admin/r17/forms?slug=central',headers=viewer).status_code==200
    assert c.post('/api/admin/r17/forms',headers=viewer,json={**FORM,'request_id':'viewer-create-0001'}).status_code==403
    assert c.post(f"/api/admin/r17/placements/{p['id']}/rotate",headers=viewer).status_code==403


def test_migration_idempotent_and_retains_survey_records(site):
    c,h,db=site
    with db.connect() as conn:
        original=conn.execute("SELECT COUNT(*) FROM surveys").fetchone()[0]
        from backend.r17 import ensure_schema
        ensure_schema(conn);ensure_schema(conn)
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert conn.execute('SELECT COUNT(*) FROM surveys').fetchone()[0]==original


def test_retention_cleanup_dry_run_and_irreversible_apply(site):
    c,h,db=site;f,_=create(site);p,key=place(site,f)
    assert answer(site,p,key,'voice-retention-session-01').status_code==201
    from scripts.purge_voice_r17 import purge
    with db.connect() as conn:
        old=(datetime.now(timezone.utc)-timedelta(days=140)).isoformat(timespec='seconds')
        conn.execute("UPDATE voice_responses_r17 SET submitted_at=?",(old,))
        conn.execute("UPDATE voice_opens_r17 SET opened_at=?",(old,))
        conn.commit()
        preview=purge(conn,apply=False)
        assert preview[0]['responses']==1 and preview[0]['opens']==1
        assert conn.execute('SELECT COUNT(*) FROM voice_responses_r17').fetchone()[0]==1
        removed=purge(conn,apply=True)
        assert removed[0]['responses']==1
        assert conn.execute('SELECT COUNT(*) FROM voice_responses_r17').fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM voice_opens_r17').fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM voice_forms_r17').fetchone()[0]==1


def test_evidence_snapshot_hash_matches_stored_json(site):
    c,h,db=site;f,_=create(site);p,key=place(site,f)
    for i in range(3):assert answer(site,p,key,f'voice-proof-check-{i:04}').status_code==201
    action=c.post('/api/admin/r17/actions',headers=h,json={
        'slug':'central','request_id':'voice-proof-action-001','placement_id':p['id'],
        'question_id':'reason','choice':'size','action_type':'stock',
        'title':'Проверить наличие нужных размеров и сделать закупку'})
    assert action.status_code==201,action.text
    from backend.r17 import digest
    import json
    with db.connect() as conn:
        record=conn.execute('SELECT evidence_json,evidence_hash FROM voice_actions_r17').fetchone()
        assert digest(json.loads(record['evidence_json']))==record['evidence_hash']


def test_qr_svg_requires_valid_active_secret_and_store_role(site):
    c,h,_=site;f,_=create(site);p,key=place(site,f)
    url=f"http://testserver/static/voice_kiosk.html#{p['public_id']}.{p['secret']}"
    endpoint=f"/api/admin/r17/placements/{p['id']}/qr.svg"
    assert c.post(endpoint,json={'url':url}).status_code==401
    bad=c.post(endpoint,headers=h,json={'url':url+'-bad'})
    assert bad.status_code==422
    poisoned=c.post(endpoint,headers=h,json={'url':url.replace('testserver','bad.example')})
    assert poisoned.status_code==422
    svg=c.post(endpoint,headers=h,json={'url':url})
    assert svg.status_code==200,svg.text[:250]
    assert 'image/svg+xml' in svg.headers['content-type']
    assert b'<svg' in svg.content and b'<path' in svg.content
    assert svg.headers['cache-control']=='no-store'
