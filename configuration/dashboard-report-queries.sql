-- ERPNext Dashboard Query Templates (MariaDB)
-- Use these in Query Report / Dashboard Chart sources.

-- 1) Daily Sales (last 30 days)
SELECT
    si.posting_date AS day,
    ROUND(SUM(si.grand_total), 2) AS sales_total
FROM `tabSales Invoice` si
WHERE si.docstatus = 1
  AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
GROUP BY si.posting_date
ORDER BY si.posting_date;


-- 2) Top 10 Items by Revenue (this month)
SELECT
    sii.item_code,
    sii.item_name,
    ROUND(SUM(sii.amount), 2) AS revenue,
    ROUND(SUM(sii.qty), 2) AS qty_sold
FROM `tabSales Invoice Item` sii
INNER JOIN `tabSales Invoice` si
    ON si.name = sii.parent
WHERE si.docstatus = 1
  AND YEAR(si.posting_date) = YEAR(CURDATE())
  AND MONTH(si.posting_date) = MONTH(CURDATE())
GROUP BY sii.item_code, sii.item_name
ORDER BY revenue DESC
LIMIT 10;


-- 3) Overdue Invoices table
SELECT
    si.name AS invoice,
    si.customer,
    si.posting_date,
    si.due_date,
    ROUND(si.grand_total, 2) AS grand_total,
    ROUND(si.outstanding_amount, 2) AS outstanding_amount,
    DATEDIFF(CURDATE(), si.due_date) AS days_overdue
FROM `tabSales Invoice` si
WHERE si.docstatus = 1
  AND si.outstanding_amount > 0
  AND si.due_date < CURDATE()
ORDER BY si.due_date ASC;


-- 4) Recurring invoices due in next 7 days
-- Note: This reports Auto Repeat records and their next schedule date.
SELECT
    ar.name,
    ar.reference_doctype,
    ar.reference_document,
    ar.frequency,
    ar.next_schedule_date,
    ar.status,
    ar.owner
FROM `tabAuto Repeat` ar
WHERE ar.disabled = 0
  AND ar.reference_doctype = 'Sales Invoice'
  AND ar.next_schedule_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)
ORDER BY ar.next_schedule_date ASC;


-- 5) Receivables aging snapshot by customer
SELECT
    si.customer,
    ROUND(SUM(CASE WHEN DATEDIFF(CURDATE(), si.due_date) <= 30 THEN si.outstanding_amount ELSE 0 END), 2) AS bucket_0_30,
    ROUND(SUM(CASE WHEN DATEDIFF(CURDATE(), si.due_date) BETWEEN 31 AND 60 THEN si.outstanding_amount ELSE 0 END), 2) AS bucket_31_60,
    ROUND(SUM(CASE WHEN DATEDIFF(CURDATE(), si.due_date) BETWEEN 61 AND 90 THEN si.outstanding_amount ELSE 0 END), 2) AS bucket_61_90,
    ROUND(SUM(CASE WHEN DATEDIFF(CURDATE(), si.due_date) > 90 THEN si.outstanding_amount ELSE 0 END), 2) AS bucket_90_plus,
    ROUND(SUM(si.outstanding_amount), 2) AS total_outstanding
FROM `tabSales Invoice` si
WHERE si.docstatus = 1
  AND si.outstanding_amount > 0
GROUP BY si.customer
ORDER BY total_outstanding DESC;
