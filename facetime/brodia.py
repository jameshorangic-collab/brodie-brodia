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
