"""Idempotent local integration of R1.6 into an existing OSMANX checkout.
Never patches data or deploys a public server; refuses unknown app anchors.
"""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'backend/app.py'
html=ROOT/'frontend/index.html'


def install():
    original=APP.read_text(encoding='utf-8')
    new=original
    if 'from backend.r16 import' not in new:
        anchor='from backend.r15 import ensure_schema as ensure_r15_schema, build_router as r15_router'
        if anchor not in new:
            raise RuntimeError('R1.5 must be in the target checkout; refusing to modify incompatible app.py')
        new=new.replace(anchor,anchor+'\nfrom backend.r16 import ensure_schema as ensure_r16_schema, build_router as r16_router',1)
    if 'ensure_r16_schema(db)' not in new:
        anchor='ensure_r15_schema(db)'
        if anchor not in new:raise RuntimeError('Missing R1.5 migration anchor')
        new=new.replace(anchor,anchor+'\n        ensure_r16_schema(db)',1)
    if 'app.include_router(r16_router(admin, db_conn))' not in new:
        anchor='app.include_router(r15_router(admin, db_conn))'
        if anchor not in new:raise RuntimeError('Missing R1.5 router anchor')
        new=new.replace(anchor,anchor+'\napp.include_router(r16_router(admin, db_conn))',1)
    new=new.replace('version="1.5.0"','version="1.6.0"')
    if new!=original:APP.write_text(new,encoding='utf-8')
    h=html.read_text(encoding='utf-8')
    if '/static/r16_nav.js' not in h:
        tag='<script type="module" src="/static/r16_nav.js"></script>'
        if '</body>' not in h:raise RuntimeError('Unknown index template')
        html.write_text(h.replace('</body>',tag+'\n</body>',1),encoding='utf-8')
    print('R1.6 integration complete (idempotent)')

if __name__=='__main__':install()
