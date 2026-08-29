# Architecture

## Design priorities

Mosaic Budget is organized around two priorities: a low-friction phone interface and conservative treatment of financial records. The browser can be replaced; the ledger must remain recoverable and explainable.

## Runtime topology

```text
Browser / installed PWA
        |
        | HTTPS, JSON, server-sent events
        v
FastAPI web service ----------------------------+
        |                                       |
        v                                       |
PostgreSQL <---------------- Background worker  |
        |                         |              |
        |                         +--> SimpleFIN |
        |                         +--> SMTP      |
        |                         +--> ntfy      |
        |                         +--> dead-man -+
        v
Verified backup service --> mounted/off-host backup storage
```

`web` and `worker` are intentionally stateless. PostgreSQL is the sole authority for financial records, sessions, jobs, incidents, audit events, and pending notification deliveries.

## Source ledger and editable ledger

### Immutable source layer

- `import_batches` stores complete accepted provider payloads and checksums.
- `source_transactions` stores provider identity scoped to the internal account.
- `source_transaction_versions` stores every distinct version of amount, dates, pending state, description, and extra fields.
- `first_seen_batch_id` and `last_seen_batch_id` retain provenance.
- `superseded_by_id` links a pending source record to a replacement posted source record when confidence is unambiguous.

### Editable budgeting layer

- `budget_transactions` contains the budgeting effective date, editable payee, notes, tags, flags, and manual locks.
- `allocations` contains one or more exact signed amounts assigned to categories.
- An unassigned transaction has zero allocations.
- A normal categorized transaction has one allocation equal to the parent amount.
- A split has multiple allocations whose sum equals the parent amount.

A normal delete changes `deleted_at`; it does not remove either layer.

### Recipient-first display labels

The API derives a human-facing `display_payee` without rewriting either ledger. Structured SimpleFIN merchant/recipient fields take priority; otherwise a conservative ACH parser may promote a high-confidence company name and remove a known payment wrapper, such as displaying **PHILO TV** for a Privacy.com description containing `PwP PHILO TV`. Ambiguous descriptions remain unchanged.

The complete imported description remains in the immutable source version and is retained separately on the editable transaction record. Its payee field remains editable. User-edited payees and rule-applied names take precedence over inference. Rules continue to evaluate the original fields, so improving a headline does not change matching behavior or provenance.

## Money and signs

All money is stored as `numeric(20,4)`. Python operations use `Decimal`; the browser parses amounts into integer ten-thousandths using `BigInt`. No financial calculation uses binary floating-point arithmetic.

SimpleFIN positive amounts are treated as inflows and negative amounts as outflows. Allocations carry the same sign as their parent transaction. Income-section activity increases received income; expense-section activity decreases the remaining budget.

## Month-specific budget structure

Sections and categories are stable historical identities with effective-month availability:

- `starts_month` is the first inclusive month in which the item may appear.
- `ends_before_month` is an optional exclusive boundary.
- `section_month_exclusions` and `category_month_exclusions` represent deliberate one-month gaps.
- `archived_at` is the explicit all-month archive state.

A category is usable only when both its own lifetime and its parent section's lifetime include the transaction month and neither has a matching month exclusion. Income is a protected section whose availability cannot be changed.

Ending an item and later resuming it converts the intervening finite gap into explicit monthly exclusions. This preserves the earlier lifetime and the later resumption without rewriting past budgets. A full restoration clears the range and exclusion controls but still leaves all transaction and audit history unchanged.

`category_budgets` rows are retained even when their category is hidden. Existing allocations are also retained. The visible budget omits hidden plans from **Left to assign**, while actual cash-flow totals continue to include historical allocations. New manual allocations, transaction date changes, and automatic rule actions validate effective availability before writing.

Names, notes, rollover settings, and ordering remain properties of the stable section/category identity and are shared across months. Availability, monthly planned values, and activity are month-sensitive.

## Budget computation

For each month, the API loads all section/category identities, evaluates their effective availability, loads category plans, current-month allocations, and prior rollover activity.

- Planned income and planned expenses produce **Left to assign**.
- Actual inflows and outflows produce actual cash flow.
- Ordinary category remaining is planned plus signed activity.
- Fund remaining includes the category's cumulative prior plans and activity.

The server computes all totals. The browser formats and previews values but is not authoritative.

## Global inbox and displayed-month assignment

The budget response's unassigned inbox is deliberately workspace-wide rather than filtered to the displayed month. Deleted, excluded, duplicate-suppressed, and duplicate-account transactions are omitted, but an eligible July transaction remains available while the August budget is open. The tray names August as the target so that this cross-month effect is explicit before a drop.

An inbox assignment sends the selected category, displayed target month, transaction IDs, and expected versions in one batch request. The server locks and validates the complete group, maps each budgeting effective date into the target year and month while preserving its day or clamping it to the month's final day, validates category availability on the resulting dates, and writes the date and allocations atomically. The move sets the manual date and allocation locks and clears review state; a failure changes none of the group.

The response contains the moved transaction versions and a short-lived, HMAC-signed Undo token containing only the server-observed original date, lock, and review values. The token is bound to the workspace, user session, category, target month, transaction IDs, and assigned versions; the browser cannot author or alter the restore state. Undo verifies that receipt and the current versions, then atomically clears the new allocations and restores the originals. Immutable source dates and imported descriptions are never rewritten by either operation.

## Analytics computation

`GET /api/analytics?start_month=YYYY-MM&end_month=YYYY-MM` accepts an inclusive range, defaults to the 12 months ending in the current month, and rejects ranges longer than 120 months. It returns ordered monthly actuals, range totals and averages, categorization coverage, and per-category month series. Empty months are emitted explicitly with zero values so comparisons keep a stable timeline.

