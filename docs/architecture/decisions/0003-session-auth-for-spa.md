# 0003. Same-origin session cookies for the SPA, not JWTs in browser storage

- **Status:** Accepted
- **Date:** 2026-10-16

## Context
The SPA needs authentication. Pantrini's mobile API uses SimpleJWT, which suits a
native app. In a browser, tokens readable by JavaScript are exposed to any XSS,
and refresh-token handling is easy to get wrong.

## Decision
Serve the SPA and the app API from the same origin through Caddy. Authenticate
with Django sessions via **django-allauth headless** (`__Host-` cookie, `Secure`,
`HttpOnly`, `SameSite=Lax`) plus CSRF tokens. MFA (TOTP, passkeys) through
allauth. API keys exist only for the ingestion API and a future public API, never
for the browser.

## Consequences
- XSS cannot steal a session token; CSRF is handled by Django's proven middleware.
- A future mobile client would use allauth headless's app (token) flow.
- The SPA cannot be served from a different domain without revisiting this.

## Alternatives considered
- **JWT in localStorage** — exposed to XSS.
- **JWT in an HttpOnly cookie** — reinvents sessions with worse revocation.
