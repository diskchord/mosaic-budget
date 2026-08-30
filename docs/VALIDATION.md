# Validation Record

## Current unreleased changes

- Python compilation, browser JavaScript syntax, service-worker syntax, SVG XML, and the PWA manifest all validate.
- The complete 113-test suite passes, including permanent month-forward structure deletion, whole-split uncategorization, future-start deletion, deleted-section child rejection, deleted-row-safe reordering, dependent-rule disabling, Analytics aggregation, balance-alert lifecycle and manual-account integration, invalid-login handling, conservative SimpleFIN recipient display names, raw-description preservation, unchanged-payee lock prevention, atomic cross-month inbox assignment, session-bound signed group Undo, same-month date locking, pending-to-posted reconciliation after a month move, atomic Transactions-list category/review/exclusion updates, atomic connection account-list saves, readable account catalogs and renaming, duplicate-account handling, explicit rule sorted/still-unsorted outcomes, category-default propagation, the 200/200+ inbox boundary, the expanded rule engine, and database-backed synchronization coverage.
- The Android companion builds an installable API 26–36 debug APK and passes Android lint. Its manifest and implementation were checked for HTTPS-only transport, exact-origin navigation, first-party-only cookies, disabled file/content/mixed access, cancelled SSL errors, cleared state on server changes, adaptive/monochrome icons, and dirty-form-safe Back handling.
- Direct route-level checks passed for the noisy ACH/Privacy.com example resolving to `PHILO TV` without changing stored source text or rule-facing payees, selected-month unsorted-only rule execution, successful rule assignments disappearing from both unassigned APIs, failed historical assignments remaining reviewable with accurate outcome counts, atomic multi-account edits, and reversible duplicate-account suppression with independent exclusion preservation and audit counts.
- A fresh SQLite Alembic run applied revisions through `0005_structure_deletions`; the new revision downgraded to a true pre-feature `0004_balance_alerts` schema and re-upgraded successfully, the earlier downgrade-to-0003 and re-upgrade checks passed, and `alembic check` reports no model/migration drift. The channel column compiles to JSONB for PostgreSQL and JSON for SQLite.
- Headless Chromium renders at 320 and 1440 pixels confirmed that the new logo is legible, month navigation stays centered, topbar controls do not overlap, actions stack on a narrow Rules screen, and desktop sync/profile controls remain right-aligned.
- A live headless Chromium interaction run exercised desktop Ctrl/Cmd toggles, inclusive Shift ranges, left-side drag initiation, a four-item group drag after forced pointer-capture loss, unblurred drop hit-testing, atomic assignment and Undo, and the **Assign selected...** dialog. A 390 x 844 touch run exercised checkbox selection, real tray scrolling, press-and-hold activation, category targeting, and group drop; a captured layout pass confirmed the shortened help text, selection bar, and bubbles fit without horizontal overflow.
- A second live Chromium pass at 1440 x 900 and 390 x 844 verified over-target income wording, inset drop-target padding, section-icon spacing, exact month-arrow centering, single-logo desktop branding, hidden-until-selected transaction controls, two-row atomic review editing, account renaming propagated into transaction and rule text, inactive and duplicate accounts omitted from the regular account list and visibly identified in connection management, and zero mobile horizontal overflow. A final account-manager pass verified 44-pixel checkbox rows, responsive one/two-column controls, removal of the explanatory sentence and per-account buttons, dirty-state reversal, and one atomic request containing edits to two accounts.
- A live stale-inbox check assigned a transaction while the browser deliberately retained an older unassigned snapshot, then verified that opening **To sort** issued one authoritative budget refresh and removed the transaction from cached state, tray rendering, and the unassigned API while it remained present in the assigned API.
- Focused authentication coverage verifies that an unknown email receives the generic credential error and creates no session. The login request is exempt from the global expired-session handler, leaving that backend message in the sign-in form.
- Focused Analytics coverage exercises inclusive ranges, monthly/category comparisons, split allocations, refunds, explicit zero months, uncategorized disclosure, duplicate/excluded/deleted visibility, and reversed, malformed, overlong, and calendar-boundary range rejection.
- Focused balance-alert coverage exercises SMTP2GO and ntfy channel selection, Unicode ntfy titles, temporarily unavailable-channel retry, strict name/numeric validation, account and connection availability, exact threshold editing, optimistic conflicts, one trigger delivery per selected channel while a condition remains open, cancellation of stale administrative deliveries, a new episode after material reconfiguration, current-balance recovery content, serialized evaluator runs, and immediate, transaction-safe evaluation for manual create/delete/restore.
- A live Chromium acceptance passed 15/15 login and Analytics checks at 1440 and 390 pixels: inline invalid credentials without a session toast, exact range totals and deltas, comparison-selector focus retention, authoritative navigation to the latest month with unsorted activity, responsive layout without page overflow, and no runtime console errors.
- A live Chromium balance-alert acceptance verified Triggered, Paused, Unavailable, and deleted states; correct SMTP2GO, threshold, and current-balance text; exclusion from Operational alerts; zero overflow at 390 pixels; and no runtime or API errors.
- Live Chromium pointer and touch acceptance confirmed that a successful drop smoothly restores the tray, keeps it open, removes the assigned transaction, and focuses the next one. The 390 x 844 touch run captured intermediate transform and opacity frames through the return animation; neither run produced a runtime exception.
- Live Chromium cross-month acceptance dropped a July 15 `PHILO TV` income transaction into August's **Other Income**, confirmed the August-target tray copy and drop highlight, persisted an August 15 budgeting date and `$160` August activity with zero July category activity, then restored the exact July date and original review/lock state through **Undo**. The Transactions list used `PHILO TV` as its headline, and the run produced no runtime exception or horizontal overflow.
- The synthetic-data screenshot harness completed all 14 desktop/mobile captures while verifying that the single hidden-items notice is the budget's final element, clears the floating **To sort** control, opens the hidden-item manager, and exposes permanent deletion for already-hidden items at both responsive widths.
- GitHub CI validates Python and JavaScript, shell syntax, Compose configuration, the PWA manifest and SVG, local Markdown links, dependency consistency, and the complete test suite.
- The backup runner passed mocked end-to-end dump/restore/record flow, concurrent-run serialization, and failed-`createdb` ownership-safety checks without touching a live database.
- The working tree and reachable Git history were scanned for common credential signatures and sensitive filenames; none were found.

