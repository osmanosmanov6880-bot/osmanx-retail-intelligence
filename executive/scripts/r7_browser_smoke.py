#!/usr/bin/env python3
"""R7 Chromium E2E: 5 real screens, 4 widths, financial controls, CSV/PDF, state and legacy protection."""
from pathlib import Path
import os, socket, subprocess, time
from playwright.sync_api import sync_playwright
BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'screenshots';OUT.mkdir(exist_ok=True)
PORT=4197
server=subprocess.Popen(['python3','-m','http.server',str(PORT),'--bind','127.0.0.1'],cwd=BASE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            with socket.create_connection(('127.0.0.1',PORT),timeout=.3):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError('R7 local HTTP server unavailable')
    with sync_playwright() as p:
        options={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage']}
        if os.getenv('OSMANX_LOCAL_CHROMIUM'):options['executable_path']=os.environ['OSMANX_LOCAL_CHROMIUM']
        browser=p.chromium.launch(**options)
        js_errors=[]
        routes=['evidence-gate','network-rebalance','capital-lab','privacy-lab','executive-brief']
        for width in (390,768,1440,1920):
            page=browser.new_page(viewport={'width':width,'height':920})
            page.on('pageerror',lambda err:js_errors.append(str(err)))
            page.goto(f'http://127.0.0.1:{PORT}/',wait_until='networkidle')
            for route in routes:
                page.evaluate('(r)=>window.__OSMANX_DIAGNOSTICS__.navigate(r)',route)
                page.wait_for_selector('main .r7-head')
                assert page.locator('main h1').count()==1,(width,route,'no unique H1')
                assert page.locator('main .r7-demo-stamp').is_visible(),(width,route,'missing demo watermark')
                dims=page.evaluate('({scroll:document.documentElement.scrollWidth,viewport:innerWidth})')
                assert dims['scroll']<=dims['viewport']+1,(width,route,dims)
                if width in (390,1440):page.screenshot(path=str(OUT/f'r7_{route}_{width}.png'),full_page=True)
            page.close()
        print('PASS R7 5 pages x 4 viewports: no horizontal overflow')
        page=browser.new_page(viewport={'width':1440,'height':900},accept_downloads=True)
        page.on('pageerror',lambda err:js_errors.append(str(err)))
        page.goto(f'http://127.0.0.1:{PORT}/',wait_until='networkidle')
        initial_revenue=page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')
        # 1: evidence gate changes immediately while preserving input focus
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("evidence-gate")')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r7.gate.ready') is True
        page.locator('[data-r7-field="gateRequests"]').fill('999')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r7.gate.ready') is False
        page.locator('[data-r7-field="gateRequests"]').fill('10')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r7.gate.ready') is True
        with page.expect_download() as x:page.locator('[data-action="r7-gate-csv"]').click()
        x.value.save_as(str(OUT/'r7_gate.csv'))
        assert 'Уникальность' in (OUT/'r7_gate.csv').read_text('utf-8-sig')
        page.locator('[data-action="r7-gate-task"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='action-board'
        print('PASS R7 gate: live quality blocking, evidence export and assigned task')
        # 2: real scenario controls, unique bounded source stock and CSV
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("network-rebalance")')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r7.network.routes')>0
        page.locator('[data-r7-field="moveProbability"]').fill('0')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r7.network.routes')==0
        page.locator('[data-r7-field="moveProbability"]').fill('90')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r7.network.routes')>0
        page.locator('[data-action="r7-move-select"]').first.click()
        with page.expect_download() as x:page.locator('[data-action="r7-move-csv"]').click()
        x.value.save_as(str(OUT/'r7_routes.csv'))
        assert 'Затраты' in (OUT/'r7_routes.csv').read_text('utf-8-sig')
        page.locator('[data-action="r7-move-task"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='action-board'
        print('PASS R7 network: probability guard, stock-constrained routes, export and task')
        # 3: capital planning budget and scenario assertions
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("capital-lab")')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r7.capital.selected')>0
        page.locator('[data-r7-field="capitalBudget"]').fill('0')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r7.capital.selected')==0
        page.locator('[data-r7-field="capitalBudget"]').fill('12000')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r7.capital.selected')>0
        with page.expect_download() as x:page.locator('[data-action="r7-capital-csv"]').click()
        x.value.save_as(str(OUT/'r7_portfolio.csv'))
        page.locator('[data-action="r7-capital-task"]').click()
        print('PASS R7 capital: budget limits, optimal scenario, export and task')
        # 4: privacy sandbox retention preview, no identifiers in exported aggregate
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("privacy-lab")')
        eligible=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r7.privacy.retained')
        page.locator('[data-r7-field="privacyRetention"]').fill('1')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r7.privacy.retained')<=eligible
        page.locator('[data-r7-field="privacyConsent"]').select_option('any')
        page.locator('[data-action="r7-privacy-apply"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r7.privacy.entries')==1
        with page.expect_download() as x:page.locator('[data-action="r7-privacy-csv"]').click()
        x.value.save_as(str(OUT/'r7_privacy.csv'))
        csv=(OUT/'r7_privacy.csv').read_text('utf-8-sig')
        assert 'Событий' in csv and 'req-14-' not in csv and 'pre-1' not in csv
        page.reload(wait_until='networkidle')
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("privacy-lab")')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r7.privacy.entries')==1
        print('PASS R7 privacy: retention, consent policy, anonymized CSV and reload')
        # 5: source-bound brief exports actual A4 PDF, no invented integration
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("executive-brief")')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r7.brief.claims')==5
        assert page.locator('main .r7-claims article').count()==5
        assert page.locator('main').get_by_text('Демонстрационные данные',exact=False).count()>0
        with page.expect_download() as x:page.locator('[data-action="r7-brief-csv"]').click()
        x.value.save_as(str(OUT/'r7_brief.csv'))
        with page.expect_download() as x:page.locator('[data-action="r7-brief-pdf"]').click()
        x.value.save_as(str(OUT/'r7_evidence.pdf'))
        blob=(OUT/'r7_evidence.pdf').read_bytes()
        assert blob.startswith(b'%PDF-1.4') and len(blob)>12000
        assert b'/Count 1' in blob
        page.locator('[data-action="r7-brief-task"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r6.board.total')>=4
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')==initial_revenue
        print('PASS R7 brief: labeled claims, real PDF, CSV, journal and no financial mutation')
        page.goto(f'http://127.0.0.1:{PORT}/OSMANX_EXECUTIVE_OFFLINE.html',wait_until='networkidle')
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("executive-brief")')
        assert page.locator('main .r7-head').count()==1
        assert not js_errors,js_errors
        print('PASS R7 standalone: all screens delivered with no JavaScript errors')
        browser.close()
finally:
    server.terminate()
    try:server.wait(timeout=5)
    except subprocess.TimeoutExpired:server.kill()
