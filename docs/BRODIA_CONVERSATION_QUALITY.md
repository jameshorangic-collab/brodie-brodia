# Final Brodia conversation upgrade — 2026-10-11

## Why an accepted contact still failed

The previous PR fixed Gemini marking a respectful Instagram request at work
`appropriate=false`. That was a real zero-probability failure, but it was not the
remaining completion failure.

A real Gemini audio reproduction **after that PR** used synthetic speech:

1. "Hi, I'm Alex. Your latte art is very cool."
2. "Could I get your phone number?"
3. "Okay, what is the number? I am ready to write it down."

The blocking tool was invoked with `appropriate=true`, `uncertain=false`.
Python accepted at rapport **91**, probability **0.6075** (high-rapport fixture,
initial 90 and controlled draw 0). Gemini first said "Here, give me yours", then
"Just shoot me a text so I have your number saved, and I'll send mine right over."
It never supplied the requested number. The follow-up skipped the tool.

**The acceptance instructions prohibited phone numbers and Instagram handles,
even after Python accepted.** They encouraged acting out an exchange without
providing details. This made indefinite deferral consistent with the prompt.
There was also no structured contact receipt: private voice events return before
room publishing, generic `--publish-data` defaults off, and the practice page did
not listen for outcomes. Earlier tests checked agreement, not completion, and
explicitly rejected any spoken number/handle, so they missed this defect.

The reproduced path proves this failure independently of probabilities. We cannot
reconstruct the flags or loaded imports in a past uninstrumented human microphone
call. The active avatar worker was in another checkout; its source contained the
previous fix, but that alone cannot prove its already-imported process version.
That worker and its files were left untouched. New sessions now identify their
engine version and source path when diagnostic mode is enabled.

## Contact completion and safeguards

