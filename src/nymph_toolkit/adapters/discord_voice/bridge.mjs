// SPDX-License-Identifier: Apache-2.0
// Adapter-owned Discord receive process. Diagnostics never include SDK errors,
// credentials, user names, or audio. Dependency installation is explicit.
import { createRequire } from 'node:module';
import { createInterface } from 'node:readline';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const snowflake = value => typeof value === 'string' && /^[1-9][0-9]{0,19}$/.test(value);

export function configuration(value) {
  const keys = ['type', 'node_modules_path', 'guild_id', 'voice_channel_id', 'participants'];
  if (!value || Array.isArray(value) || Object.keys(value).sort().join() !== keys.sort().join()
      || value.type !== 'start' || typeof value.node_modules_path !== 'string' || !path.isAbsolute(value.node_modules_path)
      || !snowflake(value.guild_id) || !snowflake(value.voice_channel_id)
      || !Array.isArray(value.participants) || value.participants.length < 1 || value.participants.length > 8
      || !value.participants.every(snowflake) || new Set(value.participants).size !== value.participants.length) {
    throw new Error('invalid_configuration');
  }
  return { ...value, participants: [...value.participants].sort() };
}

export function participants(channel, botId, allowed) {
  const current = [...channel.members.keys()].filter(id => id !== botId).sort();
  if (current.length < 1 || current.some(id => !allowed.includes(id))) throw new Error('consent_missing');
  return current;
}

export async function receive(config, emit, commands, dependencies) {
  const { Client, GatewayIntentBits, ChannelType, PermissionFlagsBits, voice, Opus } = dependencies;
  let connection, client, stopping = false, connected = false, deadline;
  const streams = new Map();
  let resolveFinished;
  const finished = new Promise(resolve => { resolveFinished = resolve; });
  const stop = async reason => {
    if (stopping) return finished;
    stopping = true;
    clearTimeout(deadline);
    // Stop receiving before asynchronous gateway teardown.
    for (const { stream, decoder } of streams.values()) {
      stream.destroy();
      decoder.delete();
    }
    streams.clear();
    try { connection?.destroy(); } catch { /* already destroyed */ }
    try { await client?.destroy(); } catch { /* no SDK diagnostic leaks */ }
    emit({ type: 'stopped', reason });
    resolveFinished();
    return finished;
  };
  commands.on('stop', () => { void stop('requested'); });
  const send = value => {
    if (!stopping && !emit(value)) void stop('output_capacity');
  };
  deadline = setTimeout(() => { void stop('startup_timeout'); }, 20000);
  try {
    client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates] });
    client.on('error', () => { void stop('gateway_error'); });
    client.on('shardDisconnect', () => { void stop('gateway_disconnected'); });
    const token = process.env.NTK_DISCORD_TOKEN;
    delete process.env.NTK_DISCORD_TOKEN;
    if (!token) throw new Error('credential_missing');
    await client.login(token);
    if (stopping) return finished;
    const channel = await client.channels.fetch(config.voice_channel_id);
    if (stopping) return finished;
    if (!channel || channel.guildId !== config.guild_id || channel.type !== ChannelType.GuildVoice) {
      throw new Error('channel_unavailable');
    }
    const permissions = channel.permissionsFor(client.user.id);
    if (!permissions?.has([PermissionFlagsBits.ViewChannel, PermissionFlagsBits.Connect])) throw new Error('permission_missing');
    const initial = participants(channel, client.user.id, config.participants);
    // Any change of the participant set ends this consented session. Muting or
    // changing presence within the same channel does not change that set.
    client.on('voiceStateUpdate', (before, after) => {
      if (after.id === client.user.id) return;
      if ((before.channelId === channel.id) !== (after.channelId === channel.id)) void stop('participants_changed');
    });
    connection = voice.joinVoiceChannel({ channelId: channel.id, guildId: channel.guildId,
      adapterCreator: channel.guild.voiceAdapterCreator, selfDeaf: false, selfMute: true, daveEncryption: true });
    connection.on('error', () => { void stop('voice_error'); });
    connection.on('stateChange', (before, after) => {
      if (connected && after.status !== voice.VoiceConnectionStatus.Ready) void stop('voice_disconnected');
    });
    await voice.entersState(connection, voice.VoiceConnectionStatus.Ready, 15000);
    if (stopping) return finished;
    // Ready at the voice transport layer alone is not evidence of DAVE readiness.
    for (let count = 0; !connection.voicePrivacyCode && count < 50 && !stopping; count++) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    if (stopping) return finished;
    if (!connection.voicePrivacyCode) throw new Error('dave_unavailable');
    if (participants(channel, client.user.id, config.participants).join() !== initial.join()) throw new Error('participants_changed');
    connected = true;
    clearTimeout(deadline);
    deadline = setTimeout(() => { void stop('session_expired'); }, 600000);
    connection.receiver.speaking.on('start', userId => {
      if (stopping || streams.has(userId)) return;
      if (!initial.includes(userId) || !connection.voicePrivacyCode) { void stop('consent_or_dave_changed'); return; }
      let stream, decoder;
      try {
        decoder = new Opus(48000, 2, Opus.Application.AUDIO);
        stream = connection.receiver.subscribe(userId, { end: { behavior: voice.EndBehaviorType.AfterSilence, duration: 1000 } });
        streams.set(userId, { stream, decoder });
        stream.on('data', packet => {
          if (stopping) return;
          try {
            if (!connection.voicePrivacyCode) throw new Error('dave_unavailable');
            const pcm = decoder.decode(packet);
            if (!Buffer.isBuffer(pcm) || pcm.length === 0 || pcm.length % 4 || pcm.length > 96000) throw new Error('invalid_pcm');
            send({ type: 'pcm', user_id: userId, at: new Date().toISOString(), pcm: pcm.toString('base64') });
          } catch { void stop('audio_decode_failed'); }
        });
        stream.on('end', () => {
          if (!streams.has(userId)) return;
          streams.delete(userId);
          decoder.delete();
          send({ type: 'segment_end', user_id: userId });
        });
        stream.on('error', () => { void stop('audio_receive_failed'); });
      } catch {
        if (!streams.has(userId)) decoder?.delete();
        void stop('audio_receive_failed');
      }
    });
    send({ type: 'ready', participants: initial, dave: true });
    await finished;
  } catch (error) {
    const allowed = ['credential_missing', 'channel_unavailable', 'permission_missing', 'consent_missing', 'participants_changed', 'dave_unavailable'];
    await stop(allowed.includes(error?.message) ? error.message : 'connection_failed');
  } finally {
    await stop('finished');
  }
}

