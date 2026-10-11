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
LINE=1 bash scripts/run.sh coach gemini --perception off --avatar --mirror-shape landscape
```

Terminal B, one practice call (scenario and receptivity default to `park neutral`):

```bash
bash scripts/run.sh facetime barista uninterested
```

Terminal B creates a room with a one-hour empty-room timeout so manual guest admission does not expire the waiting worker,
then dispatches `brodia` with the selection as metadata (the same `{"brodia": {...}}` contract the web selector uses).
It waits for the agent to join, writes a one-hour connector token to `.local/facetime-oss.json` (mode 0600, gitignored) and runs the connector.

1. On the iPhone, open FaceTime, tap **Create Link** and copy it. Paste it at the hidden prompt.
2. Click **Join** in the Chrome window, then admit the guest on the iPhone.
3. Press **Enter** in Terminal B. Confirm the connector says **receiving audio + video** (order may vary), then say hello.
   The iPhone should show the scenario's female avatar blinking while listening and moving her mouth with Gemini's voice.
4. To finish, press Enter in Terminal B (or **Stop test** in Chrome). The worker ends the job about 2 s after the guest leaves. Run Terminal B again for each new call.

`--no-launch` writes the config and prints the `npx` command without opening Chrome.

## Limits on this path

- **Caller video does not reach the worker.** The connector publishes only the caller's audio (`facetime-caller`), so feedback is voice-only and vision notes stay empty. Do not present this as FaceTime Video analysis.
- `--avatar` publishes `brodia-avatar` alongside the existing Gemini `coach-audio` track. The connector subscribes to one
  audio and one video track from its `targetIdentity`, then forwards both to FaceTime. Without `--avatar` or `--mirror`,
  the iPhone sees the connector's waiting graphic. Use `--mirror-shape landscape`: the connector renders into a 640x360
  canvas, so a portrait track would be stretched. [Connector source](https://github.com/cherthq/chert-facetime-opensource/blob/main/src/livekit.mjs).
- The connector is experimental and tested by Chert on macOS only. Linux is unverified until we complete a call.

## Verified so far (2026-10-11, Linux)

- Dispatch with metadata reaches the worker, which builds the `facetime.brodia` persona.
- A simulated `facetime-guest` audio participant gets bound, and a Gemini session starts for it.
- The connector's view of the agent is exactly one audio track (`coach-audio`).
- **Not yet done:** a real iPhone call through Chrome.

## Avatar validation (2026-10-11, macOS)

An actual LiveKit publisher/subscriber test using Gemini Live received both `brodia-avatar` and `coach-audio`:
173 decoded video frames at 14.9 FPS, 336 audible audio frames, small/medium/wide mouths and a closed mouth after speech;
two idle blinks, 1.69 ms average render time. This proves LiveKit delivery, not the final iPhone hop.
See [AVATAR_ANIMATION.md](AVATAR_ANIMATION.md) for the offline preview and repeatable live test.
