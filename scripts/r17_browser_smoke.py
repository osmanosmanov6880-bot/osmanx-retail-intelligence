"""R1.7 Chromium acceptance: live FastAPI TestClient + SQLite, no public server."""
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
    with tempfile.TemporaryDirectory(prefix='osmanx-r17-browser-') as tmp:
        os.environ['OSMANX_DEMO_MODE']='1'
        os.environ['OSMANX_DATA_DIR']=tmp
        import backend.database as database
        import backend.app as module
        importlib.reload(database);importlib.reload(module)
        with TestClient(module.app) as client, sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,
                args=['--no-sandbox','--disable-dev-shm-usage'])
            try:
                def open_screen(stem,width=1440,height=900,fragment=''):
                    page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1,
                                           accept_downloads=True)
                    errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
                    def call_api(method,path,body,headers):
                        res=client.request(method,path,json=body,headers=headers or {}) if body is not None else client.request(method,path,headers=headers or {})
                        return {'status':res.status_code,'text':res.text,'type':res.headers.get('content-type','application/json')}
                    page.expose_function('__api_call',call_api)
                    html=(ROOT/f'frontend/{stem}.html').read_text(encoding='utf-8')
                    html=html.replace('<link rel="stylesheet" href="/static/voice.css">','')
                    html=html.replace(f'<script type="module" src="/static/{stem}.js"></script>','')
                    html=html.replace('</head>','<style>'+(ROOT/'frontend/voice.css').read_text(encoding='utf-8')+'</style></head>')
                    page.set_content(html,wait_until='domcontentloaded')
                    if fragment:page.evaluate('(hash)=>{location.hash=hash}',fragment)
                    page.evaluate('''() => {window.fetch=async(path,opts={})=>{
                       const r=await window.__api_call(opts.method||'GET',path,opts.body?JSON.parse(opts.body):null,opts.headers||{});
                       return new Response(r.text,{status:r.status,headers:{'Content-Type':r.type}});
                    };}''')
                    page.evaluate("window.__OSMANX_SESSION__={getItem(){return null},setItem(){},removeItem(){}};window.__OSMANX_ORIGIN__='http://testserver'")
                    script=(ROOT/f'frontend/{stem}.js').read_text(encoding='utf-8').replace('sessionStorage','window.__OSMANX_SESSION__')
                    page.add_script_tag(content=script)
                    return page,errors

                manager,errors=open_screen('voice')
                manager.locator('.hero h1').wait_for(timeout=15000)
                manager.screenshot(path=str(QA/'r17-manager-desktop.png'),full_page=True)
                assert manager.get_by_role('tab').count()==5
                manager.locator('[data-do="save-form"]').click()
                manager.get_by_text('Черновик сохранён').wait_for(timeout=15000)
                assert manager.get_by_text('Редактор анкеты №').count()>0
                manager.locator('[data-do="publish"]').first.click()
                manager.get_by_text('Новая версия анкеты опубликована').wait_for(timeout=15000)
                manager.get_by_role('tab',name='02 / Терминалы').click()
                manager.locator('#placement-form input[name=name]').fill('Планшет у выхода')
                manager.locator('#placement-form button[type=submit]').click()
                manager.locator('#pair-link').wait_for(timeout=15000)
                link=manager.locator('#pair-link').input_value()
                assert '/static/voice_kiosk.html#' in link,link
                fragment=link.partition('#')[2]
                manager.screenshot(path=str(QA/'r17-placements-desktop.png'),full_page=True)
                with manager.expect_download() as qr_download:
                    manager.locator('[data-do=qr]').click()
                assert qr_download.value.suggested_filename=='osmanx-voice-qr.svg'
                manager.get_by_role('tab',name='03 / Опросник').click()
                assert manager.get_by_text('Опрос без регистрации').count()>0

                for i in range(3):
                    kiosk,kerrors=open_screen('voice_kiosk',width=900,height=950,fragment=fragment)
                    kiosk.locator('.kiosk-title').wait_for(timeout=15000)
                    assert 'покупку' in kiosk.locator('.kiosk-title').inner_text().lower()
                    kiosk.locator('[data-value="no"]').click()
                    kiosk.locator('#next-voice').click()
                    kiosk.locator('[data-value="size"]').click()
                    kiosk.locator('#next-voice').click()
                    kiosk.locator('[data-value="4"]').click()
                    kiosk.locator('#next-voice').click()
                    kiosk.get_by_text('Ваше мнение',exact=False).first.wait_for(timeout=15000)
                    assert kiosk.locator('#new-voice').count()==1
                    if i==0:kiosk.screenshot(path=str(QA/'r17-kiosk-complete-desktop.png'),full_page=True)
                    assert not kerrors,kerrors
                    kiosk.close()

                manager.get_by_role('tab',name='04 / Аналитика').click()
                manager.locator('h2').get_by_text('Аналитика ответов').wait_for(timeout=12000)
                # Change tab does not refetch; reload the manager after kiosk entries.
                manager.close();manager,errors=open_screen('voice')
                manager.locator('.hero h1').wait_for(timeout=15000)
                manager.get_by_role('tab',name='04 / Аналитика').click()
                assert manager.get_by_text('Не нашёл размер').count()>0
                manager.screenshot(path=str(QA/'r17-insights-desktop.png'),full_page=True)
                with manager.expect_download() as download:
                    manager.locator('[data-do="csv"]').click()
                assert download.value.suggested_filename=='osmanx-voice-insights.csv'
                manager.get_by_role('tab',name='05 / Решения').click()
                manager.locator('#action-form button[type=submit]').click()
                manager.get_by_text('Задача и подтверждение выборки сохранены').wait_for(timeout=15000)
                manager.locator('[data-do="change-action"][data-status="investigating"]').click()
                manager.locator('#action-status-form textarea[name=note]').fill('Проверили наличие и заказали нужные размеры')
                manager.locator('#action-status-form button[type=submit]').click()
                manager.get_by_text('Статус обновлён с записью в журнал').wait_for(timeout=15000)
                manager.screenshot(path=str(QA/'r17-actions-desktop.png'),full_page=True)
                assert not errors,errors

                mobile,merrors=open_screen('voice',width=390,height=844)
                mobile.locator('.hero h1').wait_for(timeout=12000)
                mobile.screenshot(path=str(QA/'r17-manager-mobile.png'),full_page=True)
                mobile.get_by_role('tab',name='04 / Аналитика').click()
                mobile.screenshot(path=str(QA/'r17-insights-mobile.png'),full_page=True)
                width=mobile.evaluate('({page:document.documentElement.scrollWidth,viewport:innerWidth})')
                assert width['page']<=width['viewport']+2,width
                assert not merrors,merrors
                mobile.close()

                kiosk,merrors=open_screen('voice_kiosk',width=390,height=844,fragment=fragment)
                kiosk.locator('.kiosk-title').wait_for(timeout=12000)
                kiosk.screenshot(path=str(QA/'r17-kiosk-mobile.png'),full_page=True)
                width=kiosk.evaluate('({page:document.documentElement.scrollWidth,viewport:innerWidth})')
                assert width['page']<=width['viewport']+2,width
                assert not merrors,merrors
                kiosk.close()
                with database.connect() as conn:
                    assert conn.execute('SELECT COUNT(*) FROM voice_forms_r17').fetchone()[0]==1
                    assert conn.execute('SELECT COUNT(*) FROM voice_placements_r17').fetchone()[0]==1
                    assert conn.execute('SELECT COUNT(*) FROM voice_responses_r17').fetchone()[0]==3
                    assert conn.execute('SELECT COUNT(*) FROM voice_actions_r17').fetchone()[0]==1
                print('R1.7 Chromium: builder, publish, paired kiosk, 3 surveys, insights, CSV, evidenced action, 390px mobile: PASS')
            finally:
                browser.close()

if __name__=='__main__':main()
