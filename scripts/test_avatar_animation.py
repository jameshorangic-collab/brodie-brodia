"""Offline behavioral tests for PCM-synchronized animation and the local streaming preview."""
import io
import os
import random
import sys
import threading
import time
import types
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.request import urlopen

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from facetime.audio_out import CueBank, CuePlayer
from facetime.avatar_preview import PreviewHandler
from facetime.brodia_avatar import CharacterAvatar, EXPRESSIONS, agent_audio_level, agent_expression


class Source:
    queued_duration = 0
    async def capture_frame(self, frame): pass
    async def wait_for_playout(self): pass


class AnimationTest(unittest.TestCase):
    def player(self): return CuePlayer(bank=CueBank.disabled(), source=Source())

    def test_rms_tracks_playout_then_stops(self):
        pl = self.player(); pl.source.queued_duration = 0.04
        self.assertIsNone(pl.audio_level())
        with patch('facetime.audio_out.time.monotonic', return_value=100):
            pcm = np.full(480, 3276, np.int16)
            self.assertIs(pl._frame(pcm), pcm)  # audio remains byte-identical
        self.assertEqual(pl.audio_level(100.01), 0)
        self.assertAlmostEqual(pl.audio_level(100.045), 0.1, places=3)
        self.assertEqual(pl.audio_level(100.061), 0)

    def test_silent_frame_closes_without_speaking_hangover(self):
        pl = self.player()
        with patch('facetime.audio_out.time.monotonic', return_value=100): pl._frame(np.full(480, 5000, np.int16))
        with patch('facetime.audio_out.time.monotonic', return_value=100.02): pl._frame(np.zeros(480, np.int16))
        self.assertEqual(pl.audio_level(100.025), 0)
        with patch('facetime.audio_out.time.monotonic', return_value=100.025): self.assertTrue(pl.speaking())

    def test_int16_min_and_bounded_history(self):
        pl = self.player()
        with patch('facetime.audio_out.time.monotonic', return_value=100):
            for _ in range(200): pl._frame(np.full(480, -32768, np.int16))
            self.assertTrue(pl.speaking()); self.assertEqual(pl.audio_level(100.001), 1)
        self.assertLessEqual(len(pl._levels), 64)

    def test_interruption_and_stop_reset_envelope(self):
        pl = self.player(); mix = pl.attach_mixer()
        with patch('facetime.audio_out.time.monotonic', return_value=100): pl._frame(np.full(480, 5000, np.int16))
        mix.clear()
        self.assertEqual(pl.audio_level(100.001), 0); self.assertFalse(pl.speaking())
        pl._frame(np.full(480, 5000, np.int16)); pl.stop()
        self.assertEqual(pl.audio_level(), 0)

    def test_mouth_amplitude_and_immediate_close(self):
        av = CharacterAvatar(size=(270, 480))
        shapes = []
        for level in (0.02, 0.065, 0.18):
            av._mouth_level = 0; shapes.append(av.mouth_shape(False, av.t0, level))
        self.assertEqual(shapes, ['small', 'medium', 'wide'])
        self.assertEqual(av.mouth_shape(True, av.t0, 0), 'rest')
        self.assertEqual(av.mouth_shape(True, av.t0, float('nan')), 'rest')
        self.assertEqual(av.mouth_shape(False, av.t0), 'rest')
        self.assertNotEqual(av.mouth_shape(True, av.t0), 'rest')

    def test_expressions_and_png_alignment(self):
        os.makedirs('data/tmp/avatar-expressions', exist_ok=True)
        for scenario in ('park', 'barista', 'street'):
            av = CharacterAvatar(scenario)
            frames = [av.frame(now=av.t0, blink=False, audio_level=0, expression=expression, motion=False) for expression in EXPRESSIONS]
            for i, expression in enumerate(EXPRESSIONS):
                Image.fromarray(frames[i]).save(f'data/tmp/avatar-expressions/{av.name}-{expression}.png')
                for other in frames[:i]: self.assertFalse(np.array_equal(frames[i], other))
            # Feature-only changes leave the existing PNG body/hair pixels untouched.
            for other in frames[1:]: np.testing.assert_array_equal(frames[0][:200], other[:200])

    def test_auto_expression_does_not_mutate_rapport(self):
        state = types.SimpleNamespace(score=70, boundaries=set(), finished=False)
        session = types.SimpleNamespace(agent_state='listening')
        model = types.SimpleNamespace(controller=types.SimpleNamespace(state=state), session=session)
        job = types.SimpleNamespace(voice=types.SimpleNamespace(model=model), a=types.SimpleNamespace(avatar_expression='auto'))
        self.assertEqual(agent_expression(job), 'playful')
        session.agent_state = 'thinking'; self.assertEqual(agent_expression(job), 'thinking')
        self.assertEqual(agent_expression(job, speaking=True), 'playful')
        session.agent_state = 'listening'; state.score = 45; self.assertEqual(agent_expression(job), 'smiling')
        state.boundaries.add('contact'); self.assertEqual(agent_expression(job), 'neutral')
        job.avatar_expression = 'thinking'; self.assertEqual(agent_expression(job), 'thinking')
        self.assertEqual(state.score, 45); self.assertEqual(state.boundaries, {'contact'})

    def test_transport_fallback_and_coach_compatibility(self):
        job = types.SimpleNamespace(player=types.SimpleNamespace(speaking=lambda _: True))
        self.assertIsNone(agent_audio_level(job))
        av = CharacterAvatar(size=(270, 480))
        self.assertEqual(av.frame(phase='coach', audio_level=0.1, expression='smiling').shape, (480, 270, 3))

    def test_blinks_idle_at_ten_and_fifteen_fps(self):
        for fps in (10, 15):
            av = CharacterAvatar(size=(270, 480), rng=random.Random(4))
            scheduled = av._blink_at - av.t0; self.assertTrue(3 <= scheduled <= 6)
            for i in range(12 * fps): av.frame(now=av.t0 + i / fps, audio_level=0)
            self.assertGreaterEqual(av.blinks, 2)
            x = av.frame(now=av.t0, blink=False, audio_level=0)
            y = av.frame(now=av.t0 + 2, blink=False, audio_level=0)
            self.assertFalse(np.array_equal(x, y))

    def test_preview_serves_real_jpeg_stream(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), PreviewHandler); server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base, timeout=3) as page: self.assertIn(b'Listening (mouth closed)', page.read())
            with urlopen(base + '/stream?voice=demo&expression=playful', timeout=3) as stream:
                self.assertEqual(stream.readline().strip(), b'--frame')
                self.assertIn(b'image/jpeg', stream.readline())
                length = int(stream.readline().split(b':')[1]); stream.readline()
                with Image.open(io.BytesIO(stream.read(length))) as img: self.assertEqual(img.size, (540, 960))
        finally: server.shutdown(); server.server_close(); thread.join(2)


if __name__ == '__main__': unittest.main()
