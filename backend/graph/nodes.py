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
) -> str:
    """Build prompt for pre-game pair discussion."""
    context_block = ""
    agent_context = agent_memory.get("context", "").strip()
    if agent_context:
        context_block = f"Personal context:\n{agent_context}\n\n"

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
    return pre_setup + "\n\n" + during


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
        for partner, summary in summaries.items():
            if summary and not any(
                partner in line_text for line_text in lines
            ):
                lines.append(f"With {partner}: {summary}")

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
        state["prompt"] = _build_pre_game_chat_prompt(
            agent_id=agent_id,
            partner_id=partner_id,
            partner_message=partner_message,
            agent_memory=agent_memory,
            conversation_history_text=conversation_history_text,
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
    llm = get_llm()
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
    state["reply_message"] = _normalize_chat_reply(payload)


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
    elif phase in ("pre_game_chat", "post_game_chat"):
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
            # Store overall connection score
            memory.setdefault("connection_scores", {})["overall"] = conn
        storage.write_memory(agent_id, memory)

    elif phase in ("pre_game_chat", "post_game_chat"):
        partner_id = state.get("partner_id") or ""
        if partner_id:
            partner_msg = state.get("partner_message") or ""
            reply = state.get("reply_message") or ""
            summaries = memory.setdefault("conversation_summaries", {})
            prev = summaries.get(partner_id, "")
            new_entry = (
                f"{partner_id}: \"{partner_msg}\" / "
                f"{agent_id}: \"{reply}\""
            )
            summaries[partner_id] = (prev + " | " + new_entry).lstrip(" | ")
            storage.write_memory(agent_id, memory)

    return state
