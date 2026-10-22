import asyncio

import pytest
from sqlalchemy import event, func, select

from app.models.entities import Expense, ExpenseSplit

pytestmark = pytest.mark.integration


async def expense(client, group, *, payer=None, amount="1200.00", **extra):
    group_id, users = group
    return await client.post(
        "/api/v1/expenses",
        json={
            "group_id": group_id,
            "paid_by": payer or users[0],
            "amount": amount,
            "description": "Dinner",
            **extra,
        },
    )


async def get_balances(client, group_id):
    response = await client.get(f"/api/v1/groups/{group_id}/balances")
    assert response.status_code == 200, response.text
    return response.json()


async def test_users_groups_members_and_pagination(client, group):
    group_id, users = group
    duplicate_name = await client.post("/api/v1/users", json={"name": "Mohit"})
    assert duplicate_name.status_code == 201
    response = await client.get("/api/v1/users?limit=2")
    data = response.json()
    assert len(data["items"]) == 2 and data["has_more"]
    assert data["items"][0]["created_at"].endswith("Z")
    assert (await client.get("/api/v1/users?limit=0")).status_code == 422
    assert len((await client.get("/api/v1/groups")).json()["items"]) == 1
    path = f"/api/v1/groups/{group_id}/members"
    assert [item["user_id"] for item in (await client.get(path)).json()["items"]] == users
    assert (await client.post(path, json={"user_id": users[0]})).status_code == 409
    assert (await client.post(path, json={"user_id": 9223372036854775807})).status_code == 404
    assert (await client.get("/api/v1/groups/9223372036854775807/members")).status_code == 404
    assert (await client.post("/api/v1/users", json={"name": "  "})).status_code == 422


async def test_expense_history_saved_membership_and_different_payers(client, group):
    group_id, users = group
    first = await expense(client, group, amount="100.00")
    assert first.status_code == 201, first.text
    assert [s["amount"] for s in first.json()["splits"]] == ["33.34", "33.33", "33.33"]
    new_user = (await client.post("/api/v1/users", json={"name": "New member"})).json()["id"]
    await client.post(f"/api/v1/groups/{group_id}/members", json={"user_id": new_user})
    second = await expense(client, group, payer=users[1], amount="40.00")
    assert len(second.json()["splits"]) == 4
    custom = await expense(
        client,
        group,
        payer=users[2],
        amount="20.00",
        split_type="custom",
        splits=[{"user_id": users[0], "amount": "20.00"}],
    )
    assert custom.status_code == 201
    history = (await client.get(f"/api/v1/groups/{group_id}/expenses")).json()["items"]
    assert len(history) == 3 and history[0]["splits"] == first.json()["splits"]
    balances = await get_balances(client, group_id)
    assert {m["user_id"]: m["net_amount"] for m in balances["members"]} == {
        users[0]: "36.66",
        users[1]: "-3.33",
        users[2]: "-23.33",
        new_user: "-10.00",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": "0"},
        {"amount": "-1"},
        {"amount": "1.001"},
        {"amount": 10.50},
        {"paid_by": 9223372036854775807},
        {"amount": "1000000000.01"},
        {"split_type": "equal", "splits": [{"user_id": 1, "amount": "1200"}]},
    ],
)
async def test_invalid_expenses(client, group, overrides):
    response = await expense(client, group, **overrides)
    assert response.status_code == 422, response.text
    assert "error" in response.json()
    group_id, _ = group
    assert (await client.get(f"/api/v1/groups/{group_id}/expenses")).json()["items"] == []


async def test_invalid_group_empty_group_and_nonmember_payer(client, group):
    assert (await expense(client, group, group_id=9223372036854775807)).status_code == 404
    empty = (await client.post("/api/v1/groups", json={"name": "Empty"})).json()["id"]
    assert (await expense(client, group, group_id=empty)).status_code == 422
    outsider = (await client.post("/api/v1/users", json={"name": "Outside"})).json()["id"]
    assert (await expense(client, group, payer=outsider)).status_code == 422


