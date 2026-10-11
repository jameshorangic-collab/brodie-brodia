import assert from 'node:assert/strict';
import { test } from 'node:test';
import { setTimeout as delay } from 'node:timers/promises';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { connectorPackage, patchedCli, waitForAdmission } from './facetime_connector.mjs';

function terminal() {
  const pending = new Set();
  const input = {
    question(_prompt, { signal }) {
      return new Promise((resolve, reject) => {
        const request = { resolve: value => { pending.delete(request); resolve(value); } };
        pending.add(request);
        signal.addEventListener('abort', () => { pending.delete(request); reject(signal.reason); }, { once: true });
      });
    },
    enter() { for (const request of [...pending]) request.resolve(''); },
    get pending() { return pending.size; },
  };
  return input;
}

test('subscribed room tracks and local hop do not trigger admission; actual caller does', async () => {
  const input = terminal(), abort = new AbortController();
  let caller = false, finished = false, polls = 0;
  const guest = { _face: { evaluate: async () => { polls++; return caller; } },
                  _connector: { evaluate: () => { throw new Error('Wrong media direction'); } },
                  status: async () => ({ audio: true, video: true, mediaLinkConnected: true }) };
  const waiting = waitForAdmission(guest, input, abort.signal, 1).then(() => { finished = true; });
  await delay(15);
  assert.ok(polls > 0); assert.equal(finished, false); assert.equal(input.pending, 1);
  caller = true;
  await waiting;
  assert.equal(input.pending, 0, 'Automatic connection left an outstanding Enter prompt');
  // The Stop question must consume the next Enter, not the canceled admission question.
  const stop = input.question('Stop', { signal: abort.signal });
  input.enter(); await stop;
});

test('manual Enter remains a fallback and cancels the polling loop', async () => {
  const input = terminal(), abort = new AbortController();
  let polls = 0;
  const guest = { _face: { evaluate: async () => { polls++; return false; } } };
  const waiting = waitForAdmission(guest, input, abort.signal, 1);
  input.enter(); await waiting;
  const done = polls;
  await delay(10);
  assert.equal(polls, done); assert.equal(input.pending, 0);
});

test('canceling admission ends both the terminal question and timer', async () => {
  const input = terminal(), abort = new AbortController();
  const guest = { _face: { evaluate: async () => false } };
  const waiting = waitForAdmission(guest, input, abort.signal, 1);
  abort.abort();
  await assert.rejects(waiting, { name: 'AbortError' });
  assert.equal(input.pending, 0);
});

test('browser media failures never disclose private navigation details', async () => {
  const input = terminal(), abort = new AbortController();
  const guest = { _face: { evaluate: async () => { throw new Error('private URL or token'); } } };
  await assert.rejects(waitForAdmission(guest, input, abort.signal, 1), /FaceTime media status unavailable/);
  assert.equal(input.pending, 0);
});

test('adapter matches the actual pinned npm CLI and rejects changed source', async () => {
  const root = await connectorPackage();
  const source = await readFile(join(root, 'src/cli.mjs'), 'utf8');
  const patched = patchedCli(source, 'file:///sdk.mjs', 'file:///adapter.mjs');
  assert.ok(patched.includes('await waitForAdmission(guest, input, abort.signal)'));
  assert.ok(patched.includes('await guest.connect()'), 'Original Chert media connection was replaced');
  assert.ok(patched.includes('await guest?.close()'), 'Original Chert cleanup was replaced');
  assert.throws(() => patchedCli(patched, 'file:///sdk.mjs', 'file:///adapter.mjs'), /incompatible startup adapter/);
});
