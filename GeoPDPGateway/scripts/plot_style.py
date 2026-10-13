"""Shared publication style for the experiment charts."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

OUTCOME_COLORS = {"allow": "#4C9F70", "deny": "#C8553D", "error": "#9A9A9A"}
PATH_PALETTE = ["#3B6EA8", "#E08E45", "#5B8E7D", "#8C6BB1", "#B5B5B5"]
PERCENTILES = (50, 90, 95, 99)
COLUMN_WIDTH = 3.4  # inches, single-column journal width


def set_style() -> None:
    sns.set_theme(context="paper", style="ticks", font="serif", font_scale=0.95,
                  rc={"axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
                      "axes.spines.right": False})


def save(fig: plt.Figure, base: str) -> None:
    """Write vector PDF and 300 dpi PNG side by side."""
    fig.savefig(f"{base}.pdf", bbox_inches="tight")
    fig.savefig(f"{base}.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