Analytics uses allocation signs and Income-section identity rather than attempting to infer meaning from raw transaction signs. Unassigned transactions are reported separately and do not distort categorized income or spending. Deleted, excluded, duplicate-suppressed, and duplicate-account transactions are filtered out with the same visibility semantics as the budget.

## Synchronization lifecycle

1. The worker claims a due connection using a PostgreSQL advisory lock.
2. It checks the rolling request quota.
3. It selects a routine or deep overlapping date window.
4. It records a sync run and request attempt.
5. It requests SimpleFIN version 2 with pending transactions included.
6. It rejects redirects, malformed JSON, invalid amounts, and invalid identities.
7. It starts the import transaction and stores the complete payload.
8. It upserts institution and account observations without overwriting user account names or activation choices.
9. It appends source versions and updates editable records only where manual locks permit. Transactions from an account marked as a duplicate are retained but flagged as duplicate-suppressed and excluded from user-facing transaction lists and budget totals.
10. It applies deterministic rules to normal imported accounts; duplicate-suppressed transactions do not run rules or generate user-facing new-transaction counts.
11. It evaluates configured balance alerts for accounts observed in the synchronization.
12. It records structured provider errors as persistent incidents.
13. It commits the imported ledger, audit events, and queued notifications.
14. It schedules the next stable polling time.

Repeating an identical payload only updates `last_seen_batch_id`; it does not duplicate a transaction or version.

## Pending-to-posted reconciliation

When a newly posted transaction has a different source ID, Mosaic looks for pending records in the same account with the same signed amount, normalized description, and a nearby date.

- Exactly one match: the posted source is attached to the existing editable transaction and the pending source is marked superseded.
- Multiple matches: no record is discarded; an incident and review item are created.
- No match: a new editable transaction is created.

Absence from a later response is never interpreted as deletion.

## Rules

Rules are JSON condition trees and ordered action lists.

Phases execute in this order:

1. `cleanup`
2. `categorize`
3. `finish`

Within a phase, rules are sorted by priority and creation time. A rule may stop further rules in its phase. The engine is deterministic for a fixed transaction and rule revision.

Manual payee, date, and allocation decisions are protected by field-specific locks. A rule may override them only when its `apply_to_manual_overrides` flag is deliberately enabled.

Regular-expression evaluation has a pattern-length limit and execution timeout.

Enabled rules may also be run manually as one ordered ruleset. A manual run is constrained to the selected calendar month and selects only active, non-excluded transactions that have no allocations when the run begins. It never revisits already sorted transactions.

## Duplicate imported accounts

The same real bank account can arrive through more than one SimpleFIN connection, so provider identity alone cannot decide which feed a household wants to use. The owner may explicitly mark one imported account as a duplicate.

Mosaic continues recording accepted import batches, source identities, and source versions for that account, but marks its editable transactions as excluded with separate duplicate-suppression provenance. Existing and future duplicate-feed transactions are omitted from normal transaction lists, inboxes, budget activity, rules, and synchronization new/change counts. Clearing the account flag restores only transactions excluded by duplicate suppression; independently excluded transactions remain excluded. No source record or allocation is deleted or merged.

## Concurrency

Each editable object has an integer version. A mutation includes the version read by the client. The API locks the row, compares versions, and either:

- applies the change and increments the version, or
- returns HTTP 409 with the current serialized object.

The browser presents a conflict choice rather than silently overwriting another device. Server-sent events announce workspace audit activity so open clients can refresh.

## Incident and notification pipeline

`notification_incidents` deduplicates active operational problems by a stable incident key. `notification_outbox` is a durable delivery queue. Detecting an incident and queuing its message occur in the same database transaction.

`balance_alerts` stores an owner-selected account, above/below comparison, exact threshold, enabled state, and selected delivery channels. Creation and edits evaluate immediately; synchronization and manual balance mutations evaluate affected accounts in the same transaction; account/connection state changes evaluate immediately; and the worker health pass also evaluates all enabled alerts. A triggered alert reuses the incident/outbox pipeline, while a real balance recovery resolves the incident and queues a recovery message with the recovered balance. Administrative closure is silent. Duplicate, inactive, unknown-balance, paused-connection, and disconnected accounts are exposed as unavailable rather than falsely watched.

Most incidents use every configured notification channel and avoid financial values. Balance alerts are an explicit opt-in exception: their incident text includes the account name, current balance, and threshold, and their outbox rows are restricted to the channels selected on that individual alert. An explicit selected-channel outbox row remains durable and retryable if that channel's deployment configuration is temporarily removed.

Delivery failures increment an attempt count and receive exponential backoff. Restarting the worker does not lose pending alerts. Recovery resolves the incident and may queue a recovery notification.

A failure of the entire host cannot be reported by that host. `EXTERNAL_HEARTBEAT_URL` must point to an independently monitored service for full-stack dead-man detection.

## Authentication and authorization

- Passwords use Argon2id.
- Server-side sessions store only a SHA-256 hash of the random cookie token.
- State-changing requests require a session-bound double-submit CSRF token.
- Login failures are rate-limited by a keyed hash of email and source address.
- Invalid credentials receive one generic inline error and never create a session; only authenticated requests that later receive HTTP 401 invoke the global session-ended flow.
- Exactly one active owner is enforced by application logic and a PostgreSQL partial unique index.
- Only the owner may create/disable users, transfer ownership, manage SimpleFIN and balance alerts, or view operational administration.

## Backup verification

The backup container creates a PostgreSQL custom-format dump, creates a temporary database, restores the dump, checks core tables, writes a verification record to the production database, and removes the temporary database. Retention is applied only after this process.

The database record is used by the worker's backup-staleness monitor. Off-host durability depends on where `BACKUP_PATH` is mounted or replicated.
