#!/usr/bin/env python3
"""True Chromium smoke: 390/768/1440/1920 px + all material user paths."""
from pathlib import Path
import subprocess, time, socket
from playwright.sync_api import sync_playwright

BASE=Path(__file__).resolve().parents[1]
PORT=4178
OUT=BASE/'screenshots'
OUT.mkdir(parents=True,exist_ok=True)
server=subprocess.Popen(['python3','-m','http.server',str(PORT),'--bind','127.0.0.1'],cwd=BASE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(35):
        try:
            with socket.create_connection(('127.0.0.1',PORT),timeout=.3):break
        except OSError:time.sleep(.1)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        errors=[]
        for width in [390,768,1440,1920]:
            page=browser.new_page(viewport={'width':width,'height':900},device_scale_factor=1,accept_downloads=True)
            page.on('pageerror',lambda exc:errors.append(str(exc)))
            page.goto(f'http://127.0.0.1:{PORT}/',wait_until='networkidle',timeout=30000)
            page.wait_for_selector('.luxury-hero',timeout=15000)
            title=page.locator('#luxury-main-title').inner_text()
            assert 'Вы знаете' in title,title
            info=page.evaluate('({scroll:document.documentElement.scrollWidth, viewport:innerWidth})')
            assert info['scroll']<=info['viewport']+1,f'{width}px overflow {info}'
            page.screenshot(path=str(OUT/f'dashboard_{width}.png'),full_page=True)
            print('PASS dashboard width=',width,'screen=',info)
            page.close()
        page=browser.new_page(viewport={'width':1440,'height':900},accept_downloads=True)
        page.on('pageerror',lambda exc:errors.append(str(exc)))
        page.goto(f'http://127.0.0.1:{PORT}/',wait_until='networkidle')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.dataset.products')==300
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.confirmedRescueGross')==28000
        page.locator('.luxury-primary[data-page="demo"]').click()
        assert page.locator('.scene-one').count()==1
        page.screenshot(path=str(OUT/'demo_scene_1.png'),full_page=True)
        for i,cls in enumerate(['scene-two','scene-three','scene-four','scene-five'],start=1):
            page.locator('button[data-action="next-scene"]').click()
            assert page.locator('.'+cls).count()==1,cls
            page.screenshot(path=str(OUT/f'demo_scene_{i+1}.png'),full_page=True)
        print('PASS five demo scenes, manual navigation')
        page.locator('button[data-page="module:0"]').last.click()
        for i in range(10):
            page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("module:'+str(i)+'")')
            assert page.locator('.module-stat').count()==4,(i,page.locator('.module-stat').count())
            assert page.locator('.data-table-panel').count()==1,i
            page.screenshot(path=str(OUT/f'module_{i+1:02}.png'),full_page=False) if i in (0,3,7) else None
        print('PASS 10 interactive analytical modules')
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("dashboard")')
        page.locator('select[data-field="store"]').select_option('s1')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.confirmedRescueSales')<7
        page.locator('select[data-field="category"]').select_option('Куртки')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.conversion') is None
        page.locator('select[data-field="scenario"]').select_option('shortages')
        assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.scenario')=='shortages'
        print('PASS reactive filters and three scenarios')
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("calculator")')
        old=page.locator('.projection-summary>strong').inner_text()
        page.locator('input[data-calc="stores"]').fill('6')
        new=page.locator('.projection-summary>strong').inner_text()
        assert new!=old,(old,new)
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("presentation")')
        page.locator('button[data-value="effect"]').click()
        assert '28 000' in page.locator('.presentation-number').inner_text()
        print('PASS calculator and presentation')
        page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("diagnostic")')
        for i in range(7):
            page.locator('.diag-option').first.click()
            page.locator('button[data-action="next-q"]').click()
        assert page.locator('.plan-line').count()==3
        with page.expect_download() as dl:
            page.locator('button[data-action="pdf"]').click()
        downloaded=dl.value
        pdf_path=OUT/downloaded.suggested_filename
        downloaded.save_as(str(pdf_path))
        assert pdf_path.read_bytes().startswith(b'%PDF-1.4')
        print('PASS diagnostic, 3 suggestions, generated PDF',pdf_path.stat().st_size,'bytes')
        assert not errors,errors
        page.close();browser.close()
        print('PASS ALL CHROMIUM BROWSER SMOKE TESTS; JS errors = 0')
finally:
    server.terminate()
    try:server.wait(timeout=3)
    except subprocess.TimeoutExpired:server.kill()
