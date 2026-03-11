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

Set the LLM_PROVIDER env var before starting the server, e.g.:
  LLM_PROVIDER=openai OPENAI_API_KEY=sk-... python app.py
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

RUN_ID = "test_run_001"
AGENTS = ["A", "B", "C"]
PRIZE_POOL = 30_000  # 10 000 per agent as fair share

EMOTIONAL_CONTEXTS = {
    "A": "You just lost your job and urgently need money for rent.",
    "B": "Your child needs an expensive medical treatment.",
    "C": "You are financially comfortable and have stable income.",
}


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
            "run_id": RUN_ID,
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
    section("3. POST /chat — pre_game exchanges")

    # A sends to B
    status, body = api(
        base, "post", "/chat",
        json={
            "run_id": RUN_ID,
            "from": "A",
            "to": "B",
            "message": "Hey! Nervous about this or are you feeling okay?",
            "phase": "pre_game",
        },
    )
    show("A → B (pre_game)", status, body)
    assert "reply" in body, "No reply received"

    # B responds back to A
    status, body = api(
        base, "post", "/chat",
        json={
            "run_id": RUN_ID,
            "from": "B",
            "to": "A",
            "message": body["reply"],
            "phase": "pre_game",
        },
    )
    show("B → A (pre_game response)", status, body)

    # A sends to C
    status, body = api(
        base, "post", "/chat",
        json={
            "run_id": RUN_ID,
            "from": "A",
            "to": "C",
            "message": "Hi! What do you think about the prize pool setup?",
            "phase": "pre_game",
        },
    )
    show("A → C (pre_game)", status, body)


def test_act(base: str):
    section("4. POST /act — each agent takes from pool")
    state_status, state = api(base, "get", "/state")
    turn_order = state.get("turn_order", AGENTS)

    for agent in turn_order:
        status, body = api(
            base, "post", "/act",
            json={"agent_id": agent, "run_id": RUN_ID},
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
            "run_id": RUN_ID,
            "from": "A",
            "to": "B",
            "message": "Why did you take that amount?",
            "phase": "post_game",
        },
    )
    show("A → B (post_game)", status, body)


def inspect_memory():
    section("7. Inspect memory files")
    memory_dir = DATA_DIR / "memory"
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
    args = parser.parse_args()
    base = args.base_url

    print("\nSimCo backend test")
    print(f"  Server : {base}")
    print(f"  Run ID : {RUN_ID}")
    print(f"  Agents : {AGENTS}")
    print(f"  Condition: {args.condition}")

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
            test_pre_game_chat(base)
            test_act(base)
            test_get_results(base)
            test_post_game_chat(base)

        inspect_memory()
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
