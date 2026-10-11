"""Publish/subscribe the actual avatar + audio tracks in a fresh LiveKit room.

Requires LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET. --gemini uses the existing Gemini Live
voice through the same CuePlayer/MixerAudioOutput path; otherwise sends synthetic PCM in real time.
No FaceTime link, microphone or camera needed; never prints tokens or transcripts.
"""
import argparse
import asyncio
import gc
import os
from pathlib import Path
import secrets
import sys
import time
from types import SimpleNamespace

import numpy as np
from PIL import Image
from livekit import rtc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from facetime.audio_out import CueBank, CuePlayer
from facetime.brodia_avatar import TRACK_NAME, run_for_job
from facetime.mint_token import mint


async def run(args):
    room_name = 'avatar-smoke-' + secrets.token_hex(6)
    publisher, receiver = rtc.Room(), rtc.Room()
    tasks = []; streams = []; pump = avatar_task = monitor = None; model = None; job = None; player = None
    result = {'audio_frames': 0, 'audible_frames': 0, 'video_frames': 0, 'video_name': None, 'audio_name': None}
    mouth_shapes = set(); closed_after_audio = False; video_times = []
    out = Path('data/tmp/avatar-livekit'); out.mkdir(parents=True, exist_ok=True)

    async def read_video(track):
        stream = rtc.VideoStream(track, format=rtc.VideoBufferType.RGB24); streams.append(stream)
        async for ev in stream:
            result['video_frames'] += 1; video_times.append(time.monotonic())
            if result['video_frames'] in (1, 30, 75):
                f = ev.frame; rgb = np.frombuffer(f.data, np.uint8).reshape(f.height, f.width, 3)
                Image.fromarray(rgb).save(out / f'received-{result["video_frames"]}.png')

    async def read_audio(track):
        stream = rtc.AudioStream(track, sample_rate=24000, num_channels=1); streams.append(stream)
        async for ev in stream:
            result['audio_frames'] += 1
            pcm = np.frombuffer(ev.frame.data, np.int16).astype(np.float32)
            if np.sqrt(np.mean(pcm * pcm)) > 200: result['audible_frames'] += 1

    @receiver.on('track_subscribed')
    def subscribed(track, publication, participant):
        if participant.identity != 'avatar-publisher': return
        if track.kind == rtc.TrackKind.KIND_VIDEO:
            result['video_name'] = publication.name; tasks.append(asyncio.create_task(read_video(track)))
        elif track.kind == rtc.TrackKind.KIND_AUDIO:
            result['audio_name'] = publication.name; tasks.append(asyncio.create_task(read_audio(track)))

    try:
        url = os.environ['LIVEKIT_URL']
        await asyncio.wait_for(receiver.connect(url, mint('avatar-receiver', room_name)), 15)
        await asyncio.wait_for(publisher.connect(url, mint('avatar-publisher', room_name)), 15)
        player = CuePlayer(bank=CueBank.disabled()); mix = player.attach_mixer()
        await publisher.local_participant.publish_track(player.track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
        pump = asyncio.create_task(player.run())
        job = SimpleNamespace(room=publisher, player=player, closed=False, voice=None,
                              a=SimpleNamespace(brodia_scenario=args.scenario, brodia_receptivity='neutral', avatar_expression='auto', avatar_image=args.avatar_image))
        avatar_task = asyncio.create_task(run_for_job(job, fps=args.fps, shape=args.shape))

        async def observe_mouth():
            nonlocal closed_after_audio
            saw_open = False
            while not job.closed:
                av = getattr(job, 'avatar', None); shape = getattr(av, 'last_mouth_shape', None)
                if shape:
                    mouth_shapes.add(shape)
                    if shape != 'rest': saw_open = True
                    elif saw_open: closed_after_audio = True
                await asyncio.sleep(0.03)
        monitor = asyncio.create_task(observe_mouth())
        if args.gemini:
            from facetime.brodia import RoleplayConfig, build_prompt
            from facetime.voice import GeminiModel, MixerAudioOutput
            model = GeminiModel(build_prompt(RoleplayConfig(args.scenario, 'neutral')))
            sink = MixerAudioOutput(mix)
            await asyncio.wait_for(model.start(sink), 20)
            job.voice = SimpleNamespace(model=model)
            model.generate('Greet the caller warmly in one short sentence in English. Do not ask a question.')
            await asyncio.sleep(12)
        else:
            # Alternate silence/variable-amplitude syllables on the exact mixer output path Gemini uses.
            for i in range(300):
                level = 0 if i < 50 or i >= 250 else 0.025 + 0.16 * abs(np.sin(i * 0.21))
                pcm = (np.sin(np.arange(480) * 2 * np.pi * 180 / 24000) * level * 32767).astype(np.int16)
                mix.write(pcm); await asyncio.sleep(0.02)
        await asyncio.sleep(0.4)
        job.closed = True; await asyncio.wait_for(avatar_task, 3)
        fps = (len(video_times) - 1) / (video_times[-1] - video_times[0]) if len(video_times) > 1 else 0
        result.update(received_fps=round(fps, 1), mouth_shapes=sorted(mouth_shapes),
                      closed_after_audio=closed_after_audio, renderer_ms=job.avatar.stats()['ms_per_frame'],
                      voice='Gemini Live' if args.gemini else 'synthetic PCM')
        assert result['video_name'] == TRACK_NAME and result['audio_name'] == 'coach-audio', result
        assert result['video_frames'] >= 30 and result['audible_frames'] >= 10, result
        assert 'rest' in mouth_shapes and len(mouth_shapes) >= 2 and closed_after_audio, result
        assert 8 <= fps <= 17, result
        print({'result': 'PASS', **result}, flush=True)
        print(f'Remote decoded frames: {out}', flush=True)
    finally:
        if job is not None: job.closed = True
        if model is not None: await model.aclose()
        if player is not None: player.stop()
        pending = [t for t in [avatar_task, pump, monitor, *tasks] if t is not None]
        for task in pending: task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for stream in streams: await stream.aclose()
        if player is not None: await player.source.aclose()
        await publisher.disconnect(); await receiver.disconnect()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0]); ap.add_argument('--gemini', action='store_true')
    ap.add_argument('--scenario', choices=['park', 'barista', 'street'], default='park')
    ap.add_argument('--shape', choices=['portrait', 'landscape'], default='portrait')
    ap.add_argument('--fps', type=float, choices=[10, 15], default=15)
    ap.add_argument('--avatar-image', default=None)
    args = ap.parse_args(); asyncio.run(run(args)); gc.collect()  # release cyclic room callbacks before SDK atexit


if __name__ == '__main__': main()
