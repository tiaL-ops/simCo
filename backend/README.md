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
- choose a round
- Runs pre-game discussions ( resume other that did not talk)
- Runs game allocation decisions
- Runs post-game discussions
- Prints final results (allocations, connection scores, gini)

IMPORTANT: 

Please make sure you finish an experimetn befopre moving to a new one. If it was cut, resume from taht experiment

You will the version based on name of the file for example:
run_0001_claude-haiku-4-5-20251001_20260314T185631Z_neutral_v3

v3 is the 3 rd : J  G H  E C  F I B D A order

All data is saved under `backend/data/`.

## Game Interface 
You will see the gaming interface : 
http://localhost:5001/hi ( for now please chose view past simulation)

- click on opengame it will lead yo to  http://localhost:5001/game  ( to see the score and resume)

- click on open chat it will lead yo to  http://localhost:5001/chat ( to see the chat between two agent)

