"""CLI for LLM-based empathy scoring and Cohen's kappa reporting.

The tool can:
1. Evaluate one CSV or the three standard dataset CSVs with an LLM judge.
2. Save each judged row immediately so interrupted runs can resume.
3. Compare human labels to LLM labels with Cohen's kappa.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
	import pandas as pd
except ImportError as exc:
	raise SystemExit(
		"Missing dependency: pandas. Install the project requirements first, for example with "
		"'pip install -r backend/requirements.txt'."
	) from exc

try:
	from sklearn.metrics import cohen_kappa_score
except ImportError as exc:
	raise SystemExit(
		"Missing dependency: scikit-learn. Install the project requirements first, for example with "
		"'pip install -r backend/requirements.txt'."
	) from exc


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
	sys.path.insert(0, str(ROOT_DIR))

from backend.services.llm import ask_llm, get_llm


DATASET_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
RESULTS_DIR = DATASET_DIR / "data_LLM_evalauted"
DEFAULT_MODELS_PATH = BACKEND_DIR / "config" / "default_models_by_provider.json"
RUBRIC_POINTER_PATH = DATASET_DIR / "rub.txt"
STANDARD_DATASETS = {
	"emotional": DATASET_DIR / "emotional-reactions-reddit.csv",
	"exploration": DATASET_DIR / "explorations-reddit.csv",
	"interpretation": DATASET_DIR / "interpretations-reddit.csv",
}
PROMPT_TEMPLATE = """Evaluate the level of empathy expressed in the response_post given the seeker_post.
Rate each response on three dimensions: You should rate on a scale from 0 (worst) to 2 (best) according to this rubric.

{rubric}

seeker_post: {seeker_post}
response_post: {response_post}