async def test_custom_split_validations(client, group):
    _, users = group
    outsider = (await client.post("/api/v1/users", json={"name": "Outside"})).json()["id"]
    for splits in (
        [{"user_id": users[0], "amount": "99"}],
        [{"user_id": users[0], "amount": "50"}, {"user_id": users[0], "amount": "50"}],
        [{"user_id": outsider, "amount": "100"}],
        [{"user_id": users[0], "amount": "0"}],
        [{"user_id": users[0], "amount": "-1"}, {"user_id": users[1], "amount": "101"}],
    ):
        response = await expense(client, group, amount="100", split_type="custom", splits=splits)
        assert response.status_code == 422, response.text
    response = await expense(
        client,
        group,
        amount="100",
        split_type="custom",
        splits=[{"user_id": users[1], "amount": "100"}, {"user_id": users[2], "amount": "0"}],
    )
    assert response.status_code == 201, response.text
    assert response.json()["splits"][-1]["amount"] == "0.00"


async def test_partial_full_and_excess_settlement(client, group):
    group_id, users = group
    await expense(client, group)
    path = f"/api/v1/groups/{group_id}/settlements"
    body = {"paid_by": users[1], "paid_to": users[0], "amount": "200"}
    assert (await client.post(path, json=body)).status_code == 201
    assert (await client.post(path, json=body | {"amount": "201"})).status_code == 409
    assert (await client.post(path, json=body)).status_code == 201
    assert (await client.post(path, json=body)).status_code == 409
    assert (
        await client.post(path, json=body | {"paid_by": users[2], "amount": "400"})
    ).status_code == 201
    assert len((await client.get(path)).json()["items"]) == 3
    assert all(m["net_amount"] == "0.00" for m in (await get_balances(client, group_id))["members"])
    assert (await client.get(f"/api/v1/groups/{group_id}/settlement-suggestions")).json()[
        "transfers"
    ] == []


async def test_simplified_route_settlement(client, group):
    group_id, (a, b, c) = group
    # A owes B; B owes C. B has zero net, so A can pay C directly.
    for payer, participant in ((b, a), (c, b)):
        response = await expense(
            client,
            group,
            payer=payer,
            amount="500",
            split_type="custom",
            splits=[{"user_id": participant, "amount": "500"}],
        )
        assert response.status_code == 201
    path = f"/api/v1/groups/{group_id}"
    suggested = (await client.get(f"{path}/settlement-suggestions")).json()
    assert suggested["payment_count"] == 1
    assert suggested["transfers"][0]["debtor"]["user_id"] == a
    assert suggested["transfers"][0]["creditor"]["user_id"] == c
    assert (
        await client.post(f"{path}/settlements", json={"paid_by": a, "paid_to": c, "amount": "500"})
    ).status_code == 201
    balances = await get_balances(client, group_id)
    assert len(balances["pairwise"]) == 3  # Historical ledger retains a zero-net cycle.
    assert all(member["net_amount"] == "0.00" for member in balances["members"])
    assert (await client.get(f"{path}/settlement-suggestions")).json()["payment_count"] == 0


async def test_transaction_rollback_on_split_insert_failure(client, app, group):
    def fail_split(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("INSERT INTO expense_splits"):
            raise RuntimeError("Injected split persistence failure")

    event.listen(app.state.engine.sync_engine, "before_cursor_execute", fail_split)
    try:
        with pytest.raises(RuntimeError, match="Injected split"):
            await expense(client, group)
    finally:
        event.remove(app.state.engine.sync_engine, "before_cursor_execute", fail_split)
    async with app.state.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Expense)) == 0
        assert await session.scalar(select(func.count()).select_from(ExpenseSplit)) == 0


