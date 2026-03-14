"""Flask application — SimCo backend.

Endpoints:
  POST /api/greet  Post a greeting message
  GET  /api/greets List all greetings
  DELETE /api/greets Clear all greetings
  POST /new-run          Initialise a fresh run (game_state + memory files)
  GET  /state            Return current game_state.json
  POST /run-pre-game     Run all pre-game discussions automatically
  POST /act              Trigger one agent's game-phase decision
  POST /chat             Send a message to an agent; returns its reply
  POST /generate-first-message  Generate an LLM opening message (not stored)
  GET  /results          Return runs/{run_id}.json + scores/{run_id}.json
"""
import os
import sys
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
from pathlib import Path

from services import storage
from services.runner import (
    init_new_run,
    run_pre_game_phase,
    act_agent,
    run_post_game_phase,
    send_chat
)
from graph.pipeline import run_pipeline


# Allow imports of sibling packages (services/, graph/) when run from backend/
sys.path.insert(0, os.path.dirname(__file__))

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')

app = Flask(__name__)
CORS(app)

# In-memory store: list of { player, message, time }
greetings = []


# ---------------------------------------------------------------------------
# POST /api/greet  |  GET /api/greets  |  DELETE /api/greets
# ---------------------------------------------------------------------------

@app.route('/')
@app.route('/hi')
def home():
    return send_from_directory(FRONTEND_DIR, 'home.html')


@app.route('/api/setup-defaults', methods=['GET'])
def setup_defaults():
    """Return setup defaults loaded from backend config files."""
    return jsonify({
        'defaults_by_provider': storage.load_default_models_by_provider(),
        'default_contexts': storage.load_default_contexts(),
    })


