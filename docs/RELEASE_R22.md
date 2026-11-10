# OSMANX Retail Intelligence R2.2 — Multi-Store Rollout

A new five-part commercial rollout governance module. It works on top of **existing R2.0 Store Readiness and R2.1 Store Assurance**, without replacing either. This release is **not a public deployment**. Rollout status expresses documented management approval, not actual installation or cash/POS operations.

## Five implemented workflows

1. **Multi-store rollout plans:** `POST/GET /api/admin/r22/waves` stores title, objective, explicit budget in kopeks, one-to-five sequential stages, up to 25 stores, idempotency keys and immutable post-submission scope. Replaying a request with changed parameters returns HTTP 409. Stage numbering must be contiguous from one.
2. **Independent readiness of every branch:** `GET /api/admin/r22/waves/{id}` checks the latest independently reviewed R2.0 report for every branch, verifies its SHA-256, review identities and age at most seven days; consults unresolved R1.9 field incidents. This is documented process readiness, not a certification of equipment.
3. **Two-person launch authorization:** `POST /waves/{id}/request-review`, `POST /approve`, with owner approval by a user different from the requesting author. A failed readiness gate prohibits approval; capturing evidence freezes R2.0 readiness SHA for the authorized store and stage. Nothing is deployed automatically.
4. **Staged expansion, hold and recovery:** `POST /waves/{id}/advance`, `/pause`, `/resume`. Every completed stage gets an immutable, SHA-256-sealed report. A future stage is entered only after readiness checks for its branches. Existing stage proofs are verified to block progressing with tampered evidence. Active field incidents or expired readiness hold progression. Actions have audited transitions.
5. **Executive portfolio and export:** `GET /portfolio`, `/portfolio.csv` summarize stages, branch counts, blocking problems, budget and management status. CSV formula injection is escaped, scope follows organization and store permissions; no assumed ROI or fictitious financial outcomes.

## User interface

`/static/rollout.html` provides five API-backed tabs (plans, branches, evidence, governance, executive portfolio), Russian-only premium dark navy UI and 390px responsive layout; `/static/r22_nav.js` adds an optional sidebar link without overriding old navigation handlers.

## Local installation

From this delta source ZIP, in the same directory containing `backend/r22.py`:

```bash
python scripts/install_r22.py --root /path/to/osmanx-retail-intelligence
```

The installer validates version 2.1.0 anchors, copies only R2.2 files and inserts the migration/router/sidebar registration. It does not start a public server or overwrite the project's stored SQLite data. Back up production files and verify permissions before using a non-demo database.

## Quality gates

```bash
python -m pytest tests/test_r22.py -q
python -m compileall -q backend scripts
node --check frontend/rollout.js
node --check frontend/r22_nav.js
python scripts/r22_browser_smoke.py
```

The R2.2 test harness deliberately reuses the **R2.0 isolated SQLite fixture** (with minimal auth/database shims). The Chromium test drives real FastAPI request handlers via a local bridge, validates actual persisted writes, owner handoff, stage progress and CSV, and captures desktop/390px screenshots. These tests **are not evidence of full main application integration**; a complete repository CI and security review are required before merge.

## Important restrictions

- A reviewed checklist and SHA-256 do not independently verify hardware accuracy, bank settlement or business improvement.
- The module does not turn on devices, change 1C, send customer messages, order stock, issue discounts or publish sites.
- Large fleets require pagination and dedicated aggregation; one wave is capped at 25 stores.
- No buyer identity or biometric information is collected.
- Public hosting and live POS/hardware integrations remain separate user-approved work.
