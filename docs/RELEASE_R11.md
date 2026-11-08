# OSMANX Retail Intelligence R1.1 — Growth Intelligence

**Development release only. No public deployment.** Five business workflows are implemented on top of the existing authenticated organization/store API and SQLite database. The Russian premium dark UI is available at `/static/growth.html` after local startup.

## 1. Anonymous, voluntary loyalty cards

- `POST /api/admin/r11/members` requires `explicit_opt_in=true`, owner/manager role, and access to the selected store.
- Issues a **cryptographically random 128-bit code** (`OXM-` + 32 hex characters), displayed only once. SQLite stores only its SHA-256 digest, never the plaintext. No name, phone, email, birth date, or video profile is collected.
- `GET /api/admin/r11/members` lists metadata, never secret codes.
- `DELETE /api/admin/r11/members/{id}` revokes the card, invalidates its secret, erases its receipt associations and unredeemed coupon links. Redeemed campaign records remain as anonymized business aggregates.
- These codes are **not proof of identity**; staff must follow the store's consent and validation process. Manual handling is not a substitute for legal/privacy review.

## 2. Actual receipt linking and return purchases

- `POST /api/admin/r11/receipts` links an existing sale ID to a member's voluntary card within the same organization and an accessible store.
- SQLite `BEGIN IMMEDIATE`, `UNIQUE(sale_id)`, and conflict checks prevent double-ownership of the same receipt. Repeat attempts with identical member and sale are idempotent.
- `GET /api/admin/r11/receipts` shows up to 100 recent linked receipts for the selected store.
- A linked receipt is a real recorded sale; it is **not** proof the loyalty program caused that sale.

## 3. Bounded bonus campaigns

- Create a dated store-scoped campaign with a maximum count, fixed estimated cost per incentive, maximum budget and minimum receipt spend.
- Each member may claim at most one incentive per campaign. Issue/redeem operations are transaction-safe and prevent exceeding the reserved budget even under concurrent requests.
- Coupons (`OXC-` + 32 hex characters) are displayed once, hashed in storage, redeemable only against an existing receipt linked to the same member, in the same store, meeting the minimum sale amount and campaign period.
- Campaigns can be paused. `GET /api/admin/r11/campaigns/{id}/effect` distinguishes receipt revenue from **additional** revenue; ROI and net profit are deliberately `null` when there is no reliable counterfactual and actual costs.
- **No POS discounts or gifts are automatically issued**, and no customer messages are sent. These are manual verification records and estimated reward liabilities.

## 4. Cohort retention with evidence limits

- `GET /api/admin/r11/retention?slug=central` summarizes only sale-linked opt-in members in an authorized store; the owner can request aggregate organization-wide results with `all_stores=true`.
- Cohorts use the first linked receipt UTC month and compute subsequent purchases within 30 days. The denominator excludes participants whose first purchase is younger than 30 days.
- Response exposes the share of linked receipts among all recorded receipts; this guards against claiming that the opt-in sample represents every shopper.
- Membership/receipt links can be erased, so retention figures can change after privacy requests.

## 5. Inventory-grounded assortment signals

- `GET /api/admin/r11/assortment?slug=central&days=30` supports 7–90 days.
- Uses recorded demand, exact normalized product/size/color matches in existing inventory, and actual `sale_items` for SKU-specific sales. Ambiguous requests are excluded and counted separately.
- Signals: investigate replenishment after repeated requests with no recorded quantity, check shelf availability when requested stock exists, or verify availability when SKU sells and appears out of stock.
- This is **not** a purchase-order trigger, demand forecast, guaranteed lost profit, or live available-to-promise quantity: inventory may include reservations and physical discrepancies.

## Local verification

```bash
python -m pytest tests/test_r11.py -q
python -m compileall -q backend scripts
node --check frontend/growth.js
python scripts/r11_browser_smoke.py
```

The Chromium suite drives real forms via FastAPI TestClient, verifies SQLite writes and reads, checks a 390px mobile viewport, and produces `qa/r11-*.png` screenshots. It does not prove a public HTTPS deployment or real hardware compatibility.

## Security and data handling boundaries

- All admin API operations require a verified user session and use store/organization permissions; writes require owner or manager role.
- Screens do not persist the issued codes in browser storage. Only cryptographic digests reach SQLite.
- The app does **not** collect customers' name, phone or direct contact details; it also does not connect data to cameras, faces or physical tracking.
- Amounts are integer kopeks. Bonus costs are estimated and are **not** actual discounts, refunds or confirmed expenses.
- Before using with real customers: obtain appropriate consent notices, establish retention and erasure procedures, test security including POS integration and review local law.
- No real 1C, POS terminal, camera, email/SMS gateway, or public server is connected by this release.
