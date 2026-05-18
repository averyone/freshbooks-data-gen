# freshbooks-data-gen

Synthetic accounting data for FreshBooks, plus a script to push it into a real FreshBooks instance via the API.

Useful when you need a populated FreshBooks account for demos, training, screenshots, or integration testing — without exposing real customer or financial data.

## What's in the box

```
freshbooks-data-gen/
├── data/                          # Generated CSVs (re-runnable, but checked in for convenience)
│   ├── clients.csv                # 40 clients (15 wholesale + 25 retail)
│   ├── items.csv                  # 20 products
│   ├── vendors.csv                # 25 vendors
│   ├── invoices.csv               # 250 invoices (891 line rows)
│   └── expenses.csv               # 660 expenses
└── scripts/
    ├── generate.py                # Build the CSVs with Faker
    ├── verify.py                  # Cross-reference + math + status sanity checks
    └── push.py                    # Push the CSVs into FreshBooks via the REST API
```

## Profile of the data

- **Business type:** e-commerce / product seller (outdoor + lifestyle goods)
- **Currency:** USD
- **Region:** United States
- **Time range:** Rolling 12 months ending 2026-05-17
- **Volume:** ~250 invoices, ~660 expenses
- **Seasonality:** Q4 holiday spike (November ~1.8x baseline, December ~1.7x)
- **Status mix:** ~83% paid, ~9% partial, ~7% overdue, plus a few sent / draft
- **Tax:** ~60% of invoices charge state sales tax against nexus customers
- **Cross-refs guaranteed:** every invoice client and item, every expense vendor, resolves cleanly

## Prerequisites

- **Python 3.8+**
- **pip** (for installing dependencies)
- **FreshBooks account** (only needed if pushing via API; a trial account is recommended)

## Quick start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

The only external dependency is [Faker](https://faker.readthedocs.io/) (used by the generator). The verify and push scripts use only the Python standard library.

### 2. Generate the CSVs

```bash
python3 scripts/generate.py
```

The seed is fixed (`SEED = 42`), so every run yields the same data. Change the seed at the top of `generate.py` for a fresh batch, or shift `END_DATE` for a different time window.

### 3. Verify data integrity

```bash
python3 scripts/verify.py
```

The verification script checks:
- **Cross-references** — every invoice `client_name` and `item_name` exists in `clients.csv` / `items.csv`; every expense `vendor` exists in `vendors.csv`
- **Invoice math** — line totals sum to subtotal; subtotal + tax = invoice total
- **Reports** — date range, invoice status mix, monthly volume distribution, financial totals, and top vendors by spend

A passing run ends with `OK`. Any issues are reported as math or reference errors with `FAIL`.

### Push into FreshBooks

```bash
export FRESHBOOKS_TOKEN="eyJ0eXAiOi..."         # OAuth bearer token
export FRESHBOOKS_ACCOUNT_ID="abc123"           # optional; resolved from /users/me if omitted

# Smoke test against your account
python3 scripts/push.py --dry-run --limit 2

# Real run, capped at 2 of each resource
python3 scripts/push.py --limit 2

# Full run
python3 scripts/push.py
```

The pusher creates records in dependency order — **items → clients → vendors → invoices → payments → expenses** — and writes each created record's FreshBooks ID into `scripts/.push_state.json`. Re-running skips anything already in state, so a partial failure can resume cleanly.

## Pusher options

| Flag | Effect |
| --- | --- |
| `--dry-run` | Print payloads, don't hit the API |
| `--limit N` | Cap each resource at N records (use this for smoke tests) |
| `--only X,Y` | Push only the listed resources (e.g. `--only clients,items`) |
| `--reset-state` | Delete `.push_state.json` and start fresh |

Resource names accepted by `--only`: `items, clients, vendors, invoices, payments, expenses`.

## Getting a FreshBooks token

The cleanest path for personal seeding is the FreshBooks OAuth flow:

1. Go to FreshBooks → Settings → Developer Portal → My Apps → Create App
2. Get an Authorization Code via the OAuth redirect flow
3. Exchange it for a Bearer token (12-hour TTL)
4. Set `FRESHBOOKS_TOKEN` from that bearer

Full walk-through: https://www.freshbooks.com/api/get-authenticated-on-the-freshbooks-api

## Importing without the API (CSV upload)

If you'd rather not touch the API, FreshBooks supports CSV bulk imports under Settings → Imports. **Import order matters:**

1. `data/items.csv`
2. `data/clients.csv`
3. `data/vendors.csv`
4. `data/invoices.csv`  (each invoice line is its own row; invoice-level fields appear only on the first line)
5. `data/expenses.csv`

If FreshBooks rejects any of the optional columns (status, payment_date, etc.), drop them and mark invoices paid afterward.

## Safety notes

- **There's no FreshBooks dev sandbox.** Push to a trial account first
- **There's no bulk-delete endpoint for invoices.** Polluting a production account means deleting records in the UI one by one — always start with `--limit 2`
- **`.push_state.json` is gitignored.** It contains FreshBooks IDs tied to your account; don't commit it

## Customizing

| What | Where |
| --- | --- |
| Time range / window | `START_DATE`, `END_DATE` in `scripts/generate.py` |
| Seasonality curve | `month_weight()` in `scripts/generate.py` |
| Product catalog | `ITEMS` list in `scripts/generate.py` |
| Client roster | `B2B_NAMES` + the retail loop in `scripts/generate.py` |
| Vendor list + spend ranges | `VENDORS` table in `scripts/generate.py` |
| Paid / overdue mix | `_assign_status()` in `scripts/generate.py` |
| Sales tax rates by state | `SALES_TAX_STATES` in `scripts/generate.py` |
| Expense category mapping | `CATEGORY_NAME_MAP` in `scripts/push.py` |

## License

MIT — see [LICENSE](LICENSE).
