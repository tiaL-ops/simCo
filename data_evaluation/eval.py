"""
Inter-rater agreement analysis
  - Aggregate JSON scores using the median of 3 human raters
  - Extract Rater 4 (column D, items A & B) from multi-section CSV files
  - Compare aggregate vs Rater 4 cell-by-cell
  - Compute Cohen's Kappa (unweighted, linear-weighted, quadratic-weighted)

Usage:
    python analysis.py
    (CSV files must be in the same folder as this script)
"""

import json
import statistics
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────────────────

raw_json = '''
[
  {
        "rater": "rater1", "form": "Form 1",
    "Claude_E":  {"A_ER":"2","A_IN":"1","A_EX":"1","B_ER":"2","B_IN":"2","B_EX":"1"},
    "Claude_N":  {"A_ER":"1","A_IN":"2","A_EX":"2","B_ER":"1","B_IN":"2","B_EX":"2"},
    "Gemini_E":  {"A_ER":"2","A_IN":"2","A_EX":"1","B_ER":"2","B_IN":"2","B_EX":"0"},
    "Gemini_N":  {"A_ER":"1","A_IN":"1","A_EX":"1","B_ER":"0","B_IN":"1","B_EX":"0"},
    "GPT_E":     {"A_ER":"1","A_IN":"2","A_EX":"0","B_ER":"1","B_IN":"2","B_EX":"0"},
    "GPT_N":     {"A_ER":"0","A_IN":"1","A_EX":"0","B_ER":"0","B_IN":"0","B_EX":"0"},
    "Grok_E":    {"A_ER":"2","A_IN":"2","A_EX":"2","B_ER":"2","B_IN":"2","B_EX":"2"},
    "Grok_N":    {"A_ER":"1","A_IN":"1","A_EX":"1","B_ER":"1","B_IN":"1","B_EX":"1"}
  },
  {
    "rater": "rater2", "form": "Form 2",
    "Claude_E":  {"A_ER":"2","A_IN":"2","A_EX":"2","B_ER":"2","B_IN":"2","B_EX":"1"},
    "Claude_N":  {"A_ER":"2","A_IN":"1","A_EX":"1","B_ER":"2","B_IN":"2","B_EX":"1"},
    "Gemini_E":  {"A_ER":"2","A_IN":"2","A_EX":"2","B_ER":"2","B_IN":"2","B_EX":"2"},
    "Gemini_N":  {"A_ER":"2","A_IN":"1","A_EX":"1","B_ER":"1","B_IN":"1","B_EX":"0"},
    "GPT_E":     {"A_ER":"2","A_IN":"2","A_EX":"1","B_ER":"1","B_IN":"1","B_EX":"0"},
    "GPT_N":     {"A_ER":"0","A_IN":"0","A_EX":"1","B_ER":"0","B_IN":"0","B_EX":"0"},
    "Grok_E":    {"A_ER":"2","A_IN":"2","A_EX":"2","B_ER":"2","B_IN":"2","B_EX":"2"},
    "Grok_N":    {"A_ER":"2","A_IN":"0","A_EX":"1","B_ER":"2","B_IN":"0","B_EX":"1"}
  },
  {
    "rater": "rater3", "form": "Form 3",
    "Claude_E":  {"A_ER":"2","A_IN":"2","A_EX":"2","B_ER":"2","B_IN":"2","B_EX":"1"},
    "Claude_N":  {"A_ER":"2","A_IN":"1","A_EX":"2","B_ER":"2","B_IN":"1","B_EX":"2"},
    "Gemini_E":  {"A_ER":"2","A_IN":"2","A_EX":"2","B_ER":"2","B_IN":"2","B_EX":"1"},
    "Gemini_N":  {"A_ER":"1","A_IN":"1","A_EX":"2","B_ER":"2","B_IN":"1","B_EX":"1"},
    "GPT_E":     {"A_ER":"2","A_IN":"2","A_EX":"1","B_ER":"2","B_IN":"2","B_EX":"0"},
    "GPT_N":     {"A_ER":"1","A_IN":"1","A_EX":"2","B_ER":"2","B_IN":"1","B_EX":"0"},
    "Grok_E":    {"A_ER":"2","A_IN":"2","A_EX":"2","B_ER":"2","B_IN":"2","B_EX":"2"},
    "Grok_N":    {"A_ER":"2","A_IN":"1","A_EX":"2","B_ER":"2","B_IN":"2","B_EX":"2"}
  }
]
'''

