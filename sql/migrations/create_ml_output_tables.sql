-- Step 5: tables to hold ML output (customer segments + transaction anomalies).
-- Lives in: sql/migrations/create_ml_output_tables.sql
-- Apply with: mysql -u root -p ai_sales_analytics < sql/migrations/create_ml_output_tables.sql
-- (or run the statements through your MySQL client of choice)

CREATE TABLE IF NOT EXISTS customer_segments (
    customer_id     INT             PRIMARY KEY,
    recency_days    INT             NOT NULL,
    frequency       INT             NOT NULL,
    monetary        DECIMAL(12, 2)  NOT NULL,
    cluster         INT             NOT NULL,
    segment_name    VARCHAR(50)     NOT NULL,
    updated_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_cluster (cluster)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS transaction_anomalies (
    transaction_id  INT             PRIMARY KEY,
    anomaly_score   DECIMAL(10, 6)  NOT NULL,
    is_anomaly      BOOLEAN         NOT NULL,
    updated_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_is_anomaly (is_anomaly),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
) ENGINE=InnoDB;