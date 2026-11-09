# OSMANX Retail Intelligence R2.1 — Store Assurance

**Five new persistent workflows**, tested with R2.0 Store Readiness. This is a local source release and has **not** been merged to GitHub `main` or deployed publicly merely by generating the source archive.

## 1. Multi-store operating portfolio

`GET /api/admin/r21/portfolio` and `/portfolio.csv` show only stores authorized to the current account principal, with the latest opening-day status, review SHA-256 integrity, review age and open tickets. CSV is spreadsheet-formula-escaped. At most 100 stores are processed in one call; larger accounts require pagination.

## 2. Counter calibration drift

`GET /api/admin/r21/drift?slug=central&days=30` aggregates actual calibration samples from R2.0. Samples below 20 manually counted visits are excluded from the error median. Tracks over-10% error, day-wise medians, insufficient sample flags and status `no_data / limited / observed / drift`. These records are only statements of staff-observed calibration, not certified hardware telemetry.

## 3. Reconciliation continuity

`GET /api/admin/r21/continuity?slug=central[&readiness_id=ID]` recounts visits, registered receipts and anonymous survey opens/responses for the local business day, then compares each counter to the last stored R2.0 reconciliation. Late inserts and deletions are visible in signed differences. Archived R2.0 summary SHA-256 is verified; a legitimate SHA does not independently prove a payment cleared.

## 4. Auditable blocker remediation

`GET /api/admin/r21/tickets`, `POST /tickets/sync`, `PATCH /tickets/{id}/assign`, `PATCH /tickets/{id}`, `GET /tickets/{id}/history` turn R2.0 review blockers, over-limit calibration and after-reconciliation data changes into durable store-scoped work orders. Synchronization is idempotent per issue and readiness day. Assign an owner and a due date. Changes follow `open -> working -> verified / dismissed`. Closing a ticket requires the owner role, an evidence note and a different staff member from the creator. Manual acknowledgments are not independent hardware proofs.

## 5. Integrity-gated pilot startup

`GET /api/admin/r21/pilots/{id}/preflight?readiness_id=ID`, `POST /pilots/{id}/safe-start`, `GET /pilots/{id}/startup-proof` make a **new, guarded start path** for an existing R1.5 Pilot Studio draft. It verifies matching organization/store, latest independently reviewed R2.0 day no more than seven days old, intact frozen SHA-256, current operational records equal to frozen evidence, unchanged visits/receipts/surveys since reconciliation, acceptable calibration and absence of open remediation tickets. On success, it switches only the pilot status to `running` in the same SQLite transaction as the immutable SHA-256 preflight record and audit event. Repeat requests are idempotent; conflicting readiness references fail.

**Important:** The older `POST /api/admin/r15/pilots/{id}/start` endpoint still exists. This R2.1 guarded API does **not** silently replace it or make the requirement universal. The installation of a mandatory gate into the legacy path should be a separate backward-compatibility/release decision. Nothing starts public hosting, modifies a payment, triggers a supplier order, or reads identities from cameras.

## Files and installation

The combined ZIP contains both R2.0 and R2.1 source deltas because the GitHub `main` verified at build time included only R1.9. The R2.1 source installer can first apply the bundled R2.0 migration:

```bash
python scripts/install_r21.py --root /absolute/path/to/osmanx-retail-intelligence --install-r20
```

This copies source files and adds migration/router imports; **it does not connect to a live database, deploy or publish a server**. For current GitHub integration, place the actual changed files in a feature branch and run all previous R0.2–R1.9 tests before merging. No tracked original data files should be overwritten.

## Local checks (isolated compatibility harness)

```bash
python -m pytest qa_contracts/test_r20.py qa_contracts/test_r21.py -q
python -m compileall -q backend scripts
node --check frontend/assurance.js
node --check frontend/r21_nav.js
python scripts/r21_browser_smoke.py
```

The local test harness uses FastAPI and genuine SQLite but stubs legacy authentication helpers, so passing tests here **does not** establish production authorization correctness. The Chromium suite exercises portofolio, CSV, data drift, safe-start, two-role ticket work and 390 px mobile layout, again against an isolated database. Full repo CI, production HTTP, real equipment, HTTPS, backups and privacy notices require separate acceptance.
