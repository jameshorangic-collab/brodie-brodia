// Real selector JavaScript with mocked DOM/LiveKit; no frontend dependencies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
const source = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];

async function test(scenario, receptivity) {
  const nodes = {
    '#start': {}, '#leave': {}, '#status': {},
    '#media': { elements: [], append(e) { this.elements.push(e); }, replaceChildren() { this.elements = []; } },
  };
  let sent, active;
  const audio = { kind: 'audio', attach: () => ({}), mediaStreamTrack: { getSettings: () => ({ sampleRate: 48000 }) } };
  class Room {
    constructor(options) {
      active = this; this.options = options; this.events = {};
      this.localParticipant = {
        enableCameraAndMicrophone: async () => { this.microphone = true; },
        trackPublications: new Map([['audio', { track: audio }]]),
      };
    }
    on(name, fn) { this.events[name] = fn; }
    async connect(url, token) { assert.equal(url, 'wss://example.invalid'); assert.equal(token, 'offline-token'); }
    async startAudio() { this.audioStarted = true; }
    async disconnect() { this.disconnected = true; }
  }
  const context = {
    document: { querySelector(selector) { return selector.includes('name=s') ? { value: scenario } : selector.includes('name=r') ? { value: receptivity } : nodes[selector]; } },
    console: { info() {} },
    LivekitClient: { Room, RoomEvent: { TrackSubscribed: 'track', Disconnected: 'disconnect' } },
    fetch: async (url, options) => {
      assert.equal(url, '/api/session'); sent = JSON.parse(options.body);
      return { ok: true, json: async () => ({ url: 'wss://example.invalid', token: 'offline-token', ...sent }) };
    },
  };
  vm.runInNewContext(source, context);
  await nodes['#start'].onclick();
  assert.deepEqual(sent, { scenario, receptivity });
  const capture = active.options.audioCaptureDefaults;
  assert.equal(capture.echoCancellation, true); assert.equal(capture.noiseSuppression, true);
  assert.equal(capture.autoGainControl, true); assert.equal(capture.channelCount, 1);
  assert.equal(active.audioStarted, true); assert.equal(active.microphone, true);
  assert.equal(nodes['#media'].elements[0].muted, true); // no local audio loopback
  active.events.track({ attach: () => ({ muted: false }) });
  assert.equal(nodes['#media'].elements[1].muted, false); // Gemini remains audible
  await nodes['#leave'].onclick();
  assert.equal(active.disconnected, true); assert.equal(nodes['#media'].elements.length, 0);
}

(async () => {
  for (const scenario of ['barista', 'street', 'park']) {
    for (const stance of ['interested', 'neutral', 'uninterested']) await test(scenario, stance);
  }
  console.log('9/9 browser selections, audio preferences, local mute, remote playback and disconnect: PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
