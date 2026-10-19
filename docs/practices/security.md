# Security

Commandr holds the keys to its customers' social accounts, ad accounts, email
lists and production telemetry. A breach would not just leak data; it would let
someone **post as our customers**. Security is a product feature here.

**Target:** OWASP ASVS 5.0 **Level 2** for the whole application, with the Level 3
items for credential storage and tenant isolation. Review every change touching
auth, tenancy, secrets, outbound HTTP, uploads or permissions against this file.

---

## Threat model (summary)

| Asset | Threat | Primary controls |
|---|---|---|
| Customers' OAuth tokens / API keys | Database or backup theft; leakage through logs or errors | Vault encryption, key held outside the DB, redaction, no secrets in task args |
| Tenant data | One customer reads or alters another's | Scoped managers + Postgres RLS, cross-tenant tests on every endpoint |
| Commandr's own network | SSRF via status-endpoint URLs, webhooks, media URLs | `safe_http` with IP pinning and deny-lists |
| Customers' audiences | Account takeover → mass posting/emailing | MFA, session security, approval-required publishing, audit log, anomaly limits |
| Ingestion API | Key leakage, flooding, poisoning | Write-only hashed keys, per-key rate limits, schema validation, size caps |
| AI features | Prompt injection via scraped comments or post text | Content treated as data; AI has no publish capability; human approval |
| Supply chain | Malicious or vulnerable dependency | Lockfiles with hashes, automated audits, minimal dependencies |
| Infrastructure | Exposed admin panels, unpatched host | Firewall, private admin access, patching, least-privilege containers |

---

## Authentication

- **django-allauth (headless mode)** for email + password, Google sign-in, and
  MFA (TOTP + WebAuthn/passkeys + recovery codes). MFA is **required** for
  organization owners and admins, offered to everyone.
- **Session cookies, not tokens in browser storage.** The SPA is served from the
  same origin as the API. Cookies: `Secure`, `HttpOnly`, `SameSite=Lax`,
  `__Host-` prefix. CSRF protection on every unsafe method. See
  [ADR 0003](../architecture/decisions/0003-session-auth-for-spa.md).
- Passwords: Argon2id, minimum 12 characters, checked against a breached-password
  list (k-anonymity range query or a local list), no composition rules.
- Session rotation on login and privilege change; idle timeout 7 days,
  absolute 30 days; "sign out everywhere" in account settings.
- Login, MFA and password-reset endpoints are rate-limited per account **and** per
  IP, with generic responses that do not reveal whether an account exists.
- Re-authentication (password or MFA) required for: connecting/disconnecting an
  integration, creating API/ingest keys, changing roles, deleting a project,
  exporting data.

## Authorization

- Roles per organization: **owner**, **admin**, **member**, **viewer**. Optional
  per-project restriction for members/viewers.
- Default deny: every DRF view declares `permission_classes`; a view without them
  fails a test that walks the URLconf.
- Object-level checks on every detail route (`has_object_permission`), not only
  list filtering.
- The UI hides what a role cannot do, but **the API is the boundary**. Every role
  rule has an API test.
- Platform staff access to customer data is by explicit, time-boxed, audited
  impersonation only, read-only by default.

## Tenant isolation

Two independent layers; either alone must be enough to stop a leak.

1. **Application:** every tenant-owned model inherits `TenantOwned` (non-null
   `organization` FK, `TenantScopedManager` as default manager). The unscoped
   manager is named `all_tenants` so its use is greppable and reviewed.
2. **Database:** Postgres row-level security on every tenant table:

   ```sql
   ALTER TABLE x ENABLE ROW LEVEL SECURITY;
   ALTER TABLE x FORCE ROW LEVEL SECURITY;
   CREATE POLICY tenant_isolation ON x
     USING (organization_id = current_setting('app.current_org_id')::uuid);
   ```

   Middleware sets `app.current_org_id` per request (`SET LOCAL` inside the
   request transaction); Celery tasks set it from their explicit
   `organization_id`. The application role is **not** the table owner and does
   not have `BYPASSRLS`. Migrations run as a separate owner role.

- IDs exposed in URLs are UUIDs (v7 for index locality), never sequential.
- Every new endpoint ships with a test proving org B gets 404 for org A's object.
- Caches are keyed with the organization id. File storage paths are prefixed with
  it and served through signed, short-lived URLs.

