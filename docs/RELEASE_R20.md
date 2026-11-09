# OSMANX RETAIL INTELLIGENCE R2.0 — STORE READINESS

Five separately persisted operational workflows; all actions are scoped to authenticated organizations and stores. **No production launch or public hosting is performed**. Compatible with the R1.9 Field Operations router and original R1.7 Voice Studio store records.

## Five implementations

1. **Opening checklist:** Eight configurable-by-code operational assertions (tablet, network, consent notice, test survey, counter, POS evidence, trained staff, privacy settings), stored with outcome, explanation, actor and change audit. Missing and failed checks block review. Marking essential controls "not applicable" also blocks approval.
2. **Counter calibration:** Append-only, idempotent measurements, comparing a manually recorded reference count with a physical counter reading. Calculated absolute and percentage error; review requires two measurements each with at least 20 manually counted arrivals and <=10% deviation. This is a procedural record, **not independently verified hardware telemetry**.
3. **Daily source reconciliation:** Counts visits, POS receipt records and anonymous survey openings/responses for the store's local calendar date. Timestamps are timezone-aware even if legacy rows have mixed UTC offsets. Inputs are bounded (max 25k rows per source table per store) to prevent silent partial totals. Records and the operator's note are retained; their presence does not prove paid settlement.
4. **Shift handover:** Stores a full action/issue description with a stable unique request key; recipient must be a distinct authorized user. Prevents double acknowledgement and blocks edits after review request. The review gate requires an acknowledged handover.
5. **Independent readiness gate:** Validation checks, multi-step review, separate reviewer (owner role), snapshot SHA-256, permanent review record, audit history and authenticated, spreadsheet-safe CSV. A final `reviewed` state is an internal procedural decision only, **not a certified physical readiness statement**.

## Files

- `backend/r20.py` — repeatable SQLite migration, Pydantic contracts, 13 protected API routes and five workflows
- `frontend/readiness.html`, `readiness.css`, `readiness.js` — five-tab premium Russian interface with responsive 390px styling
- `frontend/r20_nav.js` — additive main sidebar shortcut
- `scripts/install_r20.py` — idempotent integration, requires a checkout with R1.9 anchors
- `tests/test_r20.py` — isolated FastAPI/SQLite contracts and permission checks

## Local acceptance

```sh
python -m pytest tests/test_r20.py -q
python -m compileall -q backend scripts
node --check frontend/readiness.js
node --check frontend/r20_nav.js
```

**Important:** The included tests use isolated compatibility shims for pre-existing security/auth/database helpers, not the live repository. Run the complete existing R0.2–R1.9 test suite, integration test against an existing R1.9 SQLite copy and browser QA in the actual checkout before merging or connecting real hardware. Do not mistake 5/5 isolated tests for full CI acceptance.

## Installation into an existing checkout

```sh
python scripts/install_r20.py --root /absolute/path/to/osmanx-retail-intelligence
```

Copy this R2.0 delta package to the checkout's work machine. The installer does not connect real devices, publish the service, create users or alter live financial records. The R2.0 schema is created through application startup after installation.

## Data integrity and limits

- No individual buyer identification, face matching or automated camera tracking.
- Staff assertions and manually entered measurements are not independent physical proofs.
- Transactions are grouped by store-local day; no bank settlement, item-level economics or reconciliation to a payment provider.
- The immutable snapshot guarantees consistency with its stored JSON only; it is not a signature issued by a third-party auditor.
- Physical sensor calibration, authorization under actual production account roles, HTTPS, backups and privacy notices remain separate acceptance gates.
