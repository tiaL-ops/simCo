"""
Inter-rater agreement analysis
  - Extract individual scores from JSON (raters 1, 2, 3)
  - Extract Rater 4 (column D, items A & B) from multi-section CSV files
  - Cohen's Kappa: each human rater individually vs Rater 4 (LLM)
  - Krippendorff's Alpha:
      * humans only (raters 1-2-3) — baseline
      * all 4 raters together    — human+LLM reliability
      * per model and per dimension breakdowns for both

Usage:
    python eval.py
    (CSV files must be in the same folder as this script)
"""

import json
import re
import statistics
from pathlib import Path

import krippendorff
import numpy as np
from sklearn.metrics import cohen_kappa_score

# ─────────────────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
path = BASE_DIR / "eval.json"

raw_json = path.read_text(encoding="utf-8")

CSV_FILES = {
    "Claude_E": "matrix_Claude_E.csv",
    "Claude_N": "matrix_Claude_N.csv",
    "Gemini_E": "matrix_Gemini_E.csv",
    "Gemini_N": "matrix_Gemini_N.csv",
    "Grok_E":   "matrix_Grok_E.csv",
    "Grok_N":   "matrix_Grok_N.csv",
}

MODELS     = ["Claude_E", "Claude_N", "Gemini_E", "Gemini_N", "Grok_E", "Grok_N"]
DIMS       = ["A_ER", "A_IN", "A_EX", "B_ER", "B_IN", "B_EX"]
RATER4_COL = "D"
LABELS     = [0, 1, 2]
RATER_KEYS = ["rater1", "rater2", "rater3"]


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _parse_label_score(value) -> int | None:
    """Parse score labels like 0, 1, 2 or strings such as '2 - Strong'."""
    if value is None:
        return None
    if isinstance(value, int):
        return value if value in LABELS else None
    if isinstance(value, float):
        iv = int(value)
        return iv if iv in LABELS and value == iv else None
    text = str(value).strip()
    if not text:
        return None
    m = re.search(r"\b([012])\b", text)
    if not m:
        return None
    return int(m.group(1))


def kappa_band(k: float) -> str:
    """Landis & Koch (1977) interpretation of kappa."""
    if k != k:    return "n/a"       # NaN check
    if k < 0:     return "Poor"
    if k < 0.20:  return "Slight"
    if k < 0.40:  return "Fair"
    if k < 0.60:  return "Moderate"
    if k < 0.80:  return "Substantial"
    return "Almost perfect"


def compute_kappa(y1: list, y2: list) -> dict:
    """Unweighted, linear-weighted, and quadratic-weighted kappa."""
    pairs = [(a, b) for a, b in zip(y1, y2) if a is not None and b is not None]
    if not pairs:
        nan = float("nan")
        return {"k": nan, "k_linear": nan, "k_quadratic": nan}
    y1v = [a for a, _ in pairs]
    y2v = [b for _, b in pairs]
    k   = cohen_kappa_score(y1v, y2v, labels=LABELS)
    kl  = cohen_kappa_score(y1v, y2v, labels=LABELS, weights="linear")
    kq  = cohen_kappa_score(y1v, y2v, labels=LABELS, weights="quadratic")
    return {"k": k, "k_linear": kl, "k_quadratic": kq}


# ─────────────────────────────────────────────────────────────────────────────
# Krippendorff's Alpha
# ─────────────────────────────────────────────────────────────────────────────

def _alpha_band(a: float) -> str:
    """Krippendorff's own thresholds (>= 0.800 reliable, >= 0.667 tentative)."""
    if a != a:    return "n/a"
    if a >= 0.80: return "Reliable"
    if a >= 0.67: return "Tentative"
    return "Unreliable"


def compute_alpha(reliability_data: list[list]) -> dict:
    """
    reliability_data : list of rater vectors, each of length n_items.
                       None / np.nan = missing.
    Returns nominal and ordinal alpha.
    """
    # krippendorff expects shape (n_raters, n_items), missing as np.nan
    arr = np.array(
        [[np.nan if v is None else float(v) for v in row]
         for row in reliability_data],
        dtype=float,
    )
    if arr.shape[1] == 0:
        nan = float("nan")
        return {"nominal": nan, "ordinal": nan}
    try:
        a_nom = krippendorff.alpha(reliability_data=arr, level_of_measurement="nominal")
    except ValueError:
        a_nom = float("nan")   # degenerate: all scores identical, zero variance
    try:
        a_ord = krippendorff.alpha(reliability_data=arr, level_of_measurement="ordinal")
    except ValueError:
        a_ord = float("nan")
    return {"nominal": a_nom, "ordinal": a_ord}


