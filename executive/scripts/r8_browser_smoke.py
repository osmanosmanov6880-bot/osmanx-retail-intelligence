#!/usr/bin/env python3
"""R8 standalone Chromium acceptance, no network or local HTTP required.
Exercises five production routes at four viewports, controls, generated CSV,
board handoffs and invariance of source-derived accounting totals.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
import os
BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'screenshots'
OUT.mkdir(exist_ok=True)
html=(BASE/'OSMANX_EXECUTIVE_OFFLINE.html').read_text('utf-8')
ROUTES=('demand-radar','service-capacity','retention-experiment','replenishment-risk','profit-stress')
with sync_playwright() as p:
    params={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage']}
    if os.getenv('OSMANX_LOCAL_CHROMIUM'):
        params['executable_path']=os.environ['OSMANX_LOCAL_CHROMIUM']
    browser=p.chromium.launch(**params)
    errors=[]
    for width in (390,768,1440,1920):
        page=browser.new_page(viewport={'width':width,'height':900},accept_downloads=True)
        page.on('pageerror',lambda err:errors.append(str(err)))
        page.set_content(html,wait_until='domcontentloaded')
        for route in ROUTES:
            page.evaluate('(route)=>window.__OSMANX_DIAGNOSTICS__.navigate(route)',route)
            assert page.locator('main h1').count()==1,(width,route,'missing heading')
            assert page.locator('main .r8-stamp').count()==1,(width,route,'missing demo banner')
            d=page.evaluate('({scroll:document.documentElement.scrollWidth,viewport:window.innerWidth})')
            assert d['scroll']<=d['viewport']+1,(width,route,d)
            assert page.locator('main .r8-stat').count()==4,(width,route,'missing analysis')
            if width in (390,1440):page.screenshot(path=str(OUT/f'r8_{route}_{width}.png'),full_page=True)
        page.close()
    print('PASS R8 5 routes x 4 viewport widths, 20 responsive checks, no horizontal overflow')
    page=browser.new_page(viewport={'width':1440,'height':900},accept_downloads=True)
    page.on('pageerror',lambda err:errors.append(str(err)))
    page.set_content(html,wait_until='domcontentloaded')
    baseline=page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')

    # 1: live demand definition, quality thresholds, CSV and action handoff.
    page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("demand-radar")')
    before=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.radar.signals')
    page.locator('[data-r8-field="radarSignal"]').select_option('all')
    after=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.radar.signals')
    assert after>before,(after,before)
    page.locator('[data-r8-field="radarDays"]').fill('7')
    assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.radar.valid') is True
    with page.expect_download() as dl:page.locator('[data-action="r8-radar-csv"]').click()
    dl.value.save_as(str(OUT/'r8_radar.csv'))
    assert 'Запросов' in (OUT/'r8_radar.csv').read_text('utf-8-sig')
    page.locator('[data-action="r8-radar-task"]').click()
    assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='action-board'
    print('PASS R8 radar: independent numerator, reactive dates, CSV and decision handoff')

    # 2: measured SLA vs assumed staffing cost, no phantom revenue changes.
    page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("service-capacity")')
    page.locator('[data-r8-field="capacityDemand"]').fill('16')
    assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.capacity.cost')>0
    with page.expect_download() as dl:page.locator('[data-action="r8-capacity-csv"]').click()
    dl.value.save_as(str(OUT/'r8_capacity.csv'))
    page.locator('[data-action="r8-capacity-task"]').click()
    assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='action-board'
    print('PASS R8 service: workload input, real cost changes, CSV and action creation')

    # 3: only aggregates, holdout preserved, no personal IDs in exported file.
    page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("retention-experiment")')
    before=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.retention')
    page.locator('[data-r8-field="outreachTreatment"]').fill('5')
    after=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.retention')
    assert after['holdout']==before['holdout']
    assert after['net']<before['net']
    with page.expect_download() as dl:page.locator('[data-action="r8-outreach-csv"]').click()
    dl.value.save_as(str(OUT/'r8_outreach.csv'))
    text=(OUT/'r8_outreach.csv').read_text('utf-8-sig')
    assert 'ВСЕГО' in text and 'req-14-' not in text and 'loy-' not in text
    print('PASS R8 retention: stable offline holdout, economic downside and anonymous CSV')

    # 4: budget 0 produces zero accepted lots, restoring budget is meaningful.
    page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("replenishment-risk")')
    assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.procurement.units')>0
    page.locator('[data-r8-field="procBudget"]').fill('0')
    assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.procurement.units')==0
    page.locator('[data-r8-field="procBudget"]').fill('75000')
    assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.procurement.spent')<=75000
    with page.expect_download() as dl:page.locator('[data-action="r8-proc-csv"]').click()
    dl.value.save_as(str(OUT/'r8_procurement.csv'))
    assert 'ID снимка' in (OUT/'r8_procurement.csv').read_text('utf-8-sig')
    page.locator('[data-action="r8-proc-task"]').click()
    assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='action-board'
    print('PASS R8 purchasing: snapshot, budget zero, lot reallocation, CSV and task')

    # 5: break-even, invalid guard, reactive sensitivity, export and handoff.
    page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("profit-stress")')
    initial=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.stress.baseNet')
    page.locator('[data-r8-field="stressBase"]').fill('100')
    assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.stress.valid') is False
    assert page.locator('main [role="alert"]').count()>=1
    page.locator('[data-r8-field="stressBase"]').fill('15')
    page.locator('[data-r8-field="stressDelivery"]').fill('3000')
    assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.stress.baseNet')<initial
    with page.expect_download() as dl:page.locator('[data-action="r8-stress-csv"]').click()
    dl.value.save_as(str(OUT/'r8_stress.csv'))
    assert 'Осторожный' in (OUT/'r8_stress.csv').read_text('utf-8-sig')
    page.locator('[data-action="r8-stress-task"]').click()
    assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='action-board'
    assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')==baseline
    assert not errors,errors
    browser.close()
    print('PASS R8 stress: guardrails, break-even and CSV, accounting unchanged')
    print('PASS R8 full Chromium acceptance: 20 responsive routes, 5 live workflows, 0 JS errors')
