"""Core experiment logic — shared by app.py (Flask) and cli.py.

All phase functions read game_state.json themselves so callers don't need to
pass state around; they just call the function and get back a result dict.
"""

import itertools

from services import storage
from graph.pipeline import run_pipeline
from graph.nodes import _strip_connection_line

MIN_MESSAGES = 10           # 5 per side before LEAVE is honoured (pre-game)
MAX_MESSAGES = 20           # 10 per side hard cap (pre-game)
MAX_POST_GAME_MESSAGES = 10 # 5 per side hard cap (post-game)


# ---------------------------------------------------------------------------
# Phase 0 — new run
# ---------------------------------------------------------------------------

def new_run(
    llm_provider: str,
    llm_model: str,
    condition: str,
    agents: list[str],
    prize_pool: int,
    contexts: dict[str, str],
) -> dict:
    """Initialise game_state + memory files. Returns the new game_state."""
    run_id = storage.generate_run_id(model_type=llm_model, condition=condition)
    game_state = storage.init_new_run(
        run_id=run_id,
        condition=condition,
        llm_model=llm_model,
        llm_provider=llm_provider,
        agents=agents,
        prize_pool=prize_pool,
        contexts=contexts,
    )
    return game_state


# ---------------------------------------------------------------------------
# Phase 1 — pre-game discussions
# ---------------------------------------------------------------------------

def run_pre_game_phase(game_state: dict) -> list[dict]:
    """Run all pair discussions until each pair naturally ends or hits the cap.

    Returns a list of pair summaries:
      [{"pair": ["A","B"], "turns": 12, "scores": {"A": 4, "B": 3}}, ...]
    """
    run_id       = game_state["run_id"]
    llm_provider = game_state.get("llm_provider")
    llm_model    = game_state.get("llm_model")
    agents       = game_state.get("turn_order", [])
    pairs_summary = []

    for agent_a, agent_b in itertools.combinations(agents, 2):
        pair_log = {"pair": [agent_a, agent_b], "turns": 0, "scores": {}}

        # Opening message from agent_a
        open_result = run_pipeline(
            agent_id=agent_a, run_id=run_id,
            phase="pre_game_first_msg", partner_id=agent_b,
            llm_provider=llm_provider, llm_model=llm_model,
        )
        current_message = open_result.get("reply_message") or ""
        storage.append_conversation(
            run_id, agent_a, agent_b,
            _strip_connection_line(current_message), "pre_game"
        )

        current_sender, current_receiver = agent_a, agent_b

        while True:
            conv = storage.read_conversation(run_id, agent_a, agent_b)
            if len(conv.get("pre_game", [])) >= MAX_MESSAGES:
                # Hard cap: force both agents to rate
                for rater, ratee in [(current_receiver, current_sender),
                                     (current_sender, current_receiver)]:
                    fr = run_pipeline(
                        agent_id=rater, run_id=run_id,
                        phase="pre_game_chat", partner_id=ratee,
                        partner_message=current_message,
                        llm_provider=llm_provider, llm_model=llm_model,
                        force_final=True,
                    )
                    storage.append_conversation(
                        run_id, rater, ratee,
                        _strip_connection_line(fr.get("reply_message") or ""),
                        "pre_game"
                    )
                    if fr.get("connection_score") is not None:
                        pair_log["scores"][rater] = fr["connection_score"]
                break

            result = run_pipeline(
                agent_id=current_receiver, run_id=run_id,
                phase="pre_game_chat", partner_id=current_sender,
                partner_message=current_message,
                llm_provider=llm_provider, llm_model=llm_model,
            )
            reply = result.get("reply_message") or ""
            storage.append_conversation(
                run_id, current_receiver, current_sender,
                _strip_connection_line(reply), "pre_game"
            )
            pair_log["turns"] += 1

            if result.get("connection_score") is not None:
                pair_log["scores"][current_receiver] = result["connection_score"]

            if result.get("wants_to_leave"):
                # Give the other side a forced final rating turn
                fr = run_pipeline(
                    agent_id=current_sender, run_id=run_id,
                    phase="pre_game_chat", partner_id=current_receiver,
                    partner_message=reply,
                    llm_provider=llm_provider, llm_model=llm_model,
                    force_final=True,
                )
                storage.append_conversation(
                    run_id, current_sender, current_receiver,
                    _strip_connection_line(fr.get("reply_message") or ""),
                    "pre_game"
                )
                if fr.get("connection_score") is not None:
                    pair_log["scores"][current_sender] = fr["connection_score"]
                break

            current_message = reply
            current_sender, current_receiver = current_receiver, current_sender

        pairs_summary.append(pair_log)

    # Advance phase so resume detection works correctly
    gs = storage.read_game_state()
    if gs.get("run_id") == run_id:
        gs["phase"] = "game"
        storage.write_game_state(gs)

    return pairs_summary