def build_reliability_matrix(score_dicts: list[dict]) -> list[list]:
    """
    score_dicts : one dict per rater, each { model: { dim: score } }.
    Returns rows = raters, cols = items (model×dim in fixed order).
    """
    return [
        [sd[m][d] for m in MODELS for d in DIMS]
        for sd in score_dicts
    ]


def compute_all_alphas(per_rater: dict, rater4: dict) -> dict:
    """
    Compute Krippendorff's Alpha at three levels:
      overall   : all items pooled  (6 models × 6 dims = 36 items)
      per_model : one alpha per model (6 items each)
      per_dim   : one alpha per dim   (6 items each — one per model)

    Each level has two variants:
      humans_only : raters 1-2-3
      all_raters  : raters 1-2-3 + rater 4 (LLM)
    """
    humans = [per_rater[rk] for rk in RATER_KEYS]   # list of 3 score dicts
    all4   = humans + [rater4]                        # list of 4 score dicts

    def _alpha_pair(score_dicts_h, score_dicts_a, items_fn):
        rows_h = [items_fn(sd) for sd in score_dicts_h]
        rows_a = [items_fn(sd) for sd in score_dicts_a]
        return {
            "humans_only": compute_alpha(rows_h),
            "all_raters":  compute_alpha(rows_a),
        }

    # Overall
    overall = _alpha_pair(
        humans, all4,
        lambda sd: [sd[m][d] for m in MODELS for d in DIMS],
    )

    # Per model
    per_model = {}
    for m in MODELS:
        per_model[m] = _alpha_pair(
            humans, all4,
            lambda sd, m=m: [sd[m][d] for d in DIMS],
        )

    # Per dimension
    per_dim = {}
    for d in DIMS:
        per_dim[d] = _alpha_pair(
            humans, all4,
            lambda sd, d=d: [sd[m][d] for m in MODELS],
        )

    return {"overall": overall, "per_model": per_model, "per_dim": per_dim}


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Parse JSON: extract per-rater scores AND aggregate median
# ─────────────────────────────────────────────────────────────────────────────

def parse_json(raw_json: str) -> tuple[dict, dict]:
    """
    Returns:
      per_rater  : { "rater1": { model: { dim: int } }, "rater2": ..., "rater3": ... }
      aggregate  : { model: { dim: float (median of rater1/2/3) } }
    """
    data = json.loads(raw_json)

    # Index by rater key
    by_rater = {}
    for entry in data:
        rater_key = entry.get("rater")          # "rater1", "rater2", "rater3"
        if rater_key not in RATER_KEYS:
            continue
        by_rater[rater_key] = entry

    # Build per_rater scores
    per_rater = {rk: {} for rk in RATER_KEYS}
    for rk in RATER_KEYS:
        entry = by_rater.get(rk, {})
        for model in MODELS:
            per_rater[rk][model] = {}
            for dim in DIMS:
                raw = entry.get(model, {}).get(dim)
                per_rater[rk][model][dim] = _parse_label_score(raw)

    # Build aggregate (median across the 3 raters, ignoring None)
    aggregate = {}
    for model in MODELS:
        aggregate[model] = {}
        for dim in DIMS:
            scores = [
                per_rater[rk][model][dim]
                for rk in RATER_KEYS
                if per_rater[rk][model][dim] is not None
            ]
            if not scores:
                raise ValueError(f"No valid scores for {model}/{dim}")
            aggregate[model][dim] = statistics.median(scores)

    return per_rater, aggregate


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Parse CSVs and extract Rater 4 (column D, rows A & B)
# ─────────────────────────────────────────────────────────────────────────────

def parse_csv_sections(filepath: str) -> dict:
    csv_path = Path(filepath)
    if not csv_path.is_absolute():
        candidate = BASE_DIR / csv_path
        if candidate.exists():
            csv_path = candidate

    sections        = {}
    current_section = None
    current_header  = None

    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        for line in fh:
            line  = line.rstrip("\r\n")
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            first = parts[0]

            if len(parts) > 1 and parts[1] == "A":          # header row
                current_section = first
                current_header  = parts
                sections[current_section] = {}
                continue

            if current_section and first in list("ABCDEFGHIJ"):
                row_scores = {}
                for i, col in enumerate(current_header[1:], start=1):
                    if col in list("ABCDEFGHIJ") and i < len(parts):
                        val = parts[i]
                        row_scores[col] = None if val in ("-", "?") else int(val)
                sections[current_section][first] = row_scores

    return sections


