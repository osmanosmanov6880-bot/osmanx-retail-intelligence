"""R1.0 Experience Operations: comparable stores, shift capacity, help SLA,
paired anonymous pulse surveys and auditable incident response.

This does not recognize faces, identify shoppers, forecast profits or grant
real discounts. Store-level observations are never represented as individual intent.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from backend.database import now_iso
from backend.kiosk import verify as verify_kiosk
from backend.security import Principal, audit, check_store_access, require_role, visible_store

SCHEMA = """
CREATE TABLE IF NOT EXISTS store_service_targets_r10 (
 store_id INTEGER PRIMARY KEY REFERENCES stores(id),
 accept_minutes INTEGER NOT NULL CHECK(accept_minutes BETWEEN 1 AND 60),
 resolve_minutes INTEGER NOT NULL CHECK(resolve_minutes BETWEEN 2 AND 180),
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staff_shifts_r10 (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), user_id INTEGER REFERENCES users(id),
 label TEXT NOT NULL, capacity_per_hour INTEGER NOT NULL CHECK(capacity_per_hour BETWEEN 1 AND 500),
 start_at TEXT NOT NULL, end_at TEXT NOT NULL,
 request_id TEXT NOT NULL, payload_sha TEXT NOT NULL,
 cancelled_at TEXT, created_at TEXT NOT NULL,
 UNIQUE(organization_id,request_id)
);
CREATE INDEX IF NOT EXISTS idx_r10_shifts ON staff_shifts_r10(store_id,start_at,end_at);
CREATE TABLE IF NOT EXISTS pulse_campaigns_r10 (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 title TEXT NOT NULL, question TEXT NOT NULL, options_json TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 0 CHECK(active IN (0,1)),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_r10_one_active_pulse ON pulse_campaigns_r10(store_id) WHERE active=1;
CREATE TABLE IF NOT EXISTS pulse_responses_r10 (
 id INTEGER PRIMARY KEY, campaign_id INTEGER NOT NULL REFERENCES pulse_campaigns_r10(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 request_id TEXT NOT NULL, option_index INTEGER NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(store_id,request_id)
);
CREATE INDEX IF NOT EXISTS idx_r10_responses ON pulse_responses_r10(campaign_id,created_at);
CREATE TABLE IF NOT EXISTS incidents_r10 (
 id INTEGER PRIMARY KEY,organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 incident_key TEXT NOT NULL,kind TEXT NOT NULL,title TEXT NOT NULL,
 evidence TEXT NOT NULL,severity TEXT NOT NULL CHECK(severity IN ('medium','high')),
 status TEXT NOT NULL CHECK(status IN ('new','acknowledged','resolved')),
 note TEXT NOT NULL DEFAULT '',task_id INTEGER REFERENCES action_tasks_r08(id),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(store_id,incident_key)
);
CREATE INDEX IF NOT EXISTS idx_r10_incidents ON incidents_r10(store_id,status,created_at);
"""


def ensure_schema(db:sqlite3.Connection)->None:
    db.executescript(SCHEMA)


def canonical(data)->str:
    return json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def fingerprint(data)->str:
    return hashlib.sha256(canonical(data).encode()).hexdigest()


def store_tz(store):
    try:return ZoneInfo(store['timezone'] or 'UTC')
    except (KeyError,ZoneInfoNotFoundError):return timezone.utc


def ts(value)->datetime:
    try:
        parsed=datetime.fromisoformat(value)
        if parsed.tzinfo is None:raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError,TypeError):raise HTTPException(422,'Неверная дата с часовым поясом') from None


def range_days(days:int):
    if not 7<=days<=30:raise HTTPException(422,'Период 7–30 дней')
    return datetime.now(timezone.utc)-timedelta(days=days),datetime.now(timezone.utc)


def safe_number(n:int,rows:int):
    return round(n/rows*100,1) if rows>0 else None


def accessible_stores(db,principal):
    rows=db.execute('SELECT * FROM stores WHERE organization_id=? ORDER BY id',(principal.organization_id,)).fetchall()
    result=[]
    for row in rows:
        try:check_store_access(db,row['id'],principal);result.append(row)
        except HTTPException:pass
    return result


def benchmark(db,principal,days:int=14,source_mode:Literal['sensor','manual']='sensor'):
    start,end=range_days(days)
    stores=accessible_stores(db,principal)
    if len(stores)>100:raise HTTPException(413,'Слишком много филиалов для одного отчёта')
    rows=[]
    for store in stores:
        visits=db.execute('SELECT quantity,source,occurred_at FROM visits WHERE store_id=? AND occurred_at>=? ORDER BY id DESC LIMIT 100001',
                         (store['id'],(start-timedelta(days=2)).isoformat(timespec='seconds'))).fetchall()
        sales=db.execute('SELECT amount_kopeks,source,occurred_at FROM sales WHERE store_id=? AND occurred_at>=? ORDER BY id DESC LIMIT 100001',
                        (store['id'],(start-timedelta(days=2)).isoformat(timespec='seconds'))).fetchall()
        if len(visits)>100000 or len(sales)>100000:raise HTTPException(413,'Выберите более короткий период или выгрузку')
        def inwindow(v):
            try:return start<=ts(v['occurred_at'])<end
            except HTTPException:return False
        traffic=[r for r in visits if inwindow(r) and 'demo' not in r['source'].casefold() and ((source_mode=='manual' and r['source']=='manual') or (source_mode=='sensor' and r['source'] in ('signed_sensor','sensor','traffic')))]
        checks=[r for r in sales if inwindow(r) and 'demo' not in r['source'].casefold()]
        visits_count=sum(r['quantity'] for r in traffic)
        receipts=len(checks)
        sum_amount=sum(r['amount_kopeks'] for r in checks)
        other=sum(r['quantity'] for r in visits if inwindow(r) and 'demo' not in r['source'].casefold() and r not in traffic)
        demo_detected=any(inwindow(r) and 'demo' in r['source'].casefold() for r in visits+sales)
        warnings=[]
        if visits_count<30:warnings.append('Недостаточно подтверждённых входов для сравнения (нужно ≥30).')
        if other:warnings.append('Другие источники потока исключены, чтобы не суммировать их дважды.')
        if demo_detected:warnings.append('Демонстрационные данные исключены из расчёта.')
        if any(r['source']=='manual' for r in checks):warnings.append('Часть чеков внесена вручную; нет независимого подтверждения кассового источника.')
        if receipts>visits_count and visits_count>0:warnings.append('Чеков больше, чем входов: проверьте кассовый источник.')
        rows.append({'slug':store['slug'],'name':store['name'],'visits':visits_count,'checks':receipts,
                     'revenue_kopeks':sum_amount,'checks_per_100_visits':round(receipts/visits_count*100,1) if visits_count else None,
                     'avg_check_kopeks':round(sum_amount/receipts) if receipts else None,'comparable':visits_count>=30 and receipts<=visits_count and not demo_detected,
                     'warnings':warnings})
    return {'days':days,'source_mode':source_mode,'stores':rows,
            'method':'Чеков на 100 входов по одному выбранному источнику, без демоданных. Не является конверсией уникальных покупателей.',
            'warning':'Разница между магазинами не доказывает качество сотрудников или причину продаж.'}


def service_report(db,store,days:int=14):
    start,end=range_days(days)
    target=db.execute('SELECT * FROM store_service_targets_r10 WHERE store_id=?',(store['id'],)).fetchone()
    accept=target['accept_minutes'] if target else 3
    resolve=target['resolve_minutes'] if target else 12
    rows=db.execute('SELECT * FROM assistance_requests_r07 WHERE store_id=? ORDER BY id DESC LIMIT 100001',(store['id'],)).fetchall()
    if len(rows)>100000:raise HTTPException(413,'Слишком много обращений')
    samples=[];now=datetime.now(timezone.utc)
    for row in rows:
        try:created=ts(row['created_at'])
        except HTTPException:continue
        if not start<=created<end:continue
        accepted=ts(row['accepted_at']) if row['accepted_at'] else None
        resolved=ts(row['resolved_at']) if row['resolved_at'] else None
        accept_sec=max(0,(accepted-created).total_seconds()) if accepted else None
        resolve_sec=max(0,(resolved-created).total_seconds()) if resolved else None
        samples.append({'id':row['id'],'status':row['status'],'category':row['category'],
                        'wait_seconds':accept_sec,'resolve_seconds':resolve_sec,
                        'accept_overdue':(accept_sec or (now-created).total_seconds())>accept*60 and row['status']!='cancelled',
                        'resolve_overdue':(resolve_sec or (now-created).total_seconds())>resolve*60 and row['status'] not in ('cancelled',)})
    attended=[x for x in samples if x['wait_seconds'] is not None]
    completed=[x for x in samples if x['resolve_seconds'] is not None]
    def percentile(vals,ratio):
        if not vals:return None
        seq=sorted(vals);return round(seq[int((len(seq)-1)*ratio)]/60,1)
    return {'days':days,'targets':{'accept_minutes':accept,'resolve_minutes':resolve},'total':len(samples),
      'accepted':len(attended),'resolved':len(completed),
      'accepted_within_sla':sum(x['wait_seconds']<=accept*60 for x in attended),
      'resolved_within_sla':sum(x['resolve_seconds']<=resolve*60 for x in completed),
      'accept_rate_percent':safe_number(sum(x['wait_seconds']<=accept*60 for x in attended),len(attended)),
      'resolve_rate_percent':safe_number(sum(x['resolve_seconds']<=resolve*60 for x in completed),len(completed)),
      'pending_overdue':sum(x['accept_overdue'] and x['status']=='open' for x in samples),
      'p50_accept_minutes':percentile([x['wait_seconds'] for x in attended],.5),
      'p90_accept_minutes':percentile([x['wait_seconds'] for x in attended],.9),
      'recent':samples[:50],
      'notes':['Ожидание считается от нажатия покупателем кнопки до принятия обращения.','Нет персонального отслеживания покупателей.','Для принятия статистических решений требуется достаточный объём наблюдений.']}


def shift_report(db,store,day:date):
    local=store_tz(store)
    items=[dict(x) for x in db.execute('''SELECT sh.*,u.full_name FROM staff_shifts_r10 sh
     LEFT JOIN users u ON u.id=sh.user_id
     WHERE sh.store_id=? AND sh.cancelled_at IS NULL ORDER BY sh.start_at LIMIT 200''',(store['id'],))]
    result=[]
    for hour in range(10,23):
        moment=datetime.combine(day,time(hour,30),tzinfo=local).astimezone(timezone.utc)
        active=[x for x in items if ts(x['start_at'])<=moment<ts(x['end_at'])]
        start=moment.replace(minute=0,second=0,microsecond=0)
        events=db.execute('SELECT quantity,source,occurred_at FROM visits WHERE store_id=? AND occurred_at>=? AND occurred_at<?',
                          (store['id'],(start-timedelta(hours=1)).isoformat(timespec='seconds'),(start+timedelta(hours=2)).isoformat(timespec='seconds'))).fetchall()
        traffic=sum(x['quantity'] for x in events if 'demo' not in x['source'].casefold() and 'manual' not in x['source'].casefold() and x['occurred_at'] and ts(x['occurred_at']).astimezone(local).date()==day and ts(x['occurred_at']).astimezone(local).hour==hour)
        capacity=sum(x['capacity_per_hour'] for x in active)
        result.append({'hour':hour,'recorded_visitors':traffic,'planned_capacity':capacity,
                       'capacity_gap':max(0,traffic-capacity) if traffic else None,'staffed':len(active)})
    return {'day':str(day),'shifts':[x for x in items if ts(x['start_at']).astimezone(local).date()<=day<=ts(x['end_at']).astimezone(local).date()],
            'hours':result,'method':'Сравнение зарегистрированных входов с заявленной пропускной способностью смен; не прогноз продаж.',
            'warnings':['Без подключённого датчика нулевой поток не означает отсутствие покупателей.']}


def scoped_incident(db,incident_id,principal):
    row=db.execute('SELECT * FROM incidents_r10 WHERE id=? AND organization_id=?',(incident_id,principal.organization_id)).fetchone()
    if not row:raise HTTPException(404,'Инцидент не найден')
    check_store_access(db,row['store_id'],principal)
    return row


def incident_signals(db,store):
    today=datetime.now(timezone.utc).astimezone(store_tz(store)).date().isoformat()
    signals=[]
    incomplete=db.execute('''SELECT COUNT(*) FROM sales s WHERE s.store_id=? AND s.occurred_at>=?
       AND NOT EXISTS (SELECT 1 FROM sale_items i WHERE i.sale_id=s.id AND i.store_id=s.store_id)
       AND s.source NOT LIKE '%demo%' ''',(store['id'],(datetime.now(timezone.utc)-timedelta(days=3)).isoformat(timespec='seconds'))).fetchone()[0]
    if incomplete>=3:signals.append((f'without-lines:{today}','missing_receipt_items','У чеков отсутствуют товарные строки',
      f'{incomplete} чеков за последние 3 дня не позволяют надёжно посчитать маржу','high'))
    tasks=db.execute("SELECT COUNT(*) FROM action_tasks_r08 WHERE store_id=? AND status IN ('open','in_progress') AND due_date<?",(store['id'],today)).fetchone()[0]
    if tasks:signals.append((f'overdue-tasks:{today}','overdue_tasks','Задачи с просроченным сроком',f'{tasks} открытых задач требуют решения','medium'))
    services=service_report(db,store,days=7)
    if services['pending_overdue']:
        signals.append((f'overdue-assistance:{today}','service_sla','Покупатель ожидает помощь',
          f"{services['pending_overdue']} необработанных обращений превысили {services['targets']['accept_minutes']} мин.",'high'))
    return signals


class ServiceTarget(BaseModel):
    slug:str='central'
    accept_minutes:int=Field(ge=1,le=60)
    resolve_minutes:int=Field(ge=2,le=180)

class ShiftNew(BaseModel):
    slug:str='central'
    user_id:int|None=None
    label:str=Field(min_length=2,max_length=80)
    capacity_per_hour:int=Field(ge=1,le=500)
    start_at:datetime
    end_at:datetime
    request_id:str=Field(min_length=12,max_length=100)
    @model_validator(mode='after')
    def duration(self):
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:raise ValueError('Укажите часовой пояс')
        if not timedelta(minutes=15)<=self.end_at-self.start_at<=timedelta(hours=16):raise ValueError('Длительность смены 15 минут–16 часов')
        return self

class PulseCreate(BaseModel):
    slug:str='central'
    title:str=Field(min_length=4,max_length=90)
    question:str=Field(min_length=8,max_length=160)
    options:list[str]=Field(min_length=2,max_length=5)
    @model_validator(mode='after')
    def distinct_options(self):
        cleaned=[x.strip() for x in self.options]
        if any(not 2<=len(x)<=65 for x in cleaned) or len({x.casefold() for x in cleaned})!=len(cleaned):
            raise ValueError('От двух до пяти разных коротких ответов')
        self.options=cleaned
        return self

class PulseAnswer(BaseModel):
    request_id:str=Field(min_length=16,max_length=110)
    campaign_id:int=Field(gt=0)
    option_index:int=Field(ge=0,le=4)

class IncidentChange(BaseModel):
    status:Literal['acknowledged','resolved']
    note:str=Field(min_length=10,max_length=500)
    make_task:bool=False


def build_router(admin_dep,db_dep):
    router=APIRouter(tags=['R1.0: Retail Experience Operations'])

    @router.get('/api/admin/r10/benchmark')
    def comparison(days:int=14,source_mode:Literal['sensor','manual']='sensor',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        return benchmark(db,principal,days,source_mode)

    @router.get('/api/admin/r10/shifts')
    def shifts(slug:str='central',day:date|None=None,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        return shift_report(db,store,day or datetime.now(timezone.utc).astimezone(store_tz(store)).date())

    @router.post('/api/admin/r10/shifts',status_code=201)
    def add_shift(payload:ShiftNew,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,payload.slug,principal)
        if payload.user_id:
            u=db.execute('SELECT id,role,active FROM users WHERE id=? AND organization_id=?',(payload.user_id,principal.organization_id)).fetchone()
            if not u or not u['active']:raise HTTPException(404,'Сотрудник не найден')
            if u['role']!='owner' and not db.execute('SELECT 1 FROM user_store_access WHERE user_id=? AND store_id=?',(payload.user_id,store['id'])).fetchone():
                raise HTTPException(422,'Сотрудник не назначен на выбранный филиал')
        info={'store_id':store['id'],'user_id':payload.user_id,'label':payload.label.strip(),'cap':payload.capacity_per_hour,
              'start':payload.start_at.astimezone(timezone.utc).isoformat(),'end':payload.end_at.astimezone(timezone.utc).isoformat()}
        db.execute('BEGIN IMMEDIATE')
        try:
            old=db.execute('SELECT * FROM staff_shifts_r10 WHERE organization_id=? AND request_id=?',(principal.organization_id,payload.request_id)).fetchone()
            if old:
                if old['payload_sha']!=fingerprint(info):raise HTTPException(409,'Ключ уже используется для другой смены')
                db.commit();return {'id':old['id'],'duplicate':True}
            if payload.user_id:
                overlaps=db.execute('''SELECT id FROM staff_shifts_r10 WHERE user_id=? AND cancelled_at IS NULL
                  AND start_at<? AND end_at>?''',(payload.user_id,info['end'],info['start'])).fetchone()
                if overlaps:raise HTTPException(409,'У сотрудника уже есть смена в это время')
            cur=db.execute('''INSERT INTO staff_shifts_r10(organization_id,store_id,user_id,label,capacity_per_hour,start_at,end_at,request_id,payload_sha,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?)''',(principal.organization_id,store['id'],payload.user_id,info['label'],payload.capacity_per_hour,info['start'],info['end'],payload.request_id,fingerprint(info),now_iso()))
            audit(db,principal,'r10.shift.create',str(cur.lastrowid));db.commit()
            return {'id':cur.lastrowid,'duplicate':False}
        except Exception:db.rollback();raise

    @router.post('/api/admin/r10/shifts/{shift_id}/cancel')
    def cancel_shift(shift_id:int,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        row=db.execute('SELECT * FROM staff_shifts_r10 WHERE id=? AND organization_id=?',(shift_id,principal.organization_id)).fetchone()
        if not row:raise HTTPException(404,'Смена не найдена')
        check_store_access(db,row['store_id'],principal)
        if row['cancelled_at']:return {'cancelled':True,'duplicate':True}
        with db:
            db.execute('UPDATE staff_shifts_r10 SET cancelled_at=? WHERE id=?',(now_iso(),shift_id))
            audit(db,principal,'r10.shift.cancel',str(shift_id))
        return {'cancelled':True,'duplicate':False}

    @router.get('/api/admin/r10/service')
    def service(slug:str='central',days:int=14,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        return service_report(db,visible_store(db,slug,principal),days)

    @router.put('/api/admin/r10/service/targets')
    def set_sla(payload:ServiceTarget,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,payload.slug,principal)
        if payload.resolve_minutes<payload.accept_minutes:raise HTTPException(422,'Срок завершения не может быть меньше срока принятия')
        with db:
            db.execute('''INSERT INTO store_service_targets_r10(store_id,accept_minutes,resolve_minutes,updated_at)
              VALUES(?,?,?,?) ON CONFLICT(store_id) DO UPDATE SET accept_minutes=excluded.accept_minutes,
              resolve_minutes=excluded.resolve_minutes,updated_at=excluded.updated_at''',
              (store['id'],payload.accept_minutes,payload.resolve_minutes,now_iso()))
            audit(db,principal,'r10.sla.configure',payload.slug)
        return {'saved':True}

    @router.get('/api/admin/r10/pulse')
    def campaigns(slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        items=[]
        for row in db.execute('SELECT * FROM pulse_campaigns_r10 WHERE store_id=? ORDER BY id DESC LIMIT 100',(store['id'],)):
            counts=db.execute('SELECT option_index,COUNT(*) n FROM pulse_responses_r10 WHERE campaign_id=? GROUP BY option_index',(row['id'],)).fetchall()
            obj=dict(row);obj['options']=json.loads(obj.pop('options_json'))
            obj['counts']={str(r['option_index']):r['n'] for r in counts};obj['responses']=sum(r['n'] for r in counts)
            items.append(obj)
        configured=db.execute('SELECT enabled FROM kiosk_policies WHERE store_id=?',(store['id'],)).fetchone()
        return {'items':items,'paired_kiosk':bool(configured and configured['enabled']),
          'privacy':'Только выбор варианта ответа; имена, телефоны и видео не сохраняются.'}

    @router.post('/api/admin/r10/pulse',status_code=201)
    def create_campaign(payload:PulseCreate,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,payload.slug,principal)
        with db:
            cur=db.execute('''INSERT INTO pulse_campaigns_r10(organization_id,store_id,title,question,options_json,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?)''',(principal.organization_id,store['id'],payload.title,payload.question,
               canonical(payload.options),now_iso(),now_iso()))
            audit(db,principal,'r10.pulse.create',str(cur.lastrowid))
        return {'id':cur.lastrowid,'active':False}

    @router.post('/api/admin/r10/pulse/{campaign_id}/activate')
    def activate_campaign(campaign_id:int,slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,slug,principal)
        row=db.execute('SELECT id FROM pulse_campaigns_r10 WHERE id=? AND store_id=?',(campaign_id,store['id'])).fetchone()
        if not row:raise HTTPException(404,'Опрос не найден')
        policy=db.execute('SELECT enabled FROM kiosk_policies WHERE store_id=?',(store['id'],)).fetchone()
        if not policy or not policy['enabled']:raise HTTPException(409,'Сначала привяжите терминал в настройках магазина')
        with db:
            db.execute('UPDATE pulse_campaigns_r10 SET active=0,updated_at=? WHERE store_id=?',(now_iso(),store['id']))
            db.execute('UPDATE pulse_campaigns_r10 SET active=1,updated_at=? WHERE id=?',(now_iso(),campaign_id))
            audit(db,principal,'r10.pulse.activate',str(campaign_id))
        return {'active':True,'campaign_id':campaign_id}

    @router.post('/api/admin/r10/pulse/{campaign_id}/disable')
    def disable_campaign(campaign_id:int,slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,slug,principal)
        with db:
            cursor=db.execute('UPDATE pulse_campaigns_r10 SET active=0,updated_at=? WHERE id=? AND store_id=?',(now_iso(),campaign_id,store['id']))
            if cursor.rowcount!=1:raise HTTPException(404,'Опрос не найден')
            audit(db,principal,'r10.pulse.disable',str(campaign_id))
        return {'active':False}

    def public_access(db,slug,kiosk_token):
        row=db.execute('SELECT * FROM stores WHERE slug=?',(slug,)).fetchone()
        if not row:raise HTTPException(404,'Опрос недоступен')
        policy=db.execute('SELECT enabled FROM kiosk_policies WHERE store_id=?',(row['id'],)).fetchone()
        if not policy or not policy['enabled']:raise HTTPException(403,'Опрос доступен только на привязанном терминале')
        verify_kiosk(db,row['id'],kiosk_token)
        return row

    @router.get('/api/public/r10/pulse/{slug}')
    def public_campaign(slug:str,x_osmanx_kiosk:str|None=Header(default=None),db:sqlite3.Connection=Depends(db_dep)):
        store=public_access(db,slug,x_osmanx_kiosk)
        row=db.execute('SELECT id,question,options_json FROM pulse_campaigns_r10 WHERE store_id=? AND active=1',(store['id'],)).fetchone()
        if not row:raise HTTPException(404,'Опрос сейчас не проводится')
        return {'campaign_id':row['id'],'question':row['question'],'options':json.loads(row['options_json']),
                'store_name':store['name']}

    @router.post('/api/public/r10/pulse/{slug}',status_code=201)
    def answer_pulse(slug:str,payload:PulseAnswer,request:Request,x_osmanx_kiosk:str|None=Header(default=None),db:sqlite3.Connection=Depends(db_dep)):
        store=public_access(db,slug,x_osmanx_kiosk)
        db.execute('BEGIN IMMEDIATE')
        try:
            old=db.execute('SELECT * FROM pulse_responses_r10 WHERE store_id=? AND request_id=?',(store['id'],payload.request_id)).fetchone()
            if old:
                if old['campaign_id']!=payload.campaign_id or old['option_index']!=payload.option_index:raise HTTPException(409,'Ключ уже использован с другим ответом')
                db.commit();return {'saved':True,'duplicate':True}
            row=db.execute('SELECT * FROM pulse_campaigns_r10 WHERE id=? AND store_id=? AND active=1',(payload.campaign_id,store['id'])).fetchone()
            if not row:raise HTTPException(409,'Опрос уже завершён или заменён')
            options=json.loads(row['options_json'])
            if payload.option_index>=len(options):raise HTTPException(422,'Неизвестный вариант ответа')
            cutoff=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(timespec='seconds')
            recent=db.execute('SELECT COUNT(*) FROM pulse_responses_r10 WHERE store_id=? AND created_at>=?',(store['id'],cutoff)).fetchone()[0]
            if recent>=120:raise HTTPException(429,'Слишком много ответов, повторите позже')
            db.execute('INSERT INTO pulse_responses_r10(campaign_id,store_id,request_id,option_index,created_at) VALUES(?,?,?,?,?)',
                       (row['id'],store['id'],payload.request_id,payload.option_index,now_iso()))
            db.commit();return {'saved':True,'duplicate':False}
        except Exception:db.rollback();raise

    @router.get('/api/admin/r10/incidents')
    def incidents(slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        rows=[dict(x) for x in db.execute('SELECT * FROM incidents_r10 WHERE store_id=? ORDER BY id DESC LIMIT 150',(store['id'],))]
        return {'items':rows,'signals':[{'key':k,'kind':a,'title':b,'evidence':c,'severity':d} for k,a,b,c,d in incident_signals(db,store)]}

    @router.post('/api/admin/r10/incidents/scan')
    def scan_incidents(slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,slug,principal)
        signals=incident_signals(db,store);inserted=0
        with db:
            for key,kind,title,evidence,severity in signals:
                row=db.execute('''INSERT OR IGNORE INTO incidents_r10(organization_id,store_id,incident_key,kind,title,evidence,severity,status,created_at,updated_at)
                  VALUES(?,?,?,?,?,?,?,?,?,?)''',(principal.organization_id,store['id'],key,kind,title,evidence,severity,'new',now_iso(),now_iso()))
                inserted+=row.rowcount
            audit(db,principal,'r10.incident.scan',str(inserted))
        return {'detected':len(signals),'created':inserted}

    @router.patch('/api/admin/r10/incidents/{incident_id}')
    def update_incident(incident_id:int,payload:IncidentChange,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        db.execute('BEGIN IMMEDIATE')
        try:
            row=scoped_incident(db,incident_id,principal)
            if row['status']=='resolved':raise HTTPException(409,'Закрытый инцидент нельзя изменить')
            if row['status']=='new' and payload.status=='resolved':raise HTTPException(409,'Сначала подтвердите, что инцидент принят в работу')
            task_id=row['task_id']
            if payload.make_task and not task_id:
                cur=db.execute('''INSERT INTO action_tasks_r08(organization_id,store_id,request_id,title,category,status,evidence,created_at,updated_at)
                  VALUES(?,?,?,?,?,?,?,?,?)''',(principal.organization_id,row['store_id'],f'r10-incident-{incident_id}',
                  row['title'],'operations','open','',now_iso(),now_iso()))
                task_id=cur.lastrowid
            db.execute('UPDATE incidents_r10 SET status=?,note=?,task_id=?,updated_at=? WHERE id=?',
                       (payload.status,payload.note.strip(),task_id,now_iso(),incident_id))
            audit(db,principal,'r10.incident.'+payload.status,str(incident_id))
            db.commit();return {'id':incident_id,'status':payload.status,'task_id':task_id}
        except Exception:db.rollback();raise

    return router
