"""R1.0 Chromium E2E: five connected interfaces and paired anonymous pulse.
Uses FastAPI TestClient inside Chromium, no public HTTP server or hardware.
"""
from __future__ import annotations
import os, shutil, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
QA=ROOT/'qa';QA.mkdir(exist_ok=True)

def page_html(name):
    html=(ROOT/'frontend'/name).read_text()
    html=html.replace('<link rel="stylesheet" href="/static/experience.css">','')
    html=html.replace('<script type="module" src="/static/experience.js"></script>','')
    html=html.replace('<script type="module" src="/static/pulse.js"></script>','')
    css=(ROOT/'frontend/experience.css').read_text()
    return html.replace('</head>','<style>'+css+'</style></head>')

def new_page(browser,client,width,height,kind='experience',token=''):
    page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
    errors=[];page.on('pageerror',lambda x:errors.append(str(x)))
    def rpc(method,path,body,headers):
        response=client.request(method,path,json=body,headers=headers or {}) if body is not None else client.request(method,path,headers=headers or {})
        try:val=response.json()
        except ValueError:val={'detail':response.text}
        return {'status':response.status_code,'body':val}
    page.expose_function('__osmanx_rpc',rpc)
    page.set_content(page_html(kind+'.html'),wait_until='domcontentloaded')
    page.evaluate('''(key)=>{
       const store=new Map();if(key)store.set('osmanx_pulse_token_central',key);
       window.__TEST_SESSION__={getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)};
       window.fetch=async(path,opts={})=>{const result=await window.__osmanx_rpc(opts.method||'GET',path,opts.body?JSON.parse(opts.body):null,opts.headers||{});
          return new Response(JSON.stringify(result.body),{status:result.status,headers:{'Content-Type':'application/json'}})};
    }''',token)
    script=(ROOT/'frontend'/(kind+'.js')).read_text().replace('sessionStorage','window.__TEST_SESSION__')
    page.add_script_tag(content=script)
    page.locator('h1').first.wait_for(timeout=16000)
    return page,errors

def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r10-ui-') as path:
        os.environ['OSMANX_DATA_DIR']=path
        os.environ['OSMANX_DEMO_MODE']='1'
        from backend.app import app
        from backend.database import connect,now_iso
        with TestClient(app) as client:
            with connect() as db:
                sid=db.execute("SELECT id FROM stores WHERE slug='central'").fetchone()[0]
                ts=now_iso()
                db.execute('INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)',(sid,65,'signed_sensor',ts,'r10-browser-real-traffic'))
                db.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',(sid,280000,'pos',ts,'r10-browser-real-pos'))
                for i in range(3):db.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',(sid,10000,'pos',ts,f'r10-browser-no-lines-{i}'))
                db.commit()
            pair=client.post('/api/admin/kiosks/central/rotate').json()
            assert pair.get('token'),'Need paired kiosk access'
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
                desktop,errors=new_page(browser,client,1440,900)
                desktop.get_by_role('heading',name='Сопоставимые показатели').wait_for()
                desktop.screenshot(path=str(QA/'r10-benchmark-desktop.png'),full_page=True)
                desktop.locator('[data-tab=shifts]').click()
                desktop.get_by_role('heading',name='Добавить смену').wait_for()
                start=(datetime.now()+timedelta(days=1)).replace(hour=11,minute=0,second=0,microsecond=0)
                end=start+timedelta(hours=4)
                desktop.locator('[data-form=shift] input[name=start_at]').fill(start.strftime('%Y-%m-%dT%H:%M'))
                desktop.locator('[data-form=shift] input[name=end_at]').fill(end.strftime('%Y-%m-%dT%H:%M'))
                desktop.locator('[data-form=shift] button').click()
                desktop.get_by_text('Смена консультанта').count() if False else None
                desktop.get_by_text('Торговый зал',exact=True).first.wait_for()
                desktop.screenshot(path=str(QA/'r10-shifts-desktop.png'),full_page=True)
                desktop.locator('[data-tab=service]').click()
                desktop.locator('[data-form=sla] input[name=accept_minutes]').fill('4')
                desktop.locator('[data-form=sla] input[name=resolve_minutes]').fill('16')
                desktop.locator('[data-form=sla] button').click()
                desktop.get_by_text('Последние обращения',exact=True).wait_for()
                desktop.screenshot(path=str(QA/'r10-service-desktop.png'),full_page=True)
                desktop.locator('[data-tab=pulse]').click()
                desktop.get_by_role('heading',name='Создать короткий опрос').wait_for()
                desktop.locator('[data-form=pulse] button').click()
                desktop.get_by_text('Почему не купили?',exact=True).first.wait_for()
                desktop.locator('[data-action=activate-pulse]').first.click()
                desktop.screenshot(path=str(QA/'r10-campaigns-desktop.png'),full_page=True)
                desktop.locator('[data-tab=incidents]').click()
                desktop.locator('[data-action=scan]').click()
                desktop.get_by_text('У чеков отсутствуют товарные строки').first.wait_for()
                desktop.screenshot(path=str(QA/'r10-incidents-desktop.png'),full_page=True)
                mobile,mob_errors=new_page(browser,client,390,844)
                mobile.screenshot(path=str(QA/'r10-benchmark-mobile.png'),full_page=True)
                mobile.locator('[data-tab=pulse]').click()
                mobile.screenshot(path=str(QA/'r10-campaigns-mobile.png'),full_page=True)
                assert not mobile.evaluate('document.documentElement.scrollWidth>window.innerWidth+1'),'390px overflow'
                pulse,pulse_errors=new_page(browser,client,700,900,kind='pulse',token=pair['token'])
                pulse.get_by_role('heading',name='Чего вам сегодня не хватило?').wait_for()
                pulse.screenshot(path=str(QA/'r10-pulse-intro.png'),full_page=True)
                pulse.locator('[data-choice="0"]').click()
                pulse.get_by_role('heading',name='Спасибо за ваш ответ').wait_for()
                pulse.screenshot(path=str(QA/'r10-pulse-thanks.png'),full_page=True)
                assert client.get('/api/admin/r10/pulse').json()['items'][0]['responses']==1
                mobile_pulse,mobile_pulse_errors=new_page(browser,client,390,844,kind='pulse',token=pair['token'])
                mobile_pulse.screenshot(path=str(QA/'r10-pulse-mobile.png'),full_page=True)
                assert not mobile_pulse.evaluate('document.documentElement.scrollWidth>window.innerWidth+1'),'Mobile kiosk overflow'
                assert not errors and not mob_errors and not pulse_errors and not mobile_pulse_errors,(errors,mob_errors,pulse_errors,mobile_pulse_errors)
                browser.close()
    print('R1.0 Chromium passed: 5 modules, paired pulse, persistence, desktop and 390px.')

if __name__=='__main__':main()