def extract_rater4(csv_files: dict) -> dict:
    """{ model: { dim: int } } — column D, rows A & B only."""
    rater4 = {}
    for model, fpath in csv_files.items():
        sections      = parse_csv_sections(fpath)
        rater4[model] = {}
        for item, section in [("A", "ER"), ("A", "IN"), ("A", "EX"),
                               ("B", "ER"), ("B", "IN"), ("B", "EX")]:
            key   = f"{item}_{section}"
            score = sections.get(section, {}).get(item, {}).get(RATER4_COL)
            rater4[model][key] = score
    return rater4


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Compute all kappas
# ─────────────────────────────────────────────────────────────────────────────

def flatten(scores: dict) -> list:
    """Flatten { model: { dim: score } } into a single list (fixed order)."""
    return [scores[m][d] for m in MODELS for d in DIMS]


def compute_all_kappas(per_rater: dict, aggregate: dict, rater4: dict) -> dict:
    """
    Returns kappas at three levels for each comparison:
      - rater1 vs rater4
      - rater2 vs rater4
      - rater3 vs rater4
      - aggregate vs rater4   (median rounded to int)

    Each comparison has:
      overall   : all 48 cells pooled
      per_model : one kappa per model (6 cells)
      per_dim   : one kappa per dim   (6 cells — one per model)
    """
    r4_flat = flatten(rater4)

    results = {}

    # Individual raters vs rater4
    for rk in RATER_KEYS:
        rk_flat = flatten(per_rater[rk])
        entry = {
            "overall":   compute_kappa(rk_flat, r4_flat),
            "per_model": {},
            "per_dim":   {},
        }
        for m in MODELS:
            y1 = [per_rater[rk][m][d] for d in DIMS]
            y2 = [rater4[m][d]        for d in DIMS]
            entry["per_model"][m] = compute_kappa(y1, y2)
        for d in DIMS:
            y1 = [per_rater[rk][m][d] for m in MODELS]
            y2 = [rater4[m][d]        for m in MODELS]
            entry["per_dim"][d] = compute_kappa(y1, y2)
        results[rk] = entry

    # Aggregate vs rater4
    agg_flat = [round(aggregate[m][d]) for m in MODELS for d in DIMS]
    entry = {
        "overall":   compute_kappa(agg_flat, r4_flat),
        "per_model": {},
        "per_dim":   {},
    }
    for m in MODELS:
        y1 = [round(aggregate[m][d]) for d in DIMS]
        y2 = [rater4[m][d]          for d in DIMS]
        entry["per_model"][m] = compute_kappa(y1, y2)
    for d in DIMS:
        y1 = [round(aggregate[m][d]) for m in MODELS]
        y2 = [rater4[m][d]          for m in MODELS]
        entry["per_dim"][d] = compute_kappa(y1, y2)
    results["aggregate"] = entry

    return results


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Print results
# ─────────────────────────────────────────────────────────────────────────────

def _kappa_row(label: str, kv: dict, width: int = 14) -> str:
    return (f"  {label:<{width}}  "
            f"k={kv['k']:>6.3f}  "
            f"k_lin={kv['k_linear']:>6.3f}  "
            f"k_quad={kv['k_quadratic']:>6.3f}  "
            f"[{kappa_band(kv['k'])}]")


def _alpha_row(label: str, av: dict, width: int = 14) -> str:
    nom, ord_ = av["nominal"], av["ordinal"]
    return (f"  {label:<{width}}  "
            f"nominal={nom:>6.3f}  ordinal={ord_:>6.3f}  "
            f"[{_alpha_band(ord_)}]")


