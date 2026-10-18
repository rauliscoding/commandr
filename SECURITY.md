# Security policy

Commandr stores people's access to their social accounts, ad accounts, email
lists and production telemetry, so we take reports seriously and answer quickly.

## Reporting a vulnerability

**Do not open a public issue.** Report privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository ("Security" tab, "Report a vulnerability").

Please include what is affected, how to reproduce it, and the impact you see.
Do not access data that is not yours, and stop as soon as you have shown the issue.

## What to expect

- Acknowledgement within **3 working days**.
- An assessment and a plan within **10 working days**.
- Credit in the release notes if you would like it.

## Scope

In scope: this repository's code and the hosted service. Particularly welcome:
tenant isolation bypasses, credential exposure, SSRF through customer URLs,
authentication and session flaws, and injection.

Out of scope: denial of service by volume, findings that need a compromised
device, missing best-practice headers without a demonstrated impact, and
self-hosted instances run with settings our docs advise against.

## Supported versions

Until 1.0, only the latest release receives security fixes.
