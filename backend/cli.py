#!/usr/bin/env python3
"""SimCo — interactive CLI runner.

Usage:
    cd backend && source .venv/bin/activate
    python cli.py
"""

import os
import sys

from services import storage
from services.runner import (
    init_new_run, run_pre_game_phase, act_agent, run_post_game_phase
)

sys.path.insert(0, os.path.dirname(__file__))


# ── Colour helpers ──────────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def hdr(t):
    print(f"\n{CYAN}{'─'*60}\n  {BOLD}{t}{RESET}\n{CYAN}{'─'*60}{RESET}")


def ok(t):
    print(f"  {GREEN}✓ {t}{RESET}")


def info(t):
    print(f"  {DIM}{t}{RESET}")


def pause(label):
    print(
        f"\n{YELLOW}{'━'*60}\n  ⏸  {BOLD}{label}{RESET}"
        f"\n{YELLOW}{'━'*60}{RESET}"
        )
    input("  Press Enter to continue (Ctrl-C to abort)…")


# ── Default contexts ────────────────────────────────────────────────────────
DEFAULT_CONTEXTS = storage.load_default_contexts()

# ── Default models by provider ──────────────────────────────────────────────
DEFAULT_MODELS_BY_PROVIDER = storage.load_default_models_by_provider()

# ── Predefined turn-order variants ──────────────────────────────────────────
TURN_ORDER_VARIANTS = {
    1: list("ABCDEFGHIJ"),
    2: list("CJGAFHIEDB"),
    3: list("JGHECFIBDA"),
}


# ── Setup prompt ────────────────────────────────────────────────────────────
def prompt_setup() -> dict:
    hdr("SimCo — Experiment Setup")
    providers = ["openai", "gemini", "claude", "grok"]
    for i, p in enumerate(providers, 1):
        print(f"    {i}. {p}")
    c = input("  LLM provider [1]: ").strip() or "1"
    llm_provider = providers[int(c)-1] \
        if c.isdigit() and 1 <= int(c) <= 4 else "openai"

    default_model = DEFAULT_MODELS_BY_PROVIDER.get(llm_provider, "gpt-4o-mini")
    user_model = input(f"  Model [{default_model}]: ").strip()
    # Reject numeric input (user probably typed a number by mistake)
    if user_model and user_model.isdigit():
        print(f"    {YELLOW}⚠ Model names should not be numbers. Using default: {default_model}{RESET}")
        llm_model = default_model
    else:
        llm_model = user_model or default_model

    cond = input("  Condition — 1) neutral  2) emotional [2]: ").strip() or "2"
    condition = "neutral" if cond == "1" else "emotional"

    print("\n  Turn-order variant (10 agents, preset order):")
    print("    1. Standard  : A B C D E F G H I J")
    print("    2. Alternate : C J G A F H I E D B")
    print("    3. Third     : J G H E C F I B D A")
    print("    0. Custom    : specify number of agents manually")
    vsel = input("  Variant [0]: ").strip() or "0"
    if vsel.isdigit() and 1 <= int(vsel) <= 3:
        variant = int(vsel)
        agents = TURN_ORDER_VARIANTS[variant]
    else:
        variant = None
        n = input("  Number of agents (2–10) [3]: ").strip() or "3"
        agents = [
            chr(ord("A") + i)
            for i in range(max(2, min(10, int(n) if n.isdigit() else 3)))
        ]

    contexts = {}
    if condition == "emotional":
        print("\n  Contexts (Enter = use default):")
        for a in agents:
            d = DEFAULT_CONTEXTS.get(a, "")
            v = input(f"    {a} [{d[:55]}…]: ").strip()
            contexts[a] = v or d

    pool_default = len(agents) * 10_000
    p = input(f"  Prize pool [{pool_default:,}]: ").strip()
    prize_pool = int(p.replace(",", "")) if p else pool_default

    return dict(llm_provider=llm_provider, llm_model=llm_model,
                condition=condition, agents=agents,
                prize_pool=prize_pool, contexts=contexts,
                variant=variant)


# ── Pre-game pair completeness check ────────────────────────────────────────
def _pregame_incomplete_pairs(run_id: str, agents: list) -> list:
    """Return list of (agentA, agentB, msg_count) for pairs that haven't
    finished pre-game (i.e. fewer than 2 messages stored).
    """
    import itertools
    incomplete = []
    for a, b in itertools.combinations(agents, 2):
        conv = storage.read_conversation(run_id, a, b)
        count = len(conv.get("pre_game", []))
        if count < 2:
            incomplete.append((a, b, count))
    return incomplete


