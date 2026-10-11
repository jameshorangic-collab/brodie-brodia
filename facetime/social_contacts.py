"""Approved fictional contacts. No real phone routing or social-account links."""
import re

DEMO_CONTACTS = {
    'phone': '202-555-0147',  # NANPA reserves 555-0100..0199 for fictional use.
    'instagram': '@brodia-demo.invalid',  # deliberately invalid Instagram syntax
    'email': 'brodia@example.invalid',
}
CONTACT_METHODS = ('phone', 'instagram', 'email', 'unspecified')


def contact_method(text):
    """Hint only, never a consent/rapport classifier. Full requests are evaluated contextually."""
    lower = text.lower()
    if re.search(r"\b(?:instagram|insta|ig|handle|socials)\b", lower):
        return 'instagram'
    if re.search(r"\b(?:phone|number|digits|text(?:ing)?)\b", lower):
        return 'phone'
    if re.search(r"\b(?:email|e-mail)\b", lower):
        return 'email'
    return 'unspecified'


def contact_instruction(method):
    method = method if method in DEMO_CONTACTS else 'phone'
    detail = DEMO_CONTACTS[method]
    if method == 'instagram':
        return (f'Complete the exchange now: agree naturally to giving your Insta. '
                f'The practice screen shows the fictional demo contact {detail}, not a real account. '
                'If asked for the handle, read this demo label; never invent or link a real account.')
    return (f'Complete the exchange now: agree naturally and give the approved demo {method}: {detail}. '
            'You can say "Yeah, sure! Here, give me your phone." '
            'If asked what the number/address is, read these exact demo details rather than defer. '
            'Never say you will text it later, invent other details, or claim a real message was sent.')


def outcome_event(outcome, method):
    method = method if method in DEMO_CONTACTS else 'phone'
    return {'type': 'social_outcome', 'request': outcome.request, 'accepted': outcome.accepted,
            'contact_method': method if outcome.request == 'contact' else 'unspecified',
            'demo_contact': DEMO_CONTACTS[method] if outcome.accepted and outcome.request == 'contact' else None}
