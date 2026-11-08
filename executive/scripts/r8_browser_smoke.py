#!/usr/bin/env python3
"""R8 browser acceptance: local CSV intake, audited money, unique stock, consent, owner signoff."""
from pathlib import Path
import os, socket, subprocess, time
from playwright.sync_api import sync_playwright
BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'screenshots';OUT.mkdir(exist_ok=True)
PORT=4208
server=subprocess.Popen(['python3','-m','http.server',str(PORT),'--bind','127.0.0.1'],cwd=BASE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            with socket.create_connection(('127.0.0.1',PORT),timeout=.3):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError('R8 local server unavailable')
    with sync_playwright() as p:
        options={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage']}
        if os.getenv('OSMANX_LOCAL_CHROMIUM'):options['executable_path']=os.environ['OSMANX_LOCAL_CHROMIUM']
        browser=p.chromium.launch(**options)
        problems=[]
        routes=['local-vault','local-ledger','local-availability','local-recovery','local-brief']
        for width in (390,768,1440,1920):
            page=browser.new_page(viewport={'width':width,'height':900})
            page.on('pageerror',lambda err:problems.append(str(err)))
            page.goto(f'http://127.0.0.1:{PORT}/',wait_until='networkidle')
            for route in routes:
                page.evaluate('(r)=>window.__OSMANX_DIAGNOSTICS__.navigate(r)',route)
                page.locator('main .r8-head').wait_for()
                assert page.locator('main h1').count()==1,(route,width)
                assert page.locator('main .r8-origin').is_visible(),(route,width)
                dimensions=page.evaluate('({scroll:document.documentElement.scrollWidth,viewport:innerWidth})')
                assert dimensions['scroll']<=dimensions['viewport']+1,(route,width,dimensions)
                if width in (390,1440):page.screenshot(path=str(OUT/f'r8_{route}_{width}.png'),full_page=True)
            page.close()
        print('PASS R8: five rooms x four widths = 20 viewport checks, no overflow')
        page=browser.new_page(viewport={'width':1440,'height':900},accept_downloads=True)
        page.on('pageerror',lambda err:problems.append(str(err)))
        page.goto(f'http://127.0.0.1:{PORT}/',wait_until='networkidle')
        baseline=page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("local-vault")')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.version')==0
        assert page.locator('main').get_by_text('ФАЙЛЫ НЕ ЗАГРУЖЕНЫ').count()>0
        page.locator('[data-action="r8-sample-all"]').click()
        r=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8')
        assert r['version']==4 and r['example']==True and r['counts']=={'sales':3,'returns':1,'requests':5,'stock':3},r
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')==baseline
        print('PASS R8: 4 separate accepted CSV types, clear sample provenance, demo untouched')
        # Invalid replacement must leave four accepted tables unchanged.
        page.locator('[data-r8-text]').fill('id;date;bad\n1;2026-11-01;x')
        page.locator('[data-action="r8-accept"]').click()
        assert 'Шапка' in page.locator('main .r8-errors').first.inner_text()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.version')==4
        print('PASS R8: invalid atomic replacement blocked without mutation')
        # Finance: 33700 - 8900 = 24800; 24800 -(18100 - 4900) = 11600.
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("local-ledger")')
        r=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.ledger')
        assert r['receipts']==3 and r['net']==24800 and r['gross']==11600,r
        page.locator('[data-r8-field="ledgerStore"]').select_option('store-B')
        assert page.locator('main').get_by_text('0 ₽').count()>0
        page.locator('[data-r8-field="ledgerStore"]').select_option('all')
        with page.expect_download() as dl:page.locator('[data-action="r8-ledger-csv"]').click()
        dl.value.save_as(str(OUT/'r8_local_ledger.csv'))
        assert 'Валовая прибыль' in (OUT/'r8_local_ledger.csv').read_text('utf-8-sig')
        print('PASS R8: linked partial refunds, store drilldown, local CSV export')
        # Availability honors current snapshot, sensitivity changes and unique allocation.
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("local-availability")')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.availability.routes')==3
        page.locator('[data-r8-field="moveReserve"]').fill('2')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.availability.routes')==1
        page.locator('[data-r8-field="moveReserve"]').fill('0')
        page.locator('[data-r8-field="moveProbability"]').fill('0')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.availability.routes')==0
        page.locator('[data-r8-field="moveProbability"]').fill('70')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.availability.routes')==3
        with page.expect_download() as dl:page.locator('[data-action="r8-move-csv"]').click()
        dl.value.save_as(str(OUT/'r8_routes.csv'))
        page.locator('[data-action="r8-move-task"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='action-board'
        print('PASS R8: guarded cross-store stock allocation, live parameters, CSV and decision board')
        # Opt-in only; no message sent; deterministic holdout.
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("local-recovery")')
        pilot=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.pilot')
        assert pilot['candidates']==3 and pilot['test']+pilot['control']==3,pilot
        page.locator('[data-r8-field="lift"]').fill('0')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.pilot.net')<0
        page.locator('[data-r8-field="lift"]').fill('5')
        with page.expect_download() as dl:page.locator('[data-action="r8-pilot-csv"]').click()
        dl.value.save_as(str(OUT/'r8_optin_holdout.csv'))
        content=(OUT/'r8_optin_holdout.csv').read_text('utf-8-sig')
        assert 'q-101' in content and 'q-103' not in content and 'q-104' not in content
        page.locator('[data-action="r8-pilot-task"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='action-board'
        print('PASS R8: consent-only deterministic holdout, no real messaging, task creation')
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("local-brief")')
        assert page.locator('main .r8-claims article').count()==5
        with page.expect_download() as dl:page.locator('[data-action="r8-brief-pdf"]').click()
        dl.value.save_as(str(OUT/'r8_director.pdf'))
        pdf=(OUT/'r8_director.pdf').read_bytes()
        assert pdf.startswith(b'%PDF-1.4') and len(pdf)>12000
        with page.expect_download() as dl:page.locator('[data-action="r8-brief-csv"]').click()
        dl.value.save_as(str(OUT/'r8_director.csv'))
        page.locator('[data-action="r8-brief-save"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.audit')==1
        assert 'q-101' not in page.evaluate("localStorage.getItem('osmanx-r8-aggregate-audit')")
        assert 's-101' not in page.evaluate("localStorage.getItem('osmanx-r8-aggregate-audit')")
        print('PASS R8: generated real A4 PDF, CSV, aggregate-only signoff')
        page.reload(wait_until='networkidle')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.version')==0
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.audit')==1
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')==baseline
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("local-brief")')
        assert page.locator('[data-action="r8-brief-pdf"]').is_disabled()
        page.goto(f'http://127.0.0.1:{PORT}/OSMANX_EXECUTIVE_OFFLINE.html',wait_until='networkidle')
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("local-vault")')
        assert page.locator('main .r8-head').count()==1
        assert page.locator('main').get_by_text('ФАЙЛЫ НЕ ЗАГРУЖЕНЫ').count()>0
        assert not problems,problems
        print('PASS R8: reload destroys raw import while preserving aggregate audit; standalone works; JS errors=0')
        browser.close()
finally:
    server.terminate()
    try:server.wait(timeout=5)
    except subprocess.TimeoutExpired:server.kill()
