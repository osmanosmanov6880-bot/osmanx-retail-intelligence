"""R1.2 Retail Desk: verifiable retail operations, not POS execution.

Five modules: receipt lookup/link, coupon lifecycle, campaign spend controls,
7/30/60-day cohort analysis, and owner performance view. No PII storage.
"""
from __future__ import annotations

import csv
import io
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.database import now_iso
from backend.r11 import find_member, valid_code
from backend.retail import safe_spreadsheet_cell
from backend.security import Principal, audit, require_role, visible_store, check_store_access

DDL = """
CREATE TABLE IF NOT EXISTS coupon_fulfillments_r12 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 claim_id INTEGER NOT NULL UNIQUE REFERENCES campaign_claims_r11(id),
 proof_reference TEXT NOT NULL,
 note TEXT NOT NULL,
 actor_user_id INTEGER,
 recorded_at TEXT NOT NULL,
 UNIQUE(organization_id,store_id,proof_reference)
);
CREATE INDEX IF NOT EXISTS ix_r12_fulfill_store ON coupon_fulfillments_r12(store_id,recorded_at);
"""


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(DDL)


def receipt_for(db:sqlite3.Connection, store, source:str, external_id:str):
    sale=db.execute('''SELECT id,store_id,amount_kopeks,source,external_id,occurred_at FROM sales
                      WHERE store_id=? AND source=? AND external_id=?''',
                    (store['id'],source.strip(),external_id.strip())).fetchone()
    if not sale:raise HTTPException(404,'Чек с указанным источником и внешним номером не найден')
    return sale


def claim_for(db:sqlite3.Connection,principal:Principal,store,code:str):
    hash_value=valid_code(code,'OXC-')
    claim=db.execute('''SELECT c.*,ca.title,ca.store_id,ca.unit_cost_kopeks,ca.budget_kopeks,
                  ca.max_claims,ca.starts_on,ca.ends_on,ca.active AS campaign_active
                  FROM campaign_claims_r11 c JOIN campaigns_r11 ca ON ca.id=c.campaign_id
                  WHERE c.coupon_sha256=? AND c.organization_id=? AND ca.store_id=?''',
                  (hash_value,principal.organization_id,store['id'])).fetchone()
    if not claim:raise HTTPException(404,'Купон не найден в этом филиале')
    return claim


