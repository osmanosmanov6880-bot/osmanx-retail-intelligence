# OSMANX Retail Intelligence R2.3 — Security Center

**Scope:** five working security and recovery workflows. **Not** a public deployment or physical security certification. The platform remains local/private and has no live 1C, bank, POS or camera integration unless the operator separately configures those services.

## Five implemented blocks

1. **Close the legacy startup bypass.** In non-demo mode `POST /api/admin/r15/pilots/{id}/start` now returns HTTP 409 without changing the DB. Production users must use `POST /api/admin/r21/pilots/{id}/safe-start` with the latest independently reviewed R2.0 `readiness_id`. That guarded route performs the existing R2.1 checks on org/store, review digest, independent reviewer, calibration, reconciliation, ticket blockers and time window, and atomically stores the authorization proof. Repeating a safe-start also checks the old proof SHA and pilot status before accepting the duplicate. Pilot Studio's start button follows the guarded flow after the legacy endpoint directs it there. Demo mode deliberately remains an unsafe demonstration and must **never be internet-exposed**.
2. **Tenant and permissions audit.** Owner-only `GET /api/admin/r23/authorization?slug=...` scans actual user-to-store assignments, device organizations and active-owner state, without exposing names, tokens or password hashes. Any cross-tenant access found is a blocker, never silently corrected.
3. **Immutable evidence integrity scan.** Owner-only `GET /api/admin/r23/integrity` verifies R2.0 reviewed snapshots, two-person review identities, R2.1 startup authorization SHA, and R2.2 stage proofs. It explicitly flags previously running/closed pilots that lack R2.1 authorization. Existing historical violations are not retroactively certified.
4. **Accountable security remediation.** `GET/POST /incidents`, `PATCH /incidents/{id}`, `GET /incidents/{id}/history` persist org/store-scoped issues derived from current audit findings, with idempotent keys, owner, deadline, allowed status transitions and immutable history. A different owner must confirm resolution, and the underlying finding must no longer be present; an incident cannot be marked fixed while the data still fail.
5. **Verified recovery drill and commercial release gate.** `python -m scripts.r23_recovery_drill --backup ... --record` validates an existing SHA-manifested SQLite archive, restores it into a disposable temp DB, re-checks DB integrity, schema and full logical row content, and writes a private offline-drill receipt. It **does not overwrite** the live DB. Owner-only `/recovery`, `/release-gate` and `/report.csv` require a server-configured `OSMANX_BACKUP_DIR`, a valid latest backup not older than 24 hours, and a restore drill for that same backup within 30 days. They also check integrity issues, pending incidents and demo status. `eligible_for_operator_review` is **not permission to publicly host**.

## Interface

`/static/security.html` — five Russian-language tabs: readiness, access, evidence integrity, remediation and recovery. It uses the existing authenticated session and premium dark-blue style, responsive to 390 px. `/static/r23_nav.js` adds a shortcut in the main sidebar.

## Installation into existing R2.2 checkout

```bash
python scripts/install_r23.py --root /absolute/path/to/checkout
```

The installer patches the approved R2.2 anchor points and refuses an unknown layout or conflicting files. Migration is repeatable and only runs at app startup. It does not update or publish the live database, generate secrets or start a public server.

## Backup and drill

```bash
export OSMANX_BACKUP_DIR=/data/backups
python -m scripts.backup_db backup --destination /data/backups --keep 7
python -m scripts.r23_recovery_drill --backup /data/backups/retail-XXXX.sqlite3 --record
```

Secure the directory permissions to owner-only (`0700`) and export an **encrypted, separate/off-site copy**. The drill deliberately uses disposable local storage. It cannot validate cloud recovery point objective, encrypted transport, key management, restore of external services or the accuracy of real-world records. Never put backups or drill manifests in GitHub.

## Verification

```bash
python -m pytest tests/test_r23_core.py tests/test_r23_api.py -q
node --check frontend/r23_security.js
node --check frontend/r23_nav.js
python -m compileall -q backend scripts
python scripts/r23_browser_smoke.py
```

Existing R1.5/R1.6 tests have been adjusted to seed a running-pilot state *only within their isolated test databases* when they are testing actions/financial reports rather than startup. R2.3 tests explicitly verify that the public legacy startup route fails in real mode; R2.1 and R2.3 verify the protected route separately. The compatibility demo route is unchanged for local browser acceptance.

### Remaining production prerequisites

- Independent penetration test and OWASP review of the entire API and static frontends.
- TLS reverse proxy configuration, safe request-size limits, centralized observability and incident response procedures.
- Production account lifecycle policies (offboarding, MFA or suitable alternative), backup encryption/key custody, off-site restores and periodic drills.
- Hardware sensor validation, real POS/bank reconciliation, data-retention notice and privacy/legal compliance.

**SHA-256 is tamper detection for stored values, not a trusted third-party signature.**