## Secrets and credentials

### Platform secrets (ours)

- Environment variables injected at deploy time; `.env` never committed;
  `.env.example` documents every variable with a fake value.
- Separate secrets per environment. Rotate on staff change and at least yearly.
- `gitleaks` in pre-commit and CI (CI scans the full history). Deliberately
  public values (the development vault keys, fake test tokens) are allowlisted
  by exact string in `.gitleaks.toml`, never by path.

### Customer credentials (the vault)

- `integrations.vault` encrypts with **MultiFernet**; keys come from
  `VAULT_KEYS` (comma-separated, newest first) so rotation is: add key → re-encrypt
  job → remove old key. The key never lives in the database or its backups.
- Ciphertext columns are `bytea` named `*_encrypted`; serializers have no field
  for them. A test asserts no serializer exposes a vault field.
- Decrypt only inside the connector call; never pass plaintext through Celery
  (pass the connection id).
- Logging: a redaction filter masks known secret field names and token-shaped
  strings (`Bearer …`, `sk_…`, `re_…`, JWT patterns) in every record.
- Request minimal OAuth scopes; verify granted scopes; revoke tokens at the
  provider when a connection is deleted.

### Ingest keys

- Format `cmdr_ingest_<env>_<random 32 bytes base62>`, prefix lets secret scanners
  recognise them. Stored as SHA-256 hash + last 4 characters; shown once.
- Write-only: an ingest key can submit data for one project and do nothing else.
- Revocable instantly; last-used timestamp and IP shown in the UI.

### Request signing (status-endpoint pulls)

Commandr signs every poll so customers can reject anyone else:

```
X-Commandr-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(secret, "<t>.<method>.<path>")>
```

Customers verify with a constant-time comparison and reject `|now - t| > 300s`.
The SDK does this for them. Secrets are per project, rotatable with an overlap
window (two valid secrets).

## Outbound HTTP and SSRF

Commandr fetches URLs that customers type. **All** such requests go through
`commandr.core.safe_http`:

- Schemes `https` only (`http` allowed for uptime probes only, flagged in the UI).
- Resolve DNS once; refuse if **any** resolved address is private, loopback,
  link-local, CGNAT, multicast, reserved, or a cloud metadata address
  (`169.254.169.254`, `fd00:ec2::254`); connect to the pinned IP with SNI set.
- No redirects by default; when allowed, each hop is re-validated, max 3.
- Connect timeout 5s, total 15s, response body cap 1 MB (status) / 25 MB (media).
- Polling runs from a dedicated worker container on a network with **no route**
  to Postgres, Redis or the admin interfaces — defence in depth if validation is
  ever bypassed.

## Inbound webhooks

Verify before parsing: Stripe (`Stripe-Signature`), Meta
(`X-Hub-Signature-256`), Resend (Svix headers), Google (JWT). Reject on missing or
stale signatures, process idempotently by event id, respond fast and do the work
in a task.

## Input validation and output encoding

- DRF serializers / Pydantic models validate every input shape, with explicit max
  lengths, list sizes and numeric ranges. Ingest payloads validated against the
  JSON Schema in the OpenAPI file; reject unknown top-level fields.
- ORM only; raw SQL only with parameters and a review comment.
- React escapes by default; `dangerouslySetInnerHTML` is banned except for
  sanitised (DOMPurify) rich text in post/email editors.
- Email templates: escape every interpolated value; customer-authored HTML is
  sanitised against an allow-list.

## File uploads (post media, receipts, logos)

- Allow-list of types verified by content sniffing, not extension or client MIME.
- Size limits per type; images re-encoded server-side (strips EXIF/GPS and
  polyglots); SVG not accepted from users.
- Stored in S3-compatible object storage (Hetzner Object Storage), private bucket,
  per-org prefix, served via short-lived signed URLs with
  `Content-Disposition` and a safe `Content-Type`.

## Rate limiting and abuse

- Every limit keyed per tenant identity: ingest key → user → organization → IP
  (unauthenticated only). Never a global request-count bucket.
- Plan-based quotas on ingestion volume, connected accounts, scheduled posts and
  emails, enforced server-side.
