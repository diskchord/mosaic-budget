# Mosaic Budget

**Release:** 0.2.0 (2026-08-27)

Mosaic Budget is a self-hosted, mobile-first household budgeting application built around automatic SimpleFIN synchronization. It combines a simple EveryDollar-style monthly budget with an immutable import ledger, exact split accounting, deterministic transaction rules, multi-user conflict detection, and durable operational alerts.

This repository is a runnable MVP rather than a visual mock-up. The browser application, API, PostgreSQL schema, background worker, migrations, backup verifier, notification delivery, demo data, and automated tests are all included.

## What is implemented

- Monthly zero-based budget with Income pinned first
- Month-aware budget structure: add sections/categories from a chosen month, hide them for one month, end them from a chosen month forward, or restore them without rewriting history
- Add, edit, reorder, collapse, and globally archive budget sections and categories while preserving history
- Monthly planned amounts and rollover fund balances
- Unassigned transaction inbox with drag-and-drop category assignment
- Tap-based assignment for phones and assistive input
- Exact-cent transaction splits across multiple categories
- Manual cash income and expenditure transactions
- Deliberate soft deletion, Trash, and restoration
- SimpleFIN setup-token claiming and encrypted Access URL storage
- Automatic routine sync, daily 90-day reconciliation, retries, and local request quota
- Immutable source records and source-version history
- Pending-to-posted reconciliation without deleting ambiguous records
- Rules with account, merchant, amount, date, source, pending, review, and tag conditions
- Fixed and percentage split actions, payee cleanup, tagging, review flags, exclusion, and alerts
- Rule preview and optional historical application
- Manual selected-month rule runs limited to transactions still waiting to be sorted
- Manual categorization locks so background rules do not overwrite a person's decision
- Reversible duplicate-account suppression that retains imported source history without double-counting transactions
- One owner/administrator plus multiple simultaneous users and devices
- Revision-based conflict responses instead of silent last-write-wins edits
- Per-user bright themes, light/dark preference, density, text, and motion settings
- SMTP/SMTP2GO and ntfy notification adapters
- Persistent incident center and durable notification outbox
- Worker, synchronization, backup, and external dead-man health monitoring
- PostgreSQL backups with automated restore verification
- Installable PWA shell with no frontend build toolchain

## Requirements

- Docker Engine with Docker Compose v2
- A machine or VM that can run PostgreSQL and retain a mounted data volume
- HTTPS for any deployment reachable outside a trusted private network
- A SimpleFIN Bridge setup token to enable bank synchronization

## Start the application

```bash
cp .env.example .env
./scripts/generate-secrets.sh
```

Copy the generated values into `.env`, then replace at least:

```dotenv
POSTGRES_PASSWORD=...
APP_SECRET_KEY=...
APP_ENCRYPTION_KEY=...
BOOTSTRAP_ADMIN_EMAIL=alex@example.com
BOOTSTRAP_ADMIN_PASSWORD=a-long-unique-password
BOOTSTRAP_ADMIN_NAME=Alex
```

Start everything:

```bash
docker compose up -d --build
```

Open:

```text
http://your-docker-host:8080
```

The one-time migration service creates the schema and the bootstrap service creates the owner, starter sections/categories, Cash Wallet, and Untracked Cash accounts. Re-running startup is safe.

### Populate an optional demonstration budget

After normal startup:

```bash
make demo
```

This creates a current-month sample budget, transactions, one unassigned Hannaford bubble, and a disabled sample Hannaford rule. It is idempotent, but it writes into the active workspace; use it only before entering real data or in a test deployment.

## Connect SimpleFIN

1. Sign in as the owner.
2. Open **More**.
3. Under **Bank connections**, select **Connect SimpleFIN**.
4. Paste a newly generated SimpleFIN setup token and give the connection a name.
5. Leave the page. The worker begins the first import automatically.

The setup token is claimed once. Mosaic stores the returned Access URL encrypted with `APP_ENCRYPTION_KEY`; neither value is returned to the browser after setup or written to normal logs.

A routine fetch runs every three hours by default, at a stable non-round minute. A deeper 90-day reconciliation runs at least once per day. The app imposes a conservative local ceiling of 20 account requests per rolling 24 hours.

See [docs/SIMPLEFIN.md](docs/SIMPLEFIN.md) for synchronization details and failure behavior.

## Configure alerts

### SMTP2GO or another SMTP relay

```dotenv
SMTP_HOST=mail.smtp2go.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp2go-username
SMTP_PASSWORD=your-smtp2go-password
SMTP_FROM=budget@example.com
SMTP_TO=alex@example.com
SMTP_STARTTLS=true
SMTP_SSL=false
```

### ntfy

```dotenv
NTFY_URL=https://ntfy.sh
NTFY_TOPIC=a-private-hard-to-guess-topic
NTFY_TOKEN=your-access-token
```

Restart the web and worker after changing configuration:

```bash
docker compose up -d --force-recreate web worker
```

Use **More → Notifications → Send test notification** to verify configured channels. Messages intentionally omit transaction descriptions and amounts.

## Production deployment

Do not expose plain HTTP directly to the internet. Put Mosaic behind a reverse proxy that terminates HTTPS, then set:

```dotenv
COOKIE_SECURE=true
TRUSTED_HOSTS=budget.example.com
FORWARDED_ALLOW_IPS=the-private-IP-of-your-proxy
```

