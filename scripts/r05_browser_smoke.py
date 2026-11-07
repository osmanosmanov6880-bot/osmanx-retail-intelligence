"""R0.5 Chromium acceptance of five real commerce UI workflows, without external deployment."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from scripts.visual_smoke import page_content, javascript
QA=ROOT/'qa'
QA.mkdir(exist_ok=True)


def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r05-qa-') as tmp:
        os.environ['OSMANX_DEMO_MODE']='1'
        os.environ['OSMANX_DATA_DIR']=tmp
        from backend.app import app
        with TestClient(app) as client, sync_playwright() as play:
            browser=play.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
            def open_page(width,height):
                page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
                failures=[]
                page.on('pageerror',lambda err:failures.append(str(err)))
                def call_api(method,path,payload,headers):
                    response=client.request(method,path,json=payload,headers=headers or {}) if payload is not None else client.request(method,path,headers=headers or {})
                    try:data=response.json()
                    except ValueError:data={'detail':response.text}
                    return {'status':response.status_code,'body':data}
                page.expose_function('__api_call',call_api)
                page.set_content(page_content(),wait_until='domcontentloaded',timeout=10000)
                page.evaluate('''() => {const tokens=new Map();window.__OSMANX_SESSION__={getItem:(x)=>tokens.get(x)||null,setItem:(x,y)=>tokens.set(x,y),removeItem:(x)=>tokens.delete(x)};
                    window.fetch=async(path,opts={})=>{const r=await window.__api_call(opts.method||'GET',path,opts.body?JSON.parse(opts.body):null,opts.headers||{});
                        return new Response(JSON.stringify(r.body),{status:r.status,headers:{'Content-Type':'application/json'}})};}''')
                page.add_script_tag(content=javascript())
                page.locator('h1').first.wait_for(timeout=15000)
                return page,failures

            desktop,errors=open_page(1440,900)
            desktop.locator('.sidebar [data-nav="demand"]').click()
            desktop.locator('h1').filter(has_text='Невидимый спрос').wait_for()
            # Real matching options, not just a decorative button.
            found=False
            matches=desktop.locator('[data-matches]')
            for i in range(min(matches.count(),35)):
                matches.nth(i).click()
                if desktop.locator('[data-reserve]').count():
                    found=True;break
                desktop.locator('#entry-dialog [data-action="close-dialog"]').click()
            assert found,'Demo fixture should include an available exact-size match.'
            desktop.once('dialog',lambda d:d.accept())
            desktop.locator('[data-reserve]').first.click()
            desktop.locator('h1').filter(has_text='Резервы между филиалами').wait_for(timeout=15000)
            assert desktop.locator('text=Активный резерв').count()>0
            desktop.screenshot(path=str(QA/'r05-reservations-desktop.png'),full_page=True)
            # No phantom sale when reserving merchandise.
            reserve=client.get('/api/admin/reservations?slug=central').json()
            assert reserve and reserve[0]['status']=='held'

            desktop.locator('.sidebar [data-nav="fittings"]').click()
            desktop.locator('h1').filter(has_text='Аналитика примерочных').wait_for()
            desktop.locator('[data-dialog="fitting"]').click()
            desktop.locator('#fitting-form input[name="product"]').fill('Жакет QA')
            desktop.locator('#fitting-form input[name="size"]').fill('M')
            desktop.locator('#fitting-form input[name="trials"]').fill('12')
            desktop.locator('#fitting-form input[name="purchases"]').fill('2')
            desktop.locator('#fitting-form select[name="reason"]').select_option('fit')
            desktop.locator('#fitting-form [type="submit"]').click()
            desktop.get_by_text('Жакет QA',exact=True).wait_for(timeout=15000)
            assert '12' in desktop.locator('.content-grid').inner_text()
            desktop.screenshot(path=str(QA/'r05-fittings-desktop.png'),full_page=True)

            desktop.locator('.sidebar [data-nav="returns"]').click()
            desktop.locator('h1').filter(has_text='Возвраты и причины').wait_for()
            desktop.locator('[data-dialog="return"]').click()
            assert desktop.locator('#return-form select[name="sale_id"] option').count()>0
            desktop.locator('#return-form input[name="item"]').fill('Куртка QA')
            desktop.locator('#return-form input[name="amount_rub"]').fill('100')
            desktop.locator('#return-form select[name="reason"]').select_option('size')
            desktop.locator('#return-form [type="submit"]').click()
            desktop.get_by_text('Куртка QA',exact=True).wait_for(timeout=15000)
            desktop.screenshot(path=str(QA/'r05-returns-desktop.png'),full_page=True)

            desktop.locator('.sidebar [data-nav="pricing"]').click()
            desktop.locator('h1').filter(has_text='Скидки и валовая прибыль').wait_for()
            desktop.locator('[data-dialog="pricing"]').click()
            desktop.locator('#pricing-form input[name="title"]').fill('Акция QA — куртка')
            desktop.locator('#pricing-form input[name="sku"]').fill('QA-COAT')
            desktop.locator('#pricing-form [type="submit"]').click()
            desktop.get_by_text('Акция QA — куртка',exact=True).wait_for(timeout=15000)
            desktop.screenshot(path=str(QA/'r05-pricing-desktop.png'),full_page=True)

            desktop.locator('.sidebar [data-nav="decisions"]').click()
            desktop.locator('h1').filter(has_text='Центр решений').wait_for()
            assert desktop.locator('[data-decision-save]').count()>0
            first_key=desktop.locator('[data-decision-save]').first.get_attribute('data-decision-save')
            desktop.locator(f'[data-decision-status="{first_key}"]').select_option('testing')
            desktop.locator(f'[data-decision-note="{first_key}"]').fill('Пилот: проверяем 7 дней')
            desktop.locator('[data-decision-save]').first.click()
            desktop.get_by_text('Решение сохранено').wait_for(timeout=15000)
            assert desktop.locator(f'[data-decision-status="{first_key}"]').input_value()=='testing'
            desktop.screenshot(path=str(QA/'r05-decisions-desktop.png'),full_page=True)
            assert not errors,errors
            desktop.close()

            mobile,errors=open_page(390,844)
            mobile.locator('[data-action="menu"]').click()
            mobile.locator('.sidebar [data-nav="fittings"]').click()
            mobile.locator('h1').filter(has_text='Аналитика примерочных').wait_for(timeout=15000)
            mobile.screenshot(path=str(QA/'r05-fittings-mobile.png'),full_page=True)
            mobile.locator('[data-action="menu"]').click()
            mobile.locator('.sidebar [data-nav="decisions"]').click()
            mobile.locator('h1').filter(has_text='Центр решений').wait_for(timeout=15000)
            mobile.screenshot(path=str(QA/'r05-decisions-mobile.png'),full_page=True)
            # Important layout check: no document-wide horizontal scrollbar at phone width.
            size=mobile.evaluate('({documentWidth:document.documentElement.scrollWidth,windowWidth:window.innerWidth})')
            assert size['documentWidth']<=size['windowWidth']+2,size
            assert not errors,errors
            mobile.close()
            browser.close()
    print('R0.5 Chromium PASS: reservation, fitting, return, margin scenario, decision persistence and 390px mobile')

if __name__=='__main__':
    main()
