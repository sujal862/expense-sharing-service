# API reference

Base URL: `http://localhost:8000`. No authentication in this assignment demo.
Interactive schemas: `/docs`, `/redoc`; machine-readable OpenAPI: `/openapi.json`.

## Endpoints

| Method | Path | Request / response |
| --- | --- | --- |
| POST | `/api/v1/users` | `{ "name": "Mohit" }` → user, 201 |
| GET | `/api/v1/users` | Paginated users |
| POST | `/api/v1/groups` | `{ "name": "Goa Trip" }` → group, 201 |
| GET | `/api/v1/groups` | Paginated groups |
| POST | `/api/v1/groups/{group_id}/members` | `{ "user_id": 1 }` → member, 201 |
| GET | `/api/v1/groups/{group_id}/members` | Paginated members |
| POST | `/api/v1/expenses` | Equal/custom expense → saved expense and shares, 201 |
| GET | `/api/v1/groups/{group_id}/expenses` | Paginated expenses, each with saved shares |
| GET | `/api/v1/groups/{group_id}/balances` | All current pairwise/net balances |
| POST | `/api/v1/groups/{group_id}/settlements` | Payment already made → settlement, 201 |
| GET | `/api/v1/groups/{group_id}/settlements` | Paginated settlement history |
| GET | `/api/v1/groups/{group_id}/settlement-suggestions` | Advisory net settlement plan |
| GET | `/health` | `{ "status": "ok" }`, no database I/O |
| GET | `/ready` | `{ "status": "ready" }` after SELECT 1; otherwise 503 |

List query parameters: `limit` (1–100, default 20), `offset` (≥0, default 0).
Lists return `{"items":[],"limit":20,"offset":0,"has_more":false}`.
Order is ascending entity ID; membership order is ascending user ID.

Names: trimmed, nonblank, at most 100 characters. Descriptions: trimmed, nonblank,
at most 500 characters. IDs are positive signed-BIGINT integers. Unknown fields are rejected.
All money inputs must be unsigned decimal **strings**, ≤2 fractional places and
≤`"1000000000.00"`. JSON numbers are not accepted. Money outputs always have two decimals.
Timestamps are UTC ISO 8601 (`Z`).

## Equal expense

Assume group 1 has members 1, 2, 3. `POST /api/v1/expenses`:

```json
{"group_id":1,"paid_by":1,"amount":"100.00","description":"Dinner"}
```

201 response (example generated ID/timestamp):

```json
{
  "id":1,"group_id":1,"paid_by":1,"amount":"100.00","currency":"INR",
  "description":"Dinner","split_type":"equal","created_at":"2026-10-22T10:00:00Z",
  "splits":[
    {"user_id":1,"amount":"33.34"},
    {"user_id":2,"amount":"33.33"},
    {"user_id":3,"amount":"33.33"}
  ]
}
```

`split_type` defaults to `equal`. Omit `splits` entirely, including `null`.
The payer must be a group member. Remaining paise go to ascending user IDs.

## Custom expense

The payer can pay only on behalf of other members. For example:

```json
{
  "group_id":1,"paid_by":1,"amount":"100.00","description":"Tickets",
  "split_type":"custom",
  "splits":[{"user_id":2,"amount":"70.00"},{"user_id":3,"amount":"30.00"}]
}
```

All participants must belong to the group; duplicate IDs are rejected. Nonnegative
shares must sum exactly to the positive expense total. Zero shares are allowed.
The response uses the same expense shape with `split_type: "custom"` and saved shares.

## Balances

After the equal 100.00 expense above, `GET /api/v1/groups/1/balances`:

```json
{
  "group_id":1,"currency":"INR",
  "pairwise":[
    {"debtor":{"user_id":2,"name":"Rahul"},"creditor":{"user_id":1,"name":"Mohit"},"amount":"33.33"},
    {"debtor":{"user_id":3,"name":"Ankit"},"creditor":{"user_id":1,"name":"Mohit"},"amount":"33.33"}
  ],
  "members":[
    {"user_id":1,"name":"Mohit","net_amount":"66.66","status":"should_receive"},
    {"user_id":2,"name":"Rahul","net_amount":"-33.33","status":"should_pay"},
    {"user_id":3,"name":"Ankit","net_amount":"-33.33","status":"should_pay"}
  ]
}
```

Only nonzero pairwise obligations appear. Every current member appears in `members`,
including zero-net members with status `settled`. IDs identify users, not names.

## Record a settlement

`POST /api/v1/groups/1/settlements`:

```json
{"paid_by":2,"paid_to":1,"amount":"10.00"}
```

201 response:

```json
{
  "id":1,"group_id":1,"paid_by":2,"paid_to":1,"amount":"10.00",
  "currency":"INR","created_at":"2026-10-22T10:05:00Z"
}
```

Sender must have negative group net, recipient positive net; payment cannot exceed
either position. This endpoint records a real payment and does not execute one.
It allows a simplified route even if the sender never owed the recipient directly.

## Suggestions

With A owing B 500 and B owing C 500, the endpoint returns a single transfer:

```json
{
  "group_id":2,"currency":"INR",
  "transfers":[
    {"debtor":{"user_id":1,"name":"A"},"creditor":{"user_id":3,"name":"C"},"amount":"500.00"}
  ],
  "payment_count":1,
  "explanation":"Advisory plan matching the largest debtor and creditor, with user-ID tie-breaking. Preserves net positions and may change who pays whom. Does not guarantee the minimum number of payments. No payments have been recorded or executed."
}
```

After A pays C and records that settlement, `transfers` is empty and `payment_count`
is zero. The historical pairwise ledger can retain a zero-net cycle. Net positions and
suggestions are the current settlement guide. Fetch a fresh plan after every payment;
concurrent financial activity can change the validity of an earlier suggestion.

## Errors

```json
{
  "error":{
    "code":"validation_error",
    "message":"Request validation failed",
    "details":[{"location":["body","amount"],"message":"Value error, Use an unsigned decimal string with at most two decimal places","type":"value_error"}]
  }
}
```

| Status | Examples |
| --- | --- |
| 404 | Missing user on membership addition; missing group |
| 409 | Duplicate membership, sender/recipient wrong net direction, excessive payment, integrity conflict |
| 422 | Malformed/missing fields, invalid amount, empty group, nonmember payer/participant, custom totals |
| 503 | Database operation unavailable or readiness failed |
| 500 | Unexpected internal error, generic message only |

Service validation errors use the same envelope with `details: null`. Missing payer
and an existing nonmember payer both return `invalid_payer`/422: membership is the
required business condition. Unsupported paths/methods use the envelope as well.
