# ERPNext Dashboard Customization Guide

This guide gives you a practical dashboard setup for:
- Fast item lookup by item number/invoice
- Strict uniqueness so similar items do not conflict
- Recurring invoice tracking and sending
- Sales and cash tracking with charts and tables
- A clean, visual layout with photos

---

## 1) Dashboard Layout (What to build)

Create one workspace called **Operations Cockpit** and place blocks in this order:

1. KPI cards row
- Today Sales
- Month-to-Date Sales
- Outstanding Receivables
- Recurring Invoices Due (next 7 days)

2. Search + Actions row
- Shortcut: Item List
- Shortcut: Sales Invoice List
- Shortcut: Accounts Receivable
- Shortcut: New Sales Invoice
- Shortcut: New Delivery Note

3. Charts row
- Daily Sales (last 30 days)
- Top 10 Items by Revenue (this month)
- Invoice Collection Trend (paid vs outstanding)

4. Tables row
- Items with low stock
- Recurring invoices due soon
- Overdue sales invoices

5. Visual row
- Product photo tile 1 (best sellers)
- Product photo tile 2 (new arrivals)
- Brand/Store banner tile

Tip: keep the first row numbers-only, second row actions-only, then charts/tables. This keeps it easy to scan.

---

## 2) Enforce Unique Item Identity (No conflicts)

### 2.1 Item code strategy (required)
Use a strict item code format so every item is unique and searchable.

Recommended format:
- `ITM-<CATEGORY>-<5 DIGITS>`
- Example: `ITM-BEV-00042`, `ITM-FOOD-00107`

### 2.2 Add two custom fields on Item
In Customize Form -> Item, add:
- `custom_sku` (Data, Unique = 1)
- `custom_invoice_alias` (Data, Unique = 1)

This gives you:
- Primary unique key (`item_code`)
- Secondary unique keys for invoices/search (`custom_sku`, `custom_invoice_alias`)

### 2.3 Add duplicate protection (recommended)
Create a Server Script for DocType Event on Item (`Before Save`) and block near-duplicates by normalized item name.

Example logic:
1. Normalize item name (lowercase, trim spaces, remove repeated spaces)
2. Query existing Items with the same normalized value
3. If found and not same record, throw validation error

Result: `Coffee 1kg` and `coffee   1KG` cannot both be created.

### 2.4 Make search fast
Use Item list with saved filters and columns:
- Columns: Item Code, Item Name, Custom SKU, Item Group, Standard Rate, Disabled
- Saved filters:
  - Active Items
  - By Category
  - Low Stock Items

Train the team to search by:
- Item Code first (most precise)
- SKU second
- Name only when unsure

---

## 3) Invoice Center (Recurring + Send + Track)

### 3.1 Enable recurring invoices
Use Auto Repeat with Sales Invoice:
1. Create a template Sales Invoice per customer plan
2. Create Auto Repeat record:
- Reference DocType: Sales Invoice
- Frequency: Monthly/Weekly
- Start Date and End Date
- Submit on creation: Yes

### 3.2 Auto-send invoices
Set up Notification for Sales Invoice On Submit:
- Recipients: customer contact email
- Subject: Invoice {{ doc.name }}
- Attach Print: Yes

### 3.3 Build recurring invoice table widget
Create a saved Sales Invoice list/report with filters:
- `is_return = 0`
- `docstatus = 1`
- `due_date <= Today + 7`

Columns:
- Invoice No
- Customer
- Posting Date
- Due Date
- Grand Total
- Outstanding Amount
- Status

### 3.4 Add quick actions
Add workspace shortcuts:
- Recurring Invoices (Auto Repeat list)
- Draft Invoices
- Overdue Invoices
- Email Queue

---

## 4) Sales Tracking (Money view)

### KPI cards to add
- Today Sales
- MTD Sales
- Collected This Month
- Outstanding Receivables
- Average Invoice Value

### Charts to add
1. Daily Sales Trend (line, last 30 days)
2. Monthly Revenue vs Collections (bar)
3. Top 10 Items by Revenue (horizontal bar)
4. Outstanding by Customer (donut)

### Tables to add
1. Top Customers This Month
- Customer | Revenue | Paid | Outstanding

2. Top Items This Month
- Item Code | Item Name | Qty Sold | Revenue

3. Open Receivables Aging
- Customer | 0-30 | 31-60 | 61-90 | 90+

---

## 5) Make It Look Nice (Charts + Tables + Photos)

### Visual style
- Use one accent color family (blue/teal) for charts
- Keep card backgrounds light and consistent
- Use short card titles (2-4 words)
- Keep number formatting as currency with separators

### Photo blocks
You can add photos in two common ways:
1. Website Block / HTML Block with image URLs from Files
2. Shortcut cards pointing to product catalog pages with hero images

Recommended photo set:
- Best seller collage
- New arrivals banner
- Category hero image (Food/Beverage)

Image sizing:
- Banner: 1600x500
- Tile: 800x600
- Keep file size < 250 KB each for fast loading

---

## 6) Suggested Final Dashboard Blueprint

| Section | Block Type | Data Source |
|---|---|---|
| Financial Snapshot | KPI Cards | Sales Invoice + Payment Entry |
| Search & Actions | Shortcuts | Item, Sales Invoice, Customer |
| Sales Trends | Charts | Sales Invoice items + totals |
| Ops Watchlist | Tables | Low stock + overdue + recurring due |
| Visual Merchandising | Photos | Uploaded Files / Website blocks |

---

## 7) Quick Build Checklist

- [ ] Create workspace: Operations Cockpit
- [ ] Add 5 KPI cards
- [ ] Add 4 charts
- [ ] Add 3 tables
- [ ] Add item uniqueness fields (`custom_sku`, `custom_invoice_alias`)
- [ ] Add item duplicate-prevention script
- [ ] Configure Auto Repeat for recurring invoices
- [ ] Configure invoice email notification
- [ ] Add 3 photo tiles/banners
- [ ] Save and share workspace with your role profiles

---

## 8) Optional Next Automation

If you want, this repo can include an API script to auto-create:
- saved reports
- dashboard charts
- notification templates
- workspace shortcuts

That script can be added as `scripts/setup_dashboard_customization.py` and run once against your ERPNext instance.

---

## Included in this repo

- Server Script template for item uniqueness checks:
  - `configuration/erpnext-item-uniqueness-server-script.py`
- SQL templates for charts and table widgets:
  - `configuration/dashboard-report-queries.sql`
