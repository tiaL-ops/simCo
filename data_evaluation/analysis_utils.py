"""
analysis_utils.py
-----------------
Utility functions for the gk / PPI 2x2 analysis notebook.

Organised into sections by single responsibility (SOLID - SRP):
  - Formatting & display helpers
  - Summary statistics
  - Effect-size functions
  - Confidence intervals
  - Effect-row builders (for result tables)
  - Correlation analysis
  - Non-parametric tests
  - Multiple-comparisons correction
  - Gini-specific utilities
  - Data loading
"""

import json
import re

import numpy as np
import pandas as pd

from scipy.stats import (
    chi2_contingency,
    spearmanr,
    t as t_dist,
    wilcoxon,
)


# ── Formatting & display helpers ─────────────────────────────────────────────

def decision_text(p, alpha: float = 0.05) -> str:
    """Return 'significant' or 'not significant' based on p-value."""
    return "significant" if pd.notna(p) and p < alpha else "not significant"


def format_p(p_value) -> str:
    """Format a p-value as an APA-style string."""
    if pd.isna(p_value):
        return "p = NA"
    if p_value < 0.001:
        return "p < 0.001"
    return f"p = {p_value:.3f}"


def p_display(p) -> str:
    """Short p-value string for tables (drops leading zero)."""
    if pd.isna(p):
        return "NA"
    if p < 0.001:
        return "<.001"
    return f"{p:.3f}".replace("0.", ".")


def p_stars(p_value) -> str:
    """Return APA-style significance stars for a p-value."""
    if pd.isna(p_value):
        return ""
    if p_value < 0.001:
        return "***"
    if p_value < 0.01:
        return "**"
    if p_value < 0.05:
        return "*"
    return "ns"


def ci_display(r_value: float, n: int) -> str:
    """Format a Fisher-z correlation CI as a bracketed string."""
    ci_lo, ci_hi = fisher_ci_from_r(r_value, n)
    if np.isfinite(ci_lo) and np.isfinite(ci_hi):
        return f"[{ci_lo:.3f}, {ci_hi:.3f}]"
    return "NA"


# ── Summary statistics ───────────────────────────────────────────────────────

def summarize_mean(values) -> float:
    """Mean of values, ignoring NaN; returns NaN for empty input."""
    if values is None:
        return np.nan
    arr = np.asarray(values, dtype=float)
    if arr.size == 0 or np.all(~np.isfinite(arr)):
        return np.nan
    return float(np.nanmean(arr))


def summarize_median_iqr(values):
    """Return (median, IQR) tuple after dropping non-finite values."""
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return np.nan, np.nan
    med = float(np.median(arr))
    q1, q3 = np.quantile(arr, [0.25, 0.75])
    return med, float(q3 - q1)


def group_sd(values) -> float:
    """Sample standard deviation, dropping non-finite values."""
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 2:
        return np.nan
    return float(np.std(arr, ddof=1))


# ── Effect-size functions ────────────────────────────────────────────────────

def cohens_d_independent(values_a, values_b) -> float:
    """Pooled Cohen's d for two independent samples."""
    a = np.asarray(values_a, dtype=float)
    b = np.asarray(values_b, dtype=float)
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return np.nan
    s1 = float(np.std(a, ddof=1))
    s2 = float(np.std(b, ddof=1))
    pooled_var = ((n1 - 1) * s1 ** 2 + (n2 - 1) * s2 ** 2) / (n1 + n2 - 2)
    if pooled_var <= 0:
        return np.nan
    return float((np.mean(a) - np.mean(b)) / np.sqrt(pooled_var))