The existing blocking `decide_social_outcome` remains registered. It now accepts
an optional contact medium and returns instructions containing only approved demo
details. Phone uses **202-555-0147**, within NANPA's reserved fictional
[555-0100–0199 range](https://nanpa.com/numbering/555-line-numbers).
Instagram uses **@brodia-demo.invalid**, deliberately invalid Instagram syntax,
with a visible "fictional label; not a real account" label. It is never linked.
Explicit email requests use `brodia@example.invalid`.

Accepted contacts immediately publish a reliable `brodia.social_outcome` receipt
through LiveKit. The practice screen displays "Contact exchanged! Demo …"; a
subsequent explicit refusal clears the accepted receipt. Only approved contacts
are displayed; transcripts never enter this channel. Scenario/receptivity
selectors, artwork, landing page and FaceTime code are unchanged.

The existing background evaluator also identifies contextual social requests and
audits spoken follow-through. If Gemini misses a first decision (or changes
contact medium without a lookup), the controller calls the **same Python engine**,
reusing existing outcomes and boundaries. Unreliable speech does not trigger this
fallback. A missed/deferred/contradictory exchange can receive a brief correction
through the existing Live session when audio is idle, capped at two corrective
turns per call and suppressed if the caller starts speaking. No additional model
call is added to every spoken response. All explicit refusals remain persistent.

A fallback depends on reliable final transcription and a successful existing
evaluator response; it is not a guarantee for inaudible speech or provider outages.
Native Live tool blocking begins when the model invokes the tool, not before.

No probability retuning: an interested barista at rapport 65 has probability
0.35625; at 90 it is 0.60. Positive conversation raises rapport within the existing
bounds. Acceptance remains random. Phone and Instagram share one contact outcome;
no paraphrase or second medium rerolls rejection. Personality never changes these
probabilities or consumes outcome RNG.

## Stable personality axes and initiative

Each new controller randomly chooses one dominant axis uniformly, fixes it at 3,
and independently chooses 1 or 2 for the other axes. This produces **12 equally
likely profiles** of integer `flirtiness`, `bitchiness`, and `chaos`, independent
of scenario/receptivity. The frozen profile survives every instruction refresh.

- Flirtiness 3: confident teasing, compliments, forward romantic banter and initiative.
- Bitchiness 3: sharp wit, playful roasting, dramatic challenges; attraction can coexist with sarcasm.
- Chaos 3: absurd comparisons, eccentric brief stories, spontaneous topics and dramatic reactions.

Lower levels moderate each behavior. Roasting cannot become cruelty, humiliation,
appearance shaming or identity attacks. All characters remain fictional adults.
An uninterested flirty character may be cheeky without promising contact.
Interested characters reciprocate curiosity, remember topics, and contribute;
neutral characters are more cautious; uninterested characters can decline and
leave. Short American English replies vary questions, reactions and disclosures.

Optional nonsecret demo profiles, selected once per call:

| Environment value | Flirtiness | Bitchiness | Chaos |
| --- | --- | --- | --- |
| `flirty` | 3 | 1 | 2 |
| `bitchy` | 1 | 3 | 2 |
| `chaotic` | 2 | 1 | 3 |
| unset / empty | random | random | random |

Invalid values fail clearly. Every session logs trait levels; with
`BRODIA_DEBUG_CONVERSATION=1`, logs also include engine version/source, request,
native-tool versus guard, appropriateness, uncertainty, score, probability,
cached/boundary status, Python result and the evaluator's spoken-follow-through
category. They do not log dialogue, evaluator reasons or credentials.

## Restart and demo

After merging this PR, pull the merged code and **stop/restart the relevant worker
in its own terminal**. The installed worker has no hot reload. Other checkouts
must be updated separately; restarting an old checkout will still run old code.

```bash
git pull --ff-only
BRODIA_DEBUG_CONVERSATION=1 LINE=1 bash scripts/run.sh coach gemini --agent-name brodia --perception off
```

Keep any existing avatar flags on your worker command; this PR does not change
them. To force a demo profile, prepend one of these to the worker command:

```bash
BRODIA_DEMO_PERSONALITY=flirty
BRODIA_DEMO_PERSONALITY=bitchy
BRODIA_DEMO_PERSONALITY=chaotic
```

For example:

```bash
BRODIA_DEMO_PERSONALITY=chaotic BRODIA_DEBUG_CONVERSATION=1 LINE=1 bash scripts/run.sh coach gemini --agent-name brodia --perception off
```

Unset `BRODIA_DEMO_PERSONALITY` for randomized new calls. Run the selector with
`AGENT_NAME=brodia` **after** loading `.env.local`, so its dispatch name matches:

```bash
set -a
source .env.local
set +a
export AGENT_NAME=brodia
.venv/bin/python -m facetime.brodia_server
```

## Validation

**38 Python tests across 10 suites passed**, plus the selector JavaScript tests
with mocked DOM/LiveKit (nine combinations, camera-denied voice-only behavior,
remote playback, safe contact receipts, decline/cleanup). Offline tests cover all
12 trait profiles, environment overrides, independent outcome RNG, bounded
history, actual installed SDK blocking-tool configuration, missed-tool recovery,
uncertainty, refusal persistence, receipt publishing with generic data off, and
recovery suppression during new caller speech.

**All 12 real Gemini audio fixtures passed** using synthetic macOS caller speech,
existing AgentSession/PCM input, mixer audio and live evaluator:

| Fixture | Result |
| --- | --- |
| Interested, flirtiness 3 | Curious photography follow-ups, teasing, warm reaction to the joke |
| Interested, bitchiness 3 | Playful furry-potato roast, sarcastic photography challenge |
| Interested, chaos 3 | Espresso-machine chatter, dramatic pigeons, eccentric comparisons |
| Neutral, bitchiness 3 | Shorter dry remarks, less reciprocal initiative |
| Uninterested, flirtiness 3 | Brief cheeky response, phone and IG consistently declined |
| Interested phone, initial rapport 90 / draw 0 | Accepted, delivered receipt, spoke 202-555-0147 when asked to read it |
| Interested Instagram, initial rapport 90 / draw 0 | Accepted, delivered receipt, read the fictional demo label when asked |
| Interested decline, draw .99 | IG refusal persisted when reworded as phone; one draw |
| Interested dinner, initial rapport 90 / draw 0 | Natural acceptance through the existing date outcome |
| Memory | Recalled Alex and street photography after earlier turns |
| Random new call A | Profile (1,3,2), stable across replies |
| Random new call B | Profile (1,3,1), stable across replies |

Question-containing replies included rhetorical and service questions; these
counts are not a pacing or naturalness benchmark. The synthetic replies were
reviewed for tone and relevant follow-ups. All fixtures used Leda, produced audio,
had zero evaluator/language failures and no AI disclaimers. First audio arrived
approximately 1.49–2.07 seconds after nominal synthetic input end. This is not a
human microphone latency measurement. Controlled draws test outcome mechanics,
not population success rates. Random profiles can repeat on later calls.

**Two real dispatched worker / LiveKit network / Gemini synthetic-audio calls
passed**. The first used initial rapport 90 with an uncontrolled random draw.
The second used default initial rapport 65, randomized personality (3,2,1), and
an uncontrolled random draw. Both accepted on the first independent room and
delivered phone then IG receipts from the same cached contact decision, with
real audible room audio (2,001 and 2,310 active frames respectively).

The default-score runtime trace covers A–G:

| Step | Observation |
| --- | --- |
| A: loaded engine | `brodia-conversation-2026-10-11.2`, source in the isolated conversation checkout |
| B: tool invocation | SDK executed `decide_social_outcome`, source `gemini_tool` |
| C: flags | `appropriate=true`, `uncertain=false` |
| D: rapport | First contact decision at 66 after the greeting |
| E: probability | 0.3675 (36.75%), normal curve and barista modifier |
| F: Python result | Accept, no prior boundary, initially uncached |
| G: follow-through | Existing evaluator reported fulfilled after acceptance, reading the number, and IG exchange; both receipts arrived |

The IG lookup at current rapport 70 reused the original 0.3675 acceptance rather
than drawing again. Diagnostics expose the current score and original
`decision_score` separately, so a cached probability is not mistaken for a new
calculation. A boundary override has zero probability and no new decision score.

A separate **real Gemini structured-evaluator test (no voice)** exercised the
missing-tool guard: no native decision calls, IG acceptance, cached phone
acceptance, subsequent boundary-consistent decline, and an ordinary Instagram
mention correctly ignored. It made one outcome draw and had zero evaluator errors.

These are synthetic API/room tests plus mocked frontend tests. **No human
microphone or actual browser voice call was performed or claimed.** Audio files
were temporary synthetic inputs only; no private conversations were retained.

To reproduce API quality checks (normal API usage, macOS `say` required):

```bash
set -a
source .env.local
set +a
.venv/bin/python scripts/test_brodia_live_quality.py --case all
```

`--show-transcripts` prints only synthetic character replies. To test the actual
worker/network path, start a worker from this checkout with agent name
`brodia-final-test`, then run `AGENT_NAME=brodia-final-test .venv/bin/python
scripts/test_brodia_live_room.py`. Each declined room remains declined; the script
may create up to four independent new sessions to observe a random acceptance.
It cleans up only its own test rooms. Provider exception bodies are suppressed.


After rebasing onto the concurrently merged avatar PR, all 38 Python checks and
the mocked selector checks passed again. Real Gemini phone and Instagram audio
fixtures were rerun on that integrated branch: both completed the requested
spoken details, delivered the approved receipt, drew once, and had zero
language/evaluator failures. Their first-audio measurements were about 2.15 and
2.25 seconds during concurrent runs. New diagnostics recorded `decision_score=92`
and probability 0.615. No avatar or FaceTime source was changed by this PR.

The combined offline run exited successfully but printed an ignored LiveKit
`FfiHandle.__del__` assertion during interpreter shutdown after the tests passed.
Real Gemini/room runs completed normally. This SDK teardown message was not a
failed test and was not hidden or treated as a human-call verification.
