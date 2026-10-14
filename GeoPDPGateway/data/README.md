# Sample POC data

CSV samples of the Delta tables behind the `trades_raw` catalog, exported from ADLS:

| Source | Output |
|---|---|
| `abfss://trades@tradeslake.dfs.core.windows.net/bronze/trades` (partition `trade_date=2026-01-02`) | `data/trades.csv` |
| `abfss://trades@tradeslake.dfs.core.windows.net/bronze/customer` | `data/customer.csv` |

## Export

1. Sign in with an identity that has **Storage Blob Data Reader** on the `tradeslake` account:

   ```sh
   az login
   ```

2. Install dependencies and run the export from the repository root:

   ```sh
   .venv/bin/python -m pip install -r requirements.txt
   .venv/bin/python scripts/export_adls_samples.py
   ```

Options:

- `--limit N` max rows per table (default `1000`)
- `--trade-date YYYY-MM-DD` trades partition to export (default `2026-01-02`)
- `--out-dir PATH` output folder (default `data/`)

The script authenticates via `DefaultAzureCredential` (Azure CLI login); no keys are stored.

## Notes

- Both tables are read as Delta tables, so only the current table version is exported.
- The CSVs may contain customer data. Check whether they should be committed or git-ignored before pushing.
