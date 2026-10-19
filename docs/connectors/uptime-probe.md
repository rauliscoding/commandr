# Uptime probe

Commandr requests an address of yours every minute or every five minutes, from
Commandr's network, and tells you when it stops answering.

## Set it up

1. **Integrations → Uptime probe → Connect.**
2. Enter the address to check, for example `https://api.example.com/healthz/`.
   Use a cheap endpoint that touches what matters (the database, say), not your
   home page. `http://` works, but then we cannot check your TLS certificate.
3. Choose how often. We probe once straight away and show the result.

## What you get

- A check, *"example.com is up"*: ok for any answer below HTTP 400; failing for
  4xx/5xx, a timeout (15 s), a refused connection or a TLS error. Up to three
  redirects are followed, each one re-checked.
- A *TLS certificate* check: warning when it expires within 14 days, failing
  within 3.
- Metrics `uptime.up`, `uptime.response_ms` and `uptime.tls_expires_at`.

An email goes to the organization's owners and admins when the check starts
failing, a reminder every hour while it keeps failing, and one when it passes
again.

## What we read and store

Only the HTTP status, how long the answer took and the certificate's expiry.
The response body is read (up to 1 MB) and discarded. Addresses that resolve
to private, loopback or cloud-metadata IPs are refused.
