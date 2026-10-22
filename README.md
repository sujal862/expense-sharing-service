# Expense Sharing Service

A backend for tracking shared expenses, calculating who owes whom, and settling group balances. Built for the Decentro SDE Intern assignment.

**Python · FastAPI · MySQL · SQLAlchemy · Alembic · Docker**

[Quick start](#quick-start) · [API documentation](#api-documentation) · [Database design](#database-design) · [Tests](#tests)

## What it supports

- Create users and groups, and add group members.
- Record expenses with equal or custom splits.
- View expense history, pairwise debts, and each member's net balance.
- Record partial or full settlements.
- Get **Smart Settlement Suggestions** to simplify payments between members.

All optional bonus features are included: settlements, unequal splits, tests, and Docker support.

## Quick start

Requires Docker with Docker Compose v2. Run from the repository root.

Copy the example configuration:

```bash
# Linux / macOS
cp .env.example .env
```

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

Start the application:

```bash
docker compose up --build -d --wait api
```

MySQL starts first; migrations run automatically before the API starts. The sample credentials in `.env.example` are for local development.

| Open | Address |
| --- | --- |
| Interactive API docs | http://localhost:8000/docs |
| OpenAPI specification | http://localhost:8000/openapi.json |
| Database readiness | http://localhost:8000/ready |

To try a complete example:

```bash
docker compose exec api python -m scripts.seed_demo
```

This adds synthetic users and two groups demonstrating equal/custom splits, a late joiner, partial settlement, and a simplified payment route. Each run adds fresh records.

The API uses port **8000**; MySQL is exposed locally on **3308**. Change `API_PORT` or `MYSQL_PORT` in `.env` if needed. Stop services with `docker compose --profile test down`; development data remains in the Docker volume.

## API documentation

Use [Swagger UI](http://localhost:8000/docs) to inspect schemas and send requests. See the [API reference](docs/api-reference.md) for request/response examples and errors.

All routes below use the `/api/v1` prefix.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST / GET | `/users` | Create / list users |
| POST / GET | `/groups` | Create / list groups |
| POST / GET | `/groups/{id}/members` | Add / list members |
| POST | `/expenses` | Record an equal or custom expense |
| GET | `/groups/{id}/expenses` | View expense history |
| GET | `/groups/{id}/balances` | View pairwise and net balances |
| POST / GET | `/groups/{id}/settlements` | Record / list payments |
| GET | `/groups/{id}/settlement-suggestions` | Generate a simplified payment plan |

Example: after creating a group and adding its members, send `POST /api/v1/expenses` using their returned IDs:

```json
{
  "group_id": 1,
  "paid_by": 1,
  "amount": "1200.00",
  "description": "Dinner"
}
```

With three members, each share is ₹400; the other two members each owe the payer ₹400. Equal splitting is the default. For unequal shares, use `split_type: "custom"` and provide `splits`, as shown in the API reference.

**Money inputs are decimal strings**, such as `"1200.00"`, with at most two decimal places. List endpoints support `limit` and `offset`.

Optional: import the [Postman collection](docs/postman/expense-sharing.postman_collection.json) and [local environment](docs/postman/local.postman_environment.json), select the environment, and run the collection in order.

## Database design

MySQL stores six related tables; Alembic manages the schema.

| Table | Key fields | Stores |
| --- | --- | --- |
| `users` | `id` (PK), `name` | People; duplicate names are allowed |
| `groups` | `id` (PK), `name` | Expense-sharing groups |
| `group_members` | `group_id` + `user_id` (composite PK, FKs) | Membership without duplicates |
| `expenses` | `id` (PK), `group_id`, `paid_by` (FKs), `amount_paise`, `split_type` | Who paid and how much |
| `expense_splits` | `expense_id` + `user_id` (composite PK, FKs), `share_paise` | Each participant's saved share |
| `settlements` | `id` (PK), `group_id`, `paid_by`, `paid_to` (FKs), `amount_paise` | Payments recorded between members |

Users join groups through `group_members`. Each expense belongs to a group and has participant split rows. Settlements connect a sender and recipient within a group.

Three decisions keep the financial records consistent:

- **Integer paise:** ₹100.50 is stored as `10050`. Equal-split remainders are allocated in ascending user ID order, so shares always add up exactly.
- **Saved shares:** a member joining later does not inherit old expenses. Custom shares must total the expense amount.
- **Atomic writes:** an expense and its splits commit together. Group row locks protect membership changes and settlement validation from conflicting writes.

Balances are calculated from expenses, splits, and settlements rather than maintained in a separate balance table. Foreign keys preserve valid references and restrict deletion of financial history. Full definitions are in the [models](app/models/entities.py) and [initial migration](migrations/versions/0001_initial.py).

## Product enhancement: Smart Settlement Suggestions

After a trip, several debts can require unnecessary intermediate payments. If **A owes B ₹500** and **B owes C ₹500**, the service suggests **A pays C ₹500**.

The algorithm matches the largest debtor with the largest creditor using net balances. It preserves each member's final position and runs in **O(n log n)** after loading balances. Greedy matching is practical and deterministic, but does not guarantee the fewest possible payments.

Suggestions are advisory. The settlement endpoint separately records payments already made. Simplified payments can leave a zero-net cycle in the historical pairwise view; net balances and suggestions show what remains to settle.

See [design decisions](docs/design-decisions.md) for the rationale, assumptions, and tradeoffs.

## Tests

With Python 3.11 and an activated virtual environment:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests/unit -q
```

Tests cover money validation, splitting, balance calculations, and settlement suggestions. MySQL integration tests also cover API validation, saved membership history, rollback, and concurrent settlements.

<details>
<summary>Run the full suite against an isolated MySQL test database</summary>

Start the disposable test service:

```bash
docker compose --profile test up -d --wait test-db
```

Linux / macOS:

```bash
export TEST_DATABASE_URL='mysql+asyncmy://expense_test:test_demo@127.0.0.1:3307/expense_sharing_test'
python -m pytest -q
unset TEST_DATABASE_URL
```

Windows PowerShell:

```powershell
$env:TEST_DATABASE_URL = 'mysql+asyncmy://expense_test:test_demo@127.0.0.1:3307/expense_sharing_test'
python -m pytest -q
Remove-Item Env:TEST_DATABASE_URL
```

Integration tests clear their isolated test tables. A safety guard requires the designated test database and user. Without `TEST_DATABASE_URL`, integration tests are skipped.

</details>

## Scope and next steps

The service supports INR and append-only expense records. Equal splits include all current members; custom splits may include a subset. Settlements cannot exceed the sender's or recipient's outstanding net position.

Authentication, bank transfers, expense corrections, and idempotent requests are outside this implementation. Next steps would be group-level authorization, idempotency keys for financial writes, and traceable expense reversals.
