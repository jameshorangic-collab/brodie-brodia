// Brodia's narrow startup adapter for the pinned Chert 0.1.2 CLI.
// Media, Chrome ownership, configuration validation and cleanup stay in Chert.
import { readFile, realpath, mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { dirname, join, delimiter, resolve } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';

export async function connectorPackage(searchPath = process.env.PATH ?? '') {
  for (const directory of searchPath.split(delimiter)) {
    try {
      const executable = await realpath(join(directory, 'facetime-opensource'));
      const root = dirname(dirname(executable));
      const manifest = JSON.parse(await readFile(join(root, 'package.json'), 'utf8'));
      if (manifest.name === '@trychert/facetime-opensource' && manifest.version === '0.1.2') return root;
    } catch { /* Continue through PATH; never inspect configuration or credentials. */ }
  }
  throw new Error('Pinned Chert 0.1.2 not found. Start this adapter through scripts/run.sh facetime.');
}

export async function waitForAdmission(guest, input, signal, pollMs = 250) {
  const gate = new AbortController();
  const combined = AbortSignal.any([signal, gate.signal]);
  const manual = input.question('Click Join in Chrome and admit the guest on your iPhone. Brodia connects automatically; Enter is a fallback after admission:\n', { signal: combined });
  const automatic = (async () => {
    while (!combined.aborted) {
      // The SDK's FaceTime media shim captures only FaceTime's incoming caller
      // audio here. The inter-tab hop uses NativePeer and does not count as a
      // caller. Never use the connector tab's LiveKit subscriptions as admission.
      let ready;
      try { ready = await guest._face.evaluate(() => window.__chertSpike?.snapshot().incomingAudio > 0); }
      catch { throw new Error('FaceTime media status unavailable. Stop and launch a fresh guest.'); }
      if (ready) return;
      await delay(pollMs, undefined, { signal: combined });
    }
    combined.throwIfAborted();
  })();
  try {
    await Promise.race([manual, automatic]);
    signal.throwIfAborted();
  } finally {
    gate.abort(); // Cancel the losing readline question/poll before Chert asks Stop.
    await Promise.allSettled([manual, automatic]);
  }
}

export function patchedCli(source, sdkUrl, adapterUrl) {
  const replacements = [
    ["import { FaceTimeGuest } from './sdk.mjs';", `import { FaceTimeGuest } from ${JSON.stringify(sdkUrl)};\nimport { waitForAdmission } from ${JSON.stringify(adapterUrl)};`],
    ["await input.question('')", "await input.question('', { signal: abort.signal })"],
    ["await ask('Click Join in Chrome, then admit the guest on your iPhone. Press Enter here ONLY after admission:');", 'await waitForAdmission(guest, input, abort.signal);'],
  ];
  for (const [before, after] of replacements) {
    if (source.split(before).length !== 2) throw new Error('Chert CLI changed; refusing an incompatible startup adapter.');
    source = source.replace(before, after);
  }
  return source;
}

async function main() {
  const root = await connectorPackage();
  const cli = patchedCli(await readFile(join(root, 'src/cli.mjs'), 'utf8'),
    pathToFileURL(join(root, 'src/sdk.mjs')).href, import.meta.url);
  const local = fileURLToPath(new URL('../.local/', import.meta.url));
  await mkdir(local, { recursive: true, mode: 0o700 });
  const temporary = await mkdtemp(join(local, 'chert-startup-'));
  try {
    const entry = join(temporary, 'cli.mjs');
    await writeFile(entry, cli, { mode: 0o600 });
    await import(pathToFileURL(entry).href);
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  // Do not await at module scope: the temporary CLI imports our helpers.
  main().catch(() => {
    console.error('[facetime] Connector startup failed. Check Node/Chrome and launch again with scripts/run.sh facetime. Private details omitted.');
    process.exitCode = 1;
  });
}
