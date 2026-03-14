#!/usr/bin/env python3
"""Test script for SimCo backend — memories and endpoints.

Runs a complete mini-simulation with 3 agents:
  1. POST /new-run       — initialise a fresh run
  2. GET  /state         — verify game state
  3. POST /chat (x2)     — pre-game exchanges between A↔B and A↔C
  4. POST /act  (x3)     — each agent takes from the pool
  5. GET  /results       — verify allocations + scores
  6. POST /chat (x1)     — post-game exchange between A↔B
  7. Inspect memory file — verify summaries and connection scores

Usage:
  # Start the Flask server first (in another terminal):
  #   cd backend && python app.py

  python test_endpoints.py [--base-url http://127.0.0.1:5000]
    python test_endpoints.py --only pre_game_chat

Set the env var before starting the server, e.g.:
  OPENAI_API_KEY=sk-... python app.py
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

from services import storage

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# Basic config for the test run; these can be overridden by command-line args.
AGENTS = ["A", "B", "C"]
PRIZE_POOL = 30_000  # 10 000 per agent as fair share


EMOTIONAL_CONTEXTS = {
    "A": (
        "You lately have been evicted to your house"
        "and you and your family of 3  has nowhere to go"
    ),
    "B": (
        "Your little girl , first born, 3 years old , need surgery,"
        "but you have no insurance",
    ),
    "C": (
        "You got laid off from your finance job."
        "The only source of income of your family",
    )
}

DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# These functions call the API and print results in a readable format.
def api(base: str, method: str, path: str, **kwargs):
    url = base.rstrip("/") + path
    resp = getattr(requests, method)(url, **kwargs)
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    return resp.status_code, body


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print("=" * 60)


def show(label: str, status: int, body):
    ok = "✓" if 200 <= status < 300 else "✗"
    print(f"\n[{ok}] {label}  →  HTTP {status}")
    print(
        json.dumps(body, indent=2)
        if isinstance(body, (dict, list))
        else body
        )


# ---------------------------------------------------------------------------
# Test functions
# ---------------------------------------------------------------------------

def test_new_run(base: str, condition: str):
    section("1. POST /new-run")
    status, body = api(
        base, "post", "/new-run",
        json={
            "llm_model": DEFAULT_MODEL,
            "llm_provider": DEFAULT_PROVIDER,
            "condition": condition,
            "agents": AGENTS,
            "prize_pool": PRIZE_POOL,
            "contexts": EMOTIONAL_CONTEXTS if condition == "emotional" else {},
        },
    )
    show("Create run", status, body)
    assert 200 <= status < 300, "new-run failed"


def test_get_state(base: str):
    section("2. GET /state")
    status, body = api(base, "get", "/state")
    show("Game state", status, body)
    assert body.get("run_id") == RUN_ID, "run_id mismatch"
    assert body.get("phase") == "pre_game", "Expected pre_game phase"


def test_pre_game_chat(base: str):
    section("3. /generate-first-message + /chat — pre_game exchanges")

    # A generates LLM opening message to B
    # (identity + pre_discussion → first msg)
    status, body = api(
        base, "post", "/generate-first-message",
        json={
            "from": "A",
            "to": "B",
        },
    )
    show("A → B (generated opening)", status, body)
    assert "message" in body, "No opening message generated"
    a_to_b_opening = body["message"]

    # Send A's generated message to B; B replies
    status, body = api(
        base, "post", "/chat",
        json={
            "from": "A",
            "to": "B",
            "message": a_to_b_opening,
            "phase": "pre_game",
        },
    )
    show("A → B (pre_game)", status, body)
    assert "reply" in body, "No reply received"

    # B sends their reply back to A; A responds
    status, body = api(
        base, "post", "/chat",
        json={
            "from": "B",
            "to": "A",
            "message": body["reply"],
            "phase": "pre_game",
        },
    )
    show("B → A (pre_game response)", status, body)

    # A generates LLM opening message to C
    status, body = api(
        base, "post", "/generate-first-message",
        json={
            "from": "A",
            "to": "C",
        },
    )
    show("A → C (generated opening)", status, body)
    assert "message" in body, "No opening message generated"

    status, body = api(
        base, "post", "/chat",
        json={
            "from": "A",
            "to": "C",
            "message": body["message"],
            "phase": "pre_game",
        },
    )
    show("A → C (pre_game)", status, body)

    # B generates LLM opening message to C → creates B_C conversation file
    status, body = api(
        base, "post", "/generate-first-message",
        json={
            "from": "B",
            "to": "C",
        },
    )
    show("B → C (generated opening)", status, body)
    assert "message" in body, "No opening message generated"

    status, body = api(
        base, "post", "/chat",
        json={
            "from": "B",
            "to": "C",
            "message": body["message"],
            "phase": "pre_game",
        },
    )
    show("B → C (pre_game)", status, body)


def test_act(base: str):
    section("4. POST /act — each agent takes from pool")
    state_status, state = api(base, "get", "/state")
    turn_order = state.get("turn_order", AGENTS)

    for agent in turn_order:
        status, body = api(
            base, "post", "/act",
            json={
                "agent_id": agent,
            },
        )
        show(f"Agent {agent} acts", status, body)
        assert "amount" in body, f"Agent {agent}: no amount in response"


def test_get_results(base: str):
    section("5. GET /results")
    status, body = api(base, "get", f"/results?run_id={RUN_ID}")
    show("Results", status, body)
    assert "run" in body, "No run data"
    assert "scores" in body, "No scores data"
    allocations = body["run"].get("allocations", [])
    print(f"\n  Allocations ({len(allocations)} agents):")
    for a in allocations:
        bar = "▓" * int(a["g_k"] * 5) if a["g_k"] <= 3 else "▓" * 15
        print(
            f"    {a['agent']}: ${a['taken']:>6,}  "
            f"g_k={a['g_k']:.2f}  {bar}"
            )
    print(f"\n  Gini coefficient: {body['scores'].get('gini', 'N/A')}")


def test_post_game_chat(base: str):
    section("6. POST /chat — post_game exchange")
    status, body = api(
        base, "post", "/chat",
        json={
            "from": "A",
            "to": "B",
            "message": "Why did you take that amount?",
            "phase": "post_game",
        },
    )
    show("A → B (post_game)", status, body)


def inspect_memory(run_id: str):
    section("7. Inspect memory files")
    memory_dir = DATA_DIR / "memory" / run_id
    if not memory_dir.exists():
        print(f"  No memory directory for run '{run_id}'")
        return
    for agent in AGENTS:
        path = memory_dir / f"{agent}.json"
        if path.exists():
            data = json.loads(path.read_text())
            print(f"\nMemory for Agent {agent}:")
            print(f"  context: {data.get('context', '')[:80]}")
            print(f"  connection_scores: {data.get('connection_scores', {})}")
            summaries = data.get("conversation_summaries", {})
            for partner, summary in summaries.items():
                print(f"  summary[{partner}]: {summary[:100]}")
        else:
            print(f"\n[!] Memory file not found for {agent}: {path}")


def inspect_conversation(run_id: str):
    section("8. Inspect conversation files")
    conv_dir = DATA_DIR / "conversations" / run_id
    if not conv_dir.exists():
        print(f"  No conversations directory for run '{run_id}'")
        return
    for f in sorted(conv_dir.glob("*.json")):
        data = json.loads(f.read_text())
        pair = data.get("pair", [])
        pre = data.get("pre_game", [])
        post = data.get("post_game", [])
        print(
            f"\n  Pair {pair}: {len(pre)} pre-game turns, "
            f"{len(post)} post-game turns"
            )
        for m in pre[:2]:
            print(f"    pre  - {m['from']}: {m['message'][:80]}")
        for m in post[:2]:
            print(f"    post - {m['from']}: {m['message'][:80]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global RUN_ID
    parser = argparse.ArgumentParser(
        description="Test SimCo backend endpoints"
        )
    parser.add_argument(
        "--base-url",
        default=os.getenv(
            "BACKEND_URL",
            "http://127.0.0.1:5000"
            ),
        help="Base URL of the running Flask server",
    )
    parser.add_argument(
        "--condition",
        choices=["neutral", "emotional"],
        default="emotional",
        help="Run condition (default: emotional)",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip steps that call the LLM (useful for storage-only checks)",
    )
    parser.add_argument(
        "--only",
        choices=[
            "all",
            "pre_game_chat",
            "act",
            "results",
            "post_game_chat",
        ],
        default="all",
        help=(
            "Run only up to a specific stage checkpoint "
            "(default: all)"
        ),
    )
    args = parser.parse_args()
    base = args.base_url

    print("\nSimCo backend test")
    print(f"  Server : {base}")
    print(f"  Agents : {AGENTS}")
    print(f"  Condition: {args.condition}")
    print(f"  Only stage: {args.only}")

    RUN_ID = storage.generate_run_id(
        condition=args.condition,
        model_type=DEFAULT_MODEL,
        data_dir=DATA_DIR,
    )
    print(f"Using run_id: {RUN_ID}")

    # Verify server is up
    try:
        requests.get(base + "/state", timeout=3)
    except requests.exceptions.ConnectionError:
        print(
            f"\n[ERROR] Cannot reach {base}. "
            "Start the Flask server first:\n"
            "  cd backend && python app.py\n"
        )
        sys.exit(1)

    try:
        test_new_run(base, args.condition)
        test_get_state(base)

        if not args.skip_llm:
            if args.only == "all":
                test_pre_game_chat(base)
                test_act(base)
                test_get_results(base)
                test_post_game_chat(base)
            elif args.only == "pre_game_chat":
                test_pre_game_chat(base)
            elif args.only == "act":
                test_pre_game_chat(base)
                test_act(base)
            elif args.only == "results":
                test_pre_game_chat(base)
                test_act(base)
                test_get_results(base)
            elif args.only == "post_game_chat":
                test_pre_game_chat(base)
                test_act(base)
                test_get_results(base)
                test_post_game_chat(base)

        inspect_memory(RUN_ID)
        inspect_conversation(RUN_ID)

        section("All tests passed ✓")

    except AssertionError as exc:
        print(f"\n[FAIL] Assertion error: {exc}")
        sys.exit(1)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"\n[FAIL] Unexpected error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
