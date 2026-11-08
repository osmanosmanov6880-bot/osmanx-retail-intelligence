# OSMANX Retail Intelligence R0.9 — Evidence Lab

Five connected, real modules on top of the existing SQLite and FastAPI platform. **No public hosting or hardware deployment.** The Russian-language executive interface lives at `/static/evidence.html`; its five tabs use the same authenticated organization and store selection as the existing owner console. The previous R0.8 dashboard links to the new interface.

## 1. Demand Radar — a signal, not a sale

`GET /api/admin/r09/radar?slug=central&days=14`: compares active unanswered requests in two consecutive equal UTC windows (7–45 days each), resolves SKUs only from an existing demand case or unique matching inventory metadata across the organization, subtracts active stock holds, and identifies outstanding ordered units in the current store. Ambiguous SKUs stay ambiguous; an interest signal never becomes "lost revenue" without evidence. Sources and warnings are exposed.

## 2. Recovery Playbooks — only verified purchases count

`GET/POST /api/admin/r09/recoveries` and `PATCH /api/admin/r09/recoveries/{id}`: one scoped plan per demand request, status transitions, conflict-safe idempotency keys, audit records, and a distinction between operational repair and a verified sale. A `confirmed_sale` result requires a real receipt with the *same SKU* in its item rows, at the same store. On success it links the transaction in demand history; there is no invented order, notification or customer contact. Closed cases cannot be rewritten.

## 3. Finance Integrity — no fictitious contribution

`GET /api/admin/r09/finance?slug=central&start=YYYY-MM-DD&end=YYYY-MM-DD`: compares recorded receipt totals against actual item rows, requires nonzero recorded unit costs, and withholds the overall gross contribution when coverage is incomplete. It supports both previously used return-ledger schema variants, explicitly marking return events as **not verified bank refunds**. All monetary values are integer kopeks. Windows are based on the store's timezone. The result includes completeness metrics and warnings.

## 4. Pre-registered Experiments — comparisons with limitations

`GET/POST /api/admin/r09/protocols`, preview and evaluate routes: an immutable hypothesis, equal nonoverlapping before/after periods, comparable traffic-source selection and an optional control branch in the same organization **only when access is granted**. Metrics: receipts per 100 visits or receipt revenue per recorded entry. Warnings expose small samples, inconsistent data sources, and demonstration events. A descriptive difference (including optional difference-in-differences) is not causal evidence. Frozen evaluations store SHA-256 of the source/result snapshot and cannot be re-evaluated.

## 5. Executive Evidence Dossiers — immutable records

`GET/POST /api/admin/r09/dossiers`, GET a dossier or export its CSV. Owner/manager creates a one-time snapshot for a bounded financial window (up to 30 days); it includes finance integrity, most recent 14-day demand radar, case status aggregates, experiment hashes, collection timestamps and limitations. Payload SHA-256 and idempotency keys prevent rewriting a historical result. CSV fields use spreadsheet-formula escaping. This is an evidence pack, not an audited financial statement.

## Verification commands

```bash
python -m compileall -q backend scripts
node --check frontend/evidence.js
node --check frontend/strategy.js
python -m pytest tests/test_r09.py -q
python scripts/r09_browser_smoke.py
```

The browser suite uses Playwright Chromium with a FastAPI TestClient bridge and checks real endpoint-driven interactions at desktop and 390 px mobile widths without running a public server. Generated screenshots are under ignored `qa/r09-*.png`.

## Release limits and privacy

- No real 1C/ERP, physical camera, POS terminal or occupancy sensor was connected during this implementation. Existing ingestion interfaces remain available for separately verified integrations.
- No individual video tracking, face recognition or personal buyer profiles are used. The terminal remains anonymous.
- Demand and negative feedback are observations, never guaranteed lost revenue. Missing sources do not become zeros in a claimed profitability assessment.
- This is a private/local software release. Production security review, data protection documentation, hardware testing and public HTTPS deployment are **out of scope and deferred**.
- The implementation handles both historical R0.5 reservations schemas and both historical returns schemas, but does not migrate either one destructively.
