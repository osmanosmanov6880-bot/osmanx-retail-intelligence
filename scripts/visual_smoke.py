"""Browser UI QA without network navigation (blocked on some hosted runners).

Loads the real HTML/CSS/JavaScript into Chromium and forwards fetch() calls to
FastAPI TestClient. Not a substitute for a later HTTPS deployment acceptance.
"""
from __future__ import annotations

import os
import re
import tempfile
import sys
import shutil
from pathlib import Path

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
QA=ROOT/'qa'
QA.mkdir(exist_ok=True)

def page_content():
    html=(ROOT/'frontend/index.html').read_text()
    css=(ROOT/'frontend/styles.css').read_text()
    css=re.sub(r'@import\s+url\([^)]*\)\s*;', '', css)
    html=re.sub(r'<link[^>]+styles\.css[^>]+>', '', html)
    html=re.sub(r'<script[^>]+src="/static/app.js"[^>]*></script>', '', html)
    return html.replace('</head>',f'<style>{css}</style></head>')


def javascript(kiosk=False):
    modules=['icons.js','charts.js','api.js','app.js']
    script='\n'.join((ROOT/'frontend'/name).read_text() for name in modules)
    script=re.sub(r'^import .*?;\s*$', '', script,flags=re.M)
    script=re.sub(r'\bexport\s+(?=(?:function|const|async function))', '', script)
    script=script.replace('sessionStorage', 'window.__OSMANX_SESSION__')
    if kiosk:
        script=script.replace('location.pathname.match(/^\\/kiosk', '(window.__OSMANX_TEST_PATH__||location.pathname).match(/^\\/kiosk')
    return script


def install_page(browser,client, viewport, kiosk=False):
    page=browser.new_page(viewport=viewport,device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def call_api(method,path,payload):
        result=client.request(method,path,json=payload) if payload is not None else client.request(method,path)
        try: content=result.json()
        except ValueError: content={'detail':result.text}
        return {'status':result.status_code,'body':content}
    page.expose_function('__api_call',call_api)
    page.set_content(page_content(),wait_until='domcontentloaded',timeout=10000)
    if kiosk:
        page.evaluate('window.__OSMANX_TEST_PATH__="/kiosk/central"')
    page.evaluate('''() => { window.__OSMANX_SESSION__={getItem(){return null},setItem(){},removeItem(){}};window.fetch = async (path,opts={}) => {
      const result=await window.__api_call(opts.method||'GET',path,opts.body?JSON.parse(opts.body):null);
      return new Response(JSON.stringify(result.body),{status:result.status,headers:{'Content-Type':'application/json'}});
    }; }''')
    page.add_script_tag(content=javascript(kiosk=kiosk))
    return page, errors


def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-visual-') as store:
        os.environ['OSMANX_DEMO_MODE']='1'
        os.environ['OSMANX_DATA_DIR']=store
        # Imports happen only after data directory is configured.
        from backend.app import app
        with TestClient(app) as client, sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
            dash,errors=install_page(browser,client,{'width':1512,'height':950})
            dash.get_by_text('Обзор бизнеса').wait_for(timeout=12000)
            dash.screenshot(path=str(QA/'r02-dashboard-desktop.png'),full_page=True)
            dash.locator('[data-nav="zones"]').first.click()
            dash.get_by_text('Тепловая карта магазина',exact=True).first.wait_for(timeout=5000)
            dash.screenshot(path=str(QA/'r02-zones-desktop.png'),full_page=True)
            dash.locator('[data-dialog="zone"]').first.click()
            dash.locator('#zone-form input[name="code"]').fill('vip-corner')
            dash.locator('#zone-form input[name="name"]').fill('VIP-зона')
            dash.locator('#zone-form button[type="submit"]').click()
            dash.get_by_text('Зона сохранена').wait_for(timeout=5000)
            dash.locator('[data-nav="stock"]').first.click()
            dash.get_by_text('Остатки и доступность').wait_for(timeout=5000)
            dash.screenshot(path=str(QA/'r02-inventory-desktop.png'),full_page=True)
            dash.locator('[data-nav="demand"]').first.click()
            dash.get_by_text('Невидимый спрос').first.wait_for(timeout=5000)
            dash.locator('[data-matches]').first.click()
            dash.get_by_text('Поиск по филиалам').wait_for(timeout=5000)
            dash.locator('[data-action="close-dialog"]').click()
            dash.locator('[data-nav="actions"]').first.click()
            dash.get_by_text('Доска экспериментов').wait_for(timeout=5000)
            dash.locator('[data-dialog="experiment"]').first.click()
            dash.locator('#experiment-form input[name="title"]').fill('Проверка спроса XL')
            dash.locator('#experiment-form textarea[name="hypothesis"]').fill('Дополнительные размеры закроют неудовлетворённый спрос')
            dash.locator('#experiment-form button[type="submit"]').click()
            dash.get_by_text('Пилот создан').wait_for(timeout=6000)
            assert not errors,errors

            kiosk,kerrors=install_page(browser,client,{'width':1080,'height':900},kiosk=True)
            kiosk.get_by_text('Помогите нам').wait_for(timeout=8000)
            kiosk.screenshot(path=str(QA/'r02-kiosk-intro.png'),full_page=True)
            count=client.get('/api/admin/dashboard').json()['surveys_count']
            kiosk.locator('[data-kiosk="start"]').click()
            kiosk.locator('[data-rating="5"]').click()
            kiosk.locator('[data-kiosk="next"]').click()
            kiosk.locator('[data-purchased="no"]').click()
            kiosk.locator('[data-reason="size"]').click()
            kiosk.locator('[data-kiosk="next"]').click()
            kiosk.locator('[data-kiosk-tag="quality"]').click()
            kiosk.locator('[data-kiosk="next"]').click()
            kiosk.screenshot(path=str(QA/'r02-kiosk-feedback.png'),full_page=True)
            kiosk.locator('[data-kiosk-tag="size"]').click()
            kiosk.locator('#suggestion').fill('Больше размеров XL')
            kiosk.locator('#kiosk-form button[type="submit"]').click()
            kiosk.get_by_text('Спасибо!',exact=True).wait_for(timeout=8000)
            assert client.get('/api/admin/dashboard').json()['surveys_count']==count+1
            assert not kerrors,kerrors
            kiosk.screenshot(path=str(QA/'r02-kiosk-thanks.png'),full_page=True)

            mobile,merrors=install_page(browser,client,{'width':390,'height':844})
            mobile.get_by_text('Обзор бизнеса').wait_for(timeout=8000)
            mobile.screenshot(path=str(QA/'r02-dashboard-mobile.png'),full_page=True)
            mobile.locator('.mobile-bottom [data-nav="demand"]').click()
            mobile.get_by_text('Невидимый спрос').first.wait_for(timeout=5000)
            mobile.screenshot(path=str(QA/'r02-demand-mobile.png'),full_page=True)
            assert not merrors,merrors
            mobilek,mkerrors=install_page(browser,client,{'width':390,'height':844},kiosk=True)
            mobilek.get_by_text('Помогите нам').wait_for(timeout=8000)
            mobilek.screenshot(path=str(QA/'r02-kiosk-mobile.png'),full_page=True)
            assert not mkerrors,mkerrors
            browser.close()
            print('UI smoke: dashboard, stock, matching, pilots, kiosk 4 stages, kiosk submission, 390px mobile PASS')
            print('Screenshots:',len(list(QA.glob('r02-*.png'))))

if __name__=='__main__':main()
