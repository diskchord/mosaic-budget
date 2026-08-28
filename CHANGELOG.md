# Changelog

## Unreleased

- Prepared the project for public GitHub collaboration with a concise README, Apache 2.0 licensing, CI, issue forms, pull-request guidance, and contribution and vulnerability-reporting policies
- Added the Compose backup runner with atomic dumps, isolated restore verification, safe overlap locking, verified-backup records, retries, and retention
- Replaced the inconsistent chart/mask branding with one polished mosaic-style vector mark across the app, favicon, and PWA
- Corrected topbar grid placement and responsive page-header spacing
- Added a selected-month **Run rules** action that processes only transactions still waiting to be sorted
- Added reversible duplicate SimpleFIN account marking so duplicate-feed transactions do not appear or affect the budget while source history remains intact
- Added desktop and touch-friendly inbox multi-selection, group drag-and-drop, an accessible **Assign selected...** action, and atomic batch assignment with group Undo
- Added atomic multi-transaction editing for category, review, and budget-inclusion changes from the Transactions list
- Added editable names for manual and SimpleFIN accounts, preserved those names across synchronization, resolved account-based rule summaries to readable names, and moved duplicate feeds out of the regular account list into a muted connection-manager state
- Refined income progress wording, category drop-target padding, icon spacing, month-arrow alignment, transaction selection affordances, and desktop branding
- Added Alembic revision `0003_duplicate_accounts`

## 0.2.0 - 2026-08-27

Month-aware budget structure revision:

- Sections and categories now have an inclusive first month and an optional exclusive ending month
- New sections/categories may begin in the selected month, all months, or another chosen month
- A section/category may be hidden for one month, removed from a chosen month forward, or archived everywhere
- Ended items may resume in a later month while preserving the intervening gap
- Hidden-item manager restores one month, resumes from a month, or restores all history
- Monthly budget plans and historical allocations remain intact while an item is hidden
- Hidden historical activity remains included in cash-flow totals instead of disappearing
- New manual allocations and automatic rules cannot assign transactions to unavailable categories
- Transaction month and category can be changed atomically, avoiding an invalid intermediate state
- Income remains protected and present in every month
- Added Alembic migration `0002_month_specific_structure` for existing PostgreSQL installations
- Added mobile controls and visibility summaries for month-aware structure management
- Expanded the automated suite from 26 to 35 tests
- Verified a clean migration/bootstrap and a complete mobile browser flow for start, carry-forward, end, gap, resume, one-month hide, and restore

## 0.1.0 - 2026-08-27

Initial runnable MVP:

- Docker Compose deployment with PostgreSQL, migration, web, worker, and verified backup services
- Mobile-first monthly budget and transaction inbox
- Manual, split, deleted, restored, and automatically categorized transactions
- SimpleFIN v2 claim, polling, source ledger, pending reconciliation, quota, and incident handling
- Multi-user owner administration, session management, optimistic conflicts, and server-sent updates
- SMTP/SMTP2GO, ntfy, durable outbox, health endpoints, and external dead-man support
- Seven user themes, per-user section collapse state, and responsive PWA
- Mobile section/category editing, movement, reordering, and archival
- 26 automated unit, API, structure, and database-backed import tests
