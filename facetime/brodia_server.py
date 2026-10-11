"""Small local Brodia selector server: mints a short-lived room token and explicit agent dispatch."""
import asyncio, json, os, secrets
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from livekit import api
from facetime.brodia import RoleplayConfig
from facetime.mint_token import mint

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'


async def create_session(data):
    config = RoleplayConfig(data.get('scenario'), data.get('receptivity'))
    room = 'brodia-' + secrets.token_urlsafe(10).lower()
    metadata = json.dumps({'brodia': {'scenario': config.scenario, 'receptivity': config.receptivity}})
    async with api.LiveKitAPI() as lk:
        await lk.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(
            agent_name=os.environ.get('AGENT_NAME', 'brodia'), room=room, metadata=metadata))
    return {'room': room, 'url': os.environ['LIVEKIT_URL'], 'token': mint('brodia-browser', room, ttl_s=600),
            'scenario': config.scenario, 'receptivity': config.receptivity}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(WEB), **kwargs)
    def do_POST(self):
        if self.path != '/api/session': self.send_error(404); return
        try:
            n = int(self.headers.get('Content-Length', '0')); payload = json.loads(self.rfile.read(n))
            body = json.dumps(asyncio.run(create_session(payload))).encode()
            self.send_response(201); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            self.send_error(400, str(e))
        except Exception as e:
            self.send_error(502, 'Unable to start practice session')


def main():
    port = int(os.environ.get('BRODIA_WEB_PORT', '8080'))
    print(f'Brodia selector: http://127.0.0.1:{port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()

if __name__ == '__main__': main()
