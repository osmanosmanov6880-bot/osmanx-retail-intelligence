"""R1.7 Voice Studio: versioned anonymous exit surveys and evidence-first actions.

No buyer identification, face recognition, contact collection, automatic rewards,
POS writes or unsupported causal claims. Public endpoints require a placement key.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import re
import secrets
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.database import now_iso
from backend.retail import safe_spreadsheet_cell
from backend.security import Principal, audit, require_role, visible_store, check_store_access

SCHEMA = """
CREATE TABLE IF NOT EXISTS voice_forms_r17 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 request_id TEXT NOT NULL,
 request_hash TEXT NOT NULL,
 title TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('draft','published','archived')),
 draft_json TEXT NOT NULL,
 draft_hash TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(organization_id,request_id)
);
CREATE INDEX IF NOT EXISTS ix_r17_forms_store ON voice_forms_r17(store_id,status,id);
CREATE TABLE IF NOT EXISTS voice_versions_r17 (
 id INTEGER PRIMARY KEY,
 form_id INTEGER NOT NULL REFERENCES voice_forms_r17(id),
 revision INTEGER NOT NULL CHECK(revision>0),
 content_json TEXT NOT NULL, content_hash TEXT NOT NULL,
 published_at TEXT NOT NULL,
 UNIQUE(form_id,revision)
);
CREATE TABLE IF NOT EXISTS voice_placements_r17 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 form_id INTEGER NOT NULL REFERENCES voice_forms_r17(id),
 public_id TEXT NOT NULL UNIQUE,
 secret_hash TEXT NOT NULL,
 generation INTEGER NOT NULL DEFAULT 1,
 name TEXT NOT NULL, medium TEXT NOT NULL CHECK(medium IN ('kiosk','qr')),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_r17_placements_store ON voice_placements_r17(store_id,id);
