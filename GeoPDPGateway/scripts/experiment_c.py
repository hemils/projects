"""Experiment C: latency across paths, plus Entra token-acquisition overhead."""

from __future__ import annotations

import argparse
import csv
import os
import statistics

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from bench_common import TokenProvider, parse_target, run_query
from plot_style import COLUMN_WIDTH, PATH_PALETTE, PERCENTILES, save, set_style

SQL = "SELECT * FROM tpch.sf1.customer LIMIT 5"


def pct(values: list[float], q: float) -> float:
    return float(np.percentile(values, q))


def load(out: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    runs = pd.read_csv(f"{out}.csv")
    runs = runs[runs["outcome"] == "allow"].copy()
    runs["ms"] = runs["seconds"] * 1000
    runs["idx"] = runs.groupby("path").cumcount() + 1
    auth = pd.read_csv(f"{out}_auth.csv")
    auth["ms"] = auth["seconds"] * 1000
    return runs, auth


def percentile_table(runs: pd.DataFrame) -> pd.DataFrame:
    rows = {path: {f"p{q}": np.percentile(g["ms"], q) for q in PERCENTILES} | {"n": len(g)}
            for path, g in runs.groupby("path", sort=False)}
    return pd.DataFrame(rows).T.rename_axis("path").reset_index()


def plot_ecdf(runs, palette, out):
    fig, ax = plt.subplots(figsize=(COLUMN_WIDTH, 2.4))
    sns.ecdfplot(data=runs, x="ms", hue="path", palette=palette, linewidth=1.6, ax=ax)
    for q in (0.5, 0.95):
        ax.axhline(q, color="#777777", linestyle=":", linewidth=0.8)
        ax.text(ax.get_xlim()[1], q, f"p{int(q * 100)} ", ha="right", va="bottom", fontsize=7, color="#555555")
    ax.set(xlabel="Query latency (ms)", ylabel="Cumulative fraction")
    ax.get_legend().set_title("Path")
    sns.move_legend(ax, "lower right", frameon=False)
    save(fig, f"{out}_ecdf")


def plot_distribution(runs, palette, out):
    fig, ax = plt.subplots(figsize=(COLUMN_WIDTH, 2.4))
    sns.violinplot(data=runs, x="path", y="ms", hue="path", palette=palette, inner="quartile",
                   cut=0, linewidth=0.8, legend=False, ax=ax)
    ax.set(xlabel="Path", ylabel="Query latency (ms)")
    save(fig, f"{out}_distribution")


def plot_percentiles(table, palette, out):
    long = table.melt(id_vars="path", value_vars=[f"p{q}" for q in PERCENTILES],
                      var_name="percentile", value_name="ms")
    fig, ax = plt.subplots(figsize=(COLUMN_WIDTH + 0.6, 2.5))
    sns.barplot(data=long, x="percentile", y="ms", hue="path", palette=palette, edgecolor="white", ax=ax)
    for container in ax.containers:
        ax.bar_label(container, fmt="%.0f", fontsize=6, padding=1)
    ax.set(xlabel="Percentile", ylabel="Latency (ms)")
    ax.get_legend().set_title("Path")
    sns.move_legend(ax, "upper left", frameon=False)
    save(fig, f"{out}_percentiles")


def plot_timeline(runs, palette, out):
    runs = runs.assign(rolling=runs.groupby("path")["ms"].transform(lambda x: x.rolling(15, min_periods=1).median()))
    fig, ax = plt.subplots(figsize=(COLUMN_WIDTH + 0.6, 2.4))
    sns.scatterplot(data=runs, x="idx", y="ms", hue="path", palette=palette, s=7, alpha=0.35,
                    linewidth=0, legend=False, ax=ax)
    sns.lineplot(data=runs, x="idx", y="rolling", hue="path", palette=palette, linewidth=1.6, ax=ax)
    ax.set(xlabel="Request index", ylabel="Latency (ms)")
    ax.get_legend().set_title("Path (rolling p50)")
    sns.move_legend(ax, "upper right", frameon=False)
    save(fig, f"{out}_timeline")


def plot_overhead(table, auth, palette, out):
    """Median cost of each component on a log axis; a stacked bar would hide the token-cache win."""
    items = [(f"Query\n{r['path']}", r["p50"], palette[i % len(palette)]) for i, r in table.iterrows()]
    items += [(f"Token\n{mode}", g["ms"].median(), c)
              for (mode, g), c in zip(auth.groupby("mode", sort=False), ("#C9C9C9", "#7A7A7A"))]
    labels, values, colors = zip(*items)
    fig, ax = plt.subplots(figsize=(COLUMN_WIDTH + 0.6, 2.4))
    ax.bar(labels, values, color=colors, width=0.6)
    ax.set_yscale("log")
    for x, v in zip(labels, values):
        ax.text(x, v * 1.1, f"{v:.2f}" if v < 1 else f"{v:.0f}", ha="center", va="bottom", fontsize=7)
    ax.set(ylabel="Median cost (ms, log)")
    save(fig, f"{out}_overhead")


def write_story(runs, table, auth, out):
    base = table.iloc[0]
    lines = ["EXPERIMENT C - LATENCY OVERHEAD (generated; do not commit)", "",
             "Setup: one authenticated user (single country) repeats the same query on each path; users "
             "added in Experiment A do not alter this setup (see note at the end).", ""]
    for _, r in table.iterrows():
        lines.append(f"  {r['path']:<10} n={int(r['n'])} p50={r['p50']:.1f} p90={r['p90']:.1f} "
                     f"p95={r['p95']:.1f} p99={r['p99']:.1f} ms")
    lines += ["", "Figures:",
              "  experiment_c_ecdf: the whole latency distribution per path; a rightward shift of the "
              "gateway curve is the added cost, a steeper tail shows variance.",
              "  experiment_c_distribution: violin with quartiles, shape and spread at a glance.",
              "  experiment_c_percentiles: p50/p90/p95/p99 side by side, median cost versus tail cost.",
              "  experiment_c_timeline: latency per request with rolling p50, shows warm-up or drift.",
              "  experiment_c_overhead: median query cost beside Entra token acquisition (log scale): "
              "a cached token is negligible, a forced refresh is the only expensive auth step."]
    for _, r in table.iloc[1:].iterrows():
        lines += ["", f"Overhead of {r['path']} over {base['path']}: "
                      + ", ".join(f"p{q} +{r[f'p{q}'] - base[f'p{q}']:.1f} ms "
                                  f"({(r[f'p{q}'] / base[f'p{q}'] - 1):+.0%})" for q in PERCENTILES)]
    for mode, g in auth.groupby("mode", sort=False):
        lines.append(f"Token acquisition ({mode}): p50={g['ms'].median():.3f} ms, "
                     f"p95={np.percentile(g['ms'], 95):.3f} ms")
    lines += ["", "Impact of new users: the gateway policy check costs per request, not per user, and each "
                  "user presents a cached token, so adding users changes neither the path latency nor the "
                  "token cost measured here. It would matter only under concurrent load, which this "
                  "sequential benchmark does not exercise."]
    with open(f"{out}_story.txt", "w") as handle:
        handle.write("\n".join(lines) + "\n")


def report(out: str) -> None:
    runs, auth = load(out)
    table = percentile_table(runs)
    table.round(2).to_csv(f"{out}_percentiles.csv", index=False)
    print(table.round(1).to_string(index=False))
    set_style()
    palette = dict(zip(table["path"], PATH_PALETTE))
    plot_ecdf(runs, palette, out)
    plot_distribution(runs, palette, out)
    plot_percentiles(table, palette, out)
    plot_timeline(runs, palette, out)
    plot_overhead(table, auth, PATH_PALETTE, out)
    write_story(runs, table, auth, out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target", action="append", metavar="LABEL=HOST:PORT",
        help="repeat per path, e.g. direct=localhost:9091 gateway=localhost:9093",
    )
    parser.add_argument("--country", default="US")
    parser.add_argument("--runs", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--out", default="results/experiment_c")
    parser.add_argument("--plot-only", action="store_true", help="redraw charts from the existing CSVs")
    args = parser.parse_args()

    if args.plot_only:
        report(args.out)
        return

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    if not args.target:
        parser.error("--target is required unless --plot-only is used")
    targets = [parse_target(spec) for spec in args.target]
    provider = TokenProvider()
    upn = provider.login()
    user = os.getenv("TRINO_USER", "").strip() or upn

    auth = {"cache": [], "refresh": []}
    for _ in range(args.runs):
        auth["cache"].append(provider.acquire()[1])
    for _ in range(min(args.runs, 30)):
        try:
            auth["refresh"].append(provider.acquire(force_refresh=True)[1])
        except RuntimeError as exc:
            print(f"Skipping forced-refresh timing: {exc}")
            break
    auth = {mode: values for mode, values in auth.items() if values}
    token = provider.acquire()[0]

    latency: dict[str, list[float]] = {}
    rows = []
    for target in targets:
        for _ in range(args.warmup):
            run_query(target, user=user, token=token, country=args.country, sql=SQL)
        samples = []
        for _ in range(args.runs):
            outcome, seconds, detail = run_query(
                target, user=user, token=token, country=args.country, sql=SQL
            )
            rows.append((target.label, outcome, seconds, detail))
            if outcome == "allow":
                samples.append(seconds * 1000)
        latency[target.label] = samples
        print(f"{target.label}: ok={len(samples)}/{args.runs}")

    with open(f"{args.out}.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["path", "outcome", "seconds", "detail"])
        writer.writerows(rows)
    with open(f"{args.out}_auth.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["mode", "seconds"])
        for mode, values in auth.items():
            writer.writerows((mode, v) for v in values)

    print("path        n    p50(ms)  p95(ms)  p99(ms)")
    for label, values in latency.items():
        if values:
            print(f"{label:<10}{len(values):>5}{pct(values, 50):>10.1f}"
                  f"{pct(values, 95):>9.1f}{pct(values, 99):>9.1f}")
    for mode, values in auth.items():
        print(f"auth[{mode}] median={statistics.median(values) * 1000:.1f} ms "
              f"p95={pct(values, 95) * 1000:.1f} ms")

    report(args.out)

if __name__ == "__main__":
    main()
