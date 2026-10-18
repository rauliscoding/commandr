# Self-hosting Commandr

Run your own Commandr on one server. This is the same stack the hosted service
runs on. If you would rather not operate it yourself, the hosted version does
this for you, and paying for it funds the project.

> **Status:** Phase 0. Accounts, organizations, projects and the integration
> catalogue work; integrations themselves arrive in Phase 1. Self-hosting is
> supported for evaluation now and for production from the first tagged release.

## What you need

- A Linux server with Docker Engine and Compose v2. 2 vCPU / 4 GB RAM is plenty to
  start (a Hetzner CX22 or similar).
- Two DNS names pointing at the server, for example `app.example.com` and
  `ingest.example.com`.
- Ports 80 and 443 open to the internet. Nothing else needs to be.
- Optional: a [Resend](https://resend.com) API key for Commandr's own emails
  (sign-up verification, password reset, alerts).

## Install

```bash
git clone https://github.com/rauliscoding/commandr.git
cd commandr
cp .env.example .env
```

Fill in `.env`. Every required value is marked, and the file says how to
generate each secret. Two need care:

- **`VAULT_KEYS`** encrypts every stored OAuth token and API key. Keep a copy
  **outside** the server and outside your database backups (a password manager).
  If you lose it, every connected integration has to be reconnected; if it leaks
  together with a database dump, those credentials are exposed.
- **Three database passwords**: the superuser (setup only), the owner (runs
  migrations) and the app (runs everything else). Use three different values.

Start it:

```bash
docker compose -f deploy/compose/docker-compose.prod.yml --env-file .env up -d --build
```

Caddy obtains TLS certificates on first request. Open `https://app.example.com`,
create your account, and you are in.

Until tagged images are published to GHCR, `--build` builds them locally from
this checkout (a few minutes the first time).

## What runs

| Service | Role | Network |
|---|---|---|
| `caddy` | TLS, security headers, the web app, proxy to `web` and `ingest` | edge (ports 80/443) |
| `web` | the API | edge + data |
| `ingest` | the ingestion API (`INGEST_DOMAIN`), separate so telemetry floods cannot slow the app | edge + data |
| `worker`, `beat` | background jobs and schedules | data + egress |
| `migrate` | runs once per start, as the database owner, then exits | data |
| `db`, `redis` | Postgres 17, Redis 7 | data only — no internet route, no published ports |

## Upgrading

```bash
git pull   # or bump COMMANDR_*_IMAGE to the new tag
docker compose -f deploy/compose/docker-compose.prod.yml --env-file .env up -d --build
```

`migrate` runs before the app restarts. Migrations are written to be backwards
compatible with the previous release, so rolling back means redeploying the
previous version.

## Backups

Back up **both**:

1. **The database.** Nightly, off the server:

   ```bash
   docker compose -f deploy/compose/docker-compose.prod.yml exec -T db \
     pg_dump -U postgres -Fc commandr > commandr-$(date +%F).dump
   ```

   Encrypt it (`age`, `gpg`) and copy it to another location (a Hetzner Storage
   Box, S3-compatible storage).
2. **`.env`**, especially `VAULT_KEYS`, kept apart from the dumps.

**Test a restore** before you need one. A backup you have never restored is a
hope, not a backup.

## Admin access

The Django admin (`/admin/`) answers 404 on the public domain by design. To use
it, create a staff account once, then open a temporary private tunnel:

```bash
# On the server: create the staff account (once)
docker compose -f deploy/compose/docker-compose.prod.yml --env-file .env \
  exec web python manage.py createsuperuser

# On the server: a temporary admin process, bound to the server's loopback only
docker compose -f deploy/compose/docker-compose.prod.yml --env-file .env \
  run --rm -p 127.0.0.1:8001:8000 web

# On your machine: forward the port, then open http://localhost:8001/admin/
ssh -L 8001:127.0.0.1:8001 you@server
```

Stop the temporary process (Ctrl+C) when you are done. The admin shows users and
organizations only; tenant data is deliberately not exposed there.

## Monitoring your instance

Point an **external** uptime monitor (a different provider from your server's)
at `https://app.example.com/healthz/`. Commandr's own watchdog and daily digest
arrive in Phase 1.

## Hardening checklist

- [ ] Firewall: only 22 (from your IPs), 80 and 443.
- [ ] SSH: keys only, no root login.
- [ ] Unattended security upgrades on the host.
- [ ] `.env` readable by root only (`chmod 600 .env`).
- [ ] Backups running, encrypted, off-server, and a restore tested.
- [ ] `VAULT_KEYS` stored in a password manager.

Full guidance: [docs/practices/security.md](practices/security.md).
