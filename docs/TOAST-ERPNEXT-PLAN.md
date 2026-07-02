# Toast POS + ERPNext Integration Plan

## Overview

Use **Toast** as the front-of-house point-of-sale system and **ERPNext** as the back-office ERP for inventory, accounting, purchasing, and reporting. A lightweight sync layer connects the two systems so that every sale in Toast automatically flows into ERPNext's ledger and depletes inventory without manual entry.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     RESTAURANT FLOOR                        │
│                                                             │
│   Toast POS Terminals / Handheld / Kiosk / Online Order     │
│   - Take orders                                             │
│   - Process payments (card, cash, gift card)                │
│   - Apply discounts / comps / voids                         │
│   - Print receipts / KDS tickets                            │
└────────────────────────┬────────────────────────────────────┘
                         │  Toast Webhook / API (real-time)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   SYNC LAYER  (AWS Lambda)                  │
│                                                             │
│   - Receives Toast order-closed webhooks                    │
│   - Maps Toast menu items → ERPNext Item codes              │
│   - Maps Toast revenue centers → ERPNext Cost Centers       │
│   - Maps Toast payment types → ERPNext Payment Modes        │
│   - Calls ERPNext REST API to create documents              │
└────────────────────────┬────────────────────────────────────┘
                         │  ERPNext REST API
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   ERPNext (this AWS stack)                  │
│                                                             │
│   Accounting         Inventory          Purchasing          │
│   - Sales Invoice    - Stock Ledger     - Purchase Orders   │
│   - GL Entries       - Item master      - Supplier mgmt     │
│   - Tax entries      - Reorder alerts   - Receiving         │
│                                                             │
│   HR / Payroll       Reports            CRM                 │
│   - Employee master  - P&L              - Leads             │
│   - Attendance       - Cost of goods    - Opportunities     │
│   - Payroll runs     - Sales by item    - Loyalty programs  │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1 — ERPNext Setup (Week 1–2)

### 1.1 Chart of Accounts

- Set up restaurant-specific accounts:
  - `4000 - Food Sales`
  - `4001 - Beverage Sales`
  - `4002 - Alcohol Sales`
  - `5000 - Cost of Goods Sold (Food)`
  - `5001 - Cost of Goods Sold (Beverage)`
  - `5002 - Labor Cost`
  - `6000 - Operating Expenses`

### 1.2 Item Master

Create one ERPNext Item for every Toast menu item:

| Toast Menu Item | ERPNext Item Code | Item Group | UOM |
| --------------- | ----------------- | ---------- | --- |
| Cheeseburger    | FOOD-001          | Food       | Nos |
| House Salad     | FOOD-002          | Food       | Nos |
| Draft Beer      | BEV-001           | Beverage   | Nos |
| Soft Drink      | BEV-002           | Beverage   | Nos |

- Enable **"Is Stock Item"** for items you want to track inventory
- Set standard selling rate (used for variance reporting)

### 1.3 Warehouses

- `Main Kitchen` — ingredients stock
- `Bar` — beverage stock
- `Finished Goods` — plated items (optional)

### 1.4 Customer Setup

- Create a single customer **"Walk-in Guest"** for all POS cash/card sales
- Create named accounts for corporate clients, catering, or loyalty members

### 1.5 Payment Modes

Match every Toast payment type to an ERPNext Mode of Payment:

| Toast Type    | ERPNext Mode |
| ------------- | ------------ |
| Credit Card   | Credit Card  |
| Cash          | Cash         |
| Gift Card     | Gift Card    |
| House Account | Credit       |

---

## Phase 2 — Toast Configuration (Week 1–2)

### 2.1 Enable Webhooks

In Toast Dashboard → Integrations → Webhooks:

- Event: `OrderClosed`
- Destination: your Lambda function URL (deployed in Phase 3)

### 2.2 Revenue Centers → Cost Centers

Map each revenue center to an ERPNext Cost Center:

| Toast Revenue Center | ERPNext Cost Center        |
| -------------------- | -------------------------- |
| Dine-In              | Dine-In - Restaurant       |
| Bar                  | Bar - Restaurant           |
| To-Go                | Takeout - Restaurant       |
| Online               | Online Orders - Restaurant |
| Catering             | Catering - Restaurant      |

### 2.3 Get Toast API Credentials

- Toast Dashboard → Integrations → API → Create Partner Application
- Save: `clientId`, `clientSecret`, `restaurantGuid`

---

## Phase 3 — Sync Layer (Week 2–3)

### 3.1 Deploy AWS Lambda

**File: `lambda/toast-to-erpnext/handler.py`**

Responsibilities:

1. Receive `OrderClosed` webhook from Toast
2. Authenticate with ERPNext API (`key:secret`)
3. For each order line item:
   - Create `Sales Invoice` in ERPNext
   - Add line items with quantity and rate
   - Set cost center from revenue center map
   - Set posting date/time from Toast order timestamp
4. Submit the invoice (posts to GL automatically)
5. Create `Payment Entry` linked to the invoice
6. For tracked items: post `Stock Entry` (Stock Issue from warehouse)

**Environment variables needed:**

