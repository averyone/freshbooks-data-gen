"""
Synthetic FreshBooks-compatible CSV generator.

Profile: e-commerce / product seller, USD / United States, heavy volume.
Date range: rolling 12 months ending 2026-05-17 (configurable below).

Outputs (in ../data/):
  clients.csv   - 40 clients (B2B wholesale + retail/online buyers)
  items.csv     - 20 products
  vendors.csv   - 25 vendors (suppliers, shipping, software, utilities, services)
  invoices.csv  - ~250 invoices, one row per line item
  expenses.csv  - ~600 expenses

Cross-reference guarantees:
  - Every invoices.csv `client_name` exists in clients.csv
  - Every invoices.csv `item_name` exists in items.csv
  - Every expenses.csv `vendor` exists in vendors.csv

Realism choices:
  - Stable client roster (~40); each invoice picks from it, with repeat buyers
  - Stable 20-item catalog
  - Q4 holiday spike (Nov/Dec ~1.7x baseline volume)
  - ~70%+ paid, with realistic aging on the remainder
  - ~60% of invoices charge sales tax (mirroring nexus-state customers)
  - Coherent expense categories: COGS, shipping, marketing, software, utilities, rent, etc.
"""

import csv
import os
import random
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

# ------------------------------------------------------------------ #
# Setup
# ------------------------------------------------------------------ #

SEED = 42
random.seed(SEED)
fake = Faker("en_US")
Faker.seed(SEED)

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = (SCRIPT_DIR / ".." / "data").resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

END_DATE = date(2026, 5, 17)
START_DATE = date(2025, 5, 18)
TOTAL_DAYS = (END_DATE - START_DATE).days


def daterange_random(start: date, end: date) -> date:
    delta_days = (end - start).days
    return start + timedelta(days=random.randint(0, delta_days))


def month_weight(d: date) -> float:
    """E-commerce seasonality multiplier."""
    weights = {
        1: 0.7, 2: 0.7, 3: 0.8, 4: 0.8, 5: 0.9, 6: 0.9,
        7: 0.9, 8: 1.0, 9: 1.0, 10: 1.3, 11: 1.8, 12: 1.7,
    }
    return weights[d.month]


def pick_weighted_date() -> date:
    """Pick a date in [START_DATE, END_DATE] weighted by month_weight."""
    while True:
        candidate = START_DATE + timedelta(days=random.randint(0, TOTAL_DAYS))
        if random.random() < (month_weight(candidate) / 1.8):
            return candidate


# ------------------------------------------------------------------ #
# Items catalog (stable 20)
# ------------------------------------------------------------------ #

ITEMS = [
    ("Handmade Leather Wallet",   "Full-grain bifold leather wallet, vegetable-tanned",       68.00),
    ("Organic Cotton T-Shirt",    "100% organic cotton crew neck, unisex",                    32.00),
    ("Insulated Water Bottle 24oz","Double-wall vacuum insulated stainless steel bottle",      38.00),
    ("Merino Wool Beanie",        "Lightweight 100% merino wool knit beanie",                 28.00),
    ("Canvas Tote Bag",           "12oz heavyweight canvas tote, reinforced straps",          24.00),
    ("Recycled Polyester Hoodie", "Pullover hoodie, 80% recycled polyester / 20% cotton",     72.00),
    ("Trail Running Socks",       "Cushioned merino blend crew socks (pair)",                 18.00),
    ("Bamboo Sunglasses",         "Polarized sunglasses with bamboo frame",                   55.00),
    ("Camp Mug 12oz",             "Enamel-coated steel camp mug",                             16.00),
    ("Pocket Notebook (3-pack)",  "Soft-cover pocket notebooks, 48 pages each",               14.00),
    ("Waxed Canvas Backpack",     "20L waxed canvas roll-top backpack",                      145.00),
    ("Cork Yoga Mat",             "Cork-surface yoga mat with natural rubber base",           78.00),
    ("Stainless Pour-Over Set",   "Pour-over coffee dripper with reusable steel filter",      48.00),
    ("Hemp Crew Socks",           "Breathable hemp blend everyday crew socks (pair)",         14.00),
    ("Cedar Garden Planter",      "Untreated cedar 12in raised planter box",                  42.00),
    ("Beeswax Food Wraps (3pk)",  "Reusable organic cotton + beeswax food wraps",             22.00),
    ("Trail Map Print 12x18",     "Letterpress trail map print, archival paper",              36.00),
    ("Pour-Over Coffee Beans",    "12oz whole-bean light roast, single origin",               21.00),
    ("Travel Toiletry Pouch",     "Water-resistant waxed canvas dopp kit",                    52.00),
    ("Reusable Produce Bags (5)", "Mesh produce bags with drawstrings, set of 5",             16.00),
]

