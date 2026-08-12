-- Step 6: table to hold Ollama-generated plain-English narratives.
-- Lives in: sql/migrations/004_create_narratives_table.sql
-- Apply with: mysql -u root -p ai_sales_analytics < sql/migrations/004_create_narratives_table.sql

CREATE TABLE IF NOT EXISTS narratives (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    narrative_type  VARCHAR(30)     NOT NULL,  -- 'segment' | 'anomaly' | 'executive'
    reference_key   VARCHAR(50),               -- e.g. segment_name; NULL for 'executive'
    input_stats     JSON            NOT NULL,  -- exact numbers fed to the LLM, kept for audit/verification
    narrative_text  TEXT            NOT NULL,
    generated_at    TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_narrative_type (narrative_type)
) ENGINE=InnoDB;