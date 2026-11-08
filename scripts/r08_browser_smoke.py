"""R0.8 Chromium integration: actual form actions backed by FastAPI TestClient.

No public URL, no claimed real POS/camera integrations. Saves real screenshots.
"""
import os
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


def html():
    page=(ROOT/'frontend/strategy.html').read_text(encoding='utf-8')
    page=page.replace('<link rel="stylesheet" href="/static/operations.css" />','').replace('<link rel="stylesheet" href="/static/strategy.css" />','')
    page=page.replace('<script type="module" src="/static/strategy.js"></script>','')
    css=(ROOT/'frontend/operations.css').read_text(encoding='utf-8')+(ROOT/'frontend/strategy.css').read_text(encoding='utf-8')
    return page.replace('</head>',f'<style>{css}</style></head>')


def open_page(browser,client,width,height):
    page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1,accept_downloads=True)
    errors=[]
    page.on('pageerror',lambda err:errors.append(str(err)))
    def rpc(method,path,payload,headers):
        resp=client.request(method,path,json=payload,headers=headers or {}) if payload is not None else client.request(method,path,headers=headers or {})
        try:body=resp.json();typ='application/json'
        except ValueError:body=resp.text;typ=resp.headers.get('content-type','text/plain')
        return {'status':resp.status_code,'body':body,'content_type':typ}
    page.expose_function('__rpc',rpc)
    page.set_content(html(),wait_until='domcontentloaded')
    page.evaluate('''() => {
      const items=new Map();window.__TEST_SESSION__={getItem:k=>items.get(k)||null,setItem:(k,v)=>items.set(k,v),removeItem:k=>items.delete(k)};
      window.fetch=async(path,opts={})=>{
        const r=await window.__rpc(opts.method||'GET',path,opts.body?JSON.parse(opts.body):null,opts.headers||{});
        return new Response(typeof r.body==='string'?r.body:JSON.stringify(r.body),{status:r.status,headers:{'Content-Type':r.content_type}})
      }
    }''')
    script=(ROOT/'frontend/strategy.js').read_text(encoding='utf-8').replace('sessionStorage','window.__TEST_SESSION__')
    page.add_script_tag(content=script)
    try:
        page.get_by_role('heading',name='Умный магазин. Измеримые действия.').wait_for(timeout=10000)
    except Exception:
        print('FRONTEND_ERRORS',errors,'PAGE_TEXT',page.locator('body').inner_text()[:2000])
        raise
    return page,errors


