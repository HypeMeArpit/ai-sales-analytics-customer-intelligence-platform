-- Initial schema for the Online Retail dataset.
-- Lives in: sql/schema.sql
-- Applied by: python/init_db.py

CREATE TABLE IF NOT EXISTS transactions (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    invoice_no      VARCHAR(20)     NOT NULL,
    stock_code      VARCHAR(20)     NOT NULL,
    description     VARCHAR(255),
    quantity        INT             NOT NULL,
    invoice_date    DATETIME        NOT NULL,
    unit_price      DECIMAL(10, 2)  NOT NULL,
    customer_id     INT,
    country         VARCHAR(100),
    is_cancellation BOOLEAN         GENERATED ALWAYS AS (invoice_no LIKE 'c%') STORED,

    INDEX idx_invoice_no   (invoice_no),
    INDEX idx_customer_id  (customer_id),
    INDEX idx_stock_code   (stock_code),
    INDEX idx_invoice_date (invoice_date)
) ENGINE=InnoDB;