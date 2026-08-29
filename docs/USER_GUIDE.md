# User Guide

## Budget screen

The selected month opens on the Budget screen. Income is always first. Each visible category shows its plan, activity, progress, and remaining amount.

Select a planned value to change it. Planned amounts belong to that individual month. Fund categories carry their cumulative remaining amount between months; ordinary categories start from the selected month's plan.

## Compare months with Analytics

Open **Analytics** to compare actual activity across an inclusive range of months. Choose the first and last month to see income, spending, net cash flow, transaction coverage, and category activity together. The default range is the trailing 12 months ending with the current month, and a range may contain up to 120 months.

Monthly rows make adjacent periods easy to compare, while range totals and averages summarize the complete selection. Category comparisons use the same income-versus-expense signs as the budget. Months without activity are shown as zero rather than omitted.

Transactions still waiting to be sorted are disclosed separately and do not get guessed into income or spending. Deleted, excluded, duplicate-suppressed, and duplicate-account transactions are omitted from Analytics just as they are from normal budget activity.

## Sections and categories from month to month

Sections and categories normally carry forward automatically after their first month. Income is protected and exists in every month, but its income categories may be managed like other categories.

When creating a section or category, choose when it first appears:

- **Selected month** - it begins in the month currently open and continues forward.
- **All months** - it is also available in earlier budget history.
- **Choose another month** - it begins on a specific future or past month.

Open a section or category editor and select **Remove from budget months...** for three non-destructive choices:

- **Beginning with this month** - earlier months remain unchanged, and the item stays hidden afterward.
- **Only for this one month** - it disappears for the selected month and returns automatically in the next month.
- **Archive in every month** - it is hidden throughout the budget until deliberately restored.

A notice appears when the open month contains hidden items. **Manage hidden items** can:

- show an item in only the current month,
- resume an ended item from a chosen month while preserving the gap, or
- restore it in all months.

Hiding or ending an item does not delete it. Existing monthly plans, transaction allocations, notes, rules, and audit history remain intact. If a hidden category already contains activity in that month, the activity still contributes to cash-flow totals and is identified in the hidden-items notice.

New transactions and automatic rules cannot be assigned to a category that is unavailable in the transaction's month. Existing historical assignments remain visible when their transactions are opened.

Names and ordering are shared across months. Month specificity controls whether the item is present, not a separate name or position for every month.

## Sort incoming transactions

The **to sort** button opens the shared, month-independent inbox of unsorted activity. The tray states which budget month is currently targeted. Dropping a July transaction while August is open moves its budgeting date into August and assigns it to the chosen August category in one atomic change. The day of month is preserved where possible and clamped to the target month's final day when necessary. Check the control on the left of any transaction bubble to build a selection on either desktop or touch devices. On a computer:

- **Ctrl** (or **Cmd** on macOS) toggles individual bubbles.
- **Shift** selects an inclusive range from the last selected bubble.

Drag a checked bubble onto a category to move the entire checked group. Dragging a bubble that is not checked moves only that bubble and leaves the existing selection unchanged. On a touch device, press and hold a bubble before dragging so the inbox can still scroll normally.

For a keyboard-friendly alternative, check the bubbles and choose **Assign selected...**, then choose the destination category. Selecting a bubble normally still opens its transaction editor for individual assignment or splitting.

The target category highlights during the drag. Group assignment is atomic: either every selected transaction is moved into the displayed month and assigned, or none are changed. After a successful drop, the category pulses with its updated amount, the confirmation names the destination month, and the inbox returns smoothly, removes the assigned bubbles, stays open, and places focus on the next available transaction. Moving the budgeting date sets its manual date lock, and assigning the category sets its manual allocation lock, so synchronization and ordinary background rules cannot silently reverse either choice. **Undo** restores the original dates, locks, review state, and complete unassigned group together.

The inbox refreshes from the server before it opens, so a transaction categorized by a rule or another device is removed even if the page previously held an older copy. Rule runs report successful sorts separately from matching transactions that remain in **To sort** because an assignment was blocked or invalid; those transactions are left intact for review.

SimpleFIN sometimes supplies a long bank-formatted description instead of a separate merchant name. When Mosaic can identify a high-confidence recipient or company, that shorter name is used as the transaction headline throughout the inbox, list, details, drag preview, and rule preview. For example, a Privacy.com ACH description containing `PwP PHILO TV` is headed **PHILO TV**. The complete bank description remains available under **Imported source details**, and the **Payee** field remains editable when you want a different permanent name. A payee you edit yourself or rename with a rule always takes precedence, and ambiguous descriptions are displayed unchanged.

