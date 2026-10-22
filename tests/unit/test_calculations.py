import random
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.contracts import ExpenseCreate, SettlementCreate, UserCreate
from app.utils.calculations import (
    calculate_balances,
    custom_split,
    equal_split,
    suggest_settlements,
)
from app.utils.money import format_money, parse_money, to_paise
from scripts.test_safety import validate_test_url


def test_equal_and_remainder_allocation():
    assert equal_split(120000, [1, 2, 3]) == {1: 40000, 2: 40000, 3: 40000}
    assert equal_split(10000, [3, 1, 2]) == {1: 3334, 2: 3333, 3: 3333}
    assert equal_split(1, [2, 1, 3]) == {1: 1, 2: 0, 3: 0}
    assert equal_split(19, [4]) == {4: 19}


@pytest.mark.parametrize("amount,members", [(0, [1]), (10, []), (10, [1, 1])])
def test_invalid_equal_split(amount, members):
    with pytest.raises(ValueError):
        equal_split(amount, members)


def test_custom_split():
    assert custom_split(100, [(1, 20), (2, 80), (3, 0)]) == {1: 20, 2: 80, 3: 0}


@pytest.mark.parametrize(
    "shares", [[], [(1, 0)], [(1, -1), (2, 101)], [(1, 50), (1, 50)], [(1, 99)]]
)
def test_invalid_custom_splits(shares):
    with pytest.raises(ValueError):
        custom_split(100, shares)


def test_pairwise_netting_self_shares_and_net_formula():
    net, pairs = calculate_balances(
        [1, 2, 3], [(1, 1, 100), (2, 1, 500), (1, 2, 200), (3, 2, 100)], [(2, 1, 50)]
    )
    assert net == {1: 250, 2: -150, 3: -100}
    assert pairs == [(2, 1, 250), (3, 2, 100)]


def test_simplified_route_can_leave_zero_net_pairwise_cycle():
    net, pairs = calculate_balances([1, 2, 3], [(1, 2, 500), (2, 3, 500)], [(1, 3, 500)])
    assert net == {1: 0, 2: 0, 3: 0}
    assert len(pairs) == 3
    assert suggest_settlements(net) == []


def test_largest_first_and_tie_breaking():
    assert suggest_settlements({4: 100, 3: 100, 2: -100, 1: -100}) == [(1, 3, 100), (2, 4, 100)]
    assert suggest_settlements({1: -80, 2: -120, 3: 150, 4: 50}) == [
        (2, 3, 120),
        (1, 4, 50),
        (1, 3, 30),
    ]


def test_greedy_is_not_globally_optimal():
    # Four payments could group (800+700) and (600+500); largest-first needs five.
    assert len(suggest_settlements({1: -800, 2: -700, 3: -600, 4: -500, 5: 1500, 6: 1100})) == 5


def test_reject_unbalanced_suggestion_input():
    with pytest.raises(ValueError):
        suggest_settlements({1: -100, 2: 99})


def test_randomized_financial_invariants():
    rng = random.Random(42)
    for _ in range(250):
        members = list(range(1, rng.randint(2, 30)))
        obligations = []
        paid = dict.fromkeys(members, 0)
        allocated = dict.fromkeys(members, 0)
        for _ in range(20):
            payer = rng.choice(members)
            amount = rng.randint(1, 1000000)
            shares = equal_split(amount, members)
            assert sum(shares.values()) == amount
            paid[payer] += amount
            for participant, share in shares.items():
                allocated[participant] += share
                obligations.append((participant, payer, share))
        net, _ = calculate_balances(members, obligations, [])
        assert net == {user: paid[user] - allocated[user] for user in members}
        assert sum(net.values()) == 0
        transfers = suggest_settlements(net)
        assert len(transfers) <= len(members) - 1
        for sender, recipient, amount in transfers:
            assert amount > 0 and sender != recipient
            net[sender] += amount
            net[recipient] -= amount
        assert all(value == 0 for value in net.values())


@pytest.mark.parametrize("value", ["0", "0.01", "100.50", "1000000000.00"])
def test_money_round_trip(value):
    amount = parse_money(value)
    assert Decimal(format_money(to_paise(amount))) == Decimal(value)


@pytest.mark.parametrize(
    "value",
    [
        100.5,
        100,
        True,
        None,
        "-1",
        "1.001",
        "1.000",
        "NaN",
        "Infinity",
        "1e2",
        " 1.00",
        "1000000000.01",
    ],
)
def test_reject_invalid_money(value):
    with pytest.raises(ValueError):
        parse_money(value)


def test_schema_validation():
    with pytest.raises(ValidationError):
        UserCreate(name="   ")
    base = {"group_id": 1, "paid_by": 1, "description": "Dinner", "amount": "100.00"}
    for extra in ({"splits": []}, {"splits": None}, {"split_type": "custom"}, {"amount": "0"}):
        with pytest.raises(ValidationError):
            ExpenseCreate(**(base | extra))
    with pytest.raises(ValidationError):
        SettlementCreate(paid_by=1, paid_to=1, amount="1")


@pytest.mark.parametrize(
    "test_url",
    [
        "mysql+asyncmy://expense:demo@localhost/expense_sharing",
        "mysql+asyncmy://root:demo@localhost/expense_sharing_test",
        "sqlite+aiosqlite:///expense_sharing_test",
    ],
)
def test_cleanup_safety_guard(test_url):
    with pytest.raises(ValueError):
        validate_test_url(test_url, "mysql+asyncmy://expense:demo@localhost/expense_sharing")


def test_guard_accepts_only_explicit_test_database():
    url = "mysql+asyncmy://expense_test:demo@localhost/expense_sharing_test"
    assert validate_test_url(url, "mysql+asyncmy://expense:demo@localhost/expense_sharing") == url
    with pytest.raises(ValueError):
        validate_test_url(url, url)
