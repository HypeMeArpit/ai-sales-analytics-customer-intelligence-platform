"""
Transaction-level anomaly detection via Isolation Forest.

This is a statistical/unsupervised complement to the rule-based data-quality
flags (is_cancellation, is_return, is_stock_adjustment) — it catches unusual
*combinations* of values (e.g. a huge quantity at an unusually high price)
that no fixed business rule was written to check for.

Lives in: python/anomaly_detection.py
Run from the python/ folder with: python anomaly_detection.py

Requires: sql/migrations/003_create_ml_output_tables.sql already applied.

Outputs:
  - data/processed/transaction_anomalies_top50.csv  (most anomalous rows,
                                                       for manual review)
  - MySQL table `transaction_anomalies`
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sqlalchemy import text

from connection import get_engine

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = _PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Same "genuine sale" definition used in segmentation.py — anomaly detection
# on cancellations/adjustments would just rediscover rows we've already
# flagged with business rules, which isn't the point of this layer.
GENUINE_SALE_FILTER = """
    customer_id IS NOT NULL
    AND is_cancellation = 0
    AND is_stock_adjustment = 0
    AND quantity > 0
    AND unit_price > 0
"""

TRANSACTIONS_QUERY = f"""
    SELECT
        id,
        customer_id,
        quantity,
        unit_price,
        (quantity * unit_price) AS total_value,
        HOUR(invoice_date) AS invoice_hour,
        DAYOFWEEK(invoice_date) AS invoice_dow
    FROM transactions
    WHERE {GENUINE_SALE_FILTER}
    ORDER BY id
"""

CONTAMINATION = 0.01  # assume ~1% of genuine-sale rows are anomalous


def pull_transactions() -> pd.DataFrame:
    engine = get_engine()
    df = pd.read_sql(text(TRANSACTIONS_QUERY), con=engine)
    print(f"Pulled {len(df):,} genuine-sale transactions for anomaly scoring")
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Log-transform quantity/price/total_value (all heavily right-skewed —
    most orders are small, a few are huge) so Isolation Forest's random
    splits aren't dominated by raw magnitude alone.
    """
    df = df.copy()
    df["log_quantity"] = np.log1p(df["quantity"])
    df["log_unit_price"] = np.log1p(df["unit_price"])
    df["log_total_value"] = np.log1p(df["total_value"])
    return df


def fit_isolation_forest(df: pd.DataFrame) -> pd.DataFrame:
    feature_cols = ["log_quantity", "log_unit_price", "log_total_value", "invoice_hour", "invoice_dow"]

    model = IsolationForest(
        n_estimators=200,
        contamination=CONTAMINATION,
        random_state=42,
        n_jobs=-1,
    )
    df = df.copy()
    # decision_function: higher = more normal, lower/negative = more anomalous.
    # Flip sign so higher anomaly_score = more anomalous (more intuitive
    # for a business audience reading the output table).
    df["anomaly_score"] = -model.fit(df[feature_cols]).decision_function(df[feature_cols])
    df["is_anomaly"] = model.predict(df[feature_cols]) == -1
    return df


def save_outputs(df: pd.DataFrame) -> None:
    n_flagged = df["is_anomaly"].sum()
    print(f"\nFlagged {n_flagged:,} anomalous transactions out of {len(df):,} ({n_flagged / len(df):.2%})")

    top50 = df.sort_values("anomaly_score", ascending=False).head(50)
    top50_cols = ["id", "customer_id", "quantity", "unit_price", "total_value", "anomaly_score"]
    top_path = PROCESSED_DIR / "transaction_anomalies_top50.csv"
    top50[top50_cols].to_csv(top_path, index=False)
    print(f"✅ Saved {top_path.name} for manual review")

    out = df[["id", "anomaly_score", "is_anomaly"]].rename(columns={"id": "transaction_id"})

    engine = get_engine()
    with engine.begin() as conn:
        # transaction_id is a PRIMARY KEY, so clear old results before
        # reinserting rather than appending — this script is rerunnable.
        conn.execute(text("TRUNCATE TABLE transaction_anomalies"))

    out.to_sql(
        "transaction_anomalies",
        con=engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=5000,
    )
    print(f"✅ Wrote {len(out):,} rows to MySQL table `transaction_anomalies`")


if __name__ == "__main__":
    df = pull_transactions()
    df = engineer_features(df)
    df = fit_isolation_forest(df)
    save_outputs(df)