## Split a transaction

Open a transaction and choose **Split**. Add each category and exact signed amount. The remaining indicator must reach zero before saving. Mosaic rejects duplicate categories and any split whose exact total differs from the transaction.

## Edit several transactions

Open **Transactions** and select from the left edge of each row. After the first selection, the selection controls remain visible and the action bar can select every loaded result, clear the group, or open **Edit selected...**. Shift-select chooses a range; Ctrl-select or Cmd-select toggles a row without opening it.

The group editor can move single-category or unassigned transactions to one category, make them unassigned, change their review status, and include or exclude them from budget totals. Unchanged fields retain each transaction's individual value. Split transactions can still be updated together for review or budget status, but must be recategorized individually. Group updates are version-checked and atomic, so a conflict changes none of the selected transactions.

## Add cash or manual activity

Open Transactions and select **Add transaction**. Choose Cash Wallet to maintain a running manual cash balance, or Untracked Cash when only the budget effect matters. Positive amounts are income; negative amounts are expenditure.

## Delete and restore

Open the transaction menu, choose Delete, and type the displayed signed amount. The item moves to Trash. Synced source identity is retained so a later bank sync cannot simply bring it back. Open Trash to restore it.

## Rules

Create a rule from the Rules screen or from a representative transaction. A rule consists of:

- a readable set of all/any/none conditions,
- a phase and priority,
- one or more actions,
- optional permission to override manual decisions, and
- a stop/continue choice.

Preview matching transactions before saving. Historical application can be limited to unassigned records or selected explicitly. Keep merchant rules as narrow as necessary by adding account and amount conditions.

To process transactions already in the inbox, open **Rules**, choose the month in the header, and select **Run rules**. Mosaic runs the complete enabled ruleset in its normal phase and priority order, but only against non-excluded transactions in that selected month that are still unsorted. Transactions with an existing category or split are never changed by this manual run.

A rule may reference a category that is not present in the month currently open, because it may be valid for other months. At runtime, Mosaic checks the transaction's own month. If the target is unavailable there, the rule leaves the transaction intact, flags it for review, and opens an operational incident instead of assigning it incorrectly.

## Name and deduplicate accounts

Open **More → Accounts** and use the edit button to give a manual or synced account a familiar name. Account names are used throughout transaction and rule displays, remain scoped to the workspace, and are not overwritten by a later SimpleFIN synchronization.

If the same bank account is imported through two SimpleFIN connections, open **More → Bank connections**, open the affected connection, and choose **Manage accounts**. Mark the redundant copy as **This is a duplicate account**, make any other account-name or status changes, and choose **Save all accounts** once. All changes are validated and saved atomically.

Mosaic immediately removes that account's transactions from the inbox, transaction lists, and budget totals. Future observations from the duplicate feed remain in the protected source ledger but stay hidden and do not run rules. Clearing the duplicate setting restores transactions that Mosaic hid for this reason; transactions you excluded separately remain excluded.

Inactive and duplicate accounts are omitted from the regular **More → Accounts** list. Imported accounts remain visible with a muted status inside their bank connection and its account manager, where the owner can rename or reactivate them, or clear the duplicate setting.

## Account balance alerts

The owner can open **More → Balance alerts** and add a named threshold for an account. Choose whether Mosaic should notify when the balance falls below or rises above the amount, then select any configured SMTP2GO/email and ntfy channels. A channel must be configured by the deployment owner before it can be selected.

Mosaic sends one notification when the threshold condition opens instead of repeating a message on every check. When the balance returns to the safe side, it sends a recovery notification with the new balance. Alerts can be edited, disabled, or deleted, and their current state remains visible on the More screen. An inactive, duplicate, unknown-balance, paused-connection, or disconnected account is marked unavailable instead of being presented as actively watched.

Balance-alert messages deliberately include the account name, current balance, and configured threshold. Create an alert only on channels whose recipients are trusted to receive that financial information.

## Sign in

An incorrect email or password is reported directly beneath the sign-in form. The separate session-ended notification is reserved for a session that expires after a successful sign-in, so an ordinary credential mistake does not produce two competing messages.

## Conflicts

When another device changes the same object first, Mosaic rejects the stale save and shows the current server version. Review the new value, then keep it or deliberately reapply yours. Nothing is overwritten silently.

## Themes

Themes and display preferences belong to the signed-in user. Changing a theme does not affect another household member. High Contrast and reduced-motion settings remain available independently of the bright default themes.
