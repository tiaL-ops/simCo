"""LangGraph nodes for the per-agent-turn pipeline.

Node order:
    (1) load_context
    (2) build_prompt
    (3) call_llm
    (4) parse_output
    (5) update_memory
"""

import re
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate


from services import storage
from services.llm import ask_llm, get_llm
from graph.state import AgentTurnState

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_template(name: str) -> ChatPromptTemplate:
    """Load a .txt prompt file and return a ChatPromptTemplate."""
    path = PROMPTS_DIR / f"{name}.txt"
    text = path.read_text(encoding="utf-8").strip()
    return ChatPromptTemplate.from_template(text)


def _render(template: ChatPromptTemplate, **kwargs: str) -> str:
    """Render a ChatPromptTemplate to a plain string
    (HumanMessage content)."""
    messages = template.format_messages(**kwargs)
    return messages[0].content


def _format_conversation_history(conversation_history: list[dict]) -> str:
    """Format turn history into readable prompt text."""
    history_lines = [
        f"Turn {m['turn']} - {m['from']}: {m['message']}"
        for m in conversation_history
    ]
    return "\n".join(history_lines) if history_lines \
        else "(No previous exchange)"


def _build_pre_game_chat_prompt(
    agent_id: str,
    partner_id: str,
    partner_message: str,
    agent_memory: dict,
    conversation_history_text: str,
    is_final: bool = False,
) -> str:
    """Build prompt for pre-game pair discussion."""
    agent_context = agent_memory.get("context", "").strip()

    identity = _render(
        _load_template("agents_definition"),
        agent_name=agent_id,
        context=agent_context or "No special context.",
    )
    context_block = f"Personal context:\n{agent_context}\n\n" if agent_context else ""
    pre_setup = _render(
        _load_template("pre_discussion"),
        context_block=context_block,
    )
    during = _render(
        _load_template("during_pre_game"),
        partner_id=partner_id,
        agent_id=agent_id,
        conversation_history=conversation_history_text,
        partner_message=partner_message,
    )
    prompt = identity + "\n\n" + pre_setup + "\n\n" + during
    if is_final:
        prompt += (
            f"\n\nThis is your last exchange with {partner_id}. "
            f"After your reply, rate your connection:\n"
            f"Connection_to_{partner_id}_from_{agent_id}: [1-5]"
        )
    return prompt


def _build_pre_game_first_msg_prompt(
    agent_id: str,
    partner_id: str,
    agent_memory: dict,
) -> str:
    """Build prompt for agent-initiated opening message (no prior exchange)."""
    agent_context = agent_memory.get("context", "").strip()

    identity = _render(
        _load_template("agents_definition"),
        agent_name=agent_id,
        context=agent_context or "No special context.",
    )
    context_block = f"Personal context:\n{agent_context}\n\n" if agent_context else ""
    pre_setup = _render(
        _load_template("pre_discussion"),
        context_block=context_block,
    )
    first_msg = _render(
        _load_template("first_message_pre_game"),
        partner_id=partner_id,
        agent_id=agent_id,
    )
    return identity + "\n\n" + pre_setup + "\n\n" + first_msg


def _is_final_exchange(
    run_id: str, agent_id: str, partner_id: str, phase_key: str
) -> bool:
    """Return True if this is the last allowed exchange for this pair."""
    conv = storage.read_conversation(run_id, agent_id, partner_id)
    # 20 messages total = 10 per side; after this reply it will be full.
    return len(conv.get(phase_key, [])) >= 19


def _build_game_prompt(
    game_state: dict,
    agent_memory: dict,
    discussion_summary: str,
) -> str:
    """Build prompt for allocation decision during the game phase."""
    prize_pool = game_state.get("prize_pool", 0)
    agents_remaining = game_state.get("agents_remaining", 1)
    fair_share = round(prize_pool / agents_remaining, 2) \
        if agents_remaining else 0

    condition = game_state.get("condition", "neutral")
    condition_context = (
        "neutral — no personal context"
        if condition == "neutral"
        else agent_memory.get("context", "neutral — no personal context")
    )

    return _render(
        _load_template("game_decision"),
        remaining_agents=str(agents_remaining),
        prize_pool=f"{prize_pool:,}",
        fair_share=f"{fair_share:,.2f}",
        condition_context=condition_context,
        discussion_summary=discussion_summary or "None",
    )


