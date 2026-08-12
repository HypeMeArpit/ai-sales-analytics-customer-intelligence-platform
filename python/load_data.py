"""
Loads the Online Retail CSV from data/raw/ into the `transactions` table.

Lives in: python/load_data.py
Run from the python/ folder with: python load_data.py
"""

from pathlib import Path

import pandas as pd

from connection import get_engine

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = _PROJECT_ROOT / "data" / "raw"

COLUMN_MAP = {
    "Invoice": "invoice_no",
    "StockCode": "stock_code",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoice_date",
    "Price": "unit_price",
    "Customer ID": "customer_id",
    "Country": "country",
}


def find_data_file() -> Path:
    # Kaggle serves this dataset as .xlsx, but fall back to .csv in case
    # that ever changes.
    files = list(RAW_DIR.glob("*.xlsx")) + list(RAW_DIR.glob("*.csv"))
    if not files:
        raise FileNotFoundError(
            f"No .xlsx or .csv found in {RAW_DIR}. Run `python download_data.py` first."
        )
    if len(files) > 1:
        print(f"⚠️  Multiple data files found, using the first: {files[0].name}")
    return files[0]


def load_and_clean(data_path: Path) -> pd.DataFrame:
    if data_path.suffix == ".xlsx":
        df = pd.read_excel(data_path)  # requires openpyxl, already in requirements.txt
    else:
        df = pd.read_csv(data_path, encoding="latin-1")

    df = df.rename(columns=COLUMN_MAP)

    expected = set(COLUMN_MAP.values())
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(
            f"CSV is missing expected columns: {missing}. "
            f"Found columns: {list(df.columns)}"
        )

    df = df[list(COLUMN_MAP.values())]

    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df["customer_id"] = pd.to_numeric(df["customer_id"], errors="coerce").astype("Int64")

    before = len(df)
    df = df.dropna(subset=["invoice_no", "stock_code", "invoice_date", "quantity", "unit_price"])
    dropped = before - len(df)
    if dropped:
        print(f"⚠️  Dropped {dropped} rows with unusable core fields (out of {before})")

    return df


def load_to_mysql(df: pd.DataFrame, if_exists: str = "append") -> None:
    engine = get_engine()
    df.to_sql(
        "transactions",
        con=engine,
        if_exists=if_exists,
        index=False,
        chunksize=5000,
        method="multi",
    )
    print(f"✅ Loaded {len(df):,} rows into `transactions`")


if __name__ == "__main__":
    data_path = find_data_file()
    print(f"Reading {data_path.name} ...")
    df = load_and_clean(data_path)
    load_to_mysql(df)