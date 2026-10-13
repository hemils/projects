"""Submit SQL through Trino Gateway using an Entra bearer token."""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a catalog-qualified SQL query through Trino Gateway."
    )
    parser.add_argument("query", help="SQL statement to submit to Trino Gateway")
    args = parser.parse_args()

    host = os.getenv("TRINO_HOST", "localhost")
    port = int(os.getenv("TRINO_PORT", "9093"))
    user = os.getenv("TRINO_USER", "").strip()
    if not user:
        parser.error("Set TRINO_USER to the Trino principal (the Entra UPN).")
    access_token = os.getenv("TRINO_ACCESS_TOKEN", "").strip()
    if not access_token:
        parser.error("Set TRINO_ACCESS_TOKEN (see trinoGateway/README.md).")

    from trino.dbapi import connect

    ca_bundle = os.getenv("TRINO_CA_BUNDLE", "").strip()
    poc_country = os.getenv("TRINO_POC_COUNTRY", "").strip().upper()
    headers = {"Authorization": f"Bearer {access_token}"}
    if poc_country:
        headers["X-Poc-User-Country"] = poc_country
    connection = connect(
        host=host,
        port=port,
        user=user,
        http_scheme=os.getenv("TRINO_HTTP_SCHEME", "https"),
        http_headers=headers,
        verify=ca_bundle or True,
    )
    try:
        cursor = connection.cursor()
        try:
            print(f"Executing query: {args.query}")
            cursor.execute(args.query)
            columns = [column[0] for column in (cursor.description or [])]
            if columns:
                print("\t".join(columns))
            for row in cursor.fetchall():
                print("\t".join(str(value) for value in row))
        finally:
            cursor.close()
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
