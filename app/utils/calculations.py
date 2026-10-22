import heapq
from collections import defaultdict


def equal_split(amount: int, user_ids: list[int]) -> dict[int, int]:
    members = sorted(user_ids)
    if amount <= 0 or not members or len(set(members)) != len(members):
        raise ValueError("Positive amount and distinct participants are required")
    base, remainder = divmod(amount, len(members))
    return {
        user_id: base + (1 if index < remainder else 0) for index, user_id in enumerate(members)
    }


def custom_split(amount: int, shares: list[tuple[int, int]]) -> dict[int, int]:
    result = dict(shares)
    if len(result) != len(shares):
        raise ValueError("Duplicate participant IDs")
    if amount <= 0 or not shares or any(share < 0 for _, share in shares):
        raise ValueError("Shares must be nonnegative with at least one positive share")
    if sum(result.values()) != amount:
        raise ValueError("Custom shares must sum exactly to the expense amount")
    return result


def calculate_balances(
    members: list[int],
    obligations: list[tuple[int, int, int]],
    settlements: list[tuple[int, int, int]],
) -> tuple[dict[int, int], list[tuple[int, int, int]]]:
    """Obligations: (participant, payer, share); settlements: (sender, recipient, amount)."""
    net = dict.fromkeys(members, 0)
    pairs: dict[tuple[int, int], int] = defaultdict(int)

    def add_debt(debtor: int, creditor: int, amount: int) -> None:
        if debtor == creditor:
            return
        net[debtor] -= amount
        net[creditor] += amount
        low, high = sorted((debtor, creditor))
        pairs[low, high] += amount if debtor == low else -amount

    for participant, payer, share in obligations:
        add_debt(participant, payer, share)
    for sender, recipient, amount in settlements:
        add_debt(recipient, sender, amount)
    pairwise = []
    for (low, high), amount in sorted(pairs.items()):
        if amount > 0:
            pairwise.append((low, high, amount))
        elif amount < 0:
            pairwise.append((high, low, -amount))
    return net, sorted(pairwise)


def suggest_settlements(net: dict[int, int]) -> list[tuple[int, int, int]]:
    if sum(net.values()) != 0:
        raise ValueError("Net balances must sum to zero")
    debtors = [(amount, user_id) for user_id, amount in net.items() if amount < 0]
    creditors = [(-amount, user_id) for user_id, amount in net.items() if amount > 0]
    heapq.heapify(debtors)
    heapq.heapify(creditors)
    transfers = []
    while debtors and creditors:
        debt, debtor = heapq.heappop(debtors)
        credit, creditor = heapq.heappop(creditors)
        amount = min(-debt, -credit)
        transfers.append((debtor, creditor, amount))
        if debt + amount < 0:
            heapq.heappush(debtors, (debt + amount, debtor))
        if credit + amount < 0:
            heapq.heappush(creditors, (credit + amount, creditor))
    return transfers
