"""Flask application — SimCo backend.

Endpoints:
  POST /api/greet  Post a greeting message
  GET  /api/greets List all greetings
  DELETE /api/greets Clear all greetings
  POST /new-run   Initialise a fresh run (game_state + memory files)
  GET  /state     Return current game_state.json
  POST /act       Trigger one agent's game-phase decision (calls LangGraph)
  POST /chat      Send a message to an agent; returns its reply (calls LangGraph)
  GET  /results   Return runs/{run_id}.json + scores/{run_id}.json
"""
import os
import sys
from flask import Flask, request, jsonify
from flask_cors import CORS

from datetime import datetime

from services import storage
from graph.pipeline import run_pipeline
from graph.nodes import _strip_connection_line


# Allow imports of sibling packages (services/, graph/) when run from backend/
sys.path.insert(0, os.path.dirname(__file__))

app = Flask(__name__)
CORS(app)

# In-memory store: list of { player, message, time }
greetings = []


# ---------------------------------------------------------------------------
# POST /api/greet  |  GET /api/greets  |  DELETE /api/greets
# ---------------------------------------------------------------------------

@app.route('/api/greet', methods=['POST'])
def post_greet():
    data = request.get_json(force=True, silent=True) or {}
    player = str(data.get('player', '')).strip()
    message = str(data.get('message', '')).strip()

    if not player or not message:
        return jsonify({'error': 'player and message are required'}), 400

    entry = {
        'player': player,
        'message': message,
        'time': datetime.utcnow().strftime('%H:%M:%S')
    }
    greetings.append(entry)
    return jsonify(entry), 201


@app.route('/api/greets', methods=['GET'])
def get_greets():
    return jsonify(greetings)


@app.route('/api/greets', methods=['DELETE'])
def clear_greets():
    greetings.clear()
    return jsonify({'cleared': True})


# ---------------------------------------------------------------------------
# POST /new-run
# ---------------------------------------------------------------------------

@app.route("/new-run", methods=["POST"])
def new_run():
    """Initialise game_state.json and per-agent memory for a fresh run.

    Expected JSON body:
      {
        "run_id":     "run_001",
        "condition":  "neutral" | "emotional",
        "agents":     ["A","B","C","D","E","F","G","H","I","J"],
        "prize_pool": 100000,           // optional, default 100000
        "contexts":   { "A": "...", … } // optional, only for emotional
      }
    """
    data = request.get_json(force=True, silent=True) or {}

    run_id = str(data.get("run_id", "")).strip()
    condition = str(data.get("condition", "neutral")).strip()
    agents = data.get("agents") or [chr(ord("A") + i) for i in range(10)]
    prize_pool = int(data.get("prize_pool", 100_000))
    contexts = data.get("contexts") or {}

    if not run_id:
        return jsonify({"error": "run_id is required"}), 400
    if condition not in ("neutral", "emotional"):
        return jsonify({
            "error": "condition must be 'neutral' or 'emotional'"
            }), 400

    game_state = storage.init_new_run(
        run_id=run_id,
        condition=condition,
        agents=agents,
        prize_pool=prize_pool,
        contexts=contexts,
    )
    return jsonify({"status": "ok", "game_state": game_state}), 201


# ---------------------------------------------------------------------------
# GET /state
# ---------------------------------------------------------------------------

@app.route("/state", methods=["GET"])
def get_state():
    """Return the current game_state.json."""
    state = storage.read_game_state()
    if not state:
        return jsonify({
            "error": "No active run. Call POST /new-run first."
            }), 404
    return jsonify(state)


# ---------------------------------------------------------------------------
# POST /act
# ---------------------------------------------------------------------------

@app.route("/act", methods=["POST"])
def act():
    """Trigger an agent's game-phase decision.

    Expected JSON body:
            {
                "agent_id": "A",
                "run_id": "run_001",
                "provider": "openai",         // optional
                "model": "gpt-4o-mini"        // optional
            }

    Returns:
      { "amount": 8000, "reasoning": "...", "connection_score": 3,
        "new_pool": 92000, "agents_remaining": 9 }
    """
    data = request.get_json(force=True, silent=True) or {}
    agent_id = str(data.get("agent_id", "")).strip()
    run_id = str(data.get("run_id", "")).strip()
    llm_provider = str(data.get("provider", "")).strip() or None
    llm_model = str(data.get("model", "")).strip() or None

    if not agent_id or not run_id:
        return jsonify({"error": "agent_id and run_id are required"}), 400

    game_state = storage.read_game_state()
    if game_state.get("run_id") != run_id:
        return jsonify({
            "error": f"run_id '{run_id}' does not match active run"
        }), 400

    # Run LangGraph pipeline
    result = run_pipeline(
        agent_id=agent_id,
        run_id=run_id,
        phase="game",
        llm_provider=llm_provider,
        llm_model=llm_model,
    )

    amount = result.get("amount") or 0
    reasoning = result.get("reasoning") or ""
    connection_score = result.get("connection_score")

    # Clamp to available pool
    prize_pool = game_state.get("prize_pool", 0)
    amount = max(0, min(amount, prize_pool))

    fair_share = (
        prize_pool / game_state.get("agents_remaining", 1)
        if game_state.get("agents_remaining", 1) > 0
        else 0
    )

    # Persist allocation
    storage.append_allocation(
        run_id, agent_id, amount, fair_share, reasoning
        )

    # Advance game state
    new_pool = prize_pool - amount
    agents_remaining = max(0, game_state.get("agents_remaining", 1) - 1)
    current_turn = game_state.get("current_turn", 0) + 1

    game_state.update(
        {
            "prize_pool": new_pool,
            "agents_remaining": agents_remaining,
            "current_turn": current_turn,
        }
    )

    if agents_remaining == 0:
        game_state["phase"] = "post_game"
        storage.compute_and_write_scores(run_id)

    storage.write_game_state(game_state)

    return jsonify(
        {
            "amount": amount,
            "reasoning": reasoning,
            "connection_score": connection_score,
            "new_pool": new_pool,
            "agents_remaining": agents_remaining,
        }
    )


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

