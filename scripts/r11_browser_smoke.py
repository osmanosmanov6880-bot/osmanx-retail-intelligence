"""Local Chromium acceptance for R1.1, no external network or public deployment."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
QA=ROOT/'qa'
QA.mkdir(exist_ok=True)


def page_contents():
    html=(ROOT/'frontend/growth.html').read_text()
    css=(ROOT/'frontend/growth.css').read_text()
    html=html.replace('<link rel="stylesheet" href="/static/growth.css" />','')
    html=html.replace('<script type="module" src="/static/growth.js"></script>','')
    return html.replace('</head>',f'<style>{css}</style></head>')


def open_page(browser,client,width,height):
    page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    def call(method,path,payload,headers):
        response=client.request(method,path,json=payload,headers=headers or {}) if payload is not None else client.request(method,path,headers=headers or {})
        try:data=response.json()
        except ValueError:data={'detail':response.text}
        return {'status':response.status_code,'body':data}
    page.expose_function('__api_call',call)
    page.set_content(page_contents(),wait_until='domcontentloaded',timeout=10000)
    page.evaluate('''() => {
       const tokens=new Map();window.__OSMANX_SESSION__={getItem:(x)=>tokens.get(x)||null,setItem:(x,y)=>tokens.set(x,y),removeItem:(x)=>tokens.delete(x)};
       window.fetch=async(path,opts={})=>{
         const res=await window.__api_call(opts.method||'GET',path,opts.body?JSON.parse(opts.body):null,opts.headers||{});
         return new Response(JSON.stringify(res.body),{status:res.status,headers:{'Content-Type':'application/json'}});
       }
    }''')
    js=(ROOT/'frontend/growth.js').read_text().replace('sessionStorage','window.__OSMANX_SESSION__')
    page.add_script_tag(content=js)
    page.locator('h1').first.wait_for(timeout=15000)
    return page,errors


def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r11-qa-') as temp:
        os.environ['OSMANX_DEMO_MODE']='1';os.environ['OSMANX_DATA_DIR']=temp
        from backend.app import app
        from backend.database import connect,now_iso
        with TestClient(app) as client, sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
            page,errors=open_page(browser,client,1440,900)
            page.locator('[data-form="member"] input[type="checkbox"]').check()
            page.locator('[data-form="member"] button[type="submit"]').click()
            page.locator('.codebox b').wait_for(timeout=10000)
            member_code=page.locator('.codebox b').inner_text()
            assert member_code.startswith('OXM-'),member_code
            page.screenshot(path=str(QA/'r11-loyalty-desktop.png'),full_page=True)
            with connect() as db:
                store_id=db.execute("SELECT id FROM stores WHERE slug='central'").fetchone()[0]
                sale_id=db.execute('''INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id)
                        VALUES(?,?,?,?,?)''',(store_id,200000,'qa-r11',now_iso(),'r11-qa-sale')).lastrowid
                db.execute('INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                           (store_id,'OX-QA-XXL','Куртка из проверки','XXL','чёрный',0,'manual',now_iso()))
                for _ in range(4):
                    db.execute('INSERT INTO demand(store_id,product,size,color,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                               (store_id,'Куртка из проверки','XXL','чёрный','open',now_iso(),now_iso()))
                db.commit()
            page.locator('[data-tab="receipts"]').click()
            page.locator('form[data-form="receipt"] [name="member_code"]').fill(member_code)
            page.locator('form[data-form="receipt"] [name="sale_id"]').fill(str(sale_id))
            page.locator('form[data-form="receipt"] button[type="submit"]').click()
            page.get_by_text(f'Чек №{sale_id}',exact=False).wait_for(timeout=10000)
            page.screenshot(path=str(QA/'r11-receipts-desktop.png'),full_page=True)
            page.locator('[data-tab="campaigns"]').click()
            form=page.locator('form[data-form="campaign"]')
            form.locator('[name="title"]').fill('Бонус за участие')
            form.locator('[name="reward_description"]').fill('Небольшой подарок')
            form.locator('[name="unit_cost_kopeks"]').fill('5000')
            form.locator('[name="budget_kopeks"]').fill('10000')
            form.locator('[name="max_claims"]').fill('2')
            form.locator('[name="min_spend_kopeks"]').fill('50000')
            form.locator('button[type="submit"]').click()
            page.get_by_text('Бонус за участие',exact=False).wait_for(timeout=10000)
            claim=page.locator('form[data-form="claim"]').first
            claim.locator('[name="member_code"]').fill(member_code)
            claim.locator('button[type="submit"]').click()
            page.locator('.codebox b').wait_for(timeout=10000)
            coupon=page.locator('.codebox b').inner_text()
            assert coupon.startswith('OXC-')
            redeem=page.locator('form[data-form="redeem"]').first
            redeem.locator('[name="coupon_code"]').fill(coupon)
            redeem.locator('[name="sale_id"]').fill(str(sale_id))
            redeem.locator('button[type="submit"]').click()
            page.get_by_text('сверено: 1',exact=False).first.wait_for(timeout=10000)
            page.screenshot(path=str(QA/'r11-campaigns-desktop.png'),full_page=True)
            page.locator('[data-action="effect"]').first.click()
            page.get_by_text('ROI: не определён',exact=False).first.wait_for(timeout=10000)
            page.locator('[data-tab="retention"]').click()
            page.get_by_text('Когорты первых покупок').first.wait_for(timeout=10000)
            page.screenshot(path=str(QA/'r11-retention-desktop.png'),full_page=True)
            page.locator('[data-tab="assortment"]').click()
            page.get_by_text('Куртка из проверки').first.wait_for(timeout=10000)
            page.screenshot(path=str(QA/'r11-assortment-desktop.png'),full_page=True)
            mobile,mobile_errors=open_page(browser,client,390,844)
            for tab,filename in [('members','loyalty'),('campaigns','campaigns'),('retention','retention'),('assortment','assortment')]:
                mobile.locator(f'[data-tab="{tab}"]').click()
                mobile.locator('#growth-content').wait_for(timeout=15000)
                mobile.screenshot(path=str(QA/f'r11-{filename}-mobile.png'),full_page=True)
                assert mobile.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2'),tab
            with connect() as db:
                assert db.execute('SELECT COUNT(*) FROM loyalty_members_r11').fetchone()[0]==1
                assert db.execute('SELECT COUNT(*) FROM loyalty_receipts_r11').fetchone()[0]==1
                assert db.execute("SELECT COUNT(*) FROM campaign_claims_r11 WHERE status='redeemed'").fetchone()[0]==1
                assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert errors==[],errors
            assert mobile_errors==[],mobile_errors
            browser.close()
    print('R1.1 Chromium acceptance passed: five workflows, 1440 + 390 px, SQLite persisted, no console errors.')

if __name__=='__main__':
    main()
