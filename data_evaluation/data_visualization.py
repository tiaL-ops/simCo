"""Visualize connection scores from backend/all_data memory files.

Outputs saved in data_evaluation/:
1) connection_heatmap_all_models.png
   - Heatmap (2x2 panels) of mean directed connection scores per provider.
2) connection_network_all_models.png
   - One additional visualization style (directed network map, 2x2 panels).
3) visulation.txt
   - Text interpretation and summary statistics.

Usage:
	python data_visualization.py
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT_DIR = Path(__file__).resolve().parents[1]
BASE_DIR = Path(__file__).resolve().parent
ALL_DATA_DIR = ROOT_DIR / "backend" / "all_data"

PROVIDERS = ("Claude", "GPT", "Gemini", "Grok")
CONDITIONS = ("neutral", "emotional")
AGENTS = tuple(chr(c) for c in range(ord("A"), ord("J") + 1))
AGENT_TO_INDEX = {agent: i for i, agent in enumerate(AGENTS)}


@dataclass
class ProviderData:
	provider: str
	matrix_all: np.ndarray
	count_all: np.ndarray
	matrix_by_condition: dict[str, np.ndarray]
	count_by_condition: dict[str, np.ndarray]
	run_counts: dict[str, int]


def _empty_matrix() -> np.ndarray:
	return np.zeros((len(AGENTS), len(AGENTS)), dtype=float)


def _list_run_dirs(provider: str) -> list[Path]:
	memory_dir = ALL_DATA_DIR / f"data_{provider}" / "memory"
	if not memory_dir.exists():
		return []
	return sorted(path for path in memory_dir.iterdir() if path.is_dir())


def _infer_condition(run_name: str) -> str | None:
	for condition in CONDITIONS:
		if f"_{condition}_" in run_name:
			return condition
	return None


def _safe_score(raw: object) -> float | None:
	if raw is None:
		return None
	try:
		value = float(raw)
	except (TypeError, ValueError):
		return None
	if math.isnan(value):
		return None
	return value


def collect_provider_data(provider: str) -> ProviderData:
	matrix_all = _empty_matrix()
	count_all = _empty_matrix()
	matrix_by_condition = {condition: _empty_matrix() for condition in CONDITIONS}
	count_by_condition = {condition: _empty_matrix() for condition in CONDITIONS}
	run_counts = {condition: 0 for condition in CONDITIONS}

	for run_dir in _list_run_dirs(provider):
		condition = _infer_condition(run_dir.name)
		if condition is None:
			continue

		run_counts[condition] += 1

		for agent_file in sorted(run_dir.glob("*.json")):
			try:
				payload = json.loads(agent_file.read_text(encoding="utf-8"))
			except json.JSONDecodeError:
				continue

			from_agent = str(payload.get("agent_id", "")).strip()
			if from_agent not in AGENT_TO_INDEX:
				continue
			from_idx = AGENT_TO_INDEX[from_agent]

			raw_scores = payload.get("connection_scores")
			if not isinstance(raw_scores, dict):
				continue

			for to_agent, raw_value in raw_scores.items():
				to_agent = str(to_agent).strip()
				if to_agent not in AGENT_TO_INDEX:
					continue
				if to_agent == from_agent:
					continue

				score = _safe_score(raw_value)
				if score is None:
					continue

				to_idx = AGENT_TO_INDEX[to_agent]
				matrix_all[from_idx, to_idx] += score
				count_all[from_idx, to_idx] += 1
				matrix_by_condition[condition][from_idx, to_idx] += score
				count_by_condition[condition][from_idx, to_idx] += 1

	return ProviderData(
		provider=provider,
		matrix_all=matrix_all,
		count_all=count_all,
		matrix_by_condition=matrix_by_condition,
		count_by_condition=count_by_condition,
		run_counts=run_counts,
	)


def compute_mean(sum_matrix: np.ndarray, count_matrix: np.ndarray) -> np.ndarray:
	mean = np.full(sum_matrix.shape, np.nan, dtype=float)
	mask = count_matrix > 0
	mean[mask] = sum_matrix[mask] / count_matrix[mask]
	np.fill_diagonal(mean, np.nan)
	return mean


def _configure_heatmap_axes(ax: plt.Axes, title: str) -> None:
	ax.set_title(title)
	ax.set_xticks(range(len(AGENTS)))
	ax.set_yticks(range(len(AGENTS)))
	ax.set_xticklabels(AGENTS)
	ax.set_yticklabels(AGENTS)
	ax.set_xlabel("To Agent")
	ax.set_ylabel("From Agent")


def save_heatmap(provider_data: dict[str, ProviderData]) -> Path:
	fig, axes = plt.subplots(2, 2, figsize=(16, 13), constrained_layout=True)
	fig.suptitle("Mean Connection Scores by Provider (All Runs)", fontsize=16)

	vmax = 5.0
	vmin = 0.0
	last_im = None

	for idx, provider in enumerate(PROVIDERS):
		row, col = divmod(idx, 2)
		ax = axes[row, col]
		pdata = provider_data[provider]
		mean_matrix = compute_mean(pdata.matrix_all, pdata.count_all)

		im = ax.imshow(mean_matrix, vmin=vmin, vmax=vmax, cmap="YlOrRd")
		last_im = im
		_configure_heatmap_axes(
			ax,
			f"{provider} (runs: N={pdata.run_counts['neutral']}, E={pdata.run_counts['emotional']})",
		)

		# Annotate each valid cell for readability.
		for i in range(len(AGENTS)):
			for j in range(len(AGENTS)):
				value = mean_matrix[i, j]
				if np.isnan(value):
					continue
				ax.text(j, i, f"{value:.1f}", ha="center", va="center", fontsize=7)

	if last_im is not None:
		cbar = fig.colorbar(last_im, ax=axes.ravel().tolist(), shrink=0.86)
		cbar.set_label("Mean connection score")

	output_path = BASE_DIR / "connection_heatmap_all_models.png"
	fig.savefig(output_path, dpi=220)
	plt.close(fig)
	return output_path


def _draw_network_panel(ax: plt.Axes, mean_matrix: np.ndarray, provider: str, threshold: float = 4.4) -> None:
	n = len(AGENTS)
	theta = np.linspace(0, 2 * np.pi, n, endpoint=False)
	x = np.cos(theta)
	y = np.sin(theta)

	ax.set_title(f"{provider} network (edges >= {threshold:.1f})")
	ax.set_aspect("equal")
	ax.axis("off")

	for i, agent in enumerate(AGENTS):
		ax.scatter(x[i], y[i], s=250, color="#2b6cb0", zorder=3)
		ax.text(x[i] * 1.08, y[i] * 1.08, agent, ha="center", va="center", fontsize=9)

	for i in range(n):
		for j in range(n):
			if i == j:
				continue
			value = mean_matrix[i, j]
			if np.isnan(value) or value < threshold:
				continue

			start = np.array([x[i], y[i]])
			end = np.array([x[j], y[j]])
			vec = end - start
			dist = np.linalg.norm(vec)
			if dist == 0:
				continue
			unit = vec / dist

			# Shorten arrow so it starts/ends outside the node markers.
			s = start + unit * 0.09
			e = end - unit * 0.11
			alpha = min(0.95, 0.2 + (value / 5.0) * 0.75)
			lw = 0.8 + (value / 5.0) * 1.6
			ax.annotate(
				"",
				xy=(e[0], e[1]),
				xytext=(s[0], s[1]),
				arrowprops=dict(arrowstyle="->", linewidth=lw, color="#d97706", alpha=alpha),
				zorder=1,
			)


def save_network_map(provider_data: dict[str, ProviderData]) -> Path:
	fig, axes = plt.subplots(2, 2, figsize=(15, 13), constrained_layout=True)
	fig.suptitle("High-Trust Directed Connection Map (All Runs)", fontsize=16)

	for idx, provider in enumerate(PROVIDERS):
		row, col = divmod(idx, 2)
		ax = axes[row, col]
		pdata = provider_data[provider]
		mean_matrix = compute_mean(pdata.matrix_all, pdata.count_all)
		_draw_network_panel(ax, mean_matrix, provider)

	output_path = BASE_DIR / "connection_network_all_models.png"
	fig.savefig(output_path, dpi=220)
	plt.close(fig)
	return output_path


def summarize_provider(pdata: ProviderData) -> list[str]:
	lines: list[str] = []
	mean_all = compute_mean(pdata.matrix_all, pdata.count_all)

	lines.append(f"Provider: {pdata.provider}")
	lines.append(
		f"  runs -> neutral={pdata.run_counts['neutral']}, emotional={pdata.run_counts['emotional']}"
	)

	valid_values = mean_all[~np.isnan(mean_all)]
	overall_mean = float(np.mean(valid_values)) if valid_values.size else float("nan")
	lines.append(f"  overall mean directed score: {overall_mean:.3f}")

	# Strongest directed pair
	if valid_values.size:
		idx = np.nanargmax(mean_all)
		i, j = np.unravel_index(idx, mean_all.shape)
		lines.append(
			f"  strongest directed pair: {AGENTS[i]} -> {AGENTS[j]} ({mean_all[i, j]:.3f})"
		)

	# Most trusted target (highest mean incoming)
	incoming_means = np.nanmean(mean_all, axis=0)
	if np.any(~np.isnan(incoming_means)):
		best_target = int(np.nanargmax(incoming_means))
		lines.append(
			f"  most trusted target (incoming avg): {AGENTS[best_target]} ({incoming_means[best_target]:.3f})"
		)

	# Reciprocity: smaller means more symmetric two-way relationships.
	reciprocity = np.nanmean(np.abs(mean_all - mean_all.T))
	lines.append(f"  reciprocity gap |A_ij - A_ji| mean: {reciprocity:.3f}")

	# Emotional-neutral shift.
	mean_neutral = compute_mean(
		pdata.matrix_by_condition["neutral"], pdata.count_by_condition["neutral"]
	)
	mean_emotional = compute_mean(
		pdata.matrix_by_condition["emotional"], pdata.count_by_condition["emotional"]
	)
	shift = np.nanmean(mean_emotional - mean_neutral)
	lines.append(f"  emotional - neutral mean shift: {shift:.3f}")

	# Largest pairwise shift, if both conditions available.
	delta = mean_emotional - mean_neutral
	if np.any(~np.isnan(delta)):
		didx = np.nanargmax(np.abs(delta))
		di, dj = np.unravel_index(didx, delta.shape)
		sign = "increase" if delta[di, dj] >= 0 else "decrease"
		lines.append(
			f"  largest condition shift: {AGENTS[di]} -> {AGENTS[dj]} ({delta[di, dj]:+.3f}, {sign})"
		)

	lines.append("")
	return lines


def save_interpretation(
	provider_data: dict[str, ProviderData],
	heatmap_path: Path,
	network_path: Path,
) -> Path:
	out = BASE_DIR / "visulation.txt"
	lines: list[str] = []
	lines.append("Connection Visualization Summary")
	lines.append("=" * 80)
	lines.append(f"Heatmap image: {heatmap_path.name}")
	lines.append(f"Network image: {network_path.name}")
	lines.append("")
	lines.append("Interpretation")
	lines.append("- Heatmap: cell(i, j) is the mean score assigned by i to j across runs.")
	lines.append("- Network map: directed edges only for high-trust links (>= 4.4).")
	lines.append("- Self-links are excluded.")
	lines.append("")

	for provider in PROVIDERS:
		lines.extend(summarize_provider(provider_data[provider]))

	out.write_text("\n".join(lines), encoding="utf-8")
	return out


def main() -> None:
	provider_data = {provider: collect_provider_data(provider) for provider in PROVIDERS}

	heatmap_path = save_heatmap(provider_data)
	network_path = save_network_map(provider_data)
	summary_path = save_interpretation(provider_data, heatmap_path, network_path)

	print("Saved:")
	print(f"- {heatmap_path}")
	print(f"- {network_path}")
	print(f"- {summary_path}")


if __name__ == "__main__":
	main()

