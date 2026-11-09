"""R1.8 Chromium functional acceptance with isolated real SQLite and FastAPI TestClient."""
from __future__ import annotations
import importlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
QA=ROOT/'qa';QA.mkdir(exist_ok=True)

def main():
    with tempfile.TemporaryDirectory(prefix='r18-browser-') as tmp:
        os.environ['OSMANX_DATA_DIR']=tmp
        os.environ['OSMANX_DEMO_MODE']='1'
        import backend.database as database
        import backend.r15 as r15
        import backend.r17 as r17
        import backend.r18 as r18
        importlib.reload(database)
        database.initialize_db(demo=True)
        with database.connect() as db:
            r15.ensure_schema(db);r17.ensure_schema(db);r18.ensure_schema(db);db.commit()
        from backend.security import Principal
        def admin():return Principal(0,1,'demo@osmanx.local','owner',demo=True)
        def db_conn():
            with database.connect() as db:yield db
        app=FastAPI();app.include_router(r15.build_router(admin,db_conn));app.include_router(r17.build_router(admin,db_conn));app.include_router(r18.build_router(admin,db_conn))
        with TestClient(app) as client,sync_playwright() as play:
            from scripts.tests_fixture_r18 import populate
            p,v=populate((client,database),count=4)
            browser=play.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox','--disable-dev-shm-usage'])
            try:
                def screen(width,height):
                    page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1,accept_downloads=True)
                    errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
                    def call_api(method,url,data,headers):
                        response=client.request(method,url,json=data,headers=headers or {}) if data is not None else client.request(method,url,headers=headers or {})
                        return {'status':response.status_code,'text':response.text,'type':response.headers.get('content-type','application/json')}
                    page.expose_function('__api_call',call_api)
                    html=(ROOT/'frontend/bridge.html').read_text()
                    html=html.replace('<link rel="stylesheet" href="/static/bridge.css">','').replace('<script src="/static/bridge.js" defer></script>','')
                    html=html.replace('</head>','<style>'+(ROOT/'frontend/bridge.css').read_text()+'</style></head>')
                    page.set_content(html,wait_until='domcontentloaded')
                    page.evaluate('''() => {window.__OSMANX_SESSION__={getItem(){return null}};window.fetch=async(path,opts={})=>{
                     const r=await window.__api_call(opts.method||'GET',path,opts.body?JSON.parse(opts.body):null,opts.headers||{});
                     return new Response(r.text,{status:r.status,headers:{'Content-Type':r.type}});
                    };}''')
                    js=(ROOT/'frontend/bridge.js').read_text().replace('sessionStorage','window.__OSMANX_SESSION__')
                    page.add_script_tag(content=js)
                    page.get_by_text('От ответа клиента',exact=False).first.wait_for(timeout=12000)
                    return page,errors

                desktop,errors=screen(1440,900)
                desktop.get_by_text('Нужного размера нет').first.wait_for(timeout=15000)
                desktop.screenshot(path=str(QA/'r18-signals-desktop.png'),full_page=True)
                desktop.locator('#hypothesis-create button[type=submit]').click()
                desktop.get_by_text('Гипотеза сохранена с источником').wait_for(timeout=15000)
                desktop.get_by_role('tab',name='02 / Гипотезы').click()
                desktop.get_by_text('Проверить запрос покупателей:',exact=False).first.wait_for()
                desktop.screenshot(path=str(QA/'r18-hypotheses-desktop.png'),full_page=True)
                desktop.locator('#hypothesis-state textarea').fill('Проверяем наличие размера и качество зарегистрированных ответов')
                desktop.locator('#hypothesis-state button[type=submit]').click()
                desktop.get_by_text('Статус и история сохранены').wait_for(timeout=15000)
                desktop.get_by_role('tab',name='03 / Пилоты').click()
                desktop.locator('#pilot-create button[type=submit]').click()
                desktop.get_by_text('Черновик пилота создан').wait_for(timeout=15000)
                desktop.screenshot(path=str(QA/'r18-pilot-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='04 / Исполнение').click()
                desktop.locator('#task-create button[type=submit]').click()
                desktop.get_by_text('Задача назначена').wait_for(timeout=15000)
                desktop.screenshot(path=str(QA/'r18-tasks-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='05 / Контроль').click()
                desktop.get_by_text('Карта управленческих решений').wait_for()
                desktop.screenshot(path=str(QA/'r18-board-desktop.png'),full_page=True)
                with desktop.expect_download(timeout=15000) as download:
                    desktop.locator('#bridge-export').click()
                assert download.value.suggested_filename=='osmanx-decision-bridge.csv'
                assert not errors,errors
                desktop.close()

                mobile,errors=screen(390,844)
                mobile.screenshot(path=str(QA/'r18-signals-mobile.png'),full_page=True)
                mobile.get_by_role('tab',name='02 / Гипотезы').click()
                mobile.screenshot(path=str(QA/'r18-hypotheses-mobile.png'),full_page=True)
                mobile.get_by_role('tab',name='05 / Контроль').click()
                mobile.screenshot(path=str(QA/'r18-board-mobile.png'),full_page=True)
                dims=mobile.evaluate('({width:document.documentElement.scrollWidth,viewport:innerWidth})')
                assert dims['width']<=dims['viewport']+2,dims
                assert not errors,errors
                mobile.close()
                with database.connect() as db:
                    assert db.execute('SELECT COUNT(*) FROM bridge_hypotheses_r18').fetchone()[0]==1
                    assert db.execute('SELECT COUNT(*) FROM bridge_tasks_r18').fetchone()[0]==1
                    assert db.execute('SELECT COUNT(*) FROM pilots_r15').fetchone()[0]==1
                print('R1.8 browser: SIGNAL -> HYPOTHESIS -> PILOT -> TASK -> BOARD/CSV + mobile 390: PASS')
            finally:browser.close()

if __name__=='__main__':main()
