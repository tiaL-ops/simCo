Code associated with the paper: Do AI Agents Exhibit Greed in Shared Resource Environments? Accepted to IEEE International Conference on AItest.

Author: Fanamby Randriamahenintsoa & Landy Rakotoarison.

## Citation and usage
Please cite :
@inproceedings{randriamahenintsoa2025simco,
  title     = {Do AI Agents Exhibit Greed in Shared Resource Environments?},
  author    = {Rakotoarison, Landy and Randriamahenintsoa, Fanamby },
  booktitle = {Proceedings of the IEEE International Conference on AItest},
  year      = {2026}
}

# SimCo

SimCo is a multi-agent simulation for studying how LLM agents behave in a shared resource game.
Agents discuss with each other, decide how much to take from a common pool, and are evaluated for greed/fairness/empathy under different conditions.


https://github.com/user-attachments/assets/39bd4f5d-3c94-420e-9939-d99859df3c08


## What this repository contains

- A Flask backend for run orchestration, storage, and APIs
- A Phaser web interface to inspect and replay simulation runs
- A CLI to create/resume experiments phase by phase


## Core experiment

- 10 agents (A-J) share a common pool 
- Two phases:
	- pre-game pair discussions
	- game allocation decisions


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

Open to view chat and past simulation

- `http://localhost:5001/hi` (home: standalone game + past run viewer)
- `http://localhost:5001/game` (simulation view)
- `http://localhost:5001/chat` (pair chat viewer)

Note: web gameplay is independent from model simulation runs. To view player information and chat log you would need to run our CLI first.


```bash
cd backend
python cli.py
```

### 3) Run experiments from CLI!

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


Additional analysis artifacts are in:

- `data_evaluation/artifacts/`

## Repository structure

```text
backend/            Flask API, CLI, orchestration, prompts, storage, and data
frontend/           Phaser-based UI pages and game scripts
data_evaluation/    Analysis scripts, notebooks, statistical artifacts

```

## Data
All model simulation results are in backend/data
 

## Configuration

Default contexts and model mappings are configured in:

- `backend/config/default_contexts.json`
- `backend/config/default_models_by_provider.json`

## Reproducibility notes

- Runs are written with timestamped IDs and condition/model metadata.
- Keep each run consistent end-to-end (resume before starting another run).
- For exact comparisons, fix provider/model, condition, and turn-order variant.





## Licence
Apache-2.0
```

