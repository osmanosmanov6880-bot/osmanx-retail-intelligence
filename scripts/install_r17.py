"""Idempotently add R1.7 Voice Studio to an actual R1.6 source checkout.

Requires the current repository layout. Refuses to modify unexpected anchors.
No internet, database migrations, deployment, or secret creation are triggered.
"""
from __future__ import annotations
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def patch(path,old,new):
    item=ROOT/path
    text=item.read_text(encoding='utf-8')
    if new in text:return False
    if old not in text:raise RuntimeError(f'Unexpected layout: {path}, missing anchor: {old[:80]}')
    item.write_text(text.replace(old,new,1),encoding='utf-8')
    return True


def main():
    app='backend/app.py'
    patch(app,'from backend.r15 import ensure_schema as ensure_r15_schema, build_router as r15_router',
          'from backend.r15 import ensure_schema as ensure_r15_schema, build_router as r15_router\nfrom backend.r17 import ensure_schema as ensure_r17_schema, build_router as r17_router')
    patch(app,'        ensure_r15_schema(db)\n', '        ensure_r15_schema(db)\n        ensure_r17_schema(db)\n')
    patch(app,'app.include_router(r15_router(admin, db_conn))',
          'app.include_router(r15_router(admin, db_conn))\napp.include_router(r17_router(admin, db_conn))')
    for version in ('1.6.0','1.5.0'):
        src=(ROOT/app).read_text(encoding='utf-8')
        if f'version="{version}"' in src:
            patch(app,f'version="{version}"','version="1.7.0"')
            break
    index='frontend/index.html'
    patch(index,'</body>','  <script src="/static/r17_nav.js" defer></script>\n</body>')
    print('Voice Studio R1.7 wired into the local app. Run tests before using real data.')

if __name__=='__main__':main()
