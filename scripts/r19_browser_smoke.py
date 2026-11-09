"""R1.9 browser acceptance via isolated FastAPI TestClient/SQLite, no public HTTP navigation."""
from __future__ import annotations
import importlib,os,re,shutil,sys,tempfile
from pathlib import Path
from fastapi import FastAPI,Depends,Header,HTTPException
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
QA=ROOT/'qa';QA.mkdir(exist_ok=True)

def main():
 with tempfile.TemporaryDirectory(prefix='osmanx-r19-browser-') as tmp:
  os.environ.update(OSMANX_DATA_DIR=tmp,OSMANX_ADMIN_PASSWORD='bootstrap-super-secret-2026',
                    OSMANX_BOOTSTRAP_EMAIL='owner@osmanx.local')
  import backend.database as database
  import backend.security as security
  import backend.r17 as r17
  import backend.r19 as r19
  importlib.reload(database)
  database.initialize_db(demo=False)
  with database.connect() as db:
   r17.ensure_schema(db);r19.ensure_schema(db);db.commit()
   user=db.execute("SELECT * FROM users WHERE email='owner@osmanx.local'").fetchone()
   signed=security.issue_session(user,'session-master-secret-for-r19-browser-2026')
  app=FastAPI()
  def conn():
   db=database.connect()
   try:yield db
   finally:db.close()
  def admin(authorization:str|None=Header(default=None),db=Depends(conn)):
   if not authorization or not authorization.startswith('Bearer '):raise HTTPException(401,'Требуется вход')
   return security.verify_session(authorization[7:],'session-master-secret-for-r19-browser-2026',db)
  app.include_router(r17.build_router(admin,conn));app.include_router(r19.build_router(admin,conn))
  with TestClient(app) as client:
   headers={'Authorization':'Bearer '+signed}
   form=client.post('/api/admin/r17/forms',headers=headers,json={
     'slug':'central','request_id':'r19-browser-published-form-00001','title':'Как прошёл визит?',
     'questions':[{'id':'purchased','title':'Купили ли вы понравившуюся вещь?', 'type':'choice',
                   'options':[{'id':'yes','label':'Да'},{'id':'no','label':'Нет'}]},
                  {'id':'rating','title':'Как оцените посещение магазина?', 'type':'rating'}]})
   assert form.status_code==201,form.text
   assert client.post(f"/api/admin/r17/forms/{form.json()['id']}/publish",headers=headers).status_code==200
   placement=client.post('/api/admin/r17/placements',headers=headers,json={
     'form_id':form.json()['id'],'name':'Планшет у выхода','medium':'kiosk'})
   assert placement.status_code==201,placement.text
   p=placement.json()
   with sync_playwright() as playwright:
    browser=playwright.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,
                args=['--no-sandbox','--disable-dev-shm-usage'])
    try:
     def screen(name='field',width=1440,height=900,auth=False,fragment=''):
      context=browser.new_context(viewport={'width':width,'height':height},device_scale_factor=1,accept_downloads=True)
      page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
      def transport(method,path,body,headers):
       response=client.request(method,path,json=body,headers=headers or {}) if body is not None else client.request(method,path,headers=headers or {})
       return {'status':response.status_code,'text':response.text,'type':response.headers.get('content-type','application/json')}
      page.expose_function('__test_api',transport)
      html=(ROOT/'frontend'/f'{name}.html').read_text(encoding='utf-8')
      html=re.sub(r'<link rel="stylesheet" href="/static/[^\"]+">','',html)
      html=re.sub(r'<script type="module" src="/static/[^\"]+"></script>','',html)
      css=(ROOT/'frontend/voice.css').read_text(encoding='utf-8')
      if name=='field':css+='\n'+(ROOT/'frontend/field.css').read_text(encoding='utf-8')
      page.set_content(html.replace('</head>','<style>'+css+'</style></head>'),wait_until='domcontentloaded')
      if fragment:page.evaluate('(frag)=>{location.hash=frag}',fragment)
      page.evaluate("""() => {
        window.__R19_STORAGE__={map:new Map(),getItem(k){return this.map.get(k)??null},
          setItem(k,v){this.map.set(k,String(v))},removeItem(k){this.map.delete(k)},
          get length(){return this.map.size}};
        window.__R19_DROP_SUBMIT__=false;
        window.fetch=async(path,opts={})=>{
          if(window.__R19_DROP_SUBMIT__&&path.endsWith('/submit')){
            window.__R19_DROP_SUBMIT__=false;throw new TypeError('network unavailable');
          }
          const r=await window.__test_api(opts.method||'GET',path,opts.body?JSON.parse(opts.body):null,opts.headers||{});
          return new Response(r.text,{status:r.status,headers:{'Content-Type':r.type}});
        };
      }""")
      if name=='field':
       script=(ROOT/'frontend/field.js').read_text(encoding='utf-8')
       script=script.replace("sessionStorage.getItem('osmanx_admin_token')",repr(signed) if auth else "''")
      else:
       script=(ROOT/'frontend/voice_kiosk.js').read_text(encoding='utf-8').replace('localStorage','window.__R19_STORAGE__')
      page.add_script_tag(content=script)
      return page,context,errors

     manager,mctx,errors=screen(auth=True)
     manager.get_by_text('Каждый терминал.').wait_for(timeout=10000)
     assert manager.locator('.terminal-card').count()==1
     manager.screenshot(path=str(QA/'r19-fleet-desktop.png'),full_page=True)
     manager.get_by_role('tab',name='02 / Расписание').click()
     manager.locator('input[name="start"]').fill('00:00')
     manager.locator('input[name="end"]').fill('23:59')
     manager.locator('#schedule-form button[type=submit]').click()
     manager.get_by_text('Расписание обновлено').wait_for(timeout=10000)
     manager.screenshot(path=str(QA/'r19-schedule-desktop.png'),full_page=True)
     assert not errors,errors

     kiosk,kctx,kerrors=screen(name='voice_kiosk',width=900,height=950,fragment=p['fragment'])
     kiosk.locator('.kiosk-title').wait_for(timeout=10000)
     kiosk.screenshot(path=str(QA/'r19-kiosk-online.png'),full_page=True)
     kiosk.locator('[data-value="no"]').click();kiosk.locator('#next-voice').click()
     kiosk.locator('[data-value="4"]').click()
     kiosk.evaluate('window.__R19_DROP_SUBMIT__=true')
     kiosk.locator('#next-voice').click()
     kiosk.get_by_text('Ответ сохранён на планшете').wait_for(timeout=10000)
     with database.connect() as db:
      assert db.execute('SELECT COUNT(*) FROM voice_responses_r17').fetchone()[0]==0
     kiosk.screenshot(path=str(QA/'r19-kiosk-queued.png'),full_page=True)
     assert kiosk.evaluate('window.__R19_STORAGE__.length')>=1
     kiosk.locator('#new-voice').click()
     kiosk.locator('.kiosk-title').wait_for(timeout=12000)
     with database.connect() as db:
      assert db.execute('SELECT COUNT(*) FROM voice_responses_r17').fetchone()[0]==1
      assert db.execute('SELECT COUNT(*) FROM field_heartbeat_r19').fetchone()[0]==1
     assert kiosk.evaluate("JSON.parse(window.__R19_STORAGE__.getItem('osmanx:r19:queue:'+location.hash.slice(1).split('.')[0])).length")==0
     assert not kerrors,kerrors
     kiosk.close();kctx.close()

     manager.locator('[data-do="refresh"]').click()
     manager.get_by_role('tab',name='04 / Качество').click()
     manager.get_by_text('Контроль качества опросов').wait_for(timeout=10000)
     manager.screenshot(path=str(QA/'r19-quality-desktop.png'),full_page=True)
     with manager.expect_download(timeout=10000) as download:manager.locator('[data-do="quality-csv"]').click()
     assert download.value.suggested_filename=='osmanx-field-quality.csv'
     manager.get_by_role('tab',name='05 / Инциденты').click()
     manager.locator('[data-do="sync"]').click()
     manager.get_by_text('Сигналы синхронизированы').wait_for(timeout=10000)
     manager.screenshot(path=str(QA/'r19-incidents-desktop.png'),full_page=True)
     assert not errors,errors
     manager.close();mctx.close()

     mobile,mctx,merrors=screen(width=390,height=844,auth=True)
     mobile.locator('.terminal-card').wait_for(timeout=10000)
     mobile.screenshot(path=str(QA/'r19-fleet-mobile.png'),full_page=True)
     for name in ['01 / Терминалы','02 / Расписание','04 / Качество']:
      mobile.get_by_role('tab',name=name).click()
      dims=mobile.evaluate('({scroll:document.documentElement.scrollWidth,viewport:innerWidth})')
      assert dims['scroll']<=dims['viewport']+2,(name,dims)
     mobile.screenshot(path=str(QA/'r19-quality-mobile.png'),full_page=True)
     assert not merrors,merrors
     mobile.close();mctx.close()
     print('R1.9 Chromium PASS — fleet/schedule, offline retry and 1 saved response, quality CSV, incidents, 390px')
    finally:browser.close()

if __name__=='__main__':main()