@app.route("/chat", methods=["POST"])
def chat():
    """Log a message from one agent and return the recipient's reply.

    Expected JSON body:
      {
        "run_id":   "run_001",
        "from":     "A",
        "to":       "B",
        "message":  "Hey, how are you?",
                "phase":    "pre_game",   // or "post_game"
                "provider": "openai",     // optional
                "model":    "gpt-4o-mini" // optional
      }

    Returns:
      { "reply": "Hi! I'm a bit nervous…" }
    """
    data = request.get_json(force=True, silent=True) or {}
    run_id = str(data.get("run_id", "")).strip()
    from_agent = str(data.get("from", "")).strip()
    to_agent = str(data.get("to", "")).strip()
    message = str(data.get("message", "")).strip()
    phase = str(data.get("phase", "pre_game")).strip()
    llm_provider = str(data.get("provider", "")).strip() or None
    llm_model = str(data.get("model", "")).strip() or None

    if not all([run_id, from_agent, to_agent, message]):
        return jsonify({
            "error": "run_id, from, to, and message are required"
            }), 400
    if phase not in ("pre_game", "post_game"):
        return jsonify({
            "error": "phase must be 'pre_game' or 'post_game'"
            }), 400

    # Check exchange limit (max 10 per pair per phase)
    conv = storage.read_conversation(run_id, from_agent, to_agent)
    phase_key = "pre_game" if phase == "pre_game" else "post_game"
    existing = conv.get(phase_key, [])
    if len(existing) >= 20:  # 20 messages = 10 exchanges (each side speaks 10)
        return jsonify({
            "error": "Exchange limit (10) reached for this pair"
            }), 429

    # Persist the sender's message (strip any connection score line first)
    storage.append_conversation(
        run_id, from_agent, to_agent, _strip_connection_line(message), phase
    )

    # Run LangGraph for the recipient
    pipeline_phase = "pre_game_chat" \
        if phase == "pre_game" \
        else "post_game_chat"

    result = run_pipeline(
        agent_id=to_agent,
        run_id=run_id,
        phase=pipeline_phase,
        partner_id=from_agent,
        partner_message=message,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )

    reply = result.get("reply_message") or ""

    # Persist the recipient's reply
    storage.append_conversation(run_id, to_agent, from_agent, reply, phase)

    return jsonify({"reply": reply})


# ---------------------------------------------------------------------------
# POST /generate-first-message
# ---------------------------------------------------------------------------

@app.route("/generate-first-message", methods=["POST"])
def generate_first_message():
    """Generate an LLM-crafted opening message for an agent approaching another.

    The message is NOT stored — pass it as the 'message' field to POST /chat.

    Expected JSON body:
      {
        "run_id":   "run_001",
        "from":     "A",
        "to":       "B",
        "provider": "openai",     // optional
        "model":    "gpt-4o-mini" // optional
      }

    Returns:
      { "message": "Hi B, ..." }
    """
    data = request.get_json(force=True, silent=True) or {}
    run_id = str(data.get("run_id", "")).strip()
    from_agent = str(data.get("from", "")).strip()
    to_agent = str(data.get("to", "")).strip()
    llm_provider = str(data.get("provider", "")).strip() or None
    llm_model = str(data.get("model", "")).strip() or None

    if not all([run_id, from_agent, to_agent]):
        return jsonify({"error": "run_id, from, and to are required"}), 400

    result = run_pipeline(
        agent_id=from_agent,
        run_id=run_id,
        phase="pre_game_first_msg",
        partner_id=to_agent,
        partner_message=None,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )
    message = result.get("reply_message") or ""
    return jsonify({"message": message})


# ---------------------------------------------------------------------------
# GET /results
# ---------------------------------------------------------------------------

@app.route("/results", methods=["GET"])
def results():
    """Return allocation and score data for a run.

    Query param: ?run_id=run_001
    Returns:
      { "run": { … }, "scores": { … } }
    """
    run_id = request.args.get("run_id", "").strip()
    if not run_id:
        # Fall back to the active run
        game_state = storage.read_game_state()
        run_id = game_state.get("run_id", "")
    if not run_id:
        return jsonify({"error": "run_id is required"}), 400

    run_data = storage.read_run(run_id)
    scores = storage.read_scores(run_id)

    return jsonify({"run": run_data, "scores": scores})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
