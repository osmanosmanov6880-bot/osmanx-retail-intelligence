"""OSMANX R2.1: Store Assurance, five workflows anchored to R2.0 evidence.

Scope: authorized store portfolio, calibration trend, reconciliation drift,
audited remediation tickets and readiness-gated *optional* pilot startup.
Neither SHA-256 nor a signed-off checklist proves physical accuracy of equipment.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.database import now_iso
from backend.retail import safe_spreadsheet_cell
from backend.security import Principal, audit, check_store_access, require_role, visible_store
from backend.r20 import entry as readiness_entry, view as readiness_view, observed as observed_r20, store_zone

DDL = """
CREATE TABLE IF NOT EXISTS assurance_tickets_r21 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 readiness_id INTEGER NOT NULL REFERENCES readiness_days_r20(id),
 issue_key TEXT NOT NULL, description TEXT NOT NULL,
 source_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open'
    CHECK(status IN ('open','working','verified','dismissed')),
 owner TEXT NOT NULL DEFAULT '', due_date TEXT NOT NULL,
 note TEXT NOT NULL DEFAULT '', created_by INTEGER NOT NULL,
 verified_by INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(readiness_id,issue_key)
);
CREATE INDEX IF NOT EXISTS idx_r21_tickets ON assurance_tickets_r21(store_id,status,due_date);
CREATE TABLE IF NOT EXISTS assurance_ticket_history_r21 (
 id INTEGER PRIMARY KEY,
 ticket_id INTEGER NOT NULL REFERENCES assurance_tickets_r21(id),
 from_status TEXT NOT NULL, to_status TEXT NOT NULL,
 note TEXT NOT NULL, actor_id INTEGER NOT NULL, event_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assurance_pilot_starts_r21 (
 pilot_id INTEGER PRIMARY KEY REFERENCES pilots_r15(id),
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 readiness_id INTEGER NOT NULL REFERENCES readiness_days_r20(id),
 readiness_sha TEXT NOT NULL,
 preflight_json TEXT NOT NULL, preflight_sha TEXT NOT NULL,
 started_by INTEGER NOT NULL, started_at TEXT NOT NULL
);
"""


def ensure_schema(db:sqlite3.Connection)->None:
    db.executescript(DDL)


def canonical(v)->str:
    return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'))


def digest(v)->str:
    return hashlib.sha256(canonical(v).encode('utf-8')).hexdigest()


def sha_text(s:str)->str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def _safe_csv(rows,headers):
    f=io.StringIO(newline='');writer=csv.writer(f);writer.writerow(headers)
    for row in rows:writer.writerow([safe_spreadsheet_cell(str(row.get(h,''))) for h in headers])
    return '\ufeff'+f.getvalue()


def _stores(db,principal):
    rows=db.execute('SELECT * FROM stores WHERE organization_id=? ORDER BY id LIMIT 101',
                    (principal.organization_id,)).fetchall()
    if len(rows)>100:raise HTTPException(413,'Более ста филиалов: требуется постраничная обработка')
    allowed=[]
    for store in rows:
        try:check_store_access(db,store['id'],principal)
        except HTTPException:continue
        allowed.append(store)
    return allowed


def _review_state(db,readiness):
    if not readiness:return {'state':'missing','integrity':False,'sha':None,'status':None,'age_days':None}
    rec=db.execute('SELECT * FROM readiness_reviews_r20 WHERE readiness_id=?',(readiness['id'],)).fetchone()
    good=bool(rec and sha_text(rec['payload_json'])==rec['payload_sha'])
    status=readiness['status']
    return {'state':'verified' if status=='reviewed' and good else 'integrity_error' if rec and not good else status,
            'integrity':good,'sha':rec['payload_sha'] if good else None,
            'status':status,'age_days':None,'reviewer_id':rec['reviewer_id'] if rec else None}


def _latest_day(db,store_id):
    return db.execute('SELECT * FROM readiness_days_r20 WHERE store_id=? ORDER BY business_day DESC,id DESC LIMIT 1',
                      (store_id,)).fetchone()


def _t_scope(db,ticket_id,principal):
    row=db.execute('SELECT * FROM assurance_tickets_r21 WHERE id=? AND organization_id=?',
                   (ticket_id,principal.organization_id)).fetchone()
    if not row:raise HTTPException(404,'Задача не найдена')
    check_store_access(db,row['store_id'],principal)
    return row


def drift_report(db,store,days=30):
    if not 7<=days<=90:raise HTTPException(422,'Период должен быть от 7 до 90 дней')
    end=datetime.now(store_zone(store)).date()
    start=end-timedelta(days=days-1)
    records=db.execute('''SELECT d.business_day,d.status,c.id AS calibration_id,c.reference_count,
           c.counter_count,c.error_pct,c.method,c.created_at FROM readiness_days_r20 d
      JOIN readiness_calibrations_r20 c ON c.readiness_id=d.id
      WHERE d.store_id=? AND d.business_day>=? AND d.business_day<=?
      ORDER BY d.business_day ASC,c.id ASC LIMIT 5001''',
      (store['id'],start.isoformat(),end.isoformat())).fetchall()
    if len(records)>5000:raise HTTPException(413,'Слишком много замеров; уменьшите период')
    values=[];daily={};weak=0
    for r in records:
        d=dict(r); valid=d['reference_count']>=20 and d['error_pct'] is not None
        if not valid:weak+=1
        d['accepted_sample']=valid
        daily.setdefault(d['business_day'],[]).append(d)
        if valid:values.append(float(d['error_pct']))
    series=[]
    for day,rows in sorted(daily.items()):
        valid=[float(x['error_pct']) for x in rows if x['accepted_sample']]
        series.append({'day':day,'measurements':len(rows),'accepted':len(valid),
           'median_error_pct':round(median(valid),2) if valid else None,
           'over_tolerance':sum(v>10 for v in valid),
           'warnings':['Недостаточно проверенных наблюдений'] if len(valid)<2 else []})
    valid_days=sum(x['accepted']>=2 for x in series)
    high=sum(v>10 for v in values)
    status='no_data' if not values else 'drift' if high or (len(series)>=2 and series[-1]['median_error_pct'] and series[-1]['median_error_pct']>10) else 'limited' if valid_days<2 else 'observed'
    return {'store':store['slug'],'days':days,'status':status,'valid_calibrations':len(values),
      'insufficient_samples':weak,'above_10pct':high,'verified_days':valid_days,
      'median_error_pct':round(median(values),2) if values else None,'series':series,
      'notes':['Сравнение ручного подсчёта с показанием счётчика не удостоверяет датчик независимо.',
               'Отклонения выше 10% требуют ручной проверки, а не автоматической корректировки трафика.']}


def continuity_report(db,store,readiness=None):
    day=readiness or _latest_day(db,store['id'])
    if day is None:return {'store':store['slug'],'status':'missing','issues':['Нет зарегистрированной смены'],'day':None}
    rec=db.execute('''SELECT * FROM readiness_reconciliations_r20 WHERE readiness_id=? ORDER BY id DESC LIMIT 1''',
                   (day['id'],)).fetchone()
    snap=_review_state(db,day)
    if not rec:return {'store':store['slug'],'status':'missing','issues':['Нет сохранённой сверки'],'day':day['business_day'],
                         'readiness_id':day['id'],'review':snap,'recorded':None,'current':None}
    actual=observed_r20(db,store,day['business_day'])
    recorded={k:rec['store_'+k] if k in ('visits','receipts') else rec[k] for k in ('visits','receipts','voice_opens','voice_responses')}
    diff={k:actual[k]-recorded[k] for k in recorded}
    issues=[]
    if any(v!=0 for v in diff.values()):issues.append('События изменились после последней сохранённой сверки')
    if recorded['visits']==0:issues.append('Нет входов в сохранённой сверке')
    if recorded['receipts']==0:issues.append('Нет зарегистрированных кассовых чеков')
    if day['status']=='reviewed' and not snap['integrity']:issues.append('Контрольная сумма подписанного отчёта нарушена')
    return {'store':store['slug'],'day':day['business_day'],'readiness_id':day['id'],
       'status':'changed' if any(diff.values()) else 'verified_rows' if not issues else 'needs_attention',
       'recorded':recorded,'current':actual,'delta':diff,'issues':issues,'review':snap,
       'disclaimer':'Зарегистрированные чеки не подтверждают расчёт в банке. Нулевые изменения не доказывают полноту POS-данных.'}


def _issue_rows(db,store,readiness):
    r=readiness_view(db,readiness)
    issues=[('check:'+digest(i)[:16],i) for i in r['issues']]
    drift=drift_report(db,store,30)
    if drift['status']=='drift':issues.append(('calibration_drift','Калибровки за 30 дней отклонились более чем на 10%'))
    cont=continuity_report(db,store,readiness)
    if cont['status']=='changed':issues.append(('data_drift','События изменились после зафиксированной сверки'))
    if cont.get('review',{}).get('state')=='integrity_error':issues.append(('tampered_snapshot','Зафиксированный отчёт повреждён'))
    return issues


def _preflight(db,principal,pilot,readiness):
    store=db.execute('SELECT * FROM stores WHERE id=? AND organization_id=?',
                     (pilot['store_id'],principal.organization_id)).fetchone()
    if not store:raise HTTPException(404,'Филиал недоступен')
    issues=[]
    if pilot['status']!='draft':issues.append('Пилот уже не является черновиком')
    if not readiness:issues.append('Нет подходящей смены с проверенной готовностью')
    review=_review_state(db,readiness)
    cont=continuity_report(db,store,readiness) if readiness else None
    if not readiness or readiness['status']!='reviewed' or not review['integrity']:
        issues.append('Нет действующего неповреждённого заключения R2.0')
    else:
        if readiness['organization_id']!=principal.organization_id or readiness['store_id']!=pilot['store_id']:
            issues.append('Заключение другого филиала')
        if readiness['requested_by']==readiness['reviewed_by'] or review['reviewer_id']!=readiness['reviewed_by']:
            issues.append('Не соблюдена независимая проверка смены')
        try:
            age=(datetime.now(store_zone(store)).date()-date.fromisoformat(readiness['business_day'])).days
            if not 0<=age<=7:issues.append('Заключение старше семи дней или датировано будущим')
        except ValueError:issues.append('Некорректная дата смены')
    if cont and cont['status']!='verified_rows':issues.extend(cont.get('issues',[]) or ['Сверка источников требует проверки'])
    if readiness and _latest_day(db,store['id'])['id']!=readiness['id']:
        issues.append('Есть более новая смена: используйте её актуальное заключение')
    if drift_report(db,store,30)['status']=='drift':
        issues.append('Обнаружено превышение допуска в журнале калибровок за 30 дней')
    if readiness and review['integrity']:
        snapshot=db.execute('SELECT payload_json FROM readiness_reviews_r20 WHERE readiness_id=?',(readiness['id'],)).fetchone()
        try:
            frozen=json.loads(snapshot['payload_json'])
            current=readiness_view(db,readiness)
            if any(frozen[k]!=current[k] for k in ('checks','calibrations','reconciliations','handovers')):
                issues.append('Исходные записи готовности изменены после независимой проверки')
        except (KeyError,TypeError,ValueError):
            issues.append('Структура заключения не соответствует сохранённому отчёту')
    if readiness:
        if any(x>10 for x in (z['error_pct'] for z in db.execute('''SELECT error_pct FROM readiness_calibrations_r20
                         WHERE readiness_id=? AND reference_count>=20''',(readiness['id'],)) if z['error_pct'] is not None)):
            issues.append('Отклонения калибровки больше десяти процентов')
    open_tickets=db.execute('''SELECT COUNT(*) FROM assurance_tickets_r21 WHERE store_id=?
                             AND status IN ('open','working')''',(pilot['store_id'],)).fetchone()[0]
    if open_tickets:issues.append(f'Незакрытые задачи готовности: {open_tickets}')
    return {'pilot_id':pilot['id'],'store':store['slug'],'readiness_id':readiness['id'] if readiness else None,
            'readiness_sha':review['sha'],'readiness_status':review['status'],'continuity':cont,
            'open_tickets':open_tickets,'issues':list(dict.fromkeys(issues)),
            'ready':not issues,'checked_at':now_iso(),
            'disclaimer':'Процедурная готовность не является независимой экспертизой датчиков и не запускает публичный сервис.'}


class TicketSync(BaseModel):
    readiness_id:int=Field(gt=0)


class TicketAssignment(BaseModel):
    owner:str=Field(min_length=3,max_length=120)
    due_date:date


class TicketState(BaseModel):
    status:Literal['working','verified','dismissed']
    note:str=Field(min_length=12,max_length=600)


class SafeStartIn(BaseModel):
    readiness_id:int=Field(gt=0)


def build_router(admin,db_conn):
    router=APIRouter(prefix='/api/admin/r21',tags=['R2.1 Store Assurance'])

    @router.get('/portfolio')
    def portfolio(principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        items=[]
        for s in _stores(db,principal):
            latest=_latest_day(db,s['id'])
            review=_review_state(db,latest)
            if latest:
                review['age_days']=(datetime.now(store_zone(s)).date()-date.fromisoformat(latest['business_day'])).days
            tickets=db.execute("SELECT COUNT(*) FROM assurance_tickets_r21 WHERE store_id=? AND status IN ('open','working')",(s['id'],)).fetchone()[0]
            items.append({'slug':s['slug'],'store':s['name'],'store_id':s['id'],'readiness_id':latest['id'] if latest else None,
              'business_day':latest['business_day'] if latest else None,'status':review['state'],
              'integrity':review['integrity'],'age_days':review['age_days'],'open_tickets':tickets})
        return {'stores':items,'total':len(items),'reviewed':sum(x['status']=='verified' for x in items),
                'alerts':sum(x['status'] not in ('verified',) or x['open_tickets'] for x in items),
                'note':'Включены только филиалы, к которым у пользователя есть доступ.'}

    @router.get('/portfolio.csv')
    def portfolio_csv(principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        payload=portfolio(principal,db)
        return Response(_safe_csv(payload['stores'],['slug','store','business_day','status','integrity','age_days','open_tickets']),
                        media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="osmanx-store-assurance.csv"','Cache-Control':'no-store'})

    @router.get('/drift')
    def drift(slug:str='central',days:int=30,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        return drift_report(db,visible_store(db,slug,principal),days)

    @router.get('/continuity')
    def continuity(slug:str='central',readiness_id:int|None=None,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        s=visible_store(db,slug,principal)
        day=readiness_entry(db,readiness_id,principal) if readiness_id is not None else None
        if day is not None and day['store_id']!=s['id']:raise HTTPException(404,'Смена относится к другому филиалу')
        return continuity_report(db,s,day)

    @router.get('/tickets')
    def tickets(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        s=visible_store(db,slug,principal)
        return {'items':[dict(x) for x in db.execute('SELECT * FROM assurance_tickets_r21 WHERE store_id=? ORDER BY id DESC LIMIT 200',(s['id'],))]}

    @router.post('/tickets/sync')
    def sync(body:TicketSync,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            db.execute('BEGIN IMMEDIATE')
            row=readiness_entry(db,body.readiness_id,principal)
            store=db.execute('SELECT * FROM stores WHERE id=? AND organization_id=?',(row['store_id'],principal.organization_id)).fetchone()
            issues=_issue_rows(db,store,row)
            added=[];found=[]
            for key,description in issues:
                old=db.execute('SELECT * FROM assurance_tickets_r21 WHERE readiness_id=? AND issue_key=?',(row['id'],key)).fetchone()
                if old:
                    found.append(old['id']);continue
                stamp=now_iso();due=(datetime.now(store_zone(store)).date()+timedelta(days=2)).isoformat()
                cur=db.execute('''INSERT INTO assurance_tickets_r21(organization_id,store_id,readiness_id,issue_key,description,source_hash,
                  due_date,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                  (principal.organization_id,store['id'],row['id'],key,description,digest({'key':key,'description':description}),
                   due,principal.user_id,stamp,stamp))
                audit(db,principal,'r21.ticket.open',str(cur.lastrowid));added.append(cur.lastrowid)
            db.commit();return {'added':added,'existing':found,'issues_found':len(issues)}
        except Exception:db.rollback();raise

    @router.patch('/tickets/{ticket_id}/assign')
    def assign(ticket_id:int,body:TicketAssignment,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        if body.due_date<date.today() or body.due_date>date.today()+timedelta(days=365):raise HTTPException(422,'Срок вне допустимого периода')
        try:
            db.execute('BEGIN IMMEDIATE');r=_t_scope(db,ticket_id,principal)
            if r['status'] in ('verified','dismissed'):raise HTTPException(409,'Задача уже закрыта')
            db.execute('UPDATE assurance_tickets_r21 SET owner=?,due_date=?,updated_at=? WHERE id=?',
                       (body.owner.strip(),str(body.due_date),now_iso(),ticket_id))
            db.execute('INSERT INTO assurance_ticket_history_r21(ticket_id,from_status,to_status,note,actor_id,event_at) VALUES(?,?,?,?,?,?)',
                       (ticket_id,r['status'],r['status'],'Назначен: '+body.owner.strip(),principal.user_id,now_iso()))
            audit(db,principal,'r21.ticket.assign',str(ticket_id));db.commit()
            return {'id':ticket_id,'assigned':True}
        except Exception:db.rollback();raise

    @router.patch('/tickets/{ticket_id}')
    def update_ticket(ticket_id:int,body:TicketState,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            db.execute('BEGIN IMMEDIATE');r=_t_scope(db,ticket_id,principal)
            allowed={'open':('working','dismissed'),'working':('verified','dismissed')}
            if body.status not in allowed.get(r['status'],()):raise HTTPException(409,'Недопустимый переход')
            if body.status in ('verified','dismissed'):
                require_role(principal,'owner')
                if principal.user_id==r['created_by']:raise HTTPException(409,'Нужен независимый проверяющий')
            if body.status=='working' and not r['owner'].strip():raise HTTPException(409,'Сначала назначьте ответственного')
            db.execute('UPDATE assurance_tickets_r21 SET status=?,note=?,verified_by=?,updated_at=? WHERE id=?',
                       (body.status,body.note.strip(),principal.user_id if body.status in ('verified','dismissed') else None,now_iso(),ticket_id))
            db.execute('INSERT INTO assurance_ticket_history_r21(ticket_id,from_status,to_status,note,actor_id,event_at) VALUES(?,?,?,?,?,?)',
                       (ticket_id,r['status'],body.status,body.note.strip(),principal.user_id,now_iso()))
            audit(db,principal,'r21.ticket.update',f'{ticket_id}:{body.status}');db.commit()
            return {'id':ticket_id,'status':body.status,'disclaimer':'Закрытие задачи — ручное подтверждение, а не доказанная исправность оборудования.'}
        except Exception:db.rollback();raise

    @router.get('/tickets/{ticket_id}/history')
    def ticket_history(ticket_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        _t_scope(db,ticket_id,principal)
        return {'items':[dict(x) for x in db.execute('SELECT * FROM assurance_ticket_history_r21 WHERE ticket_id=? ORDER BY id',(ticket_id,))]}

    @router.get('/pilots/{pilot_id}/preflight')
    def preflight(pilot_id:int,readiness_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        pilot=db.execute('SELECT * FROM pilots_r15 WHERE id=? AND organization_id=?',(pilot_id,principal.organization_id)).fetchone()
        if not pilot:raise HTTPException(404,'Пилот не найден')
        check_store_access(db,pilot['store_id'],principal)
        day=readiness_entry(db,readiness_id,principal)
        if day['store_id']!=pilot['store_id']:raise HTTPException(404,'Заключение относится к другому филиалу')
        return _preflight(db,principal,pilot,day)

    @router.post('/pilots/{pilot_id}/safe-start')
    def safe_start(pilot_id:int,body:SafeStartIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            db.execute('BEGIN IMMEDIATE')
            pilot=db.execute('SELECT * FROM pilots_r15 WHERE id=? AND organization_id=?',(pilot_id,principal.organization_id)).fetchone()
            if not pilot:raise HTTPException(404,'Пилот не найден')
            check_store_access(db,pilot['store_id'],principal)
            readiness=readiness_entry(db,body.readiness_id,principal)
            if readiness['store_id']!=pilot['store_id']:raise HTTPException(404,'Нельзя использовать заключение другого магазина')
            previous=db.execute('SELECT * FROM assurance_pilot_starts_r21 WHERE pilot_id=?',(pilot_id,)).fetchone()
            if previous:
                if previous['readiness_id']!=body.readiness_id:raise HTTPException(409,'Пилот уже запущен с другим заключением')
                db.rollback();return {'id':pilot_id,'status':pilot['status'],'duplicate':True,'sha256':previous['preflight_sha']}
            check=_preflight(db,principal,pilot,readiness)
            if not check['ready']:raise HTTPException(409,'Запуск заблокирован: '+check['issues'][0])
            snapshot=canonical(check);sha=sha_text(snapshot)
            now=now_iso()
            updated=db.execute("UPDATE pilots_r15 SET status='running',started_at=? WHERE id=? AND status='draft'",(now,pilot_id))
            if updated.rowcount!=1:raise HTTPException(409,'Пилот уже изменил состояние')
            db.execute('''INSERT INTO assurance_pilot_starts_r21(pilot_id,organization_id,store_id,readiness_id,readiness_sha,
                       preflight_json,preflight_sha,started_by,started_at) VALUES(?,?,?,?,?,?,?,?,?)''',
                       (pilot_id,principal.organization_id,pilot['store_id'],readiness['id'],check['readiness_sha'],snapshot,sha,principal.user_id,now))
            audit(db,principal,'r21.pilot.safe_start',str(pilot_id));db.commit()
            return {'id':pilot_id,'status':'running','duplicate':False,'sha256':sha,
                    'note':'Запущен только процесс сбора результатов пилота, публичное размещение не выполнено.'}
        except Exception:db.rollback();raise

    @router.get('/pilots/{pilot_id}/startup-proof')
    def startup_proof(pilot_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        row=db.execute('SELECT * FROM assurance_pilot_starts_r21 WHERE pilot_id=? AND organization_id=?',(pilot_id,principal.organization_id)).fetchone()
        if not row:raise HTTPException(404,'Подтверждение запуска не найдено')
        check_store_access(db,row['store_id'],principal)
        good=sha_text(row['preflight_json'])==row['preflight_sha']
        return {'pilot_id':pilot_id,'integrity':good,'sha256':row['preflight_sha'],
                'report':json.loads(row['preflight_json']) if good else None,
                'warning':None if good else 'Контрольная сумма подтверждения повреждена'}

    return router
