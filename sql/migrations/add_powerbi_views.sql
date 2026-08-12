-- Step 7 (Power BI): convenience view joining flagged anomalies back to
-- their full transaction detail, so Power BI doesn't need to do this merge
-- itself in Power Query.
-- Lives in: sql/migrations/add_powerbi_views.sql
-- Apply with: mysql -u root -p ai_sales_analytics < sql/migrations/add_powerbi_views.sql

CREATE OR REPLACE VIEW vw_anomaly_detail AS
SELECT
    t.id             AS transaction_id,
    t.invoice_no,
    t.customer_id,
    t.country,
    t.quantity,
    t.unit_price,
    (t.quantity * t.unit_price) AS total_value,
    t.invoice_date,
    ta.anomaly_score,
    ta.is_anomaly
FROM transaction_anomalies ta
JOIN transactions t ON t.id = ta.transaction_id;