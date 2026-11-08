# OSMANX Retail Intelligence R1.7 — Voice Studio

**Five real product modules**, integrated with the existing FastAPI, SQLite, organizational roles and Russian premium dark interface. **No public deployment, no camera, no physical POS or 1C connected.**

## 1. Versioned, conditional questionnaire builder

`GET/POST /api/admin/r17/forms`, `PATCH /forms/{id}`, `POST /forms/{id}/publish`, `POST /forms/{id}/archive`, `GET /forms/{id}/versions`. A form has up to eight questions with ordered conditions referring only to earlier choice questions; each choice has two to six options. Published versions are immutable and idempotent. Editing a published form changes only its draft until the next explicit publish. Old answers remain attached to their original version. Conditional hidden answers are rejected server-side. Free-text answers, contacts, biometric identifiers and buyer profiles are not supported.

## 2. Paired QR and kiosk placements

`GET/POST /api/admin/r17/placements`, `POST /placements/{id}/rotate`, `POST /placements/{id}/disable`, `POST /placements/{id}/qr.svg`. The manager issues a high-entropy secret **shown once**. Only a SHA-256 hash is saved; rotating invalidates the old link. The QR code is a downloadable SVG generated from the valid same-origin link by the server. Secrets are passed to the anonymous API in a request header; the browser receives the initial link in its URL fragment rather than the request path or query. This does not prevent users from deliberately sharing QR links or copying a device key. Physical kiosk enrollment, device attestation and anti-fraud calibration remain future work.

## 3. Anonymous, version-bound survey flow

`GET /api/voice/r17/{public_id}/form`, `POST /open`, `POST /submit` require a live placement key. Opening returns a random idempotency record, not a buyer profile; submitting requires an existing opening less than two hours old and the same published version. One response per opening; changed repeats return 409. Strict server validation accepts only active questions and known answers, with a 3,000/day completion guard per placement. No automatic discounts or physical gift issuance.

`/static/voice_kiosk.html#PUBLIC_ID.SECRET` is the actual fullscreen, touch-friendly buyer interface. The secret should be safeguarded like a QR bearer token.

## 4. Response insights and honest measurement

`GET /api/admin/r17/insights?slug=central&days=14`, `/insights.csv` aggregate by actual placement and published version. Results include answer counts, distribution, open events and completed responses with sample-size and selection warnings. **Opens are not unique people; reported purchase is not a verified POS transaction.** Percentages are observational, not causal proof. CSV is authenticated and spreadsheet-formula-escaped. Input queries are bounded and grouped only across the user's authorized store.

## 5. Evidence-backed management tasks

`GET/POST /api/admin/r17/actions`, `PATCH /actions/{id}`, `GET /actions/{id}/history`. An action needs at least three matching observed choices in the same placement and version; it stores immutable counts, source details and SHA-256 plus the permitted workflow `new → investigating → implemented` or `dismissed`. Notes and history are audited; implementation of a task is not proof of financial lift.

## Retention, backups and privacy

`python -m scripts.purge_voice_r17` previews per-store purge of raw response and opening records using existing `survey_retention_days` (clamped to 7–365 days). Add `--apply` to perform deletion inside a transaction. Retain or delete decision evidence records according to your separate business/legal retention policy; the raw observations may expire earlier than the snapshot. The cleanup **is not automatically scheduled**.

No personally identifying fields are requested, but a store still must provide appropriate notice, evaluate local privacy obligations and avoid distributing bearer keys in untrusted contexts. Kiosk and QR surveys are voluntary; there is no credible guarantee against coordinated malicious submissions.

## Local verification

```bash
pip install -r requirements.txt pytest httpx playwright
python -m pytest tests/test_r17.py -q
python -m compileall -q backend scripts
node --check frontend/voice.js
node --check frontend/voice_kiosk.js
node --check frontend/r17_nav.js
python scripts/r17_browser_smoke.py
```

The Chromium acceptance suite uses live FastAPI TestClient/SQLite, tests a real questionnaire creation, publication, QR download, three buyer flows, analytics, authenticated CSV, evidenced action and both 1440 / 390 px displays. It does not simulate a public HTTPS deployment or a physical tablet.
