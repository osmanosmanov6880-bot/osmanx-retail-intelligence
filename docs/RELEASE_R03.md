# OSMANX RETAIL INTELLIGENCE — R0.3 · Engineering release

## Five full modules

1. **Organization isolation and RBAC.** Organizations, users and assigned store access. Four roles: `owner`, `manager`, `analyst`, `viewer`. All admin routes enforce a principal, all lookups check the organization, and ID-based demand/experiment routes also verify organization and branch. Passwords use salted PBKDF2-HMAC-SHA256. Bearer sessions are validated against active accounts and a session revocation counter.
2. **Signed device intake.** Separate HMAC-derived key per device, bound to exactly one branch and event type. Signing input is UTF-8 bytes of `<unix timestamp>\n<device_id>\n<raw JSON>`. Freshness ±300s; payload-bound deduplication by `(device,kind,external_id)`; conflicting retries fail 409. Creation, rotation and revocation supported. Old global `X-OSMANX-Ingest-Key` endpoints return 410 in real mode.
3. **Two-step POS and inventory imports.** Validate normalized records, reject repeated IDs and invalid numbers, stage source data with SHA-256, show additions/updates/unchanged/conflicts and apply with `BEGIN IMMEDIATE` after revalidating. No partial batch commits. 24h expiration. Receipts with an existing ID but different amount/time are rejected. Stock changes use case-insensitive SKU matching to avoid duplicate rows with differently cased IDs.
4. **Kiosk operations and privacy controls.** Anonymous optional free-text survey, request-id + payload hash idempotency, strict one-time redemption, timezone-aware daily reward budget, configurable 7–365 day retention and operator CLI for explicit deletion of expired feedback and related reward codes. No face IDs, no camera files, no contact data fields.
5. **Quality-aware owner UI and tests.** Existing premium dark navy/red kiosk/dashboard maintained; new team and integrations UI, preview/apply actions, sensor registration and key rotation, traffic source policy (`manual`, `sensor`, `auto`, `combined`), data-quality disclosures, 27+ API/DB tests and interactive Chromium coverage including 390px screens.

## Source locations

- `backend/security.py` — principals, RBAC, sessions, devices, audit
- `backend/imports.py` — transactional staging and apply
- `backend/privacy.py` — reward budget and retention
- `backend/analytics.py` — selected traffic sources and quality warnings
- `backend/app.py` — HTTP endpoints with organization guards
- `frontend/app.js`, `frontend/styles.css` — controls and views
- `scripts/provision_tenant.py` — trusted tenant creation from CLI only
- `scripts/send_device_event.py` — signed device test sender
- `scripts/purge_surveys.py` — dry-run-by-default retention cleanup
- `tests/test_r03.py`, `scripts/r03_browser_smoke.py` — acceptance

## Threat model and limits

- **New tenants:** only a trusted server operator can create an organization using the provisioning CLI. There is no public registration form, so the system does not allow anonymous tenant creation.
- **Public kiosk:** accessible by store slug; it accepts voluntary feedback, not names/faces. A response can include user-entered personal data in free text, so stores should publish a suitable privacy notice and review the text. The provided notice tells visitors not to enter contacts. The retention purge must be scheduled on the server; it does not run automatically.
- **Rewards:** optional, store-defined manual code, NOT automatically recognized by 1C/POS and NOT a guaranteed discount. A 20-code/day initial limit is configurable by owner.
- **Hardware:** signed ingestion protocol is real; physical cameras, people counters and POS connectors are NOT connected. Only anonymous aggregate events are accepted. Device secrets must be kept in the server/gateway's secure environment and transmitted over HTTPS.
- **Backups and hardening:** SQLite database backups, distributed rate limits, authentication MFA, independent penetration testing, GDPR/legal review, reliable sensor calibration and production HTTPS monitoring are still required before a public multi-client launch.
- **Tenant separation:** all requests are logically filtered on organization and store; the system remains a single SQLite deployment, not a complete production multi-tenant infrastructure.
- **Claims:** data quality and hypotheses are separate from measured causal impact. Simple receipt-per-entry conversion is a proxy; returns, multiple visits and multiple receipts can change interpretation.

## Reproducible validation

```bash
python -m pytest tests -q
python -m compileall -q backend scripts
node --check frontend/app.js
python scripts/visual_smoke.py
python scripts/r03_browser_smoke.py
```

## Provision a distinct client

With a secure env (see README), a trusted server operator executes:

```bash
export OSMANX_NEW_OWNER_PASSWORD='example-choose-a-unique-strong-password'
python -m scripts.provision_tenant --slug demo-shop --name 'Demo Shop' --store demo-shop-main --email owner@example.com
```

The new owner then signs in with the assigned email and password. Never run this command with an actual customer's password in shell command history; use environment/secret management. Store slugs are globally unique.