CSV_FILES = {
    "Claude_E": "Claude_E.csv",
    "Claude_N": "Claude_N.csv",
    "Gemini_E": "Gemini_E.csv",
    "Gemini_N": "Gemini_N.csv",
    "GPT_E":    "GPT_E.csv",
    "GPT_N":    "GPT_N.csv",
    "Grok_E":   "Grok_E.csv",
    "Grok_N":   "Grok_N.csv",
}

MODELS     = ["Claude_E","Claude_N","Gemini_E","Gemini_N","GPT_E","GPT_N","Grok_E","Grok_N"]
DIMS       = ["A_ER","A_IN","A_EX","B_ER","B_IN","B_EX"]
RATER4_COL = "D"    # column D = Rater 4 in every CSV
LABELS     = [0, 1, 2]
BASE_DIR   = Path(__file__).resolve().parent


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Aggregate JSON scores (median across 3 raters)
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_json(raw_json: str) -> dict:
    """
    For each (model, dimension) pair collect the integer score from all
    three raters and return the median.

    Returns: { model: { dim: float (median) } }
    """
    data = json.loads(raw_json)
    aggregate = {}
    for model in MODELS:
        aggregate[model] = {}
        for dim in DIMS:
            scores = [
                int(rater[model][dim])
                for rater in data
                if model in rater and dim in rater.get(model, {})
            ]
            aggregate[model][dim] = statistics.median(scores)
    return aggregate


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Parse multi-section CSVs and extract Rater 4 (column D)
# ─────────────────────────────────────────────────────────────────────────────

def parse_csv_sections(filepath: str) -> dict:
    """
    Parse a multi-section CSV.  Each section begins with a header row
    whose first cell is the section name (ER / IN / EX) and second cell is A.

    Returns: { section: { row: { col: int|None } } }
    """
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

            if current_section and first in list("ABCDEFGHIJ"):  # data row
                row_scores = {}
                for i, col in enumerate(current_header[1:], start=1):
                    if col in list("ABCDEFGHIJ") and i < len(parts):
                        val = parts[i]
                        row_scores[col] = None if val == "-" else int(val)
                sections[current_section][first] = row_scores

    return sections


def extract_rater4(csv_files: dict) -> dict:
    """
    Extract Rater 4's (column D) scores for items A and B from every CSV.

    Returns: { model: { "A_ER": int, ..., "B_EX": int } }
    """
    rater4 = {}
    for model, fpath in csv_files.items():
        sections      = parse_csv_sections(fpath)
        rater4[model] = {}
        for item, section in [("A","ER"),("A","IN"),("A","EX"),
                               ("B","ER"),("B","IN"),("B","EX")]:
            key   = f"{item}_{section}"
            score = sections.get(section, {}).get(item, {}).get(RATER4_COL, None)
            rater4[model][key] = score
    return rater4


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Cohen's Kappa
# ─────────────────────────────────────────────────────────────────────────────

def kappa_band(k: float) -> str:
    """Landis & Koch (1977) interpretation of kappa."""
    if k < 0:     return "Poor"
    if k < 0.20:  return "Slight"
    if k < 0.40:  return "Fair"
    if k < 0.60:  return "Moderate"
    if k < 0.80:  return "Substantial"
    return "Almost perfect"


def compute_kappa(y1: list, y2: list) -> dict:
    """
    Compute unweighted, linear-weighted, and quadratic-weighted kappa.
    Returns dict with keys: k, k_linear, k_quadratic.
    """
    k = _cohen_kappa(y1, y2, weight="none")
    kl = _cohen_kappa(y1, y2, weight="linear")
    kq = _cohen_kappa(y1, y2, weight="quadratic")
    return {"k": k, "k_linear": kl, "k_quadratic": kq}