def anova_eta_squared(groups) -> float:
    """Eta-squared effect size for a one-way ANOVA."""
    arrays = [np.asarray(g, dtype=float) for g in groups]
    arrays = [arr[np.isfinite(arr)] for arr in arrays]
    arrays = [arr for arr in arrays if len(arr) > 0]
    if len(arrays) < 2:
        return np.nan
    all_values = np.concatenate(arrays)
    grand_mean = float(np.mean(all_values))
    ss_between = sum(
        len(arr) * (float(np.mean(arr)) - grand_mean) ** 2 for arr in arrays
    )
    ss_total = float(np.sum((all_values - grand_mean) ** 2))
    if ss_total <= 0:
        return np.nan
    return float(ss_between / ss_total)


def kruskal_epsilon_squared(h_stat: float, groups) -> float:
    """Epsilon-squared effect size for a Kruskal-Wallis test."""
    k = len(groups)
    n_total = int(sum(len(g) for g in groups))
    if n_total <= k:
        return np.nan
    epsilon_sq = (float(h_stat) - k + 1) / (n_total - k)
    return float(max(0.0, epsilon_sq))


def cramers_v(ctab: pd.DataFrame) -> float:
    """Cramer's V association strength for a contingency table."""
    observed = ctab.to_numpy(dtype=float)
    n = observed.sum()
    if n <= 0:
        return np.nan
    rows, cols = observed.shape
    min_dim = min(rows - 1, cols - 1)
    if min_dim <= 0:
        return np.nan
    chi2, _, _, _ = chi2_contingency(observed, correction=False)
    return float(np.sqrt(chi2 / (n * min_dim)))


# ── Confidence intervals ─────────────────────────────────────────────────────

def fisher_ci_from_r(r_value: float, n: int, alpha: float = 0.05):
    """
    Fisher z-transformation 95 % CI for a Pearson/Spearman correlation.

    Returns a (lo, hi) tuple; both are NaN when conditions are not met.
    """
    if pd.isna(r_value) or n is None or n <= 3 or abs(r_value) >= 1:
        return (np.nan, np.nan)
    z = np.arctanh(float(r_value))
    se = 1.0 / np.sqrt(n - 3)
    z_crit = 1.96  # alpha = 0.05 two-sided
    lo = np.tanh(z - z_crit * se)
    hi = np.tanh(z + z_crit * se)
    return (float(lo), float(hi))


# ── Effect-row builders ──────────────────────────────────────────────────────

def build_effect_row(
    effect_name: str,
    diff_values,
    t_value: float,
    p_value: float,
    mean_emotional=None,
    mean_neutral=None,
    alpha: float = 0.05,
) -> dict:
    """
    Build a summary-table row for a paired-difference effect on g_k.

    Parameters
    ----------
    effect_name   : label for the row
    diff_values   : array of per-block differences (emotional - neutral)
    t_value       : t-statistic from the paired/one-sample test
    p_value       : corresponding p-value
    mean_emotional: group values for the emotional condition (optional)
    mean_neutral  : group values for the neutral condition (optional)
    alpha         : significance threshold (default 0.05)
    """
    values = np.asarray(diff_values, dtype=float)
    n = len(values)
    df_val = n - 1

    mean_diff = float(np.mean(values))
    sd_diff = float(np.std(values, ddof=1)) if n > 1 else np.nan
    se_diff = float(sd_diff / np.sqrt(n)) if n > 1 else np.nan

    if n > 1 and np.isfinite(se_diff):
        t_crit = float(t_dist.ppf(0.975, df_val))
        ci_low = mean_diff - t_crit * se_diff
        ci_high = mean_diff + t_crit * se_diff
        ci_text = f"[{ci_low:.4f}, {ci_high:.4f}]"
    else:
        ci_text = "NA"

    if n > 1 and np.isfinite(sd_diff) and sd_diff > 0:
        cohen_d = float(mean_diff / sd_diff)
    else:
        cohen_d = np.nan

    return {
        "Effect": effect_name,
        "Mean_emotional": summarize_mean(mean_emotional),
        "Mean_neutral": summarize_mean(mean_neutral),
        "M_diff": mean_diff,
        "SE": se_diff,
        "t": float(t_value),
        "df": int(df_val),
        "p": float(p_value),
        "95% CI": ci_text,
        "d (cohen's d)": cohen_d,
        "decision_alpha_0.05": decision_text(float(p_value), alpha),
    }


