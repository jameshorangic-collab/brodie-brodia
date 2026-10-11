"""Ephemeral, Python-owned rapport and social outcomes; no network or transcript logs.

Scores and probabilities are simulation tuning, not estimates of real attraction.
The evaluator supplies observations; these rules own bounds and consent history.
"""
from dataclasses import dataclass, field
import math
import random

from facetime.brodia import RoleplayConfig

REQUESTS = ('contact', 'date', 'meet_again', 'continue')
BANDS = ('very reserved', 'polite but cautious', 'comfortable', 'warm and engaged', 'very receptive')


@dataclass(frozen=True)
class RapportSettings:
    initial: dict = field(default_factory=lambda: {'interested': 65, 'neutral': 40, 'uninterested': 15})
    max_delta: int = 4
    hysteresis: int = 3
    probability_points: tuple = ((0, .02), (20, .02), (40, .12), (60, .40), (80, .70), (100, .90))

    def __post_init__(self):
        if set(self.initial) != {'interested', 'neutral', 'uninterested'}:
            raise ValueError('initial values must configure all three receptivities')
        if any(type(v) is not int or not 0 <= v <= 100 for v in self.initial.values()):
            raise ValueError('initial rapport must be integer 0..100')
        if type(self.max_delta) is not int or not 1 <= self.max_delta <= 10:
            raise ValueError('max_delta must be integer 1..10')
        if type(self.hysteresis) is not int or not 0 <= self.hysteresis <= 10:
            raise ValueError('hysteresis must be integer 0..10')
        points = self.probability_points
        if len(points) < 2 or points[0][0] != 0 or points[-1][0] != 100:
            raise ValueError('probability curve must span 0..100')
        if any(not 0 <= p < 1 for _, p in points) or any(a[0] >= b[0] or a[1] > b[1] for a, b in zip(points, points[1:])):
            raise ValueError('probability points must increase and remain below 1')


@dataclass(frozen=True)
class Evaluation:
    rapport_delta: int
    reason: str
    interaction_type: str
    reliable: bool
    # The speaker has set an explicit boundary, not merely started reserved.
    boundary: str = 'none'

    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict):
            raise ValueError('evaluation must be an object')
        delta, kind, reliable = data.get('rapport_delta'), data.get('interaction_type'), data.get('reliable')
        reason, boundary = data.get('reason'), data.get('boundary', 'none')
        if type(delta) is not int or not -10 <= delta <= 10 or type(reliable) is not bool:
            raise ValueError('invalid evaluator delta/reliability')
        if kind not in ('positive', 'neutral', 'negative', 'uncertain') or not isinstance(reason, str) or not reason.strip():
            raise ValueError('invalid evaluator type/reason')
        if boundary not in ('none', 'all', *REQUESTS):
            raise ValueError('invalid boundary')
        if (kind == 'positive' and delta < 0) or (kind == 'negative' and delta > 0) or (kind in ('neutral', 'uncertain') and delta != 0):
            raise ValueError('delta does not match interaction type')
        return cls(delta, reason[:240], kind, reliable, boundary)


def acceptance_probability(score, points):
    if not isinstance(score, (int, float)) or not math.isfinite(score):
        raise ValueError('rapport must be finite')
    score = min(100, max(0, score))
    for (lo, p0), (hi, p1) in zip(points, points[1:]):
        if score <= hi:
            return p0 + (p1 - p0) * (score - lo) / (hi - lo)
    return points[-1][1]


@dataclass(frozen=True)
class Outcome:
    request: str
    accepted: bool
    probability: float
    reason: str

    def instruction(self):
        return {
            'request': self.request,
            'decision': 'accept' if self.accepted else 'decline',
            'direction': 'Express this decision naturally in American English. Do not reroll or reverse it. '
                         'On a later social request, call decide_social_outcome again even for a stored decision: '
                         'Python returns the cached outcome without rerolling. '
                         'Stay in character without AI or privacy disclaimers. '
                         + ('Sound pleased and act out exchanging contacts (e.g. "Yeah, sure! Give me yours.") '
                            'or agree naturally to the proposed plan. Never invent phone numbers or Instagram handles. '
                            'Respond to the requested contact method; do not invent linked accounts or claim details were already exchanged. '
                            'Only for an explicit fictional email request may you use brodia@example.invalid.'
                            if self.accepted else
                            'Decline kindly and clearly. Do not flirt around the refusal, suggest trying again, or offer contact details.'),
        }


