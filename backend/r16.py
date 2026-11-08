"""R1.6 Pilot Command: portfolio, integrity diagnostics, economics scenarios,
independently reviewed rollout proposals, and auditable follow-up tasks.

Read-only metrics do not imply causal lift; no automated POS/ERP actions.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.database import now_iso
from backend.r15 import get_pilot, preview as pilot_preview, daily_observations, _store_for_pilot, _timezone
from backend.retail import safe_spreadsheet_cell
from backend.security import Principal, audit, check_store_access, require_role, visible_store

DDL = """
CREATE TABLE IF NOT EXISTS pilot_scenarios_r16 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 pilot_id INTEGER NOT NULL REFERENCES pilots_r15(id),
 request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
 ticket_kopeks INTEGER NOT NULL CHECK(ticket_kopeks > 0),
 gross_margin_bps INTEGER NOT NULL CHECK(gross_margin_bps BETWEEN 1 AND 9999),
 note TEXT NOT NULL, assumptions_json TEXT NOT NULL,
 result_json TEXT NOT NULL, created_by INTEGER NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(organization_id, request_id)
);
CREATE INDEX IF NOT EXISTS ix_r16_scenario_pilot ON pilot_scenarios_r16(pilot_id,id);
CREATE TABLE IF NOT EXISTS pilot_rollouts_r16 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 pilot_id INTEGER NOT NULL UNIQUE REFERENCES pilots_r15(id),
 request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
 snapshot_sha TEXT NOT NULL, proposal TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('pending','approved','rejected')),
 submitted_by INTEGER NOT NULL, submitted_at TEXT NOT NULL,
 reviewer_id INTEGER, reviewed_at TEXT, decision_note TEXT NOT NULL DEFAULT '',
 UNIQUE(organization_id,request_id)
);
CREATE INDEX IF NOT EXISTS ix_r16_rollouts_state ON pilot_rollouts_r16(organization_id,state);
CREATE TABLE IF NOT EXISTS pilot_followups_r16 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 pilot_id INTEGER NOT NULL REFERENCES pilots_r15(id),
 request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
 title TEXT NOT NULL, owner TEXT NOT NULL, due_date TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('open','working','done','cancelled')),
 evidence TEXT NOT NULL DEFAULT '', created_by INTEGER NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(organization_id,request_id)
);
CREATE INDEX IF NOT EXISTS ix_r16_followups_pilot ON pilot_followups_r16(pilot_id,status,due_date);
CREATE TABLE IF NOT EXISTS pilot_followup_history_r16 (
 id INTEGER PRIMARY KEY,
 followup_id INTEGER NOT NULL REFERENCES pilot_followups_r16(id),
 prior_state TEXT NOT NULL, next_state TEXT NOT NULL,
 note TEXT NOT NULL, changed_by INTEGER NOT NULL, changed_at TEXT NOT NULL
);
"""


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(DDL)


def canonical(obj) -> str:
    return json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':'))


def fingerprint(obj) -> str:
    return hashlib.sha256(canonical(obj).encode('utf-8')).hexdigest()


def visible_pilot(db, pilot_id: int, principal: Principal):
    return get_pilot(db,pilot_id,principal)


def _scoped(db,table:str,item_id:int,principal:Principal):
    if table not in ('pilot_scenarios_r16','pilot_rollouts_r16','pilot_followups_r16'):
        raise ValueError('Unsupported table')
    row=db.execute(f'SELECT * FROM {table} WHERE id=? AND organization_id=?',(item_id,principal.organization_id)).fetchone()
    if row is None:raise HTTPException(404,'Запись не найдена')
    visible_pilot(db,row['pilot_id'],principal)
    return row


def quality_report(db,p,principal):
    """Strict observation audit: red flags never silently become zeros or verified sales."""
    s=_store_for_pilot(db,p)
    days=daily_observations(db,s,p)
    result=pilot_preview(db,principal,p)
    checks=[]
    for phase,key in (('База','baseline'),('Проверка','intervention')):
        summary=result[key];subset=[x for x in days if x['phase']==key]
        missing=[x['day'] for x in subset if x['visits']==0]
        sources=summary['visit_sources']
        if missing:checks.append({'severity':'block','code':key+'_gaps','title':f'{phase}: дни без входов','detail':', '.join(missing[:10])})
        if summary['visits']<50:checks.append({'severity':'block','code':key+'_small','title':f'{phase}: менее 50 входов','detail':str(summary['visits'])})
        if summary['receipts']==0:checks.append({'severity':'block','code':key+'_no_pos','title':f'{phase}: нет чеков','detail':'Нет возможности подтвердить продажи.'})
        if summary['demo_records']:checks.append({'severity':'block','code':key+'_demo','title':f'{phase}: демонстрационные события','detail':str(summary['demo_records'])})
        if len(sources)>1:checks.append({'severity':'block','code':key+'_mixed','title':f'{phase}: несколько источников входов','detail':', '.join(sources)})
        if summary['receipts']>summary['visits'] and summary['visits']:
            checks.append({'severity':'block','code':key+'_more_receipts','title':f'{phase}: чеков больше входов','detail':'Нужна проверка методики.'})
        if summary['unknown_sources']:
            checks.append({'severity':'warning','code':key+'_unknown','title':f'{phase}: источники не классифицированы','detail':str(summary['unknown_sources'])})
    for cat in ('traffic','pos'):
        row=next((x for x in result['source_attestations'] if x['category']==cat),None)
        if not row or row['status']!='checked':
            checks.append({'severity':'block','code':'attestation_'+cat,'title':'Источник '+cat+' не подтверждён','detail':'Операторская самопроверка обязательна для допуска к рассмотрению.'})
    today=datetime.now(_timezone(s)).date()
    if date.fromisoformat(p['after_end'])>=today:
        checks.append({'severity':'block','code':'unfinished','title':'Период ещё не окончен','detail':'Подведение итогов до завершения окна преждевременно.'})
    if result['baseline']['visit_sources']!=result['intervention']['visit_sources']:
        checks.append({'severity':'block','code':'source_changed','title':'Состав источников трафика изменился','detail':'Проверьте сопоставимость методики.'})
    if p['status'] in ('completed','cancelled'):
        rec=db.execute('SELECT payload_json,payload_sha FROM pilot_snapshots_r15 WHERE pilot_id=?',(p['id'],)).fetchone()
        if not rec or hashlib.sha256(rec['payload_json'].encode()).hexdigest()!=rec['payload_sha']:
            checks.append({'severity':'block','code':'snapshot_invalid','title':'Итоговый снимок отсутствует или повреждён','detail':'Недопустимо принимать решение.'})
        else:
            try:
                frozen=json.loads(rec['payload_json'])['result']
                fields=('visits','receipts','revenue_kopeks','surveys','demand_requests')
                changed=any(frozen[period][field]!=result[period][field]
                            for period in ('baseline','intervention') for field in fields)
                if changed:
                    checks.append({'severity':'block','code':'snapshot_data_drift',
                                   'title':'Данные изменились после фиксации итога',
                                   'detail':'Сверьте новые события и подготовьте отдельную версию отчёта, старый снимок не переписывайте.'})
            except (KeyError,TypeError,ValueError):
                checks.append({'severity':'block','code':'snapshot_format','title':'Неверная структура снимка',
                               'detail':'Результат нельзя независимо проверить.'})
    blocking=sum(x['severity']=='block' for x in checks)
    return {'pilot_id':p['id'],'status':'reviewable' if not blocking else 'needs_attention','blocking':blocking,
            'warnings':len(checks)-blocking,'checks':checks,'pilot_status':p['status'],
            'baseline':result['baseline'],'intervention':result['intervention'],
            'delta':result['delta'],'metric':p['metric'],
            'disclaimer':'Самопроверка источников и полнота записей не доказывают причинный эффект, прибыль или оплату чека.'}


def portfolio(db,principal:Principal):
    # SQL restricts both org and branch visibility before business computations.
    candidates=db.execute('''SELECT p.*,s.slug,s.name AS store_name FROM pilots_r15 p JOIN stores s ON s.id=p.store_id
      WHERE p.organization_id=? ORDER BY p.id DESC LIMIT 101''',(principal.organization_id,)).fetchall()
    if len(candidates)>100:raise HTTPException(413,'Слишком много пилотов; используйте архивирование или постраничную выборку')
    visible=[]
    for p in candidates:
        try:check_store_access(db,p['store_id'],principal)
        except HTTPException:continue
        q=quality_report(db,p,principal)
        visible.append({'id':p['id'],'title':p['title'],'store':p['store_name'],'slug':p['slug'],
                        'status':p['status'],'metric':p['metric'],'delta':q['delta'],
                        'quality':q['status'],'blocking':q['blocking'],
                        'action_count':db.execute('SELECT COUNT(*) FROM pilot_actions_r15 WHERE pilot_id=?',(p['id'],)).fetchone()[0],
                        'followups_open':db.execute("SELECT COUNT(*) FROM pilot_followups_r16 WHERE pilot_id=? AND status IN ('open','working')",(p['id'],)).fetchone()[0],
                        'budget_kopeks':p['budget_kopeks']})
    return {'items':visible,'total':len(visible),'methodology':'Только доступные филиалы. Дельта описательная; не измеряет причинный эффект.'}


class ScenarioIn(BaseModel):
    request_id: str = Field(min_length=12,max_length=100)
    ticket_kopeks: int = Field(gt=0,le=1000000000)
    gross_margin_bps: int = Field(ge=1,le=9999)
    note: str = Field(min_length=12,max_length=300)


def scenario_analysis(db,p,principal:Principal,data:ScenarioIn):
    if p['metric']!='receipts_per_100_entries':
        raise HTTPException(422,'Сценарий требует KPI «чеки на 100 входов», а не показатели опросов или выручки.')
    result=pilot_preview(db,principal,p)
    before,after=result['baseline'],result['intervention']
    # An assumption-based scenario only. Assumed basket and margin are NOT confirmed by a POS.
    delta=result['delta']; visits=after['visits']
    projected=(Decimal(str(delta))*Decimal(visits)/Decimal(100)) if delta is not None else None
    gross=int((max(Decimal(0),projected)*Decimal(data.ticket_kopeks)*Decimal(data.gross_margin_bps)/Decimal(10000)).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) if projected is not None else None
    costs=result['actual_logged_cost_kopeks']
    report={'observed_delta_receipts_per_100_entries':delta,'intervention_entries':visits,
            'assumed_ticket_kopeks':data.ticket_kopeks,'assumed_gross_margin_bps':data.gross_margin_bps,
            'scenario_incremental_receipts':float(max(Decimal(0),projected)) if projected is not None else None,
            'scenario_gross_contribution_kopeks':gross,
            'logged_actions_cost_kopeks':costs,
            'scenario_net_after_logged_costs_kopeks':gross-costs if gross is not None else None,
            'basis_status':result['status'],'quality_warning_count':len(result['warnings']),
            'disclaimer':'Расчёт условный: чек и маржа заданы вручную, разница периодов не означает причинный эффект. Не является подтверждённой прибылью.'}
    return report


class RolloutIn(BaseModel):
    request_id: str = Field(min_length=12,max_length=100)
    proposal: str = Field(min_length=20,max_length=700)


class ReviewIn(BaseModel):
    decision: Literal['approved','rejected']
    note: str = Field(min_length=16,max_length=600)


class FollowUpIn(BaseModel):
    request_id: str = Field(min_length=12,max_length=100)
    title: str = Field(min_length=12,max_length=180)
    owner: str = Field(min_length=3,max_length=100)
    due_date: date


class FollowUpUpdate(BaseModel):
    status: Literal['working','done','cancelled']
    note: str = Field(min_length=8,max_length=500)


def _json_csv(rows):
    out=io.StringIO();writer=csv.writer(out)
    writer.writerow(['Пилот','Филиал','Статус','Качество','Блокирующие_проблемы','Изменение_метрики','Действия','Открытые_задачи'])
    for p in rows:
        writer.writerow([safe_spreadsheet_cell(str(p[k])) for k in ('title','store','status','quality','blocking','delta','action_count','followups_open')])
    return '\ufeff'+out.getvalue()


def build_router(admin,db_conn):
    router=APIRouter(prefix='/api/admin/r16',tags=['R1.6 Pilot Command'])

    @router.get('/portfolio')
    def portfolio_get(principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        return portfolio(db,principal)

    @router.get('/portfolio.csv')
    def portfolio_csv(principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        content=_json_csv(portfolio(db,principal)['items'])
        return Response(content,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="osmanx-pilot-portfolio.csv"','Cache-Control':'no-store'})

    @router.get('/pilots/{pilot_id}/quality')
    def quality_get(pilot_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        return quality_report(db,visible_pilot(db,pilot_id,principal),principal)

    @router.get('/pilots/{pilot_id}/scenarios')
    def scenarios_get(pilot_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        visible_pilot(db,pilot_id,principal)
        return {'items':[{'id':r['id'],'assumptions':json.loads(r['assumptions_json']),
                 'result':json.loads(r['result_json']),'created_at':r['created_at']} for r in db.execute(
                'SELECT * FROM pilot_scenarios_r16 WHERE pilot_id=? ORDER BY id DESC LIMIT 100',(pilot_id,))]}

    @router.post('/pilots/{pilot_id}/scenarios',status_code=201)
    def scenario_create(pilot_id:int,data:ScenarioIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        spec=data.model_dump(mode='json');digest=fingerprint({'pilot_id':pilot_id,**spec})
        try:
            db.execute('BEGIN IMMEDIATE')
            p=visible_pilot(db,pilot_id,principal)
            existing=db.execute('SELECT * FROM pilot_scenarios_r16 WHERE organization_id=? AND request_id=?',(principal.organization_id,data.request_id)).fetchone()
            if existing:
                if existing['fingerprint']!=digest:raise HTTPException(409,'Ключ повторно использован с другими допущениями')
                db.rollback();return {'id':existing['id'],'duplicate':True,'result':json.loads(existing['result_json'])}
            result=scenario_analysis(db,p,principal,data)
            cur=db.execute('''INSERT INTO pilot_scenarios_r16(organization_id,pilot_id,request_id,fingerprint,ticket_kopeks,gross_margin_bps,
               note,assumptions_json,result_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
               (principal.organization_id,pilot_id,data.request_id,digest,data.ticket_kopeks,data.gross_margin_bps,
                data.note.strip(),canonical(spec),canonical(result),principal.user_id,now_iso()))
            audit(db,principal,'r16.scenario.create',str(cur.lastrowid));db.commit()
            return {'id':cur.lastrowid,'duplicate':False,'result':result}
        except Exception:db.rollback();raise

    @router.get('/pilots/{pilot_id}/rollout')
    def rollout_get(pilot_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        visible_pilot(db,pilot_id,principal)
        row=db.execute('SELECT * FROM pilot_rollouts_r16 WHERE pilot_id=?',(pilot_id,)).fetchone()
        return {'item':dict(row) if row else None}

    @router.post('/pilots/{pilot_id}/rollout',status_code=201)
    def rollout_submit(pilot_id:int,data:RolloutIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        digest=fingerprint({'pilot_id':pilot_id,**data.model_dump()})
        try:
            db.execute('BEGIN IMMEDIATE')
            p=visible_pilot(db,pilot_id,principal)
            old=db.execute('SELECT * FROM pilot_rollouts_r16 WHERE pilot_id=?',(pilot_id,)).fetchone()
            if old:
                if old['request_id']!=data.request_id or old['fingerprint']!=digest:
                    raise HTTPException(409,'Для этого пилота уже есть другой план развёртывания')
                db.rollback();return {'id':old['id'],'duplicate':True,'state':old['state']}
            if p['status']!='completed':raise HTTPException(409,'Рассмотрение доступно только после зафиксированного завершения пилота')
            snap=db.execute('SELECT * FROM pilot_snapshots_r15 WHERE pilot_id=?',(pilot_id,)).fetchone()
            if not snap or hashlib.sha256(snap['payload_json'].encode()).hexdigest()!=snap['payload_sha']:
                raise HTTPException(409,'Снимок результата отсутствует или повреждён')
            cur=db.execute('''INSERT INTO pilot_rollouts_r16(organization_id,pilot_id,request_id,fingerprint,snapshot_sha,
                proposal,state,submitted_by,submitted_at) VALUES(?,?,?,?,?,?,?,?,?)''',
                (principal.organization_id,pilot_id,data.request_id,digest,snap['payload_sha'],data.proposal.strip(),
                 'pending',principal.user_id,now_iso()))
            audit(db,principal,'r16.rollout.submit',str(cur.lastrowid));db.commit()
            return {'id':cur.lastrowid,'duplicate':False,'state':'pending'}
        except Exception:db.rollback();raise

    @router.post('/rollouts/{rollout_id}/review')
    def rollout_review(rollout_id:int,data:ReviewIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner')
        try:
            db.execute('BEGIN IMMEDIATE')
            row=_scoped(db,'pilot_rollouts_r16',rollout_id,principal)
            if row['state']!='pending':raise HTTPException(409,'Решение уже зафиксировано')
            if row['submitted_by']==principal.user_id:raise HTTPException(409,'Требуется независимый проверяющий, отличный от автора')
            p=visible_pilot(db,row['pilot_id'],principal)
            snapshot=db.execute('SELECT payload_sha,payload_json FROM pilot_snapshots_r15 WHERE pilot_id=?',(p['id'],)).fetchone()
            if not snapshot or snapshot['payload_sha']!=row['snapshot_sha'] or hashlib.sha256(snapshot['payload_json'].encode()).hexdigest()!=row['snapshot_sha']:
                raise HTTPException(409,'Исходный отчёт изменился или повреждён')
            if data.decision=='approved' and quality_report(db,p,principal)['blocking']>0:
                raise HTTPException(409,'Нельзя одобрить внедрение при блокирующих проблемах качества данных')
            db.execute('UPDATE pilot_rollouts_r16 SET state=?,reviewer_id=?,reviewed_at=?,decision_note=? WHERE id=?',
                       (data.decision,principal.user_id,now_iso(),data.note.strip(),rollout_id))
            audit(db,principal,'r16.rollout.review',f'{rollout_id}:{data.decision}');db.commit()
            return {'id':rollout_id,'state':data.decision,'note':'Одобрение не запускает POS, закупку или публикацию автоматически.'}
        except Exception:db.rollback();raise

    @router.get('/pilots/{pilot_id}/followups')
    def followups(pilot_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        visible_pilot(db,pilot_id,principal)
        return {'items':[dict(x) for x in db.execute('SELECT * FROM pilot_followups_r16 WHERE pilot_id=? ORDER BY due_date,id LIMIT 200',(pilot_id,))]}

    @router.post('/pilots/{pilot_id}/followups',status_code=201)
    def create_followup(pilot_id:int,data:FollowUpIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        if data.due_date<date.today()-timedelta(days=1) or data.due_date>date.today()+timedelta(days=366):
            raise HTTPException(422,'Срок задачи должен быть от вчера до года вперёд')
        digest=fingerprint({'pilot_id':pilot_id,**data.model_dump(mode='json')})
        try:
            db.execute('BEGIN IMMEDIATE')
            p=visible_pilot(db,pilot_id,principal)
            old=db.execute('SELECT * FROM pilot_followups_r16 WHERE organization_id=? AND request_id=?',(principal.organization_id,data.request_id)).fetchone()
            if old:
                if old['fingerprint']!=digest:raise HTTPException(409,'Ключ задачи повторно использован с другими параметрами')
                db.rollback();return {'id':old['id'],'duplicate':True}
            cur=db.execute('''INSERT INTO pilot_followups_r16(organization_id,pilot_id,request_id,fingerprint,title,owner,due_date,
              status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
              (principal.organization_id,pilot_id,data.request_id,digest,data.title.strip(),data.owner.strip(),
               str(data.due_date),'open',principal.user_id,now_iso(),now_iso()))
            audit(db,principal,'r16.followup.create',str(cur.lastrowid));db.commit()
            return {'id':cur.lastrowid,'duplicate':False}
        except Exception:db.rollback();raise

    @router.patch('/followups/{task_id}')
    def followup_update(task_id:int,data:FollowUpUpdate,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            db.execute('BEGIN IMMEDIATE')
            row=_scoped(db,'pilot_followups_r16',task_id,principal)
            next_allowed={'open':('working','cancelled'),'working':('done','cancelled'),
                          'done':(),'cancelled':()}
            if data.status not in next_allowed[row['status']]:raise HTTPException(409,'Недопустимое изменение статуса задачи')
            db.execute('UPDATE pilot_followups_r16 SET status=?,evidence=?,updated_at=? WHERE id=?',
                       (data.status,data.note.strip(),now_iso(),task_id))
            db.execute('INSERT INTO pilot_followup_history_r16(followup_id,prior_state,next_state,note,changed_by,changed_at) VALUES(?,?,?,?,?,?)',
                       (task_id,row['status'],data.status,data.note.strip(),principal.user_id,now_iso()))
            audit(db,principal,'r16.followup.update',f'{task_id}:{data.status}');db.commit()
            return {'id':task_id,'status':data.status}
        except Exception:db.rollback();raise

    @router.get('/followups/{task_id}/history')
    def followup_history(task_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        _scoped(db,'pilot_followups_r16',task_id,principal)
        return {'items':[dict(x) for x in db.execute('SELECT prior_state,next_state,note,changed_at FROM pilot_followup_history_r16 WHERE followup_id=? ORDER BY id',(task_id,))]}

    return router
