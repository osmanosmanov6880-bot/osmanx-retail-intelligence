"""Chromium acceptance of all five R0.7 workflows; no public deployment.

The real UI JavaScript calls the real FastAPI API via a browser-to-TestClient bridge.
"""
from __future__ import annotations

import os
import re
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


def markup(name='operations'):
    text=(ROOT/f'frontend/{name}.html').read_text(encoding='utf-8')
    text=re.sub(r'<link[^>]+rel="stylesheet"[^>]*>', '', text)
    text=re.sub(r'<script[^>]+src="/static/[^\"]+"[^>]*></script>', '', text)
    css=(ROOT/'frontend/operations.css').read_text(encoding='utf-8')
    return text.replace('</head>',f'<style>{css}</style></head>')


def open_page(browser,client,width=1440,height=900,kind='operations',assist_path=''):
    page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def api(method,path,payload,headers):
        result=client.request(method,path,json=payload,headers=headers or {}) if payload is not None else client.request(method,path,headers=headers or {})
        try:body=result.json()
        except ValueError:body={'detail':result.text}
        return {'status':result.status_code,'body':body}
    page.expose_function('__api_call',api)
    page.set_content(markup(kind),wait_until='domcontentloaded')
    page.evaluate('''() => {
       const values=new Map();window.__OSMANX_SESSION__={getItem:k=>values.get(k)||null,
        setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
       window.fetch=async(p,o={})=>{
         const r=await window.__api_call(o.method||'GET',p,o.body?JSON.parse(o.body):null,o.headers||{});
         return new Response(JSON.stringify(r.body),{status:r.status,headers:{'Content-Type':'application/json'}})
       };
    }''')
    script=(ROOT/f'frontend/{kind}.js').read_text(encoding='utf-8')
    if kind=='operations':
        script=script.replace('sessionStorage','window.__OSMANX_SESSION__')
    else:
        script=script.replace("const path=location.pathname.match", "const path=(window.__TEST_ASSIST_PATH__||location.pathname).match")
        page.evaluate('window.__TEST_ASSIST_PATH__='+__import__('json').dumps(assist_path))
    page.add_script_tag(content=script)
    if kind=='operations':page.get_by_role('heading',name='Операционный центр').wait_for(timeout=15000)
    return page,errors


def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r07-browser-') as temp:
        os.environ['OSMANX_DATA_DIR']=temp
        os.environ['OSMANX_DEMO_MODE']='1'
        from backend.app import app
        from backend.database import connect,now_iso
        with TestClient(app) as client:
            st=client.post('/api/admin/stores',json={'slug':'r07north','name':'Северный бутик'})
            assert st.status_code==201,st.text
            with connect() as db:
                sid=db.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
                db.execute('''INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at)
                  VALUES(?,?,?,?,?,?,?,?)''',(sid,'R07-COAT','Пальто премиум','L','чёрный',8,'manual',now_iso()))
                db.execute('INSERT INTO zones(store_id,code,name,x,y) VALUES(?,?,?,?,?)',(sid,'display-7','Зона витрины',20,20))
                db.commit()
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
                page,errors=open_page(browser,client)
                page.screenshot(path=str(QA/'r07-brief-desktop.png'),full_page=True)
                page.locator('[data-tab=counts]').click()
                coat_id=next(x['id'] for x in client.get('/api/admin/r07/stock').json()['items'] if x['sku']=='R07-COAT')
                page.locator('[data-form=count] [name=inventory_id]').select_option(str(coat_id))
                page.locator('[data-form=count] [name=observed_qty]').fill('7')
                page.locator('[data-form=count] [name=reason]').fill('Пересчёт в торговом зале')
                page.locator('[data-form=count] button[type=submit]').click()
                page.get_by_text('Пересчёт №1').first.wait_for(timeout=12000)
                page.locator('[data-action=count-apply]').first.click()
                page.get_by_text('Применена',exact=True).first.wait_for(timeout=12000)
                assert next(x['quantity'] for x in client.get('/api/admin/r07/stock').json()['items'] if x['sku']=='R07-COAT')==7
                page.screenshot(path=str(QA/'r07-counts-desktop.png'),full_page=True)

                page.locator('[data-tab=transfers]').click()
                page.locator('[data-form=transfer] [name=inventory_id]').select_option(str(coat_id))
                page.locator('[data-form=transfer] [name=quantity]').fill('2')
                page.locator('[data-form=transfer] button[type=submit]').click()
                page.get_by_text('№1 · R07-COAT').first.wait_for(timeout=12000)
                page.locator('[data-action=ship]').first.click()
                page.locator('[data-action=receive]').first.click()
                page.get_by_text('Принято',exact=True).first.wait_for(timeout=12000)
                assert next(x['quantity'] for x in client.get('/api/admin/r07/stock').json()['items'] if x['sku']=='R07-COAT')==5
                page.screenshot(path=str(QA/'r07-transfers-desktop.png'),full_page=True)

                page.locator('[data-tab=assistance]').click()
                page.locator('[data-form=point] [name=name]').fill('Примерочная №1')
                page.locator('[data-form=point] button[type=submit]').click()
                page.get_by_text('Ссылка для QR-кода').first.wait_for(timeout=12000)
                points=client.get('/api/admin/r07/assistance').json()
                point_id=points['points'][0]['id']
                # Extract the one-time URL shown by the real interface to test the public QR flow.
                url=page.locator('.qr-result code').inner_text()
                token=url.split('/assist/')[-1]
                assert len(token)>25
                help_page,help_errors=open_page(browser,client,390,844,kind='assist',assist_path='/assist/'+token)
                help_page.get_by_role('button',name='Не могу найти размер').click()
                help_page.get_by_text('Сотрудник получил вызов').wait_for(timeout=15000)
                help_page.screenshot(path=str(QA/'r07-assist-kiosk-mobile.png'),full_page=True)
                page.locator('[data-action=refresh]').click()
                page.get_by_text('Нужен размер').first.wait_for(timeout=12000)
                page.locator('[data-action=help-accept]').first.click()
                page.get_by_text('Принят',exact=True).first.wait_for(timeout=12000)
                page.locator('[data-action=help-resolve]').first.click()
                page.get_by_text('Завершён',exact=True).first.wait_for(timeout=12000)
                page.screenshot(path=str(QA/'r07-assistance-desktop.png'),full_page=True)
                assert not help_errors,help_errors
                help_page.close()

                page.locator('[data-tab=zones]').click()
                page.locator('[data-form=trial] [name=title]').fill('Витрина с новой подсветкой')
                page.locator('[data-form=trial] button[type=submit]').click()
                page.get_by_text('Витрина с новой подсветкой').first.wait_for(timeout=12000)
                page.screenshot(path=str(QA/'r07-zones-desktop.png'),full_page=True)

                page.locator('[data-tab=brief]').click()
                page.get_by_text('Управленческая сводка').wait_for()
                page.screenshot(path=str(QA/'r07-brief-final.png'),full_page=True)
                assert not errors,errors
                mobile,mobile_errors=open_page(browser,client,390,844)
                mobile.screenshot(path=str(QA/'r07-brief-mobile.png'),full_page=True)
                mobile.locator('[data-tab=counts]').click()
                mobile.screenshot(path=str(QA/'r07-counts-mobile.png'),full_page=True)
                width=mobile.evaluate('document.documentElement.scrollWidth')
                assert width<=400,f'Mobile horizontal overflow: {width}'
                assert not mobile_errors,mobile_errors
                browser.close()
        print('R0.7 CHROMIUM PASS: desktop + mobile, count, transfer, public help, zones and brief')


if __name__=='__main__':main()
