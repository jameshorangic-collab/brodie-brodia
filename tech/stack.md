# Brodia runtime baseline

This is the Brodie-derived implementation repository for the Brodia LiveKit
worker. The canonical LiveKit dispatch name is `brodia`.

## Verified local baseline

- Python runtime: `.venv/bin/python` (Python 3.12)
- Dependency source: `requirements.txt`
- Worker entry point: `python -m facetime.worker`
- Environment template: `.env.example`; `.env.local` is ignored by Git

## Safe setup and checks

```sh
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env.local
AGENT_NAME=brodia .venv/bin/python -m facetime.worker --help
python scripts/test_voice.py
```

To run a real LiveKit worker, populate `LIVEKIT_URL`, `LIVEKIT_API_KEY`,
`LIVEKIT_API_SECRET`, and the applicable voice-provider values in `.env.local`.
Load that file locally, then start the worker with:

```sh
set -a && source .env.local && set +a
AGENT_NAME=brodia .venv/bin/python -m facetime.worker --voice gemini dev
```

## Current verification boundary

The local runtime, ignored secret file, dispatch-name default, and worker help
path are verifiable without credentials. A completed bidirectional LiveKit call,
interruption behavior, and sponsor eligibility remain unverified until the team
uses its assigned LiveKit project and test credentials. Do not treat worker
registration alone as proof of a completed call.
