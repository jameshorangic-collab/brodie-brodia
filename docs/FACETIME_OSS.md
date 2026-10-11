# Testing Brodia on real FaceTime without the shared line

Uses Chert's open-source connector ([cherthq/chert-facetime-opensource](https://github.com/cherthq/chert-facetime-opensource), npm `@trychert/facetime-opensource@0.1.2`). A Chrome window on this laptop joins **your own FaceTime link** as a browser guest and bridges it to a LiveKit room where the `brodia` worker is waiting. No Chert slot is needed, and nothing has to be released afterwards.

```text
iPhone (FaceTime link) <-> Chrome guest + connector (laptop) <-> LiveKit room brodia-ft-* <-> brodia worker
```

## Needs

- Node 22.22+ and `npx`
- **Google Chrome** (the connector launches Playwright's `chrome` channel; Chromium does not count). On Fedora: `sudo dnf install https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm`
- An iPhone with FaceTime, and the repo's usual `.env.local` and `.venv`

## Run

Terminal A, the worker registered under its dispatch name:

```bash
cd /Users/james/brodie-brodia
bash scripts/run.sh coach gemini --agent-name brodia-final-facetime --perception off --avatar --avatar-image assets/avatar/brodia-girl.png --avatar-fps 15 --mirror-shape landscape
```

Terminal B, one practice call (scenario and receptivity default to `park neutral`):

```bash
cd /Users/james/brodie-brodia
bash scripts/run.sh facetime barista interested --agent-name brodia-final-facetime
```

Terminal B creates a room with a one-hour empty-room timeout so manual guest admission does not expire the waiting worker,
then dispatches the explicitly named worker with the selection as metadata (the same `{"brodia": {...}}` contract the web selector uses).
`--agent-name` on both commands keeps the production worker and connector aligned even if `.env.local` names another worker.
It waits for **both `coach-audio` and `brodia-avatar` on the same agent**, writes a fresh one-hour connector token to
`.local/facetime-oss.json` (mode 0600, gitignored) with that agent's exact participant identity, and runs the connector.
If either publication is missing, it stops with the required worker flags instead of opening a silent waiting face.

1. On the iPhone, open FaceTime, tap **Create Link** and copy it. Paste it at the hidden prompt.
2. Click **Join** in the Chrome window, then admit the guest on the iPhone.
3. Press **Enter** in Terminal B. Confirm the connector says **receiving audio + video** (order may vary), then say hello.
   The iPhone should show the scenario's female avatar blinking while listening and moving her mouth with Gemini's voice.
4. Say **"goodbye"**, **"end practice"**, or **"end this conversation"** to switch to Coach Brodie and hear feedback.
   Wait for feedback before hanging up. Then press Enter in Terminal B (or **Stop test** in Chrome). The worker ends the
   job about 2 s after the guest leaves. Run Terminal B again for each new call.

`--no-launch` writes the config and prints the `npx` command without opening Chrome.
Always create each new session through `scripts/run.sh facetime`; do not reuse `.local/facetime-avatar.json` from
the older checkout or reconnect an old guest after starting a new worker. Stop any previous connector with Ctrl+C first.

## Limits on this path

- **Caller video does not reach the worker.** The connector publishes only the caller's audio (`facetime-caller`), so feedback is voice-only and vision notes stay empty. Do not present this as FaceTime Video analysis.
- `--avatar` publishes `brodia-avatar` alongside the existing Gemini `coach-audio` track. The connector subscribes to one
  audio and one video track from its `targetIdentity`, then forwards both to FaceTime. The launcher requires `--avatar`.
  Include `--avatar-image assets/avatar/brodia-girl.png` to use the supplied girl. Use `--mirror-shape landscape`:
  the connector renders into a 640x360 canvas, so a portrait track would be stretched.
  [Connector source](https://github.com/cherthq/chert-facetime-opensource).
- The connector is experimental and tested by Chert on macOS only. Linux is unverified until we complete a call.

## Earlier dispatch validation (2026-10-11, Linux)

- Dispatch with metadata reaches the worker, which builds the `facetime.brodia` persona.
- A simulated `facetime-guest` audio participant gets bound, and a Gemini session starts for it.
- The connector's view of the agent is exactly one audio track (`coach-audio`).
- That test did not include a real iPhone; the macOS call below does.

## Production integration validation (2026-10-11, macOS + real iPhone)

Compared production `main` at `38af2b1` with `/Users/james/brodia-avatar-live` at `75678c8`:
the avatar renderer, illustration, audio mixer, FaceTime launcher and worker publication code were already merged.
PR #28's engine `brodia-conversation-2026-10-11.2` was loaded in the production worker; nothing was copied over it.

The old connector process had been started from the other checkout with `.local/facetime-avatar.json`, referring
to a different room and exact agent identity than the production worker's fresh `.local/facetime-oss.json`.
Inspected the actual installed Chert 0.1.2 `sdk.mjs`, `media.mjs`, `hop.mjs` and packaged `dist/livekit.js`:

- LiveKit filters subscriptions by `targetIdentity`; its "receiving audio + video" message counts subscriptions.
- Agent audio feeds the connector's outgoing Web Audio destination; decoded agent video is painted on its canvas.
- A local WebRTC hop sends those to the FaceTime tab, which supplies them as the guest's microphone/camera.
- The FaceTime peer's received caller audio travels over the reverse hop and is published as `facetime-caller`.
- The green Chert face is the fallback while a room video element is not decoded, so worker publication logs alone
  cannot establish that the iPhone is receiving the right session.

Stopped the stale connector and opened a fresh guest **from the production checkout using its current room/agent**.
The caller admitted it and confirmed the supplied girl, audible Gemini replies, incoming microphone and animated mouth
on the actual iPhone. An independent LiveKit subscriber also measured audible `facetime-caller` and `coach-audio`,
and decoded the 960x540 `brodia-avatar`. No connector fork or worker media replacement was needed.

The first closing request, "end this conversation", failed because Python's old `END_PHRASES` omitted it.
The later "I have to go. Bye" did trigger the coach avatar and spoken feedback in the call logs.
Expanded natural closing phrases, retained the one-time feedback transition, and moved its diagnostic into the
executed Brodia event branch. The new launcher readiness checks and explicit dispatch-name option prevent the same
configuration mistake from silently reaching the phone.

Offline regression checks:

```bash
.venv/bin/python scripts/test_facetime_oss.py
.venv/bin/python scripts/test_brodia_feedback.py
.venv/bin/python scripts/test_brodia_conversation_quality.py
.venv/bin/python scripts/test_brodia_live_engine.py
.venv/bin/python scripts/test_brodia_avatar.py
.venv/bin/python scripts/test_avatar_animation.py
```

For the new closing phrase, the opt-in `scripts/test_facetime_feedback_live.py --worker-log <fresh-worker-log>`
dispatches the configured `AGENT_NAME`, speaks synthetic English through LiveKit into the real Gemini worker,
and checks one feedback transition, one coach-avatar transition, audible returned speech and decoded landscape video.
This is a **synthetic voice network test**, distinct from the human iPhone test above.
It passed from the updated production checkout: one feedback transition, one coach-avatar transition,
1,313 audible frames during the closing/feedback exchange and 710 decoded 960x540 video frames.

## Avatar validation (2026-10-11, macOS)

An actual LiveKit publisher/subscriber test using Gemini Live received both `brodia-avatar` and `coach-audio`:
173 decoded video frames at 14.9 FPS, 336 audible audio frames, small/medium/wide mouths and a closed mouth after speech;
two idle blinks, 1.69 ms average render time. This proves LiveKit delivery, not the final iPhone hop.
See [AVATAR_ANIMATION.md](AVATAR_ANIMATION.md) for the offline preview and repeatable live test.
