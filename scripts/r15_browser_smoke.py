"""R1.5 Chromium full UI acceptance using real FastAPI TestClient and SQLite.

No public network/navigation. Every browser interaction calls live backend routes.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
QA=ROOT/'qa';QA.mkdir(exist_ok=True)


def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r15-browser-') as temp:
        os.environ['OSMANX_DEMO_MODE']='1'
        os.environ['OSMANX_DATA_DIR']=temp
        import backend.database as database
        import backend.app as module
        importlib.reload(database);importlib.reload(module)
        with TestClient(module.app) as client, sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,
                                               args=['--no-sandbox','--disable-dev-shm-usage'])
            try:
                def open_pilot(width,height):
                    page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1,accept_downloads=True)
                    errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))

                    def backend_call(method,path,body,headers):
                        response=client.request(method,path,json=body,headers=headers or {}) if body is not None else client.request(method,path,headers=headers or {})
                        return {'status':response.status_code,'body':response.text,
                                'content_type':response.headers.get('content-type','application/json')}
                    page.expose_function('__api_call',backend_call)
                    html=(ROOT/'frontend/pilot.html').read_text(encoding='utf-8')
                    html=html.replace('<link rel="stylesheet" href="/static/pilot.css">','')
                    html=html.replace('<script type="module" src="/static/pilot.js"></script>','')
                    html=html.replace('</head>','<style>'+ (ROOT/'frontend/pilot.css').read_text(encoding='utf-8')+'</style></head>')
                    page.set_content(html,wait_until='domcontentloaded')
                    page.evaluate('''() => {window.fetch=async (path,opts={})=>{
                      const body=opts.body?JSON.parse(opts.body):null;
                      const r=await window.__api_call(opts.method||'GET',path,body,opts.headers||{});
                      return new Response(r.body,{status:r.status,headers:{'Content-Type':r.content_type}});
                    };}''')
                    page.evaluate('window.__OSMANX_SESSION__={getItem(){return null}}')
                    page.add_script_tag(content=(ROOT/'frontend/pilot.js').read_text(encoding='utf-8').replace('sessionStorage','window.__OSMANX_SESSION__'))
                    page.locator('.hero h1').wait_for(timeout=15000)
                    return page,errors

                desktop,errors=open_pilot(1440,900)
                assert desktop.locator('#new-pilot').count()==1
                desktop.screenshot(path=str(QA/'r15-plan-desktop.png'),full_page=True)
                desktop.locator('#new-pilot button[type=submit]').click()
                desktop.locator('#start-pilot').wait_for(timeout=15000)
                desktop.locator('#start-pilot').click()
                desktop.get_by_text('Работает',exact=True).first.wait_for(timeout=15000)
                desktop.get_by_role('tab',name='02. Источники').click()
                desktop.locator('textarea[name=note]').fill('Вручную сверили кассовый журнал и посещения за контрольный час')
                desktop.locator('#attestation button').click()
                desktop.get_by_text('Вручную сверили кассовый журнал',exact=False).first.wait_for(timeout=15000)
                desktop.screenshot(path=str(QA/'r15-sources-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='04. Действия').click()
                desktop.locator('textarea[name=description]').fill('Сотрудники стали фиксировать запросы на отсутствующие размеры')
                desktop.locator('input[name=cost_rub]').fill('150')
                desktop.locator('#action-entry button').click()
                desktop.get_by_text('Сотрудники стали фиксировать запросы',exact=False).first.wait_for(timeout=15000)
                desktop.screenshot(path=str(QA/'r15-actions-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='03. Показатели').click()
                desktop.get_by_text('Входы · база').wait_for(timeout=15000)
                desktop.screenshot(path=str(QA/'r15-daily-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='05. Отчёт').click()
                desktop.locator('textarea[name=note]').fill('Проверили зарегистрированные показатели; часть данных демонстрационная')
                desktop.locator('#close-form button').click()
                desktop.locator('#check-snapshot').wait_for(timeout=15000)
                desktop.locator('#check-snapshot').click()
                desktop.get_by_text('SHA-256 подтверждён:',exact=False).wait_for(timeout=15000)
                desktop.screenshot(path=str(QA/'r15-report-desktop.png'),full_page=True)
                with desktop.expect_download() as download:
                    desktop.locator('#download-snapshot').click()
                assert download.value.suggested_filename=='osmanx-pilot-report.csv'
                assert not errors,errors

                mobile,merrors=open_pilot(390,844)
                mobile.screenshot(path=str(QA/'r15-plan-mobile.png'),full_page=True)
                mobile.get_by_role('tab',name='03. Показатели').click()
                mobile.screenshot(path=str(QA/'r15-daily-mobile.png'),full_page=True)
                mobile.get_by_role('tab',name='05. Отчёт').click()
                mobile.screenshot(path=str(QA/'r15-report-mobile.png'),full_page=True)
                size=mobile.evaluate('({width:document.documentElement.scrollWidth,screen:innerWidth})')
                assert size['width']<=size['screen']+2,size
                assert not merrors,merrors
                with database.connect() as conn:
                    assert conn.execute("SELECT COUNT(*) FROM pilots_r15 WHERE status='completed'").fetchone()[0]==1
                    assert conn.execute('SELECT COUNT(*) FROM pilot_actions_r15').fetchone()[0]==1
                    assert conn.execute('SELECT COUNT(*) FROM pilot_snapshots_r15').fetchone()[0]==1
                print('R1.5 Chromium: complete five-tab flow + approved source, action, sealed report, CSV, 390px mobile: PASS')
            finally:browser.close()


if __name__=='__main__':main()
