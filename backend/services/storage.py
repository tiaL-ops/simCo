"""Storage service: read/write all JSON data files.

All data lives under backend/data/:
  game_state.json
  runs/{run_id}.json
  conversations/{run_id}/{A}_{B}.json   (pair sorted alphabetically)
    memory/{run_id}/{agent_id}.json
  scores/{run_id}.json
"""
import re
import json
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"

GAME_STATE_FILE = DATA_DIR / "game_state.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            data, indent=2, ensure_ascii=False
            ),
        encoding="utf-8"
        )


def _pair_key(a: str, b: str) -> str:
    """Return alphabetically sorted pair name (e.g. 'A_B')."""
    return "_".join(sorted([a, b]))


def _normalize_text(value: Any) -> str:
    """Coerce mixed JSON values to safe plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value if item is not None)
    return str(value)


def load_default_contexts() -> dict[str, str]:
    """Load default emotional contexts from config/default_contexts.json."""
    path = CONFIG_DIR / "default_contexts.json"
    data = _read(path)
    if isinstance(data, dict):
        return {
            str(k): _normalize_text(v)
            for k, v in data.items()
        }
    return {}


def load_default_models_by_provider() -> dict[str, str]:
    """Load default provider-model mapping from config JSON."""
    path = CONFIG_DIR / "default_models_by_provider.json"
    data = _read(path)
    if isinstance(data, dict):
        return {
            str(k): _normalize_text(v)
            for k, v in data.items()
            if _normalize_text(v)
        }
    return {}


def generate_run_id(
    condition: str,
    model_type: str,
    variant: int | None = None,
    data_dir: Path | None = None,
) -> str:
    """Create run_id with per-spec order, model, UTC timestamp, condition.

    Format:
      run_<order>_<model>_<YYYYMMDDTHHMMSSZ>_<condition>[_v<N>]
    Example:
      run_0012_gpt-4o-mini_20260312T154501Z_emotional_v2

    Order is scoped by (model, condition[_vN]), not global. This means
    each model/condition/variant tuple has its own independent sequence.
    """
    base_dir = data_dir or DATA_DIR
    runs_dir = base_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Keep model/context safe for filenames and consistent IDs.
    safe_model = re.sub(
        r"[^a-zA-Z0-9._-]+",
        "-",
        (model_type or "default").strip().lower())
    safe_condition = re.sub(
        r"[^a-zA-Z0-9._-]+",
        "-",
        (condition or "neutral").strip().lower()
    )
    if variant is not None:
        safe_condition = f"{safe_condition}_v{variant}"

    # Determine next run order for this specific model/condition pair.
    # Looks for files like: run_0001_<model>_<ts>_<condition>.json
    pattern = (
        rf"run_(\d+)_{re.escape(safe_model)}_"
        rf"\d{{8}}T\d{{6}}Z_{re.escape(safe_condition)}$"
    )
    max_order = 0
    for f in runs_dir.glob("run_*.json"):
        match = re.match(pattern, f.stem)
        if match:
            max_order = max(max_order, int(match.group(1)))
    next_order = max_order + 1

    # UTC timestamp for stable ordering across environments.
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    return f"run_{next_order:04d}_{safe_model}_{timestamp}_{safe_condition}"


# ---------------------------------------------------------------------------
# game_state.json
# ---------------------------------------------------------------------------

def read_game_state() -> dict:
    data = _read(GAME_STATE_FILE)
    return data if data is not None else {}


def write_game_state(state: dict) -> None:
    _write(GAME_STATE_FILE, state)


# ---------------------------------------------------------------------------
# memory/{run_id}/{agent_id}.json
# ---------------------------------------------------------------------------

def _resolve_memory_paths(
    agent_id: str,
    run_id: str | None = None,
) -> tuple[Path, Path]:
    """Return (primary_run_path, legacy_flat_path) for an agent memory file."""
    resolved_run_id = (run_id or "").strip()
    if not resolved_run_id:
        state = read_game_state()
        resolved_run_id = str(state.get("run_id", "")).strip()

    if resolved_run_id:
        primary = DATA_DIR / "memory" / resolved_run_id / f"{agent_id}.json"
    else:
        primary = DATA_DIR / "memory" / f"{agent_id}.json"

    legacy = DATA_DIR / "memory" / f"{agent_id}.json"
    return primary, legacy


def read_memory(agent_id: str, run_id: str | None = None) -> dict:
    path, legacy_path = _resolve_memory_paths(agent_id, run_id)
    data = _read(path)
    if data is None and legacy_path != path:
        # Backward compatibility for runs created before run-scoped memory.
        data = _read(legacy_path)
    if data is None:
        return {
            "agent_id": agent_id,
            "condition": "neutral",
            "context": "",
            "conversation_summaries": {},
            "connection_scores": {},
        }
    return data


def write_memory(
    agent_id: str,
    data: dict,
    run_id: str | None = None,
) -> None:
    path, _legacy_path = _resolve_memory_paths(agent_id, run_id)
    _write(path, data)


def init_agent_memory(
        agent_id: str,
        condition: str,
        context: str = "",
        run_id: str | None = None,
        ) -> dict:
    memory = {
        "agent_id": agent_id,
        "condition": condition,
        "context": _normalize_text(context),
        "conversation_summaries": {},
        "connection_scores": {},
    }
    write_memory(agent_id, memory, run_id=run_id)
    return memory


# ---------------------------------------------------------------------------
# conversations/{run_id}/{A}_{B}.json
# ---------------------------------------------------------------------------

def read_conversation(run_id: str, agent_a: str, agent_b: str) -> dict:
    key = _pair_key(agent_a, agent_b)
    path = DATA_DIR / "conversations" / run_id / f"{key}.json"
    data = _read(path)
    if data is None:
        return {
            "run_id": run_id,
            "pair": sorted([agent_a, agent_b]),
            "pre_game": [],
            "post_game": [],
        }
    return data


def append_conversation(
    run_id: str,
    from_agent: str,
    to_agent: str,
    message: str,
    phase: str,
) -> None:
    """Append one message to the conversation file.

    Args:
        phase: "pre_game" or "post_game"
    """
    conv = read_conversation(run_id, from_agent, to_agent)
    phase_key = "pre_game" if phase == "pre_game" else "post_game"
    turns = conv.get(phase_key, [])
    turn_num = len(turns) + 1
    turns.append({"turn": turn_num, "from": from_agent, "message": message})
    conv[phase_key] = turns

    key = _pair_key(from_agent, to_agent)
    path = DATA_DIR / "conversations" / run_id / f"{key}.json"
    _write(path, conv)


def clear_conversation_phase(run_id: str, phase: str) -> None:
    """Clear one phase across all pair conversation files for a run."""
    conv_dir = DATA_DIR / "conversations" / run_id
    if not conv_dir.exists():
        return

    phase_key = "pre_game" if phase == "pre_game" else "post_game"
    for path in conv_dir.glob("*.json"):
        data = _read(path)
        if not data:
            continue
        data[phase_key] = []
        _write(path, data)


def get_all_agent_conversations(run_id: str, agent_id: str) -> list[dict]:
    """Return all conversation objects that involve agent_id."""
    conv_dir = DATA_DIR / "conversations" / run_id
    if not conv_dir.exists():
        return []
    conversations = []
    for f in conv_dir.glob("*.json"):
        parts = f.stem.split("_")
        if agent_id in parts:
            data = _read(f)
            if data:
                conversations.append(data)
    return conversations


# ---------------------------------------------------------------------------
# runs/{run_id}.json
# ---------------------------------------------------------------------------

def read_run(run_id: str) -> dict:
    path = DATA_DIR / "runs" / f"{run_id}.json"
    data = _read(path)
    if data is None:
        return {
            "run_id": run_id,
            "condition": "neutral",
            "allocations": []
            }
    return data


def append_allocation(
    run_id: str,
    agent: str,
    taken: int,
    fair_share: float,
    reasoning: str,
) -> None:
    run = read_run(run_id)
    g_k = round(taken / fair_share, 4) if fair_share > 0 else 0
    run["allocations"].append(
        {
            "agent": agent,
            "taken": taken,
            "fair_share": round(fair_share, 2),
            "g_k": g_k,
            "reasoning": reasoning,
        }
    )
    _write(DATA_DIR / "runs" / f"{run_id}.json", run)


def init_run_file(
    run_id: str,
    condition: str,
    llm_model: str | None,
    llm_provider: str | None,
) -> dict:
    data = {
        "run_id": run_id,
        "condition": condition,
        "llm_model": llm_model,
        "llm_provider": llm_provider,
        "allocations": [],
        "connection_scores": [],
        "post_game_requests": [],
    }
    _write(DATA_DIR / "runs" / f"{run_id}.json", data)
    return data


def append_connection_score(
    run_id: str,
    from_agent: str,
    to_agent: str,
    score: int,
) -> None:
    """Record a directional connection score in runs/{run_id}.json.

    Directional: how from_agent rates to_agent (asymmetric by design).
    Overwrites any previous score for the same (from, to) pair.
    """
    run = read_run(run_id)
    scores = run.setdefault("connection_scores", [])
    # Replace existing entry for same pair, or append.
    for entry in scores:
        if entry["from"] == from_agent and entry["to"] == to_agent:
            entry["score"] = score
            _write(DATA_DIR / "runs" / f"{run_id}.json", run)
            return
    scores.append({"from": from_agent, "to": to_agent, "score": score})
    _write(DATA_DIR / "runs" / f"{run_id}.json", run)


def clear_post_game_requests(run_id: str) -> None:
    """Remove all post-game requests for a run."""
    run = read_run(run_id)
    run["post_game_requests"] = []
    _write(DATA_DIR / "runs" / f"{run_id}.json", run)


def replace_post_game_requests(
    run_id: str,
    from_agent: str,
    requests_for_agent: list[dict],
) -> None:
    """Replace one agent's post-game requests in runs/{run_id}.json."""
    run = read_run(run_id)
    requests = [
        entry for entry in run.setdefault("post_game_requests", [])
        if entry.get("from") != from_agent
    ]

    seen_targets = set()
    for req in requests_for_agent:
        target = _normalize_text(req.get("to"))
        cleaned_message = _normalize_text(req.get("message"))
        if not target or target == from_agent or not cleaned_message:
            continue
        if target in seen_targets:
            continue
        seen_targets.add(target)
        requests.append(
            {
                "from": from_agent,
                "to": target,
                "message": cleaned_message,
            }
        )

    run["post_game_requests"] = requests
    _write(DATA_DIR / "runs" / f"{run_id}.json", run)