# ── Resume / redo existing run ───────────────────────────────────────────────
def offer_resume() -> "tuple[dict, str] | None":
    """If game_state.json has a run_id, offer to resume or redo it.
    Returns (game_state, start_phase) or None to start a new run.
    """
    try:
        gs = storage.read_game_state()
    except Exception:
        return None
    if not gs.get("run_id"):
        return None

    run_id = gs["run_id"]
    stored_phase = gs.get("phase", "pre_game")

    run_data = storage.read_run(run_id)
    has_scores = bool(run_data.get("connection_scores"))
    has_allocs = bool(run_data.get("allocations"))
    has_post = stored_phase == "post_game"

    # Determine completion status and sensible default
    if has_allocs and has_post:
        completed = True
        auto_phase = "pre_game"   # redo from scratch by default
    elif has_allocs:
        completed = False
        auto_phase = "post_game"
    elif has_scores or stored_phase == "game":
        completed = False
        auto_phase = "game"
    else:
        completed = False
        auto_phase = "pre_game"

    status_parts = []
    if has_scores:
        status_parts.append(
            f"{len(run_data['connection_scores'])} connection scores"
            )
    if has_allocs:
        status_parts.append(
            f"{len(run_data['allocations'])} allocations"
            )
    status = "  |  " + ", ".join(status_parts) if status_parts else ""

    label = "Redo completed run?" if completed else "Resume existing run?"
    hdr(label)
    info(f"Run     : {run_id}")
    info(f"Phase   : {stored_phase}{status}")
    info(
        f"Agents  : {', '.join(gs.get('turn_order', []))}  "
        f"|  Pool: ${gs.get('prize_pool', 0):,}"
        )

    # Pre-game completeness check — show any pairs that never fully talked
    agents = gs.get("turn_order", [])
    if agents:
        missing = _pregame_incomplete_pairs(run_id, agents)
        if missing:
            print(f"\n  {YELLOW}⚠  Pre-game incomplete pairs:{RESET}")
            for a, b, n in missing:
                if n == 0:
                    print(f"    {a}↔{b}  — not started")
                else:
                    print(f"    {a}↔{b}  — only {n} message{'s' if n != 1 else ''} (abruptly stopped)")
            print(f"  {DIM}(resume from 'pre_game' to re-run these pairs){RESET}")

    prompt = "\n  Redo? [Y/n]: " if completed else "\n  Resume? [Y/n]: "
    c = input(prompt).strip().lower()
    if c in ("n", "no"):
        return None

    phases = ["pre_game", "game", "post_game"]
    print("\n  Start from which phase?")
    for i, p in enumerate(phases, 1):
        tag = " ← default" if p == auto_phase else ""
        print(f"    {i}. {p}{tag}")
    sel = input(f"  [Enter = {auto_phase}]: ").strip()
    if sel.isdigit() and 1 <= int(sel) <= len(phases):
        start_phase = phases[int(sel) - 1]
    else:
        start_phase = auto_phase

    return gs, start_phase


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{BOLD}{CYAN}  SimCo — Social Connection Experiment{RESET}")
    start_phase = "pre_game"
    try:
        resume = offer_resume()
        if resume is not None:
            game_state, start_phase = resume
            ok(
                f"Resuming {BOLD}{game_state['run_id']}{RESET}"
                f" from phase: {start_phase}"
                )
        else:
            cfg = prompt_setup()
            hdr("PHASE 0 — New Run")
            game_state = init_new_run(**cfg)
            ok(f"Run created: {BOLD}{game_state['run_id']}{RESET}")
            info(
                f"Agents: {', '.join(game_state['turn_order'])}  "
                f"|  Pool: ${game_state['prize_pool']:,}"
                )
            pause("Run ready — about to start pre-game discussions")
    except (KeyboardInterrupt, EOFError):
        print("\n  Aborted.")
        return

    try:
        # Phase 1 — pre-game
        if start_phase == "pre_game":
            hdr("PHASE 1 — Pre-Game Discussions")
            pairs = run_pre_game_phase(game_state)
            for p in pairs:
                a, b = p["pair"]
                scores = "  ".join(
                    f"{k}→{b if k==a else a}: {v}/5"
                    for k, v in p["scores"].items()
                    )
                ok(f"{a}↔{b}  {p['turns']} turns  |  {scores or 'no scores'}")
            pause("Pre-game done — about to run game (allocation decisions)")

        # Phase 2 — game
        if start_phase in ("pre_game", "game"):
            hdr("PHASE 2 — Game")
            # When explicitly redoing game phase, reset turn counters
            if start_phase == "game":
                n = len(game_state["turn_order"])
                orig_pool = game_state.get("initial_prize_pool") or n * 10_000
                game_state["current_turn"] = 0
                game_state["agents_remaining"] = n
                game_state["prize_pool"] = orig_pool
                game_state["phase"] = "game"
                storage.write_game_state(game_state)
            current_turn = game_state.get("current_turn", 0)
            for agent_id in game_state["turn_order"][current_turn:]:
                r = act_agent(agent_id)
                print(f"  {BOLD}{agent_id}{RESET}  took ${r['amount']:>8,}  "
                      f"(fair ${r['fair_share']:,.0f})")
                info(f"    {r['reasoning'][:100]}")
            pause("Game done — about to start post-game discussions")

        # Phase 3 — post-game
        if start_phase in ("pre_game", "game", "post_game"):
            hdr("PHASE 3 — Post-Game Discussions")
            post_pairs = run_post_game_phase(game_state)
            for p in post_pairs:
                tag = "⟷ mutual" if p.get("mutual") else "→ one-sided"
                ok(
                    f"{p['initiator']} → {p['pair'][1]}  "
                    f"[{tag}]  {p['turns']} turns"
                    )
                info(f"    {p['message'][:100]}")
            pause("Post-game done — results below")

        # Results
        hdr("RESULTS")
        run = storage.read_run(game_state["run_id"])
        scores = storage.read_scores(game_state["run_id"])
        print(f"\n  {BOLD}Allocations:{RESET}")
        for a in run.get("allocations", []):
            print(f"    {a['agent']}  ${a['taken']:>8,}  g_k={a['g_k']:.2f}")
        print(f"\n  {BOLD}Connection scores:{RESET}")
        for cs in run.get("connection_scores", []):
            print(f"    {cs['from']} → {cs['to']} : {cs['score']}/5")
        print(f"\n  {BOLD}Post-game requests:{RESET}")
        for req in run.get("post_game_requests", []):
            print(f"    {req['from']} → {req['to']} : {req['message']}")
        print(f"\n  {BOLD}Gini:{RESET} {scores.get('gini', 'N/A')}")
        ok(
            f"All data saved under backend/data/  "
            f"(run: {game_state['run_id']})"
            )

    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}  Run interrupted. Partial data saved.{RESET}")


if __name__ == "__main__":
    main()
