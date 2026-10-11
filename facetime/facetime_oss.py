"""Put a Brodia session on a real FaceTime call through Chert's open-source connector (no shared line).

Dispatches the `brodia` worker into a fresh room with the chosen scenario/receptivity, waits for both media tracks,
mints a one-hour token for the connector's browser guest, writes it to .local/facetime-oss.json (0600, gitignored) and
runs `npx @trychert/facetime-opensource --config` on it. The connector prompts privately for the FaceTime link.

Start the worker first with Gemini, --avatar --avatar-image assets/avatar/brodia-girl.png --mirror-shape landscape.
Use matching --agent-name values on the worker and this command; see docs/FACETIME_OSS.md for the exact two commands.

The connector forwards caller AUDIO only (track "facetime-caller"); caller video does not reach the worker on this path,
so feedback is voice-only. Needs Node 22.22+, installed Google Chrome and an iPhone that creates the FaceTime link.
"""
import argparse, asyncio, json, os, secrets, subprocess, sys
from pathlib import Path
from livekit import api
from facetime.brodia import RoleplayConfig
from facetime.mint_token import mint

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / '.local' / 'facetime-oss.json'
GUEST_IDENTITY = 'facetime-guest'
CONNECTOR = '@trychert/facetime-opensource@0.1.2'


async def dispatch_and_wait(config, timeout_s, agent_name=None):
    agent_name = agent_name or os.environ.get('AGENT_NAME', 'brodia')
    room = 'brodia-ft-' + secrets.token_urlsafe(8).lower()
    metadata = json.dumps({'brodia': {'scenario': config.scenario, 'receptivity': config.receptivity}})
    async with api.LiveKitAPI() as lk:
        # Agents do not keep an empty room alive. Manual FaceTime guest admission can exceed
        # LiveKit's default five-minute timeout; match the connector token's one-hour lifetime.
        await lk.room.create_room(api.CreateRoomRequest(name=room, empty_timeout=3600))
        await lk.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(
            agent_name=agent_name, room=room, metadata=metadata))
        last_tracks = []
        for _ in range(int(timeout_s * 2)):
            res = await lk.room.list_participants(api.ListParticipantsRequest(room=room))
            agents = [p.identity for p in res.participants if p.kind == api.ParticipantInfo.Kind.AGENT]
            for participant in res.participants:
                if participant.identity not in agents:
                    continue
                last_tracks = [t.name for t in participant.tracks]
                # Chert filters by this exact participant identity, then subscribes to
                # one audio and one video track. Joining alone is not media readiness.
                if {'coach-audio', 'brodia-avatar'}.issubset(last_tracks):
                    print('[facetime] Worker media ready: coach-audio + brodia-avatar', flush=True)
                    return room, participant.identity
            await asyncio.sleep(0.5)
    raise SystemExit(f'Worker {agent_name!r} did not publish coach-audio + brodia-avatar in {room!r} within '
                     f'{timeout_s:.0f} s (published: {last_tracks}). Start the worker with --agent-name {agent_name} '
                     '--voice gemini --perception off --avatar --avatar-image assets/avatar/brodia-girl.png '
                     '--mirror-shape landscape against the same LiveKit project.')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('scenario', nargs='?', default='park'); ap.add_argument('receptivity', nargs='?', default='neutral')
    ap.add_argument('--timeout', type=float, default=30.0, help='seconds to wait for the dispatched agent to join')
    ap.add_argument('--agent-name', help='dispatch name of the worker started in this checkout (overrides AGENT_NAME)')
    ap.add_argument('--no-launch', action='store_true', help='only write the connector config and print the next command')
    a = ap.parse_args()
    config = RoleplayConfig(a.scenario, a.receptivity)
    room, agent = asyncio.run(dispatch_and_wait(config, a.timeout, a.agent_name))
    CONFIG.parent.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump({'url': os.environ['LIVEKIT_URL'], 'token': mint(GUEST_IDENTITY, room, ttl_s=3600), 'targetIdentity': agent}, f)
    print(f'[facetime] {config.scenario} + {config.receptivity}: room {room!r}, agent {agent!r} joined; connector config in {CONFIG.relative_to(ROOT)}', flush=True)
    cmd = ['npx', '-y', CONNECTOR, '--config', str(CONFIG)]
    if a.no_launch:
        print(' '.join(cmd)); return
    print('[facetime] Create a FaceTime link on your iPhone (FaceTime > Create Link), paste it at the hidden prompt, click Join in '
          'Chrome, admit the guest on the iPhone, then press Enter here.', flush=True)
    sys.exit(subprocess.call(cmd))


if __name__ == '__main__':
    main()
