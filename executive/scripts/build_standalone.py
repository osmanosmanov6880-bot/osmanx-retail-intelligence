#!/usr/bin/env python3
"""Build a single offline HTML with inline CSS/JS. No npm, network or server required."""
from pathlib import Path
import re
base=Path(__file__).resolve().parents[1]
parts=[]
for name in ['model.mjs','ui.mjs','pdf.mjs','r3_core.mjs','r3_views.mjs','r4_core.mjs','r4_views.mjs','r4_dossier.mjs','r5_core.mjs','r5_views.mjs','r5_report.mjs','app.mjs']:
    code=(base/'src'/name).read_text()
    code=re.sub(r'^import .*? from [\'\"].*?[\'\"];\s*$', '', code, flags=re.M)
    code=re.sub(r'\bexport\s+(?=(const|let|var|function|class)\b)', '', code)
    parts.append('// MODULE '+name+'\n'+code)
js='\n'.join(parts)
(base/'build_check.js').write_text(js)
css=(base/'src/styles.css').read_text()+'\n'+(base/'src/luxury.css').read_text()+'\n'+(base/'src/r3.css').read_text()+ '\n' + (base/'src/r4.css').read_text()+ '\n' + (base/'src/r5.css').read_text()
import base64
asset=(base/'assets/atelier-scene.webp').read_bytes()
css=css.replace("url('../assets/atelier-scene.webp')", "url(data:image/webp;base64,"+base64.b64encode(asset).decode('ascii')+")")
html=f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover" />
<meta name="color-scheme" content="dark" /><meta name="theme-color" content="#070b13" />
<title>OSMANX — Retail Intelligence Executive</title>
<style>{css}</style></head>
<body><div id="app"><div class="boot">OSMAN<span>X</span><small>RETAIL INTELLIGENCE</small></div></div>
<script>{js}</script></body></html>'''
output=base/'OSMANX_EXECUTIVE_OFFLINE.html'
output.write_text(html)
print(f'{output} · {output.stat().st_size:,} bytes · self-contained')
