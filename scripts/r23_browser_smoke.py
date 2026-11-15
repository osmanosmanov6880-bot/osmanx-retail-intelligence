"""R2.3 actual FastAPI+SQLite->Chromium desktop/mobile acceptance (demo data only)."""
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
QA=ROOT/'qa'
QA.mkdir(exist_ok=True)


def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r23-browser-') as tmp:
        os.environ['OSMANX_DEMO_MODE']='1'
        os.environ['OSMANX_DATA_DIR']=tmp
        os.environ.pop('OSMANX_BACKUP_DIR',None)
        import backend.database as database
        import backend.app as module
        importlib.reload(database);importlib.reload(module)
        with TestClient(module.app) as client,sync_playwright() as play:
            browser=play.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,
                args=['--no-sandbox','--disable-dev-shm-usage'])
            try:
                def screen(width,height):
                    page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1,
                                          accept_downloads=True)
                    errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
                    def api_call(method,path,body,headers):
                        response=client.request(method,path,json=body,headers=headers or {}) if body is not None else client.request(method,path,headers=headers or {})
                        return {'status':response.status_code,'text':response.text,
                                'content_type':response.headers.get('content-type','application/json')}
                    page.expose_function('__r23_api',api_call)
                    html=(ROOT/'frontend/security.html').read_text(encoding='utf-8')
                    html=html.replace('<link rel="stylesheet" href="/static/r23_security.css">','')
                    html=html.replace('<script src="/static/r23_security.js" defer></script>','')
                    css=(ROOT/'frontend/r23_security.css').read_text(encoding='utf-8')
                    html=html.replace('</head>','<style>'+css+'</style></head>')
                    page.set_content(html,wait_until='domcontentloaded')
                    page.evaluate('''() => {window.__R23_TEST_SESSION__={getItem(){return null}};
                        window.fetch=async(path,opts={})=>{let r=await window.__r23_api(opts.method||'GET',path,
                          opts.body?JSON.parse(opts.body):null,opts.headers||{});
                          return new Response(r.text,{status:r.status,headers:{'Content-Type':r.content_type}})};
                    }''')
                    js=(ROOT/'frontend/r23_security.js').read_text(encoding='utf-8').replace('sessionStorage','window.__R23_TEST_SESSION__')
                    page.add_script_tag(content=js)
                    page.get_by_text('Каждое разрешение',exact=False).first.wait_for(timeout=15000)
                    return page,errors
                desktop,errors=screen(1440,900)
                assert desktop.get_by_role('tab').count()==5
                desktop.get_by_text('Коммерческий запуск запрещён').wait_for(timeout=10000)
                desktop.screenshot(path=str(QA/'r23-gate-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='02 / Доступ').click()
                desktop.screenshot(path=str(QA/'r23-access-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='03 / Доказательства').click()
                desktop.screenshot(path=str(QA/'r23-evidence-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='04 / Нарушения').click()
                desktop.screenshot(path=str(QA/'r23-incidents-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='05 / Восстановление').click()
                desktop.get_by_text('Не задан OSMANX_BACKUP_DIR').wait_for(timeout=10000)
                desktop.screenshot(path=str(QA/'r23-recovery-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='01 / Готовность').click()
                with desktop.expect_download(timeout=15000) as download:
                    desktop.locator('#csv-r23').click()
                assert download.value.suggested_filename=='osmanx-security-r23.csv'
                assert errors==[],errors
                desktop.close()
                mobile,merrors=screen(390,844)
                mobile.screenshot(path=str(QA/'r23-gate-mobile.png'),full_page=True)
                mobile.get_by_role('tab',name='05 / Восстановление').click()
                mobile.screenshot(path=str(QA/'r23-recovery-mobile.png'),full_page=True)
                width=mobile.evaluate('({scroll:document.documentElement.scrollWidth,viewport:innerWidth})')
                assert width['scroll']<=width['viewport']+2,width
                assert merrors==[],merrors
                mobile.close()
                print('R2.3 Chromium: five tabs, real API+SQLite, blocked demo, CSV, 1440 and 390px PASS')
            finally:browser.close()

if __name__=='__main__':main()
