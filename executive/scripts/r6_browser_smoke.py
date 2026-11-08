#!/usr/bin/env python3
"""R6 acceptance: live DOM interactions, real CSV downloads and mobile viewports."""
from pathlib import Path
import os, socket, subprocess, time
from playwright.sync_api import sync_playwright
BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'screenshots';OUT.mkdir(exist_ok=True)
PORT=4196
server=subprocess.Popen(['python3','-m','http.server',str(PORT),'--bind','127.0.0.1'],cwd=BASE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(80):
        try:
            with socket.create_connection(('127.0.0.1',PORT),timeout=.3):break
        except OSError:time.sleep(.10)
    else:raise RuntimeError('Local HTTP test server unavailable')
    with sync_playwright() as p:
        options={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage']}
        if os.getenv('OSMANX_LOCAL_CHROMIUM'):options['executable_path']=os.getenv('OSMANX_LOCAL_CHROMIUM')
        browser=p.chromium.launch(**options)
        errors=[]
        routes=['mapping-lab','demand-trace','returns-risk','pilot-design','action-board']
        for w in (390,768,1440,1920):
            page=browser.new_page(viewport={'width':w,'height':920},device_scale_factor=1)
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{PORT}/',wait_until='networkidle')
            for route in routes:
                page.evaluate('(r)=>window.__OSMANX_DIAGNOSTICS__.navigate(r)',route)
                page.wait_for_selector('main .r6-head',timeout=10000)
                assert page.locator('main h1').count()==1,(w,route,'h1 count')
                dims=page.evaluate('({scroll:document.documentElement.scrollWidth,viewport:innerWidth})')
                assert dims['scroll']<=dims['viewport']+1,(w,route,dims)
                assert page.locator('.r6-stamp').is_visible(),(w,route,'demo tag not visible')
                if w in (390,1440):page.screenshot(path=str(OUT/f'r6_{route}_{w}.png'),full_page=True)
            page.close()
        print('PASS R6 responsive five routes x four widths; no horizontal scroll')
        page=browser.new_page(viewport={'width':1440,'height':900},accept_downloads=True)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(f'http://127.0.0.1:{PORT}/',wait_until='networkidle')
        revenue_before=page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("mapping-lab")')
        page.locator('[data-action="r6-mapping-example"]').click()
        assert page.locator('[data-r6-field^="map:"]').count()==7
        page.locator('[data-action="r6-mapping-verify"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r6.mapped') is True
        with page.expect_download() as download:page.locator('[data-action="r6-mapping-export"]').click()
        download.value.save_as(str(OUT/'r6_canonical_sales.csv'))
        assert 'JKT-AURA' in (OUT/'r6_canonical_sales.csv').read_text('utf-8-sig')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')==revenue_before
        print('PASS R6 CSV mapping, atomic contract, export and isolation')
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("demand-trace")')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r6.demand.linked')==7
        previous=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r6.demand.net')
        page.locator('[data-r6-field="demandProbability"]').fill('45')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r6.demand.net')>previous
        page.locator('[data-action="r6-demand-select"]').first.click()
        with page.expect_download() as download:page.locator('[data-action="r6-demand-csv"]').click()
        download.value.save_as(str(OUT/'r6_demand.csv'))
        page.locator('[data-action="r6-demand-task"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='action-board'
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r6.board.total')==1
        print('PASS R6 demand evidence, real recalculation, CSV and task creation')
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("returns-risk")')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r6.returns.returned')>0
        page.locator('[data-r6-field="returnDimension"]').select_option('size')
        assert page.locator('[data-action="r6-return-select"]').count()==5
        page.locator('[data-action="r6-return-select"]').first.click()
        with page.expect_download() as download:page.locator('[data-action="r6-returns-csv"]').click()
        download.value.save_as(str(OUT/'r6_returns.csv'))
        page.locator('[data-action="r6-return-task"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r6.board.total')==2
        print('PASS R6 return cohort, Wilson denominator, CSV and task')
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("pilot-design")')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r6.pilot.needed')>200
        before=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r6.pilot.needed')
        page.locator('[data-r6-field="pilotLift"]').fill('10')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r6.pilot.needed')<before
        with page.expect_download() as download:page.locator('[data-action="r6-pilot-csv"]').click()
        download.value.save_as(str(OUT/'r6_pilot.csv'))
        page.locator('[data-action="r6-pilot-task"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r6.board.total')==3
        print('PASS R6 pilot sample sizing, deterministic allocation and handoff')
        page.locator('[data-action="r6-board-create"]').scroll_into_view_if_needed()
        page.locator('[data-r6-form="title"]').fill('Сверить реальные остатки размера L')
        page.locator('[data-r6-form="due"]').fill('2026-11-12')
        page.locator('[data-r6-form="priority"]').select_option('urgent')
        page.locator('[data-action="r6-board-create"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r6.board.total')==4
        page.locator('[data-action="r6-board-start"]').click()
        page.locator('[data-action="r6-board-review"]').click()
        page.locator('[data-r6-form="outcome"]').fill('Проверка выполнена, пересчитали остаток вручную; причинность не доказана.')
        page.locator('[data-action="r6-board-close"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r6.board.closed')==1
        with page.expect_download() as download:page.locator('[data-action="r6-board-export"]').click()
        download.value.save_as(str(OUT/'r6_board.csv'))
        page.reload(wait_until='networkidle')
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("action-board")')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r6.board.closed')==1
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')==revenue_before
        print('PASS R6 action lifecycle, closing evidence, reload persistence, CSV and untouched demo')
        page.goto(f'http://127.0.0.1:{PORT}/OSMANX_EXECUTIVE_OFFLINE.html',wait_until='networkidle')
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("pilot-design")')
        assert page.locator('.r6-head').count()==1
        assert not errors,errors
        print('PASS R6 standalone HTML and no browser JavaScript errors')
        browser.close()
finally:
    server.terminate()
    try:server.wait(timeout=5)
    except subprocess.TimeoutExpired:server.kill()
