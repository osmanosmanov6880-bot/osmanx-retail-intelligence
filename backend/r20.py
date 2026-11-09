"""OSMANX R2.0: audited store launch readiness, not a production safety certification.

Five operational blocks: checklist, calibration, counted-data reconciliation,
shift handover, and cryptographically sealed review decision. No cameras, PII,
or automation of payments, equipment, or public deployment.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.database import now_iso
from backend.security import Principal, audit, check_store_access, require_role, visible_store
from backend.retail import safe_spreadsheet_cell

CHECKS = {
    'tablet': 'Планшет работает и физически закреплён',
    'network': 'Защищённый доступ и подключение проверены',
    'notice': 'Уведомление о добровольности опроса размещено',
    'survey': 'Тестовый опрос отправлен и появился в системе',
    'counter': 'Счётчик входов проверен вручную',
    'pos': 'Источник чеков и методика сверки согласованы',
    'staff': 'Ответственный сотрудник знает порядок действий',
    'privacy': 'Настроены сроки хранения и доступ сотрудников',
}

DDL = """
CREATE TABLE IF NOT EXISTS readiness_days_r20 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 business_day TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','review_requested','reviewed','rejected')),
 requested_by INTEGER, reviewed_by INTEGER, review_note TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(store_id,business_day)
);
CREATE TABLE IF NOT EXISTS readiness_checks_r20 (
 id INTEGER PRIMARY KEY,
 readiness_id INTEGER NOT NULL REFERENCES readiness_days_r20(id),
 key TEXT NOT NULL, outcome TEXT NOT NULL CHECK(outcome IN ('pass','fail','not_applicable')),
 note TEXT NOT NULL, actor_id INTEGER NOT NULL,
 updated_at TEXT NOT NULL, UNIQUE(readiness_id,key)
);
CREATE TABLE IF NOT EXISTS readiness_calibrations_r20 (
 id INTEGER PRIMARY KEY,
 readiness_id INTEGER NOT NULL REFERENCES readiness_days_r20(id),
 request_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL,
 reference_count INTEGER NOT NULL CHECK(reference_count>=0),
 counter_count INTEGER NOT NULL CHECK(counter_count>=0),
 abs_error INTEGER NOT NULL, error_pct REAL,
 method TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(readiness_id,request_id)
);
CREATE TABLE IF NOT EXISTS readiness_reconciliations_r20 (
 id INTEGER PRIMARY KEY,
 readiness_id INTEGER NOT NULL REFERENCES readiness_days_r20(id),
 store_visits INTEGER NOT NULL, store_receipts INTEGER NOT NULL,
 voice_opens INTEGER NOT NULL, voice_responses INTEGER NOT NULL,
 recorded_at TEXT NOT NULL, note TEXT NOT NULL,
 author_id INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS readiness_handover_r20 (
 id INTEGER PRIMARY KEY,
 readiness_id INTEGER NOT NULL REFERENCES readiness_days_r20(id),
 request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
 shift TEXT NOT NULL CHECK(shift IN ('morning','day','evening')),
 issues TEXT NOT NULL, actions TEXT NOT NULL,
 created_by INTEGER NOT NULL, acknowledged_by INTEGER,
 created_at TEXT NOT NULL, acknowledged_at TEXT,
 UNIQUE(readiness_id,request_id)
);
CREATE TABLE IF NOT EXISTS readiness_reviews_r20 (
 id INTEGER PRIMARY KEY,
 readiness_id INTEGER NOT NULL UNIQUE REFERENCES readiness_days_r20(id),
 payload_json TEXT NOT NULL, payload_sha TEXT NOT NULL,
 reviewer_id INTEGER NOT NULL, reviewed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS readiness_audit_r20 (
 id INTEGER PRIMARY KEY, readiness_id INTEGER NOT NULL REFERENCES readiness_days_r20(id),
 event TEXT NOT NULL, actor_id INTEGER NOT NULL, detail TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_r20_day ON readiness_days_r20(organization_id,store_id,business_day);
CREATE INDEX IF NOT EXISTS idx_r20_handover ON readiness_handover_r20(readiness_id,acknowledged_by);
"""


def ensure_schema(db:sqlite3.Connection)->None:
    db.executescript(DDL)


def canonical(value)->str:
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))


def sha(value)->str:
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def entry(db,day_id:int,user:Principal):
    row=db.execute('SELECT * FROM readiness_days_r20 WHERE id=? AND organization_id=?',
                   (day_id,user.organization_id)).fetchone()
    if not row:raise HTTPException(404,'Смена не найдена')
    check_store_access(db,row['store_id'],user)
    return row


def lock_draft(row):
    if row['status']!='draft':raise HTTPException(409,'Смена уже отправлена на проверку; правки заблокированы')


def event(db,row,user,name,detail=''):
    db.execute('INSERT INTO readiness_audit_r20(readiness_id,event,actor_id,detail,created_at) VALUES(?,?,?,?,?)',
               (row['id'],name,user.user_id,detail,now_iso()))
    audit(db,user,'r20.'+name,str(row['id']))


def store_zone(store):
    try:return ZoneInfo(store['timezone'] or 'UTC')
    except (KeyError, ZoneInfoNotFoundError):return timezone.utc


def bounds(store,day:str):
    d=date.fromisoformat(day)
    tz=store_zone(store)
    start=datetime.combine(d,datetime.min.time(),tzinfo=tz)
    end=start+timedelta(days=1)
    return start.astimezone(timezone.utc),end.astimezone(timezone.utc)


def observed(db,store,day):
    start,end=bounds(store,day)
    lo,hi=start.isoformat(),end.isoformat()
    # ISO strings are mixed across historical sources: parse timestamps in Python
    # rather than incorrectly comparing differing UTC offsets lexically in SQL.
    out={k:0 for k in ('visits','receipts','voice_opens','voice_responses')}
    for table,stamp,field in [('visits','occurred_at','quantity'),('sales','occurred_at','id')]:
        records=db.execute(f'SELECT {stamp},{field} FROM {table} WHERE store_id=? ORDER BY id DESC LIMIT 25001',
                           (store['id'],)).fetchall()
        if len(records)>25000:raise HTTPException(413,'Слишком много событий: требуется отдельный агрегатор')
        for r in records:
            try:t=datetime.fromisoformat(r[stamp]);t=t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
            except (TypeError,ValueError):continue
            if start<=t.astimezone(timezone.utc)<end:
                out['visits' if table=='visits' else 'receipts']+=(r[field] if table=='visits' else 1)
    for table,stamp,key in [('voice_opens_r17','opened_at','voice_opens'),('voice_responses_r17','submitted_at','voice_responses')]:
        records=db.execute(f'''SELECT e.{stamp} AS occurred FROM {table} e
          JOIN voice_placements_r17 p ON p.id=e.placement_id WHERE p.store_id=? ORDER BY e.id DESC LIMIT 25001''',
          (store['id'],)).fetchall()
        if len(records)>25000:raise HTTPException(413,'Слишком много ответов для дневного расчёта')
        for r in records:
            try:t=datetime.fromisoformat(r['occurred']);t=t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
            except (TypeError,ValueError):continue
            if start<=t.astimezone(timezone.utc)<end:out[key]+=1
    return out


def view(db,row):
    checks=[dict(x) for x in db.execute('SELECT key,outcome,note,updated_at FROM readiness_checks_r20 WHERE readiness_id=? ORDER BY key',(row['id'],))]
    calibrations=[dict(x) for x in db.execute('SELECT * FROM readiness_calibrations_r20 WHERE readiness_id=? ORDER BY id',(row['id'],))]
    handovers=[dict(x) for x in db.execute('SELECT id,shift,issues,actions,created_by,acknowledged_by,created_at,acknowledged_at FROM readiness_handover_r20 WHERE readiness_id=? ORDER BY id',(row['id'],))]
    reconciliations=[dict(x) for x in db.execute('SELECT * FROM readiness_reconciliations_r20 WHERE readiness_id=? ORDER BY id DESC LIMIT 2',(row['id'],))]
    flagged=[]
    for key in CHECKS:
        check=next((x for x in checks if x['key']==key),None)
        if check is None:flagged.append('Не проверено: '+CHECKS[key])
        elif check['outcome']=='fail':flagged.append('Проблема: '+CHECKS[key])
        elif check['outcome']=='not_applicable' and key in ('counter','pos','notice','privacy'):
            flagged.append('Обязательная проверка не может быть пропущена: '+CHECKS[key])
    passed_calibrations=[x for x in calibrations if x['reference_count']>=20 and x['error_pct'] is not None and x['error_pct']<=10]
    if len(passed_calibrations)<2:flagged.append('Нужны две калибровки не менее 20 входов с отклонением не более 10%')
    if not reconciliations:flagged.append('Отсутствует сверка входов, чеков и опросов')
    elif reconciliations[0]['store_visits']==0:
        flagged.append('Нет зарегистрированных входов: нельзя подтвердить подсчёт посетителей')
    elif reconciliations[0]['store_receipts']==0:
        flagged.append('Нет записей кассы: полнота продаж не подтверждена')
    if not any(h['acknowledged_by'] is not None and h['acknowledged_by']!=h['created_by'] for h in handovers):
        flagged.append('Передача смены не подтверждена вторым сотрудником')
    return {'day':dict(row),'checks':checks,'calibrations':calibrations,'reconciliations':reconciliations,
            'handovers':handovers,'issues':flagged,'reviewable':not flagged,
            'disclaimer':'Проверка означает документированную готовность процесса, но не подтверждает точность физических датчиков и кассы.'}


class StartDay(BaseModel):
    slug:str='central'
    business_day:date


class CheckIn(BaseModel):
    key:str
    outcome:Literal['pass','fail','not_applicable']
    note:str=Field(min_length=12,max_length=500)


class CalibrationIn(BaseModel):
    request_id:str=Field(min_length=12,max_length=100)
    reference_count:int=Field(ge=0,le=10000)
    counter_count:int=Field(ge=0,le=10000)
    method:str=Field(min_length=12,max_length=300)


class ReconcileIn(BaseModel):
    note:str=Field(min_length=12,max_length=500)


class HandoverIn(BaseModel):
    request_id:str=Field(min_length=12,max_length=100)
    shift:Literal['morning','day','evening']
    issues:str=Field(min_length=12,max_length=600)
    actions:str=Field(min_length=12,max_length=600)


class AcknowledgeIn(BaseModel):
    note:str=Field(min_length=12,max_length=500)


class ReviewIn(BaseModel):
    decision:Literal['reviewed','rejected']
    note:str=Field(min_length=12,max_length=600)


def build_router(admin,db_conn):
    router=APIRouter(prefix='/api/admin/r20',tags=['R2.0 Store Readiness'])

    @router.get('/days')
    def list_days(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        return {'items':[dict(r) for r in db.execute('SELECT * FROM readiness_days_r20 WHERE store_id=? ORDER BY business_day DESC LIMIT 90',(store['id'],))]}

    @router.post('/days',status_code=201)
    def start_day(body:StartDay,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager');store=visible_store(db,body.slug,principal)
        if abs((body.business_day-datetime.now(store_zone(store)).date()).days)>31:
            raise HTTPException(422,'Дату можно выбрать в пределах 31 дня')
        try:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM readiness_days_r20 WHERE store_id=? AND business_day=?',(store['id'],str(body.business_day))).fetchone()
            if old:db.rollback();return {'id':old['id'],'duplicate':True}
            stamp=now_iso()
            cur=db.execute('INSERT INTO readiness_days_r20(organization_id,store_id,business_day,created_at,updated_at) VALUES(?,?,?,?,?)',
                           (principal.organization_id,store['id'],str(body.business_day),stamp,stamp))
            row=db.execute('SELECT * FROM readiness_days_r20 WHERE id=?',(cur.lastrowid,)).fetchone()
            event(db,row,principal,'day.created');db.commit();return {'id':row['id'],'duplicate':False}
        except Exception:db.rollback();raise

    @router.get('/days/{day_id}')
    def get_day(day_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        return view(db,entry(db,day_id,principal))

    @router.put('/days/{day_id}/checks')
    def check(day_id:int,body:CheckIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        if body.key not in CHECKS:raise HTTPException(422,'Неизвестная контрольная точка')
        try:
            db.execute('BEGIN IMMEDIATE');row=entry(db,day_id,principal);lock_draft(row)
            db.execute('''INSERT INTO readiness_checks_r20(readiness_id,key,outcome,note,actor_id,updated_at) VALUES(?,?,?,?,?,?)
                 ON CONFLICT(readiness_id,key) DO UPDATE SET outcome=excluded.outcome,note=excluded.note,actor_id=excluded.actor_id,updated_at=excluded.updated_at''',
                 (day_id,body.key,body.outcome,body.note.strip(),principal.user_id,now_iso()))
            event(db,row,principal,'check.recorded',body.key+':'+body.outcome);db.commit();return {'saved':True}
        except Exception:db.rollback();raise

    @router.post('/days/{day_id}/calibrations',status_code=201)
    def calibrate(day_id:int,body:CalibrationIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        fingerprint=sha(body.model_dump(mode='json'))
        try:
            db.execute('BEGIN IMMEDIATE');row=entry(db,day_id,principal);lock_draft(row)
            previous=db.execute('SELECT id,fingerprint FROM readiness_calibrations_r20 WHERE readiness_id=? AND request_id=?',(day_id,body.request_id)).fetchone()
            if previous:
                if previous['fingerprint']!=fingerprint:raise HTTPException(409,'Ключ калибровки занят другим измерением')
                db.rollback();return {'id':previous['id'],'duplicate':True}
            gap=abs(body.counter_count-body.reference_count)
            percent=round(100*gap/body.reference_count,2) if body.reference_count else None
            cur=db.execute('''INSERT INTO readiness_calibrations_r20(readiness_id,request_id,fingerprint,reference_count,counter_count,abs_error,error_pct,method,created_at)
                 VALUES(?,?,?,?,?,?,?,?,?)''',(day_id,body.request_id,fingerprint,body.reference_count,body.counter_count,gap,percent,body.method.strip(),now_iso()))
            event(db,row,principal,'calibration.recorded',str(cur.lastrowid));db.commit()
            return {'id':cur.lastrowid,'duplicate':False,'error_pct':percent,'within_tolerance':percent is not None and percent<=10 and body.reference_count>=20}
        except Exception:db.rollback();raise

    @router.post('/days/{day_id}/reconcile',status_code=201)
    def reconcile(day_id:int,body:ReconcileIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            db.execute('BEGIN IMMEDIATE');row=entry(db,day_id,principal);lock_draft(row)
            store=db.execute('SELECT * FROM stores WHERE id=? AND organization_id=?',(row['store_id'],principal.organization_id)).fetchone()
            result=observed(db,store,row['business_day'])
            cur=db.execute('''INSERT INTO readiness_reconciliations_r20(readiness_id,store_visits,store_receipts,voice_opens,voice_responses,recorded_at,note,author_id)
                   VALUES(?,?,?,?,?,?,?,?)''',(day_id,result['visits'],result['receipts'],result['voice_opens'],result['voice_responses'],now_iso(),body.note.strip(),principal.user_id))
            event(db,row,principal,'reconciliation.recorded',str(cur.lastrowid));db.commit()
            return {'id':cur.lastrowid,'counts':result,'warnings':(['Нет входов за день'] if not result['visits'] else [])+
                        (['Нет кассовых чеков за день'] if not result['receipts'] else [])}
        except Exception:db.rollback();raise

    @router.post('/days/{day_id}/handovers',status_code=201)
    def handover(day_id:int,body:HandoverIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager');digest=sha(body.model_dump())
        try:
            db.execute('BEGIN IMMEDIATE');row=entry(db,day_id,principal);lock_draft(row)
            previous=db.execute('SELECT id,fingerprint FROM readiness_handover_r20 WHERE readiness_id=? AND request_id=?',(day_id,body.request_id)).fetchone()
            if previous:
                if previous['fingerprint']!=digest:raise HTTPException(409,'Повторный ключ передачи смены с другими данными')
                db.rollback();return {'id':previous['id'],'duplicate':True}
            cur=db.execute('''INSERT INTO readiness_handover_r20(readiness_id,request_id,fingerprint,shift,issues,actions,created_by,created_at)
                         VALUES(?,?,?,?,?,?,?,?)''',(day_id,body.request_id,digest,body.shift,body.issues.strip(),body.actions.strip(),principal.user_id,now_iso()))
            event(db,row,principal,'handover.created',str(cur.lastrowid));db.commit();return {'id':cur.lastrowid,'duplicate':False}
        except Exception:db.rollback();raise

    @router.post('/handovers/{handover_id}/ack')
    def acknowledge(handover_id:int,body:AcknowledgeIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            db.execute('BEGIN IMMEDIATE')
            record=db.execute('SELECT * FROM readiness_handover_r20 WHERE id=?',(handover_id,)).fetchone()
            if not record:raise HTTPException(404,'Передача смены не найдена')
            row=entry(db,record['readiness_id'],principal);lock_draft(row)
            if record['created_by']==principal.user_id:raise HTTPException(409,'Нужен другой сотрудник')
            if record['acknowledged_by'] is not None:raise HTTPException(409,'Передача уже подтверждена')
            db.execute('UPDATE readiness_handover_r20 SET acknowledged_by=?,acknowledged_at=? WHERE id=?',
                       (principal.user_id,now_iso(),handover_id))
            event(db,row,principal,'handover.acknowledged',body.note.strip());db.commit();return {'acknowledged':True}
        except Exception:db.rollback();raise

    @router.post('/days/{day_id}/review-request')
    def request_review(day_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            db.execute('BEGIN IMMEDIATE');row=entry(db,day_id,principal);lock_draft(row)
            data=view(db,row)
            if data['issues']:raise HTTPException(409,'Нельзя запросить проверку: '+data['issues'][0])
            db.execute("UPDATE readiness_days_r20 SET status='review_requested',requested_by=?,updated_at=? WHERE id=?",
                       (principal.user_id,now_iso(),day_id))
            event(db,row,principal,'review.requested');db.commit();return {'status':'review_requested'}
        except Exception:db.rollback();raise

    @router.post('/days/{day_id}/review')
    def review(day_id:int,body:ReviewIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner')
        try:
            db.execute('BEGIN IMMEDIATE');row=entry(db,day_id,principal)
            if row['status']!='review_requested':raise HTTPException(409,'Смена не отправлена на проверку')
            if principal.user_id==row['requested_by']:raise HTTPException(409,'Независимый проверяющий должен отличаться от автора')
            data=view(db,row)
            if body.decision=='reviewed' and data['issues']:raise HTTPException(409,'Обнаружены блокирующие проблемы')
            frozen={'day':data['day'],'checks':data['checks'],'calibrations':data['calibrations'],
                    'reconciliations':data['reconciliations'],'handovers':data['handovers'],
                    'issues':data['issues'],'decision':body.decision,'note':body.note.strip(),
                    'frozen_at':now_iso(),'disclaimer':data['disclaimer']}
            payload=canonical(frozen);checksum=hashlib.sha256(payload.encode()).hexdigest()
            db.execute('INSERT INTO readiness_reviews_r20(readiness_id,payload_json,payload_sha,reviewer_id,reviewed_at) VALUES(?,?,?,?,?)',
                       (day_id,payload,checksum,principal.user_id,now_iso()))
            db.execute('UPDATE readiness_days_r20 SET status=?,reviewed_by=?,review_note=?,updated_at=? WHERE id=?',
                       (body.decision,principal.user_id,body.note.strip(),now_iso(),day_id))
            event(db,row,principal,'review.'+body.decision);db.commit()
            return {'status':body.decision,'sha256':checksum}
        except Exception:db.rollback();raise

    @router.get('/days/{day_id}/snapshot')
    def snapshot(day_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        entry(db,day_id,principal)
        record=db.execute('SELECT * FROM readiness_reviews_r20 WHERE readiness_id=?',(day_id,)).fetchone()
        if not record:raise HTTPException(404,'Зафиксированный отчёт ещё не существует')
        if hashlib.sha256(record['payload_json'].encode()).hexdigest()!=record['payload_sha']:
            raise HTTPException(409,'Снимок повреждён')
        return {'sha256':record['payload_sha'],'report':json.loads(record['payload_json'])}

    @router.get('/days/{day_id}/report.csv')
    def csv_report(day_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        row=entry(db,day_id,principal);report=view(db,row)
        buffer=io.StringIO();writer=csv.writer(buffer)
        writer.writerow(['Тип','Показатель','Значение','Примечание'])
        for c in report['checks']:
            writer.writerow(['Контроль',safe_spreadsheet_cell(CHECKS[c['key']]),c['outcome'],safe_spreadsheet_cell(c['note'])])
        for c in report['calibrations']:
            writer.writerow(['Калибровка',c['reference_count'],c['counter_count'],c['error_pct']])
        for c in report['reconciliations'][:1]:
            writer.writerow(['Сверка','Входы',c['store_visits'],'чеков: '+str(c['store_receipts'])])
        for i in report['issues']:writer.writerow(['Проблема',safe_spreadsheet_cell(i),'',''])
        return Response('\ufeff'+buffer.getvalue(),media_type='text/csv; charset=utf-8',headers={
            'Cache-Control':'no-store','Content-Disposition':'attachment; filename="osmanx-store-readiness.csv"'})

    return router