def _cohen_kappa(y1: list, y2: list, weight: str) -> float:
    """Pure-Python Cohen's kappa for none, linear, and quadratic weights."""
    pairs = [(a, b) for a, b in zip(y1, y2) if a is not None and b is not None]
    if not pairs:
        return float("nan")

    n_labels = len(LABELS)
    if n_labels < 2:
        return float("nan")

    label_to_idx = {label: idx for idx, label in enumerate(LABELS)}
    matrix = [[0 for _ in range(n_labels)] for _ in range(n_labels)]
    row_totals = [0 for _ in range(n_labels)]
    col_totals = [0 for _ in range(n_labels)]

    for a, b in pairs:
        if a not in label_to_idx or b not in label_to_idx:
            continue
        i = label_to_idx[a]
        j = label_to_idx[b]
        matrix[i][j] += 1
        row_totals[i] += 1
        col_totals[j] += 1

    n = sum(sum(row) for row in matrix)
    if n == 0:
        return float("nan")

    if weight == "none":
        weights = [[0.0 if i == j else 1.0 for j in range(n_labels)] for i in range(n_labels)]
    elif weight == "linear":
        denom = float(n_labels - 1)
        weights = [[abs(i - j) / denom for j in range(n_labels)] for i in range(n_labels)]
    elif weight == "quadratic":
        denom = float((n_labels - 1) ** 2)
        weights = [[((i - j) ** 2) / denom for j in range(n_labels)] for i in range(n_labels)]
    else:
        return float("nan")

    observed = [[matrix[i][j] / n for j in range(n_labels)] for i in range(n_labels)]
    expected = [
        [((row_totals[i] / n) * (col_totals[j] / n)) for j in range(n_labels)]
        for i in range(n_labels)
    ]

    num = 0.0
    den = 0.0
    for i in range(n_labels):
        for j in range(n_labels):
            num += weights[i][j] * observed[i][j]
            den += weights[i][j] * expected[i][j]

    if den == 0:
        return 1.0 if num == 0 else float("nan")

    return 1.0 - (num / den)


def compute_all_kappas(aggregate: dict, rater4: dict) -> dict:
    """
    Compute Cohen's Kappa at three levels:
      - overall   : all 48 cells pooled
      - per_model : one kappa per model (6 cells each)
      - per_dim   : one kappa per dimension (8 cells each)

    Note: aggregate medians are rounded to the nearest integer before
    computing kappa, as kappa requires discrete category labels.
    """
    all_agg, all_r4 = [], []
    for m in MODELS:
        for d in DIMS:
            all_agg.append(round(aggregate[m][d]))
            all_r4.append(rater4[m][d])

    result = {
        "overall":   compute_kappa(all_agg, all_r4),
        "per_model": {},
        "per_dim":   {},
    }

    for m in MODELS:
        y1 = [round(aggregate[m][d]) for d in DIMS]
        y2 = [rater4[m][d] for d in DIMS]
        result["per_model"][m] = compute_kappa(y1, y2)

    for d in DIMS:
        y1 = [round(aggregate[m][d]) for m in MODELS]
        y2 = [rater4[m][d] for m in MODELS]
        result["per_dim"][d] = compute_kappa(y1, y2)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Print all results
# ─────────────────────────────────────────────────────────────────────────────

