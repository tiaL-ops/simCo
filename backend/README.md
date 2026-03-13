# Backend CLI Quickstart

## Setup
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run
```bash
python cli.py
```

## What the CLI does
- Creates or resumes a run
- Runs pre-game discussions
- Runs game allocation decisions
- Runs post-game discussions
- Prints final results (allocations, connection scores, gini)

All data is saved under `backend/data/`.