# ---------------------------------------------------------------------------
# Phase 2 — game (one agent at a time)
# ---------------------------------------------------------------------------

def act_agent(agent_id: str) -> dict:
    """Run one agent's allocation decision. Returns result dict.

    Reads and updates game_state.json internally.
    """
    game_state = storage.read_game_state()
    run_id       = game_state["run_id"]
    llm_provider = game_state.get("llm_provider")
    llm_model    = game_state.get("llm_model")
    prize_pool   = game_state.get("prize_pool", 0)
    agents_remaining = game_state.get("agents_remaining", 1)

    result = run_pipeline(
        agent_id=agent_id, run_id=run_id,
        phase="game", llm_provider=llm_provider, llm_model=llm_model,
    )

    amount    = max(0, min(result.get("amount") or 0, prize_pool))
    reasoning = result.get("reasoning") or ""
    fair_share = prize_pool / agents_remaining if agents_remaining else 0

    storage.append_allocation(run_id, agent_id, amount, fair_share, reasoning)

    new_pool         = prize_pool - amount
    agents_remaining = max(0, agents_remaining - 1)
    game_state.update({
        "prize_pool":        new_pool,
        "agents_remaining":  agents_remaining,
        "current_turn":      game_state.get("current_turn", 0) + 1,
    })
    if agents_remaining == 0:
        game_state["phase"] = "post_game"
        storage.compute_and_write_scores(run_id)
    storage.write_game_state(game_state)

    return {
        "amount":           amount,
        "reasoning":        reasoning,
        "connection_score": result.get("connection_score"),
        "fair_share":       fair_share,
        "new_pool":         new_pool,
        "agents_remaining": agents_remaining,
    }


# ---------------------------------------------------------------------------
# Phase 3 — post-game discussions
# ---------------------------------------------------------------------------

