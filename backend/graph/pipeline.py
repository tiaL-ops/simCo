"""LangGraph pipeline: assembles and compiles the per-agent-turn graph.

Graph:
    Node order:
    (1) load_context
    (2) build_prompt
    (3) call_llm
    (4) parse_output
    (5) update_memory
    (6) END

The pipeline is stateless — all persistence is handled by the nodes via
the storage service.
"""

from langgraph.graph import StateGraph, END

from graph.state import AgentTurnState
from graph.nodes import (
    load_context,
    build_prompt,
    call_llm,
    parse_output,
    update_memory,
)

# Build once at import time; thread-safe for Flask's development server.
_graph = StateGraph(AgentTurnState)
_graph.add_node("load_context", load_context)
_graph.add_node("build_prompt", build_prompt)
_graph.add_node("call_llm", call_llm)
_graph.add_node("parse_output", parse_output)
_graph.add_node("update_memory", update_memory)

_graph.set_entry_point("load_context")
_graph.add_edge("load_context", "build_prompt")
_graph.add_edge("build_prompt", "call_llm")
_graph.add_edge("call_llm", "parse_output")
_graph.add_edge("parse_output", "update_memory")
_graph.add_edge("update_memory", END)

compiled_graph = _graph.compile()


def run_pipeline(
    agent_id: str,
    run_id: str,
    phase: str,
    partner_id: str | None = None,
    partner_message: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> AgentTurnState:
    """Run the full pipeline for one agent turn.

    Args:
        agent_id:        The agent acting this turn.
        run_id:          Current run identifier.
        phase:           One of "pre_game_chat", "game", "post_game_init",
                         "post_game_chat".
        partner_id:      Required for chat phases.
        partner_message: The incoming message for chat phases.
        llm_provider:    Provider from UI (openai/claude/gemini/grok).
        llm_model:       Provider-specific model id from UI.

    Returns:
        The final AgentTurnState with all fields populated.
    """
    initial: AgentTurnState = {
        "agent_id": agent_id,
        "run_id": run_id,
        "phase": phase,
        "partner_id": partner_id,
        "partner_message": partner_message,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        # Fields populated by nodes
        "game_state": {},
        "agent_memory": {},
        "conversation_history": [],
        "discussion_summary": "",
        "prompt": "",
        "raw_response": "",
        "amount": None,
        "reasoning": None,
        "connection_score": None,
        "reply_message": None,
    }
    result = compiled_graph.invoke(initial)
    return result
