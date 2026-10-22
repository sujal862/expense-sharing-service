from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def make_engine(url: str):
    return create_async_engine(
        url,
        pool_pre_ping=True,
        isolation_level="REPEATABLE READ",
        connect_args={"init_command": "SET time_zone = '+00:00'", "charset": "utf8mb4"},
    )


def make_session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session
