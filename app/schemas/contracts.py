from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from app.utils.money import MONEY_PATTERN, parse_money

UserId = Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Money = Annotated[
    Decimal,
    BeforeValidator(parse_money),
    WithJsonSchema(
        {
            "type": "string",
            "pattern": MONEY_PATTERN,
            "examples": ["100.50"],
            "description": "INR decimal string, at most 2 decimal places; maximum 1000000000.00",
        }
    ),
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class UserCreate(Contract):
    name: Name = Field(examples=["Mohit"])


class GroupCreate(Contract):
    name: Name = Field(examples=["Goa Trip"])


class Timestamped(Contract):
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class UserOut(Timestamped):
    id: int
    name: str


class GroupOut(Timestamped):
    id: int
    name: str


class MemberCreate(Contract):
    user_id: UserId


class MemberOut(Contract):
    user_id: int
    name: str
    joined_at: datetime

    @field_validator("joined_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class SplitCreate(Contract):
    user_id: UserId
    amount: Money


class ExpenseCreate(Contract):
    group_id: UserId
    paid_by: UserId
    amount: Money
    description: Description
    split_type: Literal["equal", "custom"] = "equal"
    splits: list[SplitCreate] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def split_contract(self):
        if self.amount <= 0:
            raise ValueError("Expense amount must be positive")
        if self.split_type == "equal" and "splits" in self.model_fields_set:
            raise ValueError("Equal expenses must omit splits")
        if self.split_type == "custom" and not self.splits:
            raise ValueError("Custom expenses require splits")
        return self


class SplitOut(Contract):
    user_id: int
    amount: str


class ExpenseOut(Timestamped):
    id: int
    group_id: int
    paid_by: int
    amount: str
    currency: Literal["INR"] = "INR"
    description: str
    split_type: Literal["equal", "custom"]
    splits: list[SplitOut]


class SettlementCreate(Contract):
    paid_by: UserId
    paid_to: UserId
    amount: Money

    @model_validator(mode="after")
    def valid_payment(self):
        if self.amount <= 0:
            raise ValueError("Settlement amount must be positive")
        if self.paid_by == self.paid_to:
            raise ValueError("Sender and recipient must differ")
        return self


class SettlementOut(Timestamped):
    id: int
    group_id: int
    paid_by: int
    paid_to: int
    amount: str
    currency: Literal["INR"] = "INR"


class Person(Contract):
    user_id: int
    name: str


class PairwiseBalance(Contract):
    debtor: Person
    creditor: Person
    amount: str


class NetBalance(Person):
    net_amount: str
    status: Literal["should_receive", "should_pay", "settled"]


class BalancesOut(Contract):
    group_id: int
    currency: Literal["INR"] = "INR"
    pairwise: list[PairwiseBalance]
    members: list[NetBalance]


class SuggestionsOut(Contract):
    group_id: int
    currency: Literal["INR"] = "INR"
    transfers: list[PairwiseBalance]
    payment_count: int
    explanation: str


T = TypeVar("T")


class Page(Contract, Generic[T]):
    items: list[T]
    limit: int
    offset: int
    has_more: bool


class ErrorDetail(Contract):
    code: str
    message: str
    details: list[dict] | None = None


class ErrorOut(Contract):
    error: ErrorDetail


class HealthOut(Contract):
    status: str
