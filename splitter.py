#!/usr/bin/env python3
"""Split shared expenses and work out the fewest transfers needed to settle up."""

import argparse
import csv
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# Above this many people with a non-zero balance the exact search gets slow
# (it is exponential), so we fall back to a greedy settlement instead.
EXACT_LIMIT = 15


@dataclass
class Expense:
    payer: str
    amount: int  # in cents
    participants: list
    description: str = ""


def parse_amount(text):
    """Turn a string like "12.5" into an integer number of cents."""
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        raise ValueError(f"Invalid amount: {text!r}") from None
    if not value.is_finite() or value <= 0:
        raise ValueError(f"Amount must be a positive number: {text!r}")
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def read_expenses(lines):
    """Parse expenses from CSV lines with columns payer, amount, participants[, description].

    Participants are separated by semicolons, e.g. "alice;bob;carol".
    """
    reader = csv.DictReader(lines)
    missing = {"payer", "amount", "participants"} - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"CSV is missing column(s): {', '.join(sorted(missing))}")

    expenses = []
    for line_no, row in enumerate(reader, start=2):
        payer = (row["payer"] or "").strip()
        participants = [p.strip() for p in (row["participants"] or "").split(";") if p.strip()]
        if not payer or not participants:
            raise ValueError(f"Line {line_no}: payer and participants are required")
        try:
            amount = parse_amount(row["amount"] or "")
        except ValueError as exc:
            raise ValueError(f"Line {line_no}: {exc}") from None
        description = (row.get("description") or "").strip()
        expenses.append(Expense(payer, amount, participants, description))
    return expenses


def compute_balances(expenses):
    """Return {name: cents}. Positive means the person is owed money.

    Each expense is split evenly; leftover cents go to the first participants listed.
    """
    balances = {}
    for expense in expenses:
        balances[expense.payer] = balances.get(expense.payer, 0) + expense.amount
        share, remainder = divmod(expense.amount, len(expense.participants))
        for index, person in enumerate(expense.participants):
            owed = share + (1 if index < remainder else 0)
            balances[person] = balances.get(person, 0) - owed
    return balances


def _greedy(balances):
    """Repeatedly pay the largest creditor from the largest debtor."""
    debtors = {name: -amount for name, amount in balances.items() if amount < 0}
    creditors = {name: amount for name, amount in balances.items() if amount > 0}
    transfers = []
    while debtors and creditors:
        debtor = min(debtors, key=lambda name: (-debtors[name], name))
        creditor = min(creditors, key=lambda name: (-creditors[name], name))
        amount = min(debtors[debtor], creditors[creditor])
        transfers.append((debtor, creditor, amount))
        for side, name in ((debtors, debtor), (creditors, creditor)):
            side[name] -= amount
            if side[name] == 0:
                del side[name]
    return transfers


def _zero_sum_groups(names, amounts):
    """Partition people into the largest possible number of zero-sum groups.

    Settling a group of k people needs at least k - 1 transfers, so maximizing
    the number of groups minimizes the total number of transfers.
    """
    n = len(names)
    full = (1 << n) - 1
    sums = [0] * (full + 1)
    best = [0] * (full + 1)
    for mask in range(1, full + 1):
        low = mask & -mask
        sums[mask] = sums[mask ^ low] + amounts[low.bit_length() - 1]
        best[mask] = max(best[mask ^ (1 << i)] for i in range(n) if mask >> i & 1)
        if sums[mask] == 0:
            best[mask] += 1

    # Walk back down from the full set; each zero-sum mask on the way starts a group.
    groups, boundary, mask = [], full, full
    while mask:
        target = best[mask] - (1 if sums[mask] == 0 else 0)
        i = next(i for i in range(n) if mask >> i & 1 and best[mask ^ (1 << i)] == target)
        mask ^= 1 << i
        if mask == 0 or sums[mask] == 0:
            groups.append([names[j] for j in range(n) if (boundary ^ mask) >> j & 1])
            boundary = mask
    return groups


def settle(balances):
    """Return the fewest (debtor, creditor, cents) transfers that zero every balance."""
    if sum(balances.values()) != 0:
        raise ValueError("Balances do not sum to zero")
    nonzero = {name: amount for name, amount in sorted(balances.items()) if amount}
    if len(nonzero) > EXACT_LIMIT:
        return sorted(_greedy(nonzero))

    names = list(nonzero)
    transfers = []
    for group in _zero_sum_groups(names, [nonzero[name] for name in names]):
        transfers.extend(_greedy({name: nonzero[name] for name in group}))
    return sorted(transfers)


def format_cents(cents):
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def report(expenses):
    """Build the text summary printed by the CLI."""
    balances = compute_balances(expenses)
    total = sum(expense.amount for expense in expenses)
    width = max(len(name) for name in balances)
    lines = [f"Total spent: {format_cents(total)} across {len(expenses)} expense(s)", "", "Balances:"]
    for name, cents in sorted(balances.items()):
        sign = "+" if cents > 0 else ""
        lines.append(f"  {name:<{width}}  {sign}{format_cents(cents)}")
    lines += ["", "Settle up:"]
    transfers = settle(balances)
    if not transfers:
        lines.append("  Everyone is even.")
    for debtor, creditor, cents in transfers:
        lines.append(f"  {debtor} pays {creditor} {format_cents(cents)}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Split shared expenses from a CSV file and show who should pay whom."
    )
    parser.add_argument(
        "csv_file",
        help="CSV with columns payer, amount, participants (semicolon-separated), description",
    )
    args = parser.parse_args(argv)

    try:
        with open(args.csv_file, newline="", encoding="utf-8") as handle:
            expenses = read_expenses(handle)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not expenses:
        print("No expenses found.")
        return 0

    print(report(expenses))
    return 0


if __name__ == "__main__":
    sys.exit(main())
