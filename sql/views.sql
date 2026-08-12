-- Analysis-ready views on top of `transactions`.
-- Lives in: sql/views.sql
-- Run this AFTER sql/migrations/002_add_data_quality_flags.sql.
--
-- The raw table is never filtered in place -- each view just applies a
-- different lens over the same underlying data, so you can always point to
-- "nothing was deleted" in your README / interview walkthrough.

-- Revenue / product-level analysis: drops non-product noise rows (POST,
-- BANK CHARGES, etc.), rows with an invalid price, and internal stock
-- adjustments (damages, giveaways -- not customer transactions). Genuine
-- customer cancellations (is_cancellation) ARE kept -- they're real
-- transactions, just netted out at the aggregation level instead of being
-- excluded outright.
CREATE OR REPLACE VIEW vw_revenue_transactions AS
SELECT *
FROM transactions
WHERE is_non_product = FALSE
  AND is_invalid_price = FALSE
  AND is_stock_adjustment = FALSE;

-- Customer segmentation: additionally drops guest/anonymous orders, since
-- they can't be tied to a customer for RFM / clustering work.
CREATE OR REPLACE VIEW vw_customer_transactions AS
SELECT *
FROM vw_revenue_transactions
WHERE is_missing_customer = FALSE;

-- Net sales per product: nets returns against purchases rather than
-- excluding either side, so revenue totals reflect what actually happened.
CREATE OR REPLACE VIEW vw_net_sales AS
SELECT
    stock_code,
    description,
    SUM(quantity)               AS net_quantity,
    SUM(quantity * unit_price)  AS net_revenue
FROM vw_revenue_transactions
GROUP BY stock_code, description;