-- Step 6 follow-up: enforce one current narrative per (narrative_type, reference_key)
-- so generate_narratives.py can upsert instead of appending duplicate rows on rerun.
-- Lives in: sql/migrations/add_narratives_unique_key.sql
-- Apply with: mysql -u root -p ai_sales_analytics < sql/migrations/add_narratives_unique_key.sql

-- Before adding the constraint, collapse any existing duplicates down to the
-- most recent row per (narrative_type, reference_key) — otherwise the ALTER
-- TABLE below will fail if reruns have already produced duplicates.
DELETE n1 FROM narratives n1
INNER JOIN narratives n2
    ON n1.narrative_type = n2.narrative_type
   AND n1.reference_key <=> n2.reference_key   -- <=> so NULL = NULL matches (executive narrative has NULL reference_key)
   AND n1.id < n2.id;                          -- keep the highest id (most recent) per group

-- reference_key is nullable (NULL for the 'executive' narrative), and MySQL
-- treats multiple NULLs as distinct under a normal UNIQUE index — which would
-- silently defeat this constraint for the one row that needs it most. A
-- generated column that substitutes a sentinel for NULL keeps the uniqueness
-- rule meaningful without changing what reference_key means anywhere else.
ALTER TABLE narratives
    ADD COLUMN reference_key_norm VARCHAR(50)
        GENERATED ALWAYS AS (COALESCE(reference_key, '__none__')) STORED,
    ADD UNIQUE KEY uq_narrative_type_reference (narrative_type, reference_key_norm);