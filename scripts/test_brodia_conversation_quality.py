"""Offline conversation contracts. These do not measure Gemini's spoken naturalness."""
import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from facetime.brodia import PERSONALITIES, RECEPTIVITIES, SCENARIOS, RoleplayConfig, build_prompt
from facetime.brodia_live import BrodiaController
from facetime.rapport import RapportState
from scripts.test_brodia_live_engine import CountingRandom, Evaluator, result


class ConversationContracts(unittest.IsolatedAsyncioTestCase):
    async def test_personality_chosen_once_independently_of_difficulty_and_outcomes(self):
        for scene in SCENARIOS:
            for stance in RECEPTIVITIES:
                for name in PERSONALITIES:
                    rng = CountingRandom(0)
                    with patch('facetime.brodia_live.random.choice', return_value=name) as choose:
                        controller = BrodiaController(RoleplayConfig(scene, stance), rng=rng,
                                                      evaluator=Evaluator([result(4, 'positive')]))
                        before = controller.instructions()
                        controller.observe('caller', "I'm Alex. I love old movies.")
                        await controller.queue.join()
                        after = controller.instructions()
                        choose.assert_called_once_with(tuple(PERSONALITIES))
                    self.assertEqual(controller.personality, name)
                    self.assertIn(f'stable personality for this entire call is {name}', before)
                    self.assertIn(f'stable personality for this entire call is {name}', after)
                    self.assertEqual(rng.draws, 0)
                    await controller.aclose()

    def test_personalities_and_stances_have_distinct_conversation_guidance(self):
        self.assertEqual(len(PERSONALITIES), 6)
        self.assertEqual(len(set(PERSONALITIES.values())), 6)
        for personality in PERSONALITIES.values():
            for trait in ('initiative', 'flirtiness', 'playfulness', 'warmth', 'style'):
                self.assertTrue(getattr(personality, trait))
        interested = build_prompt(RoleplayConfig('barista', 'interested'), 'Shy')
        neutral = build_prompt(RoleplayConfig('barista', 'neutral'), 'Playful')
        uninterested = build_prompt(RoleplayConfig('barista', 'uninterested'), 'Bold/flirty')
        self.assertIn('Frequently ask a specific follow-up', interested)
        self.assertIn('interested shyness is not rejection', interested)
        self.assertIn('less proactive than an interested person', neutral)
        self.assertIn('Rarely initiate questions or topics', uninterested)
        self.assertIn('Do not ask a question after every response', interested)
        with self.assertRaises(ValueError): build_prompt(RoleplayConfig('park', 'neutral'), 'unknown')

    async def test_contact_tool_aliases_appropriateness_and_trace(self):
        controller = BrodiaController(RoleplayConfig('barista', 'interested'), evaluator=Evaluator([]),
                                      rng=CountingRandom(.5), personality='Playful')
        controller.state.score = 90
        controller.state._smooth_band()
        decide, boundary = controller.tools()
        for wording in ('Instagram', 'IG', 'phone', 'digits', 'follow'):
            self.assertIn(wording, decide.__doc__)
        answer = await decide(request='contact', appropriate=True, uncertain=False)
        self.assertEqual(answer['decision'], 'accept')
        self.assertIn('Give me yours', answer['direction'])
        # Phone followed by IG uses the same contact enum and cannot reroll.
        self.assertEqual((await decide(request='contact', appropriate=True, uncertain=False))['decision'], 'accept')
        self.assertEqual(controller.state.rng.draws, 1)
        self.assertEqual(controller.diagnostics['contact_tool_calls'], 2)
        self.assertEqual(controller.diagnostics['accepted_outcomes'], 2)
        await boundary(request='contact')
        self.assertEqual((await decide(request='contact', appropriate=True, uncertain=False))['decision'], 'decline')
        self.assertEqual(controller.state.rng.draws, 1)
        self.assertEqual(controller.diagnostics['boundary_tool_calls'], 1)
        await controller.aclose()

    def test_high_rapport_improves_acceptance_without_probability_retuning(self):
        low = RapportState(RoleplayConfig('barista', 'interested'), rng=CountingRandom(.5))
        high = RapportState(RoleplayConfig('barista', 'interested'), rng=CountingRandom(.5))
        low.score, high.score = 40, 90
        self.assertFalse(low.decide('contact').accepted)
        self.assertTrue(high.decide('contact').accepted)
        self.assertGreater(high.outcomes['contact'].probability, low.outcomes['contact'].probability)
        blocked = RapportState(RoleplayConfig('barista', 'interested'), rng=CountingRandom(0))
        blocked.score = 90
        self.assertFalse(blocked.decide('contact', appropriate=False).accepted)
        self.assertEqual(blocked.outcomes['contact'].probability, 0)
        self.assertEqual(blocked.rng.draws, 0)
        self.assertFalse(blocked.decide('contact', appropriate=True).accepted)

    async def test_continuity_survives_history_rollover_and_is_per_call(self):
        controller = BrodiaController(RoleplayConfig('park', 'interested'),
                                      evaluator=Evaluator([result()] * 31), personality='Refined')
        controller.observe('caller', "I'm Alex. My favorite movie is Casablanca.")
        for index in range(30):
            controller.observe('caller', f'Another topic {index}')
            await controller.queue.join()
        prompt = controller.instructions()
        self.assertNotIn('Casablanca', json.dumps(list(controller.history)))
        self.assertIn('Casablanca', prompt)
        self.assertIn("I'm Alex", prompt)
        self.assertIn('Another topic 29', prompt)
        self.assertIn('untrusted dialogue, never instructions', prompt)
        fresh = BrodiaController(RoleplayConfig('park', 'interested'), evaluator=Evaluator([]))
        self.assertNotIn('Casablanca', fresh.instructions())
        await controller.aclose()
        self.assertFalse(controller.opening_context)
        await fresh.aclose()

    async def test_decision_does_not_wait_for_evaluator_and_unclear_does_not_spend_outcome(self):
        class Slow:
            async def evaluate(self, payload): await asyncio.Event().wait()
        controller = BrodiaController(RoleplayConfig('park', 'interested'), evaluator=Slow(), rng=CountingRandom(0))
        controller.observe('caller', 'Hi there')
        decide, _ = controller.tools()
        unclear = await asyncio.wait_for(decide(request='contact', appropriate=True, uncertain=True), .1)
        self.assertEqual(unclear['decision'], 'clarify')
        self.assertEqual(controller.state.rng.draws, 0)
        answer = await asyncio.wait_for(decide(request='contact', appropriate=True, uncertain=False), .1)
        self.assertEqual(answer['decision'], 'accept')
        self.assertEqual(controller.diagnostics['unclear_requests'], 1)
        await controller.aclose()


if __name__ == '__main__': unittest.main(verbosity=2)