Validation date: 2026-08-30
Source state: 0.2.0 plus the changes listed under Unreleased

## 0.2.0 baseline validation

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
2. Start the supplied Compose stack on the target host and confirm migrations through `0005_structure_deletions` complete once.
3. Confirm existing sections/categories appear in all historical and future months as before the update.
4. Run `make test` inside Docker.
5. In a disposable workspace, exercise a category start, one-month hide, forward ending, and restoration. Then permanently delete a disposable category and section, confirm they disappear only from the selected month forward, and confirm affected transactions return fully uncategorized to **To sort**.
6. Claim a test SimpleFIN token and inspect at least one routine and one deep run.
7. Verify that repeating a sync does not duplicate transactions, then mark a disposable imported account as duplicate and confirm its transactions disappear and restore when unmarked.
8. Rename both a manual account and a disposable SimpleFIN account, synchronize again, and confirm the custom names remain visible in transactions and account-based rules.
9. Run enabled rules for a selected month and confirm only unsorted transactions in that month are changed.
10. In the transaction inbox, check bubbles on desktop and touch, exercise Ctrl/Cmd toggling and an inclusive Shift range on desktop, then confirm dragging a checked bubble assigns the complete group while dragging an unchecked bubble assigns only that transaction. After several successful drops, confirm the tray returns without a snap, remains open, focuses the next available transaction, and lets clicks and drags pass through stacked confirmation text while each **Undo** button remains interactive.
11. On a touch device, confirm ordinary inbox scrolling still works and press-and-hold starts a drag; also assign a checked group with **Assign selected...** using only the keyboard.
12. In the Transactions list, select several rows and atomically change category, review status, and budget inclusion; confirm a stale row or split recategorization changes none of the group.
13. While viewing one month, assign a transaction imported in another month and confirm its budgeting date moves into the displayed month, retains or month-end clamps its day, and cannot be reverted by a later source sync. Confirm a failed group assignment changes no transactions, and that **Undo** restores the complete group's original dates, locks, review state, and allocations.
14. Compare a known two-month period in Analytics and confirm income, spending, net, unsorted disclosure, and at least one category series against the underlying transactions.
15. Enter an invalid email/password and confirm the backend credential message appears only beneath the form, without a session-ended toast.
16. Send SMTP and ntfy test messages, then create a synthetic balance alert for each configured channel. Cross and recover the threshold and confirm both messages contain the intended account, current balance, and threshold and reach only the selected recipients.
17. Run `make backup`, confirm restore verification, and copy one dump off-host.
18. Confirm an external monitor reports failure when the worker or host is stopped.