```
ERPNEXT_URL       = https://3.216.86.193
ERPNEXT_API_KEY   = 647f56b706a1bea
ERPNEXT_API_SECRET= 6c615d3ea8cbd4d
TOAST_CLIENT_ID   = (from Toast dashboard)
TOAST_CLIENT_SECRET = (from Toast dashboard)
TOAST_RESTAURANT_GUID = (from Toast dashboard)
```

### 3.2 Item Mapping Table

Store in DynamoDB or SSM Parameter Store:

```json
{
  "toast_item_guid_abc123": "FOOD-001",
  "toast_item_guid_def456": "FOOD-002",
  "toast_item_guid_ghi789": "BEV-001"
}
```

### 3.3 Sync Frequency

- **Real-time**: closed orders via Toast webhook → instant invoice in ERPNext
- **End of day**: daily batch reconciliation to catch any missed webhooks
- **Inventory**: daily stock count sync from ERPNext → reorder alerts

---

## Phase 4 — Inventory Integration (Week 3–4)

### 4.1 Ingredient-Level Tracking (Optional but recommended)

Use ERPNext **Bill of Materials (BOM)**:

- `Cheeseburger` BOM: 200g beef patty, 1 bun, 2 slices cheese, 30g lettuce
- When invoice is submitted, ERPNext auto-backflushes raw ingredients

### 4.2 Purchase Orders from ERPNext

When ingredient stock falls below reorder level:

1. ERPNext auto-creates a **Purchase Order** to the supplier
2. PO is approved in ERPNext by manager
3. On delivery, **Purchase Receipt** is entered → stock levels update
4. **Purchase Invoice** is created → accounts payable posted

### 4.3 Reorder Alerts

- Set reorder levels per item in ERPNext Item master
- ERPNext sends email alert when stock < minimum
- Or: run `verify-backups`-style workflow daily to check stock levels

---

## Phase 5 — Reporting (Week 4)

### Reports available in ERPNext out of the box:

| Report              | Use                                   |
| ------------------- | ------------------------------------- |
| Sales Analytics     | Revenue by item, category, date range |
| Gross Profit        | Revenue minus COGS per item           |
| Stock Ledger        | Full ingredient movement history      |
| Accounts Receivable | Open catering/corporate invoices      |
| Accounts Payable    | Outstanding supplier invoices         |
| Cash Flow           | Weekly/monthly cash position          |
| Trial Balance       | Full P&L and balance sheet            |

### Custom Restaurant Reports to build:

- **Sales by Revenue Center** (Dine-in vs Bar vs Takeout vs Online)
- **Top 20 Items by Revenue** (weekly)
- **Food Cost %** = COGS Food / Food Revenue (target: 28–32%)
- **Beverage Cost %** = COGS Bev / Bev Revenue (target: 18–24%)
- **Labor Cost %** (once payroll is connected)

---

## Phase 6 — HR & Payroll (Week 5–6, Optional)

- Import employee list from Toast (tip-outs, clock-in/out) into ERPNext HR
- Run payroll in ERPNext → posts labor cost to GL automatically
- ERPNext handles:
  - Hourly wages + overtime
  - Tip distribution records
  - Payroll tax entries
  - Direct deposit (via integration with Gusto or manual)

---

## Data Flow Summary

```
Customer orders in Toast
       │
       ▼
Toast closes order + charges payment
       │
       ▼
Toast fires webhook → Lambda
       │
       ├── Create Sales Invoice in ERPNext (revenue posted to GL)
       ├── Create Payment Entry in ERPNext (cash/AR cleared)
       └── Post Stock Entry in ERPNext (inventory depleted)
                          │
                          ▼
                 ERPNext Reports + Alerts
                 (low stock, unpaid invoices, P&L)
                          │
                          ▼
                 Manager reviews in ERPNext
                 Creates Purchase Orders to restock
```

---

## GitHub Actions Workflows to Add

| Workflow                | Purpose                                          |
| ----------------------- | ------------------------------------------------ |
| `sync-toast-menu.yml` | Pull Toast menu → update ERPNext item master    |
| `daily-reconcile.yml` | Compare Toast daily totals vs ERPNext invoices   |
| `stock-report.yml`    | Email daily inventory levels below reorder point |
| `deploy-lambda.yml`   | Deploy/update the Toast→ERPNext sync Lambda     |

---

## Cost Estimate (Monthly)

| Component                            | Cost                     |
| ------------------------------------ | ------------------------ |
| ERPNext on EC2 t3.micro (current)    | ~$10/mo                  |
| RDS MariaDB db.t3.micro (current)    | ~$15/mo                  |
| Lambda sync (millions of free calls) | ~$0                      |
| DynamoDB item mapping table          | ~$1/mo                   |
| Toast POS subscription               | $110+/mo (Toast pricing) |
| **Total AWS add-on**           | **~$1–2/mo**      |

---

## Next Steps

1. [ ] Get Toast API credentials from Toast Dashboard
2. [ ] Create item master in ERPNext matching Toast menu
3. [ ] Deploy Lambda sync function
4. [ ] Configure Toast webhook pointing to Lambda URL
5. [ ] Run one day in parallel (Toast + manual ERPNext) to validate numbers match
6. [ ] Go live — all sales auto-post to ERPNext
