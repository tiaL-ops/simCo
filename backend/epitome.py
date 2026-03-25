#!/usr/bin/env python3
"""
epitome.py — CLI tool that evaluates EPITOME empathy scores across
multi-agent conversation datasets stored in backend/all_data/.

Usage:
    cd backend && source .venv/bin/activate
    python epitome.py
"""

import csv
import datetime
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

from services.llm import ask_llm, get_llm
from services.storage import load_default_models_by_provider

load_dotenv()

_DEFAULT_MODELS = load_default_models_by_provider()

# ── Colour helpers ──────────────────────────────────────────────────────────
BOLD  = "\033[1m"
DIM   = "\033[2m"
CYAN  = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED   = "\033[91m"
RESET = "\033[0m"


def hdr(t: str) -> None:
    print(f"\n{CYAN}{'─'*62}\n  {BOLD}{t}{RESET}\n{CYAN}{'─'*62}{RESET}")


def ok(t: str) -> None:
    print(f"  {GREEN}✓ {t}{RESET}")


def info(t: str) -> None:
    print(f"  {DIM}{t}{RESET}")


def warn(t: str) -> None:
    print(f"  {YELLOW}⚠ {t}{RESET}")


def err(t: str) -> None:
    print(f"  {RED}✗ {t}{RESET}")


# ── Paths ────────────────────────────────────────────────────────────────────
BACKEND_DIR  = Path(__file__).parent
ALL_DATA_DIR = BACKEND_DIR / "all_data"
RESULTS_DIR  = BACKEND_DIR / "epitome_results"

# Matches: run_<id>_<model>_<timestamp>_<condition>_v<N>
RUN_FOLDER_RE = re.compile(
    r"^run_(?P<run_id>\d+)_(?P<model>.+?)_(?P<timestamp>\d{8}T\d{6}Z)"
    r"_(?P<condition>neutral|emotional)_v(?P<version>\d+)$"
)

# ── EPITOME rubric & judge prompt ────────────────────────────────────────────
# Load the exact rubric text from rubric.txt at module import time
_RUBRIC_PATH = BACKEND_DIR / "rubric.txt"
RUBRIC = _RUBRIC_PATH.read_text(encoding="utf-8")

JUDGE_PROMPT = """\
You are an expert empathy evaluator applying the EPITOME framework.

{rubric}

Below is a conversation between two agents. Evaluate only the messages
sent BY Agent {speaker} (ignore Agent {listener}'s messages entirely).
Score how Agent {speaker} expressed empathy TOWARD Agent {listener}
across the entire conversation.

--- CONVERSATION TRANSCRIPT ---
{transcript}
--- END TRANSCRIPT ---

Return ONLY valid JSON — no markdown fences, no explanation outside the JSON:
{{
  "ER": <0|1|2>,
  "IN": <0|1|2>,
  "EX": <0|1|2>,
  "rationale": "<1-2 sentence justification>"
}}
"""


# ── Discovery ────────────────────────────────────────────────────────────────
def discover_runs(conditions: set[str]) -> list[dict]:
    """Return all matching run-folder metadata dicts under all_data/."""
    runs: list[dict] = []
    if not ALL_DATA_DIR.exists():
        return runs
    for data_dir in sorted(ALL_DATA_DIR.iterdir()):
        if not data_dir.is_dir() or not data_dir.name.startswith("data_"):
            continue
        provider = data_dir.name[len("data_"):]
        conv_dir = data_dir / "conversations"
        if not conv_dir.exists():
            continue
        for folder in sorted(conv_dir.iterdir()):
            if not folder.is_dir():
                continue
            m = RUN_FOLDER_RE.match(folder.name)
            if not m or m.group("condition") not in conditions:
                continue
            if m.group("version") != "1":
                continue
            runs.append(
                {
                    "path": folder,
                    "provider": provider,
                    "run_id": m.group("run_id"),
                    "model": m.group("model"),
                    "timestamp": m.group("timestamp"),
                    "condition": m.group("condition"),
                    "version": m.group("version"),
                    "folder_name": folder.name,
                }
            )
    return runs


