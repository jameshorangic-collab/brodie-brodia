"""P04 checks for explicit ending, ephemeral evidence, and one feedback transition."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from facetime.brodia import FeedbackSession


def main():
    session = FeedbackSession()
    assert session.observe({'type': 'voice', 'role': 'caller', 'text': 'Hi, how is your day?'}) is None
    prompt = session.observe({'type': 'voice', 'role': 'caller', 'text': 'Thanks, I would like to end practice now.'})
    assert prompt is not None and 'Hi, how is your day?' in prompt
    assert 'two strengths, two improvements' in prompt
    assert session.observe({'type': 'voice', 'role': 'caller', 'text': 'bye'}) is None
    empty = FeedbackSession(); prompt = empty.observe({'type': 'voice', 'role': 'caller', 'text': 'bye'})
    assert 'No usable caller transcript' not in prompt  # the goodbye itself is evidence
    visual = FeedbackSession()
    visual.observe({'type': 'vision_note', 'source_verified': False, 'observable_description': 'facing the camera'})
    visual.observe({'type': 'vision_note', 'source_verified': True, 'observable_description': 'turned away from the camera', 'optional_nearby_utterance': 'I have to go'})
    prompt = visual.observe({'type': 'voice', 'role': 'caller', 'text': 'Please end practice'})
    assert 'turned away from the camera' in prompt and 'facing the camera' not in prompt
    no_video = FeedbackSession(); prompt = no_video.observe({'type': 'voice', 'role': 'caller', 'text': 'end practice'})
    assert 'No verified visual observation is available' in prompt
    # These are actual closing words used during the iPhone integration call.
    for closing in ('Yeah, okay. End end this conversation.', 'Can we end it?',
                    'Please end the call.', 'Let’s end it.', 'Good bye!', 'I have to go.',
                    'Please end this session.', 'Stop the conversation.', 'End it.', 'Stop!'):
        session = FeedbackSession()
        session.observe({'type': 'voice', 'role': 'caller', 'text': 'Hi, I am Alex.'})
        assert session.observe({'type': 'voice', 'role': 'coach', 'text': closing}) is None
        prompt = session.observe({'type': 'voice', 'role': 'caller', 'text': closing})
        assert prompt and session.finished and 'Hi, I am Alex.' in prompt, closing
        assert session.observe({'type': 'voice', 'role': 'caller', 'text': closing}) is None
    for continuing in ('The conversation is fun.', 'I walked by yesterday.',
                       'Can I get your number?', 'This shift will end soon.',
                       'Could you stop putting so much sugar in my coffee?'):
        assert not FeedbackSession._ends(continuing), continuing
    # Exercise the worker's real event-to-voice handoff, not just phrase matching.
    from unittest.mock import Mock
    from facetime.voice import VoiceLayer
    layer = VoiceLayer.__new__(VoiceLayer)
    layer.n_events = 0; layer.feedback = FeedbackSession(); layer.ask_voice = Mock()
    layer.on_event({'type': 'voice', 'role': 'caller', 'text': 'End this conversation.'})
    layer.on_event({'type': 'voice', 'role': 'caller', 'text': 'Goodbye.'})
    layer.ask_voice.assert_called_once()
    assert 'ROLEPLAY IS OVER' in layer.ask_voice.call_args.args[0]
    print('P04 explicit end and grounded feedback transition: PASS')


if __name__ == '__main__':
    main()
