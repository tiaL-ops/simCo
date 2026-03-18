#!/usr/bin/env python3
"""Regression tests for game prompt selection by execution mode."""

import json
import unittest
from unittest.mock import patch

from graph import nodes


def _fake_render(template, **kwargs):
    return json.dumps({"template": template, "kwargs": kwargs}, sort_keys=True)


class GamePromptSelectionTests(unittest.TestCase):
    def test_full_mode_uses_game_decision_prompt(self):
        game_state = {
            "execution_mode": "full",
            "condition": "emotional",
            "prize_pool": 30000,
            "initial_prize_pool": 50000,
            "agents_remaining": 3,
            "turn_order": ["A", "B", "C"],
        }
        agent_memory = {"context": "Need money for rent."}

        with patch("graph.nodes._load_template", side_effect=lambda name: name), \
                patch("graph.nodes._render", side_effect=_fake_render), \
                patch("graph.nodes.storage.read_memory") as read_memory:
            prompt = nodes._build_game_prompt(
                run_id="run_test",
                agent_id="A",
                game_state=game_state,
                agent_memory=agent_memory,
                discussion_summary="Met B and C before the game.",
            )

        payload = json.loads(prompt)
        self.assertEqual(payload["template"], "game_decision")
        self.assertEqual(
            payload["kwargs"]["discussion_summary"],
            "Met B and C before the game.",
        )
        read_memory.assert_not_called()

    def test_game_only_uses_game_only_decision_with_emotional_contexts(self):
        game_state = {
            "execution_mode": "game_only",
            "condition": "emotional",
            "prize_pool": 30000,
            "initial_prize_pool": 50000,
            "agents_remaining": 3,
            "turn_order": ["A", "B", "C"],
        }
        agent_memory = {"context": "Need money for rent."}

        with patch("graph.nodes._load_template", side_effect=lambda name: name), \
                patch("graph.nodes._render", side_effect=_fake_render), \
                patch(
                    "graph.nodes.storage.read_memory",
                    side_effect=[
                        {"context": "B needs surgery funds."},
                        {"context": "C was laid off recently."},
                    ],
                ) as read_memory:
            prompt = nodes._build_game_prompt(
                run_id="run_test",
                agent_id="A",
                game_state=game_state,
                agent_memory=agent_memory,
                discussion_summary="Should not be used in game-only mode.",
            )

        payload = json.loads(prompt)
        self.assertEqual(payload["template"], "game_only_decision")
        self.assertEqual(payload["kwargs"]["condition_context"], "Need money for rent.")
        self.assertEqual(
            payload["kwargs"]["others_context"],
            "- B: B needs surgery funds.\n- C: C was laid off recently.",
        )
        self.assertEqual(read_memory.call_count, 2)

    def test_game_only_neutral_uses_neutral_context_for_all_others(self):
        game_state = {
            "execution_mode": "game_only",
            "condition": "neutral",
            "prize_pool": 30000,
            "initial_prize_pool": 50000,
            "agents_remaining": 3,
            "turn_order": ["A", "B", "C"],
        }
        agent_memory = {"context": ""}

        with patch("graph.nodes._load_template", side_effect=lambda name: name), \
                patch("graph.nodes._render", side_effect=_fake_render), \
                patch("graph.nodes.storage.read_memory") as read_memory:
            prompt = nodes._build_game_prompt(
                run_id="run_test",
                agent_id="A",
                game_state=game_state,
                agent_memory=agent_memory,
                discussion_summary="Unused in game-only mode.",
            )

        payload = json.loads(prompt)
        self.assertEqual(payload["template"], "game_only_decision")
        self.assertEqual(
            payload["kwargs"]["condition_context"],
            "neutral — no personal context",
        )
        self.assertEqual(
            payload["kwargs"]["others_context"],
            "- B: neutral — no personal context\n- C: neutral — no personal context",
        )
        read_memory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
