# OSMANX RETAIL INTELLIGENCE — R0.6

**Status:** local development release; public deployment intentionally deferred. The new module runs on the existing Python/FastAPI/SQLite stack and retains the navy/red design. All UI labels are in Russian. Older R0.5 functionality is preserved: no data migrations overwrite its `reservations`, `fitting_observations`, `merchandise_returns`, `price_scenarios` or `decision_tasks` tables.

## Five completed implementation blocks

| # | Capability | Server & persistence | Customer-facing UI | Acceptance |
|---|---|---|---|---|
| 1 | Demand recovery pipeline | `demand_cases` links an existing real request to a SKU, authorized reservation, supplier line or SKU-specific sale receipt. State changes are audited. | Demand queue and case workflow. | Reject other tenants, duplicated cases and sale proof without matching SKU/quantity. |
| 2 | Purchasing and warehouse | `purchase_orders`, line items, SHA256-keyed delivery documents, `stock_movements`, SQLite `BEGIN IMMEDIATE` inventory increments. | Supplier PO forms (multi-line), send/cancel, partial delivery confirmation. | Partial/full receipts, idempotent replays, conflicting invoice, mismatched SKU details and transaction rollback. |
| 3 | Documented SKU gross margin | `sale_items` references actual sale records. Unit prices and costs in integer kopeks, receipt total cap, unique row IDs. Returns are shown separately. | Allocation to receipt and margin coverage. | Prevent over-allocation, cross-store receipts and repeated item IDs; exact amount tests. |
| 4 | Measure decisions (before/after) | `decision_evaluations` references existing `experiments`, with two completed date windows, a fixed visit source policy, metric snapshots, warnings and disclaimer. | Experiment selection, period/date inputs, history and charts. | UTC-offset/date grouping, missing visitor data, mixed source alerts, no unproven causal claims. |
| 5 | Director action center | Aggregates actionable demand, ordered stock, unallocated receipt counts, quality notes, exports with spreadsheet injection protection. | Premium responsive 1440/390px interface with connected forms, CSV export and link from the main cabinet. | Chromium flows, role/tenant tests, preservation of existing dashboards. |

## Where to open it

Run locally:

```bash
OSMANX_DEMO_MODE=1 python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

- Owner's existing dashboard: `http://127.0.0.1:8000/`
- **R0.6 Operations Center:** `http://127.0.0.1:8000/static/workflows.html`
- Existing exit survey kiosk: `http://127.0.0.1:8000/kiosk/central`

The source of truth is the existing SQLite database under `OSMANX_DATA_DIR`. In real mode the new page reuses the existing session token (`sessionStorage`) and **never** stores device/POS master keys in the browser.

## API added

All routes require organization/session authorization via the existing `admin` dependency. Write permissions: owner/manager; analysts may save comparisons; viewers read only.

- `GET /api/admin/workflows/overview?slug=central`
- `POST /api/admin/workflows/cases`
- `PATCH /api/admin/workflows/cases/{id}`
- `POST /api/admin/workflows/orders`
- `PATCH /api/admin/workflows/orders/{id}`
- `POST /api/admin/workflows/orders/{id}/receipts`
- `POST /api/admin/workflows/sale-items`
- `POST /api/admin/workflows/evaluations`
- `GET /api/admin/workflows/export?slug=central&dataset=cases|orders|sale_items|evaluations`

### Example: create and receive a purchase order

```json
{
  "slug": "central",
  "supplier": "Sample supplier",
  "reference": "PO-0001",
  "lines": [{"sku":"JKT-XL","product":"Jacket","size":"XL","color":"black","quantity":3,"unit_cost_rub":"1200.50"}]
}
```

Submit as a draft, transition to `ordered`, then receive it with a unique external delivery ID and line IDs from `/overview`. Same invoice + same content returns `duplicate:true`; same invoice + different content returns HTTP 409. A receipt updates inventory in a single transaction. This is a **manual receiving process**, not a live ERP or POS connection.

## Data and financial honesty

- Demand is **not** counted as a sale. Recovery requires a real registered receipt **with a SKU-specific recorded line and sufficient quantity**. A held reservation alone is not a purchase.
- Supplier purchase orders are commitments in a workflow, not proof that funds were paid or stock arrived. Only confirmed receipts change inventory.
- Gross margin is calculated only for documented sale items with entered cost; unallocated receipts are counted and disclosed. Aggregate returns are separately displayed, because existing refunds lack reliable SKU-level cost allocations. It is not net profit.
- Before/after comparisons are descriptive only. Seasonality, promotions, measurement changes and incomplete traffic sources may explain differences. No causal lift is claimed.
- Input is store-scoped and authenticated; customer names, facial recognition or individual camera tracking are not introduced.

## Automated verification

```bash
python -m pytest tests -q
python -m compileall -q backend scripts
node --check frontend/workflows.js
node --check frontend/r06_shortcut.js
python scripts/r06_browser_smoke.py
```

Additional compatibility tests reproduce the real R0.5 GitHub table layout, including `reservations` and `merchandise_returns`. The browser test exercises case creation, purchase order, goods receipt, SKU item sale and experiment evaluation at desktop and 390px mobile sizes.

## Remaining blockers for customer production

- A private HTTPS server deployment and isolation testing (explicitly postponed by the owner).
- Concrete 1C and POS adapters, signed imports from real devices and actual integration testing on those systems.
- SKU-level return adjustments, exchange workflows, operational reconciliation and cost allocation.
- Data protection compliance, backup restore drill, load tests and authentication hardening for production.
