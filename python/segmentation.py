"""
Customer segmentation via RFM (Recency, Frequency, Monetary) + K-Means.

Lives in: python/segmentation.py
Run from the python/ folder with: python segmentation.py

Requires: sql/migrations/003_create_ml_output_tables.sql already applied.

Outputs:
  - data/processed/rfm_features.csv         (raw RFM values per customer)
  - data/processed/customer_segments.csv    (RFM + cluster + segment_name)
  - data/processed/segment_profile.csv      (mean R/F/M per segment, for the
                                              Ollama narrative step later)
  - data/processed/kmeans_k_selection.png   (elbow + silhouette plot)
  - MySQL table `customer_segments`
"""

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # no display available when run from CLI
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text

from connection import get_engine

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = _PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# A "genuine sale" row: has a customer, isn't a cancellation or internal
# stock adjustment, and has a positive quantity/price. This deliberately
# also excludes returns, since those are negative-quantity rows.
GENUINE_SALE_FILTER = """
    customer_id IS NOT NULL
    AND is_cancellation = 0
    AND is_stock_adjustment = 0
    AND quantity > 0
    AND unit_price > 0
"""

RFM_QUERY = f"""
    SELECT
        customer_id,
        DATEDIFF(
            (SELECT MAX(invoice_date) FROM transactions),
            MAX(invoice_date)
        ) AS recency_days,
        COUNT(DISTINCT invoice_no) AS frequency,
        SUM(quantity * unit_price) AS monetary
    FROM transactions
    WHERE {GENUINE_SALE_FILTER}
    GROUP BY customer_id
"""


def pull_rfm() -> pd.DataFrame:
    """Compute raw RFM values per customer directly in SQL."""
    engine = get_engine()
    df = pd.read_sql(text(RFM_QUERY), con=engine)
    print(f"Pulled RFM data for {len(df):,} customers")
    return df


def engineer_features(rfm: pd.DataFrame) -> pd.DataFrame:
    """
    Log-transform Frequency/Monetary (both heavily right-skewed — a small
    number of high-volume customers otherwise dominate the distance metric)
    then standard-scale everything so R, F, and M contribute comparably to
    K-Means' Euclidean distance calculation.
    """
    features = rfm.copy()
    features["log_frequency"] = np.log1p(features["frequency"])
    features["log_monetary"] = np.log1p(features["monetary"].clip(lower=0))

    scale_cols = ["recency_days", "log_frequency", "log_monetary"]
    scaler = StandardScaler()
    scaled = scaler.fit_transform(features[scale_cols])
    scaled_df = pd.DataFrame(scaled, columns=[f"scaled_{c}" for c in scale_cols])

    return pd.concat([features.reset_index(drop=True), scaled_df], axis=1)


def find_optimal_k(scaled_matrix: np.ndarray, k_range=range(2, 9)) -> None:
    """
    Fit K-Means across a range of k, plot inertia (elbow) and silhouette
    score side by side, and save the plot. Doesn't auto-pick k — the elbow
    plot is genuinely ambiguous a lot of the time, so eyeball both panels
    and set K_CHOSEN below based on what you see.
    """
    inertias, silhouettes = [], []
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(scaled_matrix)
        inertias.append(km.inertia_)
        silhouettes.append(silhouette_score(scaled_matrix, labels))

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    axes[0].plot(list(k_range), inertias, marker="o")
    axes[0].set_title("Elbow Method (Inertia)")
    axes[0].set_xlabel("k")
    axes[0].set_ylabel("Inertia")

    axes[1].plot(list(k_range), silhouettes, marker="o", color="darkorange")
    axes[1].set_title("Silhouette Score")
    axes[1].set_xlabel("k")
    axes[1].set_ylabel("Silhouette score")

    fig.tight_layout()
    out_path = PROCESSED_DIR / "kmeans_k_selection.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)

    print(f"✅ Saved k-selection plot to {out_path}")
    for k, inertia, sil in zip(k_range, inertias, silhouettes):
        print(f"   k={k}: inertia={inertia:,.0f}  silhouette={sil:.3f}")