def _build_post_game_init_prompt(run_id: str) -> str:
    """Build prompt for post-game initial reflection."""
    run = storage.read_run(run_id)
    allocations = run.get("allocations", [])
    rows = [
        (
            (
                f"  {a['agent']}: took ${a['taken']:,} "
                f"(fair share was ${a['fair_share']:,}, g_k={a['g_k']})"
            )
        )
        for a in allocations
    ]
    results_table = "\n".join(rows) if rows else "No results yet."
    return _render(
        _load_template("post_game_init"),
        results_table=results_table,
    )


def _build_post_game_chat_prompt(
    run_id: str,
    agent_id: str,
    partner_id: str,
    partner_message: str,
    conversation_history_text: str,
) -> str:
    """Build prompt for post-game pair discussion."""
    run = storage.read_run(run_id)
    allocations = {
        a["agent"]: a["taken"] for a in run.get("allocations", [])
        }
    agent_amount = allocations.get(agent_id, 0)
    partner_amount = allocations.get(partner_id, 0)

    return _render(
        _load_template("during_post_game"),
        partner_id=partner_id,
        agent_id=agent_id,
        conversation_history=conversation_history_text,
        partner_amount=f"{partner_amount:,}",
        agent_amount=f"{agent_amount:,}",
        partner_message=partner_message,
    )


def _build_summary_conv_prompt(
    your_id_connection: str,
    conversation: str,
) -> str:
    """Build prompt for global pre-game social reflection."""
    return _render(
        _load_template("summary_conv"),
        yourID_connection=your_id_connection,
        conversation=conversation,
    )


# ---------------------------------------------------------------------------
# Node 1 — load_context
# ---------------------------------------------------------------------------

def load_context(state: AgentTurnState) -> AgentTurnState:
    """Load game_state, agent memory, and relevant conversation history."""
    agent_id = state["agent_id"]
    run_id = state["run_id"]
    phase = state["phase"]

    game_state = storage.read_game_state()
    agent_memory = storage.read_memory(agent_id)

    conversation_history: list = []
    discussion_summary = ""

    if phase in ("pre_game_chat", "post_game_chat"):
        partner_id = state.get("partner_id", "")
        if partner_id:
            conv = storage.read_conversation(
                run_id, agent_id, partner_id
                )
            phase_key = "pre_game" if phase == "pre_game_chat" else "post_game"
            conversation_history = conv.get(phase_key, [])

    elif phase == "game":
        # Collect all conversations this agent has had (pre-game)
        all_convs = storage.get_all_agent_conversations(run_id, agent_id)
        lines = []
        for conv in all_convs:
            pair = conv.get("pair", [])
            partner = next((p for p in pair if p != agent_id), "")
            pre = conv.get("pre_game", [])
            if pre:
                excerpt = " | ".join(
                    f"{m['from']}: {m['message']}" for m in pre[-4:]
                )
                lines.append(f"With {partner}: {excerpt}")

        # Also include stored summaries from memory
        summaries = agent_memory.get("conversation_summaries", {})
        overall_summary = summaries.get("overall_pre_game", "")
        if overall_summary:
            lines.append(f"Overall social reflection: {overall_summary}")

        # Include partner ranking from pre-game connection scores.
        scores = agent_memory.get("connection_scores", {})
        ranked = sorted(
            [
                (partner, score)
                for partner, score in scores.items()
                if partner != "overall" and isinstance(score, (int, float))
            ],
            key=lambda item: item[1],
            reverse=True,
        )
        if ranked:
            ranking_text = ", ".join(
                f"{partner}({int(score)})" for partner, score in ranked
            )
            lines.append(f"Connection ranking: {ranking_text}")

        discussion_summary = "\n".join(lines) if lines \
            else "No prior discussions."
        conversation_history = []

    state["game_state"] = game_state
    state["agent_memory"] = agent_memory
    state["conversation_history"] = conversation_history
    state["discussion_summary"] = discussion_summary
    return state


# ---------------------------------------------------------------------------
# Node 2 — build_prompt
# ---------------------------------------------------------------------------