# ── Conversation utilities ───────────────────────────────────────────────────
def load_conversation(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_transcript(conv: dict) -> str:
    """Combine pre_game and post_game turns into a readable string."""
    lines: list[str] = []
    for phase in ("pre_game", "post_game"):
        turns = conv.get(phase) or []
        if turns:
            lines.append(f"[{phase.replace('_', ' ').upper()}]")
            for t in turns:
                lines.append(f"  Agent {t['from']}: {t['message']}")
    return "\n".join(lines) or "(empty conversation)"


# ── Scoring ──────────────────────────────────────────────────────────────────
def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"```\s*$", "", text)
    return text.strip()


def parse_scores(response: str) -> Optional[dict]:
    """Parse ER/IN/EX from the LLM JSON response."""
    try:
        data = json.loads(_strip_fences(response))
    except json.JSONDecodeError:
        return None
    scores: dict = {}
    for key in ("ER", "IN", "EX"):
        val = data.get(key)
        try:
            ival = int(val)
        except (TypeError, ValueError):
            return None
        if ival not in (0, 1, 2):
            return None
        scores[key] = ival
    scores["rationale"] = str(data.get("rationale", ""))
    return scores


def score_ordered_pair(
    llm,
    speaker: str,
    listener: str,
    transcript: str,
) -> Optional[dict]:
    """Score ER/IN/EX from speaker's perspective toward listener."""
    prompt = JUDGE_PROMPT.format(
        rubric=RUBRIC,
        speaker=speaker,
        listener=listener,
        transcript=transcript,
    )
    response = ask_llm(llm, prompt)
    scores = parse_scores(response)
    if scores is None:
        warn(f"Could not parse scores for {speaker}→{listener}. "
             f"Raw: {response[:120]!r}")
    return scores


# ── Interactive CLI ──────────────────────────────────────────────────────────
def choose_conditions() -> set[str]:
    hdr("Step 1 — Conditions")
    print("  1. neutral only")
    print("  2. emotional only")
    print("  3. both (default)")
    raw = input("  Select [3]: ").strip() or "3"
    mapping = {
        "1": {"neutral"},
        "2": {"emotional"},
        "3": {"neutral", "emotional"},
    }
    result = mapping.get(raw, {"neutral", "emotional"})
    ok(f"Conditions selected: {', '.join(sorted(result))}")
    return result


def choose_judge() -> tuple[object, str]:
    hdr("Step 2 — LLM Judge")
    claude_model = _DEFAULT_MODELS.get("claude", "claude-haiku-4-5-20251001")
    gemini_model = _DEFAULT_MODELS.get("gemini", "gemini-3-flash-preview")
    print(f"  1. Claude  [{claude_model}]  (default)")
    print(f"  2. Gemini  [{gemini_model}]")
    raw = input("  Select [1]: ").strip() or "1"
    if raw == "2":
        model_name = gemini_model
        llm = get_llm("gemini", model=model_name, temperature=0.0)
    else:
        model_name = claude_model
        llm = get_llm("claude", model=model_name, temperature=0.0)
    ok(f"Judge: {model_name}")
    return llm, model_name


def choose_test_limit() -> Optional[int]:
    hdr("Step 3b — Test / Limit (optional)")
    print("  Enter the max number of pair files to evaluate across all selected")
    print("  runs (useful for a quick smoke-test). Leave blank to evaluate all.")
    raw = input("  Max pairs [all]: ").strip()
    if not raw:
        return None
    if raw.isdigit() and int(raw) > 0:
        limit = int(raw)
        ok(f"Will evaluate at most {limit} pair file(s)")
        return limit
    warn("Invalid input — evaluating all pairs.")
    return None


