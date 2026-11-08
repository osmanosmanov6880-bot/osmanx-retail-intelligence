# OSMANX RETAIL INTELLIGENCE R1.5 — PILOT STUDIO

**Status:** code and local acceptance completed. No public deployment or physical POS/camera/1C link was performed.

Pilot Studio provides the missing commercial proof workflow for a retailer's **7–30-day test**. A suggested default is a 14-day baseline and a 14-day trial; it is not a promise of improvements.

## Five end-to-end modules

1. **Pilot contract and frozen scope:** owner/manager chooses store, predeclares hypothesis and KPI, source selection (`sensor`, `manual` or `all`), equal nonoverlapping baseline/trial periods and cost budget. Repeated requests are idempotent by organization and conflict on differing content.
2. **Source reliability attestations:** record traffic/POS/feedback availability and operator verification notes. Explicitly *self-attested*, not automatically certified; can only be edited while the pilot is open.
3. **Daily observations and honest rate calculation:** use existing authorized store's visits, sales, anonymous surveys and demand. Supports store local timezone, reports source provenance, synthetic records, missing source dates, mixed sources, insufficient samples and zero-POS uncertainty. `receipts / entries` is **not** the percentage of unique paying customers.
4. **Immutable action/cost log:** scoped owner/manager append actions, actual recorded expenses and optional reference. Duplicate action requests return the original ID; changed duplicates return HTTP 409. Closed pilots cannot be modified.
5. **Frozen executive proof and CSV:** status `completed` only when the observation period has ended and at least one action exists. Freeze observation data, warnings and all recorded costs in one consistent SQLite transaction. SHA-256 detects tampering. Authenticated CSV export escapes spreadsheet formula-like strings. `cancelled` retains the separate reason and a snapshot.

## API

- `GET/POST /api/admin/r15/pilots`
- `GET /api/admin/r15/pilots/{id}`
- `POST /api/admin/r15/pilots/{id}/start`
- `POST /api/admin/r15/pilots/{id}/sources`
- `POST /api/admin/r15/pilots/{id}/actions`
- `GET /api/admin/r15/pilots/{id}/daily`
- `GET /api/admin/r15/pilots/{id}/preview`
- `POST /api/admin/r15/pilots/{id}/close`
- `GET /api/admin/r15/pilots/{id}/snapshot`
- `GET /api/admin/r15/pilots/{id}/snapshot.csv`

`/static/pilot.html`: five-step Russian-language experience with approved dark navy and restrained red design, mobile 390 px support and existing session-based access.

## Access and limits

- All endpoints use the existing admin authentication and store-organization permission checks. Only owner/manager roles mutate state. No anonymous write routes are introduced.
- No individual visitor tracking, facial recognition, identity inference, automatic coupon redemption, or payment execution.
- A missing visit source produces an undefined rate, not a fictional `0%` conversion.
- The application does not claim a causal effect from before/after comparisons. Source quality can be self-attested; a valid hash is proof of snapshot integrity, not independent truth of financial inputs.
- Money is recorded in integer kopeks. Logged action costs are not validated against banks or invoices.
- SQLite date aggregation has a strict input cap to avoid silently truncated totals. Very high-volume stores need a dedicated aggregation pipeline.
- Production backups, privacy notice, hardware calibration, external integration, security review and public HTTPS remain separate pre-launch work.

## Verification

```
python scripts/install_r15.py
python -m pytest tests/test_r15.py -q
python -m pytest tests -q
python -m compileall -q backend scripts
node --check frontend/pilot.js
node --check frontend/r15_nav.js
python scripts/r15_browser_smoke.py
```

The browser test uses Playwright Chromium plus FastAPI TestClient and an isolated SQLite database; it does **not** open a public website. Screenshot artifacts are `qa/r15-*.png` (ignored by Git).
