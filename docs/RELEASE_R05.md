# OSMANX Retail Intelligence R0.5 -- commerce intelligence workflows

R0.5 implements five functional workflows on top of the R0.4 API, SQLite database and Russian-language desktop/tablet/mobile design. All numbers in demo mode are synthetic. No public deployment was performed.

## 1. Branch-to-branch item reservations

- A manager opens an unresolved size/colour request, searches exact normalized matches among authorized sibling branches, then reserves one or more available units for 1-72 hours.
- `POST /api/admin/reservations` requires `demand_id`, `inventory_id`, and an idempotency `request_id`; optional quantity (1-20) and hours (1-72).
- `BEGIN IMMEDIATE`, available = physical quantity minus unexpired holds, and a unique partial index prevent double-claiming an active demand.
- Reservations can be cancelled or marked as physically collected. Collection reduces source stock **but does not create a sale**. Only an independently recorded POS receipt is a sale.
- Expiration cleanup is scoped to the organization. Stock updates and staged imports may not reduce the quantity below active holds.
- The source branch must be in the same organization, and all affected branches must be accessible to the user.

## 2. Anonymous fitting-room journal

- `POST /api/admin/fittings`: store, product, size, number of fitting trials, purchases observed, one stated reason.
- Validation rejects negative/oversized aggregates and purchases exceeding trial count.
- `GET /api/admin/fittings` reports 7- or 30-day grouped trial counts, observed purchase shares, and reason frequencies.
- Reasons are counted by **observation record**, not by individual buyer. There are no identities, video tracking or claims about every visitor.

## 3. Recorded merchandise returns

- `POST /api/admin/returns`: store, prior sale ID, a stable external return ID, item description, reason, amount in integer kopeks.
- An immediate SQLite transaction prevents duplicate refund IDs and aggregate return amounts above the original sale amount.
- Cross-store receipt references are rejected, and each organization's store scope is checked server-side.
- `GET /api/admin/returns` separates return volume/reasons from gross sales reports. **No payment refund, POS operation, or automatic modification of the original receipt is initiated.** Without POS line items, the item's SKU cannot be independently verified.

## 4. Discount gross-margin scenarios

- `POST /api/admin/pricing` accepts price, unit cost, proposed discount (basis points), baseline and assumed scenario units.
- Integer kopeks with Decimal half-up rounding avoids floating-point currency drift.
- Shows unit contribution, before/after gross-profit scenarios, the delta, break-even unit count, and a warning for nonpositive post-discount contribution.
- This is a deterministic planning calculation, **not** an ML forecast or proof of incremental profit. Tax, rent, returns, marketing and elasticity are not included.

## 5. Evidence-driven decision center

- `GET /api/admin/decisions` derives actionable signals from repeated unfilled requests, weak fitting purchase rates, repeat return reasons and pricing scenarios below cost.
- Each signal cites observable count/period and an explicitly limited recommendation.
- Owner/manager users may set `new`, `testing`, `done`, `dismissed`, with a note via `PATCH /api/admin/decisions/{decision_key}`; these states persist in `decision_tasks` by store and key.
- No synthetic "lost profit" or guaranteed conversion lift is presented as fact.

## Authentication and organization boundaries

- All `/api/admin` endpoints require a valid authenticated session outside local demo mode.
- Only owner/manager can mutate; read-only roles can inspect authorized stores.
- Cross-organization requests and reservations are not accessible, and the expiry sweep does not modify another tenant's rows.
- The customer kiosk is a separate flow and has no access to these admin endpoints.

## Upgrade and acceptance

- R0.5 schema additions use `CREATE TABLE IF NOT EXISTS` and secondary indexes; startup preserves R0.4 sales, demand, users and kiosk/POS data.
- Fresh schema and R0.4-shaped upgrade paths are tested; `PRAGMA integrity_check` and `foreign_key_check` pass.
- Server suite: `python -m pytest tests -q`.
- Browser acceptance: `python scripts/visual_smoke.py`, `python scripts/r03_browser_smoke.py`, `python scripts/r04_browser_smoke.py`, and `python scripts/r05_browser_smoke.py`.
- Browser flows verify genuine forms and round trips through SQLite, with both desktop and 390px mobile layouts; screenshots are written to `qa/` (not committed).

## How to run locally

```
python -m pip install -r requirements.txt pytest httpx playwright
python -m playwright install chromium
OSMANX_DEMO_MODE=1 python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. Synthetic demo mode bypasses login and **must never be exposed publicly**. For an internal protected pilot, see `docs/DEPLOYMENT.md`.

## Not included in R0.5

- No public HTTPS deployment, live camera integration, face identification or individual shopper tracking.
- No direct vendor-specific 1C connector or real POS refund command.
- No automatic transfer of goods across locations or customer SMS messaging.
- Physical store operation still requires staff confirmation, data-quality validation and local legal/privacy review.
