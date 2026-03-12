# Setup

First setup with no virutal environemt
cd backend 
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt


Already have virtual env
cd backend 
source .venv/bin/activate
pip install -r requirements.txt

## Run a full experiment (CLI — no server needed)
```bash
python cli.py
```
Interactive prompts guide you through setup (model, condition, agents, contexts).
Breakpoints pause between each phase so you can inspect data before continuing.

Phases:
1. **New run** — initialises game_state + memory files
2. **Pre-game** — all pairs discuss, rate each other, scores saved
3. **Game** — each agent decides how much to take from the pool
4. **Post-game** — pairs reflect on the results
5. **Results** — allocations, connection scores, Gini printed + saved

## Run via Flask API (server mode)
1. Start the Flask server: `python app.py`
2. Call endpoints in order:
   - `POST /new-run`
   - `POST /run-pre-game`
   - `POST /act` (once per agent)
   - `GET /results`

## To do:
- [ ] update parsing better depeding on model
- [ ] Choose which model to use 
- [ ] Conversation summary


## Understand the work:
So it is 