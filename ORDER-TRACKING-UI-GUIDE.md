# ERPNext Sales Order Tracking — UI Guide

Full lifecycle tracking of a Sales Order from creation to confirmed delivery,
with automatic notifications to both your team and the customer at every step.
No code required — all done through the ERPNext browser UI.

---

## The Order Lifecycle

Every order moves through these documents in sequence:

```
Sales Order → Pick List → Delivery Note → Sales Invoice → Payment Entry
     │              │            │               │
 "Confirmed"   "Picking"   "Shipped /        "Billed"
                           Delivered"
```

The **status on the Sales Order** auto-updates as each step is completed.

---

## 1 — Create a Sales Order

**Path:** Selling → Sales Order → New

| Field | What to fill |
|---|---|
| Customer | Select the customer |
| Delivery Date | The promised delivery date |
| Items | Add each item with qty and rate |
| Shipping Address | Customer's delivery address |

Click **Save** → then **Submit**. The order is now **To Deliver and Bill**.

---

## 2 — Sales Order Status — What Each Means

| Status | Meaning |
|---|---|
| **Draft** | Not confirmed yet — customer hasn't been notified |
| **To Deliver and Bill** | Confirmed, nothing shipped yet |
| **To Bill** | Delivered but not yet invoiced |
| **To Deliver** | Invoiced/paid but delivery still pending |
| **Completed** | Fully delivered and billed |
| **Cancelled** | Order was cancelled |
| **On Hold** | Paused manually |

---

## 3 — Pick List (Warehouse Picking)

Before shipping, create a Pick List so your team knows what to pull.

1. Open the Sales Order → click **Make → Pick List**
2. The Pick List shows each item + bin location
3. Warehouse staff marks items as picked → **Submit**

**View all open picks:** Stock → Pick List → filter `Status = Open`

---

## 4 — Delivery Note (Mark as Shipped)

Submitting a Delivery Note is what marks an order as dispatched.

1. Open the Sales Order → click **Make → Delivery Note**
2. Verify quantities
3. Fill the **Shipping Details** section:
   - **Transporter Name** — carrier (FedEx, UPS, in-house, etc.)
   - **LR No** — tracking number
   - **LR Date** — dispatch date
4. Click **Submit**

The Sales Order status automatically flips to **To Bill**.

**View all deliveries in transit:** Stock → Delivery Note List → filter `Status = Submitted`

---

## 5 — Confirm Customer Received the Delivery

### Option A — Log it manually
1. Open the Delivery Note
2. Scroll to **More Information → Instructions**
3. Add a note: `Delivered and confirmed by customer on [date]`
4. Save — timestamped in the activity log

### Option B — Customer Portal (self-service confirmation)
1. **Settings → Portal Settings** → enable **Delivery Notes**
2. Customer logs in at `https://<your-erpnext-domain>/me`
3. They see their delivery, can confirm receipt
4. Confirmation is logged with their timestamp

---

## 6 — Notifications Setup — Step by Step

Go to **Settings → Notifications → New** and create one rule per event below.
Set them all up once — they fire automatically forever.

---

### 6.1 Internal — New Order Created

Alerts your team the moment a Sales Order is submitted.

| Field | Value |
|---|---|
| Document Type | `Sales Order` |
| Event | `On Submit` |
| Subject | `New Order: {{ doc.name }} from {{ doc.customer_name }}` |
| Recipients | Your team / ops email(s) |
| Message | `Order {{ doc.name }} confirmed for {{ doc.customer_name }}.`<br>`Delivery by: {{ doc.delivery_date }}`<br>`Total: {{ doc.grand_total }}` |

---

### 6.2 Customer — Order Confirmation

Sends the customer a confirmation email immediately after order is placed.

| Field | Value |
|---|---|
| Document Type | `Sales Order` |
| Event | `On Submit` |
| Subject | `Your Order {{ doc.name }} is Confirmed` |
| Recipients | `{{ doc.contact_email }}` |
| Message | `Hi {{ doc.customer_name }},`<br><br>`Your order {{ doc.name }} has been confirmed.`<br>`Expected delivery: {{ doc.delivery_date }}`<br>`Total: {{ doc.grand_total }}`<br><br>`We'll notify you when it ships.` |

---

### 6.3 Internal — Delivery Due Tomorrow (Not Shipped Yet)

Warns your team the day before an order is due with nothing dispatched.

