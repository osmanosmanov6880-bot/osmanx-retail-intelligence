"""R1.6 Chromium acceptance through FastAPI TestClient and isolated SQLite.
No external network, no public deployment; state changes verified in the DB.
"""
from __future__ import annotations
import importlib
import os
import shutil
import sys
import tempfile
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
QA=ROOT/'qa';QA.mkdir(exist_ok=True)


def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r16-browser-') as tmp:
        os.environ['OSMANX_DEMO_MODE']='1';os.environ['OSMANX_DATA_DIR']=tmp
        import backend.database as database
        import backend.app as module
        importlib.reload(database);importlib.reload(module)
        with TestClient(module.app) as client, sync_playwright() as p:
            today=datetime.now(ZoneInfo('Europe/Moscow')).date()
            body={'slug':'central','request_id':'browser-pilot-r16-00001',
                 'title':'Проверка качества консультации покупателей',
                 'hypothesis':'Доля чеков на 100 входов может измениться после улучшения помощи в примерочной.',
                 'metric':'receipts_per_100_entries','source_mode':'manual','budget_kopeks':100000,
                 'before_start':str(today-timedelta(days=14)),'before_end':str(today-timedelta(days=8)),
                 'after_start':str(today-timedelta(days=7)),'after_end':str(today-timedelta(days=1))}
            created=client.post('/api/admin/r15/pilots',json=body)
            assert created.status_code==201,created.text
            pid=created.json()['id']
            browser=p.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,
                                      args=['--no-sandbox','--disable-dev-shm-usage'])
            try:
                def open_screen(width,height):
                    page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1,accept_downloads=True)
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    def call_api(method,path,payload,headers):
                        res=client.request(method,path,json=payload,headers=headers or {}) if payload is not None else client.request(method,path,headers=headers or {})
                        return {'status':res.status_code,'text':res.text,'content_type':res.headers.get('content-type','application/json')}
                    page.expose_function('__bridge',call_api)
                    html=(ROOT/'frontend/command.html').read_text()
                    html=html.replace('<link rel="stylesheet" href="/static/command.css">','')
                    html=html.replace('<script type="module" src="/static/command.js"></script>','')
                    html=html.replace('</head>','<style>'+(ROOT/'frontend/command.css').read_text()+'</style></head>')
                    page.set_content(html,wait_until='domcontentloaded')
                    page.evaluate('''() => {window.__OSMANX_SESSION__={getItem(){return null}};
                        window.fetch=async(url,opts={})=>{const r=await window.__bridge(opts.method||'GET',url,opts.body?JSON.parse(opts.body):null,opts.headers||{});
                        return new Response(r.text,{status:r.status,headers:{'Content-Type':r.content_type}})};}''')
                    code=(ROOT/'frontend/command.js').read_text().replace('sessionStorage','window.__OSMANX_SESSION__')
                    page.add_script_tag(content=code)
                    page.get_by_text('Пилоты под',exact=False).first.wait_for(timeout=15000)
                    return page,errors

                desktop,errors=open_screen(1440,900)
                assert desktop.locator('[data-choice]').count()==1
                desktop.screenshot(path=str(QA/'r16-portfolio-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='02 / Качество').click()
                desktop.get_by_text('Контроль качества').first.wait_for()
                desktop.screenshot(path=str(QA/'r16-quality-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='03 / Экономика').click()
                desktop.locator('#scenario-form textarea[name=note]').fill('Допущения только учебные, не сверены с бухгалтерией')
                desktop.locator('#scenario-form button').click()
                desktop.get_by_text('Сценарий №1').first.wait_for(timeout=15000)
                desktop.screenshot(path=str(QA/'r16-scenarios-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='04 / Решение').click()
                desktop.get_by_text('Сначала завершите пилот').first.wait_for()
                desktop.screenshot(path=str(QA/'r16-rollout-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='05 / Исполнение').click()
                desktop.locator('#task-form input[name=owner]').fill('Управляющий')
                desktop.locator('#task-form button').click()
                desktop.get_by_text('Проверить точность остатков').first.wait_for(timeout=15000)
                desktop.screenshot(path=str(QA/'r16-followups-desktop.png'),full_page=True)
                desktop.locator('[data-task][data-status=working]').click()
                desktop.locator('#proof-form textarea').fill('Сверено с управляющим, документ сохранён')
                desktop.locator('#proof-form button').click()
                desktop.locator('[data-task][data-status=done]').wait_for(timeout=15000)
                with database.connect() as db:
                    rows=db.execute('SELECT * FROM pilot_followups_r16 WHERE pilot_id=?',(pid,)).fetchall()
                    assert len(rows)==1 and rows[0]['title']=='Проверить точность остатков' and rows[0]['status']=='working'
                    scenario_count=db.execute('SELECT COUNT(*) FROM pilot_scenarios_r16 WHERE pilot_id=?',(pid,)).fetchone()[0]
                    assert scenario_count==1
                assert errors==[],errors
                phone,phone_errors=open_screen(390,844)
                phone.screenshot(path=str(QA/'r16-portfolio-mobile.png'),full_page=True)
                phone.get_by_role('tab',name='02 / Качество').click()
                phone.screenshot(path=str(QA/'r16-quality-mobile.png'),full_page=True)
                phone.get_by_role('tab',name='05 / Исполнение').click()
                phone.screenshot(path=str(QA/'r16-followups-mobile.png'),full_page=True)
                overflow=phone.evaluate('document.documentElement.scrollWidth>window.innerWidth+2')
                assert not overflow,'Horizontal overflow at 390 px'
                assert phone_errors==[],phone_errors
                print('R1.6 Chromium acceptance passed: portfolio/quality/scenarios/rollout/followups, SQLite and 390px.')
            finally:browser.close()

if __name__=='__main__':main()
