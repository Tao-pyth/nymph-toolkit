// SPDX-License-Identifier: Apache-2.0
// Real optional native dependencies and helper process, without a Discord login.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const adapter = fileURLToPath(new URL('../../src/nymph_toolkit/adapters/discord_voice/', import.meta.url));
const require = createRequire(path.join(adapter, 'node/package.json'));

test('locked dependencies load DAVE and round-trip Opus PCM', () => {
  const voice = require('@discordjs/voice');
  assert.match(voice.generateDependencyReport(), /@snazzah\/davey: 0\.1\.12/);
  const Opus = require('opusscript');
  const encoder = new Opus(48000, 2, Opus.Application.AUDIO);
  try {
    const pcm = Buffer.alloc(3840);
    const decoded = encoder.decode(encoder.encode(pcm, 960));
    assert.equal(decoded.length, pcm.length);
    assert.equal(decoded.some(value => value !== 0), false);
  } finally {
    encoder.delete();
  }
});

test('real bridge loads dependencies and exits without credential or network login', { timeout: 10000 }, async () => {
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
    ['PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'TMPDIR'].includes(key.toUpperCase())));
  const child = spawn(process.execPath, [path.join(adapter, 'bridge.mjs')], { env, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
  const ended = once(child, 'close');
  let stdout = '', stderr = '';
  child.stdout.on('data', chunk => { stdout += chunk; });
  child.stderr.on('data', chunk => { stderr += chunk; });
  try {
    child.stdin.write(JSON.stringify({ type: 'start', node_modules_path: path.join(adapter, 'node'),
      guild_id: '100', voice_channel_id: '200', participants: ['300'] }) + '\n');
    const [code] = await ended;
    assert.equal(code, 0);
    assert.equal(stderr, '');
    assert.deepEqual(stdout.trim().split('\n').map(JSON.parse), [{ type: 'stopped', reason: 'credential_missing' }]);
  } finally {
    child.stdin.destroy();
    if (child.exitCode === null) child.kill();
    await ended;
  }
});
