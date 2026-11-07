# OSMANX Retail Intelligence R0.4 — five implemented blocks

This release extends R0.3 without replacing its database, API endpoints or premium Russian-language layout. Synthetic demo measurements are marked as demo.

## 1. Self-service sessions and account protection

- `POST /api/auth/change-password`: verifies the previous password, hashes the new one with PBKDF2, increments the session version, issues a fresh token and revokes all other sessions.
- `POST /api/auth/logout-all`: invalidates existing sessions immediately.
- Both operations are audited and disabled in demo mode for password changes.
- The account screen has real controls; session tokens remain in sessionStorage, not in URLs.

## 2. Per-store paired survey kiosk

- Owners/managers can enable kiosk pairing and rotate its token through `POST /api/admin/kiosks/{slug}/rotate`.
- Kiosk token is a random 256-bit secret, stored hashed in SQLite and shown only once in the management UI.
- Pairing link uses the URL **fragment** (`/kiosk/central#access=...`), never the HTTP query string; kiosk stores it for its current browser session and sends it in `X-OSMANX-Kiosk`.
- The survey API rejects unauthorized submissions when pairing is enabled; idempotency, optional daily bonus cap and retention rules from R0.3 remain in effect.
- Rotating the pairing token revokes previously paired tablets. `DELETE /api/admin/kiosks/{slug}` disables the pairing requirement; doing so intentionally reopens the public survey.

## 3. Signed, idempotent POS receipt ingestion

- Owners/managers create POS sources through `POST /api/admin/pos/sources` and receive a one-time derived secret. Keys can be rotated or revoked.
- Source credentials are bound to a single store, separate from traffic sensor credentials. The source ID and secret are not embedded in public pages.
- Integrators send `POST /api/ingest/pos` with `X-OSMANX-Source`, `X-OSMANX-Timestamp`, and `X-OSMANX-Signature` (HMAC-SHA256 over the exact timestamp + newline + source ID + newline + raw UTF-8 JSON).
- A message has 1–200 receipts. Each receipt contains `external_id`, `amount_rub` (<= 2 fractional digits), and offset-aware `occurred_at` (within 31 days). Timestamps in headers may be at most 5 minutes out of sync.
- The entire batch is atomic. Repeat IDs with matching payloads are not double-counted; conflicting IDs reject the batch.
- This **does not** claim native 1C, iiko or fiscal POS integration. A vendor-specific adaptor is still required.

Example POS JSON:

```json
{
  "receipts": [
    {"external_id": "R-2026-00001", "amount_rub": "5490.50", "occurred_at": "2026-11-08T14:30:00+03:00"}
  ]
}
```

Sender: `OSMANX_POS_SOURCE_ID=... OSMANX_POS_SOURCE_SECRET=... python -m scripts.send_pos_batch --url https://shop.example/api/ingest/pos --file receipts.json`.

## 4. Quality-of-data and connection monitoring

- Owner/manager/analyst/viewer can see `/api/admin/operations/quality?slug=central&days=7` only for stores within their own organization and assignment.
- The Russian dashboard shows visitor and receipt counts by source, survey volume, unresolved demand, registered device status and last accepted sensor/POS event.
- Warnings: absent events, stale device (> 24h), potentially double-counted visitor sources, more checks than recorded visits, missing surveys. Warnings describe **data quality**, not proven lost profit or individual consumer behavior.

## 5. Operational readiness and backup protection

- `/api/ready` checks database availability; Docker HEALTHCHECK calls it.
- Docker runs as an unprivileged user, binds only to loopback in Compose, drops Linux capabilities, uses a read-only container filesystem and stores mutable data only in `/data`.
- `scripts/backup_db.py` creates consistent SQLite backup snapshots (including WAL state), runs integrity and foreign key checks, writes SHA256 manifests, and rotates old snapshots.
- Offline restore requires an explicit flag, validates file+manifest, preserves a safety copy and must run after stopping the service.
- CI runs API tests, syntax checks, and Playwright desktop/mobile end-to-end scenarios.

## Verification

- Existing R0.3 tests preserved.
- R0.4 tests cover key rotation/revocation, cross-tenant denial, signed receipt replay/conflict, all-or-nothing batches, terminal pairing, quality alerts, backup verification, and offline restore.
- Browser tests cover owner screens, mobile quality view and paired terminal survey end-to-end.

## Limitations and release gate

Not yet approved for unaudited public commercial deployment. Must still validate a real TLS hostname, backups to encrypted off-host storage, real device adapters, privacy documentation, real customer consent/information notices, and operational alerting. Do **not** deploy `OSMANX_DEMO_MODE=1` to a public address. No camera identification or automated claims of lost sales.
