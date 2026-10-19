# Status endpoint

Your app serves a small JSON document describing its health; Commandr fetches
it every minute or five, with a signed request. The document format is the
[ingestion contract § Status endpoint](../architecture/ingestion-contract.md#1-status-endpoint-pull).

## Set it up

1. **Integrations → Status endpoint → Connect.**
2. Enter the document's address: `https://` only, usually
   `https://api.example.com/.well-known/commandr/status`.
3. The first time in a project, Commandr shows the project's **signing
   secret** once. Put it in your app's environment as `COMMANDR_SIGNING_SECRET`.
   Every status endpoint (and the SDK) in the project uses the same one.
4. In your app, reject any request whose signature does not check out. The
   wizard shows a Python example; in short:

   ```
   X-Commandr-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(secret, "<t>.GET.<path>")>
   ```

   `<path>` is the request path without the query string. Refuse when
   `|now − t| > 300`, compare in constant time, and answer `401` otherwise.
5. Commandr sends a signed test request straight away. Until it gets a valid
   document, the wizard shows what went wrong ("your app refused our signature",
   "not valid JSON", …) and a **Check again** button.

## What you get

- Each check in your document, with your status (`ok`, `warn`, `fail`,
  `unknown`). A check that disappears from the document counts as recovered.
- *"api.example.com answers"* (`commandr.reachability`): fails when we cannot
  reach the address, get anything other than 200/304, or the document does not
  match the contract.
- Gauges as metrics, and KPIs on the Health page. A KPI sent as `null` shows
  as "—", never 0.

Checks that stop being reported turn unknown after three missed polls.