CREATE TABLE IF NOT EXISTS voice_opens_r17 (
 id INTEGER PRIMARY KEY,
 placement_id INTEGER NOT NULL REFERENCES voice_placements_r17(id),
 version_id INTEGER NOT NULL REFERENCES voice_versions_r17(id),
 request_id TEXT NOT NULL, opened_at TEXT NOT NULL,
 UNIQUE(placement_id,request_id)
);
CREATE INDEX IF NOT EXISTS ix_r17_opens_time ON voice_opens_r17(placement_id,opened_at);
CREATE TABLE IF NOT EXISTS voice_responses_r17 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 placement_id INTEGER NOT NULL REFERENCES voice_placements_r17(id),
 version_id INTEGER NOT NULL REFERENCES voice_versions_r17(id),
 request_id TEXT NOT NULL, payload_hash TEXT NOT NULL,
 answers_json TEXT NOT NULL, submitted_at TEXT NOT NULL,
 UNIQUE(placement_id,request_id)
);
CREATE INDEX IF NOT EXISTS ix_r17_responses_time ON voice_responses_r17(store_id,submitted_at);
CREATE TABLE IF NOT EXISTS voice_actions_r17 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 placement_id INTEGER NOT NULL REFERENCES voice_placements_r17(id),
 version_id INTEGER NOT NULL REFERENCES voice_versions_r17(id),
 request_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 question_id TEXT NOT NULL, choice TEXT NOT NULL,
 action_type TEXT NOT NULL CHECK(action_type IN ('stock','service','assortment','price','experience')),
 title TEXT NOT NULL, evidence_count INTEGER NOT NULL,
 evidence_total INTEGER NOT NULL, evidence_json TEXT NOT NULL, evidence_hash TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('new','investigating','implemented','dismissed')),
 note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(organization_id,request_id)
);
CREATE TABLE IF NOT EXISTS voice_action_history_r17 (
 id INTEGER PRIMARY KEY,
 action_id INTEGER NOT NULL REFERENCES voice_actions_r17(id),
 old_status TEXT NOT NULL, new_status TEXT NOT NULL,
 note TEXT NOT NULL, actor_id INTEGER NOT NULL, changed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_r17_action_store ON voice_actions_r17(store_id,status,id);
"""

ID = re.compile(r'^[a-z][a-z0-9_]{0,31}$')


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)


def canonical(value: object) -> str:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def clean_form(questions: object) -> list[dict]:
    """Strict ordered conditional-choice schema; no free text or personal data fields."""
    if not isinstance(questions,list) or not 2 <= len(questions) <= 8:
        raise HTTPException(422,'Опрос должен содержать от 2 до 8 вопросов')
    previous: dict[str,dict]={}
    result=[]
    for q in questions:
        if not isinstance(q,dict) or set(q)-{'id','title','type','options','show_if'}:
            raise HTTPException(422,'Недопустимые поля вопроса')
        ident=q.get('id');title=q.get('title');kind=q.get('type')
        if not isinstance(ident,str) or not ID.fullmatch(ident) or ident in previous:
            raise HTTPException(422,'Код вопроса должен быть уникальным: латинские буквы, цифры, _')
        if not isinstance(title,str) or not 5<=len(title.strip())<=140:
            raise HTTPException(422,'Заголовок вопроса должен содержать от 5 до 140 символов')
        if kind not in ('choice','rating'):
            raise HTTPException(422,'Поддерживаются выбор варианта и оценка от 1 до 5')
        options=[]
        if kind=='choice':
            raw=q.get('options')
            if not isinstance(raw,list) or not 2<=len(raw)<=6:
                raise HTTPException(422,'Для выбора предусмотрено 2–6 вариантов')
            codes=set()
            for opt in raw:
                if not isinstance(opt,dict) or set(opt)!={'id','label'}:
                    raise HTTPException(422,'Вариант должен иметь только id и label')
                oid, label=opt['id'],opt['label']
                if not isinstance(oid,str) or not ID.fullmatch(oid) or oid in codes:
                    raise HTTPException(422,'Неверный или повторяющийся код варианта')
                if not isinstance(label,str) or not 1<=len(label.strip())<=70:
                    raise HTTPException(422,'Название варианта должно содержать от 1 до 70 символов')
                codes.add(oid);options.append({'id':oid,'label':label.strip()})
        elif 'options' in q and q['options'] not in ([],None):
            raise HTTPException(422,'Оценка от 1 до 5 не имеет вариантов')
        condition=q.get('show_if')
        if condition is not None:
            if not isinstance(condition,dict) or set(condition)!={'question','equals'}:
                raise HTTPException(422,'Недопустимое условие показа')
            earlier=previous.get(condition['question']) if isinstance(condition.get('question'),str) else None
            if not earlier or earlier['type']!='choice' or condition['equals'] not in [v['id'] for v in earlier['options']]:
                raise HTTPException(422,'Условие может ссылаться только на уже заданный вариант выбора')
        item={'id':ident,'title':title.strip(),'type':kind,'options':options}
        if condition is not None:item['show_if']={'question':condition['question'],'equals':condition['equals']}
        result.append(item);previous[ident]=item
    if result[0].get('show_if'):
        raise HTTPException(422,'Первый вопрос не может быть условным')
    return result


def validate_answers(questions: list[dict], submitted: object) -> dict:
    if not isinstance(submitted,dict) or len(submitted)>8:
        raise HTTPException(422,'Ответы должны быть объектом без посторонних полей')
    result={}
    for question in questions:
        cond=question.get('show_if')
        visible=not cond or result.get(cond['question'])==cond['equals']
        ident=question['id']
        if not visible:
            if ident in submitted:
                raise HTTPException(422,'Ответ на скрытый вопрос запрещён')
            continue
        if ident not in submitted:
            raise HTTPException(422,'Не хватает ответа на вопрос: '+ident)
        answer=submitted[ident]
        if question['type']=='rating':
            if type(answer) is not int or not 1<=answer<=5:
                raise HTTPException(422,'Оценка должна быть целым числом от 1 до 5')
        else:
            if not isinstance(answer,str) or answer not in [o['id'] for o in question['options']]:
                raise HTTPException(422,'Неизвестный вариант: '+ident)
        result[ident]=answer
    if set(result)!=set(submitted):
        raise HTTPException(422,'Посторонние ответы запрещены')
    return result


def form_scope(db: sqlite3.Connection, form_id: int, principal: Principal):
    form=db.execute('SELECT * FROM voice_forms_r17 WHERE id=? AND organization_id=?',
                    (form_id,principal.organization_id)).fetchone()
    if not form:raise HTTPException(404,'Опрос не найден')
    check_store_access(db,form['store_id'],principal)
    return form


def placement_scope(db:sqlite3.Connection, placement_id:int, principal:Principal):
    placement=db.execute('SELECT * FROM voice_placements_r17 WHERE id=? AND organization_id=?',
                         (placement_id,principal.organization_id)).fetchone()
    if not placement:raise HTTPException(404,'Терминал не найден')
    check_store_access(db,placement['store_id'],principal)
    return placement


def placement_public(db, public_id: str, key: str | None):
    placement=db.execute('''SELECT p.*,f.status AS form_status,f.revision
        FROM voice_placements_r17 p JOIN voice_forms_r17 f ON f.id=p.form_id
        WHERE p.public_id=?''',(public_id,)).fetchone()
    if not placement or not placement['active'] or placement['form_status']!='published':
        raise HTTPException(404,'Опрос недоступен')
    if not isinstance(key,str) or not hmac.compare_digest(placement['secret_hash'],hashlib.sha256(key.encode()).hexdigest()):
        raise HTTPException(401,'Недействительный ключ терминала')
    return placement


def latest_version(db,placement):
    record=db.execute('SELECT * FROM voice_versions_r17 WHERE form_id=? ORDER BY revision DESC LIMIT 1',
                      (placement['form_id'],)).fetchone()
    if not record:raise HTTPException(409,'Опрос ещё не опубликован')
    return record


def row_dict(record):
    return dict(record) if record else None


class FormCreate(BaseModel):
    slug: str='central'
    request_id: str=Field(min_length=12,max_length=100)
    title: str=Field(min_length=5,max_length=120)
    questions: list[dict]=Field(min_length=2,max_length=8)


class FormEdit(BaseModel):
    expected_draft_hash: str=Field(min_length=64,max_length=64)
    questions: list[dict]=Field(min_length=2,max_length=8)
    title: str=Field(min_length=5,max_length=120)


class PlacementCreate(BaseModel):
    form_id: int=Field(gt=0)
    name: str=Field(min_length=3,max_length=90)
    medium: Literal['kiosk','qr']='kiosk'


class QRDownload(BaseModel):
    url: str=Field(min_length=25,max_length=800)


class OpenEvent(BaseModel):
    request_id: str=Field(min_length=16,max_length=100)
    version_hash: str=Field(min_length=64,max_length=64)


class Submission(OpenEvent):
    answers: dict[str,object]=Field(min_length=1,max_length=8)


class ActionCreate(BaseModel):
    slug: str='central'
    request_id: str=Field(min_length=12,max_length=100)
    placement_id: int=Field(gt=0)
    question_id: str=Field(min_length=1,max_length=32)
    choice: str=Field(min_length=1,max_length=32)
    action_type: Literal['stock','service','assortment','price','experience']
    title: str=Field(min_length=10,max_length=160)


class ActionUpdate(BaseModel):
    status: Literal['investigating','implemented','dismissed']
    note: str=Field(min_length=10,max_length=1500)


def _transaction(db):
    db.execute('BEGIN IMMEDIATE')


def _remaining_today(db,placement_id:int,table:str,limit:int):
    if table not in ('voice_opens_r17','voice_responses_r17'):raise ValueError('Invalid table')
    field='opened_at' if table=='voice_opens_r17' else 'submitted_at'
    today=datetime.now(timezone.utc).date().isoformat()
    count=db.execute(f'SELECT COUNT(*) FROM {table} WHERE placement_id=? AND {field}>=?',
                     (placement_id,today)).fetchone()[0]
    if count>=limit:raise HTTPException(429,'На сегодня лимит терминала исчерпан')


def _csv(rows,fields):
    out=io.StringIO(newline='');writer=csv.writer(out)
    writer.writerow(fields)
    for row in rows:writer.writerow([safe_spreadsheet_cell(row.get(x,'')) for x in fields])
    return '\ufeff'+out.getvalue()


def insight_report(db,store,days:int=14):
    if not 1<=days<=90:raise HTTPException(422,'Доступен период от 1 до 90 дней')
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
    placements=db.execute('SELECT * FROM voice_placements_r17 WHERE store_id=? ORDER BY id DESC LIMIT 200',
                          (store['id'],)).fetchall()
    records=db.execute('''SELECT r.*,p.name AS placement_name,p.medium,v.content_json,v.revision
       FROM voice_responses_r17 r JOIN voice_placements_r17 p ON p.id=r.placement_id
       JOIN voice_versions_r17 v ON v.id=r.version_id
       WHERE r.store_id=? AND r.submitted_at>=? ORDER BY r.id DESC LIMIT 50001''',
       (store['id'],cutoff)).fetchall()
    if len(records)>50000:raise HTTPException(413,'Слишком много ответов; сократите период')
    opens=db.execute('''SELECT placement_id,COUNT(*) AS n FROM voice_opens_r17
       WHERE placement_id IN (SELECT id FROM voice_placements_r17 WHERE store_id=?) AND opened_at>=?
       GROUP BY placement_id''',(store['id'],cutoff)).fetchall()
    opened={r['placement_id']:r['n'] for r in opens}
    completed=Counter(r['placement_id'] for r in records)
    summary=[]
    for p in placements:
        o=opened.get(p['id'],0);n=completed[p['id']]
        summary.append({'id':p['id'],'name':p['name'],'medium':p['medium'],'active':bool(p['active']),
                        'opens':o,'responses':n,'completion_per_open_pct':round(100*n/o,1) if o else None})
    counts=defaultdict(Counter); totals=Counter();meta={}
    placement_counts=defaultdict(Counter); placement_totals=Counter()
    for rec in records:
        questions=json.loads(rec['content_json']);answers=json.loads(rec['answers_json'])
        for q in questions:
            ident=q['id']; value=answers.get(ident)
            if value is None:continue
            key=(rec['version_id'],ident)
            counts[key][str(value)]+=1; totals[key]+=1
            placekey=(rec['placement_id'],rec['version_id'],ident)
            placement_counts[placekey][str(value)]+=1;placement_totals[placekey]+=1
            meta[key]={'version_id':rec['version_id'],'revision':rec['revision'],'question_id':ident,
                       'title':q['title'],'type':q['type'],'options':q['options']}
    questions=[]
    for key,c in counts.items():
        info=meta[key];n=totals[key]
        labels={x['id']:x['label'] for x in info['options']}
        questions.append({'version_id':info['version_id'],'revision':info['revision'],
           'question_id':info['question_id'],'title':info['title'],'responses':n,
           'counts':[{'code':code,'label':labels.get(code,str(code)),
                      'count':count,'pct':round(100*count/n,1)} for code,count in c.most_common()]})
    questions.sort(key=lambda q:(q['version_id'],q['question_id']))
    evidence_options=[]
    for (placement_id,version_id,question_id),c in placement_counts.items():
        info=meta[(version_id,question_id)]
        if info['type']!='choice':continue
        for choice,count in c.items():
            if count>=3:
                label=next((o['label'] for o in info['options'] if o['id']==choice),choice)
                evidence_options.append({'placement_id':placement_id,'version_id':version_id,
                   'question_id':question_id,'question_title':info['title'],'choice':choice,
                   'label':label,'support':count,'total':placement_totals[(placement_id,version_id,question_id)]})
    evidence_options.sort(key=lambda x:(-x['support'],x['placement_id']))
    warnings=['Ответы добровольные и могут быть нерепрезентативными. Они не доказывают причину отказа или потерю выручки.',
              'Открытие ссылки не равно уникальному посетителю. Доля завершений — ответы / открытия, не конверсия продаж.']
    if len(records)<30:warnings.append('Менее 30 ответов: доли нестабильны, не делайте выводов о всех покупателях.')
    if not opens:warnings.append('Нет зарегистрированных открытий: невозможно рассчитать долю завершений.')
    return {'store':store['slug'],'days':days,'placements':summary,'responses':len(records),
            'opens':sum(opened.values()),'questions':questions,'evidence_options':evidence_options,'warnings':warnings,'period':'UTC'}


def build_router(admin,db_conn):
    router=APIRouter()

    @router.get('/api/admin/r17/forms')
    def forms(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        rows=db.execute('SELECT * FROM voice_forms_r17 WHERE store_id=? ORDER BY id DESC LIMIT 100',
                        (store['id'],)).fetchall()
        return {'items':[{'id':r['id'],'title':r['title'],'status':r['status'],'revision':r['revision'],
                 'draft_hash':r['draft_hash'],'questions':json.loads(r['draft_json'])} for r in rows]}

    @router.post('/api/admin/r17/forms',status_code=201)
    def create_form(body:FormCreate,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager');store=visible_store(db,body.slug,principal)
        if len(body.title.strip())<5:raise HTTPException(422,'Укажите название анкеты')
        q=clean_form(body.questions);request={'store':store['id'],'title':body.title.strip(),'questions':q}
        stamp=now_iso();hash_=digest(request)
        try:
            _transaction(db)
            previous=db.execute('SELECT * FROM voice_forms_r17 WHERE organization_id=? AND request_id=?',
                               (principal.organization_id,body.request_id)).fetchone()
            if previous:
                if previous['request_hash']!=hash_:raise HTTPException(409,'Ключ уже использован с другими данными')
                db.commit();return {'id':previous['id'],'draft_hash':previous['draft_hash'],'duplicate':True}
            cur=db.execute('''INSERT INTO voice_forms_r17(organization_id,store_id,request_id,request_hash,title,status,draft_json,draft_hash,created_at,updated_at)
                   VALUES(?,?,?,?,?,'draft',?,?,?,?)''',
                   (principal.organization_id,store['id'],body.request_id,hash_,body.title.strip(),canonical(q),digest(q),stamp,stamp))
            audit(db,principal,'voice.form.create',str(cur.lastrowid));db.commit()
            return {'id':cur.lastrowid,'draft_hash':digest(q),'duplicate':False}
        except Exception:
            db.rollback();raise

    @router.patch('/api/admin/r17/forms/{form_id}')
    def edit_form(form_id:int,body:FormEdit,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager');clean=clean_form(body.questions)
        if len(body.title.strip())<5:raise HTTPException(422,'Укажите название анкеты')
        try:
            _transaction(db);row=form_scope(db,form_id,principal)
            if row['status']=='archived':raise HTTPException(409,'Архивный опрос нельзя менять')
            if row['draft_hash']!=body.expected_draft_hash:raise HTTPException(409,'Черновик изменён другим сотрудником')
            db.execute('UPDATE voice_forms_r17 SET title=?,draft_json=?,draft_hash=?,updated_at=? WHERE id=?',
                       (body.title.strip(),canonical(clean),digest(clean),now_iso(),form_id))
            audit(db,principal,'voice.form.edit',str(form_id));db.commit()
            return {'id':form_id,'draft_hash':digest(clean)}
        except Exception:db.rollback();raise

    @router.post('/api/admin/r17/forms/{form_id}/publish')
    def publish_form(form_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            _transaction(db);form=form_scope(db,form_id,principal)
            if form['status']=='archived':raise HTTPException(409,'Архив нельзя опубликовать')
            prev=db.execute('SELECT * FROM voice_versions_r17 WHERE form_id=? ORDER BY revision DESC LIMIT 1',(form_id,)).fetchone()
            if prev and prev['content_hash']==form['draft_hash']:
                db.commit();return {'version_id':prev['id'],'revision':prev['revision'],'duplicate':True}
            rev=form['revision']+1
            cur=db.execute('INSERT INTO voice_versions_r17(form_id,revision,content_json,content_hash,published_at) VALUES(?,?,?,?,?)',
                           (form_id,rev,form['draft_json'],form['draft_hash'],now_iso()))
            db.execute("UPDATE voice_forms_r17 SET status='published',revision=?,updated_at=? WHERE id=?",(rev,now_iso(),form_id))
            audit(db,principal,'voice.form.publish',f'{form_id}:{rev}');db.commit()
            return {'version_id':cur.lastrowid,'revision':rev,'duplicate':False}
        except Exception:db.rollback();raise

    @router.post('/api/admin/r17/forms/{form_id}/archive')
    def archive_form(form_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            _transaction(db);form_scope(db,form_id,principal)
            db.execute("UPDATE voice_forms_r17 SET status='archived',updated_at=? WHERE id=?",(now_iso(),form_id))
            audit(db,principal,'voice.form.archive',str(form_id));db.commit();return {'archived':True}
        except Exception:db.rollback();raise

    @router.get('/api/admin/r17/forms/{form_id}/versions')
    def versions(form_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        form_scope(db,form_id,principal)
        return {'items':[{'id':r['id'],'revision':r['revision'],'content_hash':r['content_hash'],
                   'published_at':r['published_at'],'questions':json.loads(r['content_json'])}
                  for r in db.execute('SELECT * FROM voice_versions_r17 WHERE form_id=? ORDER BY id DESC LIMIT 50',(form_id,))]}

    @router.get('/api/admin/r17/placements')
    def placements(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        return {'items':[{'id':p['id'],'public_id':p['public_id'],'name':p['name'],'medium':p['medium'],
                    'form_id':p['form_id'],'active':bool(p['active']),'generation':p['generation']}
                  for p in db.execute('SELECT * FROM voice_placements_r17 WHERE store_id=? ORDER BY id DESC LIMIT 100',(store['id'],))]}

    @router.post('/api/admin/r17/placements',status_code=201)
    def create_placement(body:PlacementCreate,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        if len(body.name.strip())<3:raise HTTPException(422,'Укажите название терминала')
        try:
            _transaction(db);form=form_scope(db,body.form_id,principal)
            if form['status']!='published':raise HTTPException(409,'Сначала опубликуйте анкету')
            secret=secrets.token_urlsafe(32);public_id=secrets.token_urlsafe(15)
            cur=db.execute('''INSERT INTO voice_placements_r17(organization_id,store_id,form_id,public_id,secret_hash,name,medium,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)''',(principal.organization_id,form['store_id'],body.form_id,public_id,
               hashlib.sha256(secret.encode()).hexdigest(),body.name.strip(),body.medium,now_iso(),now_iso()))
            audit(db,principal,'voice.placement.create',str(cur.lastrowid));db.commit()
            return {'id':cur.lastrowid,'public_id':public_id,'secret':secret,'generation':1,
                    'fragment':public_id+'.'+secret,'note':'Сохраните ссылку: ключ показывается только один раз.'}
        except Exception:db.rollback();raise

    @router.post('/api/admin/r17/placements/{placement_id}/rotate')
    def rotate(placement_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            _transaction(db);p=placement_scope(db,placement_id,principal)
            if not p['active']:raise HTTPException(409,'Терминал отключён')
            secret=secrets.token_urlsafe(32)
            db.execute('UPDATE voice_placements_r17 SET secret_hash=?,generation=generation+1,updated_at=? WHERE id=?',
                       (hashlib.sha256(secret.encode()).hexdigest(),now_iso(),placement_id))
            audit(db,principal,'voice.placement.rotate',str(placement_id));db.commit()
            return {'public_id':p['public_id'],'secret':secret,'generation':p['generation']+1}
        except Exception:db.rollback();raise

    @router.post('/api/admin/r17/placements/{placement_id}/qr.svg')
    def placement_qr(placement_id:int,body:QRDownload,request:Request,
                     principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        # The server never stores or returns the placement secret after issuance.
        require_role(principal,'owner','manager')
        placement=placement_scope(db,placement_id,principal)
        if not placement['active']:raise HTTPException(409,'Терминал отключён')
        url=urlsplit(body.url)
        origin=urlsplit(str(request.base_url))
        bits=url.fragment.split('.',1)
        if (url.scheme not in ('https','http') or url.netloc!=origin.netloc or
            url.path!='/static/voice_kiosk.html' or url.query or len(bits)!=2 or
            bits[0]!=placement['public_id'] or
            not hmac.compare_digest(placement['secret_hash'],hashlib.sha256(bits[1].encode()).hexdigest())):
            raise HTTPException(422,'QR может содержать только действующую ссылку терминала на этом сервере')
        import qrcode
        from qrcode.image.svg import SvgPathImage
        qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=8,border=4)
        qr.add_data(body.url);qr.make(fit=True)
        output=io.BytesIO();qr.make_image(image_factory=SvgPathImage).save(output)
        return Response(output.getvalue(),media_type='image/svg+xml',headers={
           'Content-Disposition':'attachment; filename="osmanx-voice-qr.svg"','Cache-Control':'no-store',
           'X-Content-Type-Options':'nosniff'})

    @router.post('/api/admin/r17/placements/{placement_id}/disable')
    def disable(placement_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            _transaction(db);placement_scope(db,placement_id,principal)
            db.execute('UPDATE voice_placements_r17 SET active=0,updated_at=? WHERE id=?',(now_iso(),placement_id))
            audit(db,principal,'voice.placement.disable',str(placement_id));db.commit();return {'disabled':True}
        except Exception:db.rollback();raise

    @router.get('/api/voice/r17/{public_id}/form')
    def public_form(public_id:str,x_voice_key:str|None=Header(default=None,alias='X-OSMANX-Voice-Key'),db:sqlite3.Connection=Depends(db_conn)):
        p=placement_public(db,public_id,x_voice_key)
        from backend.r19 import require_schedule
        require_schedule(db,p)
        v=latest_version(db,p)
        return {'name':p['name'],'medium':p['medium'],'form_version':v['revision'],
                'version_hash':v['content_hash'],'title':db.execute('SELECT title FROM voice_forms_r17 WHERE id=?',(p['form_id'],)).fetchone()[0],
                'questions':json.loads(v['content_json']), 'notice':'Опрос анонимный. Ответы добровольные. Не вводите персональные данные.'}

    @router.post('/api/voice/r17/{public_id}/open',status_code=201)
    def open_form(public_id:str,body:OpenEvent,x_voice_key:str|None=Header(default=None,alias='X-OSMANX-Voice-Key'),db:sqlite3.Connection=Depends(db_conn)):
        try:
            _transaction(db);p=placement_public(db,public_id,x_voice_key)
            from backend.r19 import require_schedule
            require_schedule(db,p)
            v=latest_version(db,p)
            if v['content_hash']!=body.version_hash:raise HTTPException(409,'Опрос обновлён. Перезагрузите анкету')
            previous=db.execute('SELECT * FROM voice_opens_r17 WHERE placement_id=? AND request_id=?',
                                (p['id'],body.request_id)).fetchone()
            if previous:
                if previous['version_id']!=v['id']:raise HTTPException(409,'Устаревшая версия анкеты')
                db.commit();return {'opened':True,'duplicate':True}
            _remaining_today(db,p['id'],'voice_opens_r17',6000)
            db.execute('INSERT INTO voice_opens_r17(placement_id,version_id,request_id,opened_at) VALUES(?,?,?,?)',
                       (p['id'],v['id'],body.request_id,now_iso()))
            db.commit();return {'opened':True,'duplicate':False}
        except Exception:db.rollback();raise

    @router.post('/api/voice/r17/{public_id}/submit',status_code=201)
    def submit(public_id:str,body:Submission,x_voice_key:str|None=Header(default=None,alias='X-OSMANX-Voice-Key'),db:sqlite3.Connection=Depends(db_conn)):
        try:
            _transaction(db);p=placement_public(db,public_id,x_voice_key);v=latest_version(db,p)
            if v['content_hash']!=body.version_hash:raise HTTPException(409,'Анкета обновлена. Начните заново')
            opened=db.execute('SELECT * FROM voice_opens_r17 WHERE placement_id=? AND request_id=?',(p['id'],body.request_id)).fetchone()
            if not opened or opened['version_id']!=v['id']:
                raise HTTPException(409,'Сначала откройте опрос')
            try:age=datetime.now(timezone.utc)-datetime.fromisoformat(opened['opened_at']).astimezone(timezone.utc)
            except ValueError:raise HTTPException(409,'Временная метка опроса недействительна')
            if age>timedelta(hours=2):raise HTTPException(409,'Сессия анкеты истекла')
            valid=validate_answers(json.loads(v['content_json']),body.answers)
            hash_=digest({'version':v['id'],'answers':valid})
            previous=db.execute('SELECT * FROM voice_responses_r17 WHERE placement_id=? AND request_id=?',
                                (p['id'],body.request_id)).fetchone()
            if previous:
                if previous['payload_hash']!=hash_:raise HTTPException(409,'Ответ уже отправлен с другим содержимым')
                db.commit();return {'saved':True,'duplicate':True}
            _remaining_today(db,p['id'],'voice_responses_r17',3000)
            db.execute('''INSERT INTO voice_responses_r17(organization_id,store_id,placement_id,version_id,request_id,payload_hash,answers_json,submitted_at)
                VALUES(?,?,?,?,?,?,?,?)''',(p['organization_id'],p['store_id'],p['id'],v['id'],body.request_id,hash_,canonical(valid),now_iso()))
            db.commit();return {'saved':True,'duplicate':False}
        except Exception:db.rollback();raise

    @router.get('/api/admin/r17/insights')
    def insights(slug:str='central',days:int=14,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        return insight_report(db,store,days)

    @router.get('/api/admin/r17/insights.csv')
    def insights_csv(slug:str='central',days:int=14,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal);report=insight_report(db,store,days)
        rows=[]
        for q in report['questions']:
            for choice in q['counts']:
                rows.append({'form_version':q['version_id'],'question_id':q['question_id'],'question':q['title'],
                             'choice':choice['label'],'count':choice['count'],'total':q['responses'],'percent':choice['pct']})
        content=_csv(rows,['form_version','question_id','question','choice','count','total','percent'])
        return Response(content,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="osmanx-voice-insights.csv"','Cache-Control':'no-store'})

    @router.get('/api/admin/r17/actions')
    def actions(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        return {'items':[dict(r) for r in db.execute('SELECT * FROM voice_actions_r17 WHERE store_id=? ORDER BY id DESC LIMIT 150',(store['id'],))]}

    @router.post('/api/admin/r17/actions',status_code=201)
    def create_action(body:ActionCreate,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager');store=visible_store(db,body.slug,principal)
        if len(body.title.strip())<10:raise HTTPException(422,'Опишите действие подробнее')
        req={'store':store['id'],'placement':body.placement_id,'question_id':body.question_id,
             'choice':body.choice,'action_type':body.action_type,'title':body.title.strip()}
        sha=digest(req)
        try:
            _transaction(db)
            previous=db.execute('SELECT * FROM voice_actions_r17 WHERE organization_id=? AND request_id=?',
                                (principal.organization_id,body.request_id)).fetchone()
            if previous:
                if previous['request_hash']!=sha:raise HTTPException(409,'Ключ уже использован для другой задачи')
                db.commit();return {'id':previous['id'],'duplicate':True}
            p=placement_scope(db,body.placement_id,principal)
            if p['store_id']!=store['id']:raise HTTPException(404,'Терминал не относится к выбранному филиалу')
            version=latest_version(db,p)
            questions=json.loads(version['content_json']);q=next((q for q in questions if q['id']==body.question_id),None)
            if not q or q['type']!='choice' or body.choice not in [o['id'] for o in q['options']]:
                raise HTTPException(422,'Вариант ответа не найден')
            rows=db.execute('SELECT answers_json FROM voice_responses_r17 WHERE placement_id=? AND version_id=? ORDER BY id DESC LIMIT 30001',
                            (p['id'],version['id'])).fetchall()
            if len(rows)>30000:raise HTTPException(413,'Для этой анкеты превышен лимит наблюдений')
            total=sum(body.question_id in json.loads(r[0]) for r in rows)
            support=sum(json.loads(r[0]).get(body.question_id)==body.choice for r in rows)
            if support<3:raise HTTPException(409,'Для создания задачи нужно минимум три подтверждённых ответа')
            evidence={'placement_id':p['id'],'version_id':version['id'],'question_id':body.question_id,
                      'choice':body.choice,'support':support,'total':total,'calculated_at':now_iso()}
            now=now_iso()
            cur=db.execute('''INSERT INTO voice_actions_r17(organization_id,store_id,placement_id,version_id,request_id,request_hash,
               question_id,choice,action_type,title,evidence_count,evidence_total,evidence_json,evidence_hash,status,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'new',?,?)''',
               (principal.organization_id,store['id'],p['id'],version['id'],body.request_id,sha,body.question_id,
                body.choice,body.action_type,body.title.strip(),support,total,canonical(evidence),digest(evidence),now,now))
            audit(db,principal,'voice.action.create',str(cur.lastrowid));db.commit()
            return {'id':cur.lastrowid,'duplicate':False,'evidence':evidence}
        except Exception:db.rollback();raise

    @router.patch('/api/admin/r17/actions/{action_id}')
    def update_action(action_id:int,body:ActionUpdate,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        require_role(principal,'owner','manager')
        try:
            _transaction(db)
            row=db.execute('SELECT * FROM voice_actions_r17 WHERE id=? AND organization_id=?',
                           (action_id,principal.organization_id)).fetchone()
            if not row:raise HTTPException(404,'Задача не найдена')
            check_store_access(db,row['store_id'],principal)
            allowed={'new':('investigating','dismissed'),'investigating':('implemented','dismissed'),
                     'implemented':(),'dismissed':()}
            if body.status not in allowed[row['status']]:raise HTTPException(409,'Недопустимый переход статуса')
            db.execute('UPDATE voice_actions_r17 SET status=?,note=?,updated_at=? WHERE id=?',
                       (body.status,body.note,now_iso(),action_id))
            db.execute('INSERT INTO voice_action_history_r17(action_id,old_status,new_status,note,actor_id,changed_at) VALUES(?,?,?,?,?,?)',
                       (action_id,row['status'],body.status,body.note,principal.user_id,now_iso()))
            audit(db,principal,'voice.action.update',str(action_id));db.commit()
            return {'updated':True,'status':body.status,'note':'Задача выполнена в системе, финансовый эффект не доказан.'}
        except Exception:db.rollback();raise

    @router.get('/api/admin/r17/actions/{action_id}/history')
    def action_history(action_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        row=db.execute('SELECT * FROM voice_actions_r17 WHERE id=? AND organization_id=?',(action_id,principal.organization_id)).fetchone()
        if not row:raise HTTPException(404,'Задача не найдена')
        check_store_access(db,row['store_id'],principal)
        return {'items':[dict(x) for x in db.execute('SELECT * FROM voice_action_history_r17 WHERE action_id=? ORDER BY id',(action_id,))]}
    return router
