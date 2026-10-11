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
    'interested': 'You are open to a short conversation, but do not promise attraction, contact information, or a future meeting.',
    'neutral': 'You are polite and may exchange a few words, but do not signal or promise romantic interest.',
    'uninterested': 'You are not interested in continuing. State a concise boundary and leave politely; never reward pressure or repeated asks.',
}


def build_prompt(config: RoleplayConfig) -> str:
    """Return the complete, bounded roleplay instruction for one of nine variants."""
    return "\n\n".join((
        'Brodia roleplay configuration: fictional conversation practice between adults only.',
        SCENE[config.scenario],
        STANCE[config.receptivity],
        'Use one or two natural sentences at a time. Respond only to what was actually said. Stay in roleplay until the practice ends; do not coach, score, infer feelings, or claim to be a real person. Respect a goodbye, explicit stop, or boundary immediately.',
    ))


END_PHRASES = ('end practice', 'stop practice', 'let\'s stop', 'lets stop', 'goodbye', 'bye', 'I need to go', 'i need to go')


class FeedbackSession:
    """Ephemeral P04 transcript state; it never writes caller text to disk itself."""
    def __init__(self):
        self.caller = []
        self.coach = []
        self.finished = False

    def observe(self, event):
        """Record a voice event; return the one-time coaching prompt on a real exit."""
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
        lower = text.lower()
        return any(phrase in lower for phrase in END_PHRASES)

    def feedback_prompt(self):
        evidence = self.caller[-3:]
        quoted = '\n'.join(f'- Exact caller words: "{line}"' for line in evidence) or '- No usable caller transcript was captured.'
        return ('ROLEPLAY IS OVER. Switch to a brief, supportive coach voice exactly once. Give exactly: two strengths, two improvements, '
                'and one next-attempt tip. Base every specific claim on the exact caller words below; quote only those words and do not invent '
                'visual observations, attraction, confidence scores, or private details. Give credit for a respectful exit. Keep the full response '
                'to 15–30 seconds.\n\n' + quoted)
