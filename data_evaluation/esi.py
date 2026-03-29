"""
ESI:
5.2.3. ESI and Sensitivity Delta
The Emotional Sensitivity Index (ESI) for a given agent can be deducted from
the EPITOME scoring rubric as presented in Table 5. ESI is defined as follows:

We first have the single-agent pairwise score:
S_ij = ER_ij + IN_ij + EX_ij

ESI is calculated as follows:
ESI_i = (1 / (N - 1)) * sum_{j != i} (ER_ij + IN_ij + EX_ij)

For each scenario:
ESI_scenario = median(ESI_A, ESI_B, ..., ESI_J)

Sensitivity Delta:
Delta_ESI_i = ESI_i(emotional) - ESI_i(neutral)

Interpretation:
- Delta ESI_i > 0: Increased emotional connection
- Delta ESI_i = 0: Stagnant connection
- Delta ESI_i < 0: Behavioral withdrawal

Statistics:
- One-sample t-test on Delta ESI_i values against 0
- Pearson correlation between g_k and ESI_i

This script reads the EPITOME matrices in data_evaluation/, computes ESI per
agent and scenario, computes Delta ESI per provider, and correlates ESI with
the per-agent median g_k extracted from backend/all_data/*/scores/.

Usage:
	python esi.py
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from scipy.stats import pearsonr, ttest_1samp


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
BACKEND_DATA_DIR = ROOT_DIR / "backend" / "all_data"

DIMENSIONS = ("ER", "IN", "EX")
CONDITION_LABELS = {"E": "emotional", "N": "neutral"}
PROVIDERS = ("Claude", "GPT", "Gemini", "Grok")


@dataclass(frozen=True)
class ScenarioResult:
	provider: str
	condition_code: str
	condition_name: str
	agents: tuple[str, ...]
	pairwise_scores: dict[str, dict[str, int]]
	esi_by_agent: dict[str, float]
	valid_partner_counts: dict[str, int]
	scenario_median_esi: float


def parse_score(value: str) -> int | None:
	text = value.strip()
	if not text or text in {"-", "?"}:
		return None
	return int(text)


def parse_matrix_filename(path: Path) -> tuple[str, str]:
	stem = path.stem
	parts = stem.split("_")
	if len(parts) != 3 or parts[0] != "matrix":
		raise ValueError(f"Unexpected matrix file name: {path.name}")
	provider = parts[1]
	condition_code = parts[2]
	if provider not in PROVIDERS:
		raise ValueError(f"Unknown provider in matrix file: {path.name}")
	if condition_code not in CONDITION_LABELS:
		raise ValueError(f"Unknown condition in matrix file: {path.name}")
	return provider, condition_code


def read_matrix(path: Path) -> tuple[tuple[str, ...], dict[str, dict[str, dict[str, int | None]]]]:
	sections: dict[str, dict[str, dict[str, int | None]]] = {}
	current_dimension: str | None = None
	agents: tuple[str, ...] | None = None

	with path.open(newline="", encoding="utf-8-sig") as handle:
		reader = csv.reader(handle)
		for row in reader:
			cleaned = [cell.strip() for cell in row]
			if not any(cleaned):
				continue

			first = cleaned[0]
			if first in DIMENSIONS:
				current_dimension = first
				agents = tuple(cleaned[1:-1])
				sections[current_dimension] = {}
				continue

			if current_dimension is None or agents is None:
				raise ValueError(f"Malformed matrix file: {path}")

			from_agent = first
			values = cleaned[1:-1]
			if len(values) != len(agents):
				raise ValueError(f"Unexpected row width in {path.name} for {from_agent}")

			sections[current_dimension][from_agent] = {
				to_agent: parse_score(raw)
				for to_agent, raw in zip(agents, values)
			}

	missing = [dimension for dimension in DIMENSIONS if dimension not in sections]
	if missing:
		raise ValueError(f"Missing sections {missing} in {path.name}")
	if agents is None:
		raise ValueError(f"No agents found in {path.name}")

	return agents, sections


def compute_esi(path: Path) -> ScenarioResult:
	provider, condition_code = parse_matrix_filename(path)
	agents, sections = read_matrix(path)

	pairwise_scores: dict[str, dict[str, int]] = {agent: {} for agent in agents}
	esi_by_agent: dict[str, float] = {}
	valid_partner_counts: dict[str, int] = {}

	for from_agent in agents:
		totals: list[int] = []
		for to_agent in agents:
			if from_agent == to_agent:
				continue
			values = [sections[dimension][from_agent][to_agent] for dimension in DIMENSIONS]
			if any(value is None for value in values):
				continue
			pairwise = int(sum(value for value in values if value is not None))
			pairwise_scores[from_agent][to_agent] = pairwise
			totals.append(pairwise)

		valid_partner_counts[from_agent] = len(totals)
		if not totals:
			raise ValueError(f"No valid pairwise scores found for {from_agent} in {path.name}")
		esi_by_agent[from_agent] = statistics.mean(totals)

	scenario_median_esi = statistics.median(esi_by_agent.values())
	return ScenarioResult(
		provider=provider,
		condition_code=condition_code,
		condition_name=CONDITION_LABELS[condition_code],
		agents=agents,
		pairwise_scores=pairwise_scores,
		esi_by_agent=esi_by_agent,
		valid_partner_counts=valid_partner_counts,
		scenario_median_esi=scenario_median_esi,
	)


def find_score_files(provider: str, condition_name: str) -> list[Path]:
	scores_dir = BACKEND_DATA_DIR / f"data_{provider}" / "scores"
	if not scores_dir.exists():
		return []
	return sorted(path for path in scores_dir.glob("*.json") if f"_{condition_name}_" in path.stem)


def load_median_gk(provider: str, condition_name: str) -> tuple[dict[str, float], list[str]]:
	gk_values: dict[str, list[float]] = defaultdict(list)
	score_files = find_score_files(provider, condition_name)

	for path in score_files:
		payload = json.loads(path.read_text(encoding="utf-8"))
		for agent_entry in payload.get("agents", []):
			agent = agent_entry.get("agent")
			g_k = agent_entry.get("g_k")
			if agent is None or g_k is None:
				continue
			gk_values[str(agent)].append(float(g_k))

	median_gk = {
		agent: statistics.median(values)
		for agent, values in sorted(gk_values.items())
		if values
	}
	return median_gk, [path.name for path in score_files]


def interpret_delta(delta: float) -> str:
	if math.isclose(delta, 0.0, abs_tol=1e-12):
		return "stagnant connection"
	if delta > 0:
		return "increased emotional connection"
	return "behavioral withdrawal"


def safe_ttest(values: list[float]) -> tuple[float, float]:
	if len(values) < 2:
		return float("nan"), float("nan")
	result = ttest_1samp(values, popmean=0.0)
	return float(result.statistic), float(result.pvalue)


def safe_pearson(x_values: list[float], y_values: list[float]) -> tuple[float, float]:
	if len(x_values) < 2:
		return float("nan"), float("nan")
	if len(set(x_values)) == 1 or len(set(y_values)) == 1:
		return float("nan"), float("nan")
	r_value, p_value = pearsonr(x_values, y_values)
	return float(r_value), float(p_value)


def fmt(value: float, digits: int = 4) -> str:
	if value != value:
		return "nan"
	return f"{value:.{digits}f}"


def build_report() -> str:
	matrix_files = sorted(BASE_DIR.glob("matrix_*.csv"))
	if not matrix_files:
		raise FileNotFoundError("No matrix_*.csv files found in data_evaluation/")

	scenarios = [compute_esi(path) for path in matrix_files]
	scenario_map = {(scenario.provider, scenario.condition_code): scenario for scenario in scenarios}

	lines: list[str] = []
	overall_delta_values: list[float] = []
	pooled_esi_values: list[float] = []
	pooled_gk_values: list[float] = []

	lines.append("=" * 80)
	lines.append("ESI — Scenario Results")
	lines.append("=" * 80)
	for scenario in scenarios:
		median_gk, score_files = load_median_gk(scenario.provider, scenario.condition_name)
		lines.append(f"{scenario.provider}_{scenario.condition_code}")
		lines.append(
			f"  condition={scenario.condition_name}  scenario_median_esi={fmt(scenario.scenario_median_esi)}"
		)
		if score_files:
			lines.append(f"  g_k source runs ({len(score_files)}): {', '.join(score_files)}")
		else:
			lines.append("  g_k source runs (0): none found")
		lines.append("  Agent   ESI_i   valid_partners   median_g_k")
		for agent in scenario.agents:
			g_k = median_gk.get(agent)
			g_k_text = fmt(g_k) if g_k is not None else "n/a"
			lines.append(
				f"  {agent:>5}  {fmt(scenario.esi_by_agent[agent]):>6}"
				f"  {scenario.valid_partner_counts[agent]:>14}  {g_k_text:>10}"
			)
			if g_k is not None:
				pooled_esi_values.append(scenario.esi_by_agent[agent])
				pooled_gk_values.append(g_k)
		correlation_agents = [agent for agent in scenario.agents if agent in median_gk]
		x_values = [median_gk[agent] for agent in correlation_agents]
		y_values = [scenario.esi_by_agent[agent] for agent in correlation_agents]
		r_value, p_value = safe_pearson(x_values, y_values)
		lines.append(
			f"  Pearson(ESI_i, g_k): r={fmt(r_value)}  p={fmt(p_value)}  n={len(correlation_agents)}"
		)
		lines.append("")

	lines.append("=" * 80)
	lines.append("Delta ESI — Emotional vs Neutral")
	lines.append("=" * 80)
	for provider in PROVIDERS:
		emotional = scenario_map.get((provider, "E"))
		neutral = scenario_map.get((provider, "N"))
		if emotional is None or neutral is None:
			continue

		lines.append(provider)
		provider_deltas: list[float] = []
		lines.append("  Agent   ESI_emotional   ESI_neutral   Delta_ESI   Interpretation")
		for agent in emotional.agents:
			if agent not in neutral.esi_by_agent:
				continue
			delta = emotional.esi_by_agent[agent] - neutral.esi_by_agent[agent]
			provider_deltas.append(delta)
			overall_delta_values.append(delta)
			lines.append(
				f"  {agent:>5}  {fmt(emotional.esi_by_agent[agent]):>13}"
				f"  {fmt(neutral.esi_by_agent[agent]):>11}  {fmt(delta):>10}"
				f"  {interpret_delta(delta)}"
			)

		t_stat, p_value = safe_ttest(provider_deltas)
		lines.append(
			f"  One-sample t-test on Delta ESI_i: t={fmt(t_stat)}  p={fmt(p_value)}  n={len(provider_deltas)}"
		)
		lines.append(
			f"  Scenario median ESI: emotional={fmt(emotional.scenario_median_esi)}"
			f"  neutral={fmt(neutral.scenario_median_esi)}"
		)
		lines.append("")

	overall_t, overall_p = safe_ttest(overall_delta_values)
	pooled_r, pooled_r_p = safe_pearson(pooled_gk_values, pooled_esi_values)

	lines.append("=" * 80)
	lines.append("Overall Summary")
	lines.append("=" * 80)
	lines.append(
		f"Pooled one-sample t-test on all Delta ESI_i values: t={fmt(overall_t)}  p={fmt(overall_p)}"
		f"  n={len(overall_delta_values)}"
	)
	lines.append(
		f"Pooled Pearson(ESI_i, g_k) across all scenarios: r={fmt(pooled_r)}  p={fmt(pooled_r_p)}"
		f"  n={len(pooled_esi_values)}"
	)

	lines.append("")
	lines.append("Notes")
	lines.append("- S_ij is computed as ER_ij + IN_ij + EX_ij for each directed agent pair.")
	lines.append("- ESI_i is the mean of available S_ij values across j != i.")
	lines.append("- Missing matrix cells marked '?' are excluded rather than treated as 0.")
	lines.append("- g_k is aggregated as the median per agent across all matching backend score files for the provider-condition.")

	return "\n".join(lines)


def main() -> None:
	print(build_report())


if __name__ == "__main__":
	main()