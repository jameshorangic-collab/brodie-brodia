"""Opt-in real dispatched worker + LiveKit network + Gemini synthetic-audio test.

Start a worker from THIS checkout with --agent-name brodia-final-test --perception off,
BRODIA_DEBUG_CONVERSATION=1 and (optionally) a high-rapport initial-score fixture.
Export AGENT_NAME=brodia-final-test and credentials, then run this script.
Random outcomes are real: each declined room stays declined; only a NEW session may
try again. No browser, human microphone, audio recording or transcript persistence.
"""
import argparse
import asyncio
import json
import logging
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from livekit import api, rtc
from facetime.brodia_server import create_session
from facetime.social_contacts import DEMO_CONTACTS
from scripts.test_brodia_live_smoke import Audio, synth


async def attempt(index):
    session = await create_session({'scenario': 'barista', 'receptivity': 'interested'})
    room = rtc.Room()
    received, readers = [], set()
    activity = {'frames': 0, 'active': 0, 'last': 0}
    input_audio = Audio()
    source = rtc.AudioSource(16000, 1)
    pump = None

    @room.on('data_received')
    def data(packet):
        if packet.topic == 'brodia.social_outcome':
            value = json.loads(packet.data)
            if value.get('type') == 'social_outcome':
                received.append(value)

    async def read(track):
        stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1)
        try:
            async for event in stream:
                activity['frames'] += 1
                if any(abs(x) > 500 for x in event.frame.data):
                    activity['active'] += 1
                    activity['last'] = time.monotonic()
        finally:
            await stream.aclose()

    @room.on('track_subscribed')
    def track_subscribed(track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            task = asyncio.create_task(read(track))
            readers.add(task)
            task.add_done_callback(readers.discard)

    async def push():
        async for frame in input_audio:
            await source.capture_frame(frame)

    async def speak(path, line, expect_receipt=False):
        await synth(path, line)
        before_receipts, before_audio = len(received), activity['active']
        input_audio.feed(path)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if not input_audio.frames and activity['active'] > before_audio and time.monotonic() - activity['last'] > 1.5:
                if not expect_receipt or len(received) > before_receipts:
                    await asyncio.sleep(2)  # let the existing background audit finish
                    return
            await asyncio.sleep(.1)
        raise AssertionError('No completed network voice reply / expected receipt')

    try:
        await room.connect(session['url'], session['token'])
        track = rtc.LocalAudioTrack.create_audio_track('synthetic-caller', source)
        await room.local_participant.publish_track(track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
        pump = asyncio.create_task(push())
        await asyncio.sleep(8)  # dispatched process + Gemini socket initialization
        with tempfile.TemporaryDirectory(prefix='brodia-room-audio-') as directory:
            path = Path(directory) / 'speech.wav'
            await speak(path, "Hi, I'm Alex. That latte art looks like a cat. You have a very cool coffee shop.")
            await speak(path, 'Could I get your phone number?', True)
            accepted = received[-1]['accepted']
            if accepted:
                if received[-1]['demo_contact'] != DEMO_CONTACTS['phone']:
                    raise AssertionError('Phone receipt did not complete the approved demo exchange')
                await speak(path, 'Okay, what is the number? I am ready to write it down.')
            await speak(path, "What's your IG too?", True)
            if received[-1]['accepted'] != accepted:
                raise AssertionError('Phone-to-IG request changed the cached outcome')
            if accepted and received[-1]['demo_contact'] != DEMO_CONTACTS['instagram']:
                raise AssertionError('IG receipt did not complete the approved demo exchange')
            if not accepted and any(x['demo_contact'] is not None for x in received):
                raise AssertionError('Declined contact leaked a demo detail')
        print(json.dumps({'result': 'PASS', 'test': 'real_worker_livekit_gemini_synthetic_audio',
                          'attempt': index, 'accepted': accepted, 'receipts': received,
                          'remote_audio_frames': activity['frames'], 'audible_frames': activity['active']}), flush=True)
        return accepted
    finally:
        if pump:
            pump.cancel()
            await asyncio.gather(pump, return_exceptions=True)
        for task in list(readers): task.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
        await room.disconnect()
        await source.aclose()
        async with api.LiveKitAPI() as lk:
            await lk.room.delete_room(api.DeleteRoomRequest(room=session['room']))


async def main(args):
    for index in range(1, args.max_attempts + 1):
        if await attempt(index):
            return 0
    print(json.dumps({'result': 'NO_ACCEPTANCE', 'reason': 'All independent sessions legitimately declined'}))
    return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-attempts', type=int, default=4)
    args = parser.parse_args()
    logging.getLogger('livekit').setLevel(logging.CRITICAL)
    try:
        sys.exit(asyncio.run(main(args)))
    except Exception as exc:
        print(json.dumps({'result': 'FAIL', 'error_type': type(exc).__name__,
                          'reason': str(exc) if isinstance(exc, AssertionError) else 'Details withheld'}))
        sys.exit(1)
