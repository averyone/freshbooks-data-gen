"""Verification pass over the generated FreshBooks CSVs.

Checks:
  - Cross-references: every invoice client/item exists; every expense vendor exists.
  - Invoice math: line totals sum to subtotal; subtotal + tax == invoice_total.
  - Reports: date range, status mix, monthly seasonality, totals, top vendors.

Run from anywhere:
    python3 scripts/verify.py
"""

import csv
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = (SCRIPT_DIR / ".." / "data").resolve()


def load(name):
    with open(DATA_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    clients  = load("clients.csv")
    items    = load("items.csv")
    vendors  = load("vendors.csv")
    invoices = load("invoices.csv")
    expenses = load("expenses.csv")

    client_labels = set()
    for c in clients:
        label = c["organization"] if c["organization"] else f'{c["first_name"]} {c["last_name"]}'
        client_labels.add(label)

    item_names = {i["name"] for i in items}
    vendor_names = {v["name"] for v in vendors}

    errors = []
    bad_invoice_clients = [r["invoice_number"] for r in invoices if r["client_name"] not in client_labels]
    bad_invoice_items   = [r["invoice_number"] for r in invoices if r["item_name"] not in item_names]
    bad_expense_vendors = [r["expense_id"] for r in expenses if r["vendor"] not in vendor_names]
    if bad_invoice_clients:
        errors.append(f"Invoices with missing client: {len(bad_invoice_clients)}")
    if bad_invoice_items:
        errors.append(f"Invoices with missing item: {len(bad_invoice_items)}")
    if bad_expense_vendors:
        errors.append(f"Expenses with missing vendor: {len(bad_expense_vendors)}")

    math_errors = 0
    by_invoice = defaultdict(list)
    for row in invoices:
        by_invoice[row["invoice_number"]].append(row)
    for inv_num, rows in by_invoice.items():
        sum_lines = round(sum(float(r["line_total"]) for r in rows), 2)
        header = next(r for r in rows if r["subtotal"])
        subtotal = float(header["subtotal"])
        tax = float(header["tax_amount"] or 0)
        total = float(header["invoice_total"])
        if abs(sum_lines - subtotal) > 0.02 or abs(round(subtotal + tax, 2) - total) > 0.02:
            math_errors += 1

    all_dates = [date.fromisoformat(r["create_date"]) for r in invoices] + \
                [date.fromisoformat(r["date"]) for r in expenses]
    print(f"Date range: {min(all_dates)}  ->  {max(all_dates)}")

    status_counter = Counter()
    for inv_num, rows in by_invoice.items():
        header = next(r for r in rows if r["status"])
        status_counter[header["status"]] += 1
    n_inv = len(by_invoice)
    print("\nInvoice status mix:")
    for status, count in status_counter.most_common():
        print(f"  {status:<8} {count:>3}  ({count/n_inv:.0%})")

    by_month = Counter()
    for inv_num, rows in by_invoice.items():
        d = date.fromisoformat(rows[0]["create_date"])
        by_month[(d.year, d.month)] += 1
    print("\nInvoices per month:")
    for ym in sorted(by_month):
        bar = "#" * by_month[ym]
        print(f"  {ym[0]}-{ym[1]:02d}  {by_month[ym]:>3}  {bar}")

    total_revenue = sum(float(rows[0]["invoice_total"]) for rows in by_invoice.values())
    total_paid    = sum(float(rows[0]["amount_paid"])   for rows in by_invoice.values())
    total_expense = sum(float(r["amount"]) for r in expenses)
    print(f"\nGross billed:  ${total_revenue:>12,.2f}")
    print(f"Collected:     ${total_paid:>12,.2f}")
    print(f"Outstanding:   ${total_revenue - total_paid:>12,.2f}")
    print(f"Expenses:      ${total_expense:>12,.2f}")
    print(f"Net (rough):   ${total_paid - total_expense:>12,.2f}")

    exp_by_vendor = Counter()
    for r in expenses:
        exp_by_vendor[r["vendor"]] += float(r["amount"])
    print("\nTop 5 vendors by spend:")
    for v, amt in exp_by_vendor.most_common(5):
        print(f"  {v:<32}  ${amt:>12,.2f}")

    print(f"\nMath errors:        {math_errors}")
    print(f"Reference errors:   {len(errors)}")
    for e in errors:
        print(f"  - {e}")
    print("\nOK" if not errors and math_errors == 0 else "\nFAIL")


if __name__ == "__main__":
    main()
