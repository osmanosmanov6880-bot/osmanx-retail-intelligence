"""R0.4 browser acceptance: quality page, POS controls, paired kiosk, mobile."""
from __future__ import annotations

import os
import sys
import tempfile
import shutil
from pathlib import Path

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from scripts.visual_smoke import page_content, javascript
QA=ROOT/'qa'
QA.mkdir(exist_ok=True)


def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r04-browser-') as temp:
        os.environ['OSMANX_DEMO_MODE']='1'
        os.environ['OSMANX_DATA_DIR']=temp
        from backend.app import app
        with TestClient(app) as client, sync_playwright() as play:
            browser=play.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
            def install(viewport,kiosk=False):
                page=browser.new_page(viewport=viewport,device_scale_factor=1)
                errors=[]
                page.on('pageerror',lambda err:errors.append(str(err)))
                def call_api(method,path,payload,headers):
                    r=client.request(method,path,json=payload,headers=headers or {}) if payload is not None else client.request(method,path,headers=headers or {})
                    try:body=r.json()
                    except ValueError:body={'detail':r.text}
                    return {'status':r.status_code,'body':body}
                page.expose_function('__api_call',call_api)
                page.set_content(page_content(),wait_until='domcontentloaded')
                if kiosk:page.evaluate('window.__OSMANX_TEST_PATH__="/kiosk/central"')
                page.evaluate('''() => {const tokens=new Map();window.__OSMANX_SESSION__={getItem:(key)=>tokens.get(key)||null,setItem:(key,val)=>tokens.set(key,val),removeItem:(key)=>tokens.delete(key)};
                    window.fetch=async(path,opts={})=>{const result=await window.__api_call(opts.method||'GET',path,
                        opts.body?JSON.parse(opts.body):null,opts.headers||{});
                        return new Response(JSON.stringify(result.body),{status:result.status,headers:{'Content-Type':'application/json'}})}; }''')
                page.add_script_tag(content=javascript(kiosk=kiosk))
                return page,errors
            page,errors=install({'width':1440,'height':900})
            page.locator('[data-nav="monitor"]').click()
            page.locator('h1').filter(has_text='Контроль качества данных').wait_for(timeout=10000)
            assert page.locator('text=Подписанные датчики').count()>0
            page.screenshot(path=str(QA/'r04-quality-desktop.png'),full_page=True)
            page.locator('[data-nav="integrations"]').click()
            page.locator('#pos-source-form input[name="name"]').fill('Cash register QA')
            page.locator('#pos-source-form button[type="submit"]').click()
            page.get_by_text('Новый источник чеков',exact=True).wait_for(timeout=10000)
            assert page.locator('#entry-dialog .code').inner_text().find('pos_')>=0
            page.locator('#entry-dialog [data-action="close-dialog"]').click()
            page.screenshot(path=str(QA/'r04-pos-integration.png'),full_page=True)
            page.locator('[data-nav="settings"]').click()
            page.once('dialog',lambda dialog:dialog.accept())
            page.locator('[data-action="pair-kiosk"]').click()
            page.locator('#entry-dialog[open]').wait_for(timeout=10000)
            secret_url=page.locator('#entry-dialog textarea').input_value()
            assert '#access=' in secret_url
            page.locator('#entry-dialog [data-action="close-dialog"]').click()
            page.screenshot(path=str(QA/'r04-paired-kiosk-settings.png'),full_page=True)
            assert not errors,errors
            page.close()
            # Browser without a paired key is blocked; entering the key unlocks the local kiosk.
            kiosk,kerrors=install({'width':390,'height':844},kiosk=True)
            kiosk.get_by_text('Подключение терминала').wait_for(timeout=10000)
            kiosk.screenshot(path=str(QA/'r04-kiosk-locked-mobile.png'),full_page=True)
            kiosk.locator('#kiosk-access-form input[name="token"]').fill(secret_url.split('#access=')[1])
            kiosk.locator('#kiosk-access-form button[type="submit"]').click()
            kiosk.locator('[data-kiosk="start"]').wait_for(timeout=10000)
            kiosk.locator('[data-kiosk="start"]').click()
            kiosk.locator('[data-rating="5"]').click()
            kiosk.locator('[data-kiosk="next"]').click()
            kiosk.locator('[data-purchased="yes"]').click()
            kiosk.locator('[data-kiosk="next"]').click()
            kiosk.locator('[data-kiosk="next"]').click()
            kiosk.locator('#kiosk-form [type="submit"]').click()
            kiosk.get_by_text('Спасибо!',exact=True).wait_for(timeout=10000)
            kiosk.screenshot(path=str(QA/'r04-kiosk-complete-mobile.png'),full_page=True)
            assert not kerrors,kerrors
            kiosk.close()
            mobile,merrors=install({'width':390,'height':844})
            mobile.locator('[data-action="menu"]').click()
            mobile.locator('[data-nav="monitor"]').first.click()
            mobile.get_by_text('Контроль качества данных').wait_for(timeout=10000)
            mobile.screenshot(path=str(QA/'r04-quality-mobile.png'),full_page=True)
            assert not merrors,merrors
            mobile.close()
            browser.close()
    print('R0.4 browser PASS: quality desktop/mobile, signed POS configuration, locked and paired kiosk submission')

if __name__=='__main__':main()
