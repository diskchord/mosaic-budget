# Security Guide

## Threat model

Mosaic stores transaction history, account metadata, and a credential-bearing SimpleFIN Access URL. Protecting the host, reverse proxy, secrets, backups, and administrator account is part of protecting the application.

## Secret handling

- `APP_SECRET_KEY` keys login-throttle identifiers and future application signing needs.
- `APP_ENCRYPTION_KEY` is a Fernet key used to encrypt the SimpleFIN Access URL at rest.
- PostgreSQL, SMTP, and ntfy passwords remain environment secrets.
- SimpleFIN setup tokens are accepted once and never stored.
- Access URLs are encrypted immediately and never returned through the API.

Keep `.env` readable only by the deployment owner. For a higher-assurance deployment, inject equivalent values with a secrets manager rather than leaving them on disk.

## Network controls

- Use HTTPS outside a private trusted network.
- Set `COOKIE_SECURE=true` when HTTPS is in use.
- Replace `TRUSTED_HOSTS=*` with the public hostname.
- Restrict the exposed application port to the reverse proxy.
- Do not publish PostgreSQL.
- Restrict `FORWARDED_ALLOW_IPS` to the proxy address so clients cannot forge scheme or source-address headers.

The SimpleFIN client allows only HTTPS, resolves and rejects private/reserved destinations, rejects local names, validates certificates through the HTTP client, and refuses redirects after credentials are attached.

## Browser protections

The server sends:

- Content Security Policy with same-origin scripts and connections
- frame denial
- MIME-sniffing prevention
- same-origin referrer policy
- restricted browser permissions
- HSTS on HTTPS requests

The session cookie is random, server-side, `HttpOnly`, `SameSite=Lax`, and optionally `Secure`. State changes require a separate session-bound CSRF token in both the cookie and request header.

## Passwords and sessions

Passwords are hashed with Argon2id. Failed logins are throttled by email/address identity without storing the raw identity. Sessions can be reviewed and revoked. Disabling a user removes their sessions. The owner cannot be removed until ownership is transferred.

Use a long unique owner password and a password manager. TOTP is not implemented in this MVP, so reverse-proxy access controls or a private overlay network materially improve security.

## Data minimization

SMTP and ntfy messages contain operational descriptions but omit merchant names, balances, transaction amounts, and credentials. Audit events may contain transaction serialization needed for accountability and should be treated as financial data.

Raw SimpleFIN payloads are intentionally retained for recoverability and diagnosis. That is a reliability advantage and a privacy responsibility. Backups therefore require the same protection as the live database.

## Deletion semantics

Normal transaction deletion is reversible and retains a tombstone. This is deliberate. It prevents a synced item from reappearing and preserves auditability. It is not a cryptographic erasure feature.

## Reporting a vulnerability

Do not include credentials, Access URLs, raw payloads, or real transaction data in an issue report. Reproduce with synthetic data and include only sanitized logs.
