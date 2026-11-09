"""Chromium QA with FastAPI TestClient bridge and isolated SQLite, no network server."""
import sys
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'qa_contracts'))
import test_r20


def main():
    qa=ROOT/'qa';qa.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='osmanx-r20-chromium-') as d:
        fixture=test_r20.site.__wrapped__(Path(d))
        client,acting,connect=next(fixture)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox','--disable-dev-shm-usage'])
            try:
                def open_view(width,height):
                    page=browser.new_page(viewport={'width':width,'height':height},accept_downloads=True)
                    errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
                    def exchange(method,path,body,headers):
                        result=client.request(method,path,json=body,headers=headers or {}) if body is not None else client.request(method,path,headers=headers or {})
                        return {'status':result.status_code,'text':result.text,'content_type':result.headers.get('content-type','application/json')}
                    page.expose_function('__server_exchange',exchange)
                    html=(ROOT/'frontend/readiness.html').read_text()
                    html=html.replace('<link rel="stylesheet" href="/static/readiness.css">','')
                    html=html.replace('<script src="/static/readiness.js" defer></script>','')
                    html=html.replace('</head>','<style>'+(ROOT/'frontend/readiness.css').read_text()+'</style></head>')
                    page.set_content(html,wait_until='domcontentloaded')
                    page.evaluate('''()=>{window.__token__={getItem(){return null}};window.fetch=async(path,opt={})=>{
                        const r=await window.__server_exchange(opt.method||'GET',path,opt.body?JSON.parse(opt.body):null,opt.headers||{});
                        return new Response(r.text,{status:r.status,headers:{'Content-Type':r.content_type}});
                    }}''')
                    script=(ROOT/'frontend/readiness.js').read_text().replace('sessionStorage','window.__token__')
                    page.add_script_tag(content=script)
                    page.locator('.hero h1').wait_for(timeout=15000)
                    return page,errors

                desktop,errors=open_view(1440,900)
                desktop.screenshot(path=str(qa/'r20-start-desktop.png'),full_page=True)
                desktop.locator('#start').click()
                desktop.locator('.check-form').first.wait_for(timeout=10000)
                assert desktop.locator('.check-form').count()==8
                for key in test_r20.CHECKS:
                    form=desktop.locator(f'.check-form[data-key="{key}"]')
                    form.locator('button[type=submit]').click()
                    desktop.locator('.check-form').first.wait_for()
                desktop.screenshot(path=str(qa/'r20-checks-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='02 / Калибровка').click()
                for manual,counter in [(100,98),(30,29)]:
                    desktop.locator('#calibration-form input[name=reference_count]').fill(str(manual))
                    desktop.locator('#calibration-form input[name=counter_count]').fill(str(counter))
                    desktop.locator('#calibration-form textarea').fill('Ручной подсчёт и сравнение с датчиком на входе')
                    desktop.locator('#calibration-form button').click()
                    desktop.get_by_text(f'{manual} вручную').wait_for(timeout=10000)
                desktop.screenshot(path=str(qa/'r20-calibration-desktop.png'),full_page=True)
                with connect() as db:
                    stamp=str(test_r20.date.today())+'T12:00:00+00:00'
                    db.execute('INSERT INTO visits(store_id,quantity,source,occurred_at) VALUES(?,?,?,?)',(1,110,'manual',stamp))
                    db.execute('INSERT INTO sales(store_id,occurred_at) VALUES(?,?)',(1,stamp))
                    db.execute('INSERT INTO voice_opens_r17(placement_id,opened_at) VALUES(?,?)',(1,stamp))
                    db.execute('INSERT INTO voice_responses_r17(placement_id,submitted_at) VALUES(?,?)',(1,stamp))
                    db.commit()
                desktop.get_by_role('tab',name='03 / Сверка').click()
                desktop.locator('#reconcile-form textarea').fill('Сверка POS, счётчика и анонимных ответов по дню')
                desktop.locator('#reconcile-form button').click()
                desktop.get_by_text('110').first.wait_for(timeout=10000)
                desktop.screenshot(path=str(qa/'r20-reconciliation-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='04 / Передача').click()
                desktop.locator('#handover-form textarea[name=issues]').fill('Проверили калибровку и расхождений не обнаружили')
                desktop.locator('#handover-form textarea[name=actions]').fill('Продолжить контроль после открытия магазина')
                desktop.locator('#handover-form button').click()
                desktop.locator('.ack-form').wait_for(timeout=10000)
                acting['user']=test_r20.Principal(2,1,'manager@example','manager')
                desktop.locator('.ack-form textarea').fill('Принимающий сотрудник сверил журнал и подпись')
                desktop.locator('.ack-form button').click()
                desktop.get_by_text('Принято',exact=True).first.wait_for(timeout=10000)
                desktop.screenshot(path=str(qa/'r20-handover-desktop.png'),full_page=True)
                desktop.get_by_role('tab',name='05 / Готовность').click()
                desktop.locator('#request-review').click()
                desktop.locator('#review-form').wait_for(timeout=10000)
                acting['user']=test_r20.Principal(1,1,'owner@example','owner')
                desktop.locator('#review-form textarea').fill('Независимая проверка всех документов выполнена')
                desktop.locator('#review-form button').click()
                desktop.locator('#verify').wait_for(timeout=10000)
                desktop.locator('#verify').click()
                desktop.get_by_text('SHA-256 подтверждён').wait_for(timeout=10000)
                desktop.screenshot(path=str(qa/'r20-reviewed-desktop.png'),full_page=True)
                with desktop.expect_download(timeout=15000) as dload:desktop.locator('#csv').click()
                assert dload.value.suggested_filename=='osmanx-store-readiness.csv'
                assert not errors,errors
                desktop.close()
                mobile,errors=open_view(390,844)
                mobile.screenshot(path=str(qa/'r20-start-mobile.png'),full_page=True)
                mobile.get_by_role('tab',name='05 / Готовность').click()
                mobile.screenshot(path=str(qa/'r20-reviewed-mobile.png'),full_page=True)
                viewport=mobile.evaluate('({scroll:document.documentElement.scrollWidth,width:innerWidth})')
                assert viewport['scroll']<=viewport['width']+2,viewport
                assert not errors,errors
                mobile.close()
                with connect() as db:
                    assert db.execute("SELECT COUNT(*) FROM readiness_days_r20 WHERE status='reviewed'").fetchone()[0]==1
                    assert db.execute('SELECT COUNT(*) FROM readiness_calibrations_r20').fetchone()[0]==2
                    assert db.execute('SELECT COUNT(*) FROM readiness_handover_r20 WHERE acknowledged_by IS NOT NULL').fetchone()[0]==1
                print('R2.0 Chromium: 5 tabs + checklist + calibration + reconciliation + handover + sealed review + CSV + mobile PASS')
            finally:
                browser.close()
        try:next(fixture)
        except StopIteration:pass

if __name__=='__main__':main()
