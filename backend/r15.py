"""R1.5 Pilot Studio: reproducible retailer pilots, with no invented profit claims.

Five workflows: pilot contracts, source attestations, daily metrics,
append-only interventions, immutable executive evidence snapshots.
No customer identities, biometric analysis, external POS actions or background jobs.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from backend.database import now_iso
from backend.retail import safe_spreadsheet_cell
from backend.security import Principal, audit, check_store_access, require_role, visible_store

DDL = """
CREATE TABLE IF NOT EXISTS pilots_r15 (
  id INTEGER PRIMARY KEY,
  organization_id INTEGER NOT NULL REFERENCES organizations(id),
  store_id INTEGER NOT NULL REFERENCES stores(id),
  request_id TEXT NOT NULL,
  spec_hash TEXT NOT NULL,
  title TEXT NOT NULL,
  hypothesis TEXT NOT NULL,
  metric TEXT NOT NULL CHECK(metric IN ('receipts_per_100_entries','revenue_per_entry_rub','feedback_per_100_entries','demand_per_100_entries')),
  source_mode TEXT NOT NULL CHECK(source_mode IN ('sensor','manual','all')),
  before_start TEXT NOT NULL, before_end TEXT NOT NULL,
  after_start TEXT NOT NULL, after_end TEXT NOT NULL,
  budget_kopeks INTEGER NOT NULL CHECK(budget_kopeks>=0),
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','running','completed','cancelled')),
  created_by INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
  started_at TEXT, completed_at TEXT,
  UNIQUE(organization_id, request_id)
);
CREATE INDEX IF NOT EXISTS idx_r15_pilots_store ON pilots_r15(store_id, created_at);
CREATE TABLE IF NOT EXISTS pilot_sources_r15 (
  id INTEGER PRIMARY KEY,
  pilot_id INTEGER NOT NULL REFERENCES pilots_r15(id) ON DELETE RESTRICT,
  category TEXT NOT NULL CHECK(category IN ('traffic','pos','feedback')),
  status TEXT NOT NULL CHECK(status IN ('checked','limited','unavailable')),
  note TEXT NOT NULL, checked_by INTEGER NOT NULL DEFAULT 0,
  checked_at TEXT NOT NULL,
  UNIQUE(pilot_id,category)
);
CREATE TABLE IF NOT EXISTS pilot_actions_r15 (
  id INTEGER PRIMARY KEY,
  pilot_id INTEGER NOT NULL REFERENCES pilots_r15(id) ON DELETE RESTRICT,
  request_id TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  category TEXT NOT NULL CHECK(category IN ('assortment','service','staffing','promotion','operations')),
  description TEXT NOT NULL,
  cost_kopeks INTEGER NOT NULL CHECK(cost_kopeks>=0),
  evidence TEXT NOT NULL DEFAULT '', created_by INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE(pilot_id,request_id)
);
CREATE INDEX IF NOT EXISTS idx_r15_actions ON pilot_actions_r15(pilot_id,created_at);
CREATE TABLE IF NOT EXISTS pilot_snapshots_r15 (
  id INTEGER PRIMARY KEY,
  pilot_id INTEGER NOT NULL UNIQUE REFERENCES pilots_r15(id),
  payload_json TEXT NOT NULL,
  payload_sha TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""

METRIC_LABELS = {
    'receipts_per_100_entries': 'Чеков на 100 входов',
    'revenue_per_entry_rub': 'Выручка по чекам на один вход, ₽',
    'feedback_per_100_entries': 'Ответов на 100 входов',
    'demand_per_100_entries': 'Запросов на 100 входов',
}


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(DDL)


def canonical(data: object) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def sha(value: object) -> str:
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def _timezone(store: sqlite3.Row):
    try:
        return ZoneInfo(store['timezone'] or 'UTC')
    except (KeyError, ZoneInfoNotFoundError):
        return timezone.utc


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def _day(value: str, tz) -> date | None:
    parsed = _parse_time(value)
    return parsed.astimezone(tz).date() if parsed else None


def _source_class(source: str) -> str:
    lower = (source or '').casefold()
    if 'demo' in lower:
        return 'demo'
    if any(key in lower for key in ('sensor', 'counter', 'device:', 'camera_count')):
        return 'sensor'
    if any(key in lower for key in ('manual', 'operator', 'staff', 'hand')):
        return 'manual'
    return 'unknown'


def _store_for_pilot(db, pilot: sqlite3.Row):
    row = db.execute('SELECT * FROM stores WHERE id=?', (pilot['store_id'],)).fetchone()
    if not row:
        raise HTTPException(409, 'Филиал для пилота больше не доступен')
    return row


def get_pilot(db, pilot_id: int, principal: Principal):
    row = db.execute('SELECT * FROM pilots_r15 WHERE id=? AND organization_id=?',
                     (pilot_id, principal.organization_id)).fetchone()
    if row is None:
        raise HTTPException(404, 'Пилот не найден')
    check_store_access(db, row['store_id'], principal)
    return row


def _window_dates(pilot):
    return ((date.fromisoformat(pilot['before_start']), date.fromisoformat(pilot['before_end'])),
            (date.fromisoformat(pilot['after_start']), date.fromisoformat(pilot['after_end'])))


def _traffic_allowed(source: str, mode: str):
    group = _source_class(source)
    return group == 'demo' or mode == 'all' or group == mode


def daily_observations(db: sqlite3.Connection, store: sqlite3.Row, pilot: sqlite3.Row) -> list[dict]:
    """Aggregate by store-local day; never try to follow an individual buyer across events."""
    tz = _timezone(store)
    before, after = _window_dates(pilot)
    start = min(before[0], after[0]); finish = max(before[1], after[1])
    lower = (datetime.combine(start-timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc)).isoformat()
    upper = (datetime.combine(finish+timedelta(days=3), datetime.min.time(), tzinfo=timezone.utc)).isoformat()
    data: dict[str, dict] = {}
    for offset in range((finish-start).days+1):
        day = (start+timedelta(days=offset)).isoformat()
        if before[0].isoformat() <= day <= before[1].isoformat(): phase='baseline'
        elif after[0].isoformat() <= day <= after[1].isoformat(): phase='intervention'
        else: continue
        data[day] = {'day':day,'phase':phase,'visits':0,'receipts':0,'revenue_kopeks':0,
                     'surveys':0,'demand_requests':0,'visit_sources':set(),'pos_sources':set(),
                     'demo_records':0,'unknown_sources':0}
    # Keep query sizes bounded: massive stores need a dedicated warehouse, not an ambiguous truncated total.
    for table,columns in [('visits','quantity,source,occurred_at'),
                          ('sales','amount_kopeks,source,occurred_at'),
                          ('surveys','created_at'),('demand','created_at')]:
        time_field='occurred_at' if table in ('visits','sales') else 'created_at'
        rows=db.execute(f'SELECT {columns} FROM {table} WHERE store_id=? AND {time_field}>=? AND {time_field}<? ORDER BY id LIMIT 100001',
                        (store['id'],lower,upper)).fetchall()
        if len(rows)>100000:
            raise HTTPException(413, f'Слишком много записей {table}: сократите период или используйте агрегатор')
        for item in rows:
            day = _day(item[time_field], tz)
            entry=data.get(day.isoformat()) if day else None
            if entry is None:continue
            if table=='visits':
                source=item['source'];group=_source_class(source)
                if group=='unknown':entry['unknown_sources']+=1
                if not _traffic_allowed(source,pilot['source_mode']):continue
                entry['visits']+=item['quantity'];entry['visit_sources'].add(source)
                if group=='demo':entry['demo_records']+=1
            elif table=='sales':
                entry['receipts']+=1;entry['revenue_kopeks']+=item['amount_kopeks']
                entry['pos_sources'].add(item['source'])
                if 'demo' in item['source'].casefold():entry['demo_records']+=1
            elif table=='surveys':entry['surveys']+=1
            else:entry['demand_requests']+=1
    result=[]
    for item in data.values():
        item['visit_sources']=sorted(item['visit_sources'])
        item['pos_sources']=sorted(item['pos_sources'])
        item['receipts_per_100_entries']=round(item['receipts']*100/item['visits'],2) if item['visits'] else None
        item['revenue_per_entry_rub']=round(item['revenue_kopeks']/100/item['visits'],2) if item['visits'] else None
        item['feedback_per_100_entries']=round(item['surveys']*100/item['visits'],2) if item['visits'] else None
        item['demand_per_100_entries']=round(item['demand_requests']*100/item['visits'],2) if item['visits'] else None
        result.append(item)
    return result


def phase_summary(days: list[dict], metric: str) -> dict:
    totals={k:sum(row[k] for row in days) for k in ('visits','receipts','revenue_kopeks','surveys','demand_requests','demo_records','unknown_sources')}
    totals['days']=len(days)
    totals['days_with_visits']=sum(row['visits']>0 for row in days)
    totals['visit_sources']=sorted({source for row in days for source in row['visit_sources']})
    totals['pos_sources']=sorted({source for row in days for source in row['pos_sources']})
    v=totals['visits']
    totals['metric_value']=(round(100*totals['receipts']/v,2) if metric=='receipts_per_100_entries' else
                            round(totals['revenue_kopeks']/100/v,2) if metric=='revenue_per_entry_rub' else
                            round(100*totals['surveys']/v,2) if metric=='feedback_per_100_entries' else
                            round(100*totals['demand_requests']/v,2)) if v else None
    return totals


def preview(db, principal: Principal, pilot: sqlite3.Row):
    store=_store_for_pilot(db,pilot)
    rows=daily_observations(db,store,pilot)
    before=phase_summary([x for x in rows if x['phase']=='baseline'],pilot['metric'])
    after=phase_summary([x for x in rows if x['phase']=='intervention'],pilot['metric'])
    attest=[dict(r) for r in db.execute('SELECT category,status,note,checked_at FROM pilot_sources_r15 WHERE pilot_id=? ORDER BY category',(pilot['id'],))]
    actions=[dict(r) for r in db.execute('SELECT id,category,description,cost_kopeks,evidence,created_at FROM pilot_actions_r15 WHERE pilot_id=? ORDER BY id',(pilot['id'],))]
    warnings=[]
    for phase,data in [('База',before),('Проверка',after)]:
        if data['visits']==0:warnings.append(f'{phase}: нет зарегистрированных входов, метрика не определена.')
        if data['visits']<50:warnings.append(f'{phase}: менее 50 входов; результат недостаточно устойчив.')
        if data['receipts']==0:warnings.append(f'{phase}: нет зарегистрированных чеков; нельзя подтвердить полноту данных кассы.')
        if data['days_with_visits']<data['days']:warnings.append(f'{phase}: отсутствуют входы хотя бы за один день.')
        if data['demo_records']:warnings.append(f'{phase}: присутствуют демонстрационные события.')
        if data['unknown_sources']:warnings.append(f'{phase}: часть источников трафика не классифицирована и может быть исключена фильтром.')
        if len(data['visit_sources'])>1:warnings.append(f'{phase}: несколько источников входов; возможен повторный учёт.')
        if data['receipts']>data['visits'] and data['visits']:warnings.append(f'{phase}: чеков больше входов; проверьте источник и методику.')
    for category in ('traffic','pos'):
        row=next((r for r in attest if r['category']==category),None)
        if row is None:warnings.append(f'Источник {category}: оператор ещё не подтвердил проверку.')
        elif row['status']!='checked':warnings.append(f'Источник {category}: отмечен как {row["status"]}.')
    if date.fromisoformat(pilot['after_end'])>=datetime.now(_timezone(store)).date():
        warnings.append('Период проверки ещё не завершён; окончательный вывод преждевременен.')
    metric_before=before['metric_value'];metric_after=after['metric_value']
    delta=(round(metric_after-metric_before,2) if metric_before is not None and metric_after is not None else None)
    enough_data=(before['visits']>=50 and after['visits']>=50 and before['receipts']>0 and after['receipts']>0
                 and before['demo_records']==0 and after['demo_records']==0
                 and before['days_with_visits']==before['days'] and after['days_with_visits']==after['days'])
    verified_sources=all(any(r['category']==c and r['status']=='checked' for r in attest) for c in ('traffic','pos'))
    finished=(date.fromisoformat(pilot['after_end'])<datetime.now(_timezone(store)).date())
    status='sufficient_to_review' if enough_data and verified_sources and finished else 'inconclusive'
    return {'pilot_id':pilot['id'],'metric':pilot['metric'],'metric_label':METRIC_LABELS[pilot['metric']],
            'baseline':before,'intervention':after,'delta':delta,'status':status,'source_attestations':attest,
            'actions':actions,'actual_logged_cost_kopeks':sum(x['cost_kopeks'] for x in actions),
            'planned_budget_kopeks':pilot['budget_kopeks'],'warnings':warnings,
            'methodology':'Сравнение двух равных временных окон. Чек ≠ уникальный покупатель. Сравнение не доказывает причинность, маржа не рассчитана.',
            'daily':rows,'calculated_at':now_iso()}


class CreatePilot(BaseModel):
    slug: str = Field(default='central',min_length=1,max_length=60)
    request_id: str = Field(min_length=12,max_length=100)
    title: str = Field(min_length=5,max_length=120)
    hypothesis: str = Field(min_length=15,max_length=500)
    metric: Literal['receipts_per_100_entries','revenue_per_entry_rub','feedback_per_100_entries','demand_per_100_entries']
    source_mode: Literal['sensor','manual','all'] = 'sensor'
    before_start: date
    before_end: date
    after_start: date
    after_end: date
    budget_kopeks: int = Field(default=0,ge=0,le=1000000000)

    @model_validator(mode='after')
    def check_windows(self):
        base=(self.before_end-self.before_start).days+1
        follow=(self.after_end-self.after_start).days+1
        if not 7<=base<=30 or follow!=base:raise ValueError('Два равных периода длительностью 7–30 дней')
        if self.before_end>=self.after_start:raise ValueError('Базовый период должен закончиться до проверки')
        if (self.after_start-self.before_end).days>14:raise ValueError('Между периодами допускается не более 13 пустых дней')
        if self.after_end>date.today()+timedelta(days=180):raise ValueError('Слишком далёкий горизонт пилота')
        return self


class Attestation(BaseModel):
    category: Literal['traffic','pos','feedback']
    status: Literal['checked','limited','unavailable']
    note: str = Field(min_length=8,max_length=500)


class Action(BaseModel):
    request_id: str = Field(min_length=12,max_length=100)
    category: Literal['assortment','service','staffing','promotion','operations']
    description: str = Field(min_length=12,max_length=500)
    cost_kopeks: int = Field(ge=0,le=1000000000)
    evidence: str = Field(default='',max_length=300)


class ClosePilot(BaseModel):
    decision: Literal['completed','cancelled']
    note: str = Field(min_length=12,max_length=500)


def build_router(admin, db_conn):
    router=APIRouter(prefix='/api/admin/r15',tags=['R1.5 Pilot Studio'])

    @router.get('/pilots')
    def pilots(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        return {'items':[dict(r) for r in db.execute('SELECT * FROM pilots_r15 WHERE store_id=? AND organization_id=? ORDER BY id DESC LIMIT 100',(store['id'],principal.organization_id))]}

    @router.post('/pilots',status_code=201)
    def create(data:CreatePilot,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        store=visible_store(db,data.slug,principal)
        spec=data.model_dump(mode='json');spec_hash=sha(spec)
        try:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT * FROM pilots_r15 WHERE organization_id=? AND request_id=?',(principal.organization_id,data.request_id)).fetchone()
            if existing:
                if existing['spec_hash']!=spec_hash:raise HTTPException(409,'Повторный ключ с другими параметрами')
                db.rollback();return {'id':existing['id'],'duplicate':True}
            cur=db.execute('''INSERT INTO pilots_r15(organization_id,store_id,request_id,spec_hash,title,hypothesis,metric,source_mode,
                before_start,before_end,after_start,after_end,budget_kopeks,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(principal.organization_id,store['id'],data.request_id,spec_hash,data.title.strip(),
                data.hypothesis.strip(),data.metric,data.source_mode,*[str(v) for v in (data.before_start,data.before_end,data.after_start,data.after_end)],
                data.budget_kopeks,principal.user_id,now_iso()))
            audit(db,principal,'r15.pilot.create',str(cur.lastrowid))
            db.commit();return {'id':cur.lastrowid,'duplicate':False}
        except Exception:db.rollback();raise

    @router.get('/pilots/{pilot_id}')
    def detail(pilot_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        row=get_pilot(db,pilot_id,principal)
        return {'pilot':dict(row),'attestations':[dict(x) for x in db.execute('SELECT category,status,note,checked_at FROM pilot_sources_r15 WHERE pilot_id=?',(pilot_id,))],
                'actions':[dict(x) for x in db.execute('SELECT * FROM pilot_actions_r15 WHERE pilot_id=? ORDER BY id',(pilot_id,))]}

    @router.post('/pilots/{pilot_id}/start')
    def start(pilot_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        db.execute('BEGIN IMMEDIATE')
        p=get_pilot(db,pilot_id,principal)
        if p['status']!='draft':raise HTTPException(409,'Запустить можно только черновик')
        db.execute("UPDATE pilots_r15 SET status='running',started_at=? WHERE id=? AND status='draft'",(now_iso(),pilot_id))
        audit(db,principal,'r15.pilot.start',str(pilot_id));db.commit()
        return {'id':pilot_id,'status':'running'}

    @router.post('/pilots/{pilot_id}/sources')
    def attest(pilot_id:int,data:Attestation,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        db.execute('BEGIN IMMEDIATE')
        p=get_pilot(db,pilot_id,principal)
        if p['status'] in ('completed','cancelled'):raise HTTPException(409,'Пилот закрыт')
        db.execute('''INSERT INTO pilot_sources_r15(pilot_id,category,status,note,checked_by,checked_at) VALUES(?,?,?,?,?,?)
            ON CONFLICT(pilot_id,category) DO UPDATE SET status=excluded.status,note=excluded.note,checked_by=excluded.checked_by,checked_at=excluded.checked_at''',
            (pilot_id,data.category,data.status,data.note.strip(),principal.user_id,now_iso()))
        audit(db,principal,'r15.source.attest',f'{pilot_id}/{data.category}');db.commit()
        return {'saved':True,'note':'Самопроверка источника не равна независимому аудиту.'}

    @router.post('/pilots/{pilot_id}/actions',status_code=201)
    def action(pilot_id:int,data:Action,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        fingerprint=sha(data.model_dump(mode='json'))
        try:
            db.execute('BEGIN IMMEDIATE')
            p=get_pilot(db,pilot_id,principal)
            if p['status']!='running':raise HTTPException(409,'Добавлять действия можно только в запущенный пилот')
            old=db.execute('SELECT id,fingerprint FROM pilot_actions_r15 WHERE pilot_id=? AND request_id=?',(pilot_id,data.request_id)).fetchone()
            if old:
                if old['fingerprint']!=fingerprint:raise HTTPException(409,'Ключ действия уже использован с другими данными')
                db.rollback();return {'id':old['id'],'duplicate':True}
            cur=db.execute('''INSERT INTO pilot_actions_r15(pilot_id,request_id,fingerprint,category,description,cost_kopeks,evidence,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)''',(pilot_id,data.request_id,fingerprint,data.category,data.description.strip(),data.cost_kopeks,
                data.evidence.strip(),principal.user_id,now_iso()))
            audit(db,principal,'r15.action.add',str(cur.lastrowid));db.commit()
            return {'id':cur.lastrowid,'duplicate':False}
        except Exception:db.rollback();raise

    @router.get('/pilots/{pilot_id}/daily')
    def daily(pilot_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        p=get_pilot(db,pilot_id,principal);return {'items':daily_observations(db,_store_for_pilot(db,p),p)}

    @router.get('/pilots/{pilot_id}/preview')
    def preview_pilot(pilot_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        p=get_pilot(db,pilot_id,principal)
        return preview(db,principal,p)

    @router.post('/pilots/{pilot_id}/close')
    def close(pilot_id:int,data:ClosePilot,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        db.execute('BEGIN IMMEDIATE')
        p=get_pilot(db,pilot_id,principal)
        if p['status']!='running':raise HTTPException(409,'Завершить можно только работающий пилот')
        store=_store_for_pilot(db,p)
        if data.decision=='completed':
            if date.fromisoformat(p['after_end'])>=datetime.now(_timezone(store)).date():
                raise HTTPException(409,'Период ещё не завершён; итог сейчас преждевременен')
            if not db.execute('SELECT 1 FROM pilot_actions_r15 WHERE pilot_id=?',(pilot_id,)).fetchone():
                raise HTTPException(409,'Для отчёта требуется минимум одно задокументированное действие')
        result=preview(db,principal,p)
        frozen={'store':store['slug'],'pilot':dict(p),'result':result,'decision':data.decision,'decision_note':data.note.strip(),
                'frozen_at':now_iso(),'disclaimer':'Наблюдаемые изменения не доказывают причинную связь и не являются расчётом чистой прибыли.'}
        payload=canonical(frozen);digest=hashlib.sha256(payload.encode('utf-8')).hexdigest()
        try:
            old=db.execute('SELECT status FROM pilots_r15 WHERE id=?',(pilot_id,)).fetchone()
            if not old or old['status']!='running':raise HTTPException(409,'Статус пилота изменился')
            cur=db.execute('INSERT INTO pilot_snapshots_r15(pilot_id,payload_json,payload_sha,created_at) VALUES(?,?,?,?)',
                           (pilot_id,payload,digest,now_iso()))
            db.execute('UPDATE pilots_r15 SET status=?,completed_at=? WHERE id=?',(data.decision,now_iso(),pilot_id))
            audit(db,principal,'r15.pilot.close',str(pilot_id));db.commit()
            return {'id':pilot_id,'status':data.decision,'snapshot_id':cur.lastrowid,'sha256':digest}
        except Exception:db.rollback();raise

    @router.get('/pilots/{pilot_id}/snapshot')
    def snapshot(pilot_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        get_pilot(db,pilot_id,principal)
        item=db.execute('SELECT * FROM pilot_snapshots_r15 WHERE pilot_id=?',(pilot_id,)).fetchone()
        if not item:raise HTTPException(404,'Закрытый отчёт ещё не создан')
        if hashlib.sha256(item['payload_json'].encode('utf-8')).hexdigest()!=item['payload_sha']:
            raise HTTPException(409,'Контрольная сумма снимка нарушена')
        return {'sha256':item['payload_sha'],'payload':json.loads(item['payload_json']),'created_at':item['created_at']}

    @router.get('/pilots/{pilot_id}/snapshot.csv')
    def snapshot_csv(pilot_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        record=snapshot(pilot_id,principal,db)
        payload=record['payload'];result=payload['result']
        output=io.StringIO();writer=csv.writer(output)
        writer.writerow(['Этап','Входы','Чеки','Выручка_коп','Ответы','Запросы','Метрика','Источник'])
        for key,label in [('baseline','База'),('intervention','Проверка')]:
            period=result[key]
            writer.writerow([safe_spreadsheet_cell(label),period['visits'],period['receipts'],period['revenue_kopeks'],
                             period['surveys'],period['demand_requests'],period['metric_value'],
                             safe_spreadsheet_cell(','.join(period['visit_sources']))])
        writer.writerow(['SHA-256',safe_spreadsheet_cell(record['sha256'])])
        writer.writerow(['Методика',safe_spreadsheet_cell(result['methodology'])])
        for warning in result['warnings']:writer.writerow(['Ограничение',safe_spreadsheet_cell(warning)])
        return Response('\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition':'attachment; filename="osmanx-pilot-evidence.csv"','Cache-Control':'no-store'})

    return router
