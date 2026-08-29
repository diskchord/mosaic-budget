# SimpleFIN Integration

## Setup-token claim

A SimpleFIN setup token is URL-safe Base64 text containing a one-time HTTPS claim URL. The owner supplies it through the bank-connections screen. Mosaic:

1. decodes and validates the claim URL,
2. rejects local, private, reserved, non-HTTPS, and fragment-bearing URLs,
3. posts an empty request without following redirects,
4. validates the credential-bearing Access URL returned by SimpleFIN,
5. encrypts that Access URL before commit, and
6. schedules an automatic initial import.

A rejected or already-used token must be disabled in the Bridge and replaced with a new token.

## Account request

The worker requests the Access URL's `accounts` endpoint with:

```text
version=2
start-date=<epoch>
end-date=<epoch>
pending=1
```

Basic Auth credentials are extracted from the Access URL but omitted from the request URL and logs. Redirects are rejected rather than followed after credentials are attached.

## Identity scope

Provider account IDs are scoped by the connection. Mosaic therefore identifies an account by:

```text
Mosaic SimpleFIN connection + source conn_id + source account id
```

A source transaction is unique by:

```text
Mosaic account + source transaction id
```

This prevents collisions among institutions or multiple SimpleFIN connections.

Those identities intentionally do not guess whether two provider accounts represent the same real account. If the same account is supplied through more than one SimpleFIN connection, the owner can mark one copy as a duplicate in the account manager. Mosaic continues retaining its raw payload and source ledger for auditability, while its editable transactions are reversibly suppressed so they do not appear twice or affect the budget.

## Polling

Defaults:

- routine import every 180 minutes
- stable randomized non-round schedule minute
- routine window of the previous seven days
- daily deep window of the previous 90 days
- pending transactions included
- local rolling ceiling of 20 requests per 24 hours

Windows overlap intentionally. Idempotent source identities and content hashes make repeated observations safe.

## Errors

Transport, authorization, payment, malformed-payload, and structured account errors are separate states. Structured `errlist` entries become deduplicated incidents and remain visible until a later successful response no longer contains them.

The app does not treat an incomplete account listing or a missing transaction as deletion.

## Pending transactions

A provider may retain a transaction ID when pending becomes posted, or replace it. Mosaic handles both:

- Same ID: append a source version and update the editable record.
- New ID with exactly one strong pending match: attach it to the existing editable record and supersede the old source.
- More than one strong match: retain all data and request review.
- No strong match: create a separate transaction.

Manual category, date, and payee locks survive source updates.

## Transaction display names

The [SimpleFIN protocol](https://www.simplefin.org/protocol.html#transaction) guarantees one human-readable transaction `description`; it does not define a separate merchant, payee, or recipient field. Its optional `extra` object is provider-defined. Mosaic therefore keeps the description and extra data unchanged in the source ledger and uses only explicit provider keys or narrow, high-confidence ACH company fields to compute a shorter display payee. Manual payees and rule-renamed payees take precedence, and any ambiguous description is shown verbatim.

The computed display value is presentation-only. Original-description and payee rule conditions continue to evaluate their existing stored fields, so adding or refining a display parser does not silently change automation.

## Disconnecting

Pausing leaves the encrypted Access URL in place. Disconnecting requires typing the connection name and removes the encrypted credential while retaining all imported data. Reconnecting later requires a new setup token.
