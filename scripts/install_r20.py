"""Idempotent source integration into the actual OSMANX R1.9 checkout.

It intentionally does not run migrations, deploy, push, or expose a public URL.
Run from this delta package with --root /path/to/current/checkout.
"""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path

DELTA=Path(__file__).resolve().parents[1]


def insert(text:str,needle:str,addition:str)->str:
    if addition in text:return text
    if needle not in text:raise RuntimeError('Unexpected R1.9 layout: missing '+needle[:100])
    return text.replace(needle,needle+'\n'+addition,1)


def install(root:Path):
    root=root.resolve()
    app=root/'backend/app.py'
    index=root/'frontend/index.html'
    if not app.is_file() or not index.is_file():raise RuntimeError('Target is not an OSMANX checkout')
    source=app.read_text()
    source=insert(source,'from backend.r19 import ensure_schema as ensure_r19_schema, build_router as r19_router',
                  'from backend.r20 import ensure_schema as ensure_r20_schema, build_router as r20_router')
    source=insert(source,'        ensure_r19_schema(db)','        ensure_r20_schema(db)')
    source=insert(source,'app.include_router(r19_router(admin, db_conn))','app.include_router(r20_router(admin, db_conn))')
    index_source=index.read_text()
    if '/static/r20_nav.js' not in index_source:
        if '</body>' not in index_source:raise RuntimeError('Unknown index.html template')
        index_source=index_source.replace('</body>','<script src="/static/r20_nav.js" defer></script>\n</body>',1)
    # Validate every prerequisite before mutating any tracked file.
    for relative in ('backend/r20.py','frontend/readiness.html','frontend/readiness.css','frontend/readiness.js','frontend/r20_nav.js'):
        origin=DELTA/relative
        if not origin.is_file():raise RuntimeError('Missing delta file: '+relative)
    for relative in ('backend/r20.py','frontend/readiness.html','frontend/readiness.css','frontend/readiness.js','frontend/r20_nav.js'):
        dest=root/relative
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(DELTA/relative,dest)
    app.write_text(source)
    index.write_text(index_source)
    print('R2.0 integrated into source tree. Run tests and migration in staging; no deployment performed.')


if __name__=='__main__':
    cli=argparse.ArgumentParser()
    cli.add_argument('--root',type=Path,required=True)
    args=cli.parse_args()
    install(args.root)
