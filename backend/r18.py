"""R1.8 Decision Bridge: aggregated Voice evidence -> hypothesis -> scoped pilot -> actions.

No identity inference, automated POS mutation, causal claims, or automatic deployment.
All evidence is aggregate and pinned to an immutable published survey version.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.database import now_iso
from backend.retail import safe_spreadsheet_cell
from backend.security import Principal, audit, check_store_access, require_role, visible_store
from backend.r15 import CreatePilot, sha as r15_sha

DDL = """
CREATE TABLE IF NOT EXISTS bridge_hypotheses_r18 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 request_id TEXT NOT NULL,
 request_hash TEXT NOT NULL,
 placement_id INTEGER NOT NULL REFERENCES voice_placements_r17(id),
 version_id INTEGER NOT NULL REFERENCES voice_versions_r17(id),
 question_id TEXT NOT NULL,
 choice_code TEXT NOT NULL,
 title TEXT NOT NULL,
 category TEXT NOT NULL CHECK(category IN ('assortment','service','stock','price','experience')),
 evidence_json TEXT NOT NULL,
 evidence_sha TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'candidate' CHECK(status IN ('candidate','investigating','pilot_linked','resolved','dismissed')),
 pilot_id INTEGER UNIQUE REFERENCES pilots_r15(id),
 pilot_request_hash TEXT,
 created_by INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(organization_id,request_id)
);
CREATE INDEX IF NOT EXISTS bridge_hyp_store ON bridge_hypotheses_r18(store_id,status,created_at);
CREATE TABLE IF NOT EXISTS bridge_history_r18 (
 id INTEGER PRIMARY KEY,
 hypothesis_id INTEGER NOT NULL REFERENCES bridge_hypotheses_r18(id),
 event TEXT NOT NULL, previous_status TEXT NOT NULL,
 next_status TEXT NOT NULL, note TEXT NOT NULL,
 actor_id INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS bridge_history_hyp ON bridge_history_r18(hypothesis_id,id);
CREATE TABLE IF NOT EXISTS bridge_tasks_r18 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 hypothesis_id INTEGER NOT NULL REFERENCES bridge_hypotheses_r18(id),
 request_id TEXT NOT NULL,
 request_hash TEXT NOT NULL,
 title TEXT NOT NULL, owner TEXT NOT NULL, due_date TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','working','done','cancelled')),
 evidence_note TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(organization_id,request_id)
);
CREATE INDEX IF NOT EXISTS bridge_tasks_hyp ON bridge_tasks_r18(hypothesis_id,status,id);
CREATE TABLE IF NOT EXISTS bridge_task_history_r18 (
 id INTEGER PRIMARY KEY,
 task_id INTEGER NOT NULL REFERENCES bridge_tasks_r18(id),
 previous_status TEXT NOT NULL, next_status TEXT NOT NULL,
 note TEXT NOT NULL, actor_id INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL
);
"""


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(DDL)


def canonical(value) -> str:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def _scope(db: sqlite3.Connection, hid: int, principal: Principal):
    row=db.execute('SELECT * FROM bridge_hypotheses_r18 WHERE id=? AND organization_id=?',
                   (hid,principal.organization_id)).fetchone()
    if row is None:raise HTTPException(404,'Гипотеза не найдена')
    check_store_access(db,row['store_id'],principal)
    return row


def _task_scope(db: sqlite3.Connection, tid: int, principal: Principal):
    row=db.execute('SELECT * FROM bridge_tasks_r18 WHERE id=? AND organization_id=?',
                   (tid,principal.organization_id)).fetchone()
    if row is None:raise HTTPException(404,'Задача не найдена')
    check_store_access(db,row['store_id'],principal)
    return row


def _version(db,store,placement_id,version_id):
    row=db.execute('''SELECT p.*, v.content_json, v.content_hash, v.revision, f.title AS form_title
      FROM voice_placements_r17 p JOIN voice_forms_r17 f ON f.id=p.form_id
      JOIN voice_versions_r17 v ON v.form_id=f.id
      WHERE p.id=? AND v.id=? AND p.store_id=? AND p.organization_id=?''',
      (placement_id,version_id,store['id'],store['organization_id'])).fetchone()
    if not row:raise HTTPException(404,'Версия опроса или точка сбора не найдена')
    return row


def _aggregate(db,store,placement_id:int,version_id:int,question_id:str,choice:str,days:int):
    if not 7<=days<=90:raise HTTPException(422,'Выберите период 7–90 дней')
    v=_version(db,store,placement_id,version_id)
    questions=json.loads(v['content_json'])
    question=next((x for x in questions if x['id']==question_id),None)
    if not question or question['type']!='choice':raise HTTPException(422,'Для гипотезы нужен вопрос с вариантами')
    label=next((o['label'] for o in question['options'] if o['id']==choice),None)
    if label is None:raise HTTPException(422,'Вариант отсутствует в опубликованной версии')
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
    records=db.execute('''SELECT answers_json FROM voice_responses_r17
         WHERE store_id=? AND placement_id=? AND version_id=? AND submitted_at>=? LIMIT 20001''',
         (store['id'],placement_id,version_id,cutoff)).fetchall()
    if len(records)>20000:raise HTTPException(413,'Данных слишком много: сократите период')
    eligible=0;support=0
    for item in records:
        answers=json.loads(item['answers_json'])
        if question_id not in answers:continue
        eligible+=1
        if answers[question_id]==choice:support+=1
    return {'store':store['slug'],'placement_id':placement_id,'version_id':version_id,
       'revision':v['revision'],'content_sha':v['content_hash'],
       'question_id':question_id,'question':question['title'],
       'choice':choice,'choice_label':label,'days':days,'eligible_answers':eligible,
       'support':support,'share_pct':round(100*support/eligible,1) if eligible else None,
       'quality':('limited' if eligible<30 else 'observed'),
       'warnings':['Ответы добровольные; выборка не репрезентирует автоматически всех посетителей.',
                   'Доля ответов не является процентом потерянных продаж и не доказывает причины отказа.']+
                  (['Менее 30 ответов на вопрос: нестабильная доля.'] if eligible<30 else []),
       'frozen_at':now_iso(),'source':'voice_responses_r17 aggregate'}


class HypothesisIn(BaseModel):
    slug: str='central'
    request_id: str=Field(min_length=12,max_length=100)
    placement_id: int=Field(gt=0)
    version_id: int=Field(gt=0)
    question_id: str=Field(min_length=1,max_length=32)
    choice: str=Field(min_length=1,max_length=32)
    days: int=Field(default=14,ge=7,le=90)
    title: str=Field(min_length=12,max_length=180)
    category: Literal['assortment','service','stock','price','experience']


class ChangeState(BaseModel):
    status: Literal['investigating','resolved','dismissed']
    note: str=Field(min_length=12,max_length=600)


class PilotBridgeIn(BaseModel):
    request_id: str=Field(min_length=12,max_length=100)
    metric: Literal['receipts_per_100_entries','revenue_per_entry_rub','feedback_per_100_entries','demand_per_100_entries']
    source_mode: Literal['sensor','manual','all']='sensor'
    before_start: date
    before_end: date
    after_start: date
    after_end: date
    budget_kopeks: int=Field(default=0,ge=0,le=1000000000)


class TaskIn(BaseModel):
    request_id: str=Field(min_length=12,max_length=100)
    title: str=Field(min_length=12,max_length=180)
    owner: str=Field(min_length=3,max_length=100)
    due_date: date


class TaskStateIn(BaseModel):
    status: Literal['working','done','cancelled']
    note: str=Field(min_length=12,max_length=700)


def _record(db,principal,hid,event,old,new,note):
    db.execute('INSERT INTO bridge_history_r18(hypothesis_id,event,previous_status,next_status,note,actor_id,created_at) VALUES(?,?,?,?,?,?,?)',
               (hid,event,old,new,note,principal.user_id,now_iso()))
    audit(db,principal,'r18.'+event,str(hid))


def _pilot_integrity(db,row):
    if not row['pilot_id']:return {'status':'not_linked','sha_ok':None,'warnings':[]}
    pilot=db.execute('SELECT * FROM pilots_r15 WHERE id=? AND store_id=? AND organization_id=?',
                     (row['pilot_id'],row['store_id'],row['organization_id'])).fetchone()
    if not pilot:return {'status':'missing','sha_ok':False,'warnings':['Связанный пилот недоступен.']}
    report={'id':pilot['id'],'status':pilot['status'],'sha_ok':None,'warnings':[]}
    if pilot['status'] in ('completed','cancelled'):
        snap=db.execute('SELECT * FROM pilot_snapshots_r15 WHERE pilot_id=?',(pilot['id'],)).fetchone()
        if not snap or hashlib.sha256(snap['payload_json'].encode()).hexdigest()!=snap['payload_sha']:
            report['sha_ok']=False;report['warnings'].append('Контрольная сумма итогового отчёта нарушена или отчёт отсутствует.')
        else:report['sha_ok']=True;report['snapshot_sha']=snap['payload_sha']
    return report


def _present(db,row):
    d=dict(row)
    d['evidence']=json.loads(d.pop('evidence_json'))
    d['evidence_valid']=digest(d['evidence'])==d['evidence_sha']
    d['pilot']=_pilot_integrity(db,row)
    d['tasks_open']=db.execute("SELECT COUNT(*) FROM bridge_tasks_r18 WHERE hypothesis_id=? AND status IN ('open','working')",(row['id'],)).fetchone()[0]
    return d


def _csv(rows,keys):
    out=io.StringIO(newline='');writer=csv.writer(out)
    writer.writerow(keys)
    for x in rows:writer.writerow([safe_spreadsheet_cell(str(x.get(k,''))) for k in keys])
    return '\ufeff'+out.getvalue()


def build_router(admin,db_conn):
    router=APIRouter(prefix='/api/admin/r18',tags=['R1.8 Decision Bridge'])

    @router.get('/signals')
    def signals(slug:str='central',days:int=14,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        if not 7<=days<=90:raise HTTPException(422,'Период 7–90 дней')
        cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
        rows=db.execute('''SELECT r.placement_id,r.version_id,r.answers_json FROM voice_responses_r17 r
            WHERE r.store_id=? AND r.submitted_at>=? ORDER BY r.id DESC LIMIT 20001''',
            (store['id'],cutoff)).fetchall()
        if len(rows)>20000:raise HTTPException(413,'Сократите период: превышен лимит выборки')
        groups={}
        for rec in rows:
            key=(rec['placement_id'],rec['version_id'])
            g=groups.setdefault(key,{'counts':{},'total':{}})
            answers=json.loads(rec['answers_json'])
            for q,c in answers.items():
                if not isinstance(c,str):continue
                g['total'][q]=g['total'].get(q,0)+1
                group=g['counts'].setdefault(q,{})
                group[c]=group.get(c,0)+1
        items=[]
        for (placement,version),g in groups.items():
            v=_version(db,store,placement,version)
            for question in json.loads(v['content_json']):
                if question['type']!='choice':continue
                q=question['id'];n=g['total'].get(q,0)
                for opt in question['options']:
                    support=g['counts'].get(q,{}).get(opt['id'],0)
                    if support<3:continue
                    items.append({'placement_id':placement,'version_id':version,'question_id':q,'question':question['title'],
                       'choice':opt['id'],'label':opt['label'],'support':support,'eligible_answers':n,
                       'share_pct':round(100*support/n,1) if n else None,'quality':'limited' if n<30 else 'observed'})
        items.sort(key=lambda x:(-x['support'],x['question']))
        return {'items':items[:100],'days':days,'anonymous_responses':len(rows),
                'warnings':['Ответы добровольные; сигнал не доказывает потерю выручки.',
                            'Публикация новой версии анкеты не смешивает вопросы прошлой версии.']}

    @router.get('/hypotheses')
    def list_hypotheses(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        rows=db.execute('SELECT * FROM bridge_hypotheses_r18 WHERE store_id=? ORDER BY id DESC LIMIT 200',(store['id'],)).fetchall()
        return {'items':[_present(db,r) for r in rows]}

    @router.post('/hypotheses',status_code=201)
    def create_hypothesis(body:HypothesisIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager');store=visible_store(db,body.slug,principal)
        spec=body.model_dump(mode='json');spec_hash=digest({**spec,'store_id':store['id']})
        try:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM bridge_hypotheses_r18 WHERE organization_id=? AND request_id=?',
                           (principal.organization_id,body.request_id)).fetchone()
            if old:
                if old['request_hash']!=spec_hash:raise HTTPException(409,'Ключ запроса использован с другими данными')
                db.rollback();return {'id':old['id'],'duplicate':True}
            evidence=_aggregate(db,store,body.placement_id,body.version_id,body.question_id,body.choice,body.days)
            if evidence['support']<3:raise HTTPException(409,'Нужно минимум три зафиксированных ответа на выбранный вариант')
            stamp=now_iso()
            cur=db.execute('''INSERT INTO bridge_hypotheses_r18(organization_id,store_id,request_id,request_hash,
              placement_id,version_id,question_id,choice_code,title,category,evidence_json,evidence_sha,created_by,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(principal.organization_id,store['id'],body.request_id,spec_hash,
              body.placement_id,body.version_id,body.question_id,body.choice,body.title.strip(),body.category,
              canonical(evidence),digest(evidence),principal.user_id,stamp,stamp))
            _record(db,principal,cur.lastrowid,'hypothesis.create','','candidate','Создана из обезличенной выборки')
            db.commit();return {'id':cur.lastrowid,'duplicate':False,'evidence':evidence}
        except Exception:db.rollback();raise

    @router.get('/hypotheses/{hid}')
    def hypothesis(hid:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        row=_scope(db,hid,principal)
        return {'item':_present(db,row),'history':[dict(r) for r in db.execute(
            'SELECT * FROM bridge_history_r18 WHERE hypothesis_id=? ORDER BY id',(hid,))],
            'tasks':[dict(r) for r in db.execute('SELECT * FROM bridge_tasks_r18 WHERE hypothesis_id=? ORDER BY id',(hid,))]}

    @router.patch('/hypotheses/{hid}/status')
    def change_status(hid:int,body:ChangeState,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            db.execute('BEGIN IMMEDIATE');row=_scope(db,hid,principal)
            permitted={'candidate':('investigating','dismissed'),'investigating':('resolved','dismissed'),
                       'pilot_linked':('resolved','dismissed')}
            if body.status not in permitted.get(row['status'],()):raise HTTPException(409,'Недопустимый переход статуса')
            if body.status=='resolved':
                if digest(json.loads(row['evidence_json']))!=row['evidence_sha']:
                    raise HTTPException(409,'Контрольная сумма исходной выборки нарушена')
                if row['pilot_id']:
                    report=_pilot_integrity(db,row)
                    if report['status']!='completed' or report['sha_ok'] is not True:
                        raise HTTPException(409,'Для закрытия требуется завершённый пилот с неповреждённым снимком')
                elif not db.execute("SELECT 1 FROM bridge_tasks_r18 WHERE hypothesis_id=? AND status='done'",(hid,)).fetchone():
                    raise HTTPException(409,'Нужно подтверждённое выполнение хотя бы одной задачи')
            db.execute('UPDATE bridge_hypotheses_r18 SET status=?,updated_at=? WHERE id=?',
                       (body.status,now_iso(),hid))
            _record(db,principal,hid,'hypothesis.status',row['status'],body.status,body.note.strip())
            db.commit();return {'id':hid,'status':body.status}
        except Exception:db.rollback();raise

    @router.post('/hypotheses/{hid}/pilot',status_code=201)
    def bridge_pilot(hid:int,body:PilotBridgeIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        # Validate the exact Pilot Studio contract before taking a DB write lock.
        try:
            db.execute('BEGIN IMMEDIATE');row=_scope(db,hid,principal)
            store=db.execute('SELECT slug FROM stores WHERE id=?',(row['store_id'],)).fetchone()
            if digest(json.loads(row['evidence_json']))!=row['evidence_sha']:
                raise HTTPException(409,'Контрольная сумма исходной выборки нарушена')
            pilot_spec=CreatePilot(slug=store['slug'],request_id=body.request_id,title=row['title'][:120],
                hypothesis='Проверить гипотезу по добровольным ответам: '+row['title'],metric=body.metric,
                source_mode=body.source_mode,before_start=body.before_start,before_end=body.before_end,
                after_start=body.after_start,after_end=body.after_end,budget_kopeks=body.budget_kopeks)
            spec=pilot_spec.model_dump(mode='json');spec_hash=r15_sha(spec)
            if row['pilot_id']:
                if row['pilot_request_hash']!=spec_hash:raise HTTPException(409,'Для гипотезы уже связан другой пилот')
                db.rollback();return {'id':row['pilot_id'],'duplicate':True}
            if row['status']!='investigating':raise HTTPException(409,'Сначала подтвердите изучение гипотезы')
            old=db.execute('SELECT id,spec_hash FROM pilots_r15 WHERE organization_id=? AND request_id=?',
                           (principal.organization_id,body.request_id)).fetchone()
            if old:raise HTTPException(409,'Ключ пилота уже занят другим процессом')
            cur=db.execute('''INSERT INTO pilots_r15(organization_id,store_id,request_id,spec_hash,title,hypothesis,metric,source_mode,
               before_start,before_end,after_start,after_end,budget_kopeks,created_by,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
               (principal.organization_id,row['store_id'],body.request_id,spec_hash,spec['title'],spec['hypothesis'],
                spec['metric'],spec['source_mode'],spec['before_start'],spec['before_end'],spec['after_start'],
                spec['after_end'],spec['budget_kopeks'],principal.user_id,now_iso()))
            db.execute("UPDATE bridge_hypotheses_r18 SET pilot_id=?,pilot_request_hash=?,status='pilot_linked',updated_at=? WHERE id=?",
                       (cur.lastrowid,spec_hash,now_iso(),hid))
            _record(db,principal,hid,'pilot.link','investigating','pilot_linked',f'Черновик Pilot Studio №{cur.lastrowid}')
            db.commit();return {'id':cur.lastrowid,'duplicate':False,'status':'draft'}
        except Exception:db.rollback();raise

    @router.post('/hypotheses/{hid}/tasks',status_code=201)
    def create_task(hid:int,body:TaskIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        spec=body.model_dump(mode='json')
        if body.due_date<date.today():raise HTTPException(422,'Срок не может быть в прошлом')
        try:
            db.execute('BEGIN IMMEDIATE');row=_scope(db,hid,principal)
            if row['status'] in ('resolved','dismissed'):raise HTTPException(409,'Гипотеза закрыта')
            key=digest({'hypothesis_id':hid,**spec})
            old=db.execute('SELECT * FROM bridge_tasks_r18 WHERE organization_id=? AND request_id=?',
                           (principal.organization_id,body.request_id)).fetchone()
            if old:
                if old['request_hash']!=key:raise HTTPException(409,'Ключ задачи уже занят другим содержимым')
                db.rollback();return {'id':old['id'],'duplicate':True}
            stamp=now_iso()
            cur=db.execute('''INSERT INTO bridge_tasks_r18(organization_id,store_id,hypothesis_id,request_id,request_hash,title,owner,due_date,created_at,updated_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?)''',
                 (principal.organization_id,row['store_id'],hid,body.request_id,key,body.title.strip(),body.owner.strip(),str(body.due_date),stamp,stamp))
            audit(db,principal,'r18.task.create',str(cur.lastrowid));db.commit()
            return {'id':cur.lastrowid,'duplicate':False}
        except Exception:db.rollback();raise

    @router.patch('/tasks/{tid}')
    def change_task(tid:int,body:TaskStateIn,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            db.execute('BEGIN IMMEDIATE');row=_task_scope(db,tid,principal)
            allowed={'open':('working','cancelled'),'working':('done','cancelled')}
            if body.status not in allowed.get(row['status'],()):raise HTTPException(409,'Недопустимый переход задачи')
            db.execute('UPDATE bridge_tasks_r18 SET status=?,evidence_note=?,updated_at=? WHERE id=?',
                       (body.status,body.note.strip(),now_iso(),tid))
            db.execute('INSERT INTO bridge_task_history_r18(task_id,previous_status,next_status,note,actor_id,created_at) VALUES(?,?,?,?,?,?)',
                       (tid,row['status'],body.status,body.note.strip(),principal.user_id,now_iso()))
            audit(db,principal,'r18.task.update',str(tid));db.commit()
            return {'id':tid,'status':body.status}
        except Exception:db.rollback();raise

    @router.get('/tasks/{tid}/history')
    def task_history(tid:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        _task_scope(db,tid,principal)
        return {'items':[dict(r) for r in db.execute('SELECT * FROM bridge_task_history_r18 WHERE task_id=? ORDER BY id',(tid,))]}

    @router.get('/board')
    def board(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        rows=db.execute('SELECT * FROM bridge_hypotheses_r18 WHERE store_id=? ORDER BY id DESC LIMIT 200',(store['id'],)).fetchall()
        items=[_present(db,r) for r in rows]
        statuses={s:sum(x['status']==s for x in items) for s in ('candidate','investigating','pilot_linked','resolved','dismissed')}
        return {'store':store['slug'],'hypotheses':len(items),'statuses':statuses,
            'pending_tasks':sum(x['tasks_open'] for x in items),
            'proof_alerts':sum(not x['evidence_valid'] or x['pilot'].get('sha_ok') is False for x in items),
            'items':items,'warnings':['Наблюдения из опросов не равны упущенной выручке.',
            'Закрытый пилот показывает сравнение периодов, а не доказательство причинного эффекта.']}

    @router.get('/board.csv')
    def export_board(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        summary=board(slug,principal,db)
        records=[{'id':x['id'],'title':x['title'],'status':x['status'],
          'support':x['evidence'].get('support',''),'eligible':x['evidence'].get('eligible_answers',''),
          'evidence_valid':x['evidence_valid'],'pilot_id':x['pilot_id'] or '',
          'pilot_status':x['pilot']['status'],'tasks_open':x['tasks_open']} for x in summary['items']]
        content=_csv(records,['id','title','status','support','eligible','evidence_valid','pilot_id','pilot_status','tasks_open'])
        return Response(content,media_type='text/csv; charset=utf-8',
           headers={'Content-Disposition':'attachment; filename="osmanx-decision-bridge.csv"','Cache-Control':'no-store'})

    return router
