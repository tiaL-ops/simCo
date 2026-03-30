# SimCo

SimCo is a multi-agent simulation for studying how LLM agents behave in a shared resource game.
Agents discuss with each other, decide how much to take from a common pool, and are evaluated for greed/fairness/empathy under different conditions.

## What this repository contains

- A Flask backend for run orchestration, storage, and APIs
- A Phaser web interface to inspect and replay simulation runs
- A CLI to create/resume experiments phase by phase
- Evaluation scripts and notebooks for post-run analysis

## Core experiment

- 10 agents (A-J) share a common pool
- Two conditions:
	- neutral
	- emotional
- Three phases:
	- pre-game pair discussions
	- game allocation decisions
	- post-game reflections/discussions

Primary metrics include:

- per-agent behavior ratio (`g_k`)
- Gini coefficient
- empathy-oriented conversation scores (EPITOME-based pipeline)

## Quickstart

### 1) Backend setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Start the web app

```bash
python app.py
```

Open:

- `http://localhost:5001/hi` (home)
- `http://localhost:5001/game` (simulation view)
- `http://localhost:5001/chat` (pair chat viewer)

### 3) Run experiments from CLI (optional)

```bash
cd backend
source .venv/bin/activate
python cli.py
```

The CLI supports:

- creating a new run
- resuming an interrupted run
- choosing condition/model/turn-order variant
- running pre-game, game, and post-game phases
- computing and storing final scores

## Data and outputs

Runtime data is stored under `backend/data/` (generated during runs), including:

- active game state
- per-run allocations
- pairwise conversations
- per-agent memory
- computed scores

Additional analysis artifacts are in:

- `data_evaluation/artifacts/`

## Repository structure

```text
backend/            Flask API, CLI, orchestration, prompts, storage
frontend/           Phaser-based UI pages and game scripts
data_evaluation/    Analysis scripts, notebooks, statistical artifacts
dataset/            Input datasets and evaluation-related resources
SystemDesign.md     Technical architecture and request/data flow
```

## Configuration

Default contexts and model mappings are configured in:

- `backend/config/default_contexts.json`
- `backend/config/default_models_by_provider.json`

## Reproducibility notes

- Runs are written with timestamped IDs and condition/model metadata.
- Keep each run consistent end-to-end (resume before starting another run).
- For exact comparisons, fix provider/model, condition, and turn-order variant.

## Citation and usage

If you use this repository for research, please cite your project/paper and clearly report:

- model/provider used
- condition setup
- scoring/evaluation protocol

## License

Add your license file and update this section before publishing.