def fit_kmeans(features: pd.DataFrame, k: int) -> pd.DataFrame:
    scale_cols = ["scaled_recency_days", "scaled_log_frequency", "scaled_log_monetary"]
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    features = features.copy()
    features["cluster"] = km.fit_predict(features[scale_cols])
    return features


def label_segments(features: pd.DataFrame) -> pd.DataFrame:
    """
    Compare each cluster's centroid against the overall customer-base
    median on R, F, M (not against other clusters' ranks). Rank-based
    thresholds looked clean in theory but broke down at low k: with only
    3 clusters, a cluster sitting at the "middle" rank gets shoved into
    the worst-case bucket even when its recency is genuinely fine — e.g.
    a cluster with 53-day recency and low frequency isn't "Lost," it's a
    recently-acquired customer who hasn't built a habit yet. Comparing
    against the actual median avoids that.
    """
    medians = features[["recency_days", "frequency", "monetary"]].median()
    profile = features.groupby("cluster")[["recency_days", "frequency", "monetary"]].mean()

    def name_for(cluster_id: int) -> str:
        row = profile.loc[cluster_id]
        is_recent = row["recency_days"] <= medians["recency_days"]
        is_frequent = row["frequency"] >= medians["frequency"]
        is_high_spend = row["monetary"] >= medians["monetary"]

        if is_recent and is_frequent and is_high_spend:
            return "Champions"
        if not is_recent and not is_frequent and not is_high_spend:
            return "Lost / Lapsed"
        if is_recent and not is_frequent and not is_high_spend:
            return "New / Low-Engagement"
        if not is_recent and (is_frequent or is_high_spend):
            return "Occasional / Low-value"
        return "Regular"

    label_map = {c: name_for(c) for c in profile.index}
    features = features.copy()
    features["segment_name"] = features["cluster"].map(label_map)
    return features


def save_outputs(features: pd.DataFrame) -> None:
    out_cols = ["customer_id", "recency_days", "frequency", "monetary", "cluster", "segment_name"]
    result = features[out_cols]

    rfm_path = PROCESSED_DIR / "rfm_features.csv"
    result.to_csv(rfm_path, index=False)

    profile = (
        result.groupby(["cluster", "segment_name"])[["recency_days", "frequency", "monetary"]]
        .agg(["mean", "count"])
    )
    profile_path = PROCESSED_DIR / "segment_profile.csv"
    profile.to_csv(profile_path)

    print(f"✅ Saved {rfm_path.name} and {profile_path.name}")
    print("\nSegment profile:")
    print(profile)

    engine = get_engine()
    with engine.begin() as conn:
        # customer_id is a PRIMARY KEY, so clear old results before
        # reinserting rather than appending (this script is meant to be
        # rerunnable as you tune k or your cleaning rules).
        conn.execute(text("TRUNCATE TABLE customer_segments"))

    result.to_sql(
        "customer_segments",
        con=engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=2000,
    )
    print(f"\n✅ Wrote {len(result):,} rows to MySQL table `customer_segments`")


if __name__ == "__main__":
    # Step 1: pull + engineer features
    rfm = pull_rfm()
    features = engineer_features(rfm)
    scale_cols = ["scaled_recency_days", "scaled_log_frequency", "scaled_log_monetary"]

    # Step 2: help you pick k — inspect the saved PNG, then set K_CHOSEN
    find_optimal_k(features[scale_cols].to_numpy())

    K_CHOSEN = 3  # chosen from silhouette score (~0.41 at k=3) + elbow plot

    # Step 3: fit final model, label clusters, save everywhere
    features = fit_kmeans(features, k=K_CHOSEN)
    features = label_segments(features)
    save_outputs(features)