#!/usr/bin/env python3
"""SimCo — interactive CLI runner.

Usage:
    cd backend && source .venv/bin/activate
    python cli.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from services import storage
from services.runner import new_run, run_pre_game_phase, act_agent, run_post_game_phase

# ── Colour helpers ──────────────────────────────────────────────────────────
BOLD = "\033[1m"; DIM = "\033[2m"; CYAN = "\033[96m"
GREEN = "\033[92m"; YELLOW = "\033[93m"; RESET = "\033[0m"

def hdr(t):  print(f"\n{CYAN}{'─'*60}\n  {BOLD}{t}{RESET}\n{CYAN}{'─'*60}{RESET}")
def ok(t):   print(f"  {GREEN}✓ {t}{RESET}")
def info(t): print(f"  {DIM}{t}{RESET}")

def pause(label):
    print(f"\n{YELLOW}{'━'*60}\n  ⏸  {BOLD}{label}{RESET}\n{YELLOW}{'━'*60}{RESET}")
    input(f"  Press Enter to continue (Ctrl-C to abort)…")

# ── Default contexts ────────────────────────────────────────────────────────
DEFAULT_CONTEXTS = {
    "A": "You lately have been evicted from your house and you and your family of 3 have nowhere to go. You found a house, affordable for your family and manageable, but the price of the deposit is high: you need 30 000$ for the deposit and for two months rent.",
    
    "B": "Your little girl, first born, three years old, needs surgery, but you have no health insurance. After taking many loans and selling many assets, three months later you still need 25 000$.",
    
    "C": "You got laid off from your finance job. You are the only source of income for your family of five. You have no savings, and are in the middle of searching for another job. You need about 5000$ to support you and your family for a month.",
    
    "D": "Your elderly parents rely on you financially, and you need to pay for the increasing medical bill. You are still short 15 000$ to afford the medical bill.",
    
    "E": "You love playing games, you are curious about the game and want to try your luck. You love to win!",
    
    "F": "You are rich and have accumulated significant wealth, and you are financially stable. Your vision board includes a holiday in Japan, the cost will be 10 000$ for a perfect week of your dream.",
    
    "G": "You just lost 20 000$ investing in the stock market yesterday. Although you knew that was a risk you want that money back somehow.",
    
    "H": "You expect to pay your loan in the next upcoming month and you have started planning ahead, yet you hope someone can just give you 25 000$ to forget about it.",
    
    "I": "You have savings that make you feel comfortable for unforeseen events.",
    
    "J": "You have been thinking about buying a new car, your favorite one costs 45 000$ and you are telling yourself if you win the lottery, that is the first thing you want to do."
}

# ── Setup prompt ────────────────────────────────────────────────────────────
def prompt_setup() -> dict:
    hdr("SimCo — Experiment Setup")
    providers = ["openai", "gemini", "claude", "grok"]
    for i, p in enumerate(providers, 1): print(f"    {i}. {p}")
    c = input("  LLM provider [1]: ").strip() or "1"
    llm_provider = providers[int(c)-1] if c.isdigit() and 1 <= int(c) <= 4 else "openai"

    defaults = {"openai":"gpt-4o-mini","gemini":"gemini-2.0-flash",
                "claude":"claude-3-5-haiku-20241022","grok":"grok-3-mini-fast-beta"}
    default_model = defaults.get(llm_provider, "gpt-4o-mini")
    llm_model = input(f"  Model [{default_model}]: ").strip() or default_model

    cond = input("  Condition — 1) neutral  2) emotional [2]: ").strip() or "2"
    condition = "neutral" if cond == "1" else "emotional"

    n = input("  Number of agents (2–10) [3]: ").strip() or "3"
    agents = [chr(ord("A") + i) for i in range(max(2, min(10, int(n) if n.isdigit() else 3)))]

    contexts = {}
    if condition == "emotional":
        print(f"\n  Contexts (Enter = use default):")
        for a in agents:
            d = DEFAULT_CONTEXTS.get(a, "")
            v = input(f"    {a} [{d[:55]}…]: ").strip()
            contexts[a] = v or d

    pool_default = len(agents) * 10_000
    p = input(f"  Prize pool [{pool_default:,}]: ").strip()
    prize_pool = int(p.replace(",", "")) if p else pool_default

    return dict(llm_provider=llm_provider, llm_model=llm_model,
                condition=condition, agents=agents,
                prize_pool=prize_pool, contexts=contexts)

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
    has_scores  = bool(run_data.get("connection_scores"))
    has_allocs  = bool(run_data.get("allocations"))
    has_post    = stored_phase == "post_game"

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
    if has_scores:  status_parts.append(f"{len(run_data['connection_scores'])} connection scores")
    if has_allocs:  status_parts.append(f"{len(run_data['allocations'])} allocations")
    status = "  |  " + ", ".join(status_parts) if status_parts else ""

    label = "Redo completed run?" if completed else "Resume existing run?"
    hdr(label)
    info(f"Run     : {run_id}")
    info(f"Phase   : {stored_phase}{status}")
    info(f"Agents  : {', '.join(gs.get('turn_order', []))}  |  Pool: ${gs.get('prize_pool', 0):,}")

    prompt = "\n  Redo? [Y/n]: " if completed else "\n  Resume? [Y/n]: "
    c = input(prompt).strip().lower()
    if c in ("n", "no"):
        return None

    phases = ["pre_game", "game", "post_game"]
    print(f"\n  Start from which phase?")
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
            ok(f"Resuming {BOLD}{game_state['run_id']}{RESET} from phase: {start_phase}")
        else:
            cfg = prompt_setup()
            hdr("PHASE 0 — New Run")
            game_state = new_run(**cfg)
            ok(f"Run created: {BOLD}{game_state['run_id']}{RESET}")
            info(f"Agents: {', '.join(game_state['turn_order'])}  |  Pool: ${game_state['prize_pool']:,}")
            pause("Run ready — about to start pre-game discussions")
    except (KeyboardInterrupt, EOFError):
        print("\n  Aborted."); return

    try:
        # Phase 1 — pre-game
        if start_phase == "pre_game":
            hdr("PHASE 1 — Pre-Game Discussions")
            pairs = run_pre_game_phase(game_state)
            for p in pairs:
                a, b = p["pair"]
                scores = "  ".join(f"{k}→{b if k==a else a}: {v}/5" for k, v in p["scores"].items())
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
                ok(f"{p['initiator']} → {p['pair'][1]}  [{tag}]  {p['turns']} turns")
                info(f"    {p['message'][:100]}")
            pause("Post-game done — results below")

        # Results
        hdr("RESULTS")
        run    = storage.read_run(game_state["run_id"])
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
        ok(f"All data saved under backend/data/  (run: {game_state['run_id']})")

    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}  Run interrupted. Partial data saved.{RESET}")

if __name__ == "__main__":
    main()

