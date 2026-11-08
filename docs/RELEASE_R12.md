# OSMANX Retail Intelligence R1.2 — Retail Desk

R1.2 adds five production-shaped **local** workflows on top of the existing R1.1 Growth Intelligence schema. No public deployment. Russian premium dark interface: `/static/retail_desk.html`. Authentication and branch access reuse the existing OSMANX session.

## 1. Cashier lookup & receipt linking

- `POST /api/admin/r12/cashier/receipt`: exact match by selected store + POS source + external receipt ID; does **not** create a receipt or a sale. Returns only the existing receipt, no profile.
- `POST /api/admin/r12/cashier/link`: owner/manager links a valid opt-in `OXM-` card to that already recorded sale in one transaction. Identical retries are idempotent; conflicting card links are refused (`409`).
- Branch authorization is checked before both read/write. `viewer` cannot change records.

## 2. Verified coupon lifecycle (no fictitious POS redemption)

- `POST /api/admin/r12/coupons/inspect`: exact coupon lookup by store, returns state and whether receipt verification or employee handoff proof exists.
- `POST /api/admin/r12/coupons/cancel`: unredeemed *issued* coupon can be cancelled by owner/manager; committed budget decreases. A redeemed or fulfilled coupon cannot be cancelled.
- `POST /api/admin/r12/coupons/fulfill`: after R1.1 receipt verification (`status=redeemed`), employee signs off a physical gift with a unique proof reference and a descriptive note. This is an **employee attestation**, not a POS-confirmed inventory movement or a monetary payment. Repeat proof is idempotent; a different proof conflicts.
- Coupon and card raw secrets are never stored in database; only SHA-256 digests of 128-bit secrets. Fulfillment stores no buyer identity.

## 3. Campaign budget/funnel controls

- `GET /api/admin/r12/campaigns/controls`: issued, redeemed, cancelled and physically fulfilled counts; committed budget vs. employee-attested estimated costs; remaining budget and claim limit. Uses existing `campaigns_r11` and `campaign_claims_r11` without duplicating canonical records.
- Linked receipt revenue is **not** incremental ROI. Employee handoff cost uses configured unit cost; it is not verified cash expense.

## 4. Cohort analytics for return visits

- `GET /api/admin/r12/retention`: compares eligible/fully matured 7-day, 30-day and 60-day first-purchase cohorts for members with voluntarily linked receipts; additionally monthly cohorts and receipt coverage. Excludes cards revoked in R1.1 and immature cohorts from denominators.
- Based on UTC-aware purchase timestamps; not all shopper traffic is identified or profiled.

## 5. Executive control panel and CSV

- `GET /api/admin/r12/executive?slug=central&days=30`: registered receipts, visits by original source, receipt conversion (where calculable), unresolved requests, campaigns, retention, and unresolved R0.7 help requests if that source exists. Warns about mixed manual/sensor data and synthetic/demo visits.
- `GET /api/admin/r12/executive/export`: authenticated UTF-8 BOM CSV, formula-safe escaped values. No net-profit or causal lift claim.
- Five UI tabs are fully API-backed, with working forms, responsive layout (1440 and 390 pixels), and persisted SQLite changes.

## Running and testing

```bash
pip install -r requirements.txt pytest httpx playwright
python -m pytest tests/test_r12.py -q
node --check frontend/retail_desk.js
python scripts/r12_browser_smoke.py
OSMANX_DEMO_MODE=1 python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Visit `http://127.0.0.1:8000/static/retail_desk.html` after signing in to the primary dashboard. The demo mode uses synthetic records; all tested mutations are local.

## Limitations / launch gate

- No connection to the actual store's 1C instance, POS terminal, camera, door counter or CRM has been made. Receipt lookup requires a previously imported receipt, not a free-text claim.
- No direct gift distribution, discount, billing, refund or POS command is executed.
- The manager confirmation of handoff is *not cryptographic proof of real-world delivery*; physical handoff needs independent operational control.
- No phone, name, face recognition or individual camera profiling; anonymous cards are 128-bit random secrets.
- Production deployment requires separate external security, privacy and legal review, backup drills and actual device acceptance; it remains deferred by user request.
