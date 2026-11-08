"""OSMANX R1.1 Growth Intelligence.

Five real but narrowly scoped workflows: anonymous opt-in memberships, receipt
linking, capped campaigns, repeat-purchase cohorts, assortment opportunities.
No PII collection, message delivery, POS discounts or automated purchases.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from backend.database import now_iso
from backend.security import Principal, audit, check_store_access, require_role, visible_store

DDL = """
CREATE TABLE IF NOT EXISTS loyalty_members_r11 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 home_store_id INTEGER NOT NULL REFERENCES stores(id),
 code_sha256 TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','revoked')),
 consent_at TEXT NOT NULL, created_at TEXT NOT NULL, revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_r11_members_org ON loyalty_members_r11(organization_id,status,id);
CREATE TABLE IF NOT EXISTS loyalty_receipts_r11 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 member_id INTEGER NOT NULL REFERENCES loyalty_members_r11(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 sale_id INTEGER NOT NULL UNIQUE REFERENCES sales(id),
 linked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_r11_loyalty_receipts_member ON loyalty_receipts_r11(member_id,linked_at);
CREATE TABLE IF NOT EXISTS campaigns_r11 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 title TEXT NOT NULL, reward_description TEXT NOT NULL,
 unit_cost_kopeks INTEGER NOT NULL CHECK(unit_cost_kopeks>0),
 budget_kopeks INTEGER NOT NULL CHECK(budget_kopeks>0),
 max_claims INTEGER NOT NULL CHECK(max_claims BETWEEN 1 AND 100000),
 min_spend_kopeks INTEGER NOT NULL CHECK(min_spend_kopeks>=0),
 starts_on TEXT NOT NULL, ends_on TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_r11_campaigns_scope ON campaigns_r11(store_id,id);
CREATE TABLE IF NOT EXISTS campaign_claims_r11 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 campaign_id INTEGER NOT NULL REFERENCES campaigns_r11(id),
 member_id INTEGER REFERENCES loyalty_members_r11(id),
 coupon_sha256 TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL CHECK(status IN ('issued','redeemed','cancelled')),
 sale_id INTEGER UNIQUE REFERENCES sales(id),
 issued_at TEXT NOT NULL, redeemed_at TEXT,
 UNIQUE(campaign_id,member_id)
);
CREATE INDEX IF NOT EXISTS ix_r11_claims_campaign ON campaign_claims_r11(campaign_id,status);
"""


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(DDL)


def digest(code: str) -> str:
    # 128-bit random codes: a bare hash is safe against guessing, unlike a PIN.
    return hashlib.sha256(code.strip().upper().encode('ascii')).hexdigest()


def valid_code(code: str, prefix: str) -> str:
    value = code.strip().upper()
    if not value.startswith(prefix) or len(value) != len(prefix) + 32:
        raise HTTPException(422, 'Неверный формат кода')
    try:
        int(value[len(prefix):], 16)
    except ValueError as exc:
        raise HTTPException(422, 'Неверный формат кода') from exc
    return digest(value)


def find_member(db: sqlite3.Connection, org: int, code: str):
    row = db.execute('SELECT * FROM loyalty_members_r11 WHERE organization_id=? AND code_sha256=?',
                     (org, valid_code(code, 'OXM-'))).fetchone()
    if not row or row['status'] != 'active':
        raise HTTPException(404, 'Карта не найдена или отозвана')
    return row


def scoped_campaign(db: sqlite3.Connection, cid: int, principal: Principal):
    row = db.execute('SELECT * FROM campaigns_r11 WHERE id=? AND organization_id=?',
                     (cid, principal.organization_id)).fetchone()
    if not row:
        raise HTTPException(404, 'Кампания не найдена')
    check_store_access(db, row['store_id'], principal)
    return row


def scoped_sale(db: sqlite3.Connection, sale_id: int, principal: Principal):
    sale = db.execute('''SELECT s.*,st.organization_id FROM sales s JOIN stores st ON st.id=s.store_id
                         WHERE s.id=? AND st.organization_id=?''',
                      (sale_id, principal.organization_id)).fetchone()
    if not sale:
        raise HTTPException(404, 'Чек не найден')
    check_store_access(db, sale['store_id'], principal)
    return sale


def _begin(db):
    db.execute('BEGIN IMMEDIATE')


def _fail(db, exc):
    db.rollback()
    raise exc


class MemberIssue(BaseModel):
    slug: str = 'central'
    explicit_opt_in: bool = False


class MemberLink(BaseModel):
    member_code: str = Field(min_length=36, max_length=36)
    sale_id: int = Field(gt=0)


class CampaignCreate(BaseModel):
    slug: str = 'central'
    title: str = Field(min_length=3, max_length=100)
    reward_description: str = Field(min_length=3, max_length=180)
    unit_cost_kopeks: int = Field(gt=0, le=10000000)
    budget_kopeks: int = Field(gt=0, le=1000000000)
    max_claims: int = Field(ge=1, le=100000)
    min_spend_kopeks: int = Field(ge=0, le=100000000)
    starts_on: date
    ends_on: date

    @model_validator(mode='after')
    def check_dates(self):
        if self.ends_on < self.starts_on or (self.ends_on-self.starts_on).days > 120:
            raise ValueError('Кампания должна длиться от 1 до 121 дня')
        if self.budget_kopeks < self.unit_cost_kopeks:
            raise ValueError('Бюджет меньше стоимости одного бонуса')
        return self


class CampaignClaim(BaseModel):
    member_code: str = Field(min_length=36, max_length=36)


class CampaignRedeem(BaseModel):
    coupon_code: str = Field(min_length=36, max_length=36)
    sale_id: int = Field(gt=0)


class CampaignActive(BaseModel):
    active: bool


def _summary(db, camp):
    rows = db.execute('SELECT status,COUNT(*) n FROM campaign_claims_r11 WHERE campaign_id=? GROUP BY status',
                      (camp['id'],)).fetchall()
    counts={r['status']:r['n'] for r in rows}
    occupied = counts.get('issued', 0) + counts.get('redeemed', 0)
    return {**dict(camp), 'issued':counts.get('issued',0),'redeemed':counts.get('redeemed',0),
            'cancelled':counts.get('cancelled',0), 'reserved_kopeks':occupied*camp['unit_cost_kopeks'],
            'remaining_budget_kopeks':max(0,camp['budget_kopeks']-occupied*camp['unit_cost_kopeks'])}


def retention(db: sqlite3.Connection, org: int, store_id: int | None):
    scope='AND r.store_id=?' if store_id is not None else ''
    params=(org,store_id) if store_id is not None else (org,)
    receipts=db.execute(f'''SELECT r.member_id,s.id sale_id,s.amount_kopeks,s.occurred_at
           FROM loyalty_receipts_r11 r JOIN sales s ON s.id=r.sale_id
           WHERE r.organization_id=? {scope} ORDER BY r.member_id,s.occurred_at,s.id''',params).fetchall()
    histories=defaultdict(list)
    for row in receipts:
        try:
            ts=datetime.fromisoformat(row['occurred_at'])
            if ts.tzinfo is None:continue
            histories[row['member_id']].append((ts.astimezone(timezone.utc),row))
        except (TypeError,ValueError):
            continue
    groups=defaultdict(lambda:{'first_buyers':0,'matured':0,'repeat_within_30d':0})
    now=datetime.now(timezone.utc)
    repeat_buyers=0
    for linked in histories.values():
        linked.sort(key=lambda x:x[0]);first=linked[0][0]
        month=first.strftime('%Y-%m');groups[month]['first_buyers']+=1
        if len(linked)>1:repeat_buyers+=1
        if first+timedelta(days=30) <= now:
            groups[month]['matured']+=1
            if any(first<ts<=first+timedelta(days=30) for ts,_ in linked[1:]):
                groups[month]['repeat_within_30d']+=1
    all_sales=db.execute('SELECT COUNT(*) FROM sales s JOIN stores st ON st.id=s.store_id WHERE st.organization_id=?'+
                         (' AND s.store_id=?' if store_id is not None else ''),params).fetchone()[0]
    cohorts=[{'month':month,**row,'repeat_rate_30d_percent':
              round(row['repeat_within_30d']*100/row['matured'],1) if row['matured'] else None}
             for month,row in sorted(groups.items(),reverse=True)][:12]
    return {'linked_receipts':sum(len(x) for x in histories.values()),
            'all_receipts':all_sales,'coverage_percent':round(sum(map(len,histories.values()))*100/all_sales,1) if all_sales else None,
            'observed_members':len(histories),'observed_repeat_members':repeat_buyers,
            'cohorts':cohorts, 'warnings':[
                'Учитываются только добровольные участники, чьи чеки были привязаны сотрудником.',
                'Когорты моложе 30 дней не включены в знаменатель 30-дневного удержания.',
                'Это не удержание всей аудитории и не доказанный эффект программы лояльности.',
                'Месячные когорты рассчитаны по UTC.'
            ]}


def assortment(db: sqlite3.Connection, store, days: int):
    if days<7 or days>90:raise HTTPException(422,'Период от 7 до 90 дней')
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
    inventory=db.execute('SELECT sku,product,size,color,quantity FROM inventory WHERE store_id=? LIMIT 10001',
                         (store['id'],)).fetchall()
    if len(inventory)>10000:raise HTTPException(413,'Слишком много SKU')
    by_key=defaultdict(list)
    def norm(v):return ' '.join((v or '').strip().casefold().split())
    by_sku={}
    for item in inventory:
        by_key[(norm(item['product']),norm(item['size']),norm(item['color']))].append(item['sku'])
        by_sku[item['sku']]=dict(item)
    requests=db.execute('SELECT product,size,color,status FROM demand WHERE store_id=? AND created_at>=? LIMIT 30001',
                        (store['id'],cutoff)).fetchall()
    if len(requests)>30000:raise HTTPException(413,'Слишком много запросов')
    demand_by_sku=Counter();ambiguous=0
    for r in requests:
        if r['status'] not in ('open','located','notified'):continue
        skus=set(by_key.get((norm(r['product']),norm(r['size']),norm(r['color'])),[]))
        if len(skus)==1:demand_by_sku[next(iter(skus))]+=1
        else:ambiguous+=1
    items=db.execute('''SELECT sku,COALESCE(SUM(quantity),0) units,
                       COALESCE(SUM(quantity*unit_revenue_kopeks),0) revenue
                       FROM sale_items WHERE store_id=? AND recorded_at>=? GROUP BY sku LIMIT 10001''',
                     (store['id'],cutoff)).fetchall()
    if len(items)>10000:raise HTTPException(413,'Слишком много позиций')
    sold={r['sku']:dict(r) for r in items}
    result=[]
    for sku,row in by_sku.items():
        requests_count=demand_by_sku.get(sku,0)
        sales_count=sold.get(sku,{}).get('units',0)
        available=row['quantity']
        if requests_count>=3 and available==0:
            signal='check_restock';label='Проверить дозакупку'
        elif requests_count>=3 and available>0:
            signal='check_visibility';label='Проверить наличие на полке'
        elif sales_count>=3 and available==0:
            signal='check_availability';label='Проверить доступность'
        else:continue
        result.append({**row,'requests':requests_count,'sold_units':sales_count,
                       'receipt_item_revenue_kopeks':sold.get(sku,{}).get('revenue',0),
                       'signal':signal,'action':label,'evidence':'Запросы и подтверждённые товарные строки чеков за выбранный период.'})
    result.sort(key=lambda x:(-x['requests'],-x['sold_units'],x['sku']))
    return {'days':days,'items':result[:100],'unresolved_demand':ambiguous,
            'warnings':['Советы не запускают закупку автоматически и не гарантируют прибыль.',
                        'Количество товара — учётный остаток, а не гарантированно свободный остаток после резервов.',
                        'Продажи учитываются только при наличии товарных строк чеков.',
                        'Неоднозначные запросы исключены; сначала уточните артикул.']}


def build_router(admin_dep, db_dep) -> APIRouter:
    router = APIRouter(prefix='/api/admin/r11', tags=['Growth Intelligence R1.1'])

    @router.get('/members')
    def members(slug: str = 'central', principal: Principal = Depends(admin_dep),
                db: sqlite3.Connection = Depends(db_dep)):
        store=visible_store(db,slug,principal)
        rows=db.execute('''SELECT m.id,m.status,m.consent_at,m.created_at,m.revoked_at,
                 s.name AS home_store,COUNT(l.id) AS linked_receipts
                 FROM loyalty_members_r11 m JOIN stores s ON s.id=m.home_store_id
                 LEFT JOIN loyalty_receipts_r11 l ON l.member_id=m.id
                 WHERE m.organization_id=? AND m.home_store_id=?
                 GROUP BY m.id ORDER BY m.id DESC LIMIT 200''',
                        (principal.organization_id,store['id'])).fetchall()
        return {'items':[dict(r) for r in rows],
                'privacy':'Имена, телефоны и адреса не сохраняются. Код карты выдаётся один раз.'}

    @router.post('/members',status_code=201)
    def issue_member(data: MemberIssue, principal: Principal = Depends(admin_dep),
                     db: sqlite3.Connection = Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,data.slug,principal)
        if not data.explicit_opt_in:
            raise HTTPException(422,'Необходимо добровольное согласие покупателя')
        code='OXM-'+secrets.token_hex(16).upper()
        timestamp=now_iso()
        try:
            _begin(db)
            cur=db.execute('''INSERT INTO loyalty_members_r11
              (organization_id,home_store_id,code_sha256,consent_at,created_at)
              VALUES(?,?,?,?,?)''',(principal.organization_id,store['id'],digest(code),timestamp,timestamp))
            audit(db,principal,'r11.member.issue',str(cur.lastrowid))
            db.commit()
            return {'id':cur.lastrowid,'member_code':code,'created_at':timestamp,
                    'message':'Сохраните код сейчас: повторно он не показывается. Это не карта со скидкой.'}
        except Exception as exc:_fail(db,exc)

    @router.delete('/members/{member_id}')
    def revoke_member(member_id: int, principal: Principal = Depends(admin_dep),
                      db: sqlite3.Connection = Depends(db_dep)):
        require_role(principal,'owner','manager')
        row=db.execute('SELECT * FROM loyalty_members_r11 WHERE id=? AND organization_id=?',
                       (member_id,principal.organization_id)).fetchone()
        if not row:raise HTTPException(404,'Участник не найден')
        check_store_access(db,row['home_store_id'],principal)
        try:
            _begin(db)
            if row['status']=='revoked':
                db.commit();return {'revoked':True,'already_revoked':True}
            db.execute('DELETE FROM loyalty_receipts_r11 WHERE member_id=?',(member_id,))
            db.execute("DELETE FROM campaign_claims_r11 WHERE member_id=? AND status='issued'",(member_id,))
            db.execute("UPDATE campaign_claims_r11 SET member_id=NULL WHERE member_id=? AND status IN ('redeemed','cancelled')",(member_id,))
            db.execute('''UPDATE loyalty_members_r11 SET status='revoked',code_sha256=?,revoked_at=? WHERE id=?''',
                       (digest('REVOKED-'+secrets.token_hex(16)),now_iso(),member_id))
            audit(db,principal,'r11.member.revoke',str(member_id))
            db.commit();return {'revoked':True,'linked_receipts_erased':True}
        except Exception as exc:_fail(db,exc)

    @router.post('/receipts',status_code=201)
    def link_receipt(data: MemberLink, principal: Principal = Depends(admin_dep),
                     db: sqlite3.Connection = Depends(db_dep)):
        require_role(principal,'owner','manager')
        member=find_member(db,principal.organization_id,data.member_code)
        sale=scoped_sale(db,data.sale_id,principal)
        try:
            _begin(db)
            current=db.execute('SELECT * FROM loyalty_receipts_r11 WHERE sale_id=?',(data.sale_id,)).fetchone()
            if current:
                if current['member_id']!=member['id']:raise HTTPException(409,'Чек уже закреплён за другой картой')
                db.commit();return {'linked':True,'duplicate':True,'member_id':member['id'],'sale_id':sale['id']}
            db.execute('''INSERT INTO loyalty_receipts_r11(organization_id,member_id,store_id,sale_id,linked_at)
              VALUES(?,?,?,?,?)''',(principal.organization_id,member['id'],sale['store_id'],sale['id'],now_iso()))
            audit(db,principal,'r11.receipt.link',str(sale['id']))
            db.commit();return {'linked':True,'duplicate':False,'member_id':member['id'],'sale_id':sale['id']}
        except Exception as exc:_fail(db,exc)

    @router.get('/receipts')
    def receipts(slug: str='central', principal: Principal = Depends(admin_dep),
                 db: sqlite3.Connection = Depends(db_dep)):
        store=visible_store(db,slug,principal)
        rows=db.execute('''SELECT r.sale_id,r.member_id,r.linked_at,s.amount_kopeks,s.occurred_at
              FROM loyalty_receipts_r11 r JOIN sales s ON s.id=r.sale_id
              WHERE r.organization_id=? AND r.store_id=? ORDER BY r.id DESC LIMIT 100''',
                        (principal.organization_id,store['id'])).fetchall()
        return {'items':[dict(x) for x in rows],
                'note':'Привязанные чеки — подмножество всех продаж. Привязка сама по себе не начисляет скидку.'}

    @router.get('/retention')
    def cohorts(slug: str='central',all_stores:bool=False,principal:Principal=Depends(admin_dep),
                db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        if all_stores:
            require_role(principal,'owner')
        return retention(db,principal.organization_id,None if all_stores else store['id'])

    @router.get('/campaigns')
    def campaigns(slug: str='central',principal:Principal=Depends(admin_dep),
                  db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        rows=db.execute('SELECT * FROM campaigns_r11 WHERE organization_id=? AND store_id=? ORDER BY id DESC LIMIT 100',
                        (principal.organization_id,store['id'])).fetchall()
        return {'items':[_summary(db,x) for x in rows],
                'note':'Сумма резервирования — плановые затраты на бонусы, а не фактический расход или скидка в кассе.'}

    @router.post('/campaigns',status_code=201)
    def create_campaign(data:CampaignCreate,principal:Principal=Depends(admin_dep),
                        db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,data.slug,principal)
        try:
            _begin(db)
            cur=db.execute('''INSERT INTO campaigns_r11(organization_id,store_id,title,reward_description,
              unit_cost_kopeks,budget_kopeks,max_claims,min_spend_kopeks,starts_on,ends_on,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
              (principal.organization_id,store['id'],data.title.strip(),data.reward_description.strip(),
               data.unit_cost_kopeks,data.budget_kopeks,data.max_claims,data.min_spend_kopeks,
               data.starts_on.isoformat(),data.ends_on.isoformat(),now_iso()))
            audit(db,principal,'r11.campaign.create',str(cur.lastrowid))
            db.commit();return {'id':cur.lastrowid,'created':True}
        except Exception as exc:_fail(db,exc)

    @router.patch('/campaigns/{campaign_id}')
    def toggle_campaign(campaign_id:int,body:CampaignActive,principal:Principal=Depends(admin_dep),
                        db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        camp=scoped_campaign(db,campaign_id,principal)
        db.execute('UPDATE campaigns_r11 SET active=? WHERE id=?',(int(body.active),camp['id']))
        audit(db,principal,'r11.campaign.toggle',str(camp['id']))
        db.commit();return {'id':camp['id'],'active':body.active}

    @router.post('/campaigns/{campaign_id}/claim',status_code=201)
    def claim_campaign(campaign_id:int,data:CampaignClaim,principal:Principal=Depends(admin_dep),
                       db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        member=find_member(db,principal.organization_id,data.member_code)
        try:
            _begin(db)
            camp=scoped_campaign(db,campaign_id,principal)
            today=datetime.now(timezone.utc).date().isoformat()
            if not camp['active'] or not (camp['starts_on']<=today<=camp['ends_on']):
                raise HTTPException(409,'Кампания сейчас не активна')
            if db.execute('SELECT 1 FROM campaign_claims_r11 WHERE campaign_id=? AND member_id=?',
                          (camp['id'],member['id'])).fetchone():
                raise HTTPException(409,'Участнику уже выдавали бонус этой кампании')
            issued=db.execute('''SELECT COUNT(*) FROM campaign_claims_r11
                WHERE campaign_id=? AND status IN ('issued','redeemed')''',(camp['id'],)).fetchone()[0]
            if issued>=camp['max_claims'] or (issued+1)*camp['unit_cost_kopeks']>camp['budget_kopeks']:
                raise HTTPException(409,'Лимит бонусов или бюджет исчерпан')
            code='OXC-'+secrets.token_hex(16).upper()
            cur=db.execute('''INSERT INTO campaign_claims_r11(organization_id,campaign_id,member_id,
                coupon_sha256,status,issued_at) VALUES(?,?,?,?,?,?)''',
                (principal.organization_id,camp['id'],member['id'],digest(code),'issued',now_iso()))
            audit(db,principal,'r11.campaign.claim',str(cur.lastrowid))
            db.commit();return {'id':cur.lastrowid,'coupon_code':code,
                                'message':'Код одноразовый. Выдача бонуса в кассе не выполняется.'}
        except Exception as exc:_fail(db,exc)

    @router.post('/campaigns/{campaign_id}/redeem')
    def redeem_campaign(campaign_id:int,data:CampaignRedeem,principal:Principal=Depends(admin_dep),
                        db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        sale=scoped_sale(db,data.sale_id,principal)
        try:
            _begin(db)
            camp=scoped_campaign(db,campaign_id,principal)
            if sale['store_id']!=camp['store_id']:
                raise HTTPException(422,'Чек относится к другому филиалу')
            claim=db.execute('''SELECT * FROM campaign_claims_r11 WHERE campaign_id=? AND coupon_sha256=?''',
                             (camp['id'],valid_code(data.coupon_code,'OXC-'))).fetchone()
            if not claim or claim['status']!='issued':
                raise HTTPException(409,'Код не найден или уже использован')
            receipt=db.execute('SELECT member_id FROM loyalty_receipts_r11 WHERE sale_id=?',(sale['id'],)).fetchone()
            if not receipt or receipt['member_id']!=claim['member_id']:
                raise HTTPException(422,'Чек должен быть привязан к этой карте участника')
            if sale['amount_kopeks']<camp['min_spend_kopeks']:
                raise HTTPException(422,'Сумма чека ниже установленного минимума')
            if sale['occurred_at'][:10]<camp['starts_on'] or sale['occurred_at'][:10]>camp['ends_on']:
                raise HTTPException(422,'Чек вне периода кампании')
            db.execute("UPDATE campaign_claims_r11 SET status='redeemed',sale_id=?,redeemed_at=? WHERE id=?",
                       (sale['id'],now_iso(),claim['id']))
            audit(db,principal,'r11.campaign.redeem',str(claim['id']))
            db.commit();return {'redeemed':True,'sale_id':sale['id'],
              'note':'Запись о проверке чека, не автоматическая выдача подарка или применение скидки.'}
        except sqlite3.IntegrityError as exc:
            db.rollback();raise HTTPException(409,'Чек уже использовался для другого бонуса') from exc
        except Exception as exc:_fail(db,exc)

    @router.get('/campaigns/{campaign_id}/effect')
    def campaign_effect(campaign_id:int,principal:Principal=Depends(admin_dep),
                        db:sqlite3.Connection=Depends(db_dep)):
        camp=scoped_campaign(db,campaign_id,principal)
        counts=_summary(db,camp)
        sums=db.execute('''SELECT COUNT(*) as receipts,COALESCE(SUM(s.amount_kopeks),0) as revenue
                 FROM campaign_claims_r11 c JOIN sales s ON s.id=c.sale_id
                 WHERE c.campaign_id=? AND c.status='redeemed' ''',(camp['id'],)).fetchone()
        return {'campaign':counts,'verified_receipts':sums['receipts'],
                'linked_receipt_revenue_kopeks':sums['revenue'],
                'estimated_reward_cost_kopeks':counts['redeemed']*camp['unit_cost_kopeks'],
                'net_profit_kopeks':None,'roi_percent':None,
                'warnings':['Выручка по связанным чекам не равна дополнительной выручке от кампании.',
                 'Затраты бонусов оценочные. Нет факта списания в кассе или стоимости обслуживания.',
                 'Без контрольной группы и себестоимости нельзя вычислить прирост прибыли или ROI.']}

    @router.get('/assortment')
    def assortment_report(slug:str='central',days:int=30,principal:Principal=Depends(admin_dep),
                          db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        return assortment(db,store,days)

    return router
