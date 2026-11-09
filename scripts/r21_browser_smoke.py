"""R2.1 Chromium QA using actual FastAPI TestClient and isolated SQLite.

Browser fetch is bridged to the API without public network access. This cannot
replace the full production authorization/integration test suite.
"""
from __future__ import annotations

import sys
import shutil
from datetime import date,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'qa_contracts'))
import test_r21
from test_r20 import Principal


def main():
    qa=ROOT/'qa';qa.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='osmanx-r21-chromium-') as tmp:
        fixture=test_r21.site.__wrapped__(Path(tmp))
        site=next(fixture)
        client,actors,connect=site
        ready_id=test_r21.prepare_reviewed(site)
        pilot_id=test_r21.pilot(site)
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,
                   args=['--no-sandbox','--disable-dev-shm-usage'])
            try:
                def open_ui(width,height):
                    page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1,accept_downloads=True)
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    def exchange(method,url,payload,headers):
                        res=client.request(method,url,json=payload,headers=headers or {}) if payload is not None else client.request(method,url,headers=headers or {})
                        return {'status':res.status_code,'body':res.text,'type':res.headers.get('content-type','application/json')}
                    page.expose_function('__exchange',exchange)
                    html=(ROOT/'frontend/assurance.html').read_text(encoding='utf-8')
                    html=html.replace('<link rel="stylesheet" href="/static/assurance.css">','').replace('<script src="/static/assurance.js" defer></script>','')
                    html=html.replace('</head>','<style>'+(ROOT/'frontend/assurance.css').read_text(encoding='utf-8')+'</style></head>')
                    page.set_content(html,wait_until='domcontentloaded')
                    page.evaluate('''() => {window.__SESSION__={getItem(){return null}};
                        window.fetch=async(path,options={})=>{const r=await window.__exchange(options.method||'GET',path,
                        options.body?JSON.parse(options.body):null,options.headers||{});
                        return new Response(r.body,{status:r.status,headers:{'Content-Type':r.type}})};}''')
                    js=(ROOT/'frontend/assurance.js').read_text().replace('sessionStorage','window.__SESSION__')
                    page.add_script_tag(content=js)
                    page.locator('.hero h1').wait_for(timeout=15000)
                    return page,errors
                desktop,errors=open_ui(1440,900)
                assert desktop.get_by_role('tab').count()==5
                desktop.screenshot(path=str(qa/'r21-portfolio-desktop.png'),full_page=True)
                with desktop.expect_download() as download:
                    desktop.locator('#download-csv').click()
                assert download.value.suggested_filename=='osmanx-store-assurance.csv'
                desktop.get_by_role('tab',name='02 / Калибровка').click()
                desktop.screenshot(path=str(qa/'r21-drift-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='03 / Сверка').click()
                desktop.get_by_text('Сопоставление журналов').first.wait_for(timeout=7000)
                desktop.screenshot(path=str(qa/'r21-continuity-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='05 / Допуск').click()
                desktop.locator('#preflight-form input[name=pilot_id]').fill(str(pilot_id))
                desktop.locator('#preflight-form button').click()
                desktop.get_by_text('Условия программной проверки соблюдены').wait_for(timeout=15000)
                desktop.screenshot(path=str(qa/'r21-preflight-desktop.png'),full_page=True)
                desktop.locator('#safe-start').click()
                desktop.get_by_text('Защищённый запуск пилота').wait_for(timeout=15000)
                with connect() as db:
                    assert db.execute('SELECT status FROM pilots_r15 WHERE id=?',(pilot_id,)).fetchone()['status']=='running'
                    assert db.execute('SELECT COUNT(*) FROM assurance_pilot_starts_r21 WHERE pilot_id=?',(pilot_id,)).fetchone()[0]==1
                # A new unreviewed shift exposes blockers and creates actionable tasks.
                tomorrow=(date.today()+timedelta(days=1)).isoformat()
                res=client.post('/api/admin/r20/days',json={'slug':'central','business_day':tomorrow})
                assert res.status_code==201,res.text
                actors['user']=Principal(2,1,'manager@test','manager')
                desktop.locator('#reload').click()
                desktop.get_by_role('tab',name='04 / Проблемы').click()
                desktop.locator('#sync-tickets').click()
                desktop.get_by_text('Проблемы зарегистрированы').wait_for(timeout=15000)
                assert desktop.locator('[data-assign]').count()>0
                desktop.locator('[data-assign]').first.click()
                form=desktop.locator('.assign-form')
                form.locator('input[name=owner]').fill('Управляющий магазина')
                form.locator('button[type=submit]').click()
                desktop.get_by_text('Ответственный назначен').wait_for(timeout=15000)
                desktop.locator('[data-ticket][data-status=working]').first.click()
                form=desktop.locator('.ticket-form')
                form.locator('textarea[name=note]').fill('Проверяем оборудование и заносим результаты в журнал')
                form.locator('button[type=submit]').click()
                desktop.get_by_text('Переход записан в журнал').wait_for(timeout=15000)
                desktop.screenshot(path=str(qa/'r21-tickets-desktop.png'),full_page=True)
                actors['user']=Principal(1,1,'owner@test','owner')
                desktop.locator('[data-ticket][data-status=verified]').first.click()
                form=desktop.locator('.ticket-form')
                form.locator('textarea[name=note]').fill('Владелец независимо сверил ремонт с журналом')
                form.locator('button[type=submit]').click()
                desktop.get_by_text('Переход записан в журнал').wait_for(timeout=15000)
                desktop.screenshot(path=str(qa/'r21-verified-ticket-desktop.png'),full_page=True)
                assert errors==[],errors
                desktop.close()
                mobile,errors=open_ui(390,844)
                mobile.screenshot(path=str(qa/'r21-portfolio-mobile.png'),full_page=True)
                mobile.get_by_role('tab',name='04 / Проблемы').click()
                mobile.screenshot(path=str(qa/'r21-tickets-mobile.png'),full_page=True)
                overflow=mobile.evaluate('({scroll:document.documentElement.scrollWidth,width:innerWidth})')
                assert overflow['scroll']<=overflow['width']+2,overflow
                assert not errors,errors
                mobile.close()
                print('R2.1 Chromium: portfolio+CSV, drift, continuity, safe-start, two-role ticket workflow, 390px PASS')
            finally:browser.close()
        try:next(fixture)
        except StopIteration:pass

if __name__=='__main__':main()