def build_gini_row(
    effect_name: str,
    group_1: str,
    group_2: str,
    mean_group_1,
    mean_group_2,
    diff_values,
    alpha: float = 0.05,
) -> dict:
    """
    Build a summary-table row for a Wilcoxon-tested Gini effect.

    Parameters
    ----------
    effect_name  : label for the row
    group_1      : name of the first group (e.g. 'emotional')
    group_2      : name of the second group (e.g. 'neutral')
    mean_group_1 : array of Gini values for group_1
    mean_group_2 : array of Gini values for group_2
    diff_values  : per-block differences (group_1 - group_2)
    alpha        : significance threshold (default 0.05)
    """
    w_stat, p_value, z_value, r_value = safe_wilcoxon(diff_values)
    med_1, iqr_1 = summarize_median_iqr(mean_group_1)
    med_2, iqr_2 = summarize_median_iqr(mean_group_2)
    return {
        "Effect": effect_name,
        "Group_1": group_1,
        "Group_2": group_2,
        "Mean_group_1": float(np.mean(np.asarray(mean_group_1, dtype=float))),
        "Mean_group_2": float(np.mean(np.asarray(mean_group_2, dtype=float))),
        "Median_group_1": med_1,
        "IQR_group_1": iqr_1,
        "Median_group_2": med_2,
        "IQR_group_2": iqr_2,
        "M_diff": float(np.mean(np.asarray(diff_values, dtype=float))),
        "W": w_stat,
        "z": z_value,
        "p": p_value,
        "r": r_value,
        "decision_alpha_0.05": decision_text(p_value, alpha),
    }


# ── Correlation analysis ─────────────────────────────────────────────────────

def spearman_summary(
    subset: pd.DataFrame,
    label_parts: dict,
    alpha: float = 0.05,
) -> dict:
    """
    Compute Spearman ρ between ppi_k and g_k for a data subset.

    Returns a dict row suitable for building a summary table.
    """
    n = int(len(subset))
    if n < 4:
        rho = np.nan
        p_rho = np.nan
        r2 = np.nan
        ci_text = "NA"
        decision = "insufficient data"
    else:
        rho_val, p_val = spearmanr(subset["ppi_k"], subset["g_k"])
        rho = float(rho_val)
        p_rho = float(p_val)
        r2 = float(rho ** 2)
        ci_text = ci_display(rho, n)
        decision = decision_text(p_rho, alpha)

    return {
        **label_parts,
        "ρ": rho,
        "p": p_rho,
        "p_text": p_display(p_rho),
        "n": n,
        "r²": r2,
        "95% CI": ci_text,
        "decision": decision,
    }


# ── Non-parametric tests ─────────────────────────────────────────────────────

