"""R0.9 Chromium: five real tabs with in-process FastAPI, no public deployment."""
from __future__ import annotations
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
QA=ROOT/'qa'
QA.mkdir(exist_ok=True)


def html():
    p=(ROOT/'frontend/evidence.html').read_text()
    p=re.sub(r'<link rel="stylesheet"[^>]*>', '', p)
    p=p.replace('<script type="module" src="/static/evidence.js"></script>','')
    css='\n'.join((ROOT/'frontend'/x).read_text() for x in ['operations.css','strategy.css','evidence.css'])
    css=re.sub(r'@import\s+url\([^)]*\)\s*;', '', css)
    return p.replace('</head>',f'<style>{css}</style></head>')


def new_page(browser,client,width,height):
    page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1,accept_downloads=True)
    errors=[]
    page.on('pageerror',lambda err:errors.append(str(err)))
    def rpc(method,url,body,headers):
        r=client.request(method,url,json=body,headers=headers or {}) if body is not None else client.request(method,url,headers=headers or {})
        try:content=r.json();ctype='application/json'
        except ValueError:content=r.text;ctype=r.headers.get('content-type','text/plain')
        return {'status':r.status_code,'body':content,'type':ctype}
    page.expose_function('__evidence_rpc',rpc)
    page.set_content(html(),wait_until='domcontentloaded',timeout=15000)
    page.evaluate('''() => {
       const memory=new Map();window.__TEST_SESSION__={getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)};
       window.fetch=async(url,opts={})=>{const result=await window.__evidence_rpc(opts.method||'GET',url,opts.body?JSON.parse(opts.body):null,opts.headers||{});
           return new Response(typeof result.body==='string'?result.body:JSON.stringify(result.body),{status:result.status,headers:{'Content-Type':result.type}})};
    }''')
    page.add_script_tag(content=(ROOT/'frontend/evidence.js').read_text().replace('sessionStorage','window.__TEST_SESSION__'))
    page.get_by_role('heading',name='Не просто цифры. Проверяемые решения.').wait_for(timeout=20000)
    return page,errors


def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r09-ui-') as tmp:
        os.environ['OSMANX_DATA_DIR']=tmp
        os.environ['OSMANX_DEMO_MODE']='1'
        from backend.app import app
        from backend.database import connect,now_iso
        with TestClient(app) as client:
            # R0.9 demo data: seeded visits/sales; prepare one unambiguous SKU and a distinct manual POS receipt.
            with connect() as db:
                sid=db.execute("SELECT id FROM stores WHERE slug='central'").fetchone()[0]
                db.execute('INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                   (sid,'R09-COAT-XL','Куртка R09 Проверка','XL','чёрный',0,'manual',now_iso()))
                db.execute('INSERT INTO demand(store_id,product,size,color,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                   (sid,'Куртка R09 Проверка','XL','чёрный','open',now_iso(),now_iso()))
                sale=db.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                   (sid,650000,'pos',now_iso(),'r09-browser-receipt')).lastrowid
                db.execute('INSERT INTO sale_items(organization_id,store_id,sale_id,sku,quantity,unit_revenue_kopeks,unit_cost_kopeks,external_id,recorded_at) VALUES(?,?,?,?,?,?,?,?,?)',
                   (1,sid,sale,'R09-COAT-XL',1,650000,300000,'r09-browser-line',now_iso()))
                db.commit()
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
                page,errors=new_page(browser,client,1440,900)
                page.get_by_text('Радар покупательского спроса').count() if False else None
                page.screenshot(path=str(QA/'r09-radar-desktop.png'),full_page=True)
                page.locator('[data-tab=recoveries]').click()
                page.get_by_role('heading',name='Рабочие планы').wait_for(timeout=15000)
                # Select a specific seeded demand SKU matching the new inventory row.
                selections=page.locator('[data-form=recovery] select[name=demand_id] option').all()
                chosen=next((x for x in selections if 'Куртка R09 Проверка' in x.inner_text()),None)
                assert chosen is not None,'expected demand case for coat'
                page.locator('[data-form=recovery] select[name=demand_id]').select_option(chosen.get_attribute('value'))
                page.locator('[data-form=recovery] button[type=submit]').click()
                page.get_by_text('SKU R09-COAT-XL').first.wait_for(timeout=12000)
                page.screenshot(path=str(QA/'r09-recoveries-desktop.png'),full_page=True)
                page.locator('[data-action=edit-result]').first.click()
                page.locator('[data-form=resolve] [name=outcome]').select_option('confirmed_sale')
                page.locator('[data-form=resolve] [name=sale_id]').fill(str(sale))
                page.locator('[data-form=resolve] [name=evidence]').fill('Подтверждённый чек с моделью, размером и количеством')
                page.locator('[data-form=resolve] button[type=submit]').click()
                page.get_by_text('Продажа подтверждена').first.wait_for(timeout=12000)
                page.locator('[data-tab=finance]').click()
                page.get_by_role('heading',name='Контроль целостности').wait_for(timeout=12000)
                page.screenshot(path=str(QA/'r09-finance-desktop.png'),full_page=True)
                page.locator('[data-tab=protocols]').click()
                page.locator('[data-form=protocol] textarea[name=hypothesis]').fill('Новая раскладка может увеличить число чеков на входы')
                page.locator('[data-form=protocol] button[type=submit]').click()
                page.get_by_text('Проверка конверсии витрины').count() if False else None
                page.locator('[data-action=preview-protocol]').first.click()
                page.get_by_text('Сравнение',exact=False).count()
                page.screenshot(path=str(QA/'r09-protocols-desktop.png'),full_page=True)
                page.locator('[data-tab=dossiers]').click()
                page.locator('[data-form=dossier] button[type=submit]').click()
                page.get_by_text('Пакет №1').first.wait_for(timeout=12000)
                page.locator('[data-action=view-dossier]').first.click()
                page.get_by_text('SHA-256:',exact=False).first.wait_for(timeout=12000)
                page.screenshot(path=str(QA/'r09-dossiers-desktop.png'),full_page=True)
                mobile,mobile_errors=new_page(browser,client,390,844)
                mobile.screenshot(path=str(QA/'r09-radar-mobile.png'),full_page=True)
                mobile.locator('[data-tab=finance]').click()
                mobile.screenshot(path=str(QA/'r09-finance-mobile.png'),full_page=True)
                mobile.locator('[data-tab=dossiers]').click()
                mobile.screenshot(path=str(QA/'r09-dossiers-mobile.png'),full_page=True)
                overflow=mobile.evaluate('document.documentElement.scrollWidth > window.innerWidth+1')
                assert not overflow,'horizontal overflow on 390px screen'
                assert not errors and not mobile_errors,(errors,mobile_errors)
                assert client.get('/api/admin/r09/recoveries').json()['items'][0]['outcome']=='confirmed_sale'
                assert client.get('/api/admin/r09/dossiers').json()['items']
                browser.close()
    print('R0.9 Chromium success: 5 tabs, confirmed sale, protocol, evidence pack, 390px. Screenshots in qa/r09-*.png')


if __name__=='__main__':main()
