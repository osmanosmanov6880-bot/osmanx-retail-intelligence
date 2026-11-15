"""R2.3 Security Center: scoped audits, remediation and recovery gates.

This module does not claim public-host readiness. Pilot startup is protected
separately by the R1.5 compatibility change and the R2.1 safe-start route.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sqlite3
import stat
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.database import now_iso
from backend.r23_core import authorization_findings, evidence_findings, integrity_report
from backend.retail import safe_spreadsheet_cell
from backend.security import Principal, audit, check_store_access, require_role, visible_store

SCHEMA = """
CREATE TABLE IF NOT EXISTS security_incidents_r23 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 request_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL,
 code TEXT NOT NULL, subject TEXT NOT NULL,
 issue_title TEXT NOT NULL,
 owner TEXT NOT NULL, due_date TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','working','verified')),
 created_by INTEGER NOT NULL, reviewed_by INTEGER,
 note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(organization_id,request_id)
);
CREATE INDEX IF NOT EXISTS idx_r23_incidents ON security_incidents_r23(organization_id,store_id,status);
CREATE TABLE IF NOT EXISTS security_incident_history_r23 (
 id INTEGER PRIMARY KEY,
 incident_id INTEGER NOT NULL REFERENCES security_incidents_r23(id),
 previous_status TEXT NOT NULL,
 next_status TEXT NOT NULL,
 note TEXT NOT NULL,
 actor_id INTEGER NOT NULL, created_at TEXT NOT NULL
);
"""


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)


def canonical(x):
    return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def sha(x):
    return hashlib.sha256(canonical(x).encode('utf-8')).hexdigest()


def _incident(db:sqlite3.Connection,identity:int,principal:Principal):
    result=db.execute('SELECT * FROM security_incidents_r23 WHERE id=? AND organization_id=?',
                      (identity,principal.organization_id)).fetchone()
    if not result:raise HTTPException(404,'Инцидент не найден')
    check_store_access(db,result['store_id'],principal)
    return result


def _current(db,principal:Principal,store):
    return integrity_report(db,principal.organization_id,store['id'])


def _backup_file_validation(path:Path)->dict:
    from scripts.backup_db import inspect_backup
    if path.is_symlink():raise ValueError('Symlink not allowed')
    result=inspect_backup(path)
    manifest=path.with_suffix('.json')
    if not manifest.is_file() or manifest.is_symlink():raise ValueError('Backup manifest missing or symlink')
    raw=json.loads(manifest.read_text(encoding='utf-8'))
    if raw.get('sha256')!=result['sha256']:raise ValueError('Backup manifest checksum mismatch')
    return result


def recovery_report(now:datetime|None=None):
    now=now or datetime.now(timezone.utc)
    path=os.getenv('OSMANX_BACKUP_DIR','').strip()
    result={'status':'blocked','backup_status':'not_configured','drill_status':'missing',
            'latest_backup_age_hours':None,'latest_drill_age_days':None,'backup_sha':None,
            'warnings':[],'methodology':'Проверка локальных файлов, manifest SHA и SQLite integrity. Не подтверждает внешнее резервирование или восстановление инфраструктуры.'}
    if not path:
        result['warnings'].append('Не задан OSMANX_BACKUP_DIR')
        return result
    directory=Path(path)
    if not directory.is_dir() or directory.is_symlink():
        result['backup_status']='unavailable';result['warnings'].append('Каталог резервных копий недоступен')
        return result
    perms=stat.S_IMODE(directory.stat().st_mode)
    if perms & 0o077:
        result['warnings'].append('Каталог копий доступен группе или другим пользователям')
    backups=sorted((x for x in directory.glob('retail-*.sqlite3') if x.is_file() and not x.is_symlink()),
                   key=lambda p:p.stat().st_mtime,reverse=True)
    if not backups:
        result['backup_status']='missing';result['warnings'].append('Нет резервных копий')
        return result
    newest=backups[0]
    age=(now.timestamp()-newest.stat().st_mtime)/3600
    result['latest_backup_age_hours']=round(age,1)
    try:
        scanned=_backup_file_validation(newest)
        result['backup_sha']=scanned['sha256']
        result['backup_status']='verified' if 0<=age<=24 else 'stale'
    except (OSError,ValueError,sqlite3.DatabaseError,json.JSONDecodeError) as exc:
        result['backup_status']='invalid';result['warnings'].append('Последняя резервная копия повреждена или не соответствует манифесту')
    drills=sorted((x for x in directory.glob('retail-*.drill.json') if x.is_file() and not x.is_symlink()),
                  key=lambda p:p.stat().st_mtime,reverse=True)
    if drills:
        latest=drills[0]
        drill_age=(now.timestamp()-latest.stat().st_mtime)/86400
        result['latest_drill_age_days']=round(drill_age,1)
        try:
            drill=json.loads(latest.read_text(encoding='utf-8'))
            verified=drill.get('ok') is True and drill.get('backup_sha')==result['backup_sha'] and drill.get('logical_matches') is True and bool(drill.get('logical_sha')) and bool(drill.get('restored_sha'))
            result['drill_status']='verified' if verified and 0<=drill_age<=30 else 'invalid_or_stale'
        except (ValueError,OSError,json.JSONDecodeError):
            result['drill_status']='invalid_or_stale'
    if result['backup_status']!='verified':result['warnings'].append('Нужна действительная резервная копия не старше 24 часов')
    if result['drill_status']!='verified':result['warnings'].append('Нет подтверждённой проверки восстановления с актуальной копии за 30 дней')
    if not result['warnings']:result['status']='ready_for_human_review'
    return result


class OpenIncident(BaseModel):
    slug: str='central'
    request_id: str=Field(min_length=12,max_length=100)
    code: str=Field(min_length=3,max_length=60)
    subject: str=Field(min_length=1,max_length=100)
    owner: str=Field(min_length=3,max_length=100)
    due_date: date


class IncidentUpdate(BaseModel):
    status: Literal['working','verified']
    note: str=Field(min_length=12,max_length=500)


def build_router(admin,db_conn):
    router=APIRouter(prefix='/api/admin/r23',tags=['R2.3 Security Center'])

    @router.get('/authorization')
    def authorization(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner');store=visible_store(db,slug,principal)
        rows=authorization_findings(db,principal.organization_id,store['id'])
        return {'store':store['slug'],'findings':rows,'blocking':len(rows),
                'note':'Структурная проверка доступов, не проникновенное тестирование.'}

    @router.get('/integrity')
    def integrity(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner');store=visible_store(db,slug,principal)
        return _current(db,principal,store)

    @router.get('/recovery')
    def recovery(principal:Principal=Depends(admin)):
        require_role(principal,'owner')
        return recovery_report()

    @router.get('/incidents')
    def incidents(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner');store=visible_store(db,slug,principal)
        return {'items':[dict(x) for x in db.execute('SELECT * FROM security_incidents_r23 WHERE store_id=? AND organization_id=? ORDER BY id DESC LIMIT 100',
                    (store['id'],principal.organization_id))]}

    @router.post('/incidents',status_code=201)
    def new_incident(body:OpenIncident,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner');store=visible_store(db,body.slug,principal)
        if body.due_date<date.today() or body.due_date>date.today()+timedelta(days=366):
            raise HTTPException(422,'Срок задачи должен быть от сегодня до года вперёд')
        params={'store_id':store['id'],**body.model_dump(mode='json')}
        fingerprint=sha(params)
        try:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT id,fingerprint FROM security_incidents_r23 WHERE organization_id=? AND request_id=?',
                           (principal.organization_id,body.request_id)).fetchone()
            if old:
                if old['fingerprint']!=fingerprint:raise HTTPException(409,'Ключ уже использован с другими параметрами')
                db.rollback();return {'id':old['id'],'duplicate':True}
            issue=next((x for x in _current(db,principal,store)['findings'] if x['code']==body.code and x['subject']==body.subject),None)
            if issue is None:raise HTTPException(409,'Такой действующей проблемы нет в аудите')
            existing=db.execute("""SELECT id FROM security_incidents_r23 WHERE organization_id=? AND store_id=? AND code=? AND subject=?
                       AND status IN ('open','working') LIMIT 1""",(principal.organization_id,store['id'],body.code,body.subject)).fetchone()
            if existing:raise HTTPException(409,'Проблема уже находится в работе')
            cur=db.execute('''INSERT INTO security_incidents_r23(organization_id,store_id,request_id,fingerprint,
                  code,subject,issue_title,owner,due_date,created_by,created_at,updated_at)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(principal.organization_id,store['id'],body.request_id,
                  fingerprint,issue['code'],issue['subject'],issue['title'],body.owner.strip(),str(body.due_date),
                  principal.user_id,now_iso(),now_iso()))
            audit(db,principal,'r23.incident.open',str(cur.lastrowid));db.commit()
            return {'id':cur.lastrowid,'duplicate':False}
        except Exception:db.rollback();raise

    @router.patch('/incidents/{incident_id}')
    def change_incident(incident_id:int,body:IncidentUpdate,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner')
        try:
            db.execute('BEGIN IMMEDIATE')
            record=_incident(db,incident_id,principal)
            expected={'open':('working',),'working':('verified',)}
            if body.status not in expected.get(record['status'],()):raise HTTPException(409,'Недопустимый переход статуса')
            if body.status=='verified':
                if record['created_by']==principal.user_id:
                    raise HTTPException(409,'Необходим независимый проверяющий, отличный от автора')
                store=db.execute('SELECT * FROM stores WHERE id=? AND organization_id=?',
                                 (record['store_id'],principal.organization_id)).fetchone()
                if any(f['code']==record['code'] and f['subject']==record['subject']
                       for f in _current(db,principal,store)['findings']):
                    raise HTTPException(409,'Проблема ещё присутствует в актуальных данных')
            db.execute('UPDATE security_incidents_r23 SET status=?,reviewed_by=?,note=?,updated_at=? WHERE id=?',
                       (body.status,principal.user_id if body.status=='verified' else None,body.note.strip(),now_iso(),incident_id))
            db.execute('''INSERT INTO security_incident_history_r23(incident_id,previous_status,next_status,note,actor_id,created_at)
                  VALUES(?,?,?,?,?,?)''',(incident_id,record['status'],body.status,body.note.strip(),principal.user_id,now_iso()))
            audit(db,principal,'r23.incident.update',f'{incident_id}:{body.status}');db.commit()
            return {'id':incident_id,'status':body.status}
        except Exception:db.rollback();raise

    @router.get('/incidents/{incident_id}/history')
    def incident_history(incident_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner');_incident(db,incident_id,principal)
        return {'items':[dict(x) for x in db.execute('SELECT previous_status,next_status,note,created_at FROM security_incident_history_r23 WHERE incident_id=? ORDER BY id',(incident_id,))]}

    @router.get('/release-gate')
    def release_gate(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner');store=visible_store(db,slug,principal)
        report=_current(db,principal,store);backups=recovery_report()
        outstanding=db.execute("SELECT COUNT(*) FROM security_incidents_r23 WHERE organization_id=? AND store_id=? AND status IN ('open','working')",
            (principal.organization_id,store['id'])).fetchone()[0]
        demo=os.getenv('OSMANX_DEMO_MODE','0')=='1'
        flags=[]
        if report['blocking']:flags.append('Не устранены ошибки целостности и доступа')
        if outstanding:flags.append('Открытые задачи по безопасности')
        if backups['status']!='ready_for_human_review':flags.append('Резервная копия и проверка восстановления не готовы')
        if demo:flags.append('Демонстрационный режим запрещён для реального магазина')
        return {'store':store['slug'],'status':'blocked' if flags else 'eligible_for_operator_review',
            'blocking':flags,'open_incidents':outstanding,'integrity':report,'recovery':backups,
            'warning':'Процедурная проверка, а не разрешение на публичную эксплуатацию. Требуется отдельный security review, HTTPS, privacy и проверка оборудования.'}

    @router.get('/report.csv')
    def report_csv(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        info=release_gate(slug,principal,db)
        output=io.StringIO(newline='');w=csv.writer(output)
        w.writerow(['Тип','Код','Объект','Статус','Описание'])
        for issue in info['integrity']['findings']:
            w.writerow(['Проверка',safe_spreadsheet_cell(issue['code']),safe_spreadsheet_cell(issue['subject']),issue['severity'],safe_spreadsheet_cell(issue['title'])])
        for item in info['blocking']:
            w.writerow(['Готовность','release_gate',safe_spreadsheet_cell(slug),'block',safe_spreadsheet_cell(item)])
        return Response('\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',headers={
            'Content-Disposition':'attachment; filename="osmanx-security-r23.csv"','Cache-Control':'no-store'})

    return router
