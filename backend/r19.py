"""R1.9 Field Operations: placement schedules, authenticated heartbeat, quality and incidents.

No biometric/person tracking, payment operations, third-party API calls, or public deployment.
A heartbeat proves only that a holder of the current placement key could reach the server.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from backend.database import now_iso
from backend.retail import safe_spreadsheet_cell
from backend.security import Principal, audit, require_role, visible_store, check_store_access
from backend.r17 import placement_public, placement_scope

SCHEMA = """
CREATE TABLE IF NOT EXISTS field_schedule_r19 (
 placement_id INTEGER PRIMARY KEY REFERENCES voice_placements_r17(id),
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 weekdays TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6',
 start_min INTEGER NOT NULL DEFAULT 540 CHECK(start_min BETWEEN 0 AND 1439),
 end_min INTEGER NOT NULL DEFAULT 1320 CHECK(end_min BETWEEN 1 AND 1440),
 revision INTEGER NOT NULL DEFAULT 1,
 updated_at TEXT NOT NULL, updated_by INTEGER,
 CHECK(start_min<end_min)
);
CREATE TABLE IF NOT EXISTS field_heartbeat_r19 (
 placement_id INTEGER PRIMARY KEY REFERENCES voice_placements_r17(id),
 last_seen TEXT NOT NULL, queue_depth INTEGER NOT NULL DEFAULT 0 CHECK(queue_depth BETWEEN 0 AND 25),
 app_version TEXT NOT NULL, network_state TEXT NOT NULL, total_heartbeats INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS field_heartbeat_events_r19 (
 id INTEGER PRIMARY KEY,
 placement_id INTEGER NOT NULL REFERENCES voice_placements_r17(id),
 request_id TEXT NOT NULL,
 payload_sha TEXT NOT NULL,
 received_at TEXT NOT NULL,
 UNIQUE(placement_id,request_id)
);
CREATE INDEX IF NOT EXISTS field_hb_events_idx ON field_heartbeat_events_r19(placement_id,received_at);
CREATE TABLE IF NOT EXISTS field_incidents_r19 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 placement_id INTEGER NOT NULL REFERENCES voice_placements_r17(id),
 signal TEXT NOT NULL CHECK(signal IN ('offline','backlog','burst','low_completion')),
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','acknowledged','resolved')),
 title TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
 detected_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(placement_id,signal)
);
CREATE INDEX IF NOT EXISTS field_incidents_idx ON field_incidents_r19(store_id,status,updated_at);
CREATE TABLE IF NOT EXISTS field_incident_history_r19 (
 id INTEGER PRIMARY KEY,
 incident_id INTEGER NOT NULL REFERENCES field_incidents_r19(id),
 previous_status TEXT NOT NULL, current_status TEXT NOT NULL,
 actor_id INTEGER, note TEXT NOT NULL, changed_at TEXT NOT NULL
);
"""


def ensure_schema(db:sqlite3.Connection)->None:
    db.executescript(SCHEMA)


def _utc_now()->datetime:
    return datetime.now(timezone.utc)


def _utc_parse(value:str)->datetime:
    try:
        parsed=datetime.fromisoformat(value)
        if parsed.tzinfo is None: raise ValueError('no timezone')
        return parsed.astimezone(timezone.utc)
    except (ValueError,TypeError):
        raise HTTPException(422,'Неверная дата источника') from None


def _store_for_placement(db, placement):
    store=db.execute('SELECT * FROM stores WHERE id=? AND organization_id=?',
                     (placement['store_id'],placement['organization_id'])).fetchone()
    if not store:raise HTTPException(404,'Филиал не найден')
    return store


def store_tz(store):
    # Store timezone is validated by the existing settings routes, but never trust old DB rows.
    try:return ZoneInfo(store['timezone'] or 'UTC')
    except (ZoneInfoNotFoundError,KeyError):return timezone.utc


def as_minutes(value:str)->int:
    try:
        hh,mm=value.split(':')
        if len(value)!=5 or not hh.isdigit() or not mm.isdigit():raise ValueError()
        hour,minute=int(hh),int(mm)
        if not (0<=hour<24 and 0<=minute<60):raise ValueError()
        return hour*60+minute
    except (ValueError,AttributeError):raise HTTPException(422,'Время должно быть в формате ЧЧ:ММ') from None


def fmt_min(value:int)->str:
    return f'{value//60:02d}:{value%60:02d}' if value<1440 else '24:00'


def schedule_state(db,placement,at=None)->dict:
    try:
        row=db.execute('SELECT * FROM field_schedule_r19 WHERE placement_id=?',(placement['id'],)).fetchone()
    except sqlite3.OperationalError as error:
        # Legacy integrations may initialize only R1.7 schema. Such placements
        # never had a schedule; keep default-open behavior. In the full app,
        # lifespan always initializes R1.9 tables before serving traffic.
        if 'no such table: field_schedule_r19' not in str(error):
            raise
        row=None
    store=_store_for_placement(db,placement)
    tz=store_tz(store)
    moment=(at or _utc_now()).astimezone(tz)
    if not row:
        return {'is_open':True,'configured':False,'enabled':True,'weekdays':[0,1,2,3,4,5,6],
                'start':'00:00','end':'24:00','revision':0,'timezone':str(tz),'local_time':moment.isoformat(timespec='minutes')}
    days=[int(x) for x in row['weekdays'].split(',')]
    minute=moment.hour*60+moment.minute
    is_open=bool(row['enabled']) and moment.weekday() in days and row['start_min']<=minute<row['end_min']
    return {'is_open':is_open,'configured':True,'enabled':bool(row['enabled']),
            'weekdays':days,'start':fmt_min(row['start_min']),'end':fmt_min(row['end_min']),
            'revision':row['revision'],'timezone':str(tz),'local_time':moment.isoformat(timespec='minutes')}


def require_schedule(db,placement)->None:
    # Legacy placements without schedule keep working by default. Check applies to form and new opens.
    if not schedule_state(db,placement)['is_open']:
        raise HTTPException(423,'Сейчас опрос не проводится. Пожалуйста, обратитесь к сотруднику.')


def placement_health(db,p,at=None)->dict:
    event=db.execute('SELECT * FROM field_heartbeat_r19 WHERE placement_id=?',(p['id'],)).fetchone()
    if not p['active']:
        return {'state':'disabled','last_seen':None,'seconds_since':None,'queue_depth':None,'app_version':None}
    if not event:
        return {'state':'unpaired','last_seen':None,'seconds_since':None,'queue_depth':None,'app_version':None}
    age=max(0,int(((at or _utc_now())-_utc_parse(event['last_seen'])).total_seconds()))
    state='online' if age<=150 else 'delayed' if age<=600 else 'offline'
    return {'state':state,'last_seen':event['last_seen'],'seconds_since':age,
            'queue_depth':event['queue_depth'],'app_version':event['app_version']}


def _placement(db, pid:int, principal:Principal):
    return placement_scope(db,pid,principal)


def quality_report(db,store,days=7):
    if not 1<=days<=30:raise HTTPException(422,'Период от 1 до 30 дней')
    cutoff=(_utc_now()-timedelta(days=days)).isoformat(timespec='seconds')
    rows=db.execute('''SELECT p.id,p.name,p.medium,p.active,
      (SELECT COUNT(*) FROM voice_opens_r17 o WHERE o.placement_id=p.id AND o.opened_at>=?) AS opens,
      (SELECT COUNT(*) FROM voice_responses_r17 r WHERE r.placement_id=p.id AND r.submitted_at>=?) AS responses
      FROM voice_placements_r17 p WHERE p.store_id=? AND p.organization_id=? ORDER BY p.id DESC LIMIT 201''',
      (cutoff,cutoff,store['id'],store['organization_id'])).fetchall()
    if len(rows)>200:raise HTTPException(413,'Слишком много терминалов')
    result=[]
    for p in rows:
        event=db.execute('''SELECT r.submitted_at, o.opened_at FROM voice_responses_r17 r
          LEFT JOIN voice_opens_r17 o ON o.placement_id=r.placement_id AND o.request_id=r.request_id
          WHERE r.placement_id=? AND r.submitted_at>=? ORDER BY r.id DESC LIMIT 5001''',
          (p['id'],cutoff)).fetchall()
        if len(event)>5000:
            result.append({'id':p['id'],'name':p['name'],'status':'too_many','warnings':['Сократите период: больше 5000 анкет.']})
            continue
        by_minute=Counter();very_fast=0
        for x in event:
            stamp=_utc_parse(x['submitted_at']);by_minute[stamp.strftime('%Y-%m-%dT%H:%M')]+=1
            if x['opened_at'] and 0<= (stamp-_utc_parse(x['opened_at'])).total_seconds()<4:
                very_fast+=1
        opens=p['opens'];responses=p['responses'];peak=max(by_minute.values(),default=0)
        completion=round(100*responses/opens,1) if opens else None
        fast_ratio=round(100*very_fast/len(event),1) if event else 0
        warnings=[]
        if responses<20:warnings.append('Менее 20 ответов — низкая устойчивость долей.')
        if completion is not None and completion>100:warnings.append('Ответов больше открытий: проверьте журнал источника.')
        if peak>=15:warnings.append('Высокая плотность ответов за одну минуту — проверьте терминал.')
        if len(event)>=10 and fast_ratio>=25:warnings.append('Необычно много ответов быстрее 4 секунд — нужна ручная проверка.')
        result.append({'id':p['id'],'name':p['name'],'medium':p['medium'],'opens':opens,
                       'responses':responses,'completion_pct':completion,'peak_per_minute':peak,
                       'fast_responses':very_fast,'fast_pct':fast_ratio,'warnings':warnings,
                       'status':'review' if any('проверьте' in w or 'проверка' in w for w in warnings) else 'observing'})
    return {'store':store['slug'],'days':days,'items':result,
        'methodology':'Ответы добровольны, открытия не равны уникальным покупателям. Сигналы аномалий — только повод для ручной проверки.'}


class ScheduleIn(BaseModel):
    expected_revision:int=Field(ge=0)
    enabled:bool=True
    weekdays:list[int]=Field(min_length=1,max_length=7)
    start:str
    end:str
    @field_validator('weekdays')
    @classmethod
    def verify_days(cls,days):
        if len(set(days))!=len(days) or any(type(day)is not int or not 0<=day<=6 for day in days):
            raise ValueError('Укажите уникальные дни от понедельника (0) до воскресенья (6)')
        return sorted(days)


class HeartbeatIn(BaseModel):
    request_id:str=Field(min_length=16,max_length=100)
    queue_depth:int=Field(ge=0,le=25)
    app_version:str=Field(min_length=2,max_length=36,pattern=r'^[a-zA-Z0-9._-]+$')
    network_state:Literal['online','recovering']='online'


class IncidentIn(BaseModel):
    status:Literal['acknowledged','resolved']
    note:str=Field(min_length=12,max_length=500)


def _csv(items,fields):
    f=io.StringIO(newline='');w=csv.writer(f);w.writerow(fields)
    for x in items:w.writerow([safe_spreadsheet_cell(x.get(key,'')) for key in fields])
    return '\ufeff'+f.getvalue()


def build_router(admin,db_conn):
    router=APIRouter()

    @router.post('/api/voice/r19/{public_id}/heartbeat',status_code=201)
    def heartbeat(public_id:str,body:HeartbeatIn,x_voice_key:str|None=Header(default=None,alias='X-OSMANX-Voice-Key'),
                  db:sqlite3.Connection=Depends(db_conn)):
        # Authenticated with exact currently active R1.7 placement key, independent of any manager session.
        data=body.model_dump(mode='json');fingerprint=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
        try:
            db.execute('BEGIN IMMEDIATE');p=placement_public(db,public_id,x_voice_key)
            old=db.execute('SELECT payload_sha FROM field_heartbeat_events_r19 WHERE placement_id=? AND request_id=?',
                           (p['id'],body.request_id)).fetchone()
            if old:
                if old['payload_sha']!=fingerprint:raise HTTPException(409,'Повтор события с другим содержимым')
                db.commit();return {'received':True,'duplicate':True}
            stamp=now_iso()
            db.execute('INSERT INTO field_heartbeat_events_r19(placement_id,request_id,payload_sha,received_at) VALUES(?,?,?,?)',
                       (p['id'],body.request_id,fingerprint,stamp))
            db.execute('''INSERT INTO field_heartbeat_r19(placement_id,last_seen,queue_depth,app_version,network_state,total_heartbeats)
               VALUES(?,?,?,?,?,1) ON CONFLICT(placement_id) DO UPDATE SET
                 last_seen=excluded.last_seen,queue_depth=excluded.queue_depth,app_version=excluded.app_version,
                 network_state=excluded.network_state,total_heartbeats=field_heartbeat_r19.total_heartbeats+1''',
                 (p['id'],stamp,body.queue_depth,body.app_version,body.network_state))
            # Keep at most 500 recent receipt IDs per tablet; old keys can no longer be replayed after rotation.
            db.execute('''DELETE FROM field_heartbeat_events_r19 WHERE placement_id=? AND id NOT IN (
                SELECT id FROM field_heartbeat_events_r19 WHERE placement_id=? ORDER BY id DESC LIMIT 500)''',(p['id'],p['id']))
            db.commit();return {'received':True,'duplicate':False,'server_time':stamp}
        except Exception:db.rollback();raise

    @router.get('/api/admin/r19/fleet')
    def fleet(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        placements=db.execute('SELECT * FROM voice_placements_r17 WHERE store_id=? AND organization_id=? ORDER BY id DESC LIMIT 200',
                              (store['id'],principal.organization_id)).fetchall()
        data=[]
        for p in placements:
            data.append({'id':p['id'],'name':p['name'],'medium':p['medium'],'active':bool(p['active']),
                         'public_id':p['public_id'],'health':placement_health(db,p),'schedule':schedule_state(db,p)})
        online=sum(x['health']['state']=='online' for x in data)
        return {'store':slug,'items':data,'online':online,'total':len(data),
                'note':'Онлайн означает только недавний подписанный сигнал терминала, не калибровку оборудования.'}

    @router.get('/api/admin/r19/fleet.csv')
    def fleet_csv(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        result=fleet(slug,principal,db)
        rows=[{'placement':x['name'],'medium':x['medium'],'state':x['health']['state'],
               'last_seen':x['health']['last_seen'] or '', 'queue_depth':x['health']['queue_depth'] or 0,
               'schedule':x['schedule']['start']+'-'+x['schedule']['end']} for x in result['items']]
        return Response(_csv(rows,['placement','medium','state','last_seen','queue_depth','schedule']),
          media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="osmanx-field-fleet.csv"','Cache-Control':'no-store'})

    @router.get('/api/admin/r19/placements/{placement_id}/schedule')
    def schedule_get(placement_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        return schedule_state(db,_placement(db,placement_id,principal))

    @router.put('/api/admin/r19/placements/{placement_id}/schedule')
    def schedule_put(placement_id:int,body:ScheduleIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        start,end=as_minutes(body.start),(1440 if body.end=='24:00' else as_minutes(body.end))
        if end<=start:raise HTTPException(422,'Конец периода должен быть позже начала')
        try:
            db.execute('BEGIN IMMEDIATE');p=_placement(db,placement_id,principal)
            existing=db.execute('SELECT revision FROM field_schedule_r19 WHERE placement_id=?',(placement_id,)).fetchone()
            current=existing['revision'] if existing else 0
            if body.expected_revision!=current:raise HTTPException(409,'Расписание изменилось. Обновите данные.')
            db.execute('''INSERT INTO field_schedule_r19(placement_id,enabled,weekdays,start_min,end_min,revision,updated_at,updated_by)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(placement_id) DO UPDATE SET
                enabled=excluded.enabled,weekdays=excluded.weekdays,start_min=excluded.start_min,
                end_min=excluded.end_min,revision=excluded.revision,
                updated_at=excluded.updated_at,updated_by=excluded.updated_by''',
                (placement_id,int(body.enabled),','.join(str(d) for d in body.weekdays),start,end,current+1,now_iso(),principal.user_id))
            audit(db,principal,'field.schedule.update',str(placement_id));db.commit()
            return schedule_state(db,p)
        except Exception:db.rollback();raise

    @router.get('/api/admin/r19/quality')
    def quality(slug:str='central',days:int=7,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        return quality_report(db,visible_store(db,slug,principal),days)

    @router.get('/api/admin/r19/quality.csv')
    def quality_csv(slug:str='central',days:int=7,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        report=quality(slug,days,principal,db)
        return Response(_csv(report['items'],['name','opens','responses','completion_pct','peak_per_minute','fast_responses','status']),
           media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="osmanx-field-quality.csv"','Cache-Control':'no-store'})

    @router.get('/api/admin/r19/incidents')
    def incidents(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        rows=db.execute('SELECT * FROM field_incidents_r19 WHERE store_id=? AND organization_id=? ORDER BY updated_at DESC,id DESC LIMIT 200',
                        (store['id'],principal.organization_id)).fetchall()
        return {'items':[dict(x) for x in rows]}

    @router.post('/api/admin/r19/incidents/sync')
    def sync(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        store=visible_store(db,slug,principal)
        candidates=[]
        for p in db.execute('SELECT * FROM voice_placements_r17 WHERE store_id=? AND active=1',(store['id'],)).fetchall():
            health=placement_health(db,p)
            if health['state']=='offline':candidates.append((p,'offline','Терминал не передаёт сигналы'))
            if health['queue_depth'] is not None and health['queue_depth']>=5:
                candidates.append((p,'backlog','На планшете накопились неотправленные ответы'))
        report=quality_report(db,store,1)
        for item in report['items']:
            if item.get('peak_per_minute',0)>=15:
                p=db.execute('SELECT * FROM voice_placements_r17 WHERE id=?',(item['id'],)).fetchone()
                candidates.append((p,'burst','Необычная частота ответов за минуту'))
            if item.get('opens',0)>=40 and item.get('completion_pct') is not None and item['completion_pct']<15:
                p=db.execute('SELECT * FROM voice_placements_r17 WHERE id=?',(item['id'],)).fetchone()
                candidates.append((p,'low_completion','Необычно низкая доля завершённых опросов'))
        changed=0
        try:
            db.execute('BEGIN IMMEDIATE')
            for p,signal,title in candidates:
                old=db.execute('SELECT * FROM field_incidents_r19 WHERE placement_id=? AND signal=?',
                               (p['id'],signal)).fetchone()
                if old:
                    if old['status']!='resolved':continue
                    db.execute('UPDATE field_incidents_r19 SET status=?,note=?,updated_at=?,detected_at=? WHERE id=?',
                               ('open','Повторный сигнал',now_iso(),now_iso(),old['id']))
                    db.execute('INSERT INTO field_incident_history_r19(incident_id,previous_status,current_status,actor_id,note,changed_at) VALUES(?,?,?,?,?,?)',
                               (old['id'],'resolved','open',principal.user_id,'Повторный сигнал',now_iso()))
                else:
                    db.execute('INSERT INTO field_incidents_r19(organization_id,store_id,placement_id,signal,title,detected_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                               (principal.organization_id,store['id'],p['id'],signal,title,now_iso(),now_iso()))
                changed+=1
            audit(db,principal,'field.incidents.sync',slug);db.commit()
            return {'signals':len(candidates),'created_or_reopened':changed}
        except Exception:db.rollback();raise

    @router.patch('/api/admin/r19/incidents/{incident_id}')
    def incident_transition(incident_id:int,body:IncidentIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            db.execute('BEGIN IMMEDIATE')
            incident=db.execute('SELECT * FROM field_incidents_r19 WHERE id=? AND organization_id=?',
                                (incident_id,principal.organization_id)).fetchone()
            if not incident:raise HTTPException(404,'Инцидент не найден')
            check_store_access(db,incident['store_id'],principal)
            previous=incident['status'];allowed={'open':'acknowledged','acknowledged':'resolved'}
            if allowed.get(previous)!=body.status:raise HTTPException(409,'Некорректный переход статуса')
            db.execute('UPDATE field_incidents_r19 SET status=?,note=?,updated_at=? WHERE id=?',
                       (body.status,body.note.strip(),now_iso(),incident_id))
            db.execute('''INSERT INTO field_incident_history_r19(incident_id,previous_status,current_status,actor_id,note,changed_at)
                          VALUES(?,?,?,?,?,?)''',(incident_id,previous,body.status,principal.user_id,body.note.strip(),now_iso()))
            audit(db,principal,'field.incident.transition',str(incident_id));db.commit()
            return {'id':incident_id,'status':body.status}
        except Exception:db.rollback();raise

    @router.get('/api/admin/r19/incidents/{incident_id}/history')
    def incident_history(incident_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        item=db.execute('SELECT * FROM field_incidents_r19 WHERE id=? AND organization_id=?',
                        (incident_id,principal.organization_id)).fetchone()
        if not item:raise HTTPException(404,'Инцидент не найден')
        check_store_access(db,item['store_id'],principal)
        return {'items':[dict(x) for x in db.execute('SELECT * FROM field_incident_history_r19 WHERE incident_id=? ORDER BY id',
                                                      (incident_id,))]}

    return router
