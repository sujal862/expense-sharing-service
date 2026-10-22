from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.entities import Expense, ExpenseSplit, Group, GroupMember, Settlement, User
from app.schemas.contracts import ExpenseCreate, SettlementCreate
from app.utils.calculations import (
    calculate_balances,
    custom_split,
    equal_split,
    suggest_settlements,
)
from app.utils.money import format_money, to_paise


async def require_group(session: AsyncSession, group_id: int, *, lock: bool = False) -> Group:
    statement = select(Group).where(Group.id == group_id)
    if lock:
        statement = statement.with_for_update()
    group = await session.scalar(statement)
    if group is None:
        raise AppError(404, "group_not_found", "Group does not exist")
    return group


async def create_user(session: AsyncSession, name: str):
    async with session.begin():
        user = User(name=name)
        session.add(user)
        await session.flush()
    return user


async def create_group(session: AsyncSession, name: str):
    async with session.begin():
        group = Group(name=name)
        session.add(group)
        await session.flush()
    return group


async def add_member(session: AsyncSession, group_id: int, user_id: int):
    async with session.begin():
        await require_group(session, group_id, lock=True)
        user = await session.get(User, user_id)
        if user is None:
            raise AppError(404, "user_not_found", "User does not exist")
        if await session.get(GroupMember, (group_id, user_id)):
            raise AppError(409, "duplicate_membership", "User already belongs to this group")
        member = GroupMember(group_id=group_id, user_id=user_id)
        session.add(member)
        await session.flush()
        result = {"user_id": user_id, "name": user.name, "joined_at": member.joined_at}
    return result


async def list_members(session: AsyncSession, group_id: int, limit: int, offset: int):
    async with session.begin():
        await require_group(session, group_id)
        rows = (
            await session.execute(
                select(User.id, User.name, GroupMember.joined_at)
                .join(GroupMember, User.id == GroupMember.user_id)
                .where(GroupMember.group_id == group_id)
                .order_by(User.id)
                .limit(limit + 1)
                .offset(offset)
            )
        ).all()
        items = [dict(user_id=row.id, name=row.name, joined_at=row.joined_at) for row in rows]
    return page(items, limit, offset)


def page(items: list, limit: int, offset: int):
    return {
        "items": items[:limit],
        "limit": limit,
        "offset": offset,
        "has_more": len(items) > limit,
    }


async def list_entities(session: AsyncSession, model, limit: int, offset: int):
    async with session.begin():
        rows = list(
            await session.scalars(select(model).order_by(model.id).limit(limit + 1).offset(offset))
        )
    return page(rows, limit, offset)


def expense_out(expense: Expense, shares: list[tuple[int, int]]):
    return {
        "id": expense.id,
        "group_id": expense.group_id,
        "paid_by": expense.paid_by,
        "amount": format_money(expense.amount_paise),
        "description": expense.description,
        "split_type": expense.split_type,
        "created_at": expense.created_at,
        "splits": [
            {"user_id": user_id, "amount": format_money(share)} for user_id, share in sorted(shares)
        ],
    }


async def create_expense(session: AsyncSession, data: ExpenseCreate):
    async with session.begin():
        await require_group(session, data.group_id, lock=True)
        members = list(
            await session.scalars(
                select(GroupMember.user_id)
                .where(GroupMember.group_id == data.group_id)
                .order_by(GroupMember.user_id)
            )
        )
        if not members:
            raise AppError(422, "empty_group", "Group has no members")
        if data.paid_by not in members:
            raise AppError(422, "invalid_payer", "Payer must be an existing group member")
        amount = to_paise(data.amount)
        if data.split_type == "equal":
            shares = equal_split(amount, members)
        else:
            try:
                shares = custom_split(
                    amount, [(split.user_id, to_paise(split.amount)) for split in data.splits]
                )
            except ValueError as error:
                raise AppError(422, "invalid_splits", str(error)) from error
            if not set(shares).issubset(members):
                raise AppError(422, "invalid_participant", "All participants must be group members")
        expense = Expense(
            group_id=data.group_id,
            paid_by=data.paid_by,
            amount_paise=amount,
            description=data.description,
            split_type=data.split_type,
        )
        session.add(expense)
        await session.flush()
        session.add_all(
            [
                ExpenseSplit(expense_id=expense.id, user_id=user_id, share_paise=share)
                for user_id, share in shares.items()
            ]
        )
        await session.flush()
        result = expense_out(expense, list(shares.items()))
    return result


