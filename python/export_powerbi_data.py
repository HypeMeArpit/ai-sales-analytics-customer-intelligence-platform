"""
Exports the tables/views Power BI needs into small, git-friendly CSVs, so
the dashboard is reviewable without a live MySQL connection (the .pbix
itself connects live to MySQL — this is the fallback/reference copy, same
"processed data is tracked in git" logic used elsewhere in this project).

Lives in: python/export_powerbi_data.py
Run from the python/ folder with: python export_powerbi_data.py

Requires: sql/migrations/005_add_powerbi_views.sql already applied.

Outputs (all under data/processed/powerbi_export/):
  - overview_daily_revenue.csv   (date-level revenue/order trend)
  - top_products.csv             (top 20 products by revenue)
  - customer_segments.csv        (full segment table, ~4,312 rows)
  - anomaly_detail.csv           (flagged transactions only, ~4,077 rows)
  - narratives.csv               (latest narrative per type/reference_key)
"""

from pathlib import Path

import pandas as pd

from connection import get_engine

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = _PROJECT_ROOT / "data" / "processed" / "powerbi_export"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

DAILY_REVENUE_QUERY = """
    SELECT
        DATE(invoice_date)            AS invoice_date,
        COUNT(DISTINCT invoice_no)    AS order_count,
        SUM(quantity * unit_price)    AS revenue
    FROM vw_revenue_transactions
    GROUP BY DATE(invoice_date)
    ORDER BY invoice_date
"""

TOP_PRODUCTS_QUERY = """
    SELECT
        stock_code,
        description,
        SUM(quantity)               AS units_sold,
        SUM(quantity * unit_price)  AS revenue
    FROM vw_revenue_transactions
    GROUP BY stock_code, description
    ORDER BY revenue DESC
    LIMIT 20
"""

SEGMENTS_QUERY = "SELECT * FROM customer_segments"

# Anomaly detail export is intentionally limited to flagged rows only
# (is_anomaly = 1) — the point of this export is "what got flagged and
# why", not a full copy of every scored transaction.
ANOMALY_DETAIL_QUERY = """
    SELECT *
    FROM vw_anomaly_detail
    WHERE is_anomaly = 1
    ORDER BY anomaly_score DESC
"""

# One row per narrative_type/reference_key, keeping only the most recent —
# guards against the duplicate rows left behind by reruns of
# generate_narratives.py (see interview_prep_qa.txt, Section 7).
LATEST_NARRATIVES_QUERY = """
    SELECT n.narrative_type, n.reference_key, n.narrative_text, n.generated_at
    FROM narratives n
    INNER JOIN (
        SELECT narrative_type, reference_key, MAX(generated_at) AS max_generated_at
        FROM narratives
        GROUP BY narrative_type, reference_key
    ) latest
      ON n.narrative_type = latest.narrative_type
     AND n.reference_key <=> latest.reference_key
     AND n.generated_at = latest.max_generated_at
"""


def export_query(query: str, filename: str) -> None:
    engine = get_engine()
    df = pd.read_sql(query, con=engine)
    out_path = EXPORT_DIR / filename
    df.to_csv(out_path, index=False)
    print(f"✅ Wrote {len(df):,} rows to {out_path.relative_to(_PROJECT_ROOT)}")


if __name__ == "__main__":
    export_query(DAILY_REVENUE_QUERY, "overview_daily_revenue.csv")
    export_query(TOP_PRODUCTS_QUERY, "top_products.csv")
    export_query(SEGMENTS_QUERY, "customer_segments.csv")
    export_query(ANOMALY_DETAIL_QUERY, "anomaly_detail.csv")
    export_query(LATEST_NARRATIVES_QUERY, "narratives.csv")
    print("\n✅ Done — Power BI export files are ready in data/processed/powerbi_export/")