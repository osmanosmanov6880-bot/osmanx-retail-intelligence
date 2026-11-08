# OSMANX Retail Intelligence R1.4 — Operations Integrity Center

R1.4 adds **five implemented operational workflows** over the existing R1.3 FastAPI/SQLite codebase. It does **not** deploy a public site, connect a physical POS terminal, perform banking settlement, grant automatic discounts or inspect individuals via video.

## 1. Controlled intake of receipt and stock events

`POST /api/admin/r14/inbox`, `GET /api/admin/r14/inbox`, `POST /api/admin/r14/inbox/{id}/review`.

- Only authorized owner/manager can stage/review; viewer roles can only inspect stores they may access.
- Store and organization scope is verified before writing; each `(organization_id, source, external_id, kind)` has a unique idempotency key. Different payload for the same key is HTTP 409.
- Receipt payload requires an integer amount in kopeks and an ISO 8601 timestamp with timezone. Stock payload requires valid SKU and quantity; unknown payload fields, including shopper contact fields, are rejected.
- Payload is capped at 8 KiB, and review cannot be repeated. Reviews do **not** create sales or update the actual warehouse.

## 2. Receipt-to-event reconciliation

`GET /api/admin/r14/reconciliation`, `/reconciliation/items`, `/reconciliation/export.csv`.

- Matches each staged receipt against the same store's existing `sales` row using `source` and `external_id`.
- Reports **matched**, **missing**, and **amount_conflict** separately, with actual/expected values and event status. The list UI can show individual exceptions.
- The CSV export has spreadsheet formula-escaping; the UI downloads with the authenticated session token rather than a public link.
- A match is **not proof of payment settlement** and a missing record is **not automatically inserted**.

## 3. Gift-cost evidence ledger

`GET/POST /api/admin/r14/gifts`, `POST /gifts/{id}/reverse`.

- Optional `coupon_claim_id` links a cost to an existing **redeemed R1.1 coupon and R1.2 fulfillment record**, requiring the same store, campaign name, amount and proof reference.
- A unique index prevents reusing a claim across different gift expense records. Costs without a coupon remain explicitly labeled `manual_entry` in the director's report.
- An owner can reverse a mistaken cost record with a reason, leaving the event in the audit log. A reversal does not reverse the physical giveaway or POS operation.
- The ledger and R1.2 campaign budget are separate accounting perspectives; **do not add their totals together** without a bookkeeping reconciliation.

## 4. Durable operational incidents

`GET /api/admin/r14/incidents`, `POST /incidents/sync`, `POST /incidents/{id}`, `GET /incidents/{id}/history`.

- Generates fixed signal IDs for pending events, missing receipts, amount conflicts, and manually evidenced gifts. Changing counts does not create duplicate incident identities.
- Requires `open → acknowledged → resolved`, an explanation, and an audit log. Reappearing signals reopen a resolved incident and create a history entry.
- All histories are scoped to the user's organization and authorized store.

## 5. Executive Integrity Center

`GET /api/admin/r14/board`, `GET /board/export.csv`, `/static/integrity.html`.

- Shows real recorded receipts, revenue, survey count, registered gift expenses, pending packets, reconciliation counts and incident state totals.
- Explicitly separates gift expenses linked to coupon documentation from manual records.
- Reports configurable windows from 1–90 days. No missing data is silently turned into a verified profit figure.
- Desktop 1440 px and mobile 390 px browser flows exercise writes and reads through FastAPI TestClient into SQLite.

## Local verification

```bash
python -m pytest tests/test_r14.py tests/test_r14_extended.py -q
python -m compileall -q backend scripts
node --check frontend/integrity.js
python scripts/r14_browser_smoke.py
```

For a full regression check, run `python -m pytest tests -q` on the **actual R1.3 repository**, not only the reconstructed R0.8 base. Re-test the migration against an existing R1.3 database before real client use.

## Known limits

- The application uses operator-entered and imported operational records, not independently attested financial statements.
- The R1.4 event inbox is a staging and verification workflow; there is **no automatic direct ERP/1C transfer**.
- Real-world consent/privacy notices, physical device testing, finance review, backup restores, and HTTPS security hardening remain to be completed prior to any production use.
- Public deployment remains intentionally deferred by the owner.