def safe_wilcoxon(diff_values):
    """
    Wilcoxon signed-rank test with a graceful fallback for older SciPy.

    Returns (w_stat, p_value, z_value, r_value).
    r is computed as |z| / sqrt(n_eff) where n_eff is the number of
    non-zero differences.
    """
    values = np.asarray(diff_values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return np.nan, np.nan, np.nan, np.nan

    non_zero = values[~np.isclose(values, 0.0)]
    n_eff = len(non_zero)
    if n_eff == 0:
        return 0.0, 1.0, 0.0, 0.0

    try:
        res = wilcoxon(
            values,
            alternative="two-sided",
            zero_method="wilcox",
            method="approx",
            correction=False,
        )
        w_stat = float(res.statistic)
        p_value = float(res.pvalue)
        z_value = float(getattr(res, "zstatistic", np.nan))
    except TypeError:
        # Fallback for older SciPy versions that do not support keyword args.
        w_stat, p_value = wilcoxon(values)
        w_stat = float(w_stat)
        p_value = float(p_value)
        z_value = np.nan

    r_value = (
        float(abs(z_value) / np.sqrt(n_eff))
        if np.isfinite(z_value) and n_eff > 0
        else np.nan
    )
    return w_stat, p_value, z_value, r_value


# ── Multiple-comparisons correction ─────────────────────────────────────────

def holm_adjust(p_values) -> np.ndarray:
    """
    Holm-Bonferroni stepwise correction for multiple comparisons.

    Returns adjusted p-values in the same order as the input array.
    """
    p_values = np.asarray(p_values, dtype=float)
    order = np.argsort(p_values)
    adjusted = np.empty_like(p_values)
    m = len(p_values)
    running_max = 0.0
    for rank, idx in enumerate(order):
        adj = (m - rank) * p_values[idx]
        running_max = max(running_max, adj)
        adjusted[idx] = min(running_max, 1.0)
    return adjusted


# ── Gini-specific utilities ──────────────────────────────────────────────────

def gini_pick_row(gini_res: pd.DataFrame, label: str):
    """
    Return the first row of *gini_res* whose 'Effect' column matches *label*.

    Returns None when no matching row is found.
    """
    matches = gini_res[gini_res["Effect"] == label]
    return matches.iloc[0] if len(matches) else None


def build_reference_vs_model_table(
    pairwise_df: pd.DataFrame,
    reference_model: str,
    model_label_map: dict,
    preferred_order=None,
) -> pd.DataFrame:
    """
    Build a per-condition reference table (e.g., all models vs Claude)
    from pairwise Tukey rows.

    Expected columns in pairwise_df:
      higher_model, lower_model, M_higher, M_lower, Delta, p_adj, d
    """
    if pairwise_df is None or pairwise_df.empty:
        return pd.DataFrame()

    ref_rows = pairwise_df[
        (pairwise_df["higher_model"] == reference_model)
        | (pairwise_df["lower_model"] == reference_model)
    ].copy()

    if ref_rows.empty:
        return pd.DataFrame()

    ref_mean = np.nan
    for _, row in ref_rows.iterrows():
        if row["higher_model"] == reference_model:
            ref_mean = float(row["M_higher"])
            break
        if row["lower_model"] == reference_model:
            ref_mean = float(row["M_lower"])
            break

    ref_label = model_label_map.get(reference_model, reference_model)
    out_rows = [
        {
            "Model": ref_label,
            "Mean g_k": ref_mean,
            "Delta vs Claude": "-",
            "p vs Claude": "-",
            "Cohen's d vs Claude": "-",
        }
    ]

    for _, row in ref_rows.iterrows():
        if row["higher_model"] == reference_model:
            other_model = row["lower_model"]
            other_mean = float(row["M_lower"])
        else:
            other_model = row["higher_model"]
            other_mean = float(row["M_higher"])

        p_val = float(row["p_adj"])
        d_val = float(row["d"]) if pd.notna(row["d"]) else np.nan
        delta = float(row["Delta"])

        out_rows.append(
            {
                "Model": model_label_map.get(other_model, other_model),
                "Mean g_k": other_mean,
                "Delta vs Claude": f"{delta:+.2f}",
                "p vs Claude": "<0.001" if p_val < 0.001 else f"{p_val:.3f}",
                "Cohen's d vs Claude": (
                    f"{d_val:.2f}" if np.isfinite(d_val) else "NA"
                ),
            }
        )

    out_df = pd.DataFrame(out_rows).drop_duplicates(
        subset=["Model"], keep="first"
        )

    if preferred_order:
        out_df["_order"] = pd.Categorical(
            out_df["Model"], categories=preferred_order, ordered=True
        )
        out_df = out_df.sort_values("_order").drop(columns=["_order"])

    return out_df.reset_index(drop=True)


# ── Data loading ─────────────────────────────────────────────────────────────

def load_run_data(run_sources: dict) -> pd.DataFrame:
    """
    Load all run JSON files from *run_sources*, compute g_k and PPI_k,
    apply the pre-exhaustion filter (fair_share > 0), and annotate
    behaviour categories (empathic / fair / greedy).

    Parameters
    ----------
    run_sources : dict mapping setup-name → Path to the runs directory

    Returns
    -------
    pd.DataFrame with columns:
        setup, run_id, model, version, condition, position_k, agent,
        fair_share, g_k, p_rem_k, ppi_k, behaviour
    """
    rows = []
    for setup, runs_dir in run_sources.items():
        files = sorted(runs_dir.glob("*.json")) if runs_dir.exists() else []
        print(f"{setup}: {len(files)} run files")

        for fp in files:
            d = json.loads(fp.read_text())

            run_id = d.get("run_id", fp.stem)
            model = d.get("llm_model", "unknown")
            condition = d.get("condition", "unknown")

            m = re.search(r"_(v\d+)$", run_id)
            version = m.group(1) if m else "unknown"

            allocations = d.get("allocations", [])
            if len(allocations) == 0:
                continue

            n_agents = len(allocations)
            p_total = float(allocations[0]["fair_share"]) * n_agents

            for idx, a in enumerate(allocations, start=1):
                fair_share = float(a["fair_share"])
                g_k = float(a["g_k"])
                p_rem_k = fair_share * (n_agents - idx + 1)
                fair_unit = p_total / n_agents
                ppi_k = p_rem_k / fair_unit if p_total > 0 else np.nan

                rows.append(
                    {
                        "setup": setup,
                        "run_id": run_id,
                        "model": model,
                        "version": version,
                        "condition": condition,
                        "position_k": idx,
                        "agent": a["agent"],
                        "fair_share": fair_share,
                        "g_k": g_k,
                        "p_rem_k": p_rem_k,
                        "ppi_k": ppi_k,
                    }
                )

    result_df = pd.DataFrame(rows)
    result_df = result_df[result_df["fair_share"] > 0].copy()
    result_df["behaviour"] = np.where(
        np.isclose(result_df["g_k"], 1.0),
        "fair",
        np.where(result_df["g_k"] > 1.0, "greedy", "empathic"),
    )
    return result_df


def load_gini_scores(
    score_sources: dict, model_label_map: dict
) -> pd.DataFrame:
    """
    Load Gini score JSON files, parse run metadata from filenames,
    and return a tidy DataFrame with one row per run.

    Parameters
    ----------
    score_sources   : dict mapping setup-name → Path to the scores directory
    model_label_map : mapping from model API name → display label

    Returns
    -------
    pd.DataFrame with columns:
        setup, run_id, model, model_label, condition, version, replicate, gini
    """
    gini_rows = []
    for setup, scores_dir in score_sources.items():
        files = (
            sorted(scores_dir.glob("*.json")) if scores_dir.exists() else []
        )
        print(f"{setup}: {len(files)} score files")

        for fp in files:
            d = json.loads(fp.read_text())
            run_id = d.get("run_id", fp.stem)
            match = re.match(
                r"run_\d+_(.+?)_\d{8}T\d{6}Z_(neutral|emotional)_(v\d+)$",
                run_id,
            )
            if not match:
                continue

            model, condition, version = match.groups()
            replicate = int(version[1:])
            gini_rows.append(
                {
                    "setup": setup,
                    "run_id": run_id,
                    "model": model,
                    "model_label": model_label_map.get(model, model),
                    "condition": condition,
                    "version": version,
                    "replicate": replicate,
                    "gini": float(d.get("gini", np.nan)),
                }
            )

    gini_df = pd.DataFrame(gini_rows)
    if not gini_df.empty:
        gini_df = gini_df.sort_values(
            ["setup", "condition", "model_label", "replicate"]
        ).reset_index(drop=True)
    return gini_df







