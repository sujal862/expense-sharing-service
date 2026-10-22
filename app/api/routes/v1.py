from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.entities import Group, User
from app.schemas.contracts import (
    BalancesOut,
    ExpenseCreate,
    ExpenseOut,
    GroupCreate,
    GroupOut,
    MemberCreate,
    MemberOut,
    Page,
    SettlementCreate,
    SettlementOut,
    SuggestionsOut,
    UserCreate,
    UserId,
    UserOut,
)
from app.services import ledger

router = APIRouter(prefix="/api/v1")
Session = Annotated[AsyncSession, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.post("/users", response_model=UserOut, status_code=201, tags=["Users"])
async def create_user(data: UserCreate, session: Session):
    return await ledger.create_user(session, data.name)


@router.get("/users", response_model=Page[UserOut], tags=["Users"])
async def list_users(session: Session, limit: Limit = 20, offset: Offset = 0):
    return await ledger.list_entities(session, User, limit, offset)


@router.post("/groups", response_model=GroupOut, status_code=201, tags=["Groups"])
async def create_group(data: GroupCreate, session: Session):
    return await ledger.create_group(session, data.name)


@router.get("/groups", response_model=Page[GroupOut], tags=["Groups"])
async def list_groups(session: Session, limit: Limit = 20, offset: Offset = 0):
    return await ledger.list_entities(session, Group, limit, offset)


@router.post(
    "/groups/{group_id}/members", response_model=MemberOut, status_code=201, tags=["Groups"]
)
async def add_member(group_id: UserId, data: MemberCreate, session: Session):
    return await ledger.add_member(session, group_id, data.user_id)


@router.get("/groups/{group_id}/members", response_model=Page[MemberOut], tags=["Groups"])
async def list_members(group_id: UserId, session: Session, limit: Limit = 20, offset: Offset = 0):
    return await ledger.list_members(session, group_id, limit, offset)


@router.post("/expenses", response_model=ExpenseOut, status_code=201, tags=["Expenses"])
async def create_expense(data: ExpenseCreate, session: Session):
    """Save an expense and immutable shares. Money inputs must be decimal strings in INR."""
    return await ledger.create_expense(session, data)


@router.get("/groups/{group_id}/expenses", response_model=Page[ExpenseOut], tags=["Expenses"])
async def list_expenses(group_id: UserId, session: Session, limit: Limit = 20, offset: Offset = 0):
    return await ledger.list_expenses(session, group_id, limit, offset)


@router.get("/groups/{group_id}/balances", response_model=BalancesOut, tags=["Balances"])
async def balances(group_id: UserId, session: Session):
    """Group ledger: pairwise obligations and net positions. Positive net means should receive."""
    return await ledger.balances(session, group_id)


@router.post(
    "/groups/{group_id}/settlements",
    response_model=SettlementOut,
    status_code=201,
    tags=["Settlements"],
)
async def record_settlement(group_id: UserId, data: SettlementCreate, session: Session):
    """Record a payment already made. Validated against net positions; does not move money."""
    return await ledger.record_settlement(session, group_id, data)


@router.get(
    "/groups/{group_id}/settlements", response_model=Page[SettlementOut], tags=["Settlements"]
)
async def list_settlements(
    group_id: UserId, session: Session, limit: Limit = 20, offset: Offset = 0
):
    return await ledger.list_settlements(session, group_id, limit, offset)


@router.get(
    "/groups/{group_id}/settlement-suggestions",
    response_model=SuggestionsOut,
    tags=["Settlements"],
)
async def suggestions(group_id: UserId, session: Session):
    """Advisory greedy net settlement plan. Suggestions are never persisted as payments."""
    return await ledger.suggestions(session, group_id)