@app.route('/api/runs', methods=['GET'])
def list_runs():
    """List all runs with summary info
    (agents, condition, allocations, convs).
    """
    runs_dir = Path(storage.DATA_DIR) / 'runs'
    conv_base = Path(storage.DATA_DIR) / 'conversations'
    active_run_id = (storage.read_game_state() or {}).get('run_id', '')
    items = []
    for f in sorted(runs_dir.glob('*.json'), reverse=True):
        try:
            run = json.loads(f.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            continue
        run_id = run.get('run_id') or f.stem
        # Count conversation pair files
        conv_dir = conv_base / run_id
        pair_count = len(list(conv_dir.glob('*.json'))) \
            if conv_dir.exists() else 0
        allocations = run.get('allocations') or []
        agents = sorted({a['agent'] for a in allocations}) or []
        items.append({
            'run_id': run_id,
            'condition': run.get('condition', ''),
            'llm_model': run.get('llm_model', ''),
            'llm_provider': run.get('llm_provider', ''),
            'agents': agents,
            'allocation_count': len(allocations),
            'conversation_pairs': pair_count,
            'connection_scores': len(run.get('connection_scores') or []),
            'post_game_requests': len(run.get('post_game_requests') or []),
            'is_active': run_id == active_run_id,
        })
    return jsonify({'runs': items})


@app.route('/api/run-view', methods=['GET'])
def run_view():
    """Return historical run data needed to render
    /game for a past simulation.
    """
    run_id = request.args.get('run_id', '').strip()
    if not run_id:
        return jsonify({'error': 'run_id is required'}), 400

    run = storage.read_run(run_id)
    scores = storage.read_scores(run_id)
    game_state = storage.read_game_state() or {}

    agents = set()
    for entry in run.get('allocations') or []:
        agent = str(entry.get('agent', '')).strip()
        if agent:
            agents.add(agent)
    for entry in scores.get('agents') or []:
        agent = str(entry.get('agent', '')).strip()
        if agent:
            agents.add(agent)

    conv_dir = Path(storage.DATA_DIR) / 'conversations' / run_id
    if conv_dir.exists():
        for f in conv_dir.glob('*.json'):
            try:
                data = json.loads(f.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                continue
            for agent in data.get('pair') or []:
                cleaned = str(agent).strip()
                if cleaned:
                    agents.add(cleaned)

    if game_state.get('run_id') == run_id:
        for agent in game_state.get('turn_order') or []:
            cleaned = str(agent).strip()
            if cleaned:
                agents.add(cleaned)

    agents_list = sorted(agents)
    allocations = run.get('allocations') or []
    total_taken = sum(int(entry.get('taken', 0) or 0) for entry in allocations)

    initial_prize_pool = None
    remaining_prize_pool = None
    if game_state.get('run_id') == run_id:
        initial_prize_pool = game_state.get('initial_prize_pool')
        remaining_prize_pool = game_state.get('prize_pool')
    elif allocations:
        initial_prize_pool = total_taken
        remaining_prize_pool = 0

    return jsonify({
        'run_id': run_id,
        'agents': agents_list,
        'run': run,
        'scores': scores,
        'total_taken': total_taken,
        'initial_prize_pool': initial_prize_pool,
        'remaining_prize_pool': remaining_prize_pool,
    })


@app.route('/game')
def game():
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/setup')
def setup():
    return send_from_directory(FRONTEND_DIR, 'setup.html')


@app.route('/chat', methods=['GET'])
def chat_page():
    return send_from_directory(FRONTEND_DIR, 'chat.html')


@app.route('/game/<path:filename>')
def game_static(filename):
    return send_from_directory(FRONTEND_DIR, filename)


@app.route('/game.js')
def game_js():
    return send_from_directory(FRONTEND_DIR, 'game.js')


@app.route('/phaser/<path:filename>')
def phaser_static(filename):
    return send_from_directory(FRONTEND_DIR, 'phaser/' + filename)


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


@app.route('/api/conversations', methods=['GET'])
def list_conversations():
    """Return conversation threads grouped by pair for one run.

    Query param: ?run_id=<id> (optional).
    If omitted, uses active game_state run.
    """
    run_id = request.args.get('run_id', '').strip()
    game_state = storage.read_game_state()
    if not run_id:
        run_id = str(game_state.get('run_id', '')).strip()
    if not run_id:
        return jsonify({'error': 'run_id is required'}), 400

    turn_order = game_state.get('turn_order', []) \
        if game_state.get('run_id') == run_id else []
    expected_pairs = {}
    for i in range(len(turn_order)):
        for j in range(i + 1, len(turn_order)):
            a, b = sorted([turn_order[i], turn_order[j]])
            expected_pairs[
                f'{a}_{b}'] = {
                    'pair': [a, b],
                    'pre_game': [],
                    'post_game': []
                    }

    conv_dir = Path(storage.DATA_DIR) / 'conversations' / run_id
    if conv_dir.exists():
        for f in sorted(conv_dir.glob('*.json')):
            try:
                data = json.loads(f.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                continue
            pair = data.get('pair') or f.stem.split('_')
            if len(pair) != 2:
                continue
            a, b = sorted([str(pair[0]), str(pair[1])])
            key = f'{a}_{b}'
            expected_pairs[key] = {
                'pair': [a, b],
                'pre_game': data.get('pre_game') or [],
                'post_game': data.get('post_game') or [],
            }

    items = []
    for key in sorted(expected_pairs.keys()):
        row = expected_pairs[key]
        pre = row.get('pre_game') or []
        post = row.get('post_game') or []
        items.append({
            'pair': row['pair'],
            'pre_game': pre,
            'post_game': post,
            'message_count': len(pre) + len(post),
        })

    return jsonify({'run_id': run_id, 'pairs': items})


# ---------------------------------------------------------------------------
# POST /new-run
# ---------------------------------------------------------------------------
@app.route("/new-run", methods=["POST"])
def new_run():
    """Initialise game_state.json and per-agent memory for a fresh run.

    Expected JSON body:
      {
        "llm_provider":   "openai", "gemini", etc. (for Phaser UI selection)
        "llm_model":      "gpt-4o-mini", "gemini-3-flash-preview", ...
                      (for Phaser UI selection)
        "condition":  "neutral" | "emotional", (from Phaser UI selection)
        "agents":     ["A","B","C","D","E","F","G","H","I","J"],
        "prize_pool": 100000,           // optional, default 100000
        "contexts":   { "A": "...", … } // optional, only for emotional
      }
    """
    data = request.get_json(force=True, silent=True) or {}

    # Condition and default model/provider selection are from Phaser
    condition = str(data.get("condition", "neutral")).strip()
    llm_model = str(data.get("llm_model", "default")).strip()
    llm_provider = str(data.get("llm_provider", "")).strip() or None
    # Generate a run_id based on existing runs, model, and condition.
    # Do not pass static run_id in the request body
    run_id = storage.generate_run_id(
        model_type=llm_model,
        condition=condition,
    )

    # agents, are from phaser
    agents = data.get("agents") or [chr(ord("A") + i) for i in range(10)]
    prize_pool = int(data.get("prize_pool", 100_000))
    contexts = data.get("contexts") or {}

    if not run_id:
        return jsonify({"error": "run_id is required"}), 400
    if condition not in ("neutral", "emotional"):
        return jsonify({
            "error": "condition must be 'neutral' or 'emotional'"
            }), 400

    game_state = init_new_run(
        llm_provider=llm_provider,
        llm_model=llm_model,
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
    """Trigger an agent's game-phase decision."""
    data = request.get_json(force=True, silent=True) or {}
    agent_id = str(data.get("agent_id", "")).strip()
    if not agent_id:
        return jsonify({"error": "agent_id is required"}), 400
    if not storage.read_game_state():
        return jsonify({
            "error": "No active run. Call POST /new-run first."
            }), 400

    result = act_agent(agent_id)
    return jsonify(result)


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

@app.route("/chat", methods=["POST"])
def chat_api():
    """Log a message from one agent and return the recipient's reply."""
    data = request.get_json(force=True, silent=True) or {}
    from_agent = str(data.get("from", "")).strip()
    to_agent = str(data.get("to", "")).strip()
    message = str(data.get("message", "")).strip()
    phase = str(data.get("phase", "pre_game")).strip()

    if not all([from_agent, to_agent, message]):
        return jsonify({"error": "from, to, and message are required"}), 400
    if phase not in ("pre_game", "post_game"):
        return jsonify({
            "error": "phase must be 'pre_game' or 'post_game'"
            }), 400

    game_state = storage.read_game_state()
    if not game_state:
        return jsonify({
            "error": "No active run. Call POST /new-run first."
            }), 400

    try:
        result = send_chat(
            run_id=game_state["run_id"],
            from_agent=from_agent, to_agent=to_agent,
            message=message, phase=phase,
            llm_provider=game_state.get("llm_provider"),
            llm_model=game_state.get("llm_model"),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 429

    return jsonify(result)


# ---------------------------------------------------------------------------
# POST /run-pre-game
# ---------------------------------------------------------------------------

@app.route("/run-pre-game", methods=["POST"])
def run_pre_game():
    """Run all pre-game pair discussions automatically."""
    game_state = storage.read_game_state()
    if not game_state:
        return jsonify({
            "error": "No active run. Call POST /new-run first."
            }), 400
    if len(game_state.get("turn_order") or []) < 2:
        return jsonify({
            "error": "Need at least 2 agents to run discussions."
            }), 400

    pairs = run_pre_game_phase(game_state)
    return jsonify({"status": "ok", "pairs": pairs}), 200


# ---------------------------------------------------------------------------
# POST /generate-first-message
# ---------------------------------------------------------------------------

@app.route("/generate-first-message", methods=["POST"])
def generate_first_message():
    """Generate an LLM-crafted opening message
    for an agent approaching another.

    The message is NOT stored — pass it as the 'message' field to POST /chat.

    Expected JSON body:
      {
        "from":     "A",
        "to":       "B",
      }

    Returns:
      {
        "message": "Hi B, ..."
    }
    """
    data = request.get_json(force=True, silent=True) or {}
    from_agent = str(data.get("from", "")).strip()
    to_agent = str(data.get("to", "")).strip()

    # Load run_id, llm_provider, and llm_model from game_state.json
    game_state = storage.read_game_state()
    if not game_state:
        return jsonify({
            "error": "No active run. Call POST /new-run first."
            }), 400

    run_id = game_state.get("run_id")
    llm_provider = game_state.get("llm_provider")
    llm_model = game_state.get("llm_model")

    if not all([from_agent, to_agent]):
        return jsonify({"error": "from and to are required"}), 400

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
      {
        "run": { … },
        "scores": { … }
    }
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
    app.run(debug=True, port=5001)