class RapportState:
    def __init__(self, config: RoleplayConfig, settings=None, rng=None):
        self.config = config
        self.settings = settings or RapportSettings()
        self.rng = rng or random.Random()
        self.score = self.settings.initial[config.receptivity]
        self.band = min(4, max(0, (self.score - 1) // 20))
        self.processed = set()
        self.boundaries = set()
        self.outcomes = {}
        self.evaluations = []
        self.last_signature = None
        self.finished = False

    def apply(self, turn_id, evaluation, text):
        if turn_id in self.processed or self.finished:
            return 0
        self.processed.add(turn_id)
        if not evaluation.reliable or evaluation.interaction_type == 'uncertain':
            return 0
        signature = ' '.join(text.lower().split())
        delta = max(-self.settings.max_delta, min(self.settings.max_delta, evaluation.rapport_delta))
        # Adjacent repetition is never a positive farming opportunity. Semantic
        # repetition, pressure, timing and humor are judged using context upstream.
        if signature == self.last_signature and delta > 0:
            delta = 0
        self.last_signature = signature
        old = self.score
        self.score = min(100, max(0, self.score + delta))
        self.evaluations.append(evaluation)
        self.evaluations = self.evaluations[-24:]
        self._smooth_band()
        return self.score - old

    def _smooth_band(self):
        while self.band < 4 and self.score > (self.band + 1) * 20 + self.settings.hysteresis:
            self.band += 1
        while self.band > 0 and self.score < self.band * 20 - self.settings.hysteresis:
            self.band -= 1

    def record_boundary(self, request):
        if request not in ('all', *REQUESTS):
            raise ValueError('unknown boundary')
        self.boundaries.add(request)
        if request in ('date', 'meet_again'):
            self.boundaries.update(('date', 'meet_again'))  # synonyms cannot reroll a refusal

    def decide(self, request, *, appropriate=True, uncertain=False):
        if request not in REQUESTS:
            raise ValueError('unknown social request')
        if type(appropriate) is not bool or type(uncertain) is not bool:
            raise ValueError('outcome flags must be booleans')
        # Explicit later boundaries override even an earlier acceptance.
        if self.finished or 'all' in self.boundaries or request in self.boundaries:
            return Outcome(request, False, 0, 'boundary or ended practice')
        if request in self.outcomes:
            return self.outcomes[request]
        if uncertain:
            return None  # Clarify; do not spend a random draw or cache a refusal.
        modifiers = {'interested': 1., 'neutral': .85, 'uninterested': .55}
        situation = {'barista': .75, 'street': .45, 'park': 1.}[self.config.scenario]
        p = acceptance_probability(self.score, self.settings.probability_points)
        p *= modifiers[self.config.receptivity]
        p *= 1. if request == 'continue' else situation
        if not appropriate:
            p = 0.
        accepted = p > 0 and self.rng.random() < p
        outcome = Outcome(request, accepted, p, 'simulation outcome')
        self.outcomes[request] = outcome
        if not accepted:
            self.record_boundary(request)
        return outcome

    def behavior_instruction(self):
        descriptions = (
            'Keep replies brief and reserved, with little reciprocal interest. You may politely leave.',
            'Be polite but cautious, answering briefly with occasional reciprocal curiosity.',
            'Be comfortable and conversational; sometimes initiate a topic or enjoy a fitting joke.',
            'Be warm and engaged: frequently ask relevant follow-ups, offer your own details, occasionally introduce a topic, and enjoy fitting banter or light flirting in your personality.',
            'Be very receptive: actively reciprocate curiosity, help the exchange flow, and sometimes initiate consensual light flirting in your personality.',
        )
        outcomes = {k: 'accepted' if v.accepted else 'declined' for k, v in self.outcomes.items()}
        return ('Private application state; never reveal the score or stages. ' + descriptions[self.band] +
                ' Change gradually, keep your stable personality, original scene and autonomy. Do not ask a question after every reply. Explicit boundaries remain binding at every level. '
                f'Binding boundaries: {sorted(self.boundaries)}. Resolved requests: {outcomes}. '
                'Any contact/date/meet-again/continue request MUST use decide_social_outcome before speaking an answer. '
                'This includes EACH later request for another contact method (phone then IG or IG then phone). '
                'A stored decision is not permission to skip the tool; Python looks it up without a new random draw. '
                'Do not make these decisions yourself. Do not announce tool calls.')