# ------------------------------------------------------------------ #
# Clients (40 - mix of B2B wholesale + repeat online buyers)
# ------------------------------------------------------------------ #

SALES_TAX_STATES = {
    "CA": 0.0825, "NY": 0.08875, "TX": 0.0825, "WA": 0.101, "IL": 0.1025,
    "MA": 0.0625, "CO": 0.0865, "OR": 0.0, "MT": 0.0, "FL": 0.075,
    "GA": 0.08, "PA": 0.06, "AZ": 0.086, "NC": 0.075, "MI": 0.06,
}
ALL_STATES = list(SALES_TAX_STATES.keys())

B2B_NAMES = [
    "Wildflower Mercantile", "North Cove Outfitters", "Linden Street Goods",
    "Marin Trading Co", "Pacific Crest Supply", "Cobalt & Pine Boutique",
    "Field & Forge", "Bramble Lane Shop", "Hollow Tree General Store",
    "Heron Bay Provisions", "Ember & Oak", "Saltwater & Sage",
    "The Foundry Market", "River Road Mercantile", "Tidewater Trading Post",
]


def build_clients():
    clients = []
    for org in B2B_NAMES:
        state = random.choice(ALL_STATES)
        clients.append({
            "organization": org,
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "email": f"orders@{org.lower().replace(' & ', '').replace(' ', '').replace('the', '')}.com",
            "phone": fake.phone_number(),
            "address_1": fake.street_address(),
            "address_2": "",
            "city": fake.city(),
            "state": state,
            "zip": fake.zipcode_in_state(state_abbr=state),
            "country": "US",
            "currency": "USD",
            "client_type": "wholesale",
        })
    for _ in range(25):
        state = random.choice(ALL_STATES)
        first = fake.first_name()
        last = fake.last_name()
        clients.append({
            "organization": "",
            "first_name": first,
            "last_name": last,
            "email": f"{first.lower()}.{last.lower()}{random.randint(1,99)}@{fake.free_email_domain()}",
            "phone": fake.phone_number(),
            "address_1": fake.street_address(),
            "address_2": random.choice(["", "", "", f"Apt {random.randint(1, 40)}"]),
            "city": fake.city(),
            "state": state,
            "zip": fake.zipcode_in_state(state_abbr=state),
            "country": "US",
            "currency": "USD",
            "client_type": "retail",
        })
    return clients


# ------------------------------------------------------------------ #
# Vendors (25)
# ------------------------------------------------------------------ #

VENDORS = [
    ("UPS",                        "Shipping & Postage",       (12.00,   480.00)),
    ("USPS",                       "Shipping & Postage",       (6.00,    240.00)),
    ("FedEx",                      "Shipping & Postage",       (15.00,   620.00)),
    ("ShipStation",                "Software & Subscriptions", (29.00,    99.00)),
    ("Shopify",                    "Software & Subscriptions", (79.00,   299.00)),
    ("Klaviyo",                    "Software & Subscriptions", (45.00,   350.00)),
    ("Stripe Fees",                "Bank & Processor Fees",    (40.00,   820.00)),
    ("PayPal Fees",                "Bank & Processor Fees",    (15.00,   320.00)),
    ("Meta Ads",                   "Advertising & Marketing",  (200.00, 4200.00)),
    ("Google Ads",                 "Advertising & Marketing",  (180.00, 3600.00)),
    ("TikTok Ads",                 "Advertising & Marketing",  (120.00, 2400.00)),
    ("Adobe Creative Cloud",       "Software & Subscriptions", (54.99,    79.99)),
    ("AWS",                        "Software & Subscriptions", (120.00,   480.00)),
    ("Avalara Sales Tax",          "Software & Subscriptions", (75.00,   180.00)),
    ("Northern Leather Supply",    "Cost of Goods Sold",      (850.00, 6200.00)),
    ("Pacific Coast Textiles",     "Cost of Goods Sold",      (620.00, 4800.00)),
    ("Cedar Mill Lumber Co",       "Cost of Goods Sold",      (310.00, 2100.00)),
    ("Uline Packaging",            "Packaging & Supplies",    (220.00, 1800.00)),
    ("EcoEnclose",                 "Packaging & Supplies",    (180.00, 1500.00)),
    ("WeWork Studio Space",        "Rent",                   (1850.00, 1850.00)),
    ("Pacific Gas & Electric",     "Utilities",              (140.00,   360.00)),
    ("AT&T Business",              "Utilities",              (89.00,    160.00)),
    ("Hartford Business Insurance","Insurance",              (340.00,   340.00)),
    ("Bench Bookkeeping",          "Professional Services",  (249.00,   249.00)),
    ("California Franchise Tax Board","Taxes",                (800.00,  2400.00)),
]


