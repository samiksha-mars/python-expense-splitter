# Python Expense Splitter

Reads a CSV of shared expenses, works out who owes what, and suggests the fewest
transfers needed to settle up. Uses only the Python standard library.

## Features

- Simple CSV input: who paid, how much, and who shared the cost
- Exact money handling in cents (leftover cents from uneven splits go to the first participants listed)
- Per-person balances (positive = is owed money, negative = owes money)
- Minimal settle-up: finds the smallest number of transfers by splitting people into as many
  independent zero-sum groups as possible (falls back to a greedy plan for very large groups)
- Helpful errors for malformed rows, including the line number

## Input format

```csv
payer,amount,participants,description
alice,120.00,alice;bob;carol;dave,Groceries
bob,60.00,alice;bob;carol,Taxi
```

- `participants` is a semicolon-separated list; the payer only shares the cost if listed
- `description` is optional

## Usage

```bash
python3 splitter.py sample.csv
```

Output for the bundled `sample.csv`:

```
Total spent: 455.50 across 5 expense(s)

Balances:
  alice  +50.00
  bob    -55.00
  carol  -92.25
  dave   +97.25

Settle up:
  bob pays alice 50.00
  bob pays dave 5.00
  carol pays dave 92.25
```

## Tests

```bash
python3 -m unittest
```
