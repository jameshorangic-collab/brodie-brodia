"""Opt-in REAL Gemini audio quality checks with macOS synthetic caller speech.

Run after exporting .env.local: python scripts/test_brodia_live_quality.py --case all
Uses the existing AgentSession, PCM input, mixer and background evaluator. No room,
browser, human microphone, or subjective listening test. High rapport and outcome
draws are controlled fixtures; speech understanding and tool calls are live Gemini.
No audio/transcripts are saved. --show-transcripts prints synthetic test replies only.
"""
import argparse
import asyncio
import json
import logging
from pathlib import Path
import re
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from facetime.audio_out import CueBank, CuePlayer
from facetime.brodia import RoleplayConfig
from facetime.brodia_live import BrodiaController
from facetime.voice import GeminiModel, MixerAudioOutput
from scripts.test_brodia_live_smoke import Audio, Source, synth


SMALL_TALK = [
    "Hi, I'm Alex. Your latte art looks like a cat. That's pretty impressive.",
    "I like finding little coffee shops when I'm out taking photos. Mostly street photography.",
    "I once spent ten minutes photographing a pigeon. He was a very demanding model.",
    "That made me laugh. This place has a nice vibe.",
]
CASES = {
    'interested_playful': dict(stance='interested', personality='Playful', lines=SMALL_TALK),
    'interested_shy': dict(stance='interested', personality='Shy', lines=SMALL_TALK),
    'neutral': dict(stance='neutral', personality='Refined', lines=SMALL_TALK),
    'uninterested': dict(stance='uninterested', personality='Sassy', draw=.99,
                        lines=[SMALL_TALK[0], 'Could I get your phone number?', "What's your IG then?"],
                        request='contact', accepted=False),
    'phone': dict(stance='interested', personality='Bold/flirty', score=90,
                  lines=[SMALL_TALK[0], 'You are fun to talk to. Could I get your phone number?', "What's your IG too?"],
                  request='contact', accepted=True),
    'instagram': dict(stance='interested', personality='Bubbly', score=90,
                      lines=[SMALL_TALK[0], "You are fun to talk to. What's your IG?", 'Could I get your number too?'],
                      request='contact', accepted=True),
    'date': dict(stance='interested', personality='Refined', score=90,
                 lines=[SMALL_TALK[0], 'Would you like to get dinner with me after your shift?'],
                 request='date', accepted=True),
    'memory': dict(stance='interested', personality='Playful',
                   lines=SMALL_TALK + ["Wait, do you remember my name and what kind of photos I take?"]),
}


class FixedDraw:
    def __init__(self, value): self.value, self.draws = value, 0
    def random(self): self.draws += 1; return self.value


