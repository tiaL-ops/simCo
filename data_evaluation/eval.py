"""Evaluation script using majority-vote human labels.

Metrics reported (no kappa):
- Accuracy (classification)
- Macro-F1 (classification, labels 0/1/2)
- Random baseline accuracy (1/3)
- T-f1 and IOU-f1 for rationale extraction when rationale annotations exist

Gold labels are established by taking the most common score among the 3 human
raters for each (model, dimension) cell.

Usage:
    python eval.py
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, f1_score

# ---------------------------------------------------------------------------
# Data config
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
EVAL_JSON_PATH = BASE_DIR / "eval.json"

CSV_FILES = {
    "Claude_E": "matrix_Claude_E.csv",
    "Claude_N": "matrix_Claude_N.csv",
    "Gemini_E": "matrix_Gemini_E.csv",
    "Gemini_N": "matrix_Gemini_N.csv",
    "Grok_E": "matrix_Grok_E.csv",
    "Grok_N": "matrix_Grok_N.csv",
}

MODELS = ["Claude_E", "Claude_N", "Gemini_E", "Gemini_N", "Grok_E", "Grok_N"]
DIMS = ["A_ER", "A_IN", "A_EX", "B_ER", "B_IN", "B_EX"]
RATER4_COL = "D"
LABELS = [0, 1, 2]
RATER_KEYS = ["rater1", "rater2", "rater3"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_label_score(value) -> int | None:
    """Parse score labels like 0, 1, 2 or strings like '2 - Strong'."""
    if value is None:
        return None
    if isinstance(value, int):
        return value if value in LABELS else None
    if isinstance(value, float):
        iv = int(value)
        return iv if value == iv and iv in LABELS else None
    text = str(value).strip()
    if not text:
        return None
    m = re.search(r"\b([012])\b", text)
    return int(m.group(1)) if m else None


def _majority_vote(values: list[int | None]) -> int | None:
    """Most common score among 3 raters; tie fallback uses rounded median."""
    valid = [v for v in values if v is not None]
    if not valid:
        return None

    counts = Counter(valid)
    top_count = max(counts.values())
    top_labels = sorted([label for label, c in counts.items() if c == top_count])
    if len(top_labels) == 1:
        return top_labels[0]

    # Tie fallback for cases like [0, 1, 2].
    return int(round(statistics.median(valid)))


def _metrics(y_true: list[int], y_pred: list[int]) -> dict:
    if not y_true:
        return {
            "n": 0,
            "accuracy": float("nan"),
            "macro_f1": float("nan"),
            "random_baseline_accuracy": 1.0 / 3.0,
        }
    return {
        "n": len(y_true),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)),
        "random_baseline_accuracy": 1.0 / 3.0,
    }


# ---------------------------------------------------------------------------
# Rationale metrics (only computed when rationale text is available)
# ---------------------------------------------------------------------------
TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize_with_spans(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in TOKEN_RE.finditer(text)]


def _extract_segments(rationale_text: str) -> list[str]:
    parts = re.split(r"\||\n+", rationale_text)
    return [p.strip() for p in parts if p.strip()]


def _build_mask_from_rationale(response_text: str, rationale_text: str) -> list[int]:
    tokens = _tokenize_with_spans(response_text)
    mask = [0] * len(tokens)
    if not rationale_text.strip():
        return mask

    response_lower = response_text.lower()
    matched = False
    for seg in _extract_segments(rationale_text):
        seg_l = seg.lower()
        if len(seg_l) < 2:
            continue
        start = 0
        while True:
            idx = response_lower.find(seg_l, start)
            if idx == -1:
                break
            end = idx + len(seg_l)
            for i, (_, ts, te) in enumerate(tokens):
                if te > idx and ts < end:
                    mask[i] = 1
            matched = True
            start = idx + 1

    if matched:
        return mask

    rat_toks = {tok.lower() for tok, _, _ in _tokenize_with_spans(rationale_text)}
    for i, (tok, _, _) in enumerate(tokens):
        if tok.lower() in rat_toks:
            mask[i] = 1
    return mask


def _binary_f1(true_mask: list[int], pred_mask: list[int]) -> float:
    n = min(len(true_mask), len(pred_mask))
    if n == 0:
        return 0.0
    tp = fp = fn = 0
    for t, p in zip(true_mask[:n], pred_mask[:n]):
        if t == 1 and p == 1:
            tp += 1
        elif t == 0 and p == 1:
            fp += 1
        elif t == 1 and p == 0:
            fn += 1
    den = 2 * tp + fp + fn
    return 0.0 if den == 0 else (2 * tp) / den


def _spans_from_mask(mask: list[int]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = None
    for i, val in enumerate(mask):
        if val == 1 and start is None:
            start = i
        elif val == 0 and start is not None:
            spans.append((start, i - 1))
            start = None
    if start is not None:
        spans.append((start, len(mask) - 1))
    return spans


def _span_iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    left = max(a[0], b[0])
    right = min(a[1], b[1])
    if right < left:
        return 0.0
    inter = right - left + 1
    union = (a[1] - a[0] + 1) + (b[1] - b[0] + 1) - inter
    return 0.0 if union <= 0 else inter / union


def _span_f1(true_mask: list[int], pred_mask: list[int], threshold: float = 0.5) -> float:
    true_spans = _spans_from_mask(true_mask)
    pred_spans = _spans_from_mask(pred_mask)
    if not true_spans and not pred_spans:
        return 1.0
    if not true_spans or not pred_spans:
        return 0.0

    matched_true: set[int] = set()
    tp = 0
    for pred in pred_spans:
        best_idx = -1
        best_iou = 0.0
        for idx, gt in enumerate(true_spans):
            if idx in matched_true:
                continue
            iou = _span_iou(pred, gt)
            if iou > best_iou:
                best_iou = iou
                best_idx = idx
        if best_idx >= 0 and best_iou > threshold:
            tp += 1
            matched_true.add(best_idx)

    fp = len(pred_spans) - tp
    fn = len(true_spans) - tp
    den = 2 * tp + fp + fn
    return 0.0 if den == 0 else (2 * tp) / den


# ---------------------------------------------------------------------------
# Data parsing
# ---------------------------------------------------------------------------

def parse_json_raters(raw_json: str) -> tuple[dict, dict]:
    """
    Returns:
      per_rater: {rater_key: {model: {dim: int|None}}}
      majority:  {model: {dim: int|None}}
    """
    data = json.loads(raw_json)

    by_rater = {}
    for entry in data:
        rk = entry.get("rater")
        if rk in RATER_KEYS:
            by_rater[rk] = entry

    per_rater = {rk: {} for rk in RATER_KEYS}
    for rk in RATER_KEYS:
        entry = by_rater.get(rk, {})
        for model in MODELS:
            per_rater[rk][model] = {}
            for dim in DIMS:
                per_rater[rk][model][dim] = _parse_label_score(entry.get(model, {}).get(dim))

    majority = {}
    for model in MODELS:
        majority[model] = {}
        for dim in DIMS:
            values = [per_rater[rk][model][dim] for rk in RATER_KEYS]
            majority[model][dim] = _majority_vote(values)

    return per_rater, majority


def parse_csv_sections(filepath: str) -> dict:
    csv_path = Path(filepath)
    if not csv_path.is_absolute():
        candidate = BASE_DIR / csv_path
        if candidate.exists():
            csv_path = candidate

    sections = {}
    current_section = None
    current_header = None

    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            first = parts[0]

            if len(parts) > 1 and parts[1] == "A":
                current_section = first
                current_header = parts
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
    """Return { model: { dim: int|None } } from column D, rows A and B."""
    rater4 = {}
    for model, fpath in csv_files.items():
        sections = parse_csv_sections(fpath)
        rater4[model] = {}
        for item, section in [
            ("A", "ER"), ("A", "IN"), ("A", "EX"),
            ("B", "ER"), ("B", "IN"), ("B", "EX"),
        ]:
            key = f"{item}_{section}"
            rater4[model][key] = sections.get(section, {}).get(item, {}).get(RATER4_COL)
    return rater4


# ---------------------------------------------------------------------------
# Metric evaluation
# ---------------------------------------------------------------------------

def compute_classification_metrics(majority: dict, rater4: dict) -> dict:
    y_true_all: list[int] = []
    y_pred_all: list[int] = []

    per_model = {}
    for model in MODELS:
        y_true: list[int] = []
        y_pred: list[int] = []
        for dim in DIMS:
            gt = majority[model][dim]
            pred = rater4[model][dim]
            if gt is None or pred is None:
                continue
            y_true.append(int(gt))
            y_pred.append(int(pred))
        per_model[model] = _metrics(y_true, y_pred)
        y_true_all.extend(y_true)
        y_pred_all.extend(y_pred)

    per_dim = {}
    for dim in DIMS:
        y_true: list[int] = []
        y_pred: list[int] = []
        for model in MODELS:
            gt = majority[model][dim]
            pred = rater4[model][dim]
            if gt is None or pred is None:
                continue
            y_true.append(int(gt))
            y_pred.append(int(pred))
        per_dim[dim] = _metrics(y_true, y_pred)

    return {
        "overall": _metrics(y_true_all, y_pred_all),
        "per_model": per_model,
        "per_dim": per_dim,
    }


def compute_rationale_metrics() -> dict:
    """
    This dataset currently contains EI labels only (0/1/2) without rationale spans.
    We report rationale metrics as unavailable to avoid fabricated numbers.
    """
    return {
        "available": False,
        "t_f1": float("nan"),
        "iou_f1": float("nan"),
        "note": "Rationale annotations/predictions are not present in eval.json + matrix_*.csv inputs.",
        "iou_threshold": 0.5,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _fmt(v: float) -> str:
    return "nan" if v != v else f"{v:.4f}"


def print_and_save_report(class_metrics: dict, rationale_metrics: dict) -> None:
    report_txt = BASE_DIR / "result.txt"
    report_json = BASE_DIR / "result_metrics.json"

    lines: list[str] = []
    lines.append("=" * 88)
    lines.append("EVALUATION (Majority vote among 3 human raters vs Rater 4)")
    lines.append("=" * 88)

    ov = class_metrics["overall"]
    lines.append("Overall classification metrics")
    lines.append(f"  n                         : {ov['n']}")
    lines.append(f"  accuracy                  : {_fmt(ov['accuracy'])}")
    lines.append(f"  macro_f1                  : {_fmt(ov['macro_f1'])}")
    lines.append(f"  random_baseline_accuracy  : {_fmt(ov['random_baseline_accuracy'])}")

    lines.append("\nPer-model classification metrics")
    lines.append(f"  {'model':<12}  {'n':>3}  {'accuracy':>10}  {'macro_f1':>10}  {'baseline':>10}")
    lines.append("  " + "-" * 56)
    for model in MODELS:
        m = class_metrics["per_model"][model]
        lines.append(
            f"  {model:<12}  {m['n']:>3}  {_fmt(m['accuracy']):>10}  {_fmt(m['macro_f1']):>10}  {_fmt(m['random_baseline_accuracy']):>10}"
        )

    lines.append("\nPer-dimension classification metrics")
    lines.append(f"  {'dim':<6}  {'n':>3}  {'accuracy':>10}  {'macro_f1':>10}  {'baseline':>10}")
    lines.append("  " + "-" * 50)
    for dim in DIMS:
        d = class_metrics["per_dim"][dim]
        lines.append(
            f"  {dim:<6}  {d['n']:>3}  {_fmt(d['accuracy']):>10}  {_fmt(d['macro_f1']):>10}  {_fmt(d['random_baseline_accuracy']):>10}"
        )

    lines.append("\nRationale extraction metrics")
    lines.append(f"  available   : {rationale_metrics['available']}")
    lines.append(f"  T-f1        : {_fmt(rationale_metrics['t_f1'])}")
    lines.append(f"  IOU-f1      : {_fmt(rationale_metrics['iou_f1'])}")
    lines.append(f"  IOU thresh  : {rationale_metrics['iou_threshold']}")
    lines.append(f"  note        : {rationale_metrics['note']}")

    lines.append("\nLoss function reference")
    lines.append("  L = lambda_EI * L_EI + lambda_RE * L_RE")
    lines.append("  L_EI and L_RE: cross-entropy")
    lines.append("  Best hyperparameters: lambda_EI=1, lambda_RE=0.5")

    text = "\n".join(lines) + "\n"
    report_txt.write_text(text, encoding="utf-8")

    payload = {
        "classification": class_metrics,
        "rationale": rationale_metrics,
        "loss_reference": {
            "formula": "L = lambda_EI * L_EI + lambda_RE * L_RE",
            "L_EI": "cross-entropy",
            "L_RE": "cross-entropy",
            "lambda_EI": 1.0,
            "lambda_RE": 0.5,
        },
    }
    report_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(text)
    print(f"Saved text report: {report_txt.name}")
    print(f"Saved json report: {report_json.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    raw_json = EVAL_JSON_PATH.read_text(encoding="utf-8")
    _per_rater, majority = parse_json_raters(raw_json)
    rater4 = extract_rater4(CSV_FILES)

    class_metrics = compute_classification_metrics(majority, rater4)
    rationale_metrics = compute_rationale_metrics()

    print_and_save_report(class_metrics, rationale_metrics)