- Anomaly guard on publishing: an unusual burst of scheduled posts or emails for
  one organization pauses the queue and notifies the owner.

## HTTP security headers (Caddy + Django)

`Strict-Transport-Security: max-age=63072000; includeSubDomains; preload` ·
`Content-Security-Policy` with nonces, `default-src 'self'`, no `unsafe-inline`
scripts, `frame-ancestors 'none'` · `X-Content-Type-Options: nosniff` ·
`Referrer-Policy: strict-origin-when-cross-origin` · `Permissions-Policy` denying
camera, microphone, geolocation · `Cross-Origin-Opener-Policy: same-origin`.
CORS disabled for the app API (same origin); the ingestion API allows no browser
origins (server-to-server only).

## AI features

- Content from social platforms, emails and customer apps is **untrusted data**.
  It is passed to models clearly delimited as data, never concatenated into
  instructions.
- Models produce drafts only. No model has a tool that publishes, sends, deletes
  or spends. A human approves each item.
- No customer data is used to train models; providers chosen with zero-retention
  terms where available; AI features can be disabled per organization.

## Logging, audit and monitoring

- Structured JSON logs with request id, organization id, user id — never secrets,
  tokens, passwords, or message/email bodies.
- `audit` app: append-only record of security-relevant actions (sign-in, MFA
  changes, role changes, connection created/removed, key created/revoked,
  publish/send approvals, exports, impersonation). Visible to org owners.
- Commandr monitors itself with the same discipline as Pantrini: external uptime
  check from **another provider**, error alerts, and a daily digest whose absence
  is an alarm.

## Supply chain

- Python: `uv` with a lockfile; `pip-audit` in CI. Node: `npm ci` with lockfile;
  `npm audit --omit=dev` in CI. Renovate or Dependabot for updates, grouped weekly.
- Add a dependency only with a stated reason, a maintenance check and a licence
  check: it must be compatible with AGPL-3.0
  ([ADR 0007](../architecture/decisions/0007-licence-deferred.md)). MIT, BSD,
  Apache-2.0, LGPL, GPL-3.0 and AGPL-3.0 are fine; SSPL, BUSL, "Commons Clause"
  and no-licence code are not.
- GitHub Actions pinned to commit SHAs; least-privilege `permissions:` per workflow.
- Container images built in CI, scanned (Trivy), published to GHCR, tagged by
  version and commit.

## Infrastructure (Hetzner)

- Hetzner Cloud Firewall: only 80/443 public; SSH restricted to known IPs or via
  a Tailscale/WireGuard tunnel; key-only SSH, no root login.
- **Portainer, Flower and any admin UI are never public** — tunnel or Cloudflare
  Access only. Postgres and Redis bind to the internal Docker network only.
- Containers run as non-root, read-only root filesystem where possible,
  `no-new-privileges`, dropped capabilities. Only Portainer mounts the Docker socket.
- Unattended security upgrades on the host; monthly reboot window.
- **Backups:** nightly encrypted Postgres dumps (`pg_dump` + `age`) to a Hetzner
  Storage Box in a different location, 30 daily / 12 monthly; WAL archiving when
  revenue justifies PITR. **A restore is tested monthly** — an untested backup is
  a hope. Volume marker check as in Pantrini, so an unmounted data volume can never
  look like a fresh empty database.

## Incident response

1. Contain (revoke keys, pause publishing queues, block the actor).
2. Assess scope from the audit log.
3. Notify affected customers without undue delay; notify the Portuguese
   supervisory authority (**CNPD**) within **72 hours** of becoming aware of a
   personal-data breach where required (GDPR Art. 33). See [privacy.md](privacy.md).
4. Post-incident review written as an incident note within a week.

## Vulnerability disclosure

`/.well-known/security.txt` with a contact address and policy. Acknowledge
reports within 3 working days.

## Review checklist (copy into PR descriptions)

- [ ] New tenant data is scoped (manager + RLS) and has a cross-tenant test
- [ ] No secret in serializer, log, exception, task argument or fixture
- [ ] Outbound requests use `core.http` / `safe_http` with timeouts
- [ ] New endpoint: explicit permissions, object-level check, rate limit, input limits
- [ ] Uploads validated by content, size-capped, re-encoded
- [ ] Security-relevant action written to the audit log
- [ ] New dependency justified and licence-checked