# ------------------------------------------------------------------ #
# Invoices / expenses generation
# ------------------------------------------------------------------ #

def generate_invoices(clients, items):
    invoices = []
    n_invoices = 250
    invoice_id = 1000

    weighted_clients = []
    for c in clients:
        weighted_clients.extend([c] * (4 if c["client_type"] == "wholesale" else 1))

    for _ in range(n_invoices):
        invoice_id += 1
        invoice_number = f"INV-{invoice_id}"
        client = random.choice(weighted_clients)
        create_date = pick_weighted_date()

        if client["client_type"] == "wholesale":
            n_lines = random.randint(2, 6)
            qty_range = (4, 24)
        else:
            n_lines = random.randint(1, 3)
            qty_range = (1, 3)

        chosen_items = random.sample(items, n_lines)
        payment_terms_days = 30 if client["client_type"] == "wholesale" else 14
        due_date = create_date + timedelta(days=payment_terms_days)

        tax_rate = SALES_TAX_STATES.get(client["state"], 0.0) if random.random() < 0.85 else 0.0

        days_old = (END_DATE - create_date).days
        status, payment_date, payment_method = _assign_status(create_date, due_date, days_old)

        client_label = client["organization"] if client["organization"] else f'{client["first_name"]} {client["last_name"]}'

        line_subtotal = 0.0
        line_rows = []
        for item in chosen_items:
            qty = random.randint(*qty_range)
            unit_rate = round(item[2] * (0.65 if client["client_type"] == "wholesale" else 1.0), 2)
            line_total = round(qty * unit_rate, 2)
            line_subtotal += line_total
            line_rows.append({
                "item_name": item[0],
                "item_description": item[1],
                "quantity": qty,
                "rate": f"{unit_rate:.2f}",
                "line_total": f"{line_total:.2f}",
            })

        tax_amount = round(line_subtotal * tax_rate, 2)
        invoice_total = round(line_subtotal + tax_amount, 2)

        if status == "partial":
            amount_paid = round(invoice_total * random.uniform(0.3, 0.6), 2)
        elif status == "paid":
            amount_paid = invoice_total
        else:
            amount_paid = 0.0

        for idx, line in enumerate(line_rows):
            invoices.append({
                "invoice_number": invoice_number,
                "client_name": client_label,
                "client_email": client["email"],
                "create_date": create_date.isoformat(),
                "due_date": due_date.isoformat(),
                "item_name": line["item_name"],
                "item_description": line["item_description"],
                "quantity": line["quantity"],
                "rate": line["rate"],
                "line_total": line["line_total"],
                "tax_name":      "US Sales Tax" if (idx == 0 and tax_rate > 0) else "",
                "tax_percent":   f"{tax_rate * 100:.3f}" if (idx == 0 and tax_rate > 0) else "",
                "subtotal":      f"{line_subtotal:.2f}" if idx == 0 else "",
                "tax_amount":    f"{tax_amount:.2f}" if idx == 0 else "",
                "invoice_total": f"{invoice_total:.2f}" if idx == 0 else "",
                "amount_paid":   f"{amount_paid:.2f}" if idx == 0 else "",
                "status":        status if idx == 0 else "",
                "payment_date":  payment_date.isoformat() if (idx == 0 and payment_date) else "",
                "payment_method": payment_method if idx == 0 else "",
                "currency": "USD",
            })
    return invoices