# ---------------------------------------------------------------------------
# scores/{run_id}.json
# ---------------------------------------------------------------------------

def read_scores(run_id: str) -> dict:
    path = DATA_DIR / "scores" / f"{run_id}.json"
    data = _read(path)
    return data if data is not None else {}


def compute_and_write_scores(run_id: str) -> dict:
    """Compute g_k per agent and Gini coefficient, then persist."""
    run = read_run(run_id)
    allocations = run.get("allocations", [])
    if not allocations:
        return {}

    taken_values = [a["taken"] for a in allocations]
    agents_data = [
        {"agent": a["agent"], "g_k": a["g_k"]}
        for a in allocations
    ]

    gini = _gini(taken_values)
    scores = {
        "run_id": run_id,
        "gini": round(gini, 4),
        "agents": agents_data,
    }
    _write(DATA_DIR / "scores" / f"{run_id}.json", scores)
    return scores


def _gini(values: list[int]) -> float:
    if not values or sum(values) == 0:
        return 0.0
    n = len(values)
    total = sum(values)
    sorted_v = sorted(values)
    cumulative = sum((i + 1) * v for i, v in enumerate(sorted_v))
    return (2 * cumulative) / (n * total) - (n + 1) / n


# ---------------------------------------------------------------------------
# Run initialisation
# ---------------------------------------------------------------------------

