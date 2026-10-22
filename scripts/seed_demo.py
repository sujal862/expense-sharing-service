"""Add synthetic demo records through the public API. Each run creates new groups."""

import argparse
import asyncio
import json

import httpx


async def seed(base_url: str):
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=30) as client:

        async def post(path, body):
            response = await client.post(f"/api/v1{path}", json=body)
            response.raise_for_status()
            return response.json()

        async def get(path):
            response = await client.get(f"/api/v1{path}")
            response.raise_for_status()
            return response.json()

        users = {}
        for name in ("Mohit", "Rahul", "Ankit", "Priya"):
            users[name] = (await post("/users", {"name": name}))["id"]
        group = await post("/groups", {"name": "Goa Trip Demo"})
        group_id = group["id"]
        path = f"/groups/{group_id}"
        for name in ("Mohit", "Rahul", "Ankit"):
            await post(f"{path}/members", {"user_id": users[name]})
        dinner = await post(
            "/expenses",
            {
                "group_id": group_id,
                "paid_by": users["Mohit"],
                "amount": "1200.00",
                "description": "Dinner before Priya joined",
            },
        )
        await post(
            "/expenses",
            {
                "group_id": group_id,
                "paid_by": users["Rahul"],
                "amount": "600.00",
                "description": "Taxi before Priya joined",
            },
        )
        await post(f"{path}/members", {"user_id": users["Priya"]})
        await post(
            "/expenses",
            {
                "group_id": group_id,
                "paid_by": users["Ankit"],
                "amount": "300.00",
                "description": "Activities, custom allocation",
                "split_type": "custom",
                "splits": [
                    {"user_id": users["Rahul"], "amount": "100.00"},
                    {"user_id": users["Priya"], "amount": "200.00"},
                ],
            },
        )
        history = await get(f"{path}/expenses")
        assert history["items"][0]["splits"] == dinner["splits"]
        before = await get(f"{path}/balances")
        suggestions = await get(f"{path}/settlement-suggestions")
        # Largest debtor Ankit pays Mohit 300.00; record only half, leaving the rest advisory.
        first = suggestions["transfers"][0]
        payment = await post(
            f"{path}/settlements",
            {
                "paid_by": first["debtor"]["user_id"],
                "paid_to": first["creditor"]["user_id"],
                "amount": "150.00",
            },
        )

        # A second group makes a transitive route explicit: Mohit -> Rahul -> Ankit.
        chain = await post("/groups", {"name": "Simplified Route Demo"})
        chain_path = f"/groups/{chain['id']}"
        for name in ("Mohit", "Rahul", "Ankit"):
            await post(f"{chain_path}/members", {"user_id": users[name]})
        for payer, participant in (("Rahul", "Mohit"), ("Ankit", "Rahul")):
            await post(
                "/expenses",
                {
                    "group_id": chain["id"],
                    "paid_by": users[payer],
                    "amount": "500.00",
                    "description": f"{payer} paid for {participant}",
                    "split_type": "custom",
                    "splits": [{"user_id": users[participant], "amount": "500.00"}],
                },
            )
        chain_before = await get(f"{chain_path}/settlement-suggestions")
        assert chain_before["payment_count"] == 1
        await post(
            f"{chain_path}/settlements",
            {
                "paid_by": users["Mohit"],
                "paid_to": users["Ankit"],
                "amount": "500.00",
            },
        )
        assert (await get(f"{chain_path}/settlement-suggestions"))["payment_count"] == 0
        print(
            json.dumps(
                {
                    "users": users,
                    "trip_group_id": group_id,
                    "chain_group_id": chain["id"],
                    "trip_balances_before_partial_payment": before,
                    "trip_suggestions_before_payment": suggestions,
                    "recorded_partial_payment": payment,
                    "trip_balances_after_partial_payment": await get(f"{path}/balances"),
                    "chain_simplified_suggestion_before_full_payment": chain_before,
                    "chain_balances_after_full_payment": await get(f"{chain_path}/balances"),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    asyncio.run(seed(parser.parse_args().base_url))
