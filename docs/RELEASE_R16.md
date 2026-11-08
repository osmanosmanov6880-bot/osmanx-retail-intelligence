# OSMANX Retail Intelligence R1.6 — Pilot Command

This release connects R1.5 Pilot Studio to a five-step decision workflow for owners and managers. There is **no public deployment, no automatic POS/ERP operation**, and no buyer identity tracking. `/static/command.html` is the new dark-blue Russian-language interface.

## Five implemented modules

1. **Scoped pilot portfolio:** `/api/admin/r16/portfolio[.csv]` aggregates only the organization's pilots and branches authorized to the current user. Displays source quality, phase change, status, actions and open follow-up work. Max 100 pilots per request; larger accounts require pagination/batch aggregation.
2. **Integrity and readiness gate:** `/api/admin/r16/pilots/{id}/quality` checks zero-traffic days, low samples, absent POS rows, demo events, mixed or changed traffic sources, staff source attestations, periods not yet finished, source inconsistencies, frozen-snapshot hash and late-event drift. These rules are screening thresholds, **not** independent auditing or causal attribution.
3. **Immutable scenario economics:** `GET/POST /pilots/{id}/scenarios` accepts an explicitly assumed average ticket and gross-margin percentage. It models conditional additional gross contribution from the observed difference in *receipts per 100 entries*, deducts separately logged pilot action costs, and states these are neither confirmed profits nor causal gains. No computation is made when the KPI or source rows cannot support it. Money is in integer kopeks and gross margin uses basis points.
4. **Two-person rollout review:** `GET/POST /pilots/{id}/rollout`, `POST /rollouts/{id}/review`. A completed R1.5 pilot needs an integrity-checked immutable snapshot; the originating author cannot approve their own proposal, review requires the owner role and blocks approval if readiness checks fail. Approval records a decision **only**; it never publishes software, spends funds or commands a cash register.
5. **Follow-up execution with audit trail:** `GET/POST /pilots/{id}/followups`, `PATCH /followups/{id}`, `GET /followups/{id}/history`. Tasks have owner, deadline, idempotency key, explicit allowed transitions and evidence notes. Duplicate requests with mismatched content return 409. Closed transitions remain immutable in the history table.

## Implementation and database

- New module: `backend/r16.py` with a repeatable, non-destructive SQLite migration (`ensure_schema`).
- UI: `frontend/command.html`, `command.css`, `command.js`, optional sidebar shortcut `r16_nav.js`.
- `scripts/install_r16.py` is idempotent and will only add R1.6 to the existing R1.5 application when known anchors are present. Run from an up-to-date checkout. `README` and GitHub CI are wired in the released branch.
- The module respects existing R1.5 authentication, organization scope and store access controls. It creates no public write endpoints.

## Tests

```bash
python -m pytest tests/test_r16.py -q
python -m pytest tests -q
python -m compileall -q backend scripts
node --check frontend/command.js
node --check frontend/r16_nav.js
python scripts/r16_browser_smoke.py
```

The Chromium acceptance tests use a FastAPI TestClient bridge with isolated SQLite. It checks real data writes and UI at 1440 and 390 px; it does not test physical tablets or internet hosting.

## Known limits and release gate

- Assumed gross margin and average ticket are hypothetical until verified by an accountant and actual item-level POS/cost data.
- Traffic and POS completeness need instrument calibration and production device integration before commercial claims.
- A signed snapshot confirms **integrity of captured values**, not the independent truth of those values.
- Rollout review deliberately refuses to auto-deploy or trigger purchases, discounts or customer messaging.
- Store data remain local/private until public-hosting work is separately approved. No live bank settlement, ERP/1C, or hardware connectors were activated.