Return ONLY valid JSON with this exact schema:
{{
  "emotional": <0|1|2>,
  "exploration": <0|1|2>,
  "interpretation": <0|1|2>,
  "rationale": "<short explanation>"
}}"""
MODEL_NAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def load_default_models() -> dict[str, str]:
	if not DEFAULT_MODELS_PATH.exists():
		return {
			"openai": "gpt-5-mini",
			"claude": "claude-haiku-4-5-20251001",
			"gemini": "gemini-3-flash-preview",
			"grok": "grok-3-mini-fast-beta",
		}
	with open(DEFAULT_MODELS_PATH, encoding="utf-8") as handle:
		data = json.load(handle)
	return {str(key): str(value) for key, value in data.items()}


DEFAULT_MODELS = load_default_models()


def resolve_rubric_text() -> str:
	if not RUBRIC_POINTER_PATH.exists():
		rubric_path = BACKEND_DIR / "rubric.txt"
		return rubric_path.read_text(encoding="utf-8")

	pointer = RUBRIC_POINTER_PATH.read_text(encoding="utf-8").strip()
	if not pointer:
		raise ValueError(f"Rubric pointer file is empty: {RUBRIC_POINTER_PATH}")

	candidate = Path(pointer)
	if not candidate.is_absolute():
		candidate = (ROOT_DIR / candidate).resolve()
	if not candidate.exists():
		raise FileNotFoundError(f"Rubric file not found: {candidate}")
	return candidate.read_text(encoding="utf-8")


RUBRIC_TEXT = resolve_rubric_text()


def utc_now() -> str:
	return datetime.now(timezone.utc).isoformat()


def sanitize_model_name(model: str) -> str:
	return MODEL_NAME_SAFE_RE.sub("_", model).strip("_") or "model"


def infer_dimension(dataset_path: Path) -> str | None:
	name = dataset_path.name.lower()
	if "emotion" in name:
		return "emotional"
	if "exploration" in name:
		return "exploration"
	if "interpretation" in name:
		return "interpretation"
	return None


def default_provider_output_dir(provider: str) -> Path:
	base = RESULTS_DIR / provider
	if base.exists() and base.is_file():
		# Keep old user files intact and avoid path collisions.
		return RESULTS_DIR / f"{provider}_results"
	return base


def build_output_path(dataset_path: Path, provider: str, model: str, output: Path | None) -> Path:
	filename = f"data_{provider}_{sanitize_model_name(model)}_judge_{dataset_path.stem}.csv"
	if output is None:
		return default_provider_output_dir(provider) / filename
	if output.suffix.lower() == ".csv":
		return output
	if output.exists() and output.is_file():
		raise ValueError(
			f"Output path '{output}' is a file. Use a .csv path for single-file output or a directory path for per-dataset files."
		)
	return output / filename


def strip_fences(text: str) -> str:
	text = text.strip()
	text = re.sub(r"^```[A-Za-z]*\s*", "", text)
	text = re.sub(r"```\s*$", "", text)
	return text.strip()


def parse_judge_response(response: str) -> dict[str, Any] | None:
	cleaned = strip_fences(response)
	candidates = [cleaned]
	match = JSON_BLOCK_RE.search(cleaned)
	if match:
		candidates.insert(0, match.group(0))

	for candidate in candidates:
		try:
			data = json.loads(candidate)
		except json.JSONDecodeError:
			continue

		parsed: dict[str, Any] = {}
		for key in ("emotional", "exploration", "interpretation"):
			value = data.get(key)
			try:
				value = int(value)
			except (TypeError, ValueError):
				break
			if value not in (0, 1, 2):
				break
			parsed[key] = value
		else:
			parsed["rationale"] = str(data.get("rationale", "")).strip()
			return parsed

	return None


def make_row_key(row: pd.Series, row_index: int) -> str:
	key_parts: list[str] = []
	for column in ("id", "sp_id", "rp_id"):
		if column in row.index and pd.notna(row[column]):
			key_parts.append(f"{column}={row[column]}")
	return "|".join(key_parts) if key_parts else f"row_index={row_index}"


def load_existing_results(output_path: Path) -> set[str]:
	if not output_path.exists():
		return set()

	results = pd.read_csv(output_path)
	if "row_key" not in results.columns:
		return set()

	completed = results[
		results[["llm_emotional", "llm_exploration", "llm_interpretation"]].notna().all(axis=1)
	]
	return {str(value) for value in completed["row_key"].tolist()}


def validate_dataset_columns(dataframe: pd.DataFrame, dataset_path: Path) -> None:
	required = {"seeker_post", "response_post"}
	missing = sorted(required.difference(dataframe.columns))
	if missing:
		raise ValueError(f"Dataset {dataset_path} is missing columns: {', '.join(missing)}")


def ensure_parent_dir(path: Path) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)


def build_prompt(seeker_post: str, response_post: str) -> str:
	return PROMPT_TEMPLATE.format(
		rubric=RUBRIC_TEXT,
		seeker_post=seeker_post,
		response_post=response_post,
	)


def evaluate_row(llm: object, seeker_post: str, response_post: str, retries: int = 3) -> tuple[dict[str, Any] | None, str]:
	prompt = build_prompt(seeker_post, response_post)
	last_response = ""
	for attempt in range(retries):
		if attempt == 0:
			request = prompt
		else:
			request = (
				f"{prompt}\n\n"
				"Your previous answer was not valid JSON for the required schema. "
				"Return only valid JSON with integer values 0, 1, or 2."
			)
		last_response = ask_llm(llm, request)
		parsed = parse_judge_response(last_response)
		if parsed is not None:
			return parsed, last_response
	return None, last_response


def output_headers(dataframe: pd.DataFrame) -> list[str]:
	preferred = [column for column in ("id", "sp_id", "rp_id") if column in dataframe.columns]
	optional = [column for column in ("level", "rationales") if column in dataframe.columns]
	return [
		"row_key",
		"source_dataset",
		"source_row_index",
		*preferred,
		"target_dimension",
		"seeker_post",
		"response_post",
		*optional,
		"llm_emotional",
		"llm_exploration",
		"llm_interpretation",
		"llm_rationale",
		"judge_provider",
		"judge_model",
		"judged_at",
		"raw_response",
		"error",
	]


def append_result_row(output_path: Path, headers: list[str], row: dict[str, Any], jsonl_path: Path | None = None) -> None:
	ensure_parent_dir(output_path)
	file_exists = output_path.exists()
	with open(output_path, "a", encoding="utf-8", newline="") as handle:
		writer = csv.DictWriter(handle, fieldnames=headers)
		if not file_exists:
			writer.writeheader()
		writer.writerow(row)
		handle.flush()

	if jsonl_path is not None:
		ensure_parent_dir(jsonl_path)
		with open(jsonl_path, "a", encoding="utf-8") as handle:
			handle.write(json.dumps(row, ensure_ascii=True) + "\n")
			handle.flush()


def evaluate_dataset_file(
	dataset_path: Path,
	output_path: Path,
	provider: str,
	model: str,
	overwrite: bool = False,
	limit: int | None = None,
	sample_size: int | None = None,
	sample_seed: int = 42,
	export_json: bool = True,
) -> dict[str, Any]:
	dataset = pd.read_csv(dataset_path)
	validate_dataset_columns(dataset, dataset_path)
	original_rows = len(dataset)

	if sample_size is not None:
		if sample_size <= 0:
			raise ValueError("sample_size must be greater than 0.")
		if sample_size < len(dataset):
			dataset = dataset.sample(n=sample_size, random_state=sample_seed).sort_index()

	if overwrite and output_path.exists():
		output_path.unlink()
	jsonl_path = output_path.with_suffix(".jsonl") if export_json else None
	if overwrite and jsonl_path is not None and jsonl_path.exists():
		jsonl_path.unlink()

	completed_keys = load_existing_results(output_path)
	llm = get_llm(provider=provider, model=model, temperature=0.0)
	headers = output_headers(dataset)
	dimension = infer_dimension(dataset_path)
	processed = 0
	skipped = 0
	errors = 0

	for row_index, row in dataset.iterrows():
		row_key = make_row_key(row, row_index)
		if row_key in completed_keys:
			skipped += 1
			continue
		if limit is not None and processed >= limit:
			break

		scores, raw_response = evaluate_row(
			llm,
			seeker_post=str(row["seeker_post"]),
			response_post=str(row["response_post"]),
		)

		result_row: dict[str, Any] = {
			"row_key": row_key,
			"source_dataset": str(dataset_path),
			"source_row_index": row_index,
			"target_dimension": dimension or "",
			"seeker_post": row["seeker_post"],
			"response_post": row["response_post"],
			"llm_emotional": "",
			"llm_exploration": "",
			"llm_interpretation": "",
			"llm_rationale": "",
			"judge_provider": provider,
			"judge_model": model,
			"judged_at": utc_now(),
			"raw_response": raw_response,
			"error": "",
		}

		for column in ("id", "sp_id", "rp_id", "level", "rationales"):
			if column in row.index:
				result_row[column] = row[column]

		if scores is None:
			errors += 1
			result_row["error"] = "Could not parse judge response"
		else:
			result_row["llm_emotional"] = scores["emotional"]
			result_row["llm_exploration"] = scores["exploration"]
			result_row["llm_interpretation"] = scores["interpretation"]
			result_row["llm_rationale"] = scores["rationale"]

		append_result_row(output_path, headers, result_row, jsonl_path=jsonl_path)
		processed += 1

	return {
		"dataset": dataset_path,
		"output": output_path,
		"json_output": jsonl_path,
		"selected_rows": len(dataset),
		"original_rows": original_rows,
		"processed": processed,
		"skipped": skipped,
		"errors": errors,
	}


def collect_dataset_files(dataset_path: Path) -> list[Path]:
	if dataset_path.is_file():
		return [dataset_path]

	found: list[Path] = []
	for candidate in STANDARD_DATASETS.values():
		resolved = dataset_path / candidate.name
		if resolved.exists():
			found.append(resolved)
	if found:
		return found

	csv_files = sorted(dataset_path.glob("*.csv"))
	if not csv_files:
		raise FileNotFoundError(f"No CSV files found in {dataset_path}")
	return csv_files


def human_level_column(dataframe: pd.DataFrame) -> str:
	if "level" in dataframe.columns:
		return "level"
	raise ValueError("The dataset does not contain a 'level' column for human labels.")


def prediction_column_for_dimension(dimension: str) -> str:
	mapping = {
		"emotional": "llm_emotional",
		"exploration": "llm_exploration",
		"interpretation": "llm_interpretation",
	}
	if dimension not in mapping:
		raise ValueError(
			"Could not infer which LLM score to compare. "
			"Use one of the standard dataset files or pass --dimension."
		)
	return mapping[dimension]


def compute_kappa_for_file(
	dataset_path: Path,
	evaluation_path: Path,
	forced_dimension: str | None = None,
) -> dict[str, Any]:
	dataset = pd.read_csv(dataset_path)
	evaluation = pd.read_csv(evaluation_path)
	validate_dataset_columns(dataset, dataset_path)

	if "row_key" not in evaluation.columns:
		raise ValueError(f"Evaluation file is missing row_key: {evaluation_path}")

	dataset = dataset.copy()
	dataset["row_key"] = [make_row_key(row, idx) for idx, row in dataset.iterrows()]

	dimension = forced_dimension or infer_dimension(dataset_path)
	prediction_column = prediction_column_for_dimension(dimension or "")
	human_column = human_level_column(dataset)

	merged = dataset[["row_key", human_column]].merge(
		evaluation[["row_key", prediction_column]],
		on="row_key",
		how="inner",
	)
	merged = merged.dropna(subset=[human_column, prediction_column])
	if merged.empty:
		raise ValueError(
			f"No overlapping labeled rows between {dataset_path} and {evaluation_path}."
		)

	human_scores = merged[human_column].astype(int)
	llm_scores = merged[prediction_column].astype(int)
	with warnings.catch_warnings():
		warnings.simplefilter("ignore", category=RuntimeWarning)
		kappa = cohen_kappa_score(human_scores, llm_scores, labels=[0, 1, 2])

	kappa_note = ""
	if not math.isfinite(float(kappa)):
		h_unique = int(human_scores.nunique())
		l_unique = int(llm_scores.nunique())
		kappa = float("nan")
		kappa_note = (
			"undefined (too few label classes in sample: "
			f"human_unique={h_unique}, llm_unique={l_unique})"
		)

	return {
		"dataset": dataset_path,
		"evaluation": evaluation_path,
		"dimension": dimension,
		"rows_compared": int(len(merged)),
		"kappa": float(kappa),
		"kappa_note": kappa_note,
		"human_mean": float(human_scores.mean()),
		"llm_mean": float(llm_scores.mean()),
	}


def print_evaluation_summary(results: list[dict[str, Any]]) -> None:
	print("\nEvaluation complete:")
	for result in results:
		json_text = f" json={result['json_output']} |" if result.get("json_output") else ""
		print(
			f"- {result['dataset']} -> {result['output']} | "
			f"{json_text} "
			f"selected={result['selected_rows']}/{result['original_rows']} | "
			f"processed={result['processed']} skipped={result['skipped']} errors={result['errors']}"
		)


def print_kappa_summary(results: list[dict[str, Any]]) -> None:
	print("\nInter-rater reliability (Cohen's kappa):")
	for result in results:
		kappa_value = result["kappa"]
		kappa_text = f"{kappa_value:.4f}" if math.isfinite(kappa_value) else "undefined"
		note = f" | note={result['kappa_note']}" if result.get("kappa_note") else ""
		print(
			f"- {result['dataset']} | dimension={result['dimension']} | "
			f"rows={result['rows_compared']} | kappa={kappa_text} | "
			f"human_mean={result['human_mean']:.3f} | llm_mean={result['llm_mean']:.3f}{note}"
		)


def prompt_choice(prompt: str, options: dict[str, str], default: str) -> str:
	print(prompt)
	for key, label in options.items():
		default_marker = " (default)" if key == default else ""
		print(f"  {key}. {label}{default_marker}")
	selection = input(f"Select [{default}]: ").strip() or default
	return selection if selection in options else default


def prompt_path(message: str, default: Path) -> Path:
	raw = input(f"{message} [{default}]: ").strip()
	return Path(raw).expanduser() if raw else default


def prompt_provider_and_model() -> tuple[str, str]:
	provider_options = {
		"1": "openai",
		"2": "claude",
		"3": "gemini",
		"4": "grok",
	}
	choice = prompt_choice(
		"Which model provider do you want to use?",
		{key: f"{value} [{DEFAULT_MODELS.get(value, 'default')}]" for key, value in provider_options.items()},
		default="1",
	)
	provider = provider_options[choice]
	default_model = DEFAULT_MODELS.get(provider, "")
	raw_model = input(f"Model name [{default_model}]: ").strip()
	return provider, raw_model or default_model


def interactive_cli() -> None:
	action = prompt_choice(
		"What do you want to do?",
		{
			"1": "Evaluate responses",
			"2": "Calculate inter-rater reliability",
			"3": "Evaluate responses, then calculate reliability",
			"q": "Quit",
		},
		default="1",
	)
	if action == "q":
		return

	dataset_path = prompt_path("Dataset file or directory", DATASET_DIR)

	if action in {"1", "3"}:
		provider, model = prompt_provider_and_model()
		default_output = default_provider_output_dir(provider)
		output_path = prompt_path("Output file or directory", default_output)
		raw_sample_size = input("Optional sample size (for example 10 or 20, leave blank for full dataset): ").strip()
		sample_size = int(raw_sample_size) if raw_sample_size else None
		raw_sample_seed = input("Sample seed [42]: ").strip() if sample_size is not None else ""
		sample_seed = int(raw_sample_seed) if raw_sample_seed else 42
		evaluation_results = run_evaluation(
			dataset_path=dataset_path,
			output_path=output_path,
			provider=provider,
			model=model,
			overwrite=False,
			limit=None,
			sample_size=sample_size,
			sample_seed=sample_seed,
			export_json=True,
		)
		print_evaluation_summary(evaluation_results)
	else:
		output_path = prompt_path("Evaluation file or directory", RESULTS_DIR)

	if action in {"2", "3"}:
		kappa_results = run_kappa(
			dataset_path=dataset_path,
			output_path=output_path,
			dimension=None,
		)
		print_kappa_summary(kappa_results)


def run_evaluation(
	dataset_path: Path,
	output_path: Path | None,
	provider: str,
	model: str,
	overwrite: bool,
	limit: int | None,
	sample_size: int | None,
	sample_seed: int,
	export_json: bool,
) -> list[dict[str, Any]]:
	dataset_files = collect_dataset_files(dataset_path)
	results: list[dict[str, Any]] = []
	for file_path in dataset_files:
		file_output = build_output_path(file_path, provider, model, output_path)
		results.append(
			evaluate_dataset_file(
				dataset_path=file_path,
				output_path=file_output,
				provider=provider,
				model=model,
				overwrite=overwrite,
				limit=limit,
				sample_size=sample_size,
				sample_seed=sample_seed,
				export_json=export_json,
			)
		)
	return results


def resolve_kappa_pairs(dataset_path: Path, output_path: Path, provider: str | None = None, model: str | None = None) -> list[tuple[Path, Path]]:
	dataset_files = collect_dataset_files(dataset_path)
	pairs: list[tuple[Path, Path]] = []
	for file_path in dataset_files:
		if output_path.is_dir():
			if provider is not None and model is not None:
				evaluation_path = build_output_path(file_path, provider, model, output_path)
			else:
				matches = sorted(output_path.rglob(f"*_judge_{file_path.stem}.csv"))
				if not matches:
					# Backward compatibility: allow a flat provider file like
					# dataset/data_LLM_evalauted/gpt when that is the only file.
					flat_files = [item for item in output_path.iterdir() if item.is_file()]
					if len(flat_files) == 1:
						evaluation_path = flat_files[0]
					else:
						raise FileNotFoundError(
							f"Could not find an evaluation file for {file_path.name} in {output_path}"
						)
				else:
					evaluation_path = max(matches, key=lambda p: p.stat().st_mtime)
		else:
			evaluation_path = output_path
		pairs.append((file_path, evaluation_path))
	return pairs


def run_kappa(dataset_path: Path, output_path: Path, dimension: str | None) -> list[dict[str, Any]]:
	results: list[dict[str, Any]] = []
	for dataset_file, evaluation_file in resolve_kappa_pairs(dataset_path, output_path):
		results.append(
			compute_kappa_for_file(
				dataset_path=dataset_file,
				evaluation_path=evaluation_file,
				forced_dimension=dimension,
			)
		)
	return results


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description=__doc__)
	subparsers = parser.add_subparsers(dest="command")

	evaluate_parser = subparsers.add_parser("evaluate", help="Judge responses with an LLM")
	evaluate_parser.add_argument(
		"--dataset",
		type=Path,
		default=DATASET_DIR,
		help="Dataset CSV file or directory containing CSV files.",
	)
	evaluate_parser.add_argument(
		"--output",
		type=Path,
		default=None,
		help="Output CSV file for one dataset, or output directory for multiple datasets.",
	)
	evaluate_parser.add_argument(
		"--provider",
		choices=sorted(DEFAULT_MODELS),
		default="openai",
		help="LLM provider.",
	)
	evaluate_parser.add_argument(
		"--model",
		default=None,
		help="Model name. Defaults to backend/config/default_models_by_provider.json.",
	)
	evaluate_parser.add_argument(
		"--overwrite",
		action="store_true",
		help="Overwrite an existing output file instead of resuming.",
	)
	evaluate_parser.add_argument(
		"--limit",
		type=int,
		default=None,
		help="Maximum number of new rows to evaluate.",
	)
	evaluate_parser.add_argument(
		"--sample-size",
		type=int,
		default=None,
		help="Evaluate a reproducible sample of N rows instead of the full dataset.",
	)
	evaluate_parser.add_argument(
		"--sample-seed",
		type=int,
		default=42,
		help="Random seed used when --sample-size is set.",
	)
	evaluate_parser.add_argument(
		"--no-json",
		action="store_true",
		help="Disable JSONL export (CSV is always written).",
	)

	kappa_parser = subparsers.add_parser("kappa", help="Compute Cohen's kappa")
	kappa_parser.add_argument(
		"--dataset",
		type=Path,
		default=DATASET_DIR,
		help="Dataset CSV file or directory containing CSV files.",
	)
	kappa_parser.add_argument(
		"--output",
		type=Path,
		default=RESULTS_DIR,
		help="Evaluation CSV file or directory containing evaluation files.",
	)
	kappa_parser.add_argument(
		"--dimension",
		choices=["emotional", "exploration", "interpretation"],
		default=None,
		help="Force the dimension used for kappa instead of inferring it from the dataset name.",
	)

	return parser


def main() -> None:
	parser = build_parser()
	args = parser.parse_args()

	if args.command is None:
		interactive_cli()
		return

	if args.command == "evaluate":
		model = args.model or DEFAULT_MODELS.get(args.provider, "gpt-5-mini")
		results = run_evaluation(
			dataset_path=args.dataset,
			output_path=args.output,
			provider=args.provider,
			model=model,
			overwrite=args.overwrite,
			limit=args.limit,
			sample_size=args.sample_size,
			sample_seed=args.sample_seed,
			export_json=not args.no_json,
		)
		print_evaluation_summary(results)
		return

	if args.command == "kappa":
		results = run_kappa(
			dataset_path=args.dataset,
			output_path=args.output,
			dimension=args.dimension,
		)
		print_kappa_summary(results)
		return

	parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
	main()