def choose_runs(all_runs: list[dict]) -> list[dict]:
    hdr("Step 3 — Data Subset")

    # ── provider filter ──────────────────────────────────────────────────────
    providers = sorted({r["provider"] for r in all_runs})
    print("  Available providers:")
    for i, p in enumerate(providers, 1):
        n = sum(1 for r in all_runs if r["provider"] == p)
        print(f"    {i}. {p}  ({n} run(s))")
    print(f"    {len(providers) + 1}. All providers  (default)")

    raw = input(f"  Select provider [{len(providers) + 1}]: ").strip() or str(len(providers) + 1)
    if raw.isdigit() and 1 <= int(raw) <= len(providers):
        pool = [r for r in all_runs if r["provider"] == providers[int(raw) - 1]]
    else:
        pool = list(all_runs)

    # ── individual run filter ────────────────────────────────────────────────
    print(f"\n  Matching runs ({len(pool)} total):")
    for i, r in enumerate(pool, 1):
        n_pairs = len(list(r["path"].glob("*.json")))
        print(
            f"    {i:3d}. [{r['condition']:8s}] v{r['version']}  "
            f"{r['folder_name']}  ({n_pairs} pairs)"
        )
    print(f"    {len(pool) + 1:3d}. All of the above  (default)")

    raw2 = input(f"  Select run [{len(pool) + 1}]: ").strip() or str(len(pool) + 1)
    if raw2.isdigit() and 1 <= int(raw2) <= len(pool):
        selected = [pool[int(raw2) - 1]]
    else:
        selected = pool

    ok(f"{len(selected)} run(s) selected")
    return selected


def confirm_plan(runs: list[dict], judge: str, limit: Optional[int]) -> bool:
    hdr("Evaluation Plan — Review & Confirm")
    total_pairs = sum(len(list(r["path"].glob("*.json"))) for r in runs)
    conditions = sorted({r["condition"] for r in runs})
    providers  = sorted({r["provider"]  for r in runs})

    effective = min(total_pairs, limit) if limit else total_pairs
    print(f"  Providers     : {', '.join(providers)}")
    print(f"  Conditions    : {', '.join(conditions)}")
    print(f"  Runs          : {len(runs)}")
    print(f"  Pair files    : {total_pairs}{f'  (capped at {limit})' if limit else ''}")
    print(f"  LLM API calls : {effective * 2}  (2 per pair file)")
    print(f"  Judge         : {judge}")
    print(f"  Output dir    : {RESULTS_DIR.relative_to(BACKEND_DIR)}/")
    ans = input("\n  Proceed? [Y/n]: ").strip().lower()
    return ans in ("", "y", "yes")


# ── Evaluation loop ──────────────────────────────────────────────────────────
def evaluate_runs(
    runs: list[dict],
    llm,
    judge_name: str,
    limit: Optional[int] = None,
    on_run_complete=None,
) -> list[dict]:
    results: list[dict] = []
    RESULTS_DIR.mkdir(exist_ok=True)
    remaining = limit  # None means unlimited

    total = len(runs)
    for idx, run in enumerate(runs, 1):
        if remaining is not None and remaining <= 0:
            break
        hdr(f"Run {idx}/{total}: {run['folder_name']}")
        pair_files = sorted(run["path"].glob("*.json"))
        if remaining is not None:
            pair_files = pair_files[:remaining]

        for pf in pair_files:
            conv = load_conversation(pf)
            pair = conv.get("pair", [])
            if len(pair) != 2:
                warn(f"Skipping {pf.name}: malformed 'pair' field {pair!r}")
                continue

            transcript = build_transcript(conv)
            agent_a, agent_b = pair[0], pair[1]

            for speaker, listener in [(agent_a, agent_b), (agent_b, agent_a)]:
                info(f"  scoring {speaker}→{listener}  ({pf.name}) …")
                scores = score_ordered_pair(llm, speaker, listener, transcript)
                if scores is None:
                    scores = {"ER": None, "IN": None, "EX": None,
                              "rationale": "PARSE_ERROR"}

                results.append(
                    {
                        "run_id":      run["run_id"],
                        "provider":    run["provider"],
                        "model":       run["model"],
                        "timestamp":   run["timestamp"],
                        "condition":   run["condition"],
                        "version":     run["version"],
                        "folder_name": run["folder_name"],
                        "pair_file":   pf.name,
                        "speaker":     speaker,
                        "listener":    listener,
                        "ER":          scores["ER"],
                        "IN":          scores["IN"],
                        "EX":          scores["EX"],
                        "rationale":   scores.get("rationale", ""),
                        "judge":       judge_name,
                        "evaluated_at": (
                            datetime.datetime.utcnow().isoformat() + "Z"
                        ),
                    }
                )

        ok(f"Done — {len(pair_files)} pair file(s) processed")
        if on_run_complete is not None:
            on_run_complete(results, run)
        if remaining is not None:
            remaining -= len(pair_files)

    return results


