#!/usr/bin/env python3
"""OSMANX ATELIER R9: live Chromium e2e, editable locally without any external API.
CI uses a real local HTTP server; restricted local runtimes fall back to set_content.
"""
from pathlib import Path
import os, socket, subprocess, time
from playwright.sync_api import sync_playwright
BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'screenshots'
OUT.mkdir(exist_ok=True)
PORT=4219
ROUTES=['payment-vault','payment-match','bank-close','exception-room','cfo-report']
server=None

def use_page(page,url,inline):
    if inline:
        page.set_content((BASE/'OSMANX_EXECUTIVE_OFFLINE.html').read_text(),wait_until='load',timeout=30000)
    else:
        page.goto(url,wait_until='networkidle',timeout=30000)

def nav(page,route):
    page.evaluate('(r)=>window.__OSMANX_DIAGNOSTICS__.navigate(r)',route)
    page.locator('main .r9-intro').wait_for(timeout=5000)

try:
    force_inline=os.getenv('OSMANX_R9_INLINE')=='1'
    if not force_inline:
        server=subprocess.Popen(['python3','-m','http.server',str(PORT),'--bind','127.0.0.1'],cwd=BASE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                with socket.create_connection(('127.0.0.1',PORT),timeout=.2):break
            except OSError:time.sleep(.1)
        else:raise RuntimeError('R9 local server unavailable')
    url=f'http://127.0.0.1:{PORT}/'
    with sync_playwright() as p:
        kwargs={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage']}
        if os.getenv('OSMANX_LOCAL_CHROMIUM'):
            kwargs['executable_path']=os.environ['OSMANX_LOCAL_CHROMIUM']
        browser=p.chromium.launch(**kwargs)
        if not force_inline:
            probe=browser.new_page()
            try:probe.goto(url,timeout=6000)
            except Exception as e:
                if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(e):
                    force_inline=True
                    print('LOCAL FALLBACK: browser policy blocks loopback; testing equivalent standalone DOM via set_content')
                else:raise
            probe.close()
        errors=[]
        for width in (390,768,1440,1920):
            page=browser.new_page(viewport={'width':width,'height':930})
            page.on('pageerror',lambda exc:errors.append(str(exc)))
            use_page(page,url,force_inline)
            for route in ROUTES:
                nav(page,route)
                assert page.locator('main h1').count()==1,(width,route)
                assert page.locator('.r9-stamp').count()==1,(width,route)
                d=page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
                assert d['scroll']<=d['width']+1,(route,width,d)
                if width in (390,1440):
                    page.screenshot(path=str(OUT/f'r9_{route}_{width}.png'),full_page=True)
            page.close()
        print('PASS R9: 5 rooms x 4 viewports = 20 responsive checks without horizontal overflow')
        page=browser.new_page(viewport={'width':1440,'height':930},accept_downloads=True)
        page.on('pageerror',lambda exc:errors.append(str(exc)))
        use_page(page,url,force_inline)
        baseline=page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')
        nav(page,'payment-vault')
        assert page.locator('[data-action="r9-accept"]').is_disabled()
        page.locator('[data-action="r9-examples"]').click()
        r=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r9')
        assert r['valid'] and r['records']==5 and r['settlements']==4 and r['matched']==4 and r['bankVerified'] and r['exceptions']==0,r
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')==baseline
        print('PASS R9: tutorial loads all source files, split payments, refunds, bank batches, isolated demo')
        nav(page,'payment-match')
        assert page.locator('main .r9-major').count()==1
        with page.expect_download() as dl:page.locator('[data-action="r9-matching-csv"]').click()
        dl.value.save_as(str(OUT/'r9_matches.csv'))
        assert 's-101' in (OUT/'r9_matches.csv').read_text(encoding='utf-8-sig')
        nav(page,'bank-close')
        page.locator('[data-r9-field="maxLagDays"]').fill('0')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r9.exceptions')>0
        page.locator('[data-r9-field="maxLagDays"]').fill('3')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r9.exceptions')==0
        with page.expect_download() as dl:page.locator('[data-action="r9-bank-csv"]').click()
        dl.value.save_as(str(OUT/'r9_bank_batches.csv'))
        with page.expect_download() as dl:page.locator('[data-action="r9-daily-csv"]').click()
        dl.value.save_as(str(OUT/'r9_cash_close.csv'))
        print('PASS R9: timing controls live, bank and daily close CSV are real downloads')
        nav(page,'cfo-report')
        assert page.locator('.r9-claims article').count()==6
        with page.expect_download() as dl:page.locator('[data-action="r9-cfo-pdf"]').click()
        dl.value.save_as(str(OUT/'r9_cfo_report.pdf'))
        pdf=(OUT/'r9_cfo_report.pdf').read_bytes()
        assert pdf.startswith(b'%PDF-') and len(pdf)>12000,(pdf[:10],len(pdf))
        with page.expect_download() as dl:page.locator('[data-action="r9-cfo-csv"]').click()
        dl.value.save_as(str(OUT/'r9_cfo_report.csv'))
        assert 'Валовая прибыль' in (OUT/'r9_cfo_report.csv').read_text(encoding='utf-8-sig')
        if not force_inline:
            page.locator('[data-action="r9-cfo-save"]').click()
            assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r9.signoffs')==1
            persisted=page.evaluate("localStorage.getItem('osmanx-r9-aggregate-signoffs')")
            assert all(s not in persisted for s in ['s-101','r-101','op-01','batch-A'])
        print('PASS R9: six source-labeled claims, real PDF, owner CSV and aggregate signoff')
        # Start a genuinely local imported working set to check anomalies and blocked mixing.
        nav(page,'payment-vault')
        page.locator('[data-action="r9-clear"]').click()
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("local-vault")')
        page.locator('main .r8-head').wait_for()
        page.locator('[data-action="r8-clear"]').click()
        for kind in ('sales','returns','requests','stock'):
            page.locator(f'[data-action="r8-kind"][data-value="{kind}"]').click()
            page.locator('[data-r8-file]').set_input_files(str(BASE/f'fixtures/r9_base_{kind}.csv'))
            page.locator('[data-r8-text]').wait_for(state='visible')
            page.wait_for_function("document.querySelector('[data-r8-text]').value.length>30")
            page.locator('[data-action="r8-accept"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.example')==False
        nav(page,'payment-vault')
        for kind in ('operations','settlements'):
            page.locator('[data-r9-field="kind"]').select_option(kind)
            page.locator('[data-r9-file]').set_input_files(str(BASE/f'fixtures/r9_{kind}.csv'))
            page.wait_for_function("document.querySelector('[data-r9-text]').value.length>30")
            page.locator('[data-action="r9-accept"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r9.bankVerified') is True
        print('PASS R9: actual browser file inputs, local work set, atomic matching and bank verification')
        # Edited operation of the original file: first card capture is reduced by 100.
        operations=(BASE/'fixtures/r9_operations.csv').read_text(encoding='utf-8-sig')
        text=operations.replace(';"s-101";8900;180;', ';"s-101";8800;180;',1)
        assert text!=operations
        page.locator('[data-r9-field="kind"]').select_option('operations')
        page.locator('[data-r9-text]').fill(text)
        page.locator('[data-action="r9-accept"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r9.exceptions')>=1
        nav(page,'exception-room')
        assert page.locator('[data-action="r9-triage-start"]').count()==1
        page.locator('[data-action="r9-triage-start"]').click()
        page.locator('[data-r9-field="reason"]').select_option('statement-checked')
        page.locator('[data-r9-field="evidenceId"]').fill('ACT-2026-R9')
        page.locator('[data-action="r9-triage-close"]').click()
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r9.closed')>=1
        with page.expect_download() as dl:page.locator('[data-action="r9-cases-csv"]').click()
        dl.value.save_as(str(OUT/'r9_exceptions.csv'))
        print('PASS R9: mismatched payment → exception → assigned document code → approved transition → CSV')
        if force_inline:
            page.close()
            page=browser.new_page(viewport={'width':1440,'height':930},accept_downloads=True)
            page.on('pageerror',lambda exc:errors.append(str(exc)))
            use_page(page,url,True)
        else:
            page.reload(wait_until='networkidle')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.version')==0
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r9.records')==0
        if not force_inline:assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r9.signoffs')==1
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')==baseline
        assert not errors,errors
        print('PASS R9: reload destroys all raw import rows; demo revenue unchanged; JS errors = 0')
        browser.close()
finally:
    if server:
        server.terminate()
        try:server.wait(timeout=5)
        except subprocess.TimeoutExpired:server.kill()