def build_prompt(state: AgentTurnState) -> AgentTurnState:
    """Dispatch prompt creation to a phase-specific builder."""
    phase = state["phase"]
    agent_id = state["agent_id"]
    partner_id = state.get("partner_id") or ""
    partner_message = state.get("partner_message") or ""
    game_state = state["game_state"]
    agent_memory = state["agent_memory"]

    conversation_history_text = _format_conversation_history(
        state.get("conversation_history", [])
    )

    if phase == "pre_game_chat":
        # Check if this is the final exchange — only then ask for rating.
        is_final = _is_final_exchange(
            state["run_id"], agent_id, partner_id, "pre_game"
        )
        state["prompt"] = _build_pre_game_chat_prompt(
            agent_id=agent_id,
            partner_id=partner_id,
            partner_message=partner_message,
            agent_memory=agent_memory,
            conversation_history_text=conversation_history_text,
            is_final=is_final,
        )
    elif phase == "pre_game_first_msg":
        state["prompt"] = _build_pre_game_first_msg_prompt(
            agent_id=agent_id,
            partner_id=partner_id,
            agent_memory=agent_memory,
        )
    elif phase == "game":
        state["prompt"] = _build_game_prompt(
            game_state=game_state,
            agent_memory=agent_memory,
            discussion_summary=state.get("discussion_summary") or "None",
        )
    elif phase == "post_game_init":
        state["prompt"] = _build_post_game_init_prompt(
            run_id=state["run_id"],
        )
    elif phase == "post_game_chat":
        state["prompt"] = _build_post_game_chat_prompt(
            run_id=state["run_id"],
            agent_id=agent_id,
            partner_id=partner_id,
            partner_message=partner_message,
            conversation_history_text=conversation_history_text,
        )
    else:
        state["prompt"] = ""

    return state


# ---------------------------------------------------------------------------
# Node 3 — call_llm
# ---------------------------------------------------------------------------

def call_llm(state: AgentTurnState) -> AgentTurnState:
    """Send prompt to the configured LLM and store the raw response."""
    llm = get_llm(
        provider=state.get("llm_provider"),
        model=state.get("llm_model"),
    )
    raw = ask_llm(llm, state["prompt"])
    state["raw_response"] = raw
    return state


# ---------------------------------------------------------------------------
# Node 4 — parse_output
# ---------------------------------------------------------------------------

def _reset_output_fields(state: AgentTurnState) -> None:
    """Reset output fields before parsing a new LLM response."""
    state["amount"] = None
    state["reasoning"] = None
    state["connection_score"] = None
    state["reply_message"] = None


def _parse_game_output(state: AgentTurnState, raw: str) -> None:
    """Parse game-phase response into amount/reasoning/connection score."""
    amount_match = re.search(r"Amount:\s*([\d,]+)", raw, re.IGNORECASE)
    if amount_match:
        state["amount"] = int(amount_match.group(1).replace(",", ""))

    reasoning_match = re.search(
        r"Reasoning:\s*(.*?)(?:\n|Connection|$)",
        raw,
        re.IGNORECASE | re.DOTALL,
    )
    if reasoning_match:
        state["reasoning"] = reasoning_match.group(1).strip()

    conn_match = re.search(
        r"Connection to others.*?:\s*([1-5])", raw, re.IGNORECASE
    )
    if conn_match:
        state["connection_score"] = int(conn_match.group(1))


