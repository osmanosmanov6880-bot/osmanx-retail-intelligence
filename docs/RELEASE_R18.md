# OSMANX Retail Intelligence R1.8 — Decision Bridge

**Five working workflows connecting R1.7 anonymous feedback to R1.5 controlled pilots.** Local/private software release; no public deployment, hardware installation, buyer identity inference, automatic POS operations or verified profit claims.

## 1. Signal discovery

`GET /api/admin/r18/signals?slug=central&days=14` reads real anonymized `voice_responses_r17`, groups choices **by placement and immutable published version**, filters to at least three matching responses, and limits the sampled records. It does not mix questionnaire revisions. The response includes response counts, denominators, provenance and sampling warnings; answers are not counted as guaranteed lost purchases.

## 2. Evidence-backed hypothesis case

`GET/POST /api/admin/r18/hypotheses`, `GET/PATCH /api/admin/r18/hypotheses/{id}[/status]`. A manager selects one published choice and a time window and commits an **aggregate** source snapshot (SHA-256). The result is idempotent by organization and request key, with an immutable event history. Valid transitions enforce `candidate → investigating → resolved/dismissed`, or permit pilot linking during investigation. A compromised evidence snapshot blocks linking and resolution.

## 3. Native Pilot Studio handoff

`POST /api/admin/r18/hypotheses/{id}/pilot` creates a **draft** in the actual `pilots_r15` table in the **same SQLite transaction** as linking it to its source hypothesis. The request is validated using the existing R1.5 `CreatePilot` model: equal 7–30-day baseline/intervention windows, allowed gap, KPI, source and budget. Repeated request returns the same pilot; conflicting payload returns 409. No checkouts, messages, coupons, billing or deployment are triggered. `Pilot Studio` owns the separate start/completion workflow. Closed pilot proof is checked by hashing its stored snapshot; a missing or tampered frozen result blocks resolution.

## 4. Accountable operational follow-ups

`POST /api/admin/r18/hypotheses/{id}/tasks`, `PATCH /api/admin/r18/tasks/{id}`, `GET /api/admin/r18/tasks/{id}/history`. Each task records title, responsible person, due date, status changes and required evidence note. Same request with different content returns 409. Allowed transitions are `open → working → done` or cancellation. Each transition has an audit record; read-only users cannot modify. Completing a task is documented execution, not verified financial improvement.

## 5. Executive evidence overview

`GET /api/admin/r18/board` and `GET /api/admin/r18/board.csv`: organization/store-scoped statuses, open tasks, immutable evidence hashes, linked pilot status, integrity warnings and injection-safe CSV. The full five-step Russian-language interface is `/static/bridge.html` and appears as a shortcut in the main sidebar. It is designed for 1440px desktop and 390px phones with keyboard-friendly controls.

## Security and limits

- Every admin endpoint requires an authenticated session in normal mode; all writes require `owner` or `manager`. All item reads and mutations verify organization and assigned store access.
- No PII, user-level video profiles or facial recognition. Aggregates are tagged to published questionnaire versions. `support` means responses, not unique people.
- No causal or revenue outcome is inferred from survey answers. SHA-256 provides evidence **integrity**, not independent truth of inputs.
- Uploads are not sent to 1C, physical POS, or any external endpoint. Production privacy, physical sensor reliability, real accounting and HTTPS validation remain deferred.

## Acceptance

```bash
python -m pytest tests/test_r18.py -q
python -m compileall -q backend scripts
node --check frontend/bridge.js
node --check frontend/r18_nav.js
python scripts/r18_browser_smoke.py
```

The browser script uses local FastAPI TestClient + SQLite bridged to Chromium (no public server) and exercises actual API round-trips including creating a hypothesis, pilot, task, and CSV download. GitHub Actions also runs the entire existing R0.2–R1.7 suite.
