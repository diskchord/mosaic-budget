# Operations Guide

## First deployment checklist

1. Copy `.env.example` to `.env`.
2. Generate and set all secrets.
3. Set the owner email, name, and a unique password of at least 14 characters.
4. Choose a durable `BACKUP_PATH`.
5. Build and start with `docker compose up -d --build`.
6. Confirm `docker compose ps` shows `db`, `web`, `worker`, and `backup` healthy after startup.
7. Sign in and connect SimpleFIN.
8. Configure SMTP and/or ntfy, then send a test alert.
9. Run `make backup` and confirm the backup record appears under **More → Operations**.
10. Configure an external monitor for `/health/sync` and/or `EXTERNAL_HEARTBEAT_URL`.

## Service responsibilities

### db

PostgreSQL financial ledger and operational state. Its volume is `postgres_data`.

### migrate

One-shot service. Applies Alembic migrations and runs the idempotent bootstrap. Web and worker start only after it succeeds.

### web

FastAPI, static PWA, authentication, budget and transaction APIs, administration, and server-sent events.

### worker

SimpleFIN scheduling, import and reconciliation, rule application, notification delivery, stale-sync monitoring, backup monitoring, session cleanup, and external heartbeat.

### backup

Daily custom-format dump and automated restore test.

## Health endpoints

- `/health/live` confirms the web process is serving.
- `/health/ready` confirms the web process can query PostgreSQL.
- `/health/sync` confirms a recent worker heartbeat, no stale enabled SimpleFIN connection, and a recent verified backup.

`/health/sync` intentionally returns HTTP 503 until the first verified backup exists. This distinguishes an installed application from an operationally protected one.

## Reading synchronization state

The connection card shows:

- last attempt
- last success
- next scheduled run
- consecutive failures
- latest sanitized error

The run history records routine/deep mode, window, account and transaction counts, structured errors, and failure code. Provider credentials are not shown.

## Retry behavior

A failed sync is rescheduled with bounded exponential delay. Authorization and payment errors alert immediately; transient errors alert after repeated failures. The request attempt remains in the rolling quota log, preventing an outage from causing an uncontrolled polling loop.

The **Retry now** control only marks the connection due. The worker still owns all provider requests and quota enforcement.

## Logs

```bash
make logs
```

Logs should contain IDs, state changes, and sanitized exception messages. They should not contain setup tokens, Access URLs, bank balances, transaction descriptions, or notification credentials.

Treat logs as sensitive operational data even with these redactions.

## Backup and recovery

### Immediate verified backup

```bash
make backup
```

### Locate backups

```bash
ls -lh "${BACKUP_PATH:-./backups}"
```

Files use PostgreSQL custom format and end in `.dump`.

### Restore into a new deployment

Stop application writers first:

```bash
docker compose stop web worker backup
```

Keep the database running, create a new empty database, and restore into it. One safe approach is to restore outside the existing database and then change `POSTGRES_DB` only after verification.

Example from the project directory:

```bash
BACKUP=./backups/mosaic-YYYYMMDDTHHMMSSZ.dump

docker compose exec db createdb -U "$POSTGRES_USER" mosaic_restore
cat "$BACKUP" | docker compose exec -T db pg_restore \
  -U "$POSTGRES_USER" \
  -d mosaic_restore \
  --clean --if-exists --no-owner
```

Inspect the restored database before cutover. Do not destroy the original PostgreSQL volume during recovery.

### Secret recovery

A database backup does not replace secret backup. Preserve securely:

- `APP_ENCRYPTION_KEY`
- `APP_SECRET_KEY`
- SMTP/ntfy credentials
- reverse-proxy TLS and DNS configuration

Without the original `APP_ENCRYPTION_KEY`, imported financial records remain usable but the stored SimpleFIN Access URL cannot be decrypted. A new SimpleFIN setup token would be required.

## Updating

1. Run `make backup`.
2. Read the migration and release notes.
3. Replace or update the source.
4. Run `docker compose up -d --build`.
5. Watch `docker compose logs migrate web worker`.
6. Confirm `/health/ready`, the budget page, a test edit, and the next sync.

Alembic is the schema authority. Do not use `Base.metadata.create_all` against production as an update strategy.

## Pausing bank access

Disabling a connection stops scheduled requests but retains its encrypted credential. Disconnecting deliberately removes the encrypted Access URL and cannot be reversed without claiming a new setup token. Imported records remain.

## User incident response

### Duplicate-looking transactions

Do not delete one immediately if a pending transaction recently posted. Check pending state and source information. Ambiguous pending reconciliation is deliberately surfaced for review rather than silently merged.

### A deleted transaction returned

This should not occur because the editable record remains tombstoned. Check whether the bank delivered a genuinely different source ID that did not match the deleted record. Preserve both records while investigating.

### Worker unhealthy

```bash
docker compose logs --tail=300 worker
docker compose restart worker
```

A worker restart is safe; due jobs, incidents, and outbox messages are stored in PostgreSQL.

### Database unhealthy

```bash
docker compose logs --tail=300 db
docker compose exec db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

Do not repeatedly recreate containers or volumes before preserving logs and confirming backup availability.

## Capacity

The supplied single-web/single-worker topology is appropriate for a household workspace. PostgreSQL advisory locks and optimistic revisions support running additional web instances and prevent simultaneous sync of the same connection. Large-scale multi-tenant hosting would require further isolation, observability, and deployment controls.
