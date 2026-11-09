# OSMANX RETAIL INTELLIGENCE R1.9 — FIELD OPERATIONS

R1.9 makes **Voice Studio** more useful on a physical store tablet while preserving the approved dark-blue, restrained-red design. It does not deploy a public site or integrate actual camera/POS hardware.

## Five shipped modules

1. **Offline answer queue:** the exit kiosk caches the most recent form and at most 25 anonymous response payloads on that specific device for up to 60 minutes. When connectivity returns it retries open + submit using the **same request ID**, relying on R1.7 server-side idempotency. It never persists the secret in local storage. A queued answer is explicitly labeled **not yet delivered**. Stale responses or responses for a different form version are not silently counted. If the browser blocks local storage, the UI warns instead of promising a save. The kiosk still requires its R1.7 secret, and answer validation remains server-side.
2. **Terminal heartbeat and fleet health:** authenticated `/api/voice/r19/{public_id}/heartbeat` with the **existing, rotating placement key**; client reports build and pending anonymous count. Server tracks online (<150s), delayed (150–600s), offline (>600s), disabled and unpaired separately. Duplicate request IDs return an idempotent receipt, modified replays are HTTP 409. Heartbeats demonstrate contact from a key holder, not the presence of a calibrated physical kiosk. Old event IDs are pruned to 500 per placement.
3. **Hours and weekdays:** admins set a store-local schedule, versioned with optimistic concurrency. R1.7 **form and open** routes enforce closed hours (HTTP 423). An already opened questionnaire can finish within the original R1.7 two-hour session expiry, even after hours, so offline recovery is not arbitrarily lost. Legacy placements without a schedule retain their prior behavior. Schedule management is limited to the owner/manager for the permitted store.
4. **Quality monitoring:** per-placement opens, completed responses, a completion-per-open ratio, unusually fast answers and per-minute bursts, with sample size and methodology warnings. Rates are **not unique-person purchase conversions**, and anomaly flags are **not evidence of fraud**. Authorized CSV uses spreadsheet formula escaping.
5. **Incident operations:** detection of overdue tablet heartbeat, queued responses, bursts, and abnormally low completion; stable signal identities and audited `open → acknowledged → resolved` transitions. Reappearing signals reopen historical incidents. Operations are scoped to the manager's company/store.

## New UI

- `/static/field.html`: terminal fleet, schedule editor, connectivity/queue explanations, survey QA and incident handling. Five working tabs, desktop and 390px layout.
- `/static/voice_kiosk.html`: enhanced original anonymous touchscreen questionnaire with offline queue and clear receipt status; same existing QR link and R1.7 keys.

## API

- `POST /api/voice/r19/{public_id}/heartbeat`
- `GET /api/admin/r19/fleet`, `/fleet.csv`
- `GET/PUT /api/admin/r19/placements/{placement_id}/schedule`
- `GET /api/admin/r19/quality`, `/quality.csv`
- `GET /api/admin/r19/incidents`, `POST /incidents/sync`
- `PATCH /api/admin/r19/incidents/{incident_id}`, `GET /incidents/{incident_id}/history`

## Local verification

```bash
python -m pytest tests/test_r19.py -q
python -m compileall -q backend scripts
node --check frontend/field.js
node --check frontend/voice_kiosk.js
node --check frontend/r19_nav.js
python scripts/r19_browser_smoke.py
```

The Chromium smoke uses isolated FastAPI+SQLite and browser content injection to work in environments that block network navigation. It verifies real API writes, offline submit failure/replay, owner scheduling, CSV, incidents, mobile width and captures screenshots at `qa/r19-*.png`.

GitHub Actions also runs prior regressions, including the legacy R1.7 Voice Studio browser flow; **do not merge if any regression fails**.

## Limits / required before use with real visitors

- Offline answers reside only in browser local storage and can be lost if the tablet is reset, cleared, runs out of capacity, or remains offline beyond expiry. This is best-effort recovery, not guaranteed delivery or a synchronized hardware queue.
- QR keys can be shared. Operators must physically secure the tablet, rotate disclosed keys and avoid using admin sessions in customer mode.
- The service never learns the identity or intent of an individual. Voluntary answer distributions may be biased and cannot prove lost revenue by themselves.
- Real deployment needs store-specific privacy notice, data lifecycle review, HTTPS, backup restore verification, device calibration and testing, infrastructure monitoring, and a security review. **Public hosting remains deferred.**
