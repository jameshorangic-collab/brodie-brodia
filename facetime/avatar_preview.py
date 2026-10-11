"""Loopback-only, offline animated avatar preview. No Gemini, LiveKit, camera or microphone.

Run: .venv/bin/python -m facetime.avatar_preview
Open http://127.0.0.1:8091. Controls exercise idle, PCM-envelope demo, fallback and four expressions.
"""
import argparse
import math
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import cv2

from facetime.brodia_avatar import CharacterAvatar, EXPRESSIONS, SIZES

HTML = b'''<!doctype html><html><head><meta charset="utf-8"><title>Brodia animation preview</title>
<style>body{background:#15252c;color:#fff;font:16px system-ui;text-align:center;margin:20px}
select{font:inherit;margin:8px;padding:6px}img{display:block;margin:12px auto;max-height:76vh;max-width:95vw;border-radius:16px}
p{color:#cad5d8}</style></head><body><h2>Brodia live animation preview</h2>
<label>Partner <select id="scenario"><option value="brodia">Brodia illustration</option><option value="park">Maya</option><option value="barista">Jess</option><option value="street">Nadia</option></select></label>
<label>Voice <select id="voice"><option value="listening">Listening (mouth closed)</option><option value="demo">Amplitude demo with pauses</option><option value="fallback">Speaking-state fallback</option></select></label>
<label>Expression <select id="expression"><option>neutral</option><option>smiling</option><option value="playful">playful / flirty</option><option>thinking</option></select></label>
<label>Shape <select id="shape"><option>portrait</option><option>landscape</option></select></label>
<p>15 FPS. Blinks every 3\xe2\x80\x936 seconds. Demo voice is a synthetic envelope; no audio is played or recorded.</p>
<img id="avatar" alt="Animated Brodia avatar"><script>
function update(){let q=new URLSearchParams();for(let id of ['scenario','voice','expression','shape'])q.set(id,document.getElementById(id).value);
document.getElementById('avatar').src='/stream?'+q.toString()}
document.querySelectorAll('select').forEach(s=>s.onchange=update);update();</script></body></html>'''


def demo_level(t):
    """Speech-like syllables plus a two-second listening pause every six seconds."""
    if t % 6 >= 4: return 0.0
    return max(0.0, 0.09 + 0.085 * math.sin(t * 18) + 0.025 * math.sin(t * 31))


class PreviewHandler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == '/':
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers(); self.wfile.write(HTML); return
        if url.path != '/stream':
            self.send_error(404); return
        q = parse_qs(url.query)
        value = lambda key, default: q.get(key, [default])[0]
        scenario = value('scenario', 'park'); expression = value('expression', 'neutral')
        voice = value('voice', 'listening'); shape = value('shape', 'portrait')
        if scenario not in ('brodia', 'park', 'barista', 'street') or expression not in EXPRESSIONS or shape not in SIZES or voice not in ('listening', 'demo', 'fallback'):
            self.send_error(400); return
        if scenario == 'brodia':
            from facetime.illustrated_avatar import IllustratedAvatar
            from facetime.brodia_avatar import PARTS
            import os
            av = IllustratedAvatar(os.path.join(PARTS, 'brodia-girl.png'), size=SIZES[shape])
        else:
            av = CharacterAvatar(scenario, size=SIZES[shape])
        self.send_response(200); self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        self.send_header('Cache-Control', 'no-store'); self.end_headers()
        self.connection.settimeout(2.0)
        deadline = time.monotonic()
        try:
            while True:
                now = time.monotonic(); t = now - av.t0
                level = None if voice == 'fallback' else demo_level(t) if voice == 'demo' else 0.0
                rgb = av.frame(now=now, speaking=voice != 'listening', audio_level=level, expression=expression)
                ok, jpeg = cv2.imencode('.jpg', cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
                if not ok: return
                payload = jpeg.tobytes()
                self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload + b'\r\n')
                self.wfile.flush(); deadline += 1 / 15
                time.sleep(max(0, deadline - time.monotonic()))
                deadline = max(deadline, time.monotonic())
        except (BrokenPipeError, ConnectionResetError, TimeoutError): pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0]); ap.add_argument('--port', type=int, default=8091)
    a = ap.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', a.port), PreviewHandler); server.daemon_threads = True
    print(f'Avatar preview: http://127.0.0.1:{server.server_port} (Ctrl+C to stop)', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == '__main__': main()
