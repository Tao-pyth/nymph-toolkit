// SPDX-License-Identifier: Apache-2.0
// These are bridge behavior tests with a controlled SDK, not a live Discord test.
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import test from 'node:test';
import { configuration, participants, receive } from '../../src/nymph_toolkit/adapters/discord_voice/bridge.mjs';

const config = () => ({ type: 'start', node_modules_path: process.cwd(), guild_id: '100', voice_channel_id: '200', participants: ['300'] });
function fixture(blockAt = null) {
  const channel = { id: '200', guildId: '100', type: 2, guild: { voiceAdapterCreator: {} },
    members: new Map([['900', {}], ['300', {}]]), permissionsFor: () => ({ has: () => true }) };
  let client, deletes = 0, joins = 0;
  const entered = Promise.withResolvers(), released = Promise.withResolvers();
  async function checkpoint(stage) {
    if (blockAt === stage) { entered.resolve(); await released.promise; }
  }
  class Client extends EventEmitter {
    constructor() { super(); client = this; this.user = { id: '900' }; this.channels = { fetch: async () => { await checkpoint('fetch'); return channel; } }; }
    async login(token) { assert.equal(token, 'private-test-token'); await checkpoint('login'); }
    async destroy() { this.destroyed = true; }
  }
  const connection = new EventEmitter();
  connection.voicePrivacyCode = 'verified-test-code';
  connection.state = { status: 'ready' };
  const streams = new Map();
  connection.receiver = { speaking: new EventEmitter(), subscribe: user => {
    const stream = new EventEmitter(); stream.destroy = () => { stream.destroyed = true; };
    streams.set(user, stream); return stream;
  } };
  connection.destroy = () => { connection.destroyed = true; };
  class Opus {
    static Application = { AUDIO: 1 };
    decode(packet) { return packet; }
    delete() { deletes++; }
  }
  const dependencies = { Client, GatewayIntentBits: { Guilds: 1, GuildVoiceStates: 2 }, ChannelType: { GuildVoice: 2 },
    PermissionFlagsBits: { ViewChannel: 1, Connect: 2 }, Opus,
    voice: { joinVoiceChannel: options => { joins++; assert.equal(options.daveEncryption, true); assert.equal(options.selfDeaf, false); return connection; },
      entersState: async () => { await checkpoint('ready'); }, VoiceConnectionStatus: { Ready: 'ready' }, EndBehaviorType: { AfterSilence: 1 } } };
  return { dependencies, channel, connection, streams, entered: entered.promise, release: released.resolve,
    get client() { return client; }, get deletes() { return deletes; }, get joins() { return joins; } };
}

async function ready(frames) {
  for (let i = 0; i < 100; i++) {
    if (frames.some(f => f.type === 'ready' || f.type === 'stopped')) return;
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.fail('Bridge did not reach an observable state');
}

test('strict configuration and complete current-participant consent', () => {
  assert.deepEqual(configuration(config()), config());
  for (const value of [null, { ...config(), participants: ['300', '300'] }, { ...config(), guild_id: 100 }, { ...config(), token: 'secret' }]) {
    assert.throws(() => configuration(value));
  }
  const channel = { members: new Map([['900', {}], ['300', {}], ['400', {}]]) };
  assert.throws(() => participants(channel, '900', ['300']), /consent_missing/);
  assert.deepEqual(participants(channel, '900', ['400', '300']), ['300', '400']);
});

test('ready requires DAVE, PCM is bounded, participant change ends reception', async () => {
  const f = fixture(), commands = new EventEmitter(), frames = [];
  process.env.NTK_DISCORD_TOKEN = 'private-test-token';
  const task = receive(config(), frame => { frames.push(frame); return true; }, commands, f.dependencies);
  await ready(frames);
  assert.deepEqual(frames[0], { type: 'ready', participants: ['300'], dave: true });
  assert.equal(process.env.NTK_DISCORD_TOKEN, undefined);
  f.connection.receiver.speaking.emit('start', '300');
  f.streams.get('300').emit('data', Buffer.alloc(3840));
  assert.equal(Buffer.from(frames[1].pcm, 'base64').length, 3840);
  f.client.emit('voiceStateUpdate', { channelId: '200' }, { id: '300', channelId: null });
  await task;
  assert.equal(frames.at(-1).reason, 'participants_changed');
  assert.equal(f.deletes, 1);
  assert.equal(f.client.destroyed, true);
  assert.equal(f.connection.destroyed, true);
  assert.equal(f.streams.get('300').destroyed, true);
  assert.equal(JSON.stringify(frames).includes('private-test-token'), false);
  const count = frames.length;
  f.streams.get('300').emit('data', Buffer.alloc(3840));
  assert.equal(frames.length, count);
});

test('unconsented speaker and malformed PCM stop without forwarding data', async () => {
  for (const unauthorized of [true, false]) {
    const f = fixture(), commands = new EventEmitter(), frames = [];
    process.env.NTK_DISCORD_TOKEN = 'private-test-token';
    const task = receive(config(), frame => { frames.push(frame); return true; }, commands, f.dependencies);
    await ready(frames);
    f.connection.receiver.speaking.emit('start', unauthorized ? '400' : '300');
    if (!unauthorized) f.streams.get('300').emit('data', Buffer.alloc(96004));
    await task;
    assert.equal(frames.filter(x => x.type === 'pcm').length, 0);
    assert.equal(frames.at(-1).reason, unauthorized ? 'consent_or_dave_changed' : 'audio_decode_failed');
  }
});

test('lost DAVE status, explicit stop and output pressure reclaim owned resources', async () => {
  for (const mode of ['dave', 'stop', 'pressure']) {
    const f = fixture(), commands = new EventEmitter(), frames = [];
    process.env.NTK_DISCORD_TOKEN = 'private-test-token';
    const task = receive(config(), frame => { frames.push(frame); return mode !== 'pressure' || frame.type !== 'pcm'; }, commands, f.dependencies);
    await ready(frames);
    f.connection.receiver.speaking.emit('start', '300');
    if (mode === 'dave') f.connection.voicePrivacyCode = '';
    if (mode === 'stop') commands.emit('stop');
    else f.streams.get('300').emit('data', Buffer.alloc(3840));
    await task;
    assert.equal(frames.at(-1).reason, { dave: 'audio_decode_failed', stop: 'requested', pressure: 'output_capacity' }[mode]);
    assert.equal(f.deletes, 1);
    assert.equal(f.connection.destroyed, true);
  }
});

test('stop during startup never creates a late connection or resumes reception', { timeout: 5000 }, async () => {
  for (const stage of ['login', 'fetch', 'ready']) {
    const f = fixture(stage), commands = new EventEmitter(), frames = [];
    process.env.NTK_DISCORD_TOKEN = 'private-test-token';
    const task = receive(config(), frame => { frames.push(frame); return true; }, commands, f.dependencies);
    await f.entered;
    commands.emit('stop');
    await new Promise(resolve => setImmediate(resolve));
    f.release();
    await task;
    assert.deepEqual(frames, [{ type: 'stopped', reason: 'requested' }], stage);
    assert.equal(f.joins, stage === 'ready' ? 1 : 0, stage);
    assert.equal(f.client.destroyed, true, stage);
    if (stage === 'ready') assert.equal(f.connection.destroyed, true);
    f.connection.receiver.speaking.emit('start', '300');
    assert.equal(f.streams.size, 0, stage);
  }
});
