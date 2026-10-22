# Design decisions

## Keeping the project simple

The PDF describes an Expense Sharing Service, so that is what this project builds.
FastAPI provides request validation and interactive API docs. MySQL fits the related
data and supports transactions, constraints, and row locking. Routes handle HTTP,
services handle business rules, and pure functions handle calculations.

Users are identified by IDs, so two people can have the same name. Groups start
empty, and the same user cannot join a group twice.

## Handling money accurately

All calculations and database amounts use integer paise: INR 100.50 becomes 10050.
The API accepts decimal strings such as `"100.50"`, validates them with Decimal,
and returns amounts with two decimal places. JSON numbers and amounts with more
than two decimal places are rejected rather than rounded.

The maximum individual expense, payment, or share is INR 1,000,000,000.00.
Expenses and payments must be positive; individual shares can be zero.

Equal expenses include all current members. Any remaining paise go to members in
ascending user ID order. For example, INR 100 becomes 33.34, 33.33, and 33.33.
Custom splits can include a subset of members and may leave out the payer. Shares
must be nonnegative, use distinct member IDs, and add up exactly to the total.

## Preserving expense history

Each expense saves its participant shares when it is created. Someone joining later
does not get charged for an old expense.

Foreign keys protect references, composite primary keys prevent duplicate memberships
and shares, and check constraints enforce amount limits. Referenced records cannot
be deleted while dependent records exist. The service checks participant membership
and share totals inside the transaction; direct SQL writes could bypass those checks.

Timestamps are stored as UTC in MySQL DATETIME(6) and returned with the UTC offset.

## Keeping writes consistent

Adding a member, creating an expense, and recording a settlement first lock the group
row with `SELECT ... FOR UPDATE`. Dependent reads happen after acquiring that lock.
This keeps membership changes and expense creation coordinated, and prevents two
settlements from using the same outdated outstanding balance.

The expense and all its shares are saved in one transaction. If any insert fails,
the whole operation rolls back. REPEATABLE READ gives balance and suggestion requests
a consistent snapshot across their queries.

The tradeoff is that writes to the same group wait for each other. That is a reasonable
choice for this assignment's scope.

## Deriving balances from records

Balances come from expenses, saved shares, and settlements. There is no separate
balance table to keep in sync.

`net = expenses paid - shares allocated + payments sent - payments received`

Positive means the member should receive money; negative means they should pay.
The group's net balances always sum to zero.

Pairwise balances cancel opposite debts between the same two users. Settlements are
validated against net positions, so a member can pay someone they did not owe directly.
Partial payments are allowed, up to both parties' outstanding positions.

For example, if A owes B 500 and B owes C 500, A can pay C 500. Everyone's net becomes
zero, although the historical pairwise view keeps a zero-net cycle. Net balances and
suggestions show what remains to pay. Settlements only record payments already made;
the API does not move bank money.

## Smart Settlement Suggestions

Many connected debts can be awkward to settle. The algorithm repeatedly matches the
largest debtor with the largest creditor and suggests the smaller outstanding amount.
Equal amounts use ascending user ID as the tie-breaker.

Priority queues make matching O(n log n) after balances are calculated. The plan
preserves everyone's net position and may change who pays whom. It is useful and
deterministic, but does not guarantee the fewest possible payments. Suggestions are
advisory and are never saved as transactions.

## Queries, testing, and limits

Queries load group data in batches instead of fetching each user's or expense's data
separately. Lists use bounded pagination and stable ID ordering. Balance calculations
still load the group's history, so large groups would need SQL aggregation or another
measured improvement.

Integration tests use a separate MySQL service. A safety guard checks the explicit test
URL before cleanup, requiring the test database and user and rejecting the configured
development database.

Docker runs migrations before starting the API for this single-instance demo. A larger
deployment should run migrations as a separate step.

Authentication, authorization, idempotency keys, multiple currencies, and expense
corrections are future improvements. Without idempotency keys, clients should check
history before retrying a payment request after an unclear network failure. This is a
local assignment demo, not a production deployment.
