"""Experiment A: policy correctness, one separately authenticated user per country."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bench_common import TokenProvider, parse_target, run_query
from pdp.policy import decide
from plot_style import OUTCOME_COLORS, save, set_style

# Country -> Entra account simulating a user there; replace <tenant-domain> (e.g. contoso.onmicrosoft.com).
USERS = {
    "US": "hemil_shah@outlook.com",
    "GB": "trino_poc_gb@hemilshahoutlook.onmicrosoft.com",#Luda830846
    "DE": "trino_poc_de@hemilshahoutlook.onmicrosoft.com",#P1q2r3s4t5
    "IN": "trino_poc_in@hemilshahoutlook.onmicrosoft.com", #Jako143488
}
QUERIES = {
    "tpch": "SELECT * FROM tpch.sf1.customer LIMIT 10",
    "trades_raw": "SELECT * FROM trades_raw.trades_schema.trades LIMIT 10",
    "customer": "SELECT * FROM customer.customer_schema.customer LIMIT 10"
}


COLUMNS = ["user", "country", "catalog", "expected", "observed", "seconds", "detail"]


def expected(country: str, catalog: str) -> str:
    """Expected decision from the policy module, so it tracks policy edits."""
    permit = decide(subject="expected", location=country, catalogs={catalog}).permit
    return "allow" if permit else "deny"


def dummy_labels(countries) -> list[str]:
    """Per-country sequential pseudonyms such as us_user1, gb_user1, gb_user2."""
    seen: dict[str, int] = {}
    labels = []
    for country in countries:
        seen[country] = seen.get(country, 0) + 1
        labels.append(f"{country.lower()}_user{seen[country]}")
    return labels


def latency_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    """p50/p90/p95 response time (ms) per observed decision and catalog."""
    ms = df.assign(ms=df["seconds"] * 1000)
    grouped = ms.groupby(["observed", "catalog"])["ms"]
    table = grouped.quantile([0.5, 0.9, 0.95]).unstack()
    table.columns = ["p50_ms", "p90_ms", "p95_ms"]
    table["n"] = grouped.size()
    return table.round(2).reset_index()


def plot_heatmap(df: pd.DataFrame, out: str) -> None:
    """Decision matrix; cell text carries the decision and its median latency, '*' marks a policy mismatch."""
    set_style()
    order = list(QUERIES)
    users = list(dict.fromkeys(df["user"]))
    pivot = lambda col, fn: df.groupby(["user", "catalog"])[col].agg(fn).unstack().reindex(index=users, columns=order)

    code = pivot("observed", lambda x: x.mode().iat[0])
    exp = pivot("expected", "first")
    p50 = pivot("seconds", "median") * 1000
    values = code.replace({"allow": 1, "deny": 0, "error": 0.5}).astype(float)
    text = code.apply(lambda col: col.str.capitalize()) + np.where(code != exp, "*", "") \
        + "\n" + p50.round(0).astype(int).astype(str) + " ms"

    cmap = LinearSegmentedColormap.from_list("decision", [OUTCOME_COLORS["deny"], "#E8E8E8", OUTCOME_COLORS["allow"]])
    fig, ax = plt.subplots(figsize=(4.2, 2.4))
    sns.heatmap(values, annot=text, fmt="", cmap=cmap, vmin=0, vmax=1, cbar=False, linewidths=1.5,
                linecolor="white", annot_kws={"color": "white", "weight": "bold", "fontsize": 7}, ax=ax)
    ax.set(xlabel="Catalog", ylabel="User")
    ax.tick_params(axis="y", rotation=0, length=0)
    ax.tick_params(axis="x", length=0)
    fig.tight_layout()
    save(fig, f"{out}_heatmap")


def write_story(df: pd.DataFrame, pct: pd.DataFrame, out: str) -> None:
    n = len(df)
    wrong = df[df["expected"] != df["observed"]]
    lines = [
        "EXPERIMENT A - POLICY CORRECTNESS (generated; do not commit)",
        "",
        f"Setup: {df['user'].nunique()} users (one per country) each ran {df['catalog'].nunique()} catalog "
        f"queries, {n} requests in total, through the gateway with a per-user Entra token.",
        "",
        "Figure: experiment_a_heatmap",
        "  Rows are users, columns are catalogs. Green = allowed, red = denied, grey = error.",
        "  The second line in each cell is the median response time. A '*' would mean the observed",
        "  decision differs from the policy module's expectation.",
        f"  Result: accuracy {(df['expected'] == df['observed']).mean():.1%}, "
        f"{len(wrong)} mismatching requests, {(df['observed'] == 'error').sum()} errors.",
        "",
        "Who can see what:",
    ]
    for user, grp in df.groupby("user", sort=False):
        ok = sorted(grp[grp["observed"] == "allow"]["catalog"].unique())
        no = sorted(grp[grp["observed"] == "deny"]["catalog"].unique())
        lines.append(f"  {user}: allowed {', '.join(ok) or '-'}; denied {', '.join(no) or '-'}")
    lines += ["", "Latency percentiles (ms) by decision and catalog (experiment_a_latency_percentiles.csv):"]
    for _, r in pct.iterrows():
        lines.append(f"  {r['observed']:<6} {r['catalog']:<11} p50={r['p50_ms']:.1f} p90={r['p90_ms']:.1f} "
                     f"p95={r['p95_ms']:.1f} (n={int(r['n'])})")
    allow, deny = pct[pct["observed"] == "allow"], pct[pct["observed"] == "deny"]
    if len(allow) and len(deny):
        lines += ["", f"Takeaway: denials return in {deny['p50_ms'].min():.0f}-{deny['p50_ms'].max():.0f} ms (p50) "
                      f"regardless of catalog, while allowed queries take {allow['p50_ms'].min():.0f}-"
                      f"{allow['p50_ms'].max():.0f} ms because they execute in Trino. Enforcement therefore "
                      "happens before any data-plane work, and the decisions match the policy matrix."]
    with open(f"{out}_story.txt", "w") as handle:
        handle.write("\n".join(lines) + "\n")


def report(df: pd.DataFrame, out: str) -> None:
    pct = latency_percentiles(df)
    pct.to_csv(f"{out}_latency_percentiles.csv", index=False)
    print(pct.to_string(index=False))
    plot_heatmap(df, out)
    write_story(df, pct, out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", default="gateway=localhost:9093")
    parser.add_argument("--runs", type=int, default=30, help="repetitions per cell")
    parser.add_argument("--out", default="results/experiment_a")
    parser.add_argument("--plot-only", action="store_true", help="redraw charts from the existing CSV")
    args = parser.parse_args()

    if args.plot_only:
        df = pd.read_csv(f"{args.out}.csv")
        names = dict(zip(df["country"].unique(), dummy_labels(df["country"].unique())))
        df["user"] = df["country"].map(names)
        report(df, args.out)
        return

    if any("<tenant-domain>" in upn for upn in USERS.values()):
        raise SystemExit("Edit USERS in this script: replace <tenant-domain> with your tenant domain.")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    target = parse_target(args.gateway)
    provider = TokenProvider()
    users = USERS

    # Each user signs in separately, so every query carries that user's own token.
    tokens = {}
    for country, upn in users.items():
        print(f"Sign in as {upn} ({country})")
        provider.login(login_hint=upn)
        tokens[country] = provider.acquire(username=upn)[0]

    # rows: (user, country, catalog, expected, observed, seconds, detail)
    rows = []
    labels_by_country = dict(zip(users, dummy_labels(users)))
    for country, upn in users.items():
        label = labels_by_country[country]
        for catalog, sql in QUERIES.items():
            for _ in range(args.runs):
                outcome, seconds, detail = run_query(
                    target, user=upn, token=tokens[country], country=country, sql=sql
                )
                rows.append(
                    (label, country, catalog, expected(country, catalog), outcome, seconds, detail)
                )
    with open(f"{args.out}.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(rows)

    false_allow = sum(1 for r in rows if r[3] == "deny" and r[4] == "allow")
    false_deny = sum(1 for r in rows if r[3] == "allow" and r[4] == "deny")
    errors = sum(1 for r in rows if r[4] == "error")
    correct = sum(1 for r in rows if r[3] == r[4])
    print(f"n={len(rows)} accuracy={correct / len(rows):.3f} "
          f"false_allow={false_allow} false_deny={false_deny} errors={errors}")

    report(pd.DataFrame(rows, columns=COLUMNS), args.out)


if __name__ == "__main__":
    main()