def _assign_status(create_date: date, due_date: date, days_old: int):
    r = random.random()
    if days_old < 14:
        if r < 0.30:
            return "paid", create_date + timedelta(days=random.randint(1, max(1, days_old))), random.choice(["Credit Card", "Stripe", "ACH"])
        elif r < 0.92:
            return "sent", None, ""
        else:
            return "draft", None, ""
    elif days_old < 45:
        if r < 0.72:
            return "paid", create_date + timedelta(days=random.randint(2, min(days_old, 35))), random.choice(["Credit Card", "Stripe", "ACH", "PayPal"])
        elif r < 0.82:
            return "sent" if create_date + timedelta(days=30) > END_DATE else "overdue", None, ""
        elif r < 0.95:
            return "partial", create_date + timedelta(days=random.randint(5, 25)), random.choice(["ACH", "Check"])
        else:
            return "overdue", None, ""
    else:
        if r < 0.84:
            paid_lag = random.randint(2, 40)
            return "paid", create_date + timedelta(days=paid_lag), random.choice(["Credit Card", "Stripe", "ACH", "PayPal", "Check"])
        elif r < 0.92:
            return "overdue", None, ""
        elif r < 0.98:
            return "partial", create_date + timedelta(days=random.randint(5, 35)), random.choice(["ACH", "Check"])
        else:
            return "draft", None, ""


def generate_expenses(vendors):
    expenses = []
    expense_id = 5000

    vendor_cadence = {
        "UPS": 12.0, "USPS": 14.0, "FedEx": 6.0, "ShipStation": 1.0, "Shopify": 1.0,
        "Klaviyo": 1.0, "Stripe Fees": 4.0, "PayPal Fees": 4.0, "Meta Ads": 4.0,
        "Google Ads": 4.0, "TikTok Ads": 3.0, "Adobe Creative Cloud": 1.0,
        "AWS": 1.0, "Avalara Sales Tax": 1.0, "Northern Leather Supply": 0.8,
        "Pacific Coast Textiles": 0.8, "Cedar Mill Lumber Co": 0.5,
        "Uline Packaging": 1.5, "EcoEnclose": 1.5, "WeWork Studio Space": 1.0,
        "Pacific Gas & Electric": 1.0, "AT&T Business": 1.0,
        "Hartford Business Insurance": 1.0 / 12, "Bench Bookkeeping": 1.0,
        "California Franchise Tax Board": 1.0 / 12,
    }

    current = date(START_DATE.year, START_DATE.month, 1)
    while current <= END_DATE:
        seasonality = month_weight(current)
        for v_name, category, (lo, hi) in vendors:
            base = vendor_cadence.get(v_name, 1.0)
            scale_with_season = category in (
                "Cost of Goods Sold", "Shipping & Postage",
                "Advertising & Marketing", "Packaging & Supplies",
                "Bank & Processor Fees",
            )
            mean_count = base * (seasonality if scale_with_season else 1.0)
            count = max(0, int(round(mean_count + random.uniform(-0.6, 0.6))))
            for _ in range(count):
                day = random.randint(1, 28)
                tx_date = date(current.year, current.month, day)
                if tx_date < START_DATE or tx_date > END_DATE:
                    continue
                amount = round(random.uniform(lo, hi), 2)
                expense_id += 1
                expenses.append({
                    "expense_id": f"EXP-{expense_id}",
                    "date": tx_date.isoformat(),
                    "vendor": v_name,
                    "category": category,
                    "description": _expense_description(v_name, category),
                    "amount": f"{amount:.2f}",
                    "tax_amount": "0.00",
                    "currency": "USD",
                    "payment_method": _payment_method_for(category),
                    "is_billable": "no",
                    "notes": "",
                })
        current = date(current.year + 1, 1, 1) if current.month == 12 else date(current.year, current.month + 1, 1)

    target_low, target_high = 560, 660
    if len(expenses) > target_high:
        expenses = random.sample(expenses, target_high)
    elif len(expenses) < target_low:
        deficit = target_low - len(expenses)
        for _ in range(deficit):
            v_name, category, (lo, hi) = random.choice(vendors)
            tx_date = daterange_random(START_DATE, END_DATE)
            amount = round(random.uniform(lo, hi), 2)
            expense_id += 1
            expenses.append({
                "expense_id": f"EXP-{expense_id}",
                "date": tx_date.isoformat(),
                "vendor": v_name,
                "category": category,
                "description": _expense_description(v_name, category),
                "amount": f"{amount:.2f}",
                "tax_amount": "0.00",
                "currency": "USD",
                "payment_method": _payment_method_for(category),
                "is_billable": "no",
                "notes": "",
            })

    expenses.sort(key=lambda e: e["date"])
    return expenses


