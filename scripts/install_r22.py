"""Integrate R2.2 into an existing CURRENT OSMANX R2.1 source checkout.

Only edits known FastAPI/index anchors after validating every local delta file.
Does not run migrations, start servers, connect accounts, or deploy publicly.
Usage: python scripts/install_r22.py --root /path/to/current/osmanx-retail-intelligence
"""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path

DELTA=Path(__file__).resolve().parents[1]
FILES=('backend/r22.py','frontend/rollout.html','frontend/rollout.css','frontend/rollout.js','frontend/r22_nav.js',
       'tests/test_r22.py','scripts/r22_browser_smoke.py','docs/RELEASE_R22.md')


def insert(text,needle,addition):
    if addition in text:return text
    if needle not in text:raise RuntimeError('R2.1 source layout does not match: '+needle[:90])
    return text.replace(needle,needle+'\n'+addition,1)


def install(root:Path):
    root=root.resolve();app=root/'backend/app.py';index=root/'frontend/index.html'
    if not app.is_file() or not index.is_file():raise RuntimeError('Expected FastAPI app and frontend/index.html')
    src=app.read_text(encoding='utf-8');html=index.read_text(encoding='utf-8')
    src=insert(src,'from backend.r21 import ensure_schema as ensure_r21_schema, build_router as r21_router',
               'from backend.r22 import ensure_schema as ensure_r22_schema, build_router as r22_router')
    src=insert(src,'        ensure_r21_schema(db)','        ensure_r22_schema(db)')
    src=insert(src,'app.include_router(r21_router(admin, db_conn))','app.include_router(r22_router(admin, db_conn))')
    if 'version="2.2.0"' not in src:
        if 'version="2.1.0"' not in src:raise RuntimeError('Expected version 2.1.0')
        src=src.replace('version="2.1.0"','version="2.2.0"',1)
    if '/static/r22_nav.js' not in html:
        if '</body>' not in html:raise RuntimeError('No closing body element in index')
        html=html.replace('</body>','<script src="/static/r22_nav.js" defer></script>\n</body>',1)
    for item in FILES:
        if not (DELTA/item).is_file():raise RuntimeError('Missing package file '+item)
    for item in FILES:
        target=root/item;target.parent.mkdir(parents=True,exist_ok=True)
        if (DELTA/item).resolve()!=target.resolve():shutil.copyfile(DELTA/item,target)
    app.write_text(src,encoding='utf-8');index.write_text(html,encoding='utf-8')
    print('R2.2 integrated into source checkout. Run CI before merging; no deployment occurred.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True,type=Path)
    install(parser.parse_args().root)
