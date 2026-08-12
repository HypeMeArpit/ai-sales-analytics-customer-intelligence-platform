-- Adds data-quality flag columns to `transactions`.
-- Lives in: sql/migrations/data_quality_flags.sql
-- Run this ONCE, after sql/schema.sql has been applied and data is loaded.
--
-- These are STORED generated columns -- same pattern as is_cancellation in
-- schema.sql. Nothing is deleted or overwritten; every row stays, just with
-- extra columns describing what's "off" about it, if anything.

ALTER TABLE transactions
    ADD COLUMN is_missing_customer BOOLEAN GENERATED ALWAYS AS (customer_id IS NULL) STORED,
    ADD COLUMN is_return           BOOLEAN GENERATED ALWAYS AS (quantity < 0) STORED,
    ADD COLUMN is_invalid_price    BOOLEAN GENERATED ALWAYS AS (unit_price <= 0) STORED,
    ADD COLUMN is_non_product      BOOLEAN GENERATED ALWAYS AS (
        stock_code IN ('POST', 'M', 'DOT', 'C2', 'BANK CHARGES', 'AMAZONFEE')
    ) STORED,
    -- Negative quantity but NOT a customer-initiated cancellation (invoice_no
    -- doesn't start with 'C'). Investigation showed these are mostly NULL
    -- descriptions plus "given away" / "damaged" / "ebay sales" -- i.e.
    -- warehouse-side stock corrections, not customer returns.
    ADD COLUMN is_stock_adjustment BOOLEAN GENERATED ALWAYS AS (
        quantity < 0 AND invoice_no NOT LIKE 'C%'
    ) STORED;

-- Index the flags you'll filter on most often.
ALTER TABLE transactions
    ADD INDEX idx_is_missing_customer (is_missing_customer),
    ADD INDEX idx_is_non_product (is_non_product),
    ADD INDEX idx_is_stock_adjustment (is_stock_adjustment);