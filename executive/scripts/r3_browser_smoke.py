#!/usr/bin/env python3
"""ATELIER R3 browser acceptance: 4 responsive widths + linked decision pathways.
Only runs where Chromium navigation is permitted; CI installs a browser explicitly.
"""
from pathlib import Path
import socket
import re
import subprocess
import time
from playwright.sync_api import sync_playwright
BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'screenshots'
OUT.mkdir(exist_ok=True)
PORT=4179
server=subprocess.Popen(['python3','-m','http.server',str(PORT),'--bind','127.0.0.1'],cwd=BASE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for _ in range(45):
  try:
   with socket.create_connection(('127.0.0.1',PORT),timeout=.3): break
  except OSError:time.sleep(.1)
 else:raise RuntimeError('Local test server unavailable')
 with sync_playwright() as playwright:
  browser=playwright.chromium.launch(headless=True,args=['--no-sandbox'])
  failures=[]
  for width in (390,768,1440,1920):
   page=browser.new_page(viewport={'width':width,'height':860},device_scale_factor=1,accept_downloads=True)
   page.on('pageerror',lambda error:failures.append(str(error)))
   page.goto(f'http://127.0.0.1:{PORT}/',wait_until='networkidle',timeout=35000)
   for route in ('dashboard','evidence','transfer-lab','pilot-lab','journal'):
    page.evaluate('route => window.__OSMANX_DIAGNOSTICS__.navigate(route)',route)
    page.wait_for_selector('#osmanx-main',timeout=9000)
    assert page.locator('main h1').count()>=1,(width,route,'page heading missing')
    values=page.evaluate('({scroll:document.documentElement.scrollWidth,width:innerWidth})')
    assert values['scroll']<=values['width']+1,(width,route,values)
    if width in (390,1440):page.screenshot(path=str(OUT/f'r3_{route}_{width}.png'),full_page=False)
   if width==390:
    page.locator('.nav-trigger').click()
    assert page.locator('.sidebar.is-open').count()==1
    assert page.locator('.sidebar [data-page="transfer-lab"]').count()==1
    page.locator('.sidebar [data-page="transfer-lab"]').click()
    assert page.locator('.sidebar.is-open').count()==0
   page.close()
  print('PASS R3 responsiveness: 390/768/1440/1920, 5 routes each')
  page=browser.new_page(viewport={'width':1440,'height':900},accept_downloads=True)
  page.on('pageerror',lambda error:failures.append(str(error)))
  page.goto(f'http://127.0.0.1:{PORT}/',wait_until='networkidle')
  page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("evidence")')
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.reconciliation.linkedGross')==28000
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.reconciliation.issues.length')==0
  page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("transfer-lab")')
  page.locator('input[data-r3-transfer="units"]').fill('4')
  page.locator('input[data-r3-transfer="units"]').press('Tab')
  page.locator('button[data-action="r3-transfer-check"]').click()
  assert 'Решение невозможно' in page.locator('.r3-alert').inner_text()
  page.locator('input[data-r3-transfer="units"]').fill('3')
  page.locator('input[data-r3-transfer="units"]').press('Tab')
  page.locator('button[data-action="r3-transfer-check"]').click()
  assert '5 550' in re.sub(r'\s+', ' ', page.locator('.r3-result-math').inner_text())
  page.locator('button[data-action="r3-transfer-save"]').click()
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='journal'
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.journal.all')==1
  page.locator('button[data-action="r3-journal-progress"]').click()
  page.locator('input[data-r3-measure="before"]').fill('4')
  page.locator('input[data-r3-measure="after"]').fill('6')
  page.locator('input[data-r3-measure="sample"]').fill('10')
  page.locator('input[data-r3-measure="expenses"]').fill('500')
  page.locator('button[data-action="r3-journal-measure"]').click()
  assert 'без контрольной группы' in page.locator('.r3-measured').inner_text().lower()
  page.locator('button[data-action="r3-journal-close"]').click()
  with page.expect_download() as d:
   page.locator('button[data-action="r3-journal-export"]').click()
  d.value.save_as(str(OUT/'r3_journal.csv'))
  assert 'PILOT-001' in (OUT/'r3_journal.csv').read_text(encoding='utf-8-sig')
  page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("pilot-lab")')
  assert 'Недостаточно данных' in page.locator('.r3-card').last.inner_text()
  page.locator('input[data-r3-pilot="controlRequests"]').fill('60')
  page.locator('input[data-r3-pilot="controlPurchases"]').fill('4')
  page.locator('input[data-r3-pilot="controlPurchases"]').press('Tab')
  assert 'Сравнение описательное' in page.locator('.r3-card').last.inner_text()
  page.locator('button[data-action="r3-pilot-save"]').click()
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.journal.all')==2
  page.reload(wait_until='networkidle')
  page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("journal")')
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.journal.all')==2
  assert not failures,failures
  page.close();browser.close()
  print('PASS R3 evidence, transfer guards, decisions lifecycle, CSV, pilot and persisted journal')
finally:
 server.terminate()
 try:server.wait(timeout=3)
 except subprocess.TimeoutExpired:server.kill()
