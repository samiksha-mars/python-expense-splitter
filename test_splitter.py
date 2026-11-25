import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from splitter import (
    _greedy,
    compute_balances,
    format_cents,
    main,
    parse_amount,
    read_expenses,
    settle,
)


def parse(text):
    return read_expenses(io.StringIO(text))


def apply_transfers(balances, transfers):
    result = dict(balances)
    for debtor, creditor, cents in transfers:
        result[debtor] += cents
        result[creditor] -= cents
    return result


class ParseTest(unittest.TestCase):

    def test_parse_amount(self):
        self.assertEqual(parse_amount("12.5"), 1250)
        self.assertEqual(parse_amount(" 3 "), 300)
        self.assertEqual(parse_amount("0.005"), 1)

    def test_parse_amount_rejects_bad_values(self):
        for bad in ("abc", "0", "-5", "nan"):
            with self.assertRaises(ValueError):
                parse_amount(bad)

    def test_read_expenses(self):
        expenses = parse(
            "payer,amount,participants,description\n"
            "alice,30,alice; bob ;carol,Dinner\n"
        )
        self.assertEqual(len(expenses), 1)
        self.assertEqual(expenses[0].payer, "alice")
        self.assertEqual(expenses[0].amount, 3000)
        self.assertEqual(expenses[0].participants, ["alice", "bob", "carol"])
        self.assertEqual(expenses[0].description, "Dinner")

    def test_missing_column(self):
        with self.assertRaises(ValueError):
            parse("payer,amount\nalice,10\n")

    def test_bad_row_reports_line(self):
        with self.assertRaisesRegex(ValueError, "Line 3"):
            parse("payer,amount,participants\nalice,10,bob\nbob,oops,alice\n")

    def test_line_number_accounts_for_blank_lines(self):
        with self.assertRaisesRegex(ValueError, "Line 5"):
            parse("payer,amount,participants\n\nalice,10,bob\n\nbob,oops,alice\n")


class BalanceTest(unittest.TestCase):

    def test_even_split(self):
        expenses = parse("payer,amount,participants\nalice,30,alice;bob;carol\n")
        self.assertEqual(compute_balances(expenses), {"alice": 2000, "bob": -1000, "carol": -1000})

    def test_leftover_cents_go_to_first_participants(self):
        expenses = parse("payer,amount,participants\nalice,10,bob;carol;dave\n")
        balances = compute_balances(expenses)
        self.assertEqual(balances["bob"], -334)
        self.assertEqual(balances["carol"], -333)
        self.assertEqual(sum(balances.values()), 0)

    def test_payer_not_participating(self):
        expenses = parse("payer,amount,participants\nalice,20,bob\n")
        self.assertEqual(compute_balances(expenses), {"alice": 2000, "bob": -2000})


class SettleTest(unittest.TestCase):

    def test_settles_all_balances(self):
        balances = {"alice": 5000, "bob": -5500, "carol": -9225, "dave": 9725}
        transfers = settle(balances)
        self.assertTrue(all(v == 0 for v in apply_transfers(balances, transfers).values()))
        self.assertEqual(len(transfers), 3)

    def test_even_balances_need_no_transfers(self):
        self.assertEqual(settle({"alice": 0, "bob": 0}), [])

    def test_beats_greedy(self):
        # Largest-first greedy needs 4 transfers here; splitting into the
        # zero-sum groups {c, d} and {a, b, e} needs only 3.
        balances = {"a": 600, "b": 300, "c": -700, "d": 700, "e": -900}
        self.assertEqual(len(_greedy(balances)), 4)
        transfers = settle(balances)
        self.assertEqual(len(transfers), 3)
        self.assertIn(("c", "d", 700), transfers)
        self.assertTrue(all(v == 0 for v in apply_transfers(balances, transfers).values()))

    def test_unbalanced_input_rejected(self):
        with self.assertRaises(ValueError):
            settle({"alice": 100, "bob": -50})


class FormatTest(unittest.TestCase):

    def test_format_cents(self):
        self.assertEqual(format_cents(12345), "123.45")
        self.assertEqual(format_cents(5), "0.05")
        self.assertEqual(format_cents(-925), "-9.25")


class MainTest(unittest.TestCase):

    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_bundled_sample(self):
        sample = Path(__file__).with_name("sample.csv")
        code, out, _ = self.run_main([str(sample)])
        self.assertEqual(code, 0)
        self.assertIn("Total spent: 455.50", out)
        self.assertIn("carol pays dave 92.25", out)

    def test_file_with_byte_order_mark(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "excel.csv"
            path.write_bytes(b"\xef\xbb\xbfpayer,amount,participants\nalice,10,bob\n")
            code, out, err = self.run_main([str(path)])
        self.assertEqual(code, 0, err)
        self.assertIn("bob pays alice 10.00", out)

    def test_bad_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("who,what\nx,y\n")
            code, _, err = self.run_main([str(path)])
        self.assertEqual(code, 1)
        self.assertIn("missing column", err)


if __name__ == "__main__":
    unittest.main()
