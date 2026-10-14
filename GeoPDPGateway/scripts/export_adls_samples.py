"""Export sample rows of the POC Delta tables (trades, customer) from ADLS to CSV."""
import argparse
import getpass
import os
from pathlib import Path

import pyarrow.compute as pc
from deltalake import DeltaTable

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
BASE = "abfss://trades@tradeslake.dfs.core.windows.net/bronze"
ACCOUNT = "tradeslake"


def load_access_key() -> str:
    """Same AZURE_ACCESS_KEY the Trino catalogs use: environment, then .env, then prompt."""
    key = os.environ.get("AZURE_ACCESS_KEY", "")
    env_file = ROOT / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "AZURE_ACCESS_KEY":
                key = value.strip().strip("'\"")
    return key or getpass.getpass("ADLS Gen2 storage account access key: ")


def open_table(path: str, key: str) -> DeltaTable:
    return DeltaTable(
        path,
        storage_options={"azure_storage_account_name": ACCOUNT, "azure_storage_account_key": key},
    )


def export(table: DeltaTable, out: Path, limit: int, row_filter=None) -> None:
    df = table.to_pyarrow_dataset().head(limit, filter=row_filter).to_pandas()
    df.to_csv(out, index=False)
    print(f"wrote {len(df)} rows -> {out}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trade-date", default="2026-01-02")
    p.add_argument("--limit", type=int, default=1000, help="max rows per table")
    p.add_argument("--out-dir", type=Path, default=DATA_DIR)
    args = p.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    key = load_access_key()

    export(
        open_table(f"{BASE}/trades", key),
        args.out_dir / "trades.csv",
        args.limit,
        row_filter=pc.field("trade_date") == args.trade_date,
    )
    export(open_table(f"{BASE}/customer", key), args.out_dir / "customer.csv", args.limit)


if __name__ == "__main__":
    main()