An example Caddy configuration is in [ops/Caddyfile.example](ops/Caddyfile.example).

The application port should be reachable only by the reverse proxy or through a trusted private network. PostgreSQL is not published to the host by the supplied Compose file.

Before relying on the deployment:

- Mount `BACKUP_PATH` on storage that is not the same physical host or replicate it off-host.
- Configure `EXTERNAL_HEARTBEAT_URL` so a failure of the whole Docker host can be detected elsewhere.
- Run a notification test.
- Run a manual verified backup with `make backup`.
- Confirm `/health/sync` from a separate monitoring host after the first worker heartbeat and verified backup.
- Preserve `APP_ENCRYPTION_KEY`; losing it makes the stored SimpleFIN credential unreadable.

See [docs/OPERATIONS.md](docs/OPERATIONS.md) and [docs/SECURITY.md](docs/SECURITY.md).

## Backups

The `backup` service performs a PostgreSQL custom-format dump, restores it into a temporary database, verifies core tables, records the successful verification inside Mosaic, and only then treats the backup as valid.

The default local directory is `./backups`. A local copy protects against a bad migration or database volume failure, but not against loss of the Docker host. Set `BACKUP_PATH` to mounted NAS storage or replicate the directory with a separate backup tool.

Run an immediate backup and restore verification:

```bash
make backup
```

The default retention is 35 days. The worker raises a critical incident when no verified backup is recorded within `BACKUP_STALE_HOURS`.

## Tests and verification

From a host with the Python development dependencies available:

```bash
make verify
```

Or inside Docker:

```bash
make test
```

The 42-test suite covers money parsing, rule condition trees, regex timeouts, split safeguards, selected-month manual rule runs, duplicate-account suppression, scheduler behavior, SimpleFIN token and URL validation, credential stripping, SSRF defenses, login/bootstrap/API flow, transaction assignment, atomic transaction month/category changes, budget recalculation, section/category ordering, month-specific starts, one-month hiding, forward endings, later resumption, history preservation, idempotent imports, deletion tombstones, pending-to-posted reconciliation, ambiguous-match review, and concurrent revision rejection.

`make verify` also compiles all Python modules and syntax-checks the browser JavaScript.

Validation performed for this delivery is recorded in [docs/VALIDATION.md](docs/VALIDATION.md).

## Data-integrity model

Mosaic deliberately separates bank data from budget edits:

1. Every accepted SimpleFIN response is stored as an import batch.
2. Each provider transaction has a stable source identity within its Mosaic account.
3. Every distinct source version is append-only.
4. The editable budget transaction contains the user's payee, date, notes, categorization, and splits.
5. Deletion is a tombstone, so the next sync cannot resurrect the record.
6. Allocations are exact decimals and PostgreSQL checks at commit that categorized splits sum to the parent transaction.
7. Every accepted financial mutation creates an audit event.
8. Clients submit object revisions; stale revisions receive HTTP 409 with the current server object.
9. Section and category visibility changes are effective-dated; hiding a budget line never deletes its monthly plans, allocations, transactions, or audit history.
10. Accounts imported more than once may be marked as duplicates; Mosaic suppresses their editable transactions while retaining the raw batches and source ledger, and can restore only the transactions it suppressed if the account is unmarked.

A transaction is never deleted merely because it is absent from a later SimpleFIN response.

## Updating

Before updating:

```bash
make backup
```

Then pull or replace the source and run:

```bash
docker compose up -d --build
```

The `migrate` service applies pending Alembic migrations before the web or worker starts. When upgrading from 0.1.0, migration `0002_month_specific_structure` gives every existing section and category an all-month lifetime, so the pre-upgrade budget remains visible unchanged. New month-specific behavior begins only when a user changes an item's availability.

## Useful commands

```bash
make up       # build and start
make down     # stop without deleting data
make logs     # follow web, worker, and backup logs
make ps       # show service state
make test     # run tests in a container
make verify   # local Python, JavaScript, and test validation
make demo     # add the optional demo budget
make backup   # run a verified backup immediately
make secrets  # generate proposed secret values
```

Do not run `docker compose down -v` unless you deliberately intend to remove the PostgreSQL volume.

## Repository layout

```text
backend/app/api/          HTTP API
backend/app/services/     budget, rules, SimpleFIN, sync, notification logic
backend/app/static/       mobile PWA interface
backend/alembic/          database migrations
backend/tests/            unit and API smoke tests
ops/backups/              verified backup process
scripts/                  setup utilities
docs/                     architecture and operating documentation
```

## Current MVP boundaries

The application is deliberately online-first: the last-known interface may be cached, but financial writes are not queued offline. This avoids hidden multi-device conflicts. Section and category visibility is month-aware and non-destructive; ordering and names remain shared across months. Transfer suggestions exist, but automatic two-sided transfer pairing and formal account reconciliation are not yet full accounting subsystems. There is no native mobile binary; the responsive PWA is installable from a browser.

A live SimpleFIN credential and a Docker/PostgreSQL daemon were not available in the construction environment, so the provider network call and PostgreSQL-specific deferred trigger were not exercised against a live deployment here. The pure logic and complete API flow were exercised locally; the supplied deployment should still be staged and monitored before being entrusted with the only copy of financial data.

## License

No public redistribution license is granted by this repository. Add the license appropriate to your intended use before publishing it.