def compute_agreement_percentages(per_rater: dict, aggregate: dict, rater4: dict) -> dict:
    """Compute exact-match percentage for each model and rater vs Rater 4 (LLM)."""
    by_model = {}
    for model in MODELS:
        matches_r1 = sum(1 for d in DIMS if per_rater["rater1"][model][d] == rater4[model][d])
        matches_r2 = sum(1 for d in DIMS if per_rater["rater2"][model][d] == rater4[model][d])
        matches_r3 = sum(1 for d in DIMS if per_rater["rater3"][model][d] == rater4[model][d])
        matches_agg = sum(1 for d in DIMS if round(aggregate[model][d]) == rater4[model][d])
        by_model[model] = {
            "rater1_pct": 100.0 * matches_r1 / len(DIMS),
            "rater2_pct": 100.0 * matches_r2 / len(DIMS),
            "rater3_pct": 100.0 * matches_r3 / len(DIMS),
            "aggregate_pct": 100.0 * matches_agg / len(DIMS),
        }
    total_dims = len(MODELS) * len(DIMS)
    matches_r1_all = sum(1 for m in MODELS for d in DIMS if per_rater["rater1"][m][d] == rater4[m][d])
    matches_r2_all = sum(1 for m in MODELS for d in DIMS if per_rater["rater2"][m][d] == rater4[m][d])
    matches_r3_all = sum(1 for m in MODELS for d in DIMS if per_rater["rater3"][m][d] == rater4[m][d])
    matches_agg_all = sum(1 for m in MODELS for d in DIMS if round(aggregate[m][d]) == rater4[m][d])
    by_rater = {
        "rater1_pct": 100.0 * matches_r1_all / total_dims,
        "rater2_pct": 100.0 * matches_r2_all / total_dims,
        "rater3_pct": 100.0 * matches_r3_all / total_dims,
        "aggregate_pct": 100.0 * matches_agg_all / total_dims,
    }
    return {"by_model": by_model, "by_rater": by_rater}