def _expense_description(vendor, category):
    table = {
        "UPS": "Outbound shipping labels", "USPS": "First-class & priority shipping",
        "FedEx": "Express shipments", "ShipStation": "Monthly subscription",
        "Shopify": "Monthly storefront subscription", "Klaviyo": "Email marketing platform",
        "Stripe Fees": "Card processing fees", "PayPal Fees": "Processing fees",
        "Meta Ads": "Facebook & Instagram ad spend", "Google Ads": "Search & shopping ads",
        "TikTok Ads": "Paid social campaign", "Adobe Creative Cloud": "Design software subscription",
        "AWS": "Cloud hosting & storage", "Avalara Sales Tax": "Sales tax automation subscription",
        "Northern Leather Supply": "Leather raw material order",
        "Pacific Coast Textiles": "Fabric raw material order",
        "Cedar Mill Lumber Co": "Cedar planter material",
        "Uline Packaging": "Boxes, mailers, void fill",
        "EcoEnclose": "Compostable mailers and tissue",
        "WeWork Studio Space": "Monthly studio rent",
        "Pacific Gas & Electric": "Studio utilities",
        "AT&T Business": "Business internet & phone",
        "Hartford Business Insurance": "Annual business policy",
        "Bench Bookkeeping": "Monthly bookkeeping service",
        "California Franchise Tax Board": "Quarterly estimated tax",
    }
    return table.get(vendor, category)


def _payment_method_for(category):
    if category in ("Rent", "Utilities", "Insurance", "Professional Services", "Taxes"):
        return "ACH"
    if category in ("Cost of Goods Sold", "Packaging & Supplies"):
        return random.choice(["ACH", "Business Credit Card"])
    return "Business Credit Card"


# ------------------------------------------------------------------ #
# CSV writer
# ------------------------------------------------------------------ #

def write_csv(filename, fieldnames, rows):
    path = DATA_DIR / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return path


def main():
    clients = build_clients()
    items = ITEMS
    vendors = VENDORS

    invoices = generate_invoices(clients, items)
    expenses = generate_expenses(vendors)

    write_csv("clients.csv",
              ["organization", "first_name", "last_name", "email", "phone",
               "address_1", "address_2", "city", "state", "zip", "country",
               "currency", "client_type"],
              clients)
    write_csv("items.csv",
              ["name", "description", "unit_cost", "currency"],
              [{"name": i[0], "description": i[1], "unit_cost": f"{i[2]:.2f}", "currency": "USD"} for i in items])
    write_csv("vendors.csv",
              ["name", "category", "currency", "country"],
              [{"name": v[0], "category": v[1], "currency": "USD", "country": "US"} for v in vendors])
    write_csv("invoices.csv",
              ["invoice_number", "client_name", "client_email", "create_date", "due_date",
               "item_name", "item_description", "quantity", "rate", "line_total",
               "tax_name", "tax_percent", "subtotal", "tax_amount", "invoice_total",
               "amount_paid", "status", "payment_date", "payment_method", "currency"],
              invoices)
    write_csv("expenses.csv",
              ["expense_id", "date", "vendor", "category", "description",
               "amount", "tax_amount", "currency", "payment_method", "is_billable", "notes"],
              expenses)

    n_invoices = len({r["invoice_number"] for r in invoices})
    print(f"clients:  {len(clients)}")
    print(f"items:    {len(items)}")
    print(f"vendors:  {len(vendors)}")
    print(f"invoices: {n_invoices} ({len(invoices)} line rows)")
    print(f"expenses: {len(expenses)}")
    print(f"\nWrote CSVs to: {DATA_DIR}")


if __name__ == "__main__":
    main()
