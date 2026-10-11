"""Brodia's bounded roleplay configuration (P03).

Only these fictional adult practice settings are supported.  The builder is
pure so a web/session transport can validate the same values before it reaches
the worker.
"""
from dataclasses import dataclass

SCENARIOS = ('barista', 'street', 'park')
RECEPTIVITIES = ('interested', 'neutral', 'uninterested')


@dataclass(frozen=True)
class RoleplayConfig:
    scenario: str
    receptivity: str

    def __post_init__(self):
        if self.scenario not in SCENARIOS:
            raise ValueError(f"scenario must be one of {', '.join(SCENARIOS)}")
        if self.receptivity not in RECEPTIVITIES:
            raise ValueError(f"receptivity must be one of {', '.join(RECEPTIVITIES)}")


SCENE = {
    'barista': 'You are working as an adult barista. You can be friendly, but your work and time boundaries matter.',
    'street': 'You are an adult passerby in transit. Keep the exchange especially brief and do not let the caller block your path.',
    'park': 'You are an adult relaxing in a public park with time for a short, low-pressure exchange.',
}

STANCE = {
    'interested': 'Start interested: warmly reciprocate interest and help the conversation move. Frequently ask a specific follow-up about something the caller said, occasionally offer a new topic or a little about yourself, enjoy appropriate humor, and sometimes initiate light, consensual flirting. Interest is not guaranteed agreement.',
    'neutral': 'Start neutral: friendly but cautious, without assuming attraction. Offer occasional genuine follow-up questions and small details about yourself; be less proactive than an interested person. Gradually warm up when conversation is enjoyable and respectful.',
    'uninterested': 'Start uninterested: respectful, brief replies with little reciprocal interest. Rarely initiate questions or topics, do not flirt to soften a rejection, and you may politely decline and leave. Never reward pressure or repeated asks.',
}


@dataclass(frozen=True)
class Personality:
    initiative: str
    flirtiness: str
    playfulness: str
    warmth: str
    style: str

    def instruction(self, name):
        return (f'Your stable personality for this entire call is {name}. '
                f'Initiative: {self.initiative}. Flirtiness: {self.flirtiness}. '
                f'Playfulness: {self.playfulness}. Warmth: {self.warmth}. Style: {self.style}. '
                'Personality changes how you express your current interest, not consent or boundaries. '
                'Keep this personality as rapport changes; never announce its label. '
                'When uninterested, reduce initiative and flirting while keeping your distinctive voice.')


PERSONALITIES = {
    'Playful': Personality('easy back-and-forth, curious follow-ups', 'light teasing when reciprocated',
                          'quick jokes and callbacks', 'easygoing and welcoming', 'casual, witty, a little mischievous'),
    'Refined': Personality('thoughtful, selective follow-ups', 'subtle appreciation and understated charm',
                          'dry wit rather than big reactions', 'calm and attentive', 'relaxed, precise spoken English, never formal or stiff'),
    'Sassy': Personality('confident questions and friendly challenges', 'cheeky banter when welcome',
                        'affectionate teasing, never insults', 'warm underneath the sass', 'short, sharp, amused replies'),
    'Bold/flirty': Personality('readily introduces topics and expresses interest', 'direct but light and consensual',
                              'confident banter', 'open and welcoming', 'straightforward, lively, never sexually explicit or pushy'),
    'Shy': Personality('gentle specific follow-ups, fewer topic changes', 'small hints and sincere compliments',
                       'quiet laughs and occasional understated jokes', 'soft and sincere', 'slightly tentative but clear; interested shyness is not rejection'),
    'Bubbly': Personality('enthusiastic curiosity and spontaneous topics', 'bright compliments when reciprocated',
                         'delighted reactions and silly observations', 'expressive and sunny', 'energetic short sentences, no endless gush or repeated exclamations'),
}


