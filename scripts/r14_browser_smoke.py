"""Offline Chromium acceptance for R1.4 through FastAPI TestClient bridge."""
import os, sys, tempfile, importlib, re
from pathlib import Path
from playwright.sync_api import sync_playwright
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))

def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r13-') as temp:
        os.environ['OSMANX_DEMO_MODE']='1';os.environ['OSMANX_DATA_DIR']=temp
        import backend.database as database
        import backend.app as module
        importlib.reload(database);importlib.reload(module)
        html=(ROOT/'frontend/integrity.html').read_text()
        css=(ROOT/'frontend/integrity.css').read_text()
        html=re.sub(r'<link[^>]+integrity\.css[^>]*>',f'<style>{css}</style>',html)
        html=re.sub(r'<script[^>]+integrity\.js[^>]*></script>','',html)
        script=(ROOT/'frontend/integrity.js').read_text().replace('sessionStorage','window.__OSMANX_SESSION__')
        with TestClient(module.app) as client,sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
            def open_page(width,height):
                page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                def api_bridge(method,path,payload,headers):
                    result=client.request(method,path,json=payload,headers=headers) if payload is not None else client.request(method,path,headers=headers)
                    try:body=result.json()
                    except ValueError:body={'detail':result.text}
                    return {'status':result.status_code,'body':body}
                page.expose_function('__api',api_bridge)
                page.set_content(html,wait_until='domcontentloaded')
                page.evaluate('''() => {window.fetch=async(path,options={})=>{const r=await window.__api(options.method||'GET',path,options.body?JSON.parse(options.body):null,options.headers||{});return new Response(JSON.stringify(r.body),{status:r.status,headers:{'Content-Type':'application/json'}})}}''')
                page.evaluate("window.__OSMANX_SESSION__={getItem:()=>null,setItem:()=>{},removeItem:()=>{}}")
                page.add_script_tag(content=script)
                page.get_by_text('Данные под контролем.').wait_for()
                return page,errors
            page,errors=open_page(1440,900)
            page.get_by_role('tab',name='Очередь кассы').click()
            page.locator('input[name=external_id]').fill('qa-receipt-1')
            page.locator('form button[type=submit]').click()
            page.get_by_text('qa-receipt-1').wait_for()
            page.get_by_role('tab',name='Сверка').click()
            page.get_by_text('Не найдено',exact=True).first.wait_for()
            page.get_by_role('tab',name='Расходы').click()
            page.locator('input[name=reference]').fill('qa-gift-1')
            page.locator('input[name=campaign]').fill('Неделя магазина')
            page.locator('input[name=cost_kopeks]').fill('1000')
            page.locator('textarea[name=note]').fill('Документ выдачи проверен')
            page.locator('form button[type=submit]').click()
            page.get_by_text('qa-gift-1').wait_for()
            page.get_by_role('tab',name='Отклонения').click()
            page.locator('#sync').click()
            page.get_by_text('Кассовые события без зарегистрированного чека').wait_for()
            page.get_by_role('tab',name='Директор').click()
            qa=ROOT/'qa';qa.mkdir(exist_ok=True)
            page.screenshot(path=str(qa/'r14-integrity-desktop.png'),full_page=True)
            mobile,errors_mobile=open_page(390,844)
            assert mobile.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
            mobile.screenshot(path=str(qa/'r14-integrity-mobile.png'),full_page=True)
            assert not errors and not errors_mobile,(errors,errors_mobile)
            browser.close()
            print('R1.4 Chromium: five sections, persistent writes, 1440px / 390px OK')
if __name__=='__main__':main()
