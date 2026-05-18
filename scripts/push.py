#!/usr/bin/env python3
"""
Push generated synthetic CSVs into a FreshBooks instance via the REST API.

Reads the CSVs in ../data/ and creates the equivalent records in
FreshBooks in the correct dependency order:

    items  ->  clients  ->  vendors  ->  invoices  ->  payments  ->  expenses

Auth
----
FreshBooks uses OAuth 2.0 bearer tokens. You need TWO pieces of info:

  1. An access token (Bearer). Easiest way to get one for personal seeding:
     https://www.freshbooks.com/api/get-authenticated-on-the-freshbooks-api
     The token is a long JWT. Set it in the FRESHBOOKS_TOKEN env var.

  2. Your account_id (sometimes shown as "Business Identifier" in the
     URL when you're logged in: app.freshbooks.com/#/<account_id>/...).
     If you don't pass FRESHBOOKS_ACCOUNT_ID, the script will call
     /auth/api/v1/users/me and pick the first business account it sees.

Optional env vars
-----------------
  FRESHBOOKS_DEFAULT_EXPENSE_CATEGORY_ID
      Numeric id of the FreshBooks expense category to use when the
      script can't find a category by name. Defaults to the first
      category returned by the API.

Resume / idempotency
--------------------
After every successful create, the script writes the local-csv-id ->
FreshBooks-id mapping to .push_state.json next to this script.
Re-running skips anything already in the state file, so it's safe
to re-run after a partial failure.

Dry run
-------
    python3 scripts/push.py --dry-run

prints the payloads without sending them.

Limit
-----
    python3 scripts/push.py --limit 5

stops after creating 5 of each resource. Handy for smoke-testing.

Scope
-----
Run a subset:

    python3 scripts/push.py --only clients,items
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Optional

import urllib.request
import urllib.error


# ------------------------------------------------------------------ #
# Configuration
# ------------------------------------------------------------------ #

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = (SCRIPT_DIR / ".." / "data").resolve()
STATE_PATH = SCRIPT_DIR / ".push_state.json"

FRESHBOOKS_BASE = "https://api.freshbooks.com"

CATEGORY_NAME_MAP = {
    "Shipping & Postage":        "Shipping/Postage",
    "Software & Subscriptions":  "Software/Tech",
    "Bank & Processor Fees":     "Bank Fees",
    "Advertising & Marketing":   "Advertising",
    "Cost of Goods Sold":        "Materials & Supplies",
    "Packaging & Supplies":      "Materials & Supplies",
    "Rent":                      "Rent",
    "Utilities":                 "Utilities",
    "Insurance":                 "Insurance",
    "Professional Services":     "Professional Services",
    "Taxes":                     "Taxes & Licenses",
}


# ------------------------------------------------------------------ #
# State
# ------------------------------------------------------------------ #

def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"items": {}, "clients": {}, "vendors": {}, "invoices": {}, "expenses": {}}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


# ------------------------------------------------------------------ #
# HTTP client
# ------------------------------------------------------------------ #

class FreshBooksClient:
    def __init__(self, token: str, account_id: str, dry_run: bool = False):
        self.token = token
        self.account_id = account_id
        self.dry_run = dry_run

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> Any:
        url = f"{FRESHBOOKS_BASE}{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Api-Version": "alpha",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        data = json.dumps(body).encode("utf-8") if body is not None else None

        if self.dry_run and method != "GET":
            print(f"[DRY] {method} {url}")
            print(f"[DRY] payload: {json.dumps(body, indent=2)[:800]}")
            mock_id = _next_dry_id()
            return {"response": {"result": {
                "item":    {"id": mock_id},
                "client":  {"id": mock_id},
                "vendor":  {"vendorid": mock_id},
                "invoice": {"id": mock_id},
                "expense": {"id": mock_id},
                "payment": {"id": mock_id},
            }}}

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        backoff = 1.0
        for _ in range(6):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                if e.code in (429, 502, 503, 504):
                    print(f"  retrying after {backoff:.1f}s (HTTP {e.code})")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30)
                    continue
                raise RuntimeError(f"HTTP {e.code} on {method} {url}\n{err_body}") from None
            except urllib.error.URLError as e:
                print(f"  network error, retrying: {e}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
        raise RuntimeError(f"Gave up after retries: {method} {url}")

    def resolve_account_id(self) -> str:
        if self.account_id:
            return self.account_id
        me = self._request("GET", "/auth/api/v1/users/me")
        try:
            memberships = me["response"]["business_memberships"]
            account_id = memberships[0]["business"]["account_id"]
        except (KeyError, IndexError):
            raise RuntimeError("Could not auto-resolve account_id. Set FRESHBOOKS_ACCOUNT_ID.")
        self.account_id = account_id
        print(f"  resolved account_id: {account_id}")
        return account_id

    def list_expense_categories(self) -> list[dict]:
        path = f"/accounting/account/{self.account_id}/expenses/categories"
        resp = self._request("GET", path)
        return resp.get("response", {}).get("result", {}).get("categories", [])

    def create_client(self, payload):
        return self._request("POST", f"/accounting/account/{self.account_id}/users/clients",
                             {"client": payload})["response"]["result"]["client"]["id"]

    def create_item(self, payload):
        return self._request("POST", f"/accounting/account/{self.account_id}/items/items",
                             {"item": payload})["response"]["result"]["item"]["id"]

    def create_vendor(self, payload):
        return self._request("POST", f"/accounting/account/{self.account_id}/expenses/vendors",
                             {"vendor": payload})["response"]["result"]["vendor"]["vendorid"]

    def create_invoice(self, payload):
        return self._request("POST", f"/accounting/account/{self.account_id}/invoices/invoices",
                             {"invoice": payload})["response"]["result"]["invoice"]["id"]

    def record_payment(self, payload):
        return self._request("POST", f"/accounting/account/{self.account_id}/payments/payments",
                             {"payment": payload})["response"]["result"]["payment"]["id"]

    def create_expense(self, payload):
        return self._request("POST", f"/accounting/account/{self.account_id}/expenses/expenses",
                             {"expense": payload})["response"]["result"]["expense"]["id"]


_dry_counter = [10_000]
def _next_dry_id():
    _dry_counter[0] += 1
    return _dry_counter[0]


# ------------------------------------------------------------------ #
# CSV readers
# ------------------------------------------------------------------ #

def read_csv(name: str) -> list[dict]:
    with open(DATA_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------ #
# Pushers
# ------------------------------------------------------------------ #

PAYMENT_METHOD_MAP = {
    "Credit Card": "credit", "Stripe": "credit", "ACH": "ach",
    "PayPal": "paypal", "Check": "check",
}


def client_label(row: dict) -> str:
    return row["organization"] if row.get("organization") else f'{row["first_name"]} {row["last_name"]}'


def push_items(fb, state, limit):
    rows = read_csv("items.csv")
    if limit:
        rows = rows[:limit]
    for row in rows:
        if row["name"] in state["items"]:
            continue
        payload = {
            "name": row["name"],
            "description": row["description"],
            "qty": "1",
            "unit_cost": {"amount": row["unit_cost"], "code": row["currency"]},
            "inventory": None,
        }
        new_id = fb.create_item(payload)
        state["items"][row["name"]] = new_id
        save_state(state)
        print(f"  + item: {row['name']} -> {new_id}")


def push_clients(fb, state, limit):
    rows = read_csv("clients.csv")
    if limit:
        rows = rows[:limit]
    for row in rows:
        label = client_label(row)
        if label in state["clients"]:
            continue
        payload = {
            "organization": row["organization"] or None,
            "fname": row["first_name"] or None,
            "lname": row["last_name"] or None,
            "email": row["email"],
            "bus_phone": row["phone"],
            "p_street": row["address_1"],
            "p_street2": row["address_2"] or None,
            "p_city": row["city"],
            "p_province": row["state"],
            "p_code": row["zip"],
            "p_country": "United States",
            "currency_code": row["currency"],
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        new_id = fb.create_client(payload)
        state["clients"][label] = new_id
        save_state(state)
        print(f"  + client: {label} -> {new_id}")


def push_vendors(fb, state, limit):
    rows = read_csv("vendors.csv")
    if limit:
        rows = rows[:limit]
    for row in rows:
        if row["name"] in state["vendors"]:
            continue
        payload = {
            "vendor_name": row["name"],
            "currency_code": row["currency"],
            "country": "United States",
        }
        try:
            new_id = fb.create_vendor(payload)
        except RuntimeError as e:
            print(f"  ! vendor endpoint failed for {row['name']}: {e}")
            print("    falling back to vendor-as-name on expenses")
            state["vendors"][row["name"]] = None
            save_state(state)
            continue
        state["vendors"][row["name"]] = new_id
        save_state(state)
        print(f"  + vendor: {row['name']} -> {new_id}")


def push_invoices(fb, state, limit):
    rows = read_csv("invoices.csv")
    by_inv: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_inv[r["invoice_number"]].append(r)

    invoice_numbers = list(by_inv.keys())
    if limit:
        invoice_numbers = invoice_numbers[:limit]

    for inv_num in invoice_numbers:
        if inv_num in state["invoices"]:
            continue
        lines = by_inv[inv_num]
        header = next(l for l in lines if l["subtotal"])
        client_id = state["clients"].get(header["client_name"])
        if not client_id:
            print(f"  ! skip {inv_num}: client {header['client_name']!r} not in state — run --only clients first")
            continue

        line_payloads = []
        tax_rate = float(header["tax_percent"]) if header.get("tax_percent") else 0.0
        for line in lines:
            lp = {
                "name": line["item_name"],
                "description": line["item_description"],
                "qty": str(line["quantity"]),
                "unit_cost": {"amount": line["rate"], "code": header["currency"]},
            }
            if tax_rate > 0:
                lp["taxName1"] = "Sales Tax"
                lp["taxAmount1"] = f"{tax_rate:.3f}"
            line_payloads.append(lp)

        created = date.fromisoformat(header["create_date"])
        due_date = date.fromisoformat(header["due_date"])
        due_offset_days = max(0, (due_date - created).days)

        invoice_payload = {
            "customerid": client_id,
            "create_date": header["create_date"],
            "due_offset_days": due_offset_days,
            "currency_code": header["currency"],
            "invoice_number": inv_num,
            "lines": line_payloads,
        }
        new_id = fb.create_invoice(invoice_payload)
        state["invoices"][inv_num] = {
            "id": new_id,
            "status": header["status"],
            "amount_paid": header["amount_paid"],
            "invoice_total": header["invoice_total"],
            "payment_date": header.get("payment_date") or None,
            "payment_method": header.get("payment_method") or None,
            "currency": header["currency"],
        }
        save_state(state)
        print(f"  + invoice: {inv_num} ({header['client_name']}) -> {new_id}")


def push_payments(fb, state, limit):
    count = 0
    for inv_num, meta in list(state["invoices"].items()):
        if "paid_recorded" in meta:
            continue
        if meta["status"] not in ("paid", "partial"):
            meta["paid_recorded"] = True
            save_state(state)
            continue
        amount_paid = float(meta["amount_paid"] or 0)
        if amount_paid <= 0:
            meta["paid_recorded"] = True
            save_state(state)
            continue
        method_label = meta.get("payment_method") or "ACH"
        method_code = PAYMENT_METHOD_MAP.get(method_label, "ach")
        payload = {
            "invoiceid": meta["id"],
            "amount": {"amount": f"{amount_paid:.2f}", "code": meta["currency"]},
            "date": meta.get("payment_date") or None,
            "type": method_code,
            "note": "Imported from synthetic dataset",
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        fb.record_payment(payload)
        meta["paid_recorded"] = True
        save_state(state)
        count += 1
        print(f"  + payment: {inv_num} ${amount_paid:.2f} ({method_label})")
        if limit and count >= limit:
            break


def push_expenses(fb, state, limit, category_map, default_cat_id):
    rows = read_csv("expenses.csv")
    if limit:
        rows = rows[:limit]
    for row in rows:
        if row["expense_id"] in state["expenses"]:
            continue
        vendor_name = row["vendor"]
        vendor_id = state["vendors"].get(vendor_name)
        cat_fb_name = CATEGORY_NAME_MAP.get(row["category"], row["category"])
        cat_id = category_map.get(cat_fb_name) or default_cat_id
        payload = {
            "amount": {"amount": row["amount"], "code": row["currency"]},
            "categoryid": cat_id,
            "date": row["date"],
            "notes": row["description"],
        }
        if vendor_id:
            payload["vendorid"] = vendor_id
        else:
            payload["vendor"] = vendor_name
        new_id = fb.create_expense(payload)
        state["expenses"][row["expense_id"]] = new_id
        save_state(state)
        print(f"  + expense: {row['expense_id']} {vendor_name} ${row['amount']} -> {new_id}")


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

def parse_args():
    p = argparse.ArgumentParser(description="Push synthetic CSVs into FreshBooks via the API.")
    p.add_argument("--dry-run", action="store_true", help="Print payloads without sending.")
    p.add_argument("--limit", type=int, default=None, help="Cap each resource at N for smoke tests.")
    p.add_argument(
        "--only",
        type=lambda s: [x.strip() for x in s.split(",")],
        default=None,
        help="Comma list of resources to push (items,clients,vendors,invoices,payments,expenses).",
    )
    p.add_argument("--reset-state", action="store_true", help="Delete .push_state.json before running.")
    return p.parse_args()


def main():
    args = parse_args()

    if args.reset_state and STATE_PATH.exists():
        STATE_PATH.unlink()
        print(f"removed {STATE_PATH.name}")

    token = os.environ.get("FRESHBOOKS_TOKEN")
    if not token and not args.dry_run:
        sys.exit("ERROR: set FRESHBOOKS_TOKEN env var (or use --dry-run).")
    if not token:
        token = "DRY_RUN_TOKEN"

    account_id = os.environ.get("FRESHBOOKS_ACCOUNT_ID", "")
    fb = FreshBooksClient(token=token, account_id=account_id, dry_run=args.dry_run)

    if not args.dry_run:
        fb.resolve_account_id()

    state = load_state()

    category_map: dict[str, int] = {}
    default_cat_id = int(os.environ.get("FRESHBOOKS_DEFAULT_EXPENSE_CATEGORY_ID") or 0)
    if not args.dry_run:
        cats = fb.list_expense_categories()
        for c in cats:
            category_map[c.get("category", "")] = c.get("categoryid")
        if not default_cat_id and cats:
            default_cat_id = cats[0]["categoryid"]
        print(f"  found {len(cats)} expense categories on account; default -> {default_cat_id}")
    else:
        default_cat_id = default_cat_id or 1

    only = set(args.only) if args.only else {"items", "clients", "vendors", "invoices", "payments", "expenses"}

    if "items" in only:
        print("\n== items ==");    push_items(fb, state, args.limit)
    if "clients" in only:
        print("\n== clients ==");  push_clients(fb, state, args.limit)
    if "vendors" in only:
        print("\n== vendors ==");  push_vendors(fb, state, args.limit)
    if "invoices" in only:
        print("\n== invoices =="); push_invoices(fb, state, args.limit)
    if "payments" in only:
        print("\n== payments =="); push_payments(fb, state, args.limit)
    if "expenses" in only:
        print("\n== expenses =="); push_expenses(fb, state, args.limit, category_map, default_cat_id)

    print("\nDone.")
    print(f"State file: {STATE_PATH}")


if __name__ == "__main__":
    main()
