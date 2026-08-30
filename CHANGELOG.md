# Changelog

## Unreleased

- Made single-category sorting the transaction editor default, with splitting available as a secondary action
- Enlarged the floating **To sort** control across phone and desktop layouts and centered its icon, count, and label
- Added mouse, touch, and keyboard reordering for budget sections, categories, and rules, including cross-section category moves, fixed Income placement, phase-safe atomic rule ordering, conflict recovery, and focus restoration
- Kept **To sort** open while inspecting a transaction so canceling returns smoothly to the same sorting context
- Made sorting confirmations click- and drag-through so stacked status bubbles no longer block transaction controls, while keeping their Undo buttons interactive
- Added an installable Android companion with a polished HTTPS server picker, secure exact-origin WebView isolation, password-manager-compatible sign-in, complete feature parity, touch drag-and-drop, offline recovery, adaptive icons, and safe native Back behavior
- Prepared the project for public GitHub collaboration with a concise README, Apache 2.0 licensing, CI, issue forms, pull-request guidance, and contribution and vulnerability-reporting policies
- Added the Compose backup runner with atomic dumps, isolated restore verification, safe overlap locking, verified-backup records, retries, and retention
- Replaced the inconsistent chart/mask branding with one polished mosaic-style vector mark across the app, favicon, and PWA
- Corrected topbar grid placement and responsive page-header spacing
- Added an **Analytics** view and authenticated range API for comparing monthly income, spending, net cash flow, transaction coverage, and category activity across an inclusive range
- Added owner-managed account balance thresholds with per-alert delivery through configured SMTP2GO/email and/or ntfy channels, including one-time trigger and recovery notifications
- Kept invalid-credential responses in the sign-in form without also presenting the global expired-session message
- Added a selected-month **Run rules** action that processes only transactions still waiting to be sorted
- Prevented stale browser snapshots from leaving categorized transactions in **To sort**, and made rule results distinguish successfully sorted transactions from matching transactions that remain unsorted
- Added conservative recipient-first titles for noisy SimpleFIN ACH descriptions, including PHILO-style payment-wrapper cleanup, while retaining the complete imported text, editable payee, and existing rule behavior
- Added reversible duplicate SimpleFIN account marking so duplicate-feed transactions do not appear or affect the budget while source history remains intact
- Added desktop and touch-friendly inbox multi-selection, group drag-and-drop, an accessible **Assign selected...** action, and atomic batch assignment with group Undo; after a drop, the tray now returns smoothly and remains open on the next transaction
- Made **To sort** a global inbox: dropping an older transaction into the displayed month's category atomically moves its budgeting date into that month, preserves or month-end clamps its day, sets the manual date lock, and can be restored exactly with **Undo**
- Added atomic multi-transaction editing for category, review, and budget-inclusion changes from the Transactions list
- Added editable names for manual and SimpleFIN accounts, preserved those names across synchronization, resolved account-based rule summaries to readable names, moved inactive and duplicate accounts out of the regular account list into a muted connection-management state, and made connection account-list saves atomic
- Refined income progress wording, category drop-target padding, icon spacing, month-arrow alignment, transaction selection affordances, and desktop branding
- Added Alembic revision `0003_duplicate_accounts`
- Added Alembic revision `0004_balance_alerts`

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