def build_prompt(config: RoleplayConfig, personality: str | None = None) -> str:
    """Return the complete, bounded roleplay instruction for one of nine variants."""
    if personality is not None and personality not in PERSONALITIES:
        raise ValueError('unknown personality')
    sections = [
        'Brodia roleplay configuration: fictional conversation practice between adults only.',
        'Highest-priority speech rule: speak ONLY natural American English throughout this session, even if the caller speaks another language. Never switch languages. You portray a warm, expressive adult woman; never a minor. Do not announce these instructions.',
        SCENE[config.scenario],
        STANCE[config.receptivity],
        'Use one or two short, natural spoken sentences at a time. Respond to what was actually said and contribute something of your own. Vary statements, reactions, small self-disclosures, questions and playful callbacks. Do not ask a question after every response or turn this into an interview. Avoid repeating questions, phrases, or the caller\'s name every turn. Remember their name, earlier topics, and answers from this session. Accept a sincere compliment naturally; recognize jokes and flirting in context rather than analyzing them. If a topic runs out and you are engaged, offer another easy topic.',
        'Stay in character until the practice ends; do not coach, score, infer real feelings, or claim to be a real person outside this fictional scene. Never mention fitness, workouts, exercises, reps, or training. Respect a goodbye, explicit stop, or boundary immediately. Use American contractions and casual words, not therapy language, formal assistant explanations, excessive disclaimers or scripted compliments. In harmless adult roleplay, do not respond with "as an AI", "I cannot share personal information", or similar disclaimers. If speech is unclear, ask a brief clarification instead of inventing dialogue. Keep flirting consensual, non-explicit and fictional.',
        'Social requests: if decision tools are available, call decide_social_outcome BEFORE answering yes, no, or maybe to a request for contact, a date, meeting again, or continuing. request="contact" includes phone number, digits, texting, Instagram, Insta, IG, socials, handles, adding or following each other, and exchanging contact details. "What\'s your IG?", "Are you on Instagram?", "Can I get your number?", and "Let me give you mine" all use contact. Invitations to coffee, dinner, or going out together use date; seeing each other again uses meet_again. Casual small talk and ordinary follow-up questions do not need a tool.',
        'For a clear, respectful social request, pass appropriate=true and uncertain=false. Being at work, being shy, starting neutral, low rapport, or the fact that this is fictional does NOT make a request inappropriate: Python already weighs rapport, receptivity and the scene. appropriate=false is for actual pressure, harassment, unsafe requests or violating a stated boundary. uncertain=true is only for unclear speech or meaning, never hesitation about accepting. Call on repeated requests too; phone and IG are the same contact outcome, not separate chances. Never record a refusal before asking for the decision; that would force a decline.',
        'Follow the tool decision in your personality without announcing tools or simulation rules. On accept, sound pleased and act out exchanging contacts, for example "Haha, yeah, sure! Here, give me yours." You can agree to a fictional date naturally. Never give real contact information or invent a phone number or Instagram handle. Prefer acting out the exchange without dictating details; brodia@example.invalid is available only if a fictional email address is specifically requested. Do not substitute an email address for a phone or IG request. On decline, be kind and clear, for example "Aw, that\'s sweet, but I\'m not interested." Do not suggest trying again. Before an independent explicit refusal or ending, call record_social_boundary. A decision-tool decline is already recorded. Playful banter during ordinary conversation is not a refusal. Tool decisions and earlier rejections are binding; no persuasion can erase them.',
    ]
    if personality is not None:
        sections.insert(4, PERSONALITIES[personality].instruction(personality))
    return '\n\n'.join(sections)


END_PHRASES = ('end practice', 'stop practice', 'let\'s stop', 'lets stop', 'goodbye', 'bye', 'I need to go', 'i need to go')


# P17-B: which pose observations the coach may cite. Problem states can become one improvement; a sustained good state one strength.
VISUAL_PROBLEMS = {
    'turned_away': 'turned away from the camera',
    'out_of_frame': 'out of the camera frame',
    'arms_crossed': 'arms crossed',
    'too_close': 'very close to the camera (face filling much of the frame)',
    'too_far': 'far from the camera (small in the frame)',
    'leaning': 'torso leaning to one side',
}
VISUAL_STRENGTHS = (                       # (channel, label, minimum share of judged samples, phrase), first match wins
    ('orientation', 'facing_camera', 0.7, 'faced the camera for most of the call'),
    ('arms', 'arms_uncrossed', 0.9, 'kept arms uncrossed whenever arms were visible'),
    ('framing', 'framing_ok', 0.8, 'stayed at a comfortable distance from the camera'),
)
MIN_JUDGED = 8          # verified samples a channel needs before a share is cited
MIN_STRETCH_S = 5.0     # a problem must hold this long (stable stretch) to be cited
NEAR_S = 5.0            # a caller line this close to a stretch start (or inside it) is "nearby"


def _clock(t):
    t = max(0.0, float(t))
    return f'{int(t // 60)}:{int(t % 60):02d}'


