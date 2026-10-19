# Push API

Send metrics, events and errors from anywhere your code runs, with a
write-only ingest key. The format is the
[ingestion contract § Push API](../architecture/ingestion-contract.md#2-push-api).

## Set it up

1. **Integrations → Push API → Connect.**
2. Name the key after where it will live ("Production API") and pick live or
   test; the environment shows in the key's prefix.
3. Copy the key. **It is shown only once**: Commandr stores only its SHA-256
   and last four characters. Keep it server-side, for example as
   `COMMANDR_INGEST_KEY`.
4. Send a test batch:

   ```bash
   curl -sS https://ingest.example.com/v1/ingest \
     -H "Authorization: Bearer $COMMANDR_INGEST_KEY" \
     -H "Content-Type: application/json" \
     -d '{"schema": "commandr.ingest/v1", "metrics": [{"name": "queue.depth", "type": "gauge", "value": 3}]}'
   ```

   The answer is `202` with `accepted` and any `rejected` items, each with a
   reason. The wizard switches to "first data" when the batch is written.

## Limits

1 MB and 1,000 items per request, timestamps within the last 24 hours, 600
requests a minute per key. No personal data in attributes or event
properties (no emails, names, IPs or user ids): such items are rejected.

## Revoking

Remove the source on the Health page. The key is refused from the next
request on; the Health page shows when each key was last used, and from where.
