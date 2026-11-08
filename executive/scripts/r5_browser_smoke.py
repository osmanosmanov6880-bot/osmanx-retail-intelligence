#!/usr/bin/env python3
"""R5 browser acceptance; real click/input/download on 390/768/1440/1920, no outside APIs."""
from pathlib import Path
import os, socket, subprocess, time
from playwright.sync_api import sync_playwright

BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'screenshots';OUT.mkdir(exist_ok=True)
PORT=4195
server=subprocess.Popen(['python3','-m','http.server',str(PORT),'--bind','127.0.0.1'],cwd=BASE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for _ in range(80):
  try:
   with socket.create_connection(('127.0.0.1',PORT),timeout=.3):break
  except OSError:time.sleep(.08)
 else:raise RuntimeError('HTTP server did not start')
 with sync_playwright() as p:
  launch={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage']}
  if os.environ.get('OSMANX_LOCAL_CHROMIUM'):launch['executable_path']=os.environ['OSMANX_LOCAL_CHROMIUM']
  browser=p.chromium.launch(**launch)
  errors=[];routes=['data-room','cohort-lab','collection-lab','service-lab','branch-lab']
  for width in (390,768,1440,1920):
   page=browser.new_page(viewport={'width':width,'height':920},device_scale_factor=1)
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(f'http://127.0.0.1:{PORT}/',wait_until='networkidle')
   for route in routes:
    page.evaluate('(r)=>window.__OSMANX_DIAGNOSTICS__.navigate(r)',route)
    page.wait_for_selector('main .r5-heading',timeout=10000)
    assert page.locator('main h1').count()==1,(width,route,'missing h1')
    size=page.evaluate('({w:document.documentElement.scrollWidth,v:innerWidth})')
    assert size['w']<=size['v']+1,(width,route,size)
    if width in (390,1440):page.screenshot(path=str(OUT/f'r5_{route}_{width}.png'),full_page=True)
   page.close()
  print('PASS R5 5 routes x 4 widths, no horizontal overflow')

  page=browser.new_page(viewport={'width':1440,'height':960},accept_downloads=True)
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(f'http://127.0.0.1:{PORT}/',wait_until='networkidle')
  page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("data-room")')
  initial=page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')
  page.locator('[data-action="r5-sample"]').click()
  page.locator('[data-action="r5-review"]').click()
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r5.import')==True
  with page.expect_download() as event:page.locator('[data-action="r5-export"]').click()
  event.value.save_as(str(OUT/'r5_checked_sales.csv'))
  assert 'sale-example' in (OUT/'r5_checked_sales.csv').read_text('utf-8-sig')
  page.locator('[data-action="r5-stage"]').click()
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.totals.revenue')==initial,'must not mix uploaded data into synthetic dashboard'
  page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("data-room")')
  page.locator('[data-r5-field="kind"]').select_option('returns')
  page.locator('[data-action="r5-sample"]').click()
  page.locator('[data-action="r5-review"]').click()
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r5.import')==True,'linked returns must validate against staged receipt'
  page.locator('[data-action="r5-clear"]').click()
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r5.import') is None
  print('PASS R5 CSV validation, linked return, export, staging isolated from demo')

  page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("cohort-lab")')
  initial=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r5.cohortMembers')
  assert initial>0
  page.locator('[data-r5-field="cohortWeeks"]').fill('6')
  assert page.locator('.r5-table th').count()==8
  page.locator('[data-action="r5-cohort-select"]').first.click()
  with page.expect_download() as event:page.locator('[data-action="r5-cohort-csv"]').click()
  event.value.save_as(str(OUT/'r5_cohorts.csv'))
  page.locator('[data-action="r5-cohort-journal"]').click()
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='journal'

  page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("collection-lab")')
  before=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r5.collection.units')
  assert before>0
  page.locator('[data-r5-field="collectionBudget"]').fill('0')
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r5.collection.units')==0
  page.locator('[data-r5-field="collectionBudget"]').fill('80000')
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r5.collection.units')==before
  with page.expect_download() as event:page.locator('[data-action="r5-collection-csv"]').click()
  event.value.save_as(str(OUT/'r5_collection.csv'))
  page.locator('[data-action="r5-collection-open"]').first.click()
  page.locator('[data-action="r5-collection-journal"]').click()
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='journal'

  page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("service-lab")')
  before=page.evaluate('window.__OSMANX_DIAGNOSTICS__.r5.service.p90')
  page.locator('[data-r5-field="serviceSla"]').fill('30')
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r5.service.p90')==before
  page.locator('[data-action="r5-service-open"][data-value="s1"]').click()
  with page.expect_download() as event:page.locator('[data-action="r5-service-csv"]').click()
  event.value.save_as(str(OUT/'r5_service.csv'))
  page.locator('[data-action="r5-service-journal"]').click()
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='journal'

  page.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("branch-lab")')
  page.locator('[data-r5-field="benchmarkMetric"]').select_option('serviceP90')
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.r5.benchmark.metric')=='serviceP90'
  page.locator('[data-action="r5-benchmark-open"][data-value="s2"]').click()
  with page.expect_download() as event:page.locator('[data-action="r5-benchmark-pdf"]').click()
  event.value.save_as(str(OUT/'r5_branch.pdf'))
  pdf=(OUT/'r5_branch.pdf').read_bytes();assert pdf[:8]==b'%PDF-1.4' and len(pdf)>40000,len(pdf)
  with page.expect_download() as event:page.locator('[data-action="r5-benchmark-csv"]').click()
  event.value.save_as(str(OUT/'r5_branch.csv'))
  assert 'Галерея' in (OUT/'r5_branch.csv').read_text('utf-8-sig')
  page.locator('[data-action="r5-benchmark-drill"]').click()
  assert page.evaluate('window.__OSMANX_DIAGNOSTICS__.state.page')=='dashboard'
  page.reload(wait_until='networkidle')
  assert not errors,errors
  print('PASS R5 cohort, procurement, service, branch drilldown, actual PDF and CSV. JS errors = 0')
  mobile=browser.new_page(viewport={'width':390,'height':844})
  mobile.on('pageerror',lambda e:errors.append(str(e)))
  mobile.goto(f'http://127.0.0.1:{PORT}/OSMANX_EXECUTIVE_OFFLINE.html',wait_until='networkidle')
  mobile.evaluate('window.__OSMANX_DIAGNOSTICS__.navigate("collection-lab")')
  assert mobile.locator('.r5-heading').count()==1
  assert mobile.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
  mobile.close();browser.close()
  assert not errors,errors
  print('PASS R5 single-file standalone and mobile viewport, no JS errors')
finally:
 server.terminate()
 try:server.wait(timeout=4)
 except subprocess.TimeoutExpired:server.kill()
