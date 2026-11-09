"""Install R2.1 source delta into a compatible R2.0 or R1.9 checkout.

No database mutation, deployment or external connection. Use source control.
Optional --install-r20 integrates the bundled R2.0 first if missing.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

DELTA=Path(__file__).resolve().parents[1]
COPY=(
    'backend/r21.py','frontend/assurance.html','frontend/assurance.css',
    'frontend/assurance.js','frontend/r21_nav.js'
)


def append_once(text:str,needle:str,addition:str)->str:
    if addition in text:return text
    if needle not in text:raise RuntimeError('Incompatible checkout: missing '+needle[:85])
    return text.replace(needle,needle+'\n'+addition,1)


def install(root:Path,install_r20=False):
    root=root.resolve()
    app=root/'backend/app.py';index=root/'frontend/index.html'
    if not (app.is_file() and index.is_file()):raise RuntimeError('Target is not a source checkout')
    for relative in COPY:
        if not (DELTA/relative).is_file():raise RuntimeError('Missing release source: '+relative)
    app_text=app.read_text(encoding='utf-8')
    if 'from backend.r20 import ensure_schema as ensure_r20_schema' not in app_text:
        if not install_r20:raise RuntimeError('Install R2.0 first or pass --install-r20')
        r20=DELTA/'scripts/install_r20.py'
        if not r20.is_file():raise RuntimeError('Bundled R2.0 installer is missing')
        subprocess.run([sys.executable,str(r20),'--root',str(root)],check=True)
        app_text=app.read_text(encoding='utf-8')
    app_text=append_once(app_text,
        'from backend.r20 import ensure_schema as ensure_r20_schema, build_router as r20_router',
        'from backend.r21 import ensure_schema as ensure_r21_schema, build_router as r21_router')
    app_text=append_once(app_text,'        ensure_r20_schema(db)','        ensure_r21_schema(db)')
    app_text=append_once(app_text,'app.include_router(r20_router(admin, db_conn))',
        'app.include_router(r21_router(admin, db_conn))')
    index_text=index.read_text(encoding='utf-8')
    if '/static/r21_nav.js' not in index_text:
        if '</body>' not in index_text:raise RuntimeError('Unknown index.html layout')
        index_text=index_text.replace('</body>','<script src="/static/r21_nav.js" defer></script>\n</body>',1)
    # Commit source files only after checking all anchors: repeatable and non-destructive.
    for relative in COPY:
        target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(DELTA/relative,target)
    app.write_text(app_text,encoding='utf-8');index.write_text(index_text,encoding='utf-8')
    print('R2.1 integrated into source checkout. Run full test suite before any deployment.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--install-r20',action='store_true')
    args=parser.parse_args();install(args.root,args.install_r20)
