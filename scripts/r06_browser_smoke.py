"""R0.6 desktop + 390px end-to-end Chromium acceptance using real API handlers."""
from __future__ import annotations
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
QA=ROOT/'qa'
QA.mkdir(exist_ok=True)


def page_source():
    page=(ROOT/'frontend/workflows.html').read_text()
    page=re.sub(r'<link[^>]*href="/static/[^\"]+"[^>]*>', '', page)
    page=re.sub(r'<script[^>]*src="/static/workflows.js"[^>]*></script>', '', page)
    css=(ROOT/'frontend/styles.css').read_text()+'\n'+(ROOT/'frontend/workflows.css').read_text()
    return page.replace('</head>','<style>'+css+'</style></head>')


def inject(browser,client,width,height):
    page=browser.new_page(viewport={'width':width,'height':height}, device_scale_factor=1)
    problems=[]
    page.on('pageerror',lambda e:problems.append(str(e)))
    def proxy(method,path,payload,headers):
        r=client.request(method,path,json=payload,headers=headers or {}) if payload is not None else client.request(method,path,headers=headers or {})
        try: content=r.json()
        except ValueError:content={'detail':r.text}
        return {'status':r.status_code,'body':content}
    page.expose_function('__api_call',proxy)
    page.set_content(page_source(),wait_until='domcontentloaded')
    page.evaluate('''() => {
      const values=new Map();window.__OSMANX_SESSION__={getItem:k=>values.get(k)||null,
        setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
      window.fetch=async(p,o={})=>{
        let r=await window.__api_call(o.method||'GET',p,o.body?JSON.parse(o.body):null,o.headers||{});
        return new Response(JSON.stringify(r.body),{status:r.status,headers:{'Content-Type':'application/json'}})
      }
    }''')
    javascript=(ROOT/'frontend/workflows.js').read_text().replace('sessionStorage','window.__OSMANX_SESSION__')
    page.add_script_tag(content=javascript)
    page.get_by_text('От спроса до').wait_for(timeout=10000)
    return page,problems


def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r06-') as base:
        os.environ['OSMANX_DEMO_MODE']='1'
        os.environ['OSMANX_DATA_DIR']=base
        from backend.app import app
        with TestClient(app) as client:
            created=client.post('/api/admin/experiments',json={'slug':'central','title':'Проверить спрос XL',
                'hypothesis':'Дополнительные размеры XL улучшат подтвержденные покупки','metric':'conversion'})
            assert created.status_code==201,created.text
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
                desktop,errors=inject(browser,client,1440,900)
                desktop.screenshot(path=str(QA/'r06-overview-desktop.png'),full_page=True)
                desktop.locator('[data-tab=cases]').click()
                desktop.get_by_text('Взять запрос в работу').wait_for()
                desktop.locator('[data-form=case-create] [name=sku]').fill('JKT-R06-XL')
                desktop.locator('[data-form=case-create] button[type=submit]').click()
                desktop.locator('.wf-row strong').filter(has_text='JKT-R06-XL').first.wait_for(timeout=7000)
                desktop.screenshot(path=str(QA/'r06-demand-desktop.png'),full_page=True)

                desktop.locator('[data-tab=orders]').click()
                desktop.locator('[data-form=order-create] [name=supplier]').fill('Склад OSMANX')
                desktop.locator('[data-form=order-create] [name=reference]').fill('R06-PO-0001')
                desktop.locator('[data-form=order-create] [name=sku]').fill('JKT-R06-XL')
                desktop.locator('[data-form=order-create] [name=product]').fill('Куртка демисезонная')
                desktop.locator('[data-form=order-create] [name=quantity]').fill('2')
                desktop.locator('[data-form=order-create] button[type=submit]').click()
                desktop.get_by_text('R06-PO-0001').first.wait_for(timeout=7000)
                desktop.locator('[data-order-status=ordered]').first.click()
                desktop.locator('[data-form=receive] [name=quantity]').first.fill('2')
                desktop.locator('[data-form=receive] [name=external_id]').first.fill('R06-INVOICE-1')
                desktop.locator('[data-form=receive] button[type=submit]').first.click()
                desktop.get_by_text('Поступил',exact=True).first.wait_for(timeout=7000)
                desktop.screenshot(path=str(QA/'r06-purchasing-desktop.png'),full_page=True)

                desktop.locator('[data-tab=finance]').click()
                desktop.locator('[data-form=sale-item] [name=sku]').fill('JKT-R06-XL')
                desktop.locator('[data-form=sale-item] [name=unit_revenue_rub]').fill('100')
                desktop.locator('[data-form=sale-item] [name=unit_cost_rub]').fill('60')
                desktop.locator('[data-form=sale-item] [name=external_id]').fill('R06-LINE-0001')
                desktop.locator('[data-form=sale-item] button[type=submit]').click()
                desktop.get_by_text('Документированная валовая маржа').first.wait_for()
                desktop.screenshot(path=str(QA/'r06-finance-desktop.png'),full_page=True)
                desktop.locator('[data-tab=evaluations]').click()
                desktop.get_by_text('Измерить гипотезу').wait_for()
                desktop.locator('[data-form=evaluate] button[type=submit]').click()
                desktop.get_by_text('История сравнений').wait_for()
                desktop.screenshot(path=str(QA/'r06-evaluation-desktop.png'),full_page=True)
                assert not errors,errors

                mobile,mobile_errors=inject(browser,client,390,844)
                mobile.screenshot(path=str(QA/'r06-overview-mobile.png'),full_page=True)
                mobile.locator('[data-tab=orders]').click()
                mobile.screenshot(path=str(QA/'r06-purchasing-mobile.png'),full_page=True)
                mobile.locator('[data-tab=evaluations]').click()
                mobile.screenshot(path=str(QA/'r06-evaluation-mobile.png'),full_page=True)
                docwidth=mobile.evaluate('document.documentElement.scrollWidth')
                assert docwidth<=400, 'Mobile screen overflow: '+str(docwidth)
                assert not mobile_errors,mobile_errors
                browser.close()
        print('R0.6 BROWSER PASS: 1440/390px, case creation, order, receipt, SKU margin, comparison')

if __name__=='__main__':main()
