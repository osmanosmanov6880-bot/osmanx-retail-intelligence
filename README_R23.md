# R2.3 — Security Center / OSMANX Retail Intelligence

Five operational controls: non-demo legacy pilot-start protection, tenant permissions checks, immutable evidence verification, independently resolved security incidents and verified SQLite recovery drills. Existing R2.1 `safe-start` remains the sole non-demo start route for real pilots.

- Admin UI after local startup: `/static/security.html` (owner role only).
- Release details: [`docs/RELEASE_R23.md`](docs/RELEASE_R23.md).
- Tests: `python -m pytest tests/test_r23_core.py tests/test_r23_recovery.py tests/test_r23_api.py -q` and `python scripts/r23_browser_smoke.py`.
- No external POS/bank operations, no public deployment.