async def list_expenses(session: AsyncSession, group_id: int, limit: int, offset: int):
    async with session.begin():
        await require_group(session, group_id)
        expenses = list(
            await session.scalars(
                select(Expense)
                .where(Expense.group_id == group_id)
                .order_by(Expense.id)
                .limit(limit + 1)
                .offset(offset)
            )
        )
        shares = defaultdict(list)
        if expenses:
            rows = await session.execute(
                select(ExpenseSplit).where(ExpenseSplit.expense_id.in_([e.id for e in expenses]))
            )
            for split in rows.scalars():
                shares[split.expense_id].append((split.user_id, split.share_paise))
        results = [expense_out(expense, shares[expense.id]) for expense in expenses]
    return page(results, limit, offset)


async def load_balances(session: AsyncSession, group_id: int):
    """Caller owns the transaction. Three group-scoped queries, no N+1 reads."""
    rows = await session.execute(
        select(User.id, User.name)
        .join(GroupMember, User.id == GroupMember.user_id)
        .where(GroupMember.group_id == group_id)
        .order_by(User.id)
    )
    names = dict(rows.all())
    obligations = (
        await session.execute(
            select(ExpenseSplit.user_id, Expense.paid_by, ExpenseSplit.share_paise)
            .join(Expense, Expense.id == ExpenseSplit.expense_id)
            .where(Expense.group_id == group_id)
        )
    ).all()
    payments = (
        await session.execute(
            select(Settlement.paid_by, Settlement.paid_to, Settlement.amount_paise).where(
                Settlement.group_id == group_id
            )
        )
    ).all()
    net, pairwise = calculate_balances(list(names), obligations, payments)
    return names, net, pairwise


def transfers_out(transfers, names):
    return [
        {
            "debtor": {"user_id": debtor, "name": names[debtor]},
            "creditor": {"user_id": creditor, "name": names[creditor]},
            "amount": format_money(amount),
        }
        for debtor, creditor, amount in transfers
    ]


async def balances(session: AsyncSession, group_id: int):
    async with session.begin():
        await require_group(session, group_id)
        names, net, pairwise = await load_balances(session, group_id)
        result = {
            "group_id": group_id,
            "pairwise": transfers_out(pairwise, names),
            "members": [
                {
                    "user_id": user_id,
                    "name": names[user_id],
                    "net_amount": format_money(amount),
                    "status": "should_receive"
                    if amount > 0
                    else "should_pay"
                    if amount < 0
                    else "settled",
                }
                for user_id, amount in net.items()
            ],
        }
    return result


async def suggestions(session: AsyncSession, group_id: int):
    async with session.begin():
        await require_group(session, group_id)
        names, net, _ = await load_balances(session, group_id)
        transfers = suggest_settlements(net)
        result = {
            "group_id": group_id,
            "transfers": transfers_out(transfers, names),
            "payment_count": len(transfers),
            "explanation": (
                "Advisory plan matching the largest debtor and creditor, "
                "with user-ID tie-breaking. "
                "Preserves net positions and may change who pays whom. Does not guarantee the "
                "minimum number of payments. No payments have been recorded or executed."
            ),
        }
    return result


def settlement_out(payment: Settlement):
    return {
        "id": payment.id,
        "group_id": payment.group_id,
        "paid_by": payment.paid_by,
        "paid_to": payment.paid_to,
        "amount": format_money(payment.amount_paise),
        "created_at": payment.created_at,
    }


async def record_settlement(session: AsyncSession, group_id: int, data: SettlementCreate):
    async with session.begin():
        # The locking read precedes all consistent reads, so a waiter gets a fresh snapshot.
        await require_group(session, group_id, lock=True)
        names, net, _ = await load_balances(session, group_id)
        if data.paid_by not in names or data.paid_to not in names:
            raise AppError(422, "invalid_member", "Sender and recipient must be group members")
        amount = to_paise(data.amount)
        if net[data.paid_by] >= 0 or net[data.paid_to] <= 0:
            raise AppError(409, "invalid_position", "Sender must owe and recipient must be owed")
        if amount > min(-net[data.paid_by], net[data.paid_to]):
            raise AppError(409, "excess_settlement", "Payment exceeds an outstanding net position")
        payment = Settlement(
            group_id=group_id, paid_by=data.paid_by, paid_to=data.paid_to, amount_paise=amount
        )
        session.add(payment)
        await session.flush()
        result = settlement_out(payment)
    return result


async def list_settlements(session: AsyncSession, group_id: int, limit: int, offset: int):
    async with session.begin():
        await require_group(session, group_id)
        rows = list(
            await session.scalars(
                select(Settlement)
                .where(Settlement.group_id == group_id)
                .order_by(Settlement.id)
                .limit(limit + 1)
                .offset(offset)
            )
        )
        results = [settlement_out(payment) for payment in rows]
    return page(results, limit, offset)
