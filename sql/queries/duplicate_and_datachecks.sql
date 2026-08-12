-- Step 4 data-cleaning exploration.
-- Lives in: sql/queries/duplicate_and_date_checks.sql
-- Run these before applying the migration, so you know what you're dealing with.

-- 1) Exact duplicate rows (every column identical).
--    Note: this is NOT the same as two separate orders for the same product --
--    those are legitimate. This only flags rows that are byte-for-byte repeats.
SELECT
    invoice_no, stock_code, description, quantity,
    invoice_date, unit_price, customer_id, country,
    COUNT(*) AS occurrences
FROM transactions
GROUP BY invoice_no, stock_code, description, quantity,
         invoice_date, unit_price, customer_id, country
HAVING COUNT(*) > 1
ORDER BY occurrences DESC;

-- 2) Overall date range -- sanity check against the known dataset window
--    (Online Retail dataset should span ~Dec 2010 to Dec 2011).
SELECT
    MIN(invoice_date) AS earliest,
    MAX(invoice_date) AS latest,
    COUNT(*)          AS total_rows
FROM transactions;

-- 3) Any rows outside that expected window? (typos, bad parses, etc.)
SELECT *
FROM transactions
WHERE invoice_date < '2010-12-01' OR invoice_date > '2011-12-31'
LIMIT 50;

-- 4) Does is_cancellation (invoice starts with 'C') always line up with a
--    negative quantity? If not, that's worth a note in your README --
--    it means "cancellation" and "return" aren't perfectly interchangeable.
SELECT
    is_cancellation,
    (quantity < 0) AS is_negative_qty,
    COUNT(*)        AS row_count
FROM transactions
GROUP BY is_cancellation, is_negative_qty;