async def test_concurrent_settlements_cannot_over_settle(client, app, group):
    group_id, users = group
    await expense(client, group)
    # Hold the group lock so both HTTP requests really overlap and wait on it.
    from app.services.ledger import require_group

    async with app.state.session_factory() as blocker, blocker.begin():
        await require_group(blocker, group_id, lock=True)
        tasks = [
            asyncio.create_task(
                client.post(
                    f"/api/v1/groups/{group_id}/settlements",
                    json={"paid_by": users[1], "paid_to": users[0], "amount": "300"},
                )
            )
            for _ in range(2)
        ]
        await asyncio.sleep(0.1)
        assert not any(task.done() for task in tasks)
    responses = await asyncio.gather(*tasks)
    assert sorted(response.status_code for response in responses) == [201, 409]
    balances = await get_balances(client, group_id)
    assert (
        next(m for m in balances["members"] if m["user_id"] == users[1])["net_amount"] == "-100.00"
    )


async def test_health_and_readiness(client):
    assert (await client.get("/health")).json() == {"status": "ok"}
    assert (await client.get("/ready")).json() == {"status": "ready"}
    assert (await client.get("/missing")).json()["error"]["code"] == "http_error"


async def test_settlement_validation_and_recipient_limit(client, group):
    group_id, (a, b, c) = group
    for payer, amount in ((b, "300"), (c, "700")):
        assert (
            await expense(
                client,
                group,
                payer=payer,
                amount=amount,
                split_type="custom",
                splits=[{"user_id": a, "amount": amount}],
            )
        ).status_code == 201
    path = f"/api/v1/groups/{group_id}/settlements"
    for payload, status in [
        ({"paid_by": a, "paid_to": b, "amount": "301"}, 409),
        ({"paid_by": b, "paid_to": a, "amount": "1"}, 409),
        ({"paid_by": a, "paid_to": a, "amount": "1"}, 422),
        ({"paid_by": a, "paid_to": b, "amount": "0"}, 422),
        ({"paid_by": a, "paid_to": b, "amount": "1.001"}, 422),
        ({"paid_by": a, "paid_to": 9223372036854775807, "amount": "1"}, 422),
    ]:
        response = await client.post(path, json=payload)
        assert response.status_code == status, response.text
    assert (await client.get(path)).json()["items"] == []


async def test_group_balance_snapshot_during_concurrent_write(client, app, group):
    from app.services.ledger import load_balances, require_group

    group_id, users = group
    async with app.state.session_factory() as reader, reader.begin():
        # First ordinary SELECT establishes the read snapshot, without blocking writers.
        await require_group(reader, group_id)
        assert (await expense(client, group)).status_code == 201
        _, net, pairs = await load_balances(reader, group_id)
        assert net == dict.fromkeys(users, 0) and pairs == []
    current = await get_balances(client, group_id)
    assert current["members"][0]["net_amount"] == "800.00"


async def test_expense_waits_for_membership_write(client, app, group):
    from app.models.entities import GroupMember
    from app.services.ledger import require_group

    group_id, _ = group
    newcomer = (await client.post("/api/v1/users", json={"name": "Late arrival"})).json()["id"]
    async with app.state.session_factory() as writer, writer.begin():
        await require_group(writer, group_id, lock=True)
        writer.add(GroupMember(group_id=group_id, user_id=newcomer))
        await writer.flush()
        task = asyncio.create_task(expense(client, group, amount="100"))
        await asyncio.sleep(0.1)
        assert not task.done()
    response = await task
    assert response.status_code == 201, response.text
    assert len(response.json()["splits"]) == 4
    assert all(split["amount"] == "25.00" for split in response.json()["splits"])


async def test_balances_remain_scoped_to_group(client, group):
    group_id, users = group
    await expense(client, group)
    another = (await client.post("/api/v1/groups", json={"name": "Separate trip"})).json()["id"]
    for user_id in users:
        await client.post(f"/api/v1/groups/{another}/members", json={"user_id": user_id})
    assert (await expense(client, (another, users), payer=users[1])).status_code == 201
    original = await get_balances(client, group_id)
    separate = await get_balances(client, another)
    assert original["members"][0]["net_amount"] == "800.00"
    assert separate["members"][0]["net_amount"] == "-400.00"
