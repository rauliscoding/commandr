# Heartbeat

Your scheduled job calls a URL when it finishes. If the call does not arrive
on time, Commandr tells you: silence is the signal.

## Set it up

1. **Integrations → Heartbeat → Connect.**
2. Name the job, say how often it runs, and how late it may be before you hear
   about it ("every day, alert when an hour late").
3. Copy the heartbeat URL. **It is shown only once**: Commandr keeps only a
   fingerprint of it. If you lose it, remove the heartbeat and add it again.
4. Add one line at the end of the job:

   ```bash
   curl -fsS -m 10 --retry 3 https://ingest.example.com/v1/heartbeat/<token>
   ```

Optional:

- at the start of the job, `…/<token>/start`, to see how long runs take;
- on failure, `curl --data-raw "what went wrong" …/<token>/fail`. The message
  appears in the alert (up to 1,000 characters; anything that looks like a
  token is masked).

## States

| State | When |
|---|---|
| Waiting (unknown) | Created, no ping yet. Never shown as ok. |
| OK | The last run succeeded and the next one is not yet late. |
| Failing | The last run reported a failure, or no success arrived within the period plus the grace. |

The URL is the credential: anyone with it can report this job. Treat it like a
password. It accepts at most 60 calls a minute.