def _strip_connection_line(text: str) -> str:
    """Remove any Connection_to_...from_... scoring line from chat text."""
    return re.sub(
        r"\s*Connection_to_\S+_from_\S+\s*:\s*[1-5]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()


def _parse_chat_output(state: AgentTurnState, raw: str) -> None:
    """Parse pre/post-game chat response into reply_message."""
    agent_id = state["agent_id"]
    partner_id = state.get("partner_id") or ""
    pattern = (
        rf"Answer_to_{re.escape(partner_id)}_from_"
        rf"{re.escape(agent_id)}:\s*(.*)"
    )
    match = re.search(pattern, raw, re.IGNORECASE | re.DOTALL)
    payload = match.group(1).strip() if match else raw.strip()
    # Always extract connection score before stripping it from the reply.
    conn_match = re.search(
        rf"Connection_to_{re.escape(partner_id)}_from_"
        rf"{re.escape(agent_id)}\s*:\s*([1-5])",
        payload,
        re.IGNORECASE,
    )
    if not conn_match:
        conn_match = re.search(r"Connection\s*[:\-]\s*([1-5])", payload, re.IGNORECASE)
    if conn_match:
        state["connection_score"] = int(conn_match.group(1))
    # Strip the connection line so it never appears in stored chat messages.
    state["reply_message"] = _normalize_chat_reply(_strip_connection_line(payload))


def _normalize_chat_reply(text: str) -> str:
    """Normalize model formatting artifacts in chat replies."""
    cleaned = text.strip()

    # Some models echo placeholders like "[answer]".
    cleaned = re.sub(
        r"^\s*\[\s*answer\s*\]\s*", "",
        cleaned,
        flags=re.IGNORECASE
        )
    cleaned = re.sub(
        r"^\s*answer\s*[:\-]\s*", "",
        cleaned,
        flags=re.IGNORECASE
    )

    # If the whole reply is wrapped in one pair of brackets, unwrap it.
    if cleaned.startswith("[") and cleaned.endswith("]") and len(cleaned) > 1:
        cleaned = cleaned[1:-1].strip()

    # If a stray leading bracket remains (common malformed output), drop it.
    if cleaned.startswith("[") and "]" not in cleaned:
        cleaned = cleaned[1:].strip()

    return cleaned


def _parse_post_game_init_output(state: AgentTurnState, raw: str) -> None:
    """Parse post-game-init output; keep raw response as reply_message."""
    state["reply_message"] = raw.strip()


def parse_output(state: AgentTurnState) -> AgentTurnState:
    """Dispatch output parsing to a phase-specific parser."""
    raw = state.get("raw_response", "")
    phase = state["phase"]

    _reset_output_fields(state)

    if phase == "game":
        _parse_game_output(state, raw)
    elif phase in ("pre_game_chat", "pre_game_first_msg", "post_game_chat"):
        _parse_chat_output(state, raw)
    elif phase == "post_game_init":
        _parse_post_game_init_output(state, raw)

    return state


# ---------------------------------------------------------------------------
# Node 5 — update_memory
# ---------------------------------------------------------------------------

def update_memory(state: AgentTurnState) -> AgentTurnState:
    """Persist relevant fields back to memory/{agent_id}.json."""
    agent_id = state["agent_id"]
    phase = state["phase"]
    memory = storage.read_memory(agent_id)

    if phase == "game":
        conn = state.get("connection_score")
        if conn is not None:
            # Store overall game-phase connection score
            memory.setdefault("connection_scores", {})["overall"] = conn
        storage.write_memory(agent_id, memory)

    elif phase in ("pre_game_chat", "pre_game_first_msg", "post_game_chat"):
        partner_id = state.get("partner_id") or ""
        if partner_id:
            partner_msg = state.get("partner_message") or ""
            reply = state.get("reply_message") or ""
            conn = state.get("connection_score")

            # Save per-partner connection score during pre-game phases.
            if phase in ("pre_game_chat", "pre_game_first_msg") and conn is not None:
                memory.setdefault("connection_scores", {})[partner_id] = conn

            # For first-msg phase there is no conversation yet — skip summary.
            if phase == "pre_game_first_msg":
                storage.write_memory(agent_id, memory)
                return state

            summaries = memory.setdefault("conversation_summaries", {})

            connection_scores = memory.get("connection_scores", {})
            ranked = sorted(
                [
                    (pid, score)
                    for pid, score in connection_scores.items()
                    if pid != "overall" and isinstance(score, (int, float))
                ],
                key=lambda item: item[1],
                reverse=True,
            )
            score_lines = [
                f"- {pid}: {int(score)}/5" for pid, score in ranked
            ]

            all_convs = storage.get_all_agent_conversations(
                state["run_id"],
                agent_id,
            )
            transcript_blocks = []
            for conv in all_convs:
                pair = conv.get("pair", [])
                pid = next((p for p in pair if p != agent_id), "")
                pre_turns = conv.get("pre_game", [])
                if not pre_turns:
                    continue
                turns_text = " | ".join(
                    f"{m.get('from', '')}: {m.get('message', '')}"
                    for m in pre_turns
                )
                transcript_blocks.append(f"- With {pid}: {turns_text}")

            global_context = (
                "Connection scores by partner:\n"
                + ("\n".join(score_lines) if score_lines else "- none yet")
            )

            conversation_context = (
                "Pre-game conversation transcripts:\n"
                + ("\n".join(transcript_blocks) if transcript_blocks else "- none yet")
            )

            summary_prompt = _build_summary_conv_prompt(
                your_id_connection=global_context,
                conversation=conversation_context,
            )

            llm = get_llm(
                provider=state.get("llm_provider"),
                model=state.get("llm_model"),
            )
            summary = ask_llm(llm, summary_prompt).strip()

            if summary:
                summaries["overall_pre_game"] = summary

            # Keep only the global pre-game summary key.
            memory["conversation_summaries"] = {
                "overall_pre_game": summaries.get("overall_pre_game", "")
            }

            storage.write_memory(agent_id, memory)

    return state
