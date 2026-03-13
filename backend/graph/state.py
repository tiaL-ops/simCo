"""LangGraph state definition for one agent turn."""

from typing import Optional
from typing_extensions import TypedDict


class GameState(TypedDict, total=False):
    """Canonical persisted overall game state schema loaded from storage."""
    run_id: str
    phase: str
    condition: str
    prize_pool: int
    initial_prize_pool: int
    turn_order: list[str]
    current_turn: int
    agents_remaining: int
    llm_provider: Optional[str]
    llm_model: Optional[str]


class AgentTurnState(TypedDict):
    """State passed through LangGraph for one agent turn."""
    # ---- Input (set before graph is invoked) ----
    agent_id: str
    run_id: str
    # Phase: "pre_game_chat" | "game" | "post_game_init" | "post_game_chat"
    phase: str
    # For chat phases only
    partner_id: Optional[str]
    partner_message: Optional[str]

    # LLM selection from Phaser UI
    llm_provider: Optional[str]
    llm_model: Optional[str]

    # ---- Loaded by load_context ----
    game_state: GameState
    agent_memory: dict
    # For chat phases: history with partner; for game: all conversations
    conversation_history: list[dict]
    # Flat text summary of all partner conversations (for game prompt)
    discussion_summary: str

    # ---- Built by build_prompt ----
    prompt: str

    # ---- Set by call_llm ----
    raw_response: str

    # ---- Parsed by parse_output ----
    amount: Optional[int]           # game phase
    reasoning: Optional[str]        # game phase
    connection_score: Optional[int]  # game or pre_game_chat (1-5)
    reply_message: Optional[str]    # chat phases
    wants_to_leave: Optional[bool]  # pre_game_chat: agent signals end of conversation
    is_final: Optional[bool]        # pre_game_chat: hard-cap turn (max 10 per side)
    post_game_targets: list[str]    # post_game_init: chosen recipients
    post_game_request_message: Optional[str]  # post_game_init: opener sent to recipients