async def run_case(name, fixture, show_transcripts):
    rng = FixedDraw(fixture.get('draw', 0))
    controller = BrodiaController(RoleplayConfig('barista', fixture['stance']), rng=rng,
                                  personality=fixture['personality'])
    if 'score' in fixture:
        controller.state.score = fixture['score']
        controller.state._smooth_band()
    traces = []
    original_decide = controller.state.decide
    def traced_decide(request, **flags):
        outcome = original_decide(request, **flags)
        traces.append(dict(request=request, **flags,
                           decision=None if outcome is None else 'accept' if outcome.accepted else 'decline',
                           probability=None if outcome is None else round(outcome.probability, 3)))
        return outcome
    controller.state.decide = traced_decide
    turns, errors, replies, latencies = [], [], [], []
    source, audio = Source(), Audio()
    player = CuePlayer(bank=CueBank.disabled(), source=source)
    sink = MixerAudioOutput(player.attach_mixer())
    pump = asyncio.create_task(player.run())
    model = GeminiModel(controller.instructions(), controller=controller,
                        on_turn=lambda role, text: turns.append((role, text)))
    try:
        await asyncio.wait_for(model.start(sink), 20)
        model.session.on('error', lambda event: errors.append('session-error'))
        model.session.input.audio = audio
        model.set_input_enabled(True)
        with tempfile.TemporaryDirectory(prefix='brodia-quality-') as directory:
            for index, line in enumerate(fixture['lines']):
                path = Path(directory) / f'turn-{index}.wav'
                await synth(path, line)
                before = len(turns)
                caller_before = controller.diagnostics['caller_finals']
                started = time.monotonic()
                duration = audio.feed(path)
                async def wait_reply():
                    while not errors:
                        new_reply = any(role == 'coach' for role, _ in turns[before:])
                        final_input = controller.diagnostics['caller_finals'] > caller_before
                        if not audio.frames and new_reply and final_input and not model.speaking:
                            return
                        await asyncio.sleep(.05)
                    raise RuntimeError('Gemini session error')
                await asyncio.wait_for(wait_reply(), 35)
                if index == 0 and sink.t_first_frame:
                    latencies.append(round((sink.t_first_frame - started - duration) * 1000))
                await asyncio.wait_for(controller.queue.join(), 12)
                reply = ' '.join(text for role, text in turns[before:] if role == 'coach')
                replies.append(reply)
                if controller.personality != fixture['personality']:
                    raise AssertionError('Personality changed during call')
        lowered = ' '.join(replies).lower().replace('\u2019', "'")
        if any(phrase in lowered for phrase in ('as an ai', 'i am an ai', "i'm an ai", 'cannot share personal information',
                                                'squats', 'push-ups', 'workout')):
            raise AssertionError('Assistant disclaimer or fitness leakage')
        if controller.diagnostics['language_failures'] or controller.diagnostics['evaluation_errors']:
            raise AssertionError('Language or evaluator failure')
        if source.frames == 0 or model.voice != 'Leda':
            raise AssertionError('Existing female voice/audio pipeline failed')
        questions = sum('?' in reply for reply in replies)
        if name.startswith('interested_') and not questions:
            raise AssertionError('Interested character asked no follow-up questions')
        if 'request' in fixture:
            decisions = [trace for trace in traces if trace['request'] == fixture['request']]
            expected = 'accept' if fixture['accepted'] else 'decline'
            if len(decisions) < len(fixture['lines']) - 1 or any(trace['decision'] != expected for trace in decisions):
                raise AssertionError('Missing tool invocation or wrong/changed outcome')
            if rng.draws > 1:
                raise AssertionError('Phone/IG paraphrase rerolled the outcome')
            if fixture['accepted'] and any(not trace['appropriate'] or trace['uncertain'] for trace in decisions):
                raise AssertionError('Respectful request incorrectly marked inappropriate/uncertain')
            if fixture['accepted']:
                refusal = r"\b(?:not interested|don't share|do not share|rather not|can't give|cannot give|no thanks)\b"
                if any(re.search(refusal, reply.lower().replace('\u2019', "'")) for reply in replies[1:]):
                    raise AssertionError('Spoken refusal contradicted accepted tool outcome')
                # The live contextual evaluator also detects explicit spoken refusals.
                # Do not require stock acceptance wording: "I'd actually love that"
                # and a proposed time are just as natural as "yeah, sure".
                if 'all' in controller.state.boundaries or fixture['request'] in controller.state.boundaries:
                    raise AssertionError('Accepted outcome contradicted by an explicit spoken boundary')
                if fixture['request'] == 'contact' and any(re.search(r'\d[\d\s().-]{5,}\d|@[\w.]+', reply)
                                                          for reply in replies[1:]):
                    raise AssertionError('Contact acceptance dictated an invented number or handle')
        if name == 'memory' and not ('alex' in replies[-1].lower() and 'street' in replies[-1].lower()):
            raise AssertionError('Name/topic continuity failed')
        report = dict(result='PASS', case=name, personality=controller.personality,
                      voice=model.voice, question_turns=questions, reply_turns=len(replies),
                      first_audio_after_input_ms=latencies, audio_frames=source.frames,
                      high_rapport_fixture=fixture.get('score'), tool_trace=traces,
                      outcome_draws=rng.draws, diagnostics=controller.diagnostics)
        if show_transcripts: report['synthetic_character_replies'] = replies
        print(json.dumps(report), flush=True)
    except AssertionError:
        report = dict(case=name, tool_trace=traces, diagnostics=controller.diagnostics)
        if show_transcripts: report['synthetic_character_replies'] = replies
        print(json.dumps(report), flush=True)
        raise
    finally:
        await model.aclose()
        player.stop()
        await asyncio.gather(pump, return_exceptions=True)


async def main(args):
    names = list(CASES) if args.case == 'all' else [args.case]
    failures = []
    for name in names:
        try:
            await run_case(name, CASES[name], args.show_transcripts)
        except Exception as exc:
            # Provider errors may contain credentials/transcripts; never print their bodies.
            report = dict(result='FAIL', case=name, error_type=type(exc).__name__)
            if isinstance(exc, AssertionError): report['reason'] = str(exc)
            print(json.dumps(report), flush=True)
            failures.append(name)
    return int(bool(failures))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=['all', *CASES], required=True)
    parser.add_argument('--show-transcripts', action='store_true')
    logging.getLogger('livekit').setLevel(logging.CRITICAL)
    logging.getLogger('google').setLevel(logging.CRITICAL)
    sys.exit(asyncio.run(main(parser.parse_args())))
