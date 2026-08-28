# Security Policy

Mosaic Budget stores sensitive financial history and an encrypted SimpleFIN
credential. Please handle suspected vulnerabilities privately and avoid sharing
real financial data while investigating them.

## Supported code

Security fixes are developed against the current `main` branch and, when
practical, the most recent release. Older deployments should first reproduce
the issue on the latest code. Release history is documented in
[CHANGELOG.md](CHANGELOG.md).

## Report a vulnerability

Use GitHub's private vulnerability reporting from this repository's
**Security** tab:

[Report a vulnerability privately](https://github.com/diskchord/mosaic-budget/security/advisories/new)

If that option is unavailable, open a public issue asking the maintainers to
provide a private contact route. Do not include the vulnerability details in
that issue.

Include, when possible:

- the affected version or commit;
- the component and configuration involved;
- reproducible steps using synthetic data;
- the likely impact and any known workarounds; and
- sanitized logs or a minimal proof of concept.

Never send SimpleFIN setup tokens or Access URLs, `.env` contents, session
cookies, private keys, account identifiers, raw bank payloads, or real
transactions.

Please allow time to reproduce and address the report before public disclosure.
The maintainers will coordinate the fix and disclosure with the reporter
through the private advisory.

## Deployment concerns

Configuration weaknesses and lost host credentials may require operational
remediation even when no source-code change is needed. The
[deployment security guide](docs/SECURITY.md) covers HTTPS, reverse proxies,
cookies, secrets, backups, browser controls, and the application's threat model.