| Field | Value |
|---|---|
| Document Type | `Sales Order` |
| Event | `Days Before` |
| Days Before | `1` |
| Date Field | `delivery_date` |
| Condition | `doc.per_delivered < 100` |
| Subject | `⚠️ Delivery Due Tomorrow: {{ doc.name }}` |
| Recipients | Warehouse / ops team |
| Message | `Order {{ doc.name }} for {{ doc.customer_name }} is due tomorrow and has not been fully shipped yet. Delivered so far: {{ doc.per_delivered }}%` |

---

### 6.4 Customer — Order Shipped

Fires the moment a Delivery Note is submitted (goods leave the building).

| Field | Value |
|---|---|
| Document Type | `Delivery Note` |
| Event | `On Submit` |
| Subject | `Your Order Has Been Dispatched — {{ doc.name }}` |
| Recipients | `{{ doc.contact_email }}` |
| Message | `Hi {{ doc.customer_name }},`<br><br>`Your order has been dispatched.`<br>`Carrier: {{ doc.transporter_name }}`<br>`Tracking #: {{ doc.lr_no }}`<br>`Dispatch Date: {{ doc.lr_date }}`<br><br>`You should receive it by your confirmed delivery date.` |

---

### 6.5 Internal — Overdue Delivery

Fires the day after delivery was due if the order is still not fully delivered.

| Field | Value |
|---|---|
| Document Type | `Sales Order` |
| Event | `Days After` |
| Days After | `1` |
| Date Field | `delivery_date` |
| Condition | `doc.per_delivered < 100` |
| Subject | `🚨 Overdue Delivery: {{ doc.name }}` |
| Recipients | Manager + ops team |
| Message | `Order {{ doc.name }} for {{ doc.customer_name }} was due {{ doc.delivery_date }} and is NOT fully delivered. Delivered: {{ doc.per_delivered }}%` |

---

### 6.6 Customer — Invoice Ready

Notifies the customer when their invoice is created after delivery.

| Field | Value |
|---|---|
| Document Type | `Sales Invoice` |
| Event | `On Submit` |
| Subject | `Invoice {{ doc.name }} — {{ doc.grand_total }}` |
| Recipients | `{{ doc.contact_email }}` |
| Message | `Hi {{ doc.customer_name }},`<br><br>`Invoice {{ doc.name }} for {{ doc.grand_total }} is ready.`<br>`Due date: {{ doc.due_date }}`<br><br>`Log in to your portal to view and download it.` |

---

### 6.7 Internal — Invoice Overdue (Unpaid)

Fires the day payment is due and the invoice is still outstanding.

| Field | Value |
|---|---|
| Document Type | `Sales Invoice` |
| Event | `Days After` |
| Days After | `0` |
| Date Field | `due_date` |
| Condition | `doc.outstanding_amount > 0` |
| Subject | `💰 Overdue Invoice: {{ doc.name }} — {{ doc.customer_name }}` |
| Recipients | Finance / accounts team |
| Message | `Invoice {{ doc.name }} for {{ doc.customer_name }} is overdue.`<br>`Outstanding: {{ doc.outstanding_amount }}`<br>`Due date: {{ doc.due_date }}` |

---

## 7 — Live Delivery Tracking Dashboard

1. **Selling → Sales Order List**
2. Add columns: `Customer`, `Delivery Date`, `% Delivered`, `Status`, `Grand Total`
   - Click **Menu (⋮) → Customize List View** to add columns
3. Set a saved filter: `Status = To Deliver and Bill`
4. For a visual board: click the **Kanban** icon → Group By **Status** → drag orders across columns as they move

---

## 8 — Customer Portal

Customers can log in and see all their orders, shipments, and invoices without calling you.

1. **Settings → Portal Settings** → enable:
   - ✅ Orders (Sales Order)
   - ✅ Delivery (Delivery Note)
   - ✅ Invoices (Sales Invoice)
2. **CRM → Contact** → open the customer → assign them a **User account**
3. Customer accesses: `https://<your-erpnext-domain>/me`

---

## 9 — Quick Reference

| What you need | Path |
|---|---|
| All active orders | Selling → Sales Order List → Status = To Deliver and Bill |
| Orders due this week | Sales Order List → Delivery Date = this week |
| In-transit shipments | Stock → Delivery Note List → Status = Submitted |
| Overdue deliveries | Sales Order List → Delivery Date < today + % Delivered < 100 |
| All notification rules | Settings → Notifications |
| Customer portal | `https://<your-erpnext-domain>/me` |
| Outstanding payments | Accounts → Accounts Receivable |
| Full order history per customer | CRM → Customer → open record → scroll to Sales Orders section |
