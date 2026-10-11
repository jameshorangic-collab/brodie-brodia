# Brodia real-time avatar animation

Extends merged [PR #25](https://github.com/jameshorangic-collab/brodie-brodia/pull/25), using the existing Jess, Maya and
Nadia PNGs and landmark JSON. No generated video, new model, paid animation service or new audio track.

## Preview first

```bash
.venv/bin/python -m facetime.avatar_preview
```

Open http://127.0.0.1:8091. Select partner, listening/amplitude demo/speaking fallback, expression and shape.
The preview runs at 15 FPS on loopback. The amplitude demo is synthetic, silent and has two-second pauses.
Listening always closes the mouth; all modes retain idle blinks, breathing, sway and tilt.

## Run the existing worker

```bash
# Browser/LiveKit room: omit LINE=1 to use the existing unnamed worker dispatch.
bash scripts/run.sh coach gemini --perception off --avatar --avatar-fps 15

# Chert's connector renders to a landscape canvas; keep the avatar in that shape.
LINE=1 bash scripts/run.sh coach gemini --perception off --avatar --avatar-fps 15 --mirror-shape landscape
# In a second terminal:
bash scripts/run.sh facetime park neutral
```

Admit the Chrome guest on the iPhone and press Enter in the connector terminal. It should report receiving audio + video.
Check a listening blink, speaking mouth movement, and immediate closure on silence. Full steps: [FACETIME_OSS.md](FACETIME_OSS.md).
`--avatar --mirror` still publishes just one outgoing video track, with the caller mirror as an inset when video is available.

## Behavior

- Blink interval: 3–6 seconds, 160 ms closed, visible at both 10 and 15 FPS.
- Breathing uses PR #25's cached plates; sway and a 0.45-degree tilt transform the PNG and facial features together.
- `CuePlayer.audio_level()` reads a bounded RMS envelope from final 24 kHz output PCM. It schedules each 20 ms frame
  using `AudioSource.queued_duration`, so animation follows playout rather than the model's generation-ahead state.
  Quiet PCM closes the mouth. The envelope expires at frame end; mixer interruption/stop clears it immediately.
  Mouth shapes use fast attack and modest release smoothing, with a -42 dBFS silence gate. Metering leaves audio bytes unchanged.
- Speaking-state cycling remains available when a custom/older transport does not expose amplitude.
- Four expressions: `neutral`, `smiling`, `playful` (flirty), `thinking`. `--avatar-expression auto` reads Gemini's thinking
  state and existing rapport: scores below 40 are neutral, 40–64 smiling, 65+ playful. Recorded boundaries or finished
  roleplay suppress playful expressions. Override with `--avatar-expression thinking`, etc.; preview exposes all four.
- Video uses the existing `brodia-avatar` camera track, I420 conversion, no simulcast, 1.2 Mbps, and a 10–15 FPS clamp.
  Gemini continues through the existing `coach-audio` track. Scenario selection, voice, prompts, rapport scoring and feedback
  remain owned by their existing modules. Coach Brodie PNGs remain unmodified after the roleplay.

## Tests and evidence

```bash
.venv/bin/python scripts/test_avatar_animation.py  # amplitude, silence, interruption, expressions, blink, preview stream
.venv/bin/python scripts/test_brodia_avatar.py    # inherited 47 checks, worker publication/inset/feedback/shutdown/timing
set -a
source .env.local
set +a
.venv/bin/python scripts/test_avatar_livekit.py --gemini
.venv/bin/python scripts/test_avatar_livekit.py --scenario street --shape landscape --fps 10
```

The live test uses a fresh isolated room and a separate real LiveKit subscriber; it never opens a mic/camera or logs credentials
or transcripts. Default input is synthetic PCM; `--gemini` requests one short live spoken greeting. Remote decoded frames go to
gitignored `data/tmp/avatar-livekit/`; expression samples go to `data/tmp/avatar-expressions/`.

Verified on 2026-10-11: 10 new offline tests and 47 inherited checks pass. Real Gemini Live + LiveKit delivered 173 video frames
at 14.9 FPS and 336 audible audio frames. All three amplitude mouth shapes and a closed mouth after speech were observed;
the character blinked twice and rendering averaged 1.69 ms. A real iPhone/FaceTime call still needs link creation and guest admission.