def init_new_run(
    run_id: str,
    condition: str,
    llm_model: str | None,
    llm_provider: str | None,
    agents: list[str],
    prize_pool: int = 100_000,
    contexts: dict[str, str] | None = None,
) -> dict:
    """Initialise game_state.json, memory files, and runs/{run_id}.json."""

    if contexts is None:
        contexts = {}

    turn_order = agents.copy()

    game_state = {
        "run_id": run_id,
        "phase": "pre_game",
        "condition": condition,
        "prize_pool": prize_pool,
        "initial_prize_pool": prize_pool,
        "turn_order": turn_order,
        "current_turn": 0,
        "agents_remaining": len(agents),
        "llm_provider": llm_provider,
        "llm_model": llm_model,
    }
    write_game_state(game_state)

    for agent_id in agents:
        init_agent_memory(
            agent_id,
            condition=condition,
            context=contexts.get(agent_id, ""),
            run_id=run_id,
        )

    init_run_file(run_id, condition, llm_model, llm_provider)

    # Create conversations directory for this run
    conv_dir = DATA_DIR / "conversations" / run_id
    conv_dir.mkdir(parents=True, exist_ok=True)

    # Create run-scoped memory directory for this run
    memory_dir = DATA_DIR / "memory" / run_id
    memory_dir.mkdir(parents=True, exist_ok=True)

    return game_state