# ── Output ───────────────────────────────────────────────────────────────────
def _build_matrix(results: list[dict], dim: str) -> tuple[list[str], dict[tuple[str, str], str]]:
    """Return (agents, averaged_scores) for one dimension."""
    valid = [r for r in results if r[dim] is not None]
    agents = sorted({r["speaker"] for r in valid} | {r["listener"] for r in valid})
    raw: dict[tuple[str, str], list] = {}
    for r in valid:
        raw.setdefault((r["speaker"], r["listener"]), []).append(r[dim])
    averaged = {k: str(round(sum(v) / len(v))) for k, v in raw.items()}
    return agents, averaged


def save_results(
    results: list[dict],
    judge_name: str,
    *,
    ts: Optional[str] = None,
    announce: bool = True,
) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    if ts is None:
        ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", judge_name)

    json_path = RESULTS_DIR / f"epitome_{safe_name}_{ts}.json"
    csv_path  = RESULTS_DIR / f"epitome_{safe_name}_{ts}.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    if results:
        fields = list(results[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(results)

    if announce:
        ok(f"JSON → {json_path.relative_to(BACKEND_DIR)}")
        ok(f"CSV  → {csv_path.relative_to(BACKEND_DIR)}")

    # ── Per-run matrix CSVs (one file per run, one sheet-like block per dim) ─
    runs_seen: dict[str, list[dict]] = {}
    for r in results:
        runs_seen.setdefault(r["folder_name"], []).append(r)

    matrix_paths: list[Path] = []
    for folder_name, run_results in sorted(runs_seen.items()):
        valid = [r for r in run_results if r["ER"] is not None]
        if not valid:
            continue
        safe_folder = re.sub(r"[^a-zA-Z0-9_-]", "_", folder_name)
        mpath = RESULTS_DIR / f"matrix_{safe_folder}_{safe_name}_{ts}.csv"
        with open(mpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for dim in ("ER", "IN", "EX"):
                agents, averaged = _build_matrix(valid, dim)
                # header rows
                writer.writerow([dim] + agents + ["Score"])
                for sender in agents:
                    row_sum = sum(
                        int(averaged[(sender, rec)])
                        for rec in agents
                        if rec != sender and averaged.get((sender, rec), "?").lstrip("-").isdigit()
                    )
                    row = [sender]
                    for receiver in agents:
                        if sender == receiver:
                            row.append("-")
                        else:
                            row.append(averaged.get((sender, receiver), "?"))
                    row.append(row_sum)
                    writer.writerow(row)
                writer.writerow([])  # blank separator between dimensions
        matrix_paths.append(mpath)

    if announce:
        for mp in matrix_paths:
            ok(f"Matrix CSV → {mp.relative_to(BACKEND_DIR)}")


def print_matrix(results: list[dict], dim: str, label: str) -> None:
    """Print a sender×receiver score matrix for one EPITOME dimension."""
    valid = [r for r in results if r[dim] is not None]
    if not valid:
        return

    agents, averaged = _build_matrix(valid, dim)

    col_w = 3
    header_pad = 2
    indent = "  "

    header = indent + f"{'':>{header_pad}}" + "".join(f"{a:>{col_w}}" for a in agents) + f"{'Score':>{col_w+2}}"
    print(f"\n{BOLD}  {label}{RESET}")
    print(header)
    print(indent + "─" * (header_pad + col_w * len(agents) + col_w + 2))

    for sender in agents:
        row_sum = sum(
            int(averaged[(sender, rec)])
            for rec in agents
            if rec != sender and averaged.get((sender, rec), "?").lstrip("-").isdigit()
        )
        cells = ""
        for receiver in agents:
            if sender == receiver:
                cells += f"{'─':>{col_w}}"
            else:
                val = averaged.get((sender, receiver), "?")
                cells += f"{val:>{col_w}}"
        print(f"{indent}{sender:>{header_pad}}{cells}{row_sum:>{col_w+2}}")

    print()


def print_matrices(results: list[dict], group_label: str = "") -> None:
    """Print ER, IN, EX matrices for a set of results, grouped by run when multiple."""
    if group_label:
        hdr(f"Score Matrices — {group_label}")
    else:
        hdr("Score Matrices")

    # Group by run folder so each run gets its own matrix set
    runs_seen: dict[str, list[dict]] = {}
    for r in results:
        runs_seen.setdefault(r["folder_name"], []).append(r)

    for folder_name, run_results in sorted(runs_seen.items()):
        cond = run_results[0]["condition"]
        provider = run_results[0]["provider"]
        valid = [r for r in run_results if r["ER"] is not None]
        if not valid:
            continue
        print(f"\n{CYAN}  ▸ {folder_name}  [{provider} | {cond}]{RESET}")
        print_matrix(valid, "ER", "Emotional Reactions (ER)  — row = expressed, col = received")
        print_matrix(valid, "IN", "Interpretations      (IN)  — row = expressed, col = received")
        print_matrix(valid, "EX", "Explorations         (EX)  — row = expressed, col = received")


def print_summary(results: list[dict]) -> None:
    hdr("Summary")
    ok(f"Total ordered pairs scored: {len(results)}")
    valid = [r for r in results if r["ER"] is not None]
    if not valid:
        warn("No valid scores — check for parse errors above.")
        return
    avg_er = sum(r["ER"] for r in valid) / len(valid)
    avg_in = sum(r["IN"] for r in valid) / len(valid)
    avg_ex = sum(r["EX"] for r in valid) / len(valid)
    print(f"  Valid scores  : {len(valid)} / {len(results)}")
    print(f"  Mean ER       : {avg_er:.3f}")
    print(f"  Mean IN       : {avg_in:.3f}")
    print(f"  Mean EX       : {avg_ex:.3f}")

    # Per-condition breakdown (if mixed)
    conditions = sorted({r["condition"] for r in valid})
    if len(conditions) > 1:
        print()
        for cond in conditions:
            subset = [r for r in valid if r["condition"] == cond]
            print(
                f"  [{cond:8s}]  ER={sum(r['ER'] for r in subset)/len(subset):.3f}"
                f"  IN={sum(r['IN'] for r in subset)/len(subset):.3f}"
                f"  EX={sum(r['EX'] for r in subset)/len(subset):.3f}"
                f"  (n={len(subset)})"
            )

    print_matrices(valid)


# ── Entry point ──────────────────────────────────────────────────────────────
def main() -> None:
    print(f"\n{BOLD}{CYAN}══ EPITOME Empathy Evaluator ══{RESET}")
    print(f"{DIM}Scores ER / IN / EX across multi-agent SimCo conversations{RESET}")

    conditions  = choose_conditions()
    llm, judge  = choose_judge()

    all_runs = discover_runs(conditions)
    if not all_runs:
        err("No matching run folders found. Check all_data/ and your condition selection.")
        sys.exit(1)

    selected = choose_runs(all_runs)
    if not selected:
        err("No runs selected.")
        sys.exit(1)

    limit = choose_test_limit()

    if not confirm_plan(selected, judge, limit):
        info("Aborted by user.")
        sys.exit(0)

    session_ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    def _checkpoint_save(partial_results: list[dict], _run: dict) -> None:
        save_results(partial_results, judge, ts=session_ts, announce=False)
        ok(f"Checkpoint saved ({len(partial_results)} ordered pairs)")

    results = evaluate_runs(
        selected,
        llm,
        judge,
        limit=limit,
        on_run_complete=_checkpoint_save,
    )

    hdr("Saving Results")
    save_results(results, judge, ts=session_ts)
    print_summary(results)


if __name__ == "__main__":
    main()