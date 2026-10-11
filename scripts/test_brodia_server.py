"""Offline contract test for the selector's private LiveKit session endpoint."""
import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from facetime import brodia_server as server


class FakeDispatch:
    def __init__(self): self.requests = []
    async def create_dispatch(self, request): self.requests.append(request)


class FakeLiveKit:
    def __init__(self): self.agent_dispatch = FakeDispatch()
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


def main():
    fake = FakeLiveKit()
    original_api, original_mint = server.api.LiveKitAPI, server.mint
    server.api.LiveKitAPI = lambda: fake
    server.mint = lambda identity, room, ttl_s: f'token:{identity}:{room}:{ttl_s}'
    old = dict(os.environ)
    try:
        os.environ.update(LIVEKIT_URL='wss://example.livekit.cloud', AGENT_NAME='brodia')
        result = asyncio.run(server.create_session({'scenario': 'park', 'receptivity': 'neutral'}))
        assert result['room'].startswith('brodia-') and result['token'].endswith(':600')
        request = fake.agent_dispatch.requests[0]
        assert request.agent_name == 'brodia' and request.room == result['room']
        assert '"scenario": "park"' in request.metadata and '"receptivity": "neutral"' in request.metadata
        try: asyncio.run(server.create_session({'scenario': 'invalid', 'receptivity': 'neutral'}))
        except ValueError: pass
        else: raise AssertionError('invalid session configuration was accepted')
    finally:
        server.api.LiveKitAPI, server.mint = original_api, original_mint
        os.environ.clear(); os.environ.update(old)
    print('Brodia selector session contract: PASS')


if __name__ == '__main__': main()
