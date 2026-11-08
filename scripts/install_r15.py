"""Non-destructive, idempotent integration patch for the existing R1.4 app.

Run from repository root. Adds new router/schema, a single nav shortcut, CI checks,
without rewriting R1.4 business handlers, old tables, or existing frontend state.
"""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def integrate():
    app_path=ROOT/'backend/app.py'
    app=app_path.read_text(encoding='utf-8')
    imp='from backend.r15 import ensure_schema as ensure_r15_schema, build_router as r15_router\n'
    if imp not in app:
        anchor='ROOT = Path(__file__).resolve().parent.parent'
        assert anchor in app, 'Unexpected app.py import layout, review manually'
        app=app.replace(anchor,imp+'\n'+anchor,1)
    call='        ensure_r15_schema(db)\n'
    if call not in app:
        anchor='        db.commit()\n    yield'
        assert anchor in app, 'Unexpected app.py lifecycle, review manually'
        app=app.replace(anchor,call+anchor,1)
    route='app.include_router(r15_router(admin, db_conn))\n'
    if route not in app:
        anchor='@app.get("/{path:path}",include_in_schema=False)'
        assert anchor in app, 'Unexpected app.py route layout, review manually'
        app=app.replace(anchor,route+'\n'+anchor,1)
    app=re.sub(r'(app\s*=\s*FastAPI\(title="OSMANX Retail Intelligence", version=")\d+(?:\.\d+){2}("\s*,)',r'\g<1>1.5.0\2',app,count=1)
    app_path.write_text(app,encoding='utf-8')

    index_path=ROOT/'frontend/index.html'
    index=index_path.read_text(encoding='utf-8')
    script='<script type="module" src="/static/r15_nav.js"></script>'
    if script not in index:
        assert '</body>' in index
        index=index.replace('</body>',script+'\n</body>',1)
    index_path.write_text(index,encoding='utf-8')

    ci_path=ROOT/'.github/workflows/ci.yml'
    if ci_path.exists():
        ci=ci_path.read_text(encoding='utf-8')
        check='      - name: R1.5 Pilot Studio - API integration tests\n        run: python -m pytest tests/test_r15.py -q\n'
        if check not in ci:
            anchor='      - name: Check Python syntax'
            assert anchor in ci
            ci=ci.replace(anchor,check+anchor,1)
        jscheck='          node --check frontend/pilot.js\n          node --check frontend/r15_nav.js\n'
        if 'node --check frontend/pilot.js' not in ci:
            anchor='      - name: Install Chromium for browser checks'
            assert anchor in ci
            ci=ci.replace(anchor,'      - name: R1.5 frontend syntax\n        run: |\n'+jscheck+anchor,1)
        smoke='      - name: R1.5 pilot browser acceptance\n        run: python scripts/r15_browser_smoke.py\n'
        if smoke not in ci:
            anchor='      - name: Upload acceptance screenshots'
            assert anchor in ci
            ci=ci.replace(anchor,smoke+anchor,1)
        if 'qa/r15-*.png' not in ci:
            ci=ci.replace('          if-no-files-found:', '            qa/r15-*.png\n          if-no-files-found:',1)
        ci_path.write_text(ci,encoding='utf-8')


if __name__=='__main__':
    integrate()
    print('R1.5 Pilot Studio safely installed; existing business modules unchanged.')