def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r08-browser-') as temp:
        os.environ['OSMANX_DEMO_MODE']='1'
        os.environ['OSMANX_DATA_DIR']=temp
        from backend.app import app
        from backend.database import connect,now_iso
        with TestClient(app) as client:
            with connect() as db:
                sid=db.execute("SELECT id FROM stores WHERE slug='central'").fetchone()[0]
                db.execute('INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                  (sid,'OX-COAT-XL','Куртка демисезонная','XL','чёрный',0,'manual',now_iso()))
                db.execute('INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                  (sid,'OX-HOOD-M','Худи оверсайз','M','графит',0,'manual',now_iso()))
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fitting_observations'").fetchone():
                    db.execute('INSERT INTO fitting_observations(store_id,product,size,trials,purchases,reason,observed_at,created_at) VALUES(?,?,?,?,?,?,?,?)',
                     (sid,'Куртка демисезонная','XL',10,1,'fit',now_iso(),now_iso()))
                else:
                    db.execute('INSERT INTO fittings(organization_id,store_id,sku,quantity,outcome,reason,occurred_at) VALUES(?,?,?,?,?,?,?)',
                     (1,sid,'OX-COAT-XL',10,'not_purchased','fit',now_iso()))
                db.commit()
            with sync_playwright() as play:
                browser=play.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
                page,errors=open_page(browser,client,1440,900)
                page.screenshot(path=str(QA/'r08-brief-desktop.png'),full_page=True)
                # Replenishment preview and a purchase-order draft.
                page.locator('[data-tab=replenishment]').click()
                page.get_by_role('heading',name='Рекомендуемые позиции').wait_for(timeout=10000)
                assert 'JEAN-BLU-32' in page.locator('#strategy-view').inner_text()
                page.screenshot(path=str(QA/'r08-replenishment-desktop.png'),full_page=True)
                page.locator('[data-form=plan] button[type=submit]').click()
                page.get_by_text('План №1').wait_for(timeout=10000)
                page.locator('[data-action=show-order]').first.click()
                page.locator('[data-order="1"] [name=supplier]').fill('Мануфактура')
                page.locator('[data-order="1"] [name^=cost_]').first.fill('1750.00')
                for inp in page.locator('[data-order="1"] [name^=cost_]').all():inp.fill('1750.00')
                page.locator('[data-order="1"] button[type=submit]').click()
                page.get_by_text('заказ 1').wait_for(timeout=10000)
                assert client.get('/api/admin/workflows/overview').json()['orders'][0]['status']=='draft'
                # Supplier review and fitting diagnosis.
                page.locator('[data-tab=suppliers]').click()
                page.locator('.strategy-row strong').filter(has_text='Мануфактура').first.wait_for(timeout=10000)
                page.locator('[data-form=review] [name=rating]').select_option('4')
                page.locator('[data-form=review] [name=issue]').fill('Проверить плановый срок по накладной')
                page.locator('[data-form=review] button').click()
                page.get_by_text('Оценка 4/5').first.wait_for(timeout=10000)
                page.screenshot(path=str(QA/'r08-suppliers-desktop.png'),full_page=True)
                page.locator('[data-tab=fittings]').click()
                page.get_by_text('10 примерок').first.wait_for(timeout=10000) if page.get_by_text('10 примерок').count() else None
                page.locator('[data-form=fitting] [name=product]').fill('Куртка демисезонная')
                page.locator('[data-form=fitting] [name=size]').fill('XL')
                page.locator('[data-form=fitting] [name=hypothesis]').fill('Проверить посадку размера XL на следующих примерках')
                page.locator('[data-form=fitting] button').click()
                page.get_by_text('Проверить посадку размера XL').first.wait_for(timeout=10000)
                page.screenshot(path=str(QA/'r08-fittings-desktop.png'),full_page=True)
                # Manager task: begin, evidence-backed completion, durable DB.
                page.locator('[data-tab=tasks]').click()
                page.locator('[data-form=task] [name=title]').fill('Проверить посадку товара и размеры')
                page.locator('[data-form=task] [name=category]').select_option('fitting')
                page.locator('[data-form=task] button').click()
                page.get_by_text('Проверить посадку товара и размеры').first.wait_for(timeout=10000)
                page.locator('[data-action=task-start]').first.click()
                page.get_by_text('in_progress').first.wait_for(timeout=10000)
                page.on('dialog',lambda d:d.accept('Сверены примерки и обновлена карточка размера'))
                page.locator('[data-action=task-done]').first.click()
                page.get_by_text('Сверены примерки').first.wait_for(timeout=10000)
                page.screenshot(path=str(QA/'r08-tasks-desktop.png'),full_page=True)
                # Snapshot is immutable and visible in archive.
                page.locator('[data-tab=brief]').click()
                page.locator('[data-action=snapshot]').click()
                page.get_by_text('Дневной отчёт сохранён').first.wait_for(timeout=10000)
                page.locator('[data-action=snapshots]').click()
                page.locator('#snapshot-history').get_by_text('SHA-256').first.wait_for(timeout=10000)
                page.screenshot(path=str(QA/'r08-brief-snapshot.png'),full_page=True)
                assert not errors,errors
                page.close()
                # Mobile: render all five sections, verify overflow and JS errors.
                mobile,errors2=open_page(browser,client,390,844)
                for tab,name in [('brief','r08-brief-mobile.png'),('replenishment','r08-replenishment-mobile.png'),('suppliers','r08-suppliers-mobile.png'),('fittings','r08-fittings-mobile.png'),('tasks','r08-tasks-mobile.png')]:
                    mobile.locator('[data-tab='+tab+']').click()
                    mobile.locator('#strategy-view .card').first.wait_for(timeout=10000)
                    mobile.screenshot(path=str(QA/name),full_page=True)
                    bounds=mobile.evaluate('''() => ({scroll:document.documentElement.scrollWidth,viewport:window.innerWidth})''')
                    assert bounds['scroll']<=bounds['viewport']+2,(tab,bounds)
                assert not errors2,errors2
                browser.close()
    print('R0.8 Chromium: five end-to-end workflows, snapshots and 390px responsive screens passed')

if __name__=='__main__':main()