def print_results(aggregate: dict, rater4: dict, kappas: dict) -> None:

    W = 72

    # ── Aggregate table ──────────────────────────────────────────────────────
    print("=" * W)
    print("TABLE 1 — Aggregate scores (median of 3 raters)")
    print("=" * W)
    print(f"{'Model':<12}", end="")
    for d in DIMS: print(f"  {d}", end="")
    print()
    print("-" * W)
    for m in MODELS:
        print(f"{m:<12}", end="")
        for d in DIMS: print(f"  {aggregate[m][d]:>4}", end="")
        print()

    # ── Rater 4 table ────────────────────────────────────────────────────────
    print("\n" + "=" * W)
    print("TABLE 2 — Rater 4 scores (column D, items A & B)")
    print("=" * W)
    print(f"{'Model':<12}", end="")
    for d in DIMS: print(f"  {d}", end="")
    print()
    print("-" * W)
    for m in MODELS:
        print(f"{m:<12}", end="")
        for d in DIMS: print(f"  {str(rater4[m][d]):>4}", end="")
        print()

    # ── Comparison table ─────────────────────────────────────────────────────
    print("\n" + "=" * W)
    print("TABLE 3 — Cell-by-cell comparison: aggregate vs Rater 4")
    print("=" * W)
    print(f"{'Model':<12}  {'Dim':<6}  {'Agg':>4}  {'R4':>4}  {'Diff':>5}  Match")
    print("-" * W)
    matches, total = 0, 0
    for m in MODELS:
        for d in DIMS:
            a    = aggregate[m][d]
            r    = rater4[m][d]
            diff = r - a
            sym  = "=" if diff == 0 else ("+" if diff > 0 else str(int(diff)))
            matches += 1 if diff == 0 else 0
            total   += 1
            print(f"{m:<12}  {d:<6}  {a:>4}  {str(r):>4}  {str(diff):>5}  {sym}")
    print("-" * W)
    print(f"Exact match rate: {matches}/{total} = {matches/total:.1%}")

    # ── Model-level summary + kappa ──────────────────────────────────────────
    print("\n" + "=" * W)
    print("TABLE 4 — Model-level summary with Cohen's Kappa")
    print("=" * W)
    print(f"{'Model':<12}  {'AggMean':>7}  {'R4Mean':>6}  {'Diff':>6}  "
          f"{'kappa':>6}  {'k_lin':>6}  {'k_quad':>7}  Band")
    print("-" * W)
    for m in MODELS:
        am = sum(aggregate[m][d] for d in DIMS) / 6
        rm = sum(rater4[m][d]   for d in DIMS) / 6
        df = rm - am
        kv = kappas["per_model"][m]
        print(
            f"{m:<12}  {am:>7.2f}  {rm:>6.2f}  {df:>+6.2f}  "
            f"{kv['k']:>6.3f}  {kv['k_linear']:>6.3f}  {kv['k_quadratic']:>7.3f}  "
            f"{kappa_band(kv['k'])}"
        )

    # ── Per-dimension kappa ──────────────────────────────────────────────────
    print("\n" + "=" * W)
    print("TABLE 5 — Per-dimension Cohen's Kappa (across all 8 models)")
    print("=" * W)
    print(f"{'Dim':<8}  {'kappa':>6}  {'k_lin':>6}  {'k_quad':>7}  Band")
    print("-" * W)
    for d in DIMS:
        kv = kappas["per_dim"][d]
        print(f"{d:<8}  {kv['k']:>6.3f}  {kv['k_linear']:>6.3f}  "
              f"{kv['k_quadratic']:>7.3f}  {kappa_band(kv['k'])}")

    # ── Overall kappa ────────────────────────────────────────────────────────
    print("\n" + "=" * W)
    print("TABLE 6 — Overall Cohen's Kappa (48 observations pooled)")
    print("=" * W)
    kv = kappas["overall"]
    print(f"  kappa (unweighted)  : {kv['k']:.4f}  [{kappa_band(kv['k'])}]")
    print(f"  kappa (linear)      : {kv['k_linear']:.4f}  [{kappa_band(kv['k_linear'])}]")
    print(f"  kappa (quadratic)   : {kv['k_quadratic']:.4f}  [{kappa_band(kv['k_quadratic'])}]")
    print("=" * W)
    print("Bands — Landis & Koch (1977):")
    print("  <0 Poor | 0.01-0.20 Slight | 0.21-0.40 Fair")
    print("  0.41-0.60 Moderate | 0.61-0.80 Substantial | 0.81-1.00 Almost perfect")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    aggregate = aggregate_json(raw_json)
    rater4    = extract_rater4(CSV_FILES)
    kappas    = compute_all_kappas(aggregate, rater4)
    print_results(aggregate, rater4, kappas)