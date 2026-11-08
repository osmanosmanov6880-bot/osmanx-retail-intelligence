#!/usr/bin/env python3
"""ATELIER R4 browser acceptance: five real workflows, PDF/CSV, layout.
All test inputs are generated demo data; no external integration or network needed.
"""
from pathlib import Path
import os
import re
import socket
import subprocess
import time
from playwright.sync_api import sync_playwright

BASE=Path(__file__).resolve().parents[1]
ARTIFACTS=BASE/'screenshots'
ARTIFACTS.mkdir(exist_ok=True)
PORT=4184
proc=subprocess.Popen(['python3','-m','http.server',str(PORT),'--bind','127.0.0.1'],cwd=BASE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for _ in range(75):
  try:
   with socket.create_connection(('127.0.0.1',PORT),timeout=.25):break
  except OSError:time.sleep(.08)
 else:raise RuntimeError('Local web server unavailable')
 with sync_playwright() as p:
  launch={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage']}
  if os.environ.get('OSMANX_LOCAL_CHROMIUM'):
   launch['executable_path']=os.environ['OSMANX_LOCAL_CHROMIUM']
  browser=p.chromium.launch(**launch)
  errors=[]
  routes=('trust-lab','demand-match','margin-stress','portfolio','dossier')
  for width in (390,768,1440,1920):
   page=browser.new_page(viewport={'width':width,'height':900},device_scale_factor=1)
   page.on('pageerror',lambda error: errors.append(str(error)))
   page.goto(f'http://127.0.0.1:{PORT}/',wait_until='networkidle')
   for route in routes:
    page.evaluate('(x) => window.__OSMANX_DIAGNOSTICS__.navigate(x)',route)
    page.wait_for_selector('main .r4-heading',timeout=10000)
    assert page.locator('main h1').count()==1,(width,route,'missing heading')
    sizing=page.evaluate('({doc:document.documentElement.scrollWidth, viewport:innerWidth})')
    assert sizing['doc']<=sizing['viewport']+1,(width,route,sizing)
    if width in (390,1440):page.screenshot(path=str(ARTIFACTS/f'r4_{route}_{width}.png'),full_page=True)
   page.close()
  print('PASS R4 5 routes x 4 responsive viewports = 20 layout checks')

  page=browser.new_page(viewport={'width':1440,'height':900},accept_downloads=True)
  page.on('pageerror',lambda error: errors.append(str(error)))
  page.goto(f'http://127.0.0.1:{PORT}/',wait_until='networkidle')
  page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("trust-lab")')
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r4.audit')==0
  page.locator('button[data-action="r4-audit-stream"][data-value="requests"]').click()
  assert page.locator('.r4-source.active').count()==1
  with page.expect_download() as d:page.locator('button[data-action="r4-audit-csv"]').click()
  d.value.save_as(str(ARTIFACTS/'r4_audit.csv'))
  assert 'Невидимый спрос' in (ARTIFACTS/'r4_audit.csv').read_text(encoding='utf-8-sig')

  page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("demand-match")')
  before=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r4.match.matched')
  page.locator('input[data-r4-field="reserve"]').fill('3')
  after=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r4.match.matched')
  assert after<=before,(before,after)
  page.locator('input[data-r4-field="reserve"]').fill('-1')
  assert page.locator('.r4-error').count()>=1
  assert page.locator('input[data-r4-field="reserve"]').count()==1,'must allow recovery from invalid buffer'
  page.locator('input[data-r4-field="reserve"]').fill('0')
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r4.match.matched')==before
  with page.expect_download() as d:page.locator('button[data-action="r4-match-csv"]').click()
  d.value.save_as(str(ARTIFACTS/'r4_match.csv'))
  assert 'req-14' in (ARTIFACTS/'r4_match.csv').read_text(encoding='utf-8-sig')
  page.locator('button[data-action="r4-match-journal"]').click()
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='journal'
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.journal.all')==1

  page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("margin-stress")')
  old=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r4.margin')
  page.locator('input[data-r4-field="discount"]').fill('40')
  new=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r4.margin')
  assert new<old,(old,new)
  page.locator('button[data-action="r4-margin-journal"]').click()
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.journal.all')==2

  page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("portfolio")')
  page.locator('input[data-r4-field="capacity"]').fill('1')
  assert len(page.evaluate('window.__OSMANX_DIAGNOSTICS__.r4.portfolio'))<=1
  page.locator('input[data-r4-field="budget"]').fill('0')
  assert len(page.evaluate('window.__OSMANX_DIAGNOSTICS__.r4.portfolio'))==0
  page.locator('input[data-r4-field="budget"]').fill('15000')
  page.locator('input[data-r4-field="capacity"]').fill('3')
  with page.expect_download() as d:page.locator('button[data-action="r4-portfolio-csv"]').click()
  d.value.save_as(str(ARTIFACTS/'r4_portfolio.csv'))
  page.locator('button[data-action="r4-portfolio-journal"]').click()
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.journal.all')==3
  page.reload(wait_until='networkidle')
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.journal.all')==3

  page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("dossier")')
  with page.expect_download() as d:page.locator('button[data-action="r4-dossier-csv"]').click()
  d.value.save_as(str(ARTIFACTS/'r4_dossier.csv'))
  assert 'Не доказанный прирост' in (ARTIFACTS/'r4_dossier.csv').read_text(encoding='utf-8-sig')
  with page.expect_download() as d:page.locator('button[data-action="r4-dossier-pdf"]').click()
  d.value.save_as(str(ARTIFACTS/'r4_dossier.pdf'))
  pdf=(ARTIFACTS/'r4_dossier.pdf').read_bytes()
  assert pdf.startswith(b'%PDF-1.4') and len(pdf)>50000,len(pdf)
  assert not errors,errors
  page.close()
  # The single-file offline edition must work from the same static server without imports.
  standalone=browser.new_page(viewport={'width':390,'height':844})
  standalone.on('pageerror',lambda error:errors.append('offline: '+str(error)))
  standalone.goto(f'http://127.0.0.1:{PORT}/OSMANX_EXECUTIVE_OFFLINE.html',wait_until='networkidle')
  standalone.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("demand-match")')
  assert standalone.locator('.r4-heading').count()==1
  assert not errors,errors
  standalone.close();browser.close()
  print('PASS R4 audit CSV, bounded allocation, invalid-input recovery, margin, prioritization, journal persistence, dossier PDF/CSV, offline edition. JS errors = 0')
finally:
 proc.terminate()
 try:proc.wait(timeout=4)
 except subprocess.TimeoutExpired:proc.kill()