async function main() {
  const { EventEmitter } = await import('node:events');
  const commands = new EventEmitter();
  const reader = createInterface({ input: process.stdin, crlfDelay: Infinity });
  let started = false, task;
  let inputBytes = 0;
  const emit = value => {
    if (process.stdout.destroyed) return false;
    return process.stdout.write(JSON.stringify(value) + '\n');
  };
  process.stdout.on('error', () => commands.emit('stop'));
  // Bound input before readline can accumulate an arbitrary unterminated line.
  process.stdin.on('data', chunk => {
    for (const byte of chunk) {
      inputBytes = byte === 10 ? 0 : inputBytes + 1;
      if (inputBytes > 8192) { commands.emit('stop'); reader.close(); process.stdin.pause(); break; }
    }
  });
  reader.on('line', line => {
    try {
      if (Buffer.byteLength(line) > 8192) throw new Error('invalid_input');
      const value = JSON.parse(line);
      if (started) {
        if (!value || value.type !== 'stop' || Object.keys(value).length !== 1) throw new Error('invalid_input');
        commands.emit('stop');
        return;
      }
      const config = configuration(value);
      started = true;
      const require = createRequire(path.join(config.node_modules_path, 'package.json'));
      const { Client, GatewayIntentBits, ChannelType, PermissionFlagsBits } = require('discord.js');
      task = receive(config, emit, commands, { Client, GatewayIntentBits, ChannelType, PermissionFlagsBits,
        voice: require('@discordjs/voice'), Opus: require('opusscript') });
      task.finally(() => { reader.close(); process.stdin.pause(); });
    } catch {
      emit({ type: 'stopped', reason: 'invalid_input_or_dependencies' });
      commands.emit('stop'); reader.close(); process.stdin.pause();
    }
  });
  reader.on('close', () => { commands.emit('stop'); });
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch(() => { process.exitCode = 1; });
}
