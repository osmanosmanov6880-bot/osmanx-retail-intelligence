"""R1.3 Chromium acceptance; actual FastAPI TestClient + in-memory browser network bridge.

Checks import preview/apply, demand matrix, stock, quality, actions, desktop/mobile UI.
Not a public HTTPS security acceptance or real 1C hardware connection.
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


def source():
    raw=(ROOT/'frontend/control.html').read_text(encoding='utf-8')
    css=(ROOT/'frontend/control.css').read_text(encoding='utf-8')
    raw=re.sub(r'<link rel="stylesheet" href="/static/control.css"\s*/?>','',raw)
    raw=re.sub(r'<script type="module" src="/static/control.js"></script>','',raw)
    return raw.replace('</head>',f'<style>{css}</style></head>')


def scripts():
    api=(ROOT/'frontend/api.js').read_text(encoding='utf-8')
    frontend=(ROOT/'frontend/control.js').read_text(encoding='utf-8')
    frontend=re.sub(r'^import .*?;\s*$','',frontend,flags=re.M)
    api=re.sub(r'\bexport\s+(?=(?:const|function|async function))','',api)
    return (api+'\n'+frontend).replace('sessionStorage','window.__OSMANX_SESSION__')


def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r13-chrome-') as directory:
        os.environ['OSMANX_DEMO_MODE']='1'
        os.environ['OSMANX_DATA_DIR']=directory
        from backend.app import app
        with TestClient(app) as client,sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
            def page_for(width,height):
                page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
                failures=[]
                page.on('pageerror',lambda error:failures.append(str(error)))
                def call_api(method,path,payload,headers):
                    reply=client.request(method,path,json=payload,headers=headers or {}) if payload is not None else client.request(method,path,headers=headers or {})
                    try:body=reply.json()
                    except ValueError:body={'detail':reply.text}
                    return {'status':reply.status_code,'body':body}
                page.expose_function('__api_call',call_api)
                page.set_content(source(),wait_until='domcontentloaded')
                page.evaluate('''() => {
                  const values=new Map();window.__OSMANX_SESSION__={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
                  window.fetch=async(path,opts={})=>{const r=await window.__api_call(opts.method||'GET',String(path),opts.body?JSON.parse(opts.body):null,opts.headers||{});
                    return new Response(JSON.stringify(r.body),{status:r.status,headers:{'Content-Type':'application/json'}})};
                }''')
                page.add_script_tag(content=scripts())
                page.locator('h1').first.wait_for(timeout=16000)
                assert page.locator('h1').inner_text().startswith('Данные.')
                return page,failures

            desktop,errors=page_for(1440,960)
            desktop.screenshot(path=str(QA/'r13-decisions-desktop.png'),full_page=True)
            desktop.get_by_role('tab',name='Импорт 1С / CSV').click()
            desktop.locator('#csv-text').fill('Артикул;Наименование;Размер;Цвет;Остаток\nOX-R13-SKU-XL;Пальто пилотное;XL;графит;3')
            desktop.get_by_role('button',name='Проверить и показать изменения').click()
            desktop.get_by_text('Предварительный просмотр').wait_for(timeout=7000)
            desktop.get_by_role('button',name='Подтвердить и записать в SQLite').wait_for(timeout=6000)
            desktop.screenshot(path=str(QA/'r13-csv-preview-desktop.png'),full_page=True)
            desktop.get_by_role('button',name='Подтвердить и записать в SQLite').click()
            desktop.get_by_role('button',name='Проверить и показать изменения').wait_for(timeout=7000)
            from backend.database import connect
            with connect() as db:
                assert db.execute("SELECT quantity FROM inventory WHERE sku='OX-R13-SKU-XL'").fetchone()['quantity']==3
            for name,filename in [
                ('Качество данных','r13-quality-desktop.png'),
                ('Матрица размеров','r13-demand-desktop.png'),
                ('Ассортимент','r13-stock-desktop.png'),
                ('Решения директора','r13-decisions-final.png')
            ]:
                desktop.get_by_role('tab',name=name).click()
                desktop.locator('.card').first.wait_for(timeout=6000)
                desktop.screenshot(path=str(QA/filename),full_page=True)
            assert not errors,errors

            mobile,mobile_errors=page_for(390,844)
            mobile.get_by_role('tab',name='Импорт 1С / CSV').click()
            mobile.locator('.card').first.wait_for(timeout=6000)
            mobile.screenshot(path=str(QA/'r13-csv-mobile.png'),full_page=True)
            mobile.get_by_role('tab',name='Матрица размеров').click()
            mobile.locator('.card').first.wait_for(timeout=6000)
            mobile.screenshot(path=str(QA/'r13-demand-mobile.png'),full_page=True)
            mobile.get_by_role('tab',name='Решения директора').click()
            mobile.locator('.card').first.wait_for(timeout=6000)
            mobile.screenshot(path=str(QA/'r13-decisions-mobile.png'),full_page=True)
            overflow=mobile.evaluate('document.documentElement.scrollWidth > window.innerWidth + 2')
            assert not overflow,'Mobile horizontal overflow outside scrollable tables'
            assert not mobile_errors,mobile_errors
            browser.close()
    print('R1.3 Chromium acceptance passed: 5 workflows + CSV apply, desktop 1440 and mobile 390 px.')

if __name__=='__main__':main()
