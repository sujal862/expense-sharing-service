from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utc_now

TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


class User(Base):
    __tablename__ = "users"
    __table_args__ = TABLE_OPTIONS
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utc_now)


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = TABLE_OPTIONS
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utc_now)


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (Index("ix_group_members_user_id", "user_id"), TABLE_OPTIONS)
    group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("groups.id", ondelete="RESTRICT"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    joined_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utc_now)


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["group_id", "paid_by"],
            ["group_members.group_id", "group_members.user_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount_paise > 0 AND amount_paise <= 100000000000", name="amount"),
        CheckConstraint("split_type IN ('equal', 'custom')", name="split_type"),
        Index("ix_expenses_group_id_id", "group_id", "id"),
        Index("ix_expenses_paid_by", "paid_by"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("groups.id", ondelete="RESTRICT"))
    paid_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    description: Mapped[str] = mapped_column(String(500))
    split_type: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utc_now)


class ExpenseSplit(Base):
    __tablename__ = "expense_splits"
    __table_args__ = (
        CheckConstraint("share_paise >= 0 AND share_paise <= 100000000000", name="share"),
        Index("ix_expense_splits_user_id", "user_id"),
        TABLE_OPTIONS,
    )
    expense_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("expenses.id", ondelete="RESTRICT"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    share_paise: Mapped[int] = mapped_column(BigInteger)


class Settlement(Base):
    __tablename__ = "settlements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["group_id", "paid_by"],
            ["group_members.group_id", "group_members.user_id"],
            name="fk_settlements_sender_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["group_id", "paid_to"],
            ["group_members.group_id", "group_members.user_id"],
            name="fk_settlements_recipient_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount_paise > 0 AND amount_paise <= 100000000000", name="amount"),
        CheckConstraint("paid_by <> paid_to", name="different_users"),
        Index("ix_settlements_group_id_id", "group_id", "id"),
        Index("ix_settlements_paid_by", "paid_by"),
        Index("ix_settlements_paid_to", "paid_to"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("groups.id", ondelete="RESTRICT"))
    paid_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"))
    paid_to: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utc_now)
