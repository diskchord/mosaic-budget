# Validation Record

## Current unreleased changes

- Python compilation, browser JavaScript syntax, service-worker syntax, SVG XML, and the PWA manifest all validate.
- The complete 42-test suite passes, including the new rule-run API, duplicate-account API, expanded rule engine, and database-backed synchronization coverage.
- Direct route-level checks passed for selected-month, unsorted-only rule execution and reversible duplicate-account suppression with independent exclusion preservation and audit counts.
- A fresh SQLite Alembic run applied revisions through `0003_duplicate_accounts`; a downgrade-to-0002 and re-upgrade check also passed.
- Headless Chromium renders at 320 and 1440 pixels confirmed that the new logo is legible, month navigation stays centered, topbar controls do not overlap, actions stack on a narrow Rules screen, and desktop sync/profile controls remain right-aligned.

Validation date: 2026-08-27
Release: 0.2.0

## Completed in the construction environment

- All Python application, migration, and test modules compiled successfully.
- The browser application passed `node --check`.
- The complete pytest suite passed: 35 tests.
- The API smoke test exercised database bootstrap, owner login, CSRF-authenticated writes, manual transaction creation, category assignment, budget activity recalculation, and stale-revision conflict rejection.
- Budget-structure API tests exercised section and category creation, reordering, movement between sections, and all-month archival.
- Month-specific structure tests exercised future starts, normal carry-forward, one-month hiding, restoration, forward endings, later resumption with a preserved gap, section-level visibility, protected Income, rejection of new allocations to unavailable categories, and an atomic transaction month/category move.
- A preservation test proved that hiding a category leaves its existing monthly plan and activity intact, keeps actual cash flow correct, and restores the original values.
- Database-backed import tests proved repeated payload idempotency, deletion-tombstone persistence, pending-to-posted inheritance of a manual allocation, and preservation/review of every record in an ambiguous pending match.
- Unit tests exercised exact money parsing, nested rule conditions, regular-expression timeout handling, fixed and percentage split validation, duplicate-category rejection, SimpleFIN scheduling, setup-token decoding, Access URL parsing, credential removal from request URLs, redirect rejection, and private-address rejection.
- A fresh SQLite migration run applied Alembic revisions `0001_initial` and `0002_month_specific_structure`, reached the expected schema, and completed bootstrap. SQLite is used only as a local verification substitute; production remains PostgreSQL.
- A headless Chromium run at a 390 x 844 phone viewport exercised the rendered interface end to end: sign-in, future category creation, carry-forward, forward removal, two-month gap, later resumption, one-month hiding, restoration, and the month-aware removal modal.
- Shell scripts passed `sh -n`; Compose YAML and the PWA manifest parsed successfully.
- The final release ZIP passed an archive integrity check, was extracted into a clean directory, and passed the complete 35-test, Python-compilation, JavaScript-syntax, configuration, and shell-syntax verification again.

## Not available in the construction environment

- Docker Engine was not available, so Compose service startup and health orchestration were not executed here.
- A live SimpleFIN setup token was not available, so no real institution data was requested.
- A PostgreSQL daemon was not available. The PostgreSQL-specific deferred allocation-sum trigger, partial unique indexes, and the in-place 0.1.0-to-0.2.0 PostgreSQL migration were inspected but not executed against a live PostgreSQL server.
- SMTP2GO, ntfy, and an external heartbeat endpoint were not supplied, so network delivery was not performed.

## Required staging validation

Before entering irreplaceable data:

1. Back up the existing database and retain the dump outside the Docker host.
2. Start the supplied Compose stack on the target host and confirm migrations through `0003_duplicate_accounts` complete once.
3. Confirm existing sections/categories appear in all historical and future months as before the update.
4. Run `make test` inside Docker.
5. In a disposable workspace, exercise a category start, one-month hide, forward ending, and restoration.
6. Claim a test SimpleFIN token and inspect at least one routine and one deep run.
7. Verify that repeating a sync does not duplicate transactions, then mark a disposable imported account as duplicate and confirm its transactions disappear and restore when unmarked.
8. Run enabled rules for a selected month and confirm only unsorted transactions in that month are changed.
9. Send SMTP and ntfy test messages.
10. Run `make backup`, confirm restore verification, and copy one dump off-host.
11. Confirm an external monitor reports failure when the worker or host is stopped.
