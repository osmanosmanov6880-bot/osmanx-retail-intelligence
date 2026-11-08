# OSMANX Retail Intelligence R1.3 — Merchant Control Room

R1.3 adds **five connected functional modules**, without public deployment and without pretending that external 1C/POS equipment is connected. It uses the existing multi-organization FastAPI + SQLite database, authorization, staged import and receipt-item records.

## 1. Merchant CSV / 1C export adapter

`POST /api/admin/r13/csv/preview` accepts a CSV **text payload** (up to 300 KB, up to 2,000 data rows) with a store slug and `inventory` or `pos` kind. Supports Russian/English header aliases, semicolon/comma delimiters, UTF-8 or Windows-1251 when decoded in the web UI. It converts monetary values exactly to decimal rubles, store-local receipt datetimes to UTC, rejects negative quantities, duplicates, malformed rows and ambiguous headers. It delegates to the preexisting `import_batches` staging service and returns a **preview**; no inventory or sales are changed yet.

`POST /api/admin/r13/csv/commit` applies a specific staged batch only after explicit confirmation; expiry and preview-fingerprint checks apply, and repeated commits are idempotent. The **existing atomic import transaction** is additionally guarded so an inventory update cannot lower on-hand quantity below active reservations. This last validation is done in the same SQLite writer transaction as stock changes. Only `owner`/`manager` may commit or preview these imports.

**Not** an automatic 1C API connection. Exports must be provided manually; CSV columns must be reviewed before import. Imports of receipts do not automatically invent SKU-level line items.

## 2. Source/data quality ledger

`GET /api/admin/r13/quality?slug=central&days=14` reports traffic source events/total, receipt sources, staged/apply import counts, receipt item-row coverage, mismatched item sums, zero/missing cost and source warnings. Multiple traffic counters are not summed into a purported reliable conversion metric. Periods are bounded to 7–90 days, and large queries are rejected rather than silently truncated.

## 3. Size-demand matrix

`GET /api/admin/r13/demand?slug=central&days=30` combines active product/size/color requests with exact SKU matches, local stock, other same-organization branch stock and active stock reservations. Unknown/ambiguous SKU prevents any automated buying recommendation. Results are interest signals, not proven lost sales.

## 4. Inventory inactivity diagnostic

`GET /api/admin/r13/stock?slug=central&days=30` evaluates recorded SKU sale-item activity and active requests against stock on hand. It estimates only the portion of stock for which a positive unit cost exists in actual item rows, and otherwise withholds the total cost figure. "No recorded sales" is clearly a *data limitation*, not proof that an item is dead stock. Supported windows: 30, 60 and 90 days.

## 5. Evidence-bound executive actions

`GET /api/admin/r13/findings`, `GET/POST /api/admin/r13/actions`, `PATCH /api/admin/r13/actions/{id}`, and `GET /api/admin/r13/actions.csv` turn real warnings and signals into reviewable tasks. Creating a task saves an immutable evidence JSON snapshot with SHA-256 hash, audit log, source and store scope; repeated request IDs cannot create duplicate tasks. Updates use optimistic `version` checks, closure requires an explanatory note, and closed tasks cannot be rewritten. CSV export is escaped against spreadsheet formulas. Tenant isolation and role checks apply on every endpoint.

## Screens and tests

UI: `http://127.0.0.1:8000/static/control.html` (local only). Dark navy premium design, responsive on desktop and 390 px mobile; import workflow displays exact staged differences and requires confirmation before apply.

```bash
python -m pytest tests/test_r13.py -q
python -m pytest tests -q
python -m compileall -q backend scripts
node --check frontend/control.js
python scripts/r13_browser_smoke.py
```

Chromium checks all five sections and a **real preview → commit → SQLite readback** without hosting the application publicly. Browser screenshots are written to ignored `qa/r13-*.png` files. Do not treat browser QA as physical cash register, sensor, or HTTPS production acceptance.

### Important constraints

- No live connection to 1C, supplier ERP, cash register, physical sensor, or cameras has been established.
- No buyer profile, facial recognition or personal tracking; the dashboard uses aggregate store records.
- Profit, financial effect and causal attribution are not estimated from visitor interest or stock alone.
- Public deployment is explicitly deferred. Backups, external integration testing, privacy review and production security signoff remain separate steps.
