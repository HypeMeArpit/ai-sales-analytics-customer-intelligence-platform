-- Follow-up to 04_duplicate_and_date_checks.sql, check #4.
-- Lives in: sql/queries/cancellation_quantity_edge_cases.sql

-- Case A: negative quantity, but invoice does NOT start with 'C'.
-- Likely stock adjustments / damages / write-offs rather than customer
-- cancellations. Look at stock_code and description to confirm.
SELECT stock_code, description, quantity, unit_price, invoice_no, customer_id, country
FROM transactions
WHERE is_cancellation = 0 AND quantity < 0
ORDER BY quantity ASC
LIMIT 30;

-- Quick tally of what stock_codes/descriptions dominate that group --
-- if it's mostly a handful of known "adjustment" codes, that's an easy story.
SELECT stock_code, description, COUNT(*) AS occurrences, SUM(quantity) AS total_qty
FROM transactions
WHERE is_cancellation = 0 AND quantity < 0
GROUP BY stock_code, description
ORDER BY occurrences DESC
LIMIT 20;

-- Case B: invoice starts with 'C' but quantity is NOT negative. Just one row --
-- pull it directly to see what's going on.
SELECT *
FROM transactions
WHERE is_cancellation = 1 AND quantity >= 0;