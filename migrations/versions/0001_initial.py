"""Initial immutable expense and settlement ledger.

Revision ID: 0001
Revises: None
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        **OPTIONS,
    )
    op.create_table(
        "groups",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        **OPTIONS,
    )
    op.create_table(
        "group_members",
        sa.Column("group_id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("joined_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        **OPTIONS,
    )
    op.create_index("ix_group_members_user_id", "group_members", ["user_id"])
    op.create_table(
        "expenses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("paid_by", sa.BigInteger(), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("split_type", sa.String(10), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["paid_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["group_id", "paid_by"],
            ["group_members.group_id", "group_members.user_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount_paise > 0 AND amount_paise <= 100000000000", name="amount"),
        sa.CheckConstraint("split_type IN ('equal', 'custom')", name="split_type"),
        **OPTIONS,
    )
    op.create_index("ix_expenses_group_id_id", "expenses", ["group_id", "id"])
    op.create_index("ix_expenses_paid_by", "expenses", ["paid_by"])
    op.create_table(
        "expense_splits",
        sa.Column("expense_id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("share_paise", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("share_paise >= 0 AND share_paise <= 100000000000", name="share"),
        **OPTIONS,
    )
    op.create_index("ix_expense_splits_user_id", "expense_splits", ["user_id"])
    op.create_table(
        "settlements",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("paid_by", sa.BigInteger(), nullable=False),
        sa.Column("paid_to", sa.BigInteger(), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["paid_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["paid_to"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["group_id", "paid_by"],
            ["group_members.group_id", "group_members.user_id"],
            name="fk_settlements_sender_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["group_id", "paid_to"],
            ["group_members.group_id", "group_members.user_id"],
            name="fk_settlements_recipient_membership",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount_paise > 0 AND amount_paise <= 100000000000", name="amount"),
        sa.CheckConstraint("paid_by <> paid_to", name="different_users"),
        **OPTIONS,
    )
    op.create_index("ix_settlements_group_id_id", "settlements", ["group_id", "id"])
    op.create_index("ix_settlements_paid_by", "settlements", ["paid_by"])
    op.create_index("ix_settlements_paid_to", "settlements", ["paid_to"])


def downgrade():
    for table in ("settlements", "expense_splits", "expenses", "group_members", "groups", "users"):
        op.drop_table(table)