def run_post_game_phase(game_state: dict) -> list[dict]:
    """Run directed post-game discussions from stored agent requests.

    Logic:
    - Each agent states who they want to talk to + their opening message
      (stored via post_game_init pipeline, no separate generation step).
    - One-sided (A→B only): A's stored message is the opener; B replies
      with LLM; they alternate up to the cap.
    - Mutual (A→B AND B→A): A's stored message is turn 1; B's stored
      message is turn 2 (no extra LLM call); then they alternate with LLM.
    - Per-pair conversation stored in conversations/{run_id}/A_B.json under
      the "post_game" key.
    """
    run_id       = game_state["run_id"]
    llm_provider = game_state.get("llm_provider")
    llm_model    = game_state.get("llm_model")
    agents       = game_state.get("turn_order", [])
    pairs_summary = []

    # Step 1 — collect every agent's choice and opener (no separate message
    # generation: the LLM produces People + Message in post_game_init and
    # we store exactly that message).
    storage.clear_post_game_requests(run_id)
    storage.clear_conversation_phase(run_id, "post_game")

    for agent_id in agents:
        run_pipeline(
            agent_id=agent_id,
            run_id=run_id,
            phase="post_game_init",
            llm_provider=llm_provider,
            llm_model=llm_model,
        )

    run = storage.read_run(run_id)
    requests = run.get("post_game_requests", [])

    # Build a fast lookup: (from, to) → stored message
    requests_map: dict[tuple, str] = {
        (r["from"], r["to"]): r["message"]
        for r in requests
        if r.get("from") and r.get("to") and r.get("message")
    }

    # Step 2 — run each unique pair exactly once
    processed_pairs: set[frozenset] = set()

    for request in requests:
        agent_a = request.get("from") or ""
        agent_b = request.get("to") or ""
        opener_a = request.get("message") or ""
        if not agent_a or not agent_b or not opener_a:
            continue

        pair_key = frozenset([agent_a, agent_b])
        if pair_key in processed_pairs:
            continue
        processed_pairs.add(pair_key)

        # Does B also have a stored message addressed to A?
        opener_b = requests_map.get((agent_b, agent_a))
        mutual = bool(opener_b)

        pair_log = {
            "pair": [agent_a, agent_b],
            "turns": 0,
            "initiator": agent_a,
            "mutual": mutual,
            "message": opener_a,
        }

        # Turn 1 — A's stored opener (no new LLM call)
        storage.append_conversation(run_id, agent_a, agent_b, opener_a, "post_game")
        pair_log["turns"] += 1

        if mutual:
            # Turn 2 — B's stored opener (no new LLM call)
            storage.append_conversation(run_id, agent_b, agent_a, opener_b, "post_game")
            pair_log["turns"] += 1
            current_message  = opener_b
            current_sender   = agent_b
            current_receiver = agent_a
        else:
            current_message  = opener_a
            current_sender   = agent_a
            current_receiver = agent_b

        # Remaining turns — LLM alternation
        while True:
            conv = storage.read_conversation(run_id, agent_a, agent_b)
            if len(conv.get("post_game", [])) >= MAX_POST_GAME_MESSAGES:
                break

            result = run_pipeline(
                agent_id=current_receiver, run_id=run_id,
                phase="post_game_chat", partner_id=current_sender,
                partner_message=current_message,
                llm_provider=llm_provider, llm_model=llm_model,
            )
            reply = result.get("reply_message") or ""
            storage.append_conversation(
                run_id, current_receiver, current_sender, reply, "post_game"
            )
            pair_log["turns"] += 1

            if result.get("wants_to_leave"):
                break

            current_message  = reply
            current_sender, current_receiver = current_receiver, current_sender

        pairs_summary.append(pair_log)

    return pairs_summary


# ---------------------------------------------------------------------------
# Single-pair chat (used by /chat endpoint)
# ---------------------------------------------------------------------------

def send_chat(
    run_id: str,
    from_agent: str,
    to_agent: str,
    message: str,
    phase: str,
    llm_provider: str | None,
    llm_model: str | None,
) -> dict:
    """Persist from_agent's message, run to_agent's reply, persist reply.

    Returns {"reply": str, "leave": bool}
    Raises ValueError on limit violations.
    """
    conv = storage.read_conversation(run_id, from_agent, to_agent)
    existing = conv.get(phase, [])

    if len(existing) >= MAX_MESSAGES:
        raise ValueError("Exchange limit (10) reached for this pair")

    storage.append_conversation(
        run_id, from_agent, to_agent,
        _strip_connection_line(message), phase
    )

    pipeline_phase = "pre_game_chat" if phase == "pre_game" else "post_game_chat"
    result = run_pipeline(
        agent_id=to_agent, run_id=run_id,
        phase=pipeline_phase, partner_id=from_agent,
        partner_message=message,
        llm_provider=llm_provider, llm_model=llm_model,
    )

    reply = result.get("reply_message") or ""
    storage.append_conversation(run_id, to_agent, from_agent, reply, phase)

    # Suppress LEAVE until minimum met
    conv_now = storage.read_conversation(run_id, from_agent, to_agent)
    below_min = phase == "pre_game" and len(conv_now.get("pre_game", [])) < MIN_MESSAGES
    wants_to_leave = bool(result.get("wants_to_leave")) and not below_min

    return {"reply": reply, "leave": wants_to_leave}
