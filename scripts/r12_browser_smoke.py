"""Chromium acceptance for Retail Desk R1.2 via authenticated TestClient bridge.
Does not navigate to public network or deploy anything.
"""
from __future__ import annotations
import os
import shutil
import sys
import tempfile
from pathlib import Path
from datetime import datetime,timedelta,timezone

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
QA=ROOT/'qa'
QA.mkdir(exist_ok=True)


def content():
    html=(ROOT/'frontend/retail_desk.html').read_text()
    css=(ROOT/'frontend/retail_desk.css').read_text()
    html=html.replace('<link rel="stylesheet" href="/static/retail_desk.css">','')
    html=html.replace('<script type="module" src="/static/retail_desk.js"></script>','')
    return html.replace('</head>',f'<style>{css}</style></head>')


def open_page(browser,client,width,height):
    p=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
    errors=[]
    p.on('pageerror',lambda error:errors.append(str(error)))
    def api_call(method,path,payload,headers):
        response=client.request(method,path,json=payload,headers=headers or {}) if payload is not None else client.request(method,path,headers=headers or {})
        try:data=response.json()
        except ValueError:data={'detail':response.text}
        return {'status':response.status_code,'body':data}
    p.expose_function('__api_call',api_call)
    p.set_content(content(),wait_until='domcontentloaded',timeout=10000)
    p.evaluate('''() => {const data=new Map([['osmanx_admin_token','demo']]);
       window.__OSMANX_SESSION__={getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};
       window.fetch=async(path,opts={})=>{const res=await window.__api_call(opts.method||'GET',path,
           opts.body?JSON.parse(opts.body):null,opts.headers||{});
           return new Response(JSON.stringify(res.body),{status:res.status,headers:{'Content-Type':'application/json'}})};
    }''')
    js=(ROOT/'frontend/retail_desk.js').read_text().replace('sessionStorage','window.__OSMANX_SESSION__')
    p.add_script_tag(content=js)
    p.get_by_role('heading',name='Retail Desk').wait_for(timeout=15000)
    return p,errors


def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r12-browser-') as temp:
        os.environ['OSMANX_DEMO_MODE']='1'
        os.environ['OSMANX_DATA_DIR']=temp
        from backend.app import app
        from backend.database import connect,now_iso
        with TestClient(app) as client,sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
            m=client.post('/api/admin/r11/members',json={'slug':'central','explicit_opt_in':True})
            assert m.status_code==201,m.text
            code=m.json()['member_code']
            with connect() as db:
                sid=db.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
                sale_id=db.execute('''INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id)
                                  VALUES(?,?,?,?,?)''',(sid,125000,'desk-qa-pos',now_iso(),'DESK-POS-001')).lastrowid
                db.commit()
            now=datetime.now(timezone.utc).date()
            camp=client.post('/api/admin/r11/campaigns',json={'slug':'central','title':'Подарок за визит',
                 'reward_description':'Мини-сувенир','unit_cost_kopeks':12000,'budget_kopeks':50000,
                 'max_claims':3,'min_spend_kopeks':0,'starts_on':(now-timedelta(days=1)).isoformat(),
                 'ends_on':(now+timedelta(days=14)).isoformat()})
            assert camp.status_code==201,camp.text
            cid=camp.json()['id']
            page,errors=open_page(browser,client,1440,900)
            assert page.locator('[data-tab]').count()==5
            f=page.locator('[data-form="lookup"]')
            f.locator('[name="source"]').fill('desk-qa-pos')
            f.locator('[name="external_id"]').fill('DESK-POS-001')
            f.locator('button[type="submit"]').click()
            page.get_by_text('Найденный чек',exact=True).wait_for(timeout=10000)
            page.screenshot(path=str(QA/'r12-cashier-desktop.png'),full_page=True)
            f=page.locator('[data-form="link"]')
            f.locator('[name="source"]').fill('desk-qa-pos')
            f.locator('[name="external_id"]').fill('DESK-POS-001')
            f.locator('[name="member_code"]').fill(code)
            f.locator('button[type="submit"]').click()
            with connect() as db:
                assert db.execute('SELECT COUNT(*) FROM loyalty_receipts_r11 WHERE sale_id=?',(sale_id,)).fetchone()[0]==1
            claim=client.post(f'/api/admin/r11/campaigns/{cid}/claim',json={'member_code':code})
            assert claim.status_code==201,claim.text
            coupon=claim.json()['coupon_code']
            page.locator('[data-tab="coupons"]').click()
            f=page.locator('[data-form="inspect"]')
            f.locator('[name="coupon_code"]').fill(coupon)
            f.locator('button[type="submit"]').click()
            page.get_by_text('Результат проверки',exact=True).wait_for(timeout=10000)
            assert page.get_by_text('issued',exact=True).count()>0
            verify=client.post(f'/api/admin/r11/campaigns/{cid}/redeem',json={'coupon_code':coupon,'sale_id':sale_id})
            assert verify.status_code==200,verify.text
            f=page.locator('[data-form="fulfill"]')
            f.locator('[name="coupon_code"]').fill(coupon)
            f.locator('[name="proof_reference"]').fill('HANDOFF-DESK-1')
            f.locator('[name="note"]').fill('Физический сувенир передан покупателю')
            f.locator('button[type="submit"]').click()
            with connect() as db:
                assert db.execute('SELECT COUNT(*) FROM coupon_fulfillments_r12').fetchone()[0]==1
            page.screenshot(path=str(QA/'r12-coupons-desktop.png'),full_page=True)
            page.locator('[data-tab="campaigns"]').click()
            page.get_by_text('Подарок за визит',exact=False).wait_for(timeout=10000)
            page.get_by_text('вручено 1',exact=False).first.wait_for(timeout=10000)
            page.screenshot(path=str(QA/'r12-campaigns-desktop.png'),full_page=True)
            page.locator('[data-tab="retention"]').click()
            page.get_by_text('Периоды зрелости',exact=True).wait_for(timeout=10000)
            page.screenshot(path=str(QA/'r12-retention-desktop.png'),full_page=True)
            page.locator('[data-tab="executive"]').click()
            page.get_by_text('Качество данных',exact=True).wait_for(timeout=10000)
            page.locator('[data-form="days"] select[name="days"]').select_option('14')
            page.locator('[data-form="days"] button[type="submit"]').click()
            page.get_by_text('14 дней',exact=False).first.wait_for(timeout=10000)
            page.screenshot(path=str(QA/'r12-executive-desktop.png'),full_page=True)
            mobile,mobile_errors=open_page(browser,client,390,844)
            for tab in ['cashier','coupons','campaigns','retention','executive']:
                mobile.locator(f'[data-tab="{tab}"]').click()
                mobile.locator('#desk-content').wait_for(timeout=15000)
                mobile.screenshot(path=str(QA/f'r12-{tab}-mobile.png'),full_page=True)
                assert mobile.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2'),tab
            assert not errors,errors
            assert not mobile_errors,mobile_errors
            browser.close()
    print('R1.2 Chromium passed: five sections, receipt & coupon fulfillment, 1440/390px, SQLite.')

if __name__=='__main__':main()
