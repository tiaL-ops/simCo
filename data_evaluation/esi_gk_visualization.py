"""Visualize ESI and fair-consumption (g_k) relationships.

Outputs (saved in data_evaluation/):
- esi_gk_scatter_by_provider.png
- esi_gk_correlation_heatmap.png
- result_esi_visualization.txt

Usage:
    python esi_gk_visualization.py
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from esi import compute_esi, load_median_gk


BASE_DIR = Path(__file__).resolve().parent
CONDITION_ORDER = ("E", "N")
CONDITION_NAME = {"E": "emotional", "N": "neutral"}
CONDITION_COLOR = {"E": "#d1495b", "N": "#2f6690"}
INCLUDED_PROVIDERS = ("Claude", "Gemini", "Grok")


def _fmt(value: float) -> str:
    if value != value:
        return "nan"
    return f"{value:.4f}"


def collect_records() -> list[dict]:
    records: list[dict] = []
    matrix_files = sorted(BASE_DIR.glob("matrix_*.csv"))
    for matrix_path in matrix_files:
        scenario = compute_esi(matrix_path)
        if scenario.provider not in INCLUDED_PROVIDERS:
            continue
        gk_by_agent, _ = load_median_gk(scenario.provider, scenario.condition_name)
        for agent in scenario.agents:
            g_k = gk_by_agent.get(agent)
            if g_k is None:
                continue
            records.append(
                {
                    "provider": scenario.provider,
                    "condition_code": scenario.condition_code,
                    "condition_name": scenario.condition_name,
                    "agent": agent,
                    "esi": scenario.esi_by_agent[agent],
                    "g_k": g_k,
                }
            )
    return records


def save_scatter(records: list[dict]) -> Path:
    fig, axes = plt.subplots(1, len(INCLUDED_PROVIDERS), figsize=(16, 5), constrained_layout=True)
    fig.suptitle("ESI vs Fair Consumption (g_k) by Provider", fontsize=16)

    for idx, provider in enumerate(INCLUDED_PROVIDERS):
        ax = axes[idx]
        rows = [r for r in records if r["provider"] == provider]

        for condition in CONDITION_ORDER:
            crows = [r for r in rows if r["condition_code"] == condition]
            x = [r["g_k"] for r in crows]
            y = [r["esi"] for r in crows]
            labels = [r["agent"] for r in crows]

            if not x:
                continue

            ax.scatter(
                x,
                y,
                s=55,
                alpha=0.88,
                color=CONDITION_COLOR[condition],
                label=CONDITION_NAME[condition],
                edgecolors="black",
                linewidths=0.4,
            )

            for xi, yi, agent in zip(x, y, labels):
                ax.text(xi + 0.015, yi + 0.015, f"{agent}-{condition}", fontsize=7)

        ax.set_title(provider)
        ax.set_xlabel("g_k (fair consumption ratio)")
        ax.set_ylabel("ESI")
        ax.grid(alpha=0.25)
        ax.legend(loc="best", fontsize=8)

    out = BASE_DIR / "esi_gk_scatter_by_provider.png"
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def _correlation(x_values: list[float], y_values: list[float]) -> tuple[float, str]:
    if len(x_values) < 2:
        return float("nan"), "not enough points"
    if len(set(x_values)) == 1:
        return float("nan"), "g_k has zero variance"
    if len(set(y_values)) == 1:
        return float("nan"), "ESI has zero variance"

    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    r = float(np.corrcoef(x, y)[0, 1])
    return r, "ok"


def save_correlation_heatmap(records: list[dict]) -> tuple[Path, dict[tuple[str, str], tuple[float, str]]]:
    corr_grid = np.full((len(INCLUDED_PROVIDERS), len(CONDITION_ORDER)), np.nan, dtype=float)
    notes: dict[tuple[str, str], tuple[float, str]] = {}

    for i, provider in enumerate(INCLUDED_PROVIDERS):
        for j, condition in enumerate(CONDITION_ORDER):
            rows = [
                r
                for r in records
                if r["provider"] == provider and r["condition_code"] == condition
            ]
            x = [r["g_k"] for r in rows]
            y = [r["esi"] for r in rows]
            r_value, reason = _correlation(x, y)
            corr_grid[i, j] = r_value
            notes[(provider, condition)] = (r_value, reason)

    fig, ax = plt.subplots(figsize=(7, 5), constrained_layout=True)
    masked = np.ma.masked_invalid(corr_grid)
    im = ax.imshow(masked, cmap="RdBu_r", vmin=-1.0, vmax=1.0)
    cbar = fig.colorbar(im, ax=ax, shrink=0.9)
    cbar.set_label("Pearson r")

    ax.set_xticks(range(len(CONDITION_ORDER)))
    ax.set_xticklabels([CONDITION_NAME[c] for c in CONDITION_ORDER])
    ax.set_yticks(range(len(INCLUDED_PROVIDERS)))
    ax.set_yticklabels(INCLUDED_PROVIDERS)
    ax.set_title("Correlation: ESI vs g_k")

    for i, provider in enumerate(INCLUDED_PROVIDERS):
        for j, condition in enumerate(CONDITION_ORDER):
            value, reason = notes[(provider, condition)]
            if math.isnan(value):
                ax.text(j, i, "nan", ha="center", va="center", color="black", fontsize=9)
                ax.text(j, i + 0.2, reason, ha="center", va="center", color="black", fontsize=6)
            else:
                ax.text(j, i, f"{value:.3f}", ha="center", va="center", color="black", fontsize=9)

    out = BASE_DIR / "esi_gk_correlation_heatmap.png"
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out, notes


def save_interpretation(records: list[dict], notes: dict[tuple[str, str], tuple[float, str]]) -> Path:
    lines: list[str] = []
    lines.append("ESI and g_k Visualization Notes")
    lines.append("=" * 80)
    lines.append("Why Gemini can appear blank:")
    value, reason = notes[("Gemini", "N")]
    lines.append(f"- Gemini_N correlation = {_fmt(value)} ({reason}).")
    lines.append(
        "- This is not missing data. Correlation is undefined when all g_k values are identical."
    )
    lines.append("")
    lines.append("Per provider-condition correlation summary:")
    for provider in INCLUDED_PROVIDERS:
        for condition in CONDITION_ORDER:
            v, r = notes[(provider, condition)]
            lines.append(f"- {provider}_{condition}: r={_fmt(v)} ({r})")
    lines.append("")

    lines.append("Record counts:")
    for provider in INCLUDED_PROVIDERS:
        for condition in CONDITION_ORDER:
            n = sum(
                1
                for rec in records
                if rec["provider"] == provider and rec["condition_code"] == condition
            )
            lines.append(f"- {provider}_{condition}: n={n}")

    out = BASE_DIR / "result_esi_visualization.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    records = collect_records()
    if not records:
        raise FileNotFoundError("No valid ESI/g_k records found from matrix and score files.")

    scatter_path = save_scatter(records)
    heatmap_path, notes = save_correlation_heatmap(records)
    report_path = save_interpretation(records, notes)

    print("Saved:")
    print(f"- {scatter_path}")
    print(f"- {heatmap_path}")
    print(f"- {report_path}")


if __name__ == "__main__":
    main()
