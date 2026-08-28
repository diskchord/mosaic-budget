# Contributing to Mosaic Budget

Thanks for helping make self-hosted budgeting simpler and safer. Bug reports,
documentation fixes, tests, and focused feature changes are all welcome.

## Before you start

- Search the existing issues before opening a new one.
- Use synthetic examples. Never post bank credentials, SimpleFIN Access URLs,
  account identifiers, raw provider payloads, or real financial records.
- Report suspected vulnerabilities through the private process in
  [SECURITY.md](SECURITY.md), not a public issue.
- For a substantial behavior or schema change, open an issue first so the
  design and migration path can be discussed.

## Development setup

Production uses PostgreSQL and Docker Compose. The automated suite uses an
in-memory SQLite database where possible, so most changes can be checked without
running the full stack.

```bash
git clone https://github.com/diskchord/mosaic-budget.git
cd mosaic-budget
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
make verify
```

Local verification requires Python 3.12 or newer and Node.js for the browser
JavaScript syntax check. To exercise the containerized application instead:

```bash
cp .env.example .env
make secrets
# Copy the generated values into .env and replace every CHANGE_ME value.
make up
make test
```

Use only disposable data while developing.

## Project map

```text
backend/app/api/       HTTP endpoints
backend/app/services/  budgeting, rules, sync, and notification logic
backend/app/static/    browser application and PWA assets
backend/alembic/       database migrations
backend/tests/         unit and API tests
docs/                  user, architecture, security, and operations guides
ops/                   deployment and backup assets
```

The [architecture guide](docs/ARCHITECTURE.md) explains the source ledger,
editable budget records, money signs, concurrency, and backup model.

## Making a change

1. Create a focused branch from `main`.
2. Keep the change small enough to review and explain.
3. Add or update tests for behavior changes.
4. Add an Alembic migration for every persistent schema change; do not rewrite
   an existing released migration.
5. Preserve exact-decimal money handling, append-only import history, deletion
   tombstones, and optimistic concurrency.
6. Update user or operations documentation when behavior changes.
7. Run `make verify` and `git diff --check`.

The frontend intentionally has no build toolchain. Keep it accessible by
supporting keyboard/tap input, visible focus, reduced motion, and narrow mobile
viewports.

## Pull requests

In the pull request, describe the user-visible outcome, the integrity or
security impact, how it was tested, and any deployment or migration steps.
Screenshots are helpful for interface changes, but they must contain only
synthetic data.

All intentionally submitted contributions are accepted under the project's
[Apache License 2.0](LICENSE).
