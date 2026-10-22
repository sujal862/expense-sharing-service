import re
from decimal import Decimal

MAX_AMOUNT_PAISE = 100_000_000_000  # INR 1,000,000,000.00 per expense/payment/share.
MONEY_PATTERN = r"^[0-9]{1,10}(\.[0-9]{1,2})?$"


def parse_money(value: object) -> Decimal:
    # Strings avoid a JSON parser converting money through binary floating point.
    if not isinstance(value, str) or re.fullmatch(MONEY_PATTERN, value) is None:
        raise ValueError("Use an unsigned decimal string with at most two decimal places")
    amount = Decimal(value)
    if amount > Decimal(MAX_AMOUNT_PAISE) / 100:
        raise ValueError("Amount must not exceed INR 1000000000.00")
    return amount


def to_paise(amount: Decimal) -> int:
    return int(amount * 100)


def format_money(paise: int) -> str:
    sign = "-" if paise < 0 else ""
    whole, fraction = divmod(abs(paise), 100)
    return f"{sign}{whole}.{fraction:02d}"