def print_results(per_rater: dict, aggregate: dict, rater4: dict,
                  kappas: dict, alphas: dict, agreements: dict) -> None:
    W = 80
    result_path = BASE_DIR / "result.txt"
    KAPPA_COMPARISONS = [
        ("rater1", "Rater 1 vs Rater 4 (LLM)"),
        ("rater2", "Rater 2 vs Rater 4 (LLM)"),
        ("rater3", "Rater 3 vs Rater 4 (LLM)"),
        ("aggregate", "Aggregate (median) vs Rater 4 (LLM)"),
    ]

    # Full detail goes to result.txt
    lines: list[str] = []

    def add(line: str = "") -> None:
        lines.append(line)

    add("=" * W)
    add("KRIPPENDORFF'S ALPHA — Overall (36 items: 6 models × 6 dims)")
    add("=" * W)
    ov = alphas["overall"]
    add(_alpha_row("Humans only (R1-R2-R3)", ov["humans_only"], width=26))
    add(_alpha_row("All 4 raters (+ LLM)", ov["all_raters"], width=26))
    add()
    add("  Thresholds (Krippendorff): >= 0.800 Reliable | >= 0.667 Tentative | < 0.667 Unreliable")
    add("  Ordinal alpha is the right metric for your 0/1/2 scale.")
    add("  Compare the two rows: if 'all 4' ≈ 'humans only', the LLM rates like a human.")

    add("\n" + "=" * W)
    add("KRIPPENDORFF'S ALPHA — Per model")
    add("=" * W)
    add(f"  {'Model':<12}  {'humans nom':>10}  {'humans ord':>10}  {'all4 nom':>8}  {'all4 ord':>8}  Band (all4 ord)")
    add("  " + "-" * 66)
    for m in MODELS:
        h = alphas["per_model"][m]["humans_only"]
        a = alphas["per_model"][m]["all_raters"]
        add(f"  {m:<12}  {h['nominal']:>10.3f}  {h['ordinal']:>10.3f}  {a['nominal']:>8.3f}  {a['ordinal']:>8.3f}  {_alpha_band(a['ordinal'])}")

    add("\n" + "=" * W)
    add("KRIPPENDORFF'S ALPHA — Per dimension")
    add("=" * W)
    add(f"  {'Dim':<8}  {'humans nom':>10}  {'humans ord':>10}  {'all4 nom':>8}  {'all4 ord':>8}  Band (all4 ord)")
    add("  " + "-" * 62)
    for d in DIMS:
        h = alphas["per_dim"][d]["humans_only"]
        a = alphas["per_dim"][d]["all_raters"]
        add(f"  {d:<8}  {h['nominal']:>10.3f}  {h['ordinal']:>10.3f}  {a['nominal']:>8.3f}  {a['ordinal']:>8.3f}  {_alpha_band(a['ordinal'])}")

    add("\n" + "=" * W)
    add("COHEN'S KAPPA — Each human rater vs Rater 4 (LLM), overall (48 obs pooled)")
    add("=" * W)
    for key, label in KAPPA_COMPARISONS:
        kv = kappas[key]["overall"]
        add(_kappa_row(label, kv, width=34))
    add()
    add("  Bands — Landis & Koch (1977):")
    add("  <0 Poor | 0.01-0.20 Slight | 0.21-0.40 Fair")
    add("  0.41-0.60 Moderate | 0.61-0.80 Substantial | 0.81-1.00 Almost perfect")

    for key, label in KAPPA_COMPARISONS:
        add("\n" + "=" * W)
        add(f"COHEN'S KAPPA DETAIL — {label}")
        add("=" * W)
        add("\n  Per model (6 cells each):")
        add(f"  {'Model':<12}  {'k':>6}  {'k_lin':>6}  {'k_quad':>7}  Band")
        add("  " + "-" * 50)
        for m in MODELS:
            kv = kappas[key]["per_model"][m]
            add(f"  {m:<12}  {kv['k']:>6.3f}  {kv['k_linear']:>6.3f}  {kv['k_quadratic']:>7.3f}  {kappa_band(kv['k'])}")
        add("\n  Per dimension (6 cells each):")
        add(f"  {'Dim':<8}  {'k':>6}  {'k_lin':>6}  {'k_quad':>7}  Band")
        add("  " + "-" * 50)
        for d in DIMS:
            kv = kappas[key]["per_dim"][d]
            add(f"  {d:<8}  {kv['k']:>6.3f}  {kv['k_linear']:>6.3f}  {kv['k_quadratic']:>7.3f}  {kappa_band(kv['k'])}")

    add("\n" + "=" * W)
    add("EXACT AGREEMENT PERCENTAGE — Each rater vs Rater 4 (LLM)")
    add("=" * W)
    add("Per-model agreement (% of 6 dimensions matching):")
    add(f"  {'Model':<12}  {'R1 %':>6}  {'R2 %':>6}  {'R3 %':>6}  {'AGG %':>7}")
    add("  " + "-" * 46)
    for m in MODELS:
        ag = agreements["by_model"][m]
        add(f"  {m:<12}  {ag['rater1_pct']:>5.1f}%  {ag['rater2_pct']:>5.1f}%  {ag['rater3_pct']:>5.1f}%  {ag['aggregate_pct']:>6.1f}%")
    add()
    add("Overall agreement (% of 36 dimensions matching per rater):")
    ag_overall = agreements["by_rater"]
    add(f"  Rater 1:       {ag_overall['rater1_pct']:.1f}%")
    add(f"  Rater 2:       {ag_overall['rater2_pct']:.1f}%")
    add(f"  Rater 3:       {ag_overall['rater3_pct']:.1f}%")
    add(f"  Aggregate:     {ag_overall['aggregate_pct']:.1f}%")

    add("\n" + "=" * W)
    add("REFERENCE — Raw scores (R1 R2 R3 = humans, AGG = median, R4 = LLM)")
    add("=" * W)
    add(f"{'Model':<12}  {'Dim':<6}  {'R1':>3}  {'R2':>3}  {'R3':>3}  {'AGG':>4}  {'R4':>3}")
    add("-" * W)
    for m in MODELS:
        for d in DIMS:
            r1 = per_rater["rater1"][m][d]
            r2 = per_rater["rater2"][m][d]
            r3 = per_rater["rater3"][m][d]
            agg = aggregate[m][d]
            r4 = rater4[m][d]
            add(f"{m:<12}  {d:<6}  {str(r1):>3}  {str(r2):>3}  {str(r3):>3}  {agg:>4}  {str(r4):>3}")
        add()

    result_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ag_overall = agreements["by_rater"]
    print("=" * W)
    print("FINAL RESULTS")
    print("=" * W)
    print("Krippendorff's Alpha (overall)")
    print(_alpha_row("Humans only (R1-R2-R3)", ov["humans_only"], width=26))
    print(_alpha_row("All 4 raters (+ LLM)", ov["all_raters"], width=26))
    print()
    print("Cohen's Kappa (overall)")
    for key, label in KAPPA_COMPARISONS:
        kv = kappas[key]["overall"]
        print(_kappa_row(label, kv, width=34))
    print()
    print("Exact Agreement Percentage (overall)")
    print(f"  Rater 1:       {ag_overall['rater1_pct']:.1f}%")
    print(f"  Rater 2:       {ag_overall['rater2_pct']:.1f}%")
    print(f"  Rater 3:       {ag_overall['rater3_pct']:.1f}%")
    print(f"  Aggregate:     {ag_overall['aggregate_pct']:.1f}%")
    print()
    print(f"Detailed report saved to: {result_path.name}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    per_rater, aggregate = parse_json(raw_json)
    rater4               = extract_rater4(CSV_FILES)
    kappas               = compute_all_kappas(per_rater, aggregate, rater4)
    alphas               = compute_all_alphas(per_rater, rater4)
    agreements           = compute_agreement_percentages(per_rater, aggregate, rater4)
    print_results(per_rater, aggregate, rater4, kappas, alphas, agreements)