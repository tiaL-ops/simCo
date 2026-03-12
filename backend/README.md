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

## To test API endpoints:
1. Start the Flask server: `python app.py`
2. In another terminal, run the test script: `python test_endpoints.py`

## To do:
- [ ] update parsing better depeding on model
- [ ] Choose which model to use 
- [ ] Conversation summary


## Understand the work:
So it is 