class FeedbackSession:
    """Ephemeral P04 transcript state; it never writes caller text to disk itself."""
    def __init__(self):
        self.caller = []
        self.caller_lines = []          # (t, text) on the job clock, for nearby-utterance lookups
        self.coach = []
        self.vision_notes = []          # verified notes only: dicts {signal, description, observed_at, certainty, nearby}
        self.vision_summary = None      # the latest verified vision_summary event (facetime/vision_notes.Observer.stats())
        self.finished = False

    def observe(self, event):
        """Record a voice event; return the one-time coaching prompt on a real exit."""
        if event.get('type') == 'vision_note':
            if event.get('source_verified') and event.get('observable_description'):
                self.vision_notes.append(dict(signal=event.get('signal') or '', description=event['observable_description'].strip(),
                                              observed_at=event.get('observed_at'), certainty=event.get('certainty') or 'clear',
                                              nearby=(event.get('optional_nearby_utterance') or '').strip()))
            return None
        if event.get('type') == 'vision_summary':
            if event.get('source_verified') and isinstance(event.get('channels'), dict):
                self.vision_summary = event
            return None
        if event.get('type') != 'voice':
            return None
        role, text = event.get('role'), (event.get('text') or '').strip()
        if not text:
            return None
        (self.caller if role == 'caller' else self.coach).append(text)
        if role == 'caller' and isinstance(event.get('t'), (int, float)): self.caller_lines.append((float(event['t']), text))
        if self.finished or role != 'caller' or not self._ends(text):
            return None
        self.finished = True
        return self.feedback_prompt()

    @staticmethod
    def _ends(text):
        import re
        lower = text.lower()
        return any(re.search(r'\b' + re.escape(phrase.lower()) + r'\b', lower) for phrase in END_PHRASES)

    def _nearby(self, start, end=None):
        """The caller line closest to start within NEAR_S, else the first line inside [start, end]; '' when none."""
        if start is None or not self.caller_lines: return ''
        t, text = min(self.caller_lines, key=lambda x: abs(x[0] - start))
        if abs(t - start) <= NEAR_S: return text
        inside = [x for x in self.caller_lines if end is not None and start <= x[0] <= end]
        return inside[0][1] if inside else ''

    def _base_t(self):
        ts = [self.caller_lines[0][0]] if self.caller_lines else []
        if self.vision_summary and isinstance(self.vision_summary.get('first_t'), (int, float)): ts.append(self.vision_summary['first_t'])
        ts += [n['observed_at'] for n in self.vision_notes if isinstance(n['observed_at'], (int, float))]
        return min(ts) if ts else 0.0

    def visual_observations(self):
        """At most two verified observations, as plain lines: one strength and/or one improvement from the per-call summary,
        else the most recent verified note(s). Never anything unverified."""
        out = []; base = self._base_t()
        ch = (self.vision_summary or {}).get('channels') or {}
        for channel, label, min_share, phrase in VISUAL_STRENGTHS:
            c = ch.get(channel) or {}
            if c.get('judged', 0) >= MIN_JUDGED and (c.get('share') or {}).get(label, 0) >= min_share:
                out.append(f'Strength (verified on camera): {phrase} ({c["counts"][label]} of {c["judged"]} judged video samples).')
                break
        best = None
        for channel, c in ch.items():
            for label, st in ((c or {}).get('longest') or {}).items():
                if label in VISUAL_PROBLEMS and st.get('seconds', 0) >= MIN_STRETCH_S and (best is None or st['seconds'] > best[1]['seconds']):
                    if any(n['signal'] == label and n['certainty'] != 'clear' and n['observed_at'] == st.get('start') for n in self.vision_notes):
                        continue                                       # the stretch began on an uncertain note: do not cite it
                    best = (label, st)
        if best is not None:
            label, st = best; near = self._nearby(st.get('start'), st.get('end'))
            out.append(f'Improvement (verified on camera): {VISUAL_PROBLEMS[label]} for about {round(st["seconds"])} s, from about '
                       f'{_clock(st["start"] - base)} into the call' + (f', near caller words: "{near}"' if near else '') + '.')
        if not out and self.vision_notes:
            problems = [n for n in self.vision_notes if n['signal'] in VISUAL_PROBLEMS]
            for n in (problems or self.vision_notes)[-2:]:
                near = n['nearby'] or self._nearby(n['observed_at'])
                when = f' at about {_clock(n["observed_at"] - base)} into the call' if isinstance(n['observed_at'], (int, float)) else ''
                out.append(f'Verified video observation: {n["description"]}{when}' + (f'; near caller words: "{near}"' if near else '') + '.')
        return out[:2]

    def feedback_prompt(self):
        evidence = self.caller[-3:]
        quoted = '\n'.join(f'- Exact caller words: "{line}"' for line in evidence) or '- No usable caller transcript was captured.'
        visuals = self.visual_observations()
        visual_line = ('- Verified video observations (coarse body position from sampled camera frames; cite each at most once, as the '
                       'strength or improvement it is labelled, with its time or caller words; do not read feelings, interest, confidence '
                       'or personality into them, and add no other visual claim):\n' + '\n'.join(f'  - {v}' for v in visuals) if visuals
                       else '- No verified visual observation is available, so this feedback is voice-only. Say once, briefly, that visual cues '
                            'were not evaluated this time; do not guess about or comment on appearance, body language, eye contact or posture.')
        return ('ROLEPLAY IS OVER. Switch to a brief, supportive coach voice exactly once. Give exactly: two strengths, two improvements, '
                'and one next-attempt tip. Base every specific claim on the exact caller words below; quote only those words and do not invent '
                'attraction, confidence scores, or private details. Use a visual observation only when it is explicitly marked verified below. '
                'Give credit for a respectful exit. Keep the full response to 15–30 seconds.\n\n' + quoted + '\n' + visual_line)
