"""Add the R1.4 Integrity Center to an existing R1.3+ checkout idempotently.

Preserves the older R1.3 Merchant Control Room and all other routers.
"""
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
app=ROOT/'backend/app.py'
s=app.read_text(encoding='utf8')
if 'from backend.r14 import install as install_r14' not in s:
    anchor='@app.get("/{path:path}",include_in_schema=False)'
    if anchor not in s:raise SystemExit('R1.4 installation aborted: SPA anchor missing')
    s=s.replace(anchor, 'from backend.r14 import install as install_r14\ninstall_r14(app, admin, db_conn)\n\n'+anchor,1)
if 'ensure_r14_schema(db)' not in s:
    anchor= ('        ensure_r13_schema(db)\n' if '        ensure_r13_schema(db)\n' in s else
             '        ensure_commerce_schema(db)\n')
    if anchor not in s:raise SystemExit('R1.4 installation aborted: schema anchor missing')
    s=s.replace(anchor,anchor+'        from backend.r14 import ensure_schema as ensure_r14_schema\n        ensure_r14_schema(db)\n',1)
if 'version="1.3.0"' in s:s=s.replace('version="1.3.0"','version="1.4.0"',1)
app.write_text(s,encoding='utf8')
ci=ROOT/'.github/workflows/ci.yml'
if ci.exists():
    t=ci.read_text(encoding='utf8')
    if 'tests/test_r14_extended.py' not in t:
        marker='      - name: Check Python syntax\n'
        if marker not in t:raise SystemExit('R1.4 CI insertion point missing')
        t=t.replace(marker,'      - name: R1.4 integration and security tests\n        run: python -m pytest tests/test_r14.py tests/test_r14_extended.py -q\n'+marker,1)
    if 'node --check frontend/integrity.js' not in t:
        marker='          node --check frontend/app.js\n'
        if marker not in t:raise SystemExit('R1.4 JS check insertion point missing')
        t=t.replace(marker,marker+'          node --check frontend/integrity.js\n',1)
    if 'scripts/r14_browser_smoke.py' not in t:
        marker='      - name: Upload acceptance screenshots\n'
        if marker not in t:raise SystemExit('R1.4 browser check insertion point missing')
        t=t.replace(marker,'      - name: R1.4 Integrity Center browser acceptance\n        run: python scripts/r14_browser_smoke.py\n'+marker,1)
    if 'qa/r14-*.png' not in t:
        marker='            qa/r13-*.png\n'
        if marker in t:t=t.replace(marker,marker+'            qa/r14-*.png\n',1)
    ci.write_text(t,encoding='utf8')
print('R1.4 hooks installed; existing R1.3 code preserved. No deployment.')
