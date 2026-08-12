"""
Validates the data-quality flags added by
sql/migrations/data_quality_flags.sql, and writes a summary CSV
into data/processed/ for use in the README's data-quality section.

Lives in: python/validate_cleaning.py
Run from the python/ folder with: python validate_cleaning.py
Requires: the migration and sql/views.sql have already been applied.
"""

from pathlib import Path

import pandas as pd

from connection import get_engine

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = _PROJECT_ROOT / "data" / "processed" / "cleaning_summary.csv"

QUERY = """
SELECT
    COUNT(*)                AS total_rows,
    SUM(is_missing_customer) AS missing_customer_id,
    SUM(is_return)           AS negative_quantity,
    SUM(is_invalid_price)    AS zero_or_negative_price,
    SUM(is_non_product)      AS non_product_stock_codes,
    SUM(is_cancellation)     AS cancellation_invoices,
    SUM(is_stock_adjustment) AS stock_adjustments
FROM transactions
"""


def main() -> None:
    engine = get_engine()
    counts = pd.read_sql(QUERY, engine)

    summary = counts.T.rename(columns={0: "count"})
    summary["pct_of_total"] = (
        summary["count"] / counts["total_rows"].iloc[0] * 100
    ).round(2)
    summary.loc["total_rows", "pct_of_total"] = 100.0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUT_PATH)

    print(summary)
    print(f"\n✅ Summary written to {OUT_PATH}")


if __name__ == "__main__":
    main()