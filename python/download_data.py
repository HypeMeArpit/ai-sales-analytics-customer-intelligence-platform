"""
Downloads the Online Retail dataset from Kaggle into data/raw/.

Lives in: python/download_data.py
Run from the python/ folder with: python download_data.py

Dataset: lakshmi25npathi/online-retail-dataset

Auth:
  Needs a Kaggle API token. Either:
    1) ~/.kaggle/kaggle.json  (Kaggle's default location), or
    2) KAGGLE_USERNAME + KAGGLE_KEY set in your .env (project root)
"""

import os
import zipfile
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

DATASET_SLUG = "lakshmi25npathi/online-retail-dataset"
RAW_DIR = _PROJECT_ROOT / "data" / "raw"


def _ensure_kaggle_env() -> None:
    if os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY"):
        return  # already set, kaggle lib will use these directly

    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if not kaggle_json.exists():
        raise RuntimeError(
            "No Kaggle credentials found. Either place kaggle.json at "
            "~/.kaggle/kaggle.json, or set KAGGLE_USERNAME and KAGGLE_KEY "
            "in your .env file."
        )


def download_dataset() -> Path:
    _ensure_kaggle_env()

    # Imported here, not top-level, since the kaggle package validates
    # credentials at import time.
    from kaggle.api.kaggle_api_extended import KaggleApi

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    api = KaggleApi()
    api.authenticate()

    print(f"Downloading {DATASET_SLUG} to {RAW_DIR} ...")
    api.dataset_download_files(DATASET_SLUG, path=str(RAW_DIR), unzip=False)

    zip_path = RAW_DIR / f"{DATASET_SLUG.split('/')[-1]}.zip"
    if zip_path.exists():
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(RAW_DIR)
        zip_path.unlink()

    downloaded = list(RAW_DIR.glob("*"))
    print(f"✅ Done. Files in data/raw/: {[f.name for f in downloaded]}")
    return RAW_DIR


if __name__ == "__main__":
    download_dataset()