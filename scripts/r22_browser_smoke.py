"""Chromium smoke through isolated FastAPI and actual R2.0/R2.2 SQLite rows.
This smoke does not claim full application's GitHub CI or deployment acceptance.
"""
from __future__ import annotations
import sys
import shutil
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'));sys.path.insert(0,str(ROOT/'qa_contracts'))
from test_r20 import site as base_fixture,Principal
from test_r22 import site as release_fixture,approve_day

QA=ROOT/'qa';QA.mkdir(exist_ok=True)

def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r22-') as d:
        base=base_fixture.__wrapped__(Path(d))
        old=next(base)
        stage=release_fixture.__wrapped__(old)
        c,actor,connect=next(stage)
        try:
            approve_day((c,actor,connect),1)
            approve_day((c,actor,connect),3)
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox','--disable-dev-shm-usage'])
                try:
                    def open_page(width,height):
                        page=browser.new_page(viewport={'width':width,'height':height},accept_downloads=True)
                        errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
                        def call(method,url,body,headers):
                            result=c.request(method,url,headers=headers or {},json=body) if body is not None else c.request(method,url,headers=headers or {})
                            return {'status':result.status_code,'body':result.text,'type':result.headers.get('content-type','application/json')}
                        page.expose_function('__bridge',call)
                        html=(ROOT/'frontend/rollout.html').read_text()
                        html=html.replace('<link rel="stylesheet" href="/static/rollout.css">','')
                        html=html.replace('<script src="/static/rollout.js" defer></script>','')
                        html=html.replace('</head>','<style>'+(ROOT/'frontend/rollout.css').read_text()+'</style></head>')
                        page.set_content(html,wait_until='domcontentloaded')
                        page.evaluate('''() => {window.__session={getItem(){return null}};
                          window.fetch=async(url,opt={})=>{const x=await __bridge(opt.method||'GET',url,opt.body?JSON.parse(opt.body):null,opt.headers||{});return new Response(x.body,{status:x.status,headers:{'Content-Type':x.type}})}}''')
                        script=(ROOT/'frontend/rollout.js').read_text().replace('sessionStorage','window.__session')
                        page.add_script_tag(content=script)
                        page.get_by_text('Масштабировать.',exact=False).wait_for(timeout=15000)
                        return page,errors
                    page,errors=open_page(1440,900)
                    page.screenshot(path=str(QA/'r22-waves-desktop.png'),full_page=True)
                    page.locator('#new-wave button').click()
                    page.get_by_text('Операция сохранена').wait_for(timeout=12000)
                    page.get_by_role('tab',name='02 / Филиалы').click()
                    page.locator('#site-form input[name=slug]').fill('central')
                    page.locator('#site-form button').click()
                    page.locator('.wave-card').first.wait_for(timeout=12000)
                    page.screenshot(path=str(QA/'r22-stores-desktop.png'),full_page=True)
                    page.get_by_role('tab',name='03 / Доказательства').click()
                    page.screenshot(path=str(QA/'r22-proof-desktop.png'),full_page=True)
                    page.get_by_role('tab',name='04 / Решения').click()
                    page.locator('#decision textarea').fill('Отправили управленческий план на независимую проверку')
                    page.locator('[data-operation=request-review]').click()
                    page.get_by_text('Операция сохранена').wait_for(timeout=12000)
                    actor['user']=Principal(2,1,'second@org.test','owner')
                    page.locator('[data-operation=approve]').wait_for(timeout=12000)
                    page.locator('#decision textarea').fill('Проверена готовность первой точки по R2.0')
                    page.locator('[data-operation=approve]').click()
                    page.get_by_text('Операция сохранена').wait_for(timeout=12000)
                    page.screenshot(path=str(QA/'r22-approved-desktop.png'),full_page=True)
                    page.locator('[data-operation=advance]').wait_for(timeout=12000)
                    page.locator('#decision textarea').fill('Подтверждён документальный итог первого этапа')
                    page.locator('[data-operation=advance]').click()
                    page.get_by_text('Операция сохранена').wait_for(timeout=12000)
                    page.get_by_role('tab',name='05 / Портфель').click()
                    with page.expect_download(timeout=12000) as download:page.locator('#export').click()
                    assert download.value.suggested_filename=='osmanx-rollout-portfolio.csv'
                    page.screenshot(path=str(QA/'r22-portfolio-desktop.png'),full_page=True)
                    assert errors==[],errors
                    page.close()
                    mobile,errors=open_page(390,844)
                    mobile.screenshot(path=str(QA/'r22-waves-mobile.png'),full_page=True)
                    mobile.get_by_role('tab',name='03 / Доказательства').click()
                    mobile.screenshot(path=str(QA/'r22-proof-mobile.png'),full_page=True)
                    overflow=mobile.evaluate('document.documentElement.scrollWidth>innerWidth+2')
                    assert not overflow,'390px horizontal overflow'
                    assert errors==[],errors
                    mobile.close()
                    print('R2.2 browser checks passed: five tabs, CRUD, independent review, proof, CSV, mobile 390px')
                finally:browser.close()
        finally:
            try:next(stage)
            except StopIteration:pass
            try:next(base)
            except StopIteration:pass

if __name__=='__main__':main()
