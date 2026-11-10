"""R2.2 Multi-Store Rollout: staged decisions backed by R2.0 readiness evidence.

No physical device controls, financial transactions or public deployment. Rollout
states are *recorded management decisions*, not live infrastructure changes.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.database import now_iso
from backend.security import Principal, audit, check_store_access, require_role, visible_store
from backend.retail import safe_spreadsheet_cell

SCHEMA = """
CREATE TABLE IF NOT EXISTS rollout_waves_r22 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 request_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 title TEXT NOT NULL, objective TEXT NOT NULL,
 budget_kopeks INTEGER NOT NULL CHECK(budget_kopeks>=0),
 state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','review_requested','active','paused','completed','cancelled')),
 stage INTEGER NOT NULL DEFAULT 1 CHECK(stage BETWEEN 1 AND 5),
 creator_id INTEGER NOT NULL, requested_by INTEGER,
 reviewer_id INTEGER, review_note TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(organization_id,request_id)
);
CREATE INDEX IF NOT EXISTS rollout_waves_org ON rollout_waves_r22(organization_id,state,id);
CREATE TABLE IF NOT EXISTS rollout_sites_r22 (
 id INTEGER PRIMARY KEY,
 wave_id INTEGER NOT NULL REFERENCES rollout_waves_r22(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 readiness_id INTEGER REFERENCES readiness_days_r20(id),
 evidence_sha TEXT, evidence_at TEXT,
 phase INTEGER NOT NULL CHECK(phase BETWEEN 1 AND 5),
 notes TEXT NOT NULL DEFAULT '',
 UNIQUE(wave_id,store_id)
);
CREATE INDEX IF NOT EXISTS rollout_sites_wave ON rollout_sites_r22(wave_id,phase);
CREATE TABLE IF NOT EXISTS rollout_events_r22 (
 id INTEGER PRIMARY KEY,
 wave_id INTEGER NOT NULL REFERENCES rollout_waves_r22(id),
 action TEXT NOT NULL, old_state TEXT NOT NULL, new_state TEXT NOT NULL,
 stage INTEGER NOT NULL, actor_id INTEGER NOT NULL,
 note TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rollout_stage_proofs_r22 (
 id INTEGER PRIMARY KEY,
 wave_id INTEGER NOT NULL REFERENCES rollout_waves_r22(id),
 stage INTEGER NOT NULL, payload_json TEXT NOT NULL,
 payload_sha TEXT NOT NULL, reviewed_by INTEGER NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(wave_id,stage)
);
"""


def ensure_schema(db:sqlite3.Connection)->None:
    db.executescript(SCHEMA)


def canonical(value)->str:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def sha(value)->str:
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def _wave(db,identity:int,p:Principal):
    w=db.execute('SELECT * FROM rollout_waves_r22 WHERE id=? AND organization_id=?',(identity,p.organization_id)).fetchone()
    if not w:raise HTTPException(404,'Волна не найдена')
    # Never let a manager infer or read another assigned branch through a wave.
    for store in db.execute('SELECT store_id FROM rollout_sites_r22 WHERE wave_id=?',(identity,)).fetchall():
        check_store_access(db,store['store_id'],p)
    return w


def _audit(db,w,p,action,old,new,note):
    db.execute('''INSERT INTO rollout_events_r22(wave_id,action,old_state,new_state,stage,actor_id,note,created_at)
                  VALUES(?,?,?,?,?,?,?,?)''',(w['id'],action,old,new,w['stage'],p.user_id,note.strip(),now_iso()))
    audit(db,p,'r22.'+action,str(w['id']))


def _readiness(db,store_id):
    d=db.execute("""SELECT d.*,r.payload_json,r.payload_sha,r.reviewed_at,r.reviewer_id FROM readiness_days_r20 d
         JOIN readiness_reviews_r20 r ON r.readiness_id=d.id
         WHERE d.store_id=? AND d.status='reviewed' ORDER BY d.business_day DESC,d.id DESC LIMIT 1""",(store_id,)).fetchone()
    if not d:return {'status':'missing','issues':['Нет независимо проверенного отчёта R2.0']}
    if d['requested_by']==d['reviewer_id'] or d['reviewed_by']!=d['reviewer_id']:
        return {'status':'invalid','issues':['Независимость подписи не подтверждена'], 'readiness_id':d['id']}
    if hashlib.sha256(d['payload_json'].encode()).hexdigest()!=d['payload_sha']:
        return {'status':'invalid','issues':['Нарушена контрольная сумма отчёта готовности'], 'readiness_id':d['id']}
    try:
        frozen=json.loads(d['payload_json'])
        if frozen.get('decision')!='reviewed' or frozen.get('issues') or frozen.get('day',{}).get('id')!=d['id']:
            return {'status':'invalid','issues':['Отчёт не подтверждает готовность'], 'readiness_id':d['id']}
        stamp=datetime.fromisoformat(d['reviewed_at']);stamp=stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
        age=datetime.now(timezone.utc)-stamp.astimezone(timezone.utc)
        if age>timedelta(days=7) or age<timedelta(minutes=-5):
            return {'status':'expired','issues':['Проверка готовности старше 7 дней или из будущего'], 'readiness_id':d['id']}
    except (ValueError,TypeError,KeyError):
        return {'status':'invalid','issues':['Невозможно разобрать отчёт'], 'readiness_id':d['id']}
    return {'status':'ready','issues':[],'readiness_id':d['id'],'sha256':d['payload_sha'],
            'reviewed_at':d['reviewed_at']}


def _risks(db,store_id):
    """Observed R1.9 signals. Missing optional telemetry is a warning, not fabricated uptime."""
    issues=[]
    try:
        rows=db.execute("""SELECT signal FROM field_incidents_r19 WHERE store_id=? AND status!='resolved'
             ORDER BY id DESC LIMIT 50""",(store_id,)).fetchall()
        issues.extend('Инцидент терминала: '+x['signal'] for x in rows)
    except sqlite3.OperationalError as exc:
        if 'no such table' not in str(exc):raise
        issues.append('Нет таблицы мониторинга R1.9')
    return issues


def _sites(db,w,principal=None):
    rows=db.execute('''SELECT s.*,st.name AS store_name,st.slug FROM rollout_sites_r22 s
                          JOIN stores st ON st.id=s.store_id WHERE s.wave_id=? ORDER BY s.phase,s.id''',(w['id'],)).fetchall()
    result=[]
    for row in rows:
        if principal:check_store_access(db,row['store_id'],principal)
        readiness=_readiness(db,row['store_id'])
        risks=_risks(db,row['store_id'])
        changed=bool(row['evidence_sha'] and (readiness.get('sha256')!=row['evidence_sha']))
        result.append({'id':row['id'],'store_id':row['store_id'],'name':row['store_name'],
          'slug':row['slug'],'phase':row['phase'],'evidence_sha':row['evidence_sha'],
          'evidence_at':row['evidence_at'],'readiness':readiness,'risks':risks,
          'drift':changed,'eligible':readiness['status']=='ready' and not risks and not changed})
    return result


def _snapshot(db,w,p):
    sites=_sites(db,w,p)
    stage=[x for x in sites if x['phase']==w['stage']]
    return {'wave':dict(w),'stores':sites,'current_stage':w['stage'],
      'current_count':len(stage),'current_ready':sum(x['eligible'] for x in stage),
      'blocking':[f"{x['name']}: "+('; '.join(x['readiness']['issues']+x['risks']) or 'Подтверждение изменилось')
                  for x in stage if not x['eligible']],
      'disclaimer':'Это документальное разрешение на этап. Оно не запускает внешние сервисы и не подтверждает прибыль.'}


def _safe_csv(rows,keys):
    out=io.StringIO(newline='');writer=csv.writer(out);writer.writerow(keys)
    for row in rows:writer.writerow([safe_spreadsheet_cell(str(row.get(k,''))) for k in keys])
    return '\ufeff'+out.getvalue()


class WaveIn(BaseModel):
    request_id:str=Field(min_length=12,max_length=100)
    title:str=Field(min_length=12,max_length=160)
    objective:str=Field(min_length=20,max_length=500)
    budget_kopeks:int=Field(ge=0,le=1000000000)


class SiteIn(BaseModel):
    slug:str
    phase:int=Field(ge=1,le=5)
    notes:str=Field(default='',max_length=250)


class DecisionIn(BaseModel):
    note:str=Field(min_length=15,max_length=600)


def build_router(admin,db_conn):
    router=APIRouter(prefix='/api/admin/r22',tags=['R2.2 Multi-Store Rollout'])

    @router.get('/waves')
    def waves(principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        rows=db.execute('SELECT * FROM rollout_waves_r22 WHERE organization_id=? ORDER BY id DESC LIMIT 100',(principal.organization_id,)).fetchall()
        permitted=[]
        for w in rows:
            try:_wave(db,w['id'],principal)
            except HTTPException:continue
            permitted.append({'id':w['id'],'title':w['title'],'state':w['state'],'stage':w['stage'],
                 'budget_kopeks':w['budget_kopeks'],'count':db.execute('SELECT COUNT(*) FROM rollout_sites_r22 WHERE wave_id=?',(w['id'],)).fetchone()[0]})
        return {'items':permitted}

    @router.post('/waves',status_code=201)
    def create(body:WaveIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager');spec=body.model_dump(mode='json');digest=sha(spec)
        try:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM rollout_waves_r22 WHERE organization_id=? AND request_id=?',(principal.organization_id,body.request_id)).fetchone()
            if old:
                if old['request_hash']!=digest:raise HTTPException(409,'Ключ занят другими параметрами')
                _wave(db,old['id'],principal);db.rollback();return {'id':old['id'],'duplicate':True}
            stamp=now_iso()
            cur=db.execute('''INSERT INTO rollout_waves_r22(organization_id,request_id,request_hash,title,objective,budget_kopeks,creator_id,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?)''',(principal.organization_id,body.request_id,digest,body.title.strip(),body.objective.strip(),body.budget_kopeks,principal.user_id,stamp,stamp))
            w=db.execute('SELECT * FROM rollout_waves_r22 WHERE id=?',(cur.lastrowid,)).fetchone()
            _audit(db,w,principal,'wave.create','','draft','Новый план запусков');db.commit()
            return {'id':cur.lastrowid,'duplicate':False}
        except Exception:db.rollback();raise

    @router.post('/waves/{wave_id}/sites',status_code=201)
    def add_site(wave_id:int,body:SiteIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager');store=visible_store(db,body.slug,principal)
        try:
            db.execute('BEGIN IMMEDIATE');w=_wave(db,wave_id,principal)
            if w['state']!='draft':raise HTTPException(409,'Список филиалов уже зафиксирован')
            if db.execute('SELECT COUNT(*) FROM rollout_sites_r22 WHERE wave_id=?',(wave_id,)).fetchone()[0]>=25:
                raise HTTPException(413,'Не более 25 филиалов в одной волне')
            old=db.execute('SELECT * FROM rollout_sites_r22 WHERE wave_id=? AND store_id=?',(wave_id,store['id'])).fetchone()
            if old:
                if old['phase']!=body.phase or old['notes']!=body.notes.strip():raise HTTPException(409,'Филиал уже назначен на другой этап')
                db.rollback();return {'id':old['id'],'duplicate':True}
            cur=db.execute('INSERT INTO rollout_sites_r22(wave_id,store_id,phase,notes) VALUES(?,?,?,?)',
                           (wave_id,store['id'],body.phase,body.notes.strip()))
            _audit(db,w,principal,'site.add','draft','draft',body.slug+':'+str(body.phase));db.commit()
            return {'id':cur.lastrowid,'duplicate':False}
        except Exception:db.rollback();raise

    @router.get('/waves/{wave_id}')
    def detail(wave_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        w=_wave(db,wave_id,principal);result=_snapshot(db,w,principal)
        result['events']=[dict(x) for x in db.execute('SELECT action,old_state,new_state,stage,note,created_at FROM rollout_events_r22 WHERE wave_id=? ORDER BY id DESC LIMIT 100',(wave_id,))]
        result['stage_proofs']=[{'stage':x['stage'],'sha256':x['payload_sha'],'intact':hashlib.sha256(x['payload_json'].encode()).hexdigest()==x['payload_sha']}
          for x in db.execute('SELECT * FROM rollout_stage_proofs_r22 WHERE wave_id=? ORDER BY stage',(wave_id,))]
        return result

    @router.post('/waves/{wave_id}/request-review')
    def request_review(wave_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            db.execute('BEGIN IMMEDIATE');w=_wave(db,wave_id,principal)
            if w['state']!='draft':raise HTTPException(409,'Запрос уже отправлен')
            sites=_sites(db,w,principal)
            if not sites or not any(x['phase']==1 for x in sites):raise HTTPException(409,'Первый этап не содержит филиалов')
            if [x['phase'] for x in sites] and sorted(set(x['phase'] for x in sites))!=list(range(1,max(x['phase'] for x in sites)+1)):
                raise HTTPException(409,'Этапы должны следовать без пропусков')
            db.execute("UPDATE rollout_waves_r22 SET state='review_requested',requested_by=?,updated_at=? WHERE id=?",(principal.user_id,now_iso(),wave_id))
            _audit(db,w,principal,'wave.request','draft','review_requested','Состав и бюджет заморожены');db.commit()
            return {'state':'review_requested'}
        except Exception:db.rollback();raise

    @router.post('/waves/{wave_id}/approve')
    def approve(wave_id:int,body:DecisionIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner')
        try:
            db.execute('BEGIN IMMEDIATE');w=_wave(db,wave_id,principal)
            if w['state']!='review_requested':raise HTTPException(409,'Нет заявки на согласование')
            if w['requested_by']==principal.user_id:raise HTTPException(409,'Независимый проверяющий должен отличаться от автора')
            report=_snapshot(db,w,principal)
            if report['blocking'] or not report['current_count']:raise HTTPException(409,'Есть неподготовленные филиалы')
            for site in report['stores']:
                if site['phase']==1:
                    db.execute('UPDATE rollout_sites_r22 SET readiness_id=?,evidence_sha=?,evidence_at=? WHERE id=?',
                      (site['readiness']['readiness_id'],site['readiness']['sha256'],now_iso(),site['id']))
            db.execute("UPDATE rollout_waves_r22 SET state='active',reviewer_id=?,review_note=?,updated_at=? WHERE id=?",
                       (principal.user_id,body.note.strip(),now_iso(),wave_id))
            _audit(db,w,principal,'wave.approve','review_requested','active',body.note);db.commit()
            return {'state':'active','stage':1,'message':'Только разрешение в журнале, не запуск оборудования'}
        except Exception:db.rollback();raise

    @router.post('/waves/{wave_id}/pause')
    def pause(wave_id:int,body:DecisionIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            db.execute('BEGIN IMMEDIATE');w=_wave(db,wave_id,principal)
            if w['state']!='active':raise HTTPException(409,'Можно остановить только активную волну')
            db.execute("UPDATE rollout_waves_r22 SET state='paused',updated_at=? WHERE id=?",(now_iso(),wave_id))
            _audit(db,w,principal,'wave.pause','active','paused',body.note);db.commit();return {'state':'paused'}
        except Exception:db.rollback();raise

    @router.post('/waves/{wave_id}/resume')
    def resume(wave_id:int,body:DecisionIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner')
        try:
            db.execute('BEGIN IMMEDIATE');w=_wave(db,wave_id,principal)
            if w['state']!='paused':raise HTTPException(409,'Волна не приостановлена')
            report=_snapshot(db,w,principal)
            if report['blocking']:raise HTTPException(409,'Есть нерешённые проблемы филиалов')
            db.execute("UPDATE rollout_waves_r22 SET state='active',updated_at=? WHERE id=?",(now_iso(),wave_id))
            _audit(db,w,principal,'wave.resume','paused','active',body.note);db.commit();return {'state':'active'}
        except Exception:db.rollback();raise

    @router.post('/waves/{wave_id}/advance')
    def advance(wave_id:int,body:DecisionIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner')
        try:
            db.execute('BEGIN IMMEDIATE');w=_wave(db,wave_id,principal)
            if w['state']!='active':raise HTTPException(409,'Этап не активен')
            report=_snapshot(db,w,principal)
            for old in db.execute('SELECT payload_json,payload_sha FROM rollout_stage_proofs_r22 WHERE wave_id=?',(wave_id,)):
                if hashlib.sha256(old['payload_json'].encode()).hexdigest()!=old['payload_sha']:
                    raise HTTPException(409,'Повреждён снимок предыдущего этапа')
            if report['blocking'] or not report['current_count']:raise HTTPException(409,'Этап не прошёл контроль готовности')
            frozen={'wave_id':wave_id,'stage':w['stage'],'snapshot':report,'decision_note':body.note.strip(),'frozen_at':now_iso()}
            payload=canonical(frozen);digest=hashlib.sha256(payload.encode()).hexdigest()
            db.execute('INSERT INTO rollout_stage_proofs_r22(wave_id,stage,payload_json,payload_sha,reviewed_by,created_at) VALUES(?,?,?,?,?,?)',
                       (wave_id,w['stage'],payload,digest,principal.user_id,now_iso()))
            next_stage=w['stage']+1
            more=any(x['phase']==next_stage for x in report['stores'])
            state='active' if more else 'completed'
            if more:
                # Next stage is entered only if that stage already has valid readiness.
                next_sites=[x for x in report['stores'] if x['phase']==next_stage]
                if any(not x['eligible'] for x in next_sites):raise HTTPException(409,'Следующий этап содержит неподготовленные филиалы')
                for site in next_sites:
                    db.execute('UPDATE rollout_sites_r22 SET readiness_id=?,evidence_sha=?,evidence_at=? WHERE id=?',
                        (site['readiness']['readiness_id'],site['readiness']['sha256'],now_iso(),site['id']))
            db.execute('UPDATE rollout_waves_r22 SET stage=?,state=?,updated_at=? WHERE id=?',
                       (next_stage if more else w['stage'],state,now_iso(),wave_id))
            _audit(db,w,principal,'wave.advance','active',state,body.note);db.commit()
            return {'state':state,'stage':next_stage if more else w['stage'],'proof_sha256':digest}
        except Exception:db.rollback();raise

    @router.get('/portfolio')
    def portfolio(principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        data=[]
        for w in db.execute('SELECT * FROM rollout_waves_r22 WHERE organization_id=? ORDER BY id DESC LIMIT 100',(principal.organization_id,)):
            try:_wave(db,w['id'],principal)
            except HTTPException:continue
            report=_snapshot(db,w,principal)
            data.append({'id':w['id'],'title':w['title'],'state':w['state'],'stage':w['stage'],
              'stores':len(report['stores']),'stage_ready':report['current_ready'],
              'stage_total':report['current_count'],'blocking':len(report['blocking']),
              'budget_kopeks':w['budget_kopeks']})
        return {'items':data,'total':len(data),'methodology':'Разрешения на управленческие этапы, не подтверждённый запуск кассы или оборудования'}

    @router.get('/portfolio.csv')
    def portfolio_csv(principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        result=portfolio(principal,db)
        text=_safe_csv(result['items'],['id','title','state','stage','stores','stage_ready','stage_total','blocking','budget_kopeks'])
        return Response(text,media_type='text/csv; charset=utf-8',headers={
            'Content-Disposition':'attachment; filename="osmanx-rollout-portfolio.csv"','Cache-Control':'no-store'})
    return router
