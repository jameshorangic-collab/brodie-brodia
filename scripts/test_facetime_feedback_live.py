"""Opt-in real worker/LiveKit/Gemini test with synthetic speech, not an iPhone test.

Start a fresh avatar worker, export its AGENT_NAME and the usual credentials, then
pass --worker-log pointing to that worker's log. No real microphone, recordings,
transcript output or extra model per-turn evaluator is introduced by this test.
"""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from livekit import api, rtc
from facetime.brodia import RoleplayConfig
from facetime.facetime_oss import dispatch_and_wait
from facetime.mint_token import mint
from scripts.test_brodia_live_smoke import Audio, synth


async def run(args):
    start = args.worker_log.stat().st_size
    name, agent = await dispatch_and_wait(RoleplayConfig('barista', 'interested'), 30)
    room = rtc.Room()
    activity = {'audio_frames': 0, 'audible_frames': 0, 'video_frames': 0, 'last_audio': 0}
    readers = set()
    audio = Audio()
    source = rtc.AudioSource(16000, 1)
    pump = None

    async def read(track):
        stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1) if track.kind == rtc.TrackKind.KIND_AUDIO else rtc.VideoStream(track)
        try:
            async for event in stream:
                if track.kind == rtc.TrackKind.KIND_VIDEO:
                    activity['video_frames'] += 1
                    activity['video_size'] = [event.frame.width, event.frame.height]
                else:
                    activity['audio_frames'] += 1
                    if any(abs(x) > 500 for x in event.frame.data):
                        activity['audible_frames'] += 1; activity['last_audio'] = time.monotonic()
        finally:
            await stream.aclose()

    @room.on('track_subscribed')
    def subscribed(track, pub, participant):
        if participant.identity == agent and pub.name in ('coach-audio', 'brodia-avatar'):
            task = asyncio.create_task(read(track)); readers.add(task); task.add_done_callback(readers.discard)

    async def push():
        async for frame in audio:
            await source.capture_frame(frame)

    async def speak(path, text):
        await synth(path, text)
        before = activity['audible_frames']
        audio.feed(path)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if not audio.frames and activity['audible_frames'] > before and time.monotonic()-activity['last_audio'] > 2:
                return
            await asyncio.sleep(.1)
        raise AssertionError('No completed audible reply to synthetic speech')

    try:
        await room.connect(os.environ['LIVEKIT_URL'], mint('facetime-feedback-verifier', name))
        track = rtc.LocalAudioTrack.create_audio_track('facetime-caller', source)
        await room.local_participant.publish_track(track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
        pump = asyncio.create_task(push())
        await asyncio.sleep(8)
        with tempfile.TemporaryDirectory(prefix='brodia-feedback-audio-') as directory:
            path = Path(directory)/'speech.wav'
            await speak(path, "Hi, I'm Alex. Your latte art is pretty cool.")
            before = activity['audible_frames']
            await speak(path, 'Okay, end this conversation.')
        log = args.worker_log.read_bytes()[start:].decode('utf8', errors='replace')
        assert log.count('[brodia] roleplay ended; generating grounded feedback') == 1, 'Feedback did not transition exactly once'
        assert log.count('[avatar] roleplay over: switching to Coach Brodie') == 1, 'Coach avatar did not transition exactly once'
        assert activity['audible_frames']-before > 100, 'Feedback audio was not audible through LiveKit'
        assert activity['video_frames'] > 100 and activity['video_size'] == [960, 540], 'Landscape avatar did not decode'
        print(json.dumps({'result': 'PASS', 'test': 'real_worker_livekit_gemini_synthetic_closing',
                          'feedback_transitions': 1, 'coach_avatar_transitions': 1,
                          'closing_and_feedback_audible_frames': activity['audible_frames']-before,
                          'video_frames': activity['video_frames'], 'video_size': activity['video_size']}))
    finally:
        if pump: pump.cancel(); await asyncio.gather(pump, return_exceptions=True)
        for task in list(readers): task.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
        await room.disconnect(); await source.aclose()
        async with api.LiveKitAPI() as lk:
            await lk.room.delete_room(api.DeleteRoomRequest(room=name))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-log', type=Path, required=True)
    args = parser.parse_args()
    logging.getLogger('livekit').setLevel(logging.CRITICAL)
    try:
        asyncio.run(run(args))
    except Exception as exc:
        print(json.dumps({'result': 'FAIL', 'error_type': type(exc).__name__,
                          'reason': str(exc) if isinstance(exc, AssertionError) else 'Details withheld'}))
        sys.exit(1)
