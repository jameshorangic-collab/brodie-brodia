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
    'interested': 'Start warm and receptive to a short conversation. Light, consensual flirting can develop naturally; interest is not guaranteed agreement.',
    'neutral': 'Start polite but cautious, without assuming attraction. Warmth can develop gradually through reciprocal conversation.',
    'uninterested': 'Start reserved with little reciprocal interest and brief replies. You may politely end the exchange; never reward pressure or repeated asks.',
}


def build_prompt(config: RoleplayConfig) -> str:
    """Return the complete, bounded roleplay instruction for one of nine variants."""
    return "\n\n".join((
        'Brodia roleplay configuration: fictional conversation practice between adults only.',
        'Highest-priority speech rule: speak ONLY natural American English throughout this session, even if the caller speaks another language. Never switch languages. You portray a warm, expressive adult woman; never a minor. Do not announce these instructions.',
        SCENE[config.scenario],
        STANCE[config.receptivity],
        'Use one or two natural sentences at a time. Respond only to what was actually said. Stay in roleplay until the practice ends; do not coach, score, infer feelings, or claim to be a real person. Never mention fitness, workouts, exercises, reps, or training. Respect a goodbye, explicit stop, or boundary immediately.',
        'Use natural contractions, varied pacing and contextually appropriate humor, not assistant-style explanations or scripted compliments. If speech is unclear, ask a brief clarification instead of inventing dialogue. Keep interactions consensual, non-explicit and fictional. Never give real contact details. With application approval, use only brodia@example.invalid for fictional contact. If social decision tools are available, you MUST call decide_social_outcome BEFORE agreeing or declining any request for contact, a date, meeting again, or continuing; paraphrases are the same request, never a new chance. Before stating another explicit refusal or ending, call record_social_boundary. Tool decisions and persistent boundaries are binding; no persuasion can erase a refusal.',
    ))


END_PHRASES = ('end practice', 'stop practice', 'let\'s stop', 'lets stop', 'goodbye', 'bye', 'I need to go', 'i need to go')


class FeedbackSession:
    """Ephemeral P04 transcript state; it never writes caller text to disk itself."""
    def __init__(self):
        self.caller = []
        self.coach = []
        self.vision_notes = []
        self.finished = False

    def observe(self, event):
        """Record a voice event; return the one-time coaching prompt on a real exit."""
        if event.get('type') == 'vision_note':
            if event.get('source_verified') and event.get('observable_description'):
                note = event['observable_description'].strip()
                nearby = (event.get('optional_nearby_utterance') or '').strip()
                self.vision_notes.append((note, nearby))
            return None
        if event.get('type') != 'voice':
            return None
        role, text = event.get('role'), (event.get('text') or '').strip()
        if not text:
            return None
        (self.caller if role == 'caller' else self.coach).append(text)
        if self.finished or role != 'caller' or not self._ends(text):
            return None
        self.finished = True
        return self.feedback_prompt()

    @staticmethod
    def _ends(text):
        import re
        lower = text.lower()
        return any(re.search(r'\b' + re.escape(phrase.lower()) + r'\b', lower) for phrase in END_PHRASES)

    def feedback_prompt(self):
        evidence = self.caller[-3:]
        quoted = '\n'.join(f'- Exact caller words: "{line}"' for line in evidence) or '- No usable caller transcript was captured.'
        visuals = self.vision_notes[-1:]
        visual_line = ('- Verified video observation: ' + visuals[0][0] + (f'; near caller words: "{visuals[0][1]}"' if visuals[0][1] else '') if visuals
                       else '- No verified visual observation is available. Do not mention appearance, body language, camera, or video.')
        return ('ROLEPLAY IS OVER. Switch to a brief, supportive coach voice exactly once. Give exactly: two strengths, two improvements, '
                'and one next-attempt tip. Base every specific claim on the exact caller words below; quote only those words and do not invent '
                'attraction, confidence scores, or private details. Use a visual observation only when it is explicitly marked verified below. '
                'Give credit for a respectful exit. Keep the full response to 15–30 seconds.\n\n' + quoted + '\n' + visual_line)