def campaign_funnel(db,store_id:int):
    rows=db.execute('''SELECT ca.id,ca.title,ca.reward_description,ca.active,
            ca.starts_on,ca.ends_on,ca.unit_cost_kopeks,ca.budget_kopeks,ca.max_claims,
            COALESCE(SUM(CASE WHEN cl.status='issued' THEN 1 ELSE 0 END),0) issued,
            COALESCE(SUM(CASE WHEN cl.status='redeemed' THEN 1 ELSE 0 END),0) redeemed,
            COALESCE(SUM(CASE WHEN cl.status='cancelled' THEN 1 ELSE 0 END),0) cancelled,
            COALESCE(SUM(CASE WHEN f.id IS NOT NULL THEN 1 ELSE 0 END),0) fulfilled,
            COALESCE(SUM(CASE WHEN cl.status='redeemed' THEN sa.amount_kopeks ELSE 0 END),0) linked_sale_kopeks
          FROM campaigns_r11 ca
          LEFT JOIN campaign_claims_r11 cl ON cl.campaign_id=ca.id
          LEFT JOIN coupon_fulfillments_r12 f ON f.claim_id=cl.id
          LEFT JOIN sales sa ON sa.id=cl.sale_id
          WHERE ca.store_id=? GROUP BY ca.id ORDER BY ca.id DESC LIMIT 200''',(store_id,)).fetchall()
    out=[]
    for r in rows:
        row=dict(r)
        row['claimed']=row['issued']+row['redeemed']
        row['committed_kopeks']=row['claimed']*row['unit_cost_kopeks']
        row['attested_cost_kopeks']=row['fulfilled']*row['unit_cost_kopeks']
        row['budget_available_kopeks']=max(0,row['budget_kopeks']-row['committed_kopeks'])
        row['unfulfilled_redeemed']=row['redeemed']-row['fulfilled']
        row['limit_available']=max(0,min(row['max_claims']-row['claimed'],row['budget_available_kopeks']//row['unit_cost_kopeks']))
        out.append(row)
    return out


def cohort_matrix(db,store_id:int):
    total=db.execute('SELECT COUNT(*) FROM sales WHERE store_id=?',(store_id,)).fetchone()[0]
    rows=db.execute('''SELECT l.member_id,s.id,s.amount_kopeks,s.occurred_at
      FROM loyalty_receipts_r11 l JOIN sales s ON s.id=l.sale_id
      JOIN loyalty_members_r11 m ON m.id=l.member_id AND m.status='active'
      WHERE l.store_id=? ORDER BY l.member_id,s.occurred_at,s.id LIMIT 100001''',(store_id,)).fetchall()
    if len(rows)>100000:raise HTTPException(413,'Слишком большой период: сократите набор данных')
    by_member=defaultdict(list)
    for r in rows:
        try:
            dt=datetime.fromisoformat(r['occurred_at'])
            if dt.tzinfo is None:continue
            by_member[r['member_id']].append((dt.astimezone(timezone.utc),r['amount_kopeks']))
        except (ValueError,TypeError):continue
    windows=(7,30,60); now=datetime.now(timezone.utc)
    overall={n:{'matured':0,'repeated':0} for n in windows}
    buckets=defaultdict(lambda:{'members':0,'receipt_count':0,'linked_revenue_kopeks':0,
                                'periods':{n:{'matured':0,'repeated':0} for n in windows}})
    repeats=0
    for purchases in by_member.values():
        purchases.sort(key=lambda x:x[0]); first=purchases[0][0]
        month=first.strftime('%Y-%m'); b=buckets[month]
        b['members']+=1;b['receipt_count']+=len(purchases)
        b['linked_revenue_kopeks']+=sum(x[1] for x in purchases)
        if len(purchases)>1:repeats+=1
        for n in windows:
            if first+timedelta(days=n)>now:continue
            b['periods'][n]['matured']+=1;overall[n]['matured']+=1
            if any(first<t<=first+timedelta(days=n) for t,_ in purchases[1:]):
                b['periods'][n]['repeated']+=1;overall[n]['repeated']+=1
    def rounded(m):return round(m['repeated']*100/m['matured'],1) if m['matured'] else None
    return {'store_id':store_id,'members_with_receipts':len(by_member),'repeat_members':repeats,
        'linked_receipts':sum(len(v) for v in by_member.values()),'all_receipts':total,
        'coverage_pct':round(sum(len(v) for v in by_member.values())*100/total,1) if total else None,
        'windows':[{'days':n,**m,'rate_pct':rounded(m)} for n,m in overall.items()],
        'cohorts':[{'month':month,'members':b['members'],'receipt_count':b['receipt_count'],
                   'linked_revenue_kopeks':b['linked_revenue_kopeks'],
                   'windows':[{'days':n,**m,'rate_pct':rounded(m)} for n,m in b['periods'].items()]}
                   for month,b in sorted(buckets.items(),reverse=True)][:18],
        'warnings':['Это только участники с добровольной картой и вручную связанными чеками.',
                    'Доли рассчитаны только по зрелым когортам; незрелые не считаются отказами.',
                    'Изменение метрики не доказывает эффект кампании без контрольного сравнения.',
                    'Периоды 7, 30 и 60 суток рассчитываются по UTC.']}


def executive(db,store,days:int):
    if not 7<=days<=90:raise HTTPException(422,'Период от 7 до 90 дней')
    since=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
    sid=store['id']
    sales=db.execute('''SELECT COUNT(*) n,COALESCE(SUM(amount_kopeks),0) amount FROM sales
                   WHERE store_id=? AND occurred_at>=?''',(sid,since)).fetchone()
    visits=db.execute('''SELECT COALESCE(SUM(quantity),0) n FROM visits WHERE store_id=? AND occurred_at>=?''',
                      (sid,since)).fetchone()['n']
    sources=db.execute('''SELECT source, SUM(quantity) total FROM visits WHERE store_id=? AND occurred_at>=?
                   GROUP BY source ORDER BY total DESC''',(sid,since)).fetchall()
    demand=db.execute('''SELECT COUNT(*) FROM demand WHERE store_id=? AND status IN ('open','located','notified')''',(sid,)).fetchone()[0]
    open_assistance=None
    has_assist=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='assistance_requests_r07'").fetchone()
    if has_assist:
        open_assistance=db.execute("""SELECT COUNT(*) FROM assistance_requests_r07
                 WHERE store_id=? AND status IN ('open','accepted')""",(sid,)).fetchone()[0]
    campaigns=campaign_funnel(db,sid)
    cohorts=cohort_matrix(db,sid)
    warnings=['Показатели учитывают только зарегистрированные чеки и посещения.',
              'Выполнение бонуса подтверждается сотрудником, а не банковской или POS-системой.',
              'Подтверждённые продажи участников не равны дополнительным продажам программы.']
    if len(sources)>1:warnings.append('Несколько источников трафика: убедитесь в отсутствии двойного подсчёта.')
    if any(r['source'].startswith('demo') for r in sources):warnings.append('В данных есть демонстрационные посещения.')
    return {'slug':store['slug'],'days':days,'report_time':now_iso(),
        'sales_count':sales['n'],'receipt_revenue_kopeks':sales['amount'],
        'recorded_visits':visits,'visits_by_source':[dict(x) for x in sources],
        'receipt_conversion_pct':round(sales['n']*100/visits,2) if visits else None,
        'active_demand_requests':demand,'campaigns':campaigns,'retention':cohorts,
        'open_assistance':open_assistance,'warnings':warnings,'note':'Операционный отчёт, не аудит чистой прибыли.'}

class ReceiptLookup(BaseModel):
    slug:str='central'
    source:str=Field(min_length=1,max_length=80)
    external_id:str=Field(min_length=1,max_length=200)

class CashierLink(ReceiptLookup):
    member_code:str=Field(min_length=36,max_length=36)

class CouponCode(BaseModel):
    slug:str='central'
    coupon_code:str=Field(min_length=36,max_length=36)

class Fulfill(CouponCode):
    proof_reference:str=Field(min_length=6,max_length=100)
    note:str=Field(min_length=6,max_length=300)


def build_router(admin_dep,db_dep):
    router=APIRouter(prefix='/api/admin/r12',tags=['Retail Operations R1.2'])

    @router.post('/cashier/receipt')
    def lookup(data:ReceiptLookup,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,data.slug,principal)
        sale=receipt_for(db,store,data.source,data.external_id)
        linked=db.execute('SELECT id FROM loyalty_receipts_r11 WHERE sale_id=?',(sale['id'],)).fetchone()
        return {'sale':dict(sale),'linked':bool(linked),'note':'Поиск только существующего чека. Без создания продажи.'}

    @router.post('/cashier/link',status_code=201)
    def link(data:CashierLink,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,data.slug,principal)
        member=find_member(db,principal.organization_id,data.member_code)
        try:
            db.execute('BEGIN IMMEDIATE')
            sale=receipt_for(db,store,data.source,data.external_id)
            other=db.execute('SELECT member_id FROM loyalty_receipts_r11 WHERE sale_id=?',(sale['id'],)).fetchone()
            if other:
                if other['member_id']!=member['id']:raise HTTPException(409,'Чек закреплён за другой картой')
                db.commit();return {'linked':True,'duplicate':True,'sale_id':sale['id']}
            db.execute('''INSERT INTO loyalty_receipts_r11(organization_id,member_id,store_id,sale_id,linked_at)
                          VALUES(?,?,?,?,?)''',(principal.organization_id,member['id'],store['id'],sale['id'],now_iso()))
            audit(db,principal,'r12.cashier.link',str(sale['id']))
            db.commit();return {'linked':True,'duplicate':False,'sale_id':sale['id']}
        except sqlite3.IntegrityError as exc:
            db.rollback();raise HTTPException(409,'Конфликт привязки чека') from exc
        except Exception:
            db.rollback();raise

    @router.post('/coupons/inspect')
    def inspect(data:CouponCode,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,data.slug,principal)
        cl=claim_for(db,principal,store,data.coupon_code)
        proof=db.execute('SELECT id,proof_reference,recorded_at FROM coupon_fulfillments_r12 WHERE claim_id=?',(cl['id'],)).fetchone()
        today=datetime.now(timezone.utc).date().isoformat()
        return {'campaign_id':cl['campaign_id'],'title':cl['title'],'status':cl['status'],
            'receipt_verified':cl['sale_id'] is not None, 'fulfilled':bool(proof),
            'fulfillment':dict(proof) if proof else None,
            'can_attest_fulfillment':cl['status']=='redeemed' and not proof,
            'can_cancel':cl['status']=='issued',
            'eligible_today':cl['starts_on']<=today<=cl['ends_on'],
            'note':'Проверка чека не является подтверждением выдачи подарка.'}

    @router.post('/coupons/cancel')
    def cancel(data:CouponCode,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,data.slug,principal)
        try:
            db.execute('BEGIN IMMEDIATE')
            cl=claim_for(db,principal,store,data.coupon_code)
            if cl['status']=='cancelled':
                db.commit();return {'cancelled':True,'duplicate':True}
            if cl['status']!='issued':raise HTTPException(409,'Подтверждённый по чеку бонус нельзя отменить')
            db.execute("UPDATE campaign_claims_r11 SET status='cancelled' WHERE id=?",(cl['id'],))
            audit(db,principal,'r12.coupon.cancel',str(cl['id']))
            db.commit();return {'cancelled':True,'duplicate':False,'campaign_id':cl['campaign_id']}
        except Exception:
            db.rollback();raise

    @router.post('/coupons/fulfill',status_code=201)
    def fulfill(data:Fulfill,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,data.slug,principal)
        try:
            db.execute('BEGIN IMMEDIATE')
            cl=claim_for(db,principal,store,data.coupon_code)
            existing=db.execute('SELECT * FROM coupon_fulfillments_r12 WHERE claim_id=?',(cl['id'],)).fetchone()
            if existing:
                if existing['proof_reference']!=data.proof_reference.strip() or existing['note']!=data.note.strip():
                    raise HTTPException(409,'Этот бонус уже отмечен другим подтверждением')
                db.commit();return {'fulfilled':True,'duplicate':True,'id':existing['id']}
            if cl['status']!='redeemed' or not cl['sale_id']:
                raise HTTPException(409,'Сначала требуется проверить купон и кассовый чек в R1.1')
            cur=db.execute('''INSERT INTO coupon_fulfillments_r12
              (organization_id,store_id,claim_id,proof_reference,note,actor_user_id,recorded_at)
              VALUES(?,?,?,?,?,?,?)''',
              (principal.organization_id,store['id'],cl['id'],data.proof_reference.strip(),data.note.strip(),
               None if principal.demo else principal.user_id,now_iso()))
            audit(db,principal,'r12.coupon.fulfill',str(cl['id']))
            db.commit();return {'fulfilled':True,'duplicate':False,'id':cur.lastrowid,
                'disclaimer':'Факт выдачи подтверждён сотрудником, но не интегрированной кассой.'}
        except sqlite3.IntegrityError as exc:
            db.rollback();raise HTTPException(409,'Номер подтверждения уже использован в этом филиале') from exc
        except Exception:
            db.rollback();raise

    @router.get('/campaigns/controls')
    def campaigns(slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        return {'items':campaign_funnel(db,store['id']),
                'warnings':['Резерв бюджета не равен списанным деньгам.',
                            'Стоимость вручённого бонуса — оценка по плановой цене, не подтверждённый расход.',
                            'Оборот связанных чеков не является доказательством роста выручки.']}

    @router.get('/retention')
    def retention(slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        return cohort_matrix(db,store['id'])

    @router.get('/executive')
    def executive_api(slug:str='central',days:int=30,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        return executive(db,store,days)

    @router.get('/executive/export')
    def export(slug:str='central',days:int=30,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        report=executive(db,store,days)
        out=io.StringIO();writer=csv.writer(out,lineterminator='\n')
        writer.writerow(['Показатель','Значение'])
        for key in ('slug','days','sales_count','receipt_revenue_kopeks','recorded_visits',
                    'receipt_conversion_pct','active_demand_requests'):
            writer.writerow([safe_spreadsheet_cell(key),safe_spreadsheet_cell(report[key])])
        for x in report['campaigns']:
            writer.writerow([safe_spreadsheet_cell('Кампания: '+x['title']),safe_spreadsheet_cell(x['attested_cost_kopeks'])])
        return Response('\ufeff'+out.getvalue(),media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition':'attachment; filename="osmanx-r12-executive.csv"',
                                 'Cache-Control':'no-store'})
    return router
