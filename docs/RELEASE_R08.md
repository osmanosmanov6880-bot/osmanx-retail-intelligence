# OSMANX Retail Intelligence R0.8 — strategy and action loops

## What's included: five integrated, usable modules

1. **Replenishment planning.** Groups recent *unfulfilled* product/size/color requests; resolves SKUs only when uniquely identified from existing catalog inventory or existing demand cases. Accounts for available stock and active holds. Produces a saved, idempotent plan. With owner/manager confirmation, SKU-by-SKU positive purchase costs and a named supplier, converts the plan to an ordinary **draft** in the already-existing `purchase_orders` / `purchase_order_lines` schema. It never submits orders to suppliers or claims requests equal lost revenue. Duplicate request IDs cannot create second plans or orders.
2. **Supplier delivery accountability.** Groups real purchase orders by supplier; calculates confirmed on-time fulfilment from expected dates and recorded receipts, overdue open orders, unfilled units, and human quality reviews. With fewer than three qualifying fulfilled orders, it withholds on-time percentages instead of displaying a misleading ranking. Supplier reviews are stored separately from dates and quantities.
3. **Fitting-room analysis.** Uses existing anonymous `fitting_observations` (or compatible `fittings`) and reports observed trials, recorded purchases and reasons. Low-conversion signals need a minimum observed sample. Owners can create hypotheses, move them into testing, and only mark them done with a concrete evidence note. No personal identification or camera inference.
4. **Owner's action queue.** Assignable tasks with deadlines, category, status transitions, idempotent request identifiers, and evidence-based closure. Assigned users must belong to the same company and have access to the store. Other tenants cannot view or update a store's tasks. Writes are auditable.
5. **Daily management brief.** Day calculation uses each store's timezone, reads actual visits/receipts and existing store workflows, clearly identifies mixed or demo sources, and returns reproducible KPI definitions. Owners can save immutable day snapshots (SHA-256) and download CSV with spreadsheet-formula escaping. A receipt total is not profit or return-adjusted revenue.

## How to open

Run locally according to the README, then open `http://127.0.0.1:8000/static/strategy.html`.
Use the same authenticated session as the main manager's console. Available links to R0.8 are also present from the R0.6 workflow and R0.7 operations pages. The new pages are in Russian and follow the navy/red minimal OSMANX styling.

## Verification

- `python -m pytest tests -q`: **67/67 passing** locally.
- `python -m compileall -q backend scripts`: succeeds.
- `node --check frontend/strategy.js` and existing frontend JavaScript checks: succeed.
- `python scripts/r08_browser_smoke.py`: Chrome desktop and 390px mobile, actual HTTP handlers through an in-process FastAPI TestClient, exercises restocking, purchase-order draft, supplier review, fitting hypothesis, tasks and saved brief snapshots; saves screenshots under ignored `qa/r08-*.png`.
- GitHub Actions is configured to repeat these validations on proposed PRs.

## Important limits

- No public deployment or hosting setup was performed. Existing deployment instructions remain optional, and this release adds no automated publication.
- No real 1C, POS, physical camera, sensor, or supplier messaging provider was connected during this release. Existing APIs can ingest permitted records, but integration with a specific provider requires separate acceptance.
- Request signals and fitting observations are **not** guaranteed missed purchases. Supplier timelines are recorded data, not contractual SLA certification. Comparing before and after does not establish causality.
- Financial screens show registered receipts and explicitly documented costs only; purchases, returns and stock movements require cross-checks against source data.
- Privacy: no facial recognition, customer profiles or uniquely identifying shopper trajectories are used in these new features.
- Multi-tenant rollout still requires independent production security and hardware testing.
