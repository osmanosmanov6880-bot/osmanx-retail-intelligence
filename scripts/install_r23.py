"""Idempotently install R2.3 source delta into an R2.2 source checkout.

Run: python scripts/install_r23.py --root /absolute/path/to/osmanx-retail-intelligence
Never overwrites original database files, creates accounts or deploys a server.
"""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATHS=('backend/r23_core.py','backend/r23.py','frontend/security.html','frontend/r23_security.css',
       'frontend/r23_security.js','frontend/r23_nav.js','scripts/r23_recovery_drill.py',
       'scripts/r23_browser_smoke.py','tests/test_r23_core.py','tests/test_r23_api.py','docs/RELEASE_R23.md')


def patch(target:Path,needle:str,replacement:str):
    text=target.read_text(encoding='utf-8')
    if replacement in text:return False
    if text.count(needle)!=1:raise ValueError(f'Unexpected source: {target}, expected unique anchor {needle[:60]}')
    target.write_text(text.replace(needle,replacement,1),encoding='utf-8');return True


def install(target:Path):
    target=target.resolve()
    if not (target/'backend/r22.py').is_file():
        raise RuntimeError('This installer requires a complete R2.2 checkout')
    if (target/'backend/database.py').is_file() is False:raise RuntimeError('Missing application database module')
    for rel in PATHS:
        src=ROOT/rel;dst=target/rel
        if not src.is_file():raise RuntimeError(f'Delta source file missing: {src}')
        dst.parent.mkdir(parents=True,exist_ok=True)
        if dst.exists():
            if dst.read_bytes()!=src.read_bytes():raise RuntimeError(f'Conflict with existing R2.3 source: {dst}')
        else:shutil.copy2(src,dst)
    app=target/'backend/app.py'
    patch(app,'from backend.r22 import ensure_schema as ensure_r22_schema, build_router as r22_router',
         'from backend.r22 import ensure_schema as ensure_r22_schema, build_router as r22_router\nfrom backend.r23 import ensure_schema as ensure_r23_schema, build_router as r23_router')
    patch(app,'        ensure_r22_schema(db)\n', '        ensure_r22_schema(db)\n        ensure_r23_schema(db)\n')
    patch(app,'app.include_router(r22_router(admin, db_conn))',
         'app.include_router(r22_router(admin, db_conn))\napp.include_router(r23_router(admin, db_conn))')
    if 'version="2.2.0"' in app.read_text():patch(app,'version="2.2.0"','version="2.3.0"')
    patch(target/'frontend/index.html','</body>', '  <script src="/static/r23_nav.js" defer></script>\n</body>')
    old="        require_role(principal,'owner','manager')\n        db.execute('BEGIN IMMEDIATE')"
    new="""        require_role(principal,'owner','manager')
        from os import getenv
        if getenv('OSMANX_DEMO_MODE','0')!='1':
            raise HTTPException(409,'R2.3: прямой запуск запрещён. Используйте R2.1 safe-start с проверенным readiness_id.')
        db.execute('BEGIN IMMEDIATE')"""
    r15=target/'backend/r15.py';s=r15.read_text();idx=s.index("    @router.post('/pilots/{pilot_id}/start')")
    before=s[:idx];after=s[idx:]
    if new not in after:
        if old not in after:raise RuntimeError('Unexpected R1.5 legacy start route')
        r15.write_text(before+after.replace(old,new,1))
    r21=target/'backend/r21.py';s=r21.read_text()
    oldbranch="""            if previous:
                if previous['readiness_id']!=body.readiness_id:raise HTTPException(409,'Пилот уже запущен с другим заключением')
                db.rollback();return {'id':pilot_id,'status':pilot['status'],'duplicate':True,'sha256':previous['preflight_sha']}"""
    newbranch="""            if previous:
                if previous['readiness_id']!=body.readiness_id:raise HTTPException(409,'Пилот уже запущен с другим заключением')
                if sha_text(previous['preflight_json'])!=previous['preflight_sha']:
                    raise HTTPException(409,'Подтверждение ранее разрешённого запуска повреждено')
                if pilot['status'] not in ('running','completed','cancelled'):
                    raise HTTPException(409,'Пилот не соответствует ранее выданному разрешению')
                db.rollback();return {'id':pilot_id,'status':pilot['status'],'duplicate':True,'sha256':previous['preflight_sha']}"""
    patch(r21,oldbranch,newbranch)
    pilot_js=target/'frontend/pilot.js'
    oldjs="if(p?.status==='draft')target.querySelector('#start-pilot').onclick=()=>mutate(()=>api(`/pilots/${p.id}/start`,{method:'POST'}));"
    newjs="if(p?.status==='draft')target.querySelector('#start-pilot').onclick=()=>mutate(()=>startWithReadiness(p));"
    patch(pilot_js,oldjs,newjs)
    newfn="""async function startWithReadiness(p){
  try{return await api(`/pilots/${p.id}/start`,{method:'POST'});}
  catch(err){
    if(!err.message.includes('R2.3'))throw err;
    const portfolio=await apiRoot('r21/portfolio');
    const entry=(portfolio.stores||[]).find(x=>x.slug===state.slug);
    if(!entry||entry.status!=='verified'||!entry.readiness_id)
      throw Error('Перед запуском нужен независимо проверенный отчёт готовности R2.0. Откройте «Готовность магазина».');
    const headers={'Accept':'application/json','Content-Type':'application/json'};
    if(token())headers.Authorization=`Bearer ${token()}`;
    const res=await fetch(`/api/admin/r21/pilots/${p.id}/safe-start`,{method:'POST',headers,cache:'no-store',
      body:JSON.stringify({readiness_id:entry.readiness_id})});
    const data=await res.json().catch(()=>({detail:'Сервер не вернул подтверждение'}));
    if(!res.ok)throw Error(typeof data.detail==='string'?data.detail:`HTTP ${res.status}`);
    return data;
  }
}
"""
    if 'async function startWithReadiness(p)' not in pilot_js.read_text():
        code=pilot_js.read_text();needle='function button(text,'
        if needle not in code:raise RuntimeError('Unknown R1.5 frontend JS layout')
        pilot_js.write_text(code.replace(needle,newfn+needle,1),encoding='utf-8')
    print('R2.3 installed; database migration executes on next application startup. Public server not started.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    a=p.parse_args();install(a.root)

if __name__=='__main__':main()
