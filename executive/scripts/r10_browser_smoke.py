#!/usr/bin/env python3
"""R10 Chromium E2E: five local CSV decision pages, 4 responsive widths, CSV and task handoff."""
import os, subprocess, socket, time
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE=Path(__file__).resolve().parents[1];OUT=BASE/'screenshots';OUT.mkdir(exist_ok=True)
PORT=4220
ROUTES=['r10-provenance','r10-funnel','r10-sku','r10-coverage','r10-packet']
def visit(page,url,inline):
 if inline:page.set_content((BASE/'OSMANX_EXECUTIVE_OFFLINE.html').read_text(),wait_until='load',timeout=30000)
 else:page.goto(url,wait_until='networkidle',timeout=30000)
def nav(page,route):
 page.evaluate('(r)=>window.__OSMANX_DIAGNOSTICS__.navigate(r)',route)
 page.locator('main .r10-heading').wait_for(timeout=6000)
server=None
try:
 inline=os.getenv('OSMANX_R10_INLINE')=='1'
 if not inline:
  server=subprocess.Popen(['python3','-m','http.server',str(PORT),'--bind','127.0.0.1'],cwd=BASE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  for _ in range(50):
   try:
    with socket.create_connection(('127.0.0.1',PORT),timeout=.2):break
   except OSError:time.sleep(.12)
  else:raise RuntimeError('R10 localhost not responding')
 url=f'http://127.0.0.1:{PORT}/'
 with sync_playwright() as p:
  options={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage']}
  if os.getenv('OSMANX_LOCAL_CHROMIUM'):options['executable_path']=os.environ['OSMANX_LOCAL_CHROMIUM']
  browser=p.chromium.launch(**options)
  if not inline:
   probe=browser.new_page()
   try:probe.goto(url,timeout=6000)
   except Exception as e:
    if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(e):inline=True
    else:raise
   probe.close()
  errors=[]
  for width in [390,768,1440,1920]:
   page=browser.new_page(viewport={'width':width,'height':920},accept_downloads=True)
   page.on('pageerror',lambda err:errors.append(str(err)))
   visit(page,url,inline)
   for route in ROUTES:
    nav(page,route)
    assert page.locator('main h1').count()==1,(width,route)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'),(width,route)
    if width in (390,1440):page.screenshot(path=str(OUT/f'r10_{route}_{width}.png'),full_page=True)
   page.close()
  assert not errors,errors
  print('PASS R10 five pages x 4 viewports = 20 responsive cases, 0 JS errors')
  page=browser.new_page(viewport={'width':1440,'height':920},accept_downloads=True)
  page.on('pageerror',lambda err:errors.append(str(err)))
  visit(page,url,inline)
  baseline=page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')
  page.evaluate('(r)=>window.__OSMANX_DIAGNOSTICS__.navigate(r)','local-vault');page.locator('main .r8-head').wait_for()
  page.locator('[data-action="r8-clear"]').click()
  for kind in ('sales','returns','requests','stock'):
   page.locator(f'[data-action="r8-kind"][data-value="{kind}"]').click()
   page.locator('[data-action="r8-sample-one"]').click()
   page.locator('[data-action="r8-accept"]').click()
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r8.counts.sales')==3
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')==baseline
  nav(page,'r10-provenance')
  assert 'R10-' in page.locator('main').inner_text()
  with page.expect_download() as dl:page.locator('[data-action="r10-manifest-csv"]').click()
  dl.value.save_as(str(OUT/'r10_manifest.csv'))
  nav(page,'r10-funnel')
  assert '5' in page.locator('.r10-stats').inner_text()
  page.locator('[data-r10-field="store"]').select_option('store-A')
  with page.expect_download() as dl:page.locator('[data-action="r10-funnel-csv"]').click()
  dl.value.save_as(str(OUT/'r10_funnel.csv'))
  assert 'JKT-01' in (OUT/'r10_funnel.csv').read_text(encoding='utf-8-sig')
  nav(page,'r10-sku')
  page.locator('[data-r10-field="minUnits"]').fill('2')
  with page.expect_download() as dl:page.locator('[data-action="r10-sku-csv"]').click()
  dl.value.save_as(str(OUT/'r10_sku.csv'))
  nav(page,'r10-coverage')
  assert 'дефицит' in page.locator('main').inner_text()
  page.locator('[data-r10-field="reserve"]').fill('1')
  with page.expect_download() as dl:page.locator('[data-action="r10-coverage-csv"]').click()
  dl.value.save_as(str(OUT/'r10_coverage.csv'))
  nav(page,'r10-packet')
  with page.expect_download() as dl:page.locator('[data-action="r10-packet-csv"]').click()
  dl.value.save_as(str(OUT/'r10_packet.csv'))
  page.locator('[data-action="r10-packet-task"]').click()
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='action-board'
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')==baseline
  assert not errors,errors
  print('PASS R10 sample CSV intake, calculated funnel, SKU filters, reserves, 5 exports and board handoff')
  browser.close()
finally:
 if server:server.terminate();server.wait(timeout=5)
