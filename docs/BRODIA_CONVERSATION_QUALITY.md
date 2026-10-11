# Brodia conversation quality — 2026-10-11

## Reproduced contact failure

The original blocking tool was registered and Gemini **did call it**. The failure
was its interpretation of `appropriate`, not missing function registration.

Before the fix, a real Gemini Live synthetic-audio run used an interested barista,
rapport initialized to 90, and an outcome RNG that always draws 0 (so any nonzero
eligible probability accepts). After an introduction/latte-art compliment, the
caller said: "You are fun to talk to. What's your IG?"

The actual Python trace was:

```json
{"request":"contact","appropriate":false,"uncertain":false,"decision":false,"probability":0.0}
```

Gemini replied that it kept work and personal life separate and did not share
socials. The old tool description told it to mark a request inappropriate when it
"violates the scene," while the scene emphasized working/time boundaries. This
allowed a respectful request at work to be classified as categorically ineligible.
`RapportState.decide()` then set probability to zero, cached the decline, and
recorded a permanent contact boundary. Higher rapport and rewording could never
recover that outcome. IG was recognized in this reproduction; the missing explicit
IG/Insta/handle examples were a separate reliability weakness, not the observed
zero-probability cause.

The previous acceptance direction also forced `brodia@example.invalid` for every
contact method, which made phone/Instagram exchanges sound unnatural. The fix
acts out the exchange without real numbers/handles and reserves that placeholder
for an explicit fictional email request.

## Localized changes

- Stronger interest/neutral/uninterested initiative, humor, follow-ups and spoken
  style, without requiring a question every turn.
- One stable random personality per controller: Playful, Refined, Sassy,
  Bold/flirty, Shy or Bubbly. The choice is independent of difficulty and outcome RNG.
- Explicit phone/IG/Insta/socials/handle mapping to one cached `contact` outcome.
  Respectful requests use `appropriate=true`; actual pressure/boundary violations
  can still decline. Boundary recording must not precede a new decision.
- Natural acceptance/decline directions, no AI disclaimers in harmless roleplay,
  and no invented phone numbers, handles or account linkage.
- Bounded session-history reminders, including early introductions/topics, plus
  clearer evaluator handling of jokes, compliments and playful non-refusals.
- Transcript-free decision diagnostics: invocation counts, flags and results.

Rapport probabilities, hysteresis, per-turn delta bounds, permanent refusals,
Gemini Live, LiveKit, Leda, the mixer and feedback are preserved. No dependency,
new model call in the spoken-response path, landing-page change or artwork change
is included.

## Validation

Offline: `test_brodia_live_engine.py` (14 tests),
`test_brodia_conversation_quality.py` (6 tests), and existing config, Gemini
dispatch, server, feedback, next-call, park-neutral, failure-mode and voice suites
passed. `node scripts/test_brodia_browser.cjs` passed. These validate instructions,
state, actual SDK configuration, dispatch and pipeline contracts; they do not prove
spoken naturalness.

Actual API testing uses `scripts/test_brodia_live_quality.py`. Synthetic caller
speech enters the existing LiveKit `AgentSession` as 16 kHz PCM and receives Gemini
streaming audio through the existing mixer. The live evaluator remains enabled.
Contact/date fixtures initialize rapport to 90 and use controlled outcome draws;
the speech understanding, appropriateness flags, tool invocation and spoken
responses come from the real Gemini API. This tests acceptance mechanics, not
population success rates or naturally accumulated high rapport.

Initial live run:

| Fixture | Observed behavior | Decision trace |
| --- | --- | --- |
| Interested / Playful barista | Specific photography follow-up, pigeon banter, 2 question-containing replies in 4 turns | No unnecessary social tools |
| Interested / Shy barista | Gentle photography follow-up and quieter reactions, 2 question-containing replies in 4 turns | No unnecessary social tools |
| Neutral / Refined barista | Shorter cautious replies, 1 question-containing reply in 4 turns | No unnecessary social tools |
| Uninterested / Sassy barista | Brief replies, no questions, consistent phone then IG declines | 2 contact calls, 1 draw, rejection persisted |
| Interested / Bold/flirty, phone first | Natural phone acceptance followed by consistent IG agreement | Contact accepted with `appropriate=true`; one later cached lookup was skipped |
| Interested / Bubbly, IG first | "Here, give me yours and I'll add you back", then phone agreement | 2 contact calls, 1 draw, same acceptance |
| Interested / Refined, dinner | Natural dinner agreement | Date called with `appropriate=true`, accepted |

The skipped cached lookup led to stronger tool-return and state instructions:
calling again is a lookup, not a reroll. The current test explicitly checks a tool
invocation for each social-request utterance and detects spoken refusal after an
accepted result. Final retest results are recorded below.

The final stricter `--case all` run passed **all eight fixtures**. Interested
Playful asked questions in 3/4 turns, Shy in 1/4, Neutral in 0/4, and Uninterested
asked only a coffee-order service question (1/3). The memory fixture recalled
Alex and street photography after four earlier turns. The differences are
observations from these fixtures, not fixed quotas for future conversations.

| Final social fixture | Tool calls | Draws | Result |
| --- | --- | --- | --- |
| Phone then IG, interested | 2 contact calls, both `appropriate=true` | 1 | Both accepted, same cached outcome |
| IG then phone, interested | 2 contact calls, both `appropriate=true` | 1 | Both accepted, same cached outcome |
| Phone then IG, uninterested | 2 contact calls | 1 | Both declined; second probability 0 due to the persistent boundary |
| Dinner, interested | 1 date call, `appropriate=true` | 1 | Accepted naturally: "That sounds lovely, I finish up around six" |

The isolated PR branch, based on the original main commit without concurrent
avatar/audio changes, separately passed all 10 Python suites and the browser
checks. A real Gemini IG-then-phone retest there also passed: 2 contact calls,
1 draw, natural acceptance, Leda mixer audio, and zero language/evaluator failures.
Its first audio arrived about 1.3 seconds after nominal synthetic input end.

Initial first-audio measurements were 1.4–1.9 seconds after nominal synthetic input
end; the final suite was approximately 1.4–2.0 seconds. Question counts include rhetorical questions and are only a coarse signal;
the synthetic transcripts were reviewed for relevant follow-ups and tone.

All tested calls selected Leda, produced mixer audio, and had zero detected language
failures and zero evaluator errors. No recordings or private conversations were
retained. This is **real Gemini audio with synthetic callers**, not a human
microphone, subjective listening study, browser or LiveKit room/network test.

Run locally (normal API usage, macOS `say` required):

```bash
set -a
source .env.local
set +a
.venv/bin/python scripts/test_brodia_live_quality.py --case all
```

`--show-transcripts` optionally prints only the synthetic test character replies.
Provider exception bodies are suppressed to avoid exposing credentials or dialogue.
Native Live cannot force a named tool on every utterance; blocking is guaranteed
once Gemini invokes it. The suite detects bypasses in its fixtures, but arbitrary
future utterances still depend on model tool-use adherence.
