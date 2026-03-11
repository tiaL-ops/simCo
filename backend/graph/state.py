"""LangGraph state definition for one agent turn."""

from typing import Optional
from typing_extensions import TypedDict


class AgentTurnState(TypedDict):
    # ---- Input (set before graph is invoked) ----
    agent_id: str
    run_id: str
    # Phase: "pre_game_chat" | "game" | "post_game_init" | "post_game_chat"
    phase: str
    # For chat phases only
    partner_id: Optional[str]
    partner_message: Optional[str]

    # ---- Loaded by load_context ----
    game_state: dict
    agent_memory: dict
    # For chat phases: history with partner; for game: all conversations
    conversation_history: list
    # Flat text summary of all partner conversations (for game prompt)
    discussion_summary: str

    # ---- Built by build_prompt ----
    prompt: str

    # ---- Set by call_llm ----
    raw_response: str

    # ---- Parsed by parse_output ----
    amount: Optional[int]           # game phase
    reasoning: Optional[str]        # game phase
    connection_score: Optional[int]  # game phase (1-5)
    reply_message: Optional[str]    # chat phases
