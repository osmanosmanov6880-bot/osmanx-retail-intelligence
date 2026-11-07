# OSMANX Retail Intelligence — private pilot deployment

This is an implementation guide for a technical operator, not a claim that a public server is deployed.

1. Provision a Linux host with Docker Engine and Compose. Keep ports closed except for your TLS reverse proxy.
2. Clone the authorized repository, create `.env` privately using `.env.example` as reference, and set:
   - `OSMANX_DEMO_MODE=0` (mandatory for any real pilot)
   - `OSMANX_ADMIN_PASSWORD` (at least 12 characters; bootstrap only)
   - `OSMANX_SESSION_SECRET` (at least 32 random characters)
   - `OSMANX_DEVICE_MASTER_SECRET` (separate 32+ character random value)
   - `OSMANX_BOOTSTRAP_EMAIL` for the first account
3. Run `docker compose up -d --build`. The API is bound to `127.0.0.1:8000` by default.
4. Configure a trusted HTTPS reverse proxy with HTTPS-only external access, managed certificates, reasonable request-size/body-rate limits and no cache for `/api` requests. Restrict reverse proxy access to the localhost upstream only. Do not trust arbitrary user-supplied forwarding headers.
5. Check `curl -fsS http://127.0.0.1:8000/api/ready` from the server. Sign in, change the first account password and then explicitly pair each survey tablet.
6. Back up with `docker compose exec -T osmanx python -m scripts.backup_db backup --destination /data/backups --keep 7`. Export encrypted backups to separate storage and practice offline restores before using real information.
7. Real sensor integration: create devices in the UI, then implement the documented `/api/ingest/v2/traffic` or `/api/ingest/v2/zones` HMAC format. Real POS integration: create POS sources and use `/api/ingest/pos`.
8. Confirm retention/erasure policies, a lawful basis for data collection, customer notices, and employee rights before using in an actual shop.

## Restore checklist

- Stop the application and any process using the SQLite database.
- Select a verified backup and retain a separate external copy.
- Use `python -m scripts.backup_db verify --file /backup/path.sqlite3`.
- Invoke `python -m scripts.backup_db restore --file /backup/path.sqlite3 --confirm-offline` with `OSMANX_DATA_DIR` pointing at the correct data directory.
- Restart one worker, confirm `/api/ready`, test login, sample survey and dashboard, then inspect logs.
- Never restore while an API worker is processing events.

## Security notes

- Demo mode bypasses admin access intentionally; NEVER expose it publicly.
- No personally identifying camera analytics or face recognition exists in this release.
- The public kiosk must be paired for a real pilot. It will then reject answers without the per-store key.
- In-memory login and survey rate limits are per-process only. Put additional rate limiting at the TLS reverse proxy for internet-facing use.
- POS webhook signer uses exact raw JSON bytes. Never expose its signing secret in browser JavaScript.
- `/api/ready` is a readiness signal, not a substitute for monitoring and incident response.
