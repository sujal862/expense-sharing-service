import os
import subprocess
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.config import Settings, get_settings
from app.main import create_app
from app.models.entities import Expense, ExpenseSplit, Group, GroupMember, Settlement, User
from scripts.test_safety import validate_test_url


@pytest.fixture(scope="session")
def test_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL explicitly to run MySQL integration tests")
    validate_test_url(url, get_settings().database_url)
    # Migrate only after the safety guard; never derive the test URL from the app URL.
    env = dict(os.environ, DATABASE_URL=url)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
    return url


@pytest_asyncio.fixture
async def app(test_url):
    application = create_app(Settings(database_url=test_url))
    async with application.router.lifespan_context(application):
        async with application.state.session_factory() as session, session.begin():
            for model in (Settlement, ExpenseSplit, Expense, GroupMember, Group, User):
                await session.execute(delete(model))
        yield application


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def group(client):
    users = []
    for name in ("Mohit", "Rahul", "Ankit"):
        response = await client.post("/api/v1/users", json={"name": name})
        assert response.status_code == 201, response.text
        users.append(response.json()["id"])
    response = await client.post("/api/v1/groups", json={"name": "Goa Trip"})
    group_id = response.json()["id"]
    for user_id in users:
        response = await client.post(
            f"/api/v1/groups/{group_id}/members", json={"user_id": user_id}
        )
        assert response.status_code == 201, response.text
    return group_id, users
