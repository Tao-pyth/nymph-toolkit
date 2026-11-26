"""Own capture, transient audio, recognition and teardown for one consent set."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import base64
from collections import deque

from ._audio import MAX_PCM_BYTES, MODEL_ID
from ._model import dump, fields, frame, snapshot, timestamp, user_id

NORMAL_STOPS = {"requested", "revoked", "participants_changed", "session_expired", "runtime_stop", "start_cancelled"}
BRIDGE_STOPS = NORMAL_STOPS | {"output_capacity", "startup_timeout", "gateway_error", "gateway_disconnected",
    "voice_error", "voice_disconnected", "consent_or_dave_changed", "audio_decode_failed", "audio_receive_failed",
    "credential_missing", "channel_unavailable", "permission_missing", "consent_missing", "dave_unavailable",
    "connection_failed", "finished", "invalid_input_or_dependencies"}


class _CredentialUnavailable(ValueError):
    """Local credential precondition failed; never carries the credential."""


class Session:
    def __init__(self, owner, key, permission):
        self.owner, self.key, self.permission = owner, key, permission
        self.retention = permission["retention_seconds"]
        self.state, self.reason, self.cleanup_confirmed = "starting", None, False
        self.process = self.launch_task = self.stop_task = None
        self.reader_task = self.stderr_task = self.consumer_task = self.timer_task = None
        self.ready = asyncio.Event()
        self.closing = False
        self.participants = []
        self.buffers = {}
        self.queue = asyncio.Queue(maxsize=8)
        self.observations = deque()
        self.sequence = self.expired = self.discarded = 0
        self.started_at = self.owner.clock()

    def summary(self):
        self._expire()
        return dict(session_id=self.key, state=self.state, reason=self.reason, cleanup_confirmed=self.cleanup_confirmed,
                    participant_count=len(self.participants), observation_count=len(self.observations),
                    last_sequence=self.sequence, expired_count=self.expired, discarded_segments=self.discarded,
                    asr_model=MODEL_ID)

    def _expire(self):
        now = self.owner.clock()
        remaining = deque((at, value) for at, value in self.observations if at > now)
        self.expired += len(self.observations) - len(remaining)
        self.observations = remaining
        for person, buffer in tuple(self.buffers.items()):
            if buffer["last"] + self.retention <= now:
                buffer["data"].clear()
                del self.buffers[person]
                self.discarded += 1
        # A slow native recognizer must not keep expired waiting audio alive.
        waiting = []
        while not self.queue.empty():
            item = self.queue.get_nowait()
            self.queue.task_done()
            if item["expires"] <= now:
                item.clear()
                self.discarded += 1
            else:
                waiting.append(item)
        for item in waiting:
            self.queue.put_nowait(item)

    def read(self, after, limit):
        self._expire()
        candidates = [value for _, value in self.observations if value["sequence"] > after]
        result = dict(session_id=self.key, state=self.state, observations=[], next_after=None,
                      last_sequence=self.sequence, expired_count=self.expired)
        for value in candidates[:limit]:
            trial = dict(result, observations=result["observations"] + [value], next_after=value["sequence"])
            if len(dump(trial).encode("ascii")) > 49152:
                break
            result = trial
        if len(result["observations"]) == len(candidates):
            result["next_after"] = None
        return snapshot(result)

    async def launch(self):
        self.launch_task = asyncio.create_task(self._launch())
        await asyncio.shield(self.launch_task)
        try:
            async with asyncio.timeout(25):
                await self.ready.wait()
        except TimeoutError:
            self.request_stop("helper_ready_timeout")
            raise

    async def _launch(self):
        failure_reason = "helper_spawn_failed"
        try:
            self.process = await self.owner.spawn()
            failure_reason = "helper_start_failed"
            self.reader_task = asyncio.create_task(self._read())
            self.stderr_task = asyncio.create_task(self._stderr())
            if self.closing:
                return
            self.consumer_task = asyncio.create_task(self._consume())
            self.timer_task = asyncio.create_task(self._timer())
            config = self.owner.config
            message = dict(type="start", node_modules_path=config["node_modules_path"], guild_id=config["guild_id"],
                           voice_channel_id=config["voice_channel_id"], participants=list(self.permission["participants"]))
            encoded = (dump(message) + "\n").encode("ascii")
            if len(encoded) > 8192:
                raise ValueError("Helper configuration too large")
            failure_reason = "helper_start_write_failed"
            self.process.stdin.write(encoded)
            await self.process.stdin.drain()
        except _CredentialUnavailable:
            self.request_stop("credential_missing")
            raise
        except BaseException:
            self.request_stop(failure_reason)
            raise

    async def _read(self):
        try:
            while True:
                raw = await self.process.stdout.readline()
                if not raw:
                    if not self.closing:
                        self.request_stop("helper_exited")
                    return
                if self.closing:
                    continue  # drain pipes during shutdown without retaining data
                self._receive(frame(raw))
        except asyncio.CancelledError:
            raise
        except Exception:
            self.request_stop("helper_protocol_error")

    async def _stderr(self):
        count = 0
        try:
            while data := await self.process.stderr.read(4096):
                count += len(data)
                if count > 65536 and not self.closing:
                    self.request_stop("helper_diagnostic_capacity")
                # SDK/native diagnostics are deliberately discarded, never logged.
        except asyncio.CancelledError:
            raise
        except Exception:
            self.request_stop("helper_diagnostic_error")

    def _receive(self, value):
        kind = value["type"]
        if kind == "stopped":
            fields(value, "type reason")
            if type(value["reason"]) is not str or value["reason"] not in BRIDGE_STOPS:
                raise ValueError("Unknown helper stop reason")
            self.request_stop(value["reason"])
        elif kind == "ready":
            fields(value, "type participants dave")
            people = value["participants"]
            if (self.state != "starting" or value["dave"] is not True or type(people) is not list
                    or not 1 <= len(people) <= 8 or any(user_id(x) not in self.permission["participants"] for x in people)
                    or len(set(people)) != len(people)):
                raise ValueError("Unconfirmed DAVE or consent")
            self.participants = sorted(people)
            self.state = "listening"
            self.ready.set()
        elif kind in ("pcm", "segment_end"):
            fields(value, "type user_id at pcm" if kind == "pcm" else "type user_id")
            person = user_id(value["user_id"])
            if self.state != "listening" or person not in self.participants:
                raise ValueError("Audio arrived outside the consented session")
            if kind == "segment_end":
                self._flush(person)
                return
            at = timestamp(value["at"])
            encoded = value["pcm"]
            if type(encoded) is not str or len(encoded) > 128000:
                raise ValueError("Invalid PCM encoding")
            pcm = base64.b64decode(encoded, validate=True)
            if not pcm or len(pcm) % 4 or len(pcm) > 96000:
                raise ValueError("Invalid PCM chunk")
            offset = 0
            while offset < len(pcm) and not self.closing:
                buffer = self.buffers.setdefault(person, dict(data=bytearray(), at=at, last=self.owner.clock()))
                take = min(len(pcm) - offset, MAX_PCM_BYTES - len(buffer["data"]))
                buffer["data"].extend(pcm[offset:offset + take])
                buffer["last"] = self.owner.clock()
                offset += take
                if len(buffer["data"]) == MAX_PCM_BYTES:
                    self._flush(person)
        else:
            raise ValueError("Unknown helper frame")

    def _flush(self, person):
        buffer = self.buffers.pop(person, None)
        if buffer is None:
            return
        if self.queue.full():
            buffer["data"].clear()
            self.request_stop("audio_capacity")
            return
        self.queue.put_nowait(dict(user_id=person, pcm=bytes(buffer["data"]), at=buffer["at"],
                                  expires=buffer["last"] + self.retention))
        buffer["data"].clear()

    async def _consume(self):
        try:
            while not self.closing:
                item = await self.queue.get()
                try:
                    if item["expires"] <= self.owner.clock():
                        self.discarded += 1
                        continue
                    result = await self.owner.work(self.owner.processor.process, item["pcm"])
                    if self.closing or item["expires"] <= self.owner.clock():
                        self.discarded += 1
                        continue
                    self._expire()
                    if len(self.observations) >= 64:
                        self.request_stop("observation_capacity")
                        continue
                    self.sequence += 1
                    observation = dict(result, sequence=self.sequence, source_kind="observed", session_id=self.key,
                                       user_id=item["user_id"], guild_id=self.owner.config["guild_id"],
                                       voice_channel_id=self.owner.config["voice_channel_id"], received_at=item["at"])
                    # One observation must always fit a read page with metadata.
                    observation = snapshot(observation, 45000)
                    self.observations.append((item["expires"], observation))
                finally:
                    item.clear()
                    self.queue.task_done()
        except asyncio.CancelledError:
            raise
        except Exception:
            self.request_stop("recognition_failed")

    async def _timer(self):
        while not self.closing:
            self._expire()
            now = self.owner.clock()
            if now - self.started_at >= 600:
                self.request_stop("session_expired")
                return
            for person, buffer in tuple(self.buffers.items()):
                if now - buffer["last"] >= 1.5:
                    self._flush(person)
                    if self.closing:
                        return
            await asyncio.sleep(.1)

    def request_stop(self, reason):
        if self.stop_task is None:
            self.closing = True
            self.state, self.reason = "stopping", reason
            self.ready.set()
            self.observations.clear()
            for buffer in self.buffers.values():
                buffer["data"].clear()
            self.buffers.clear()
            while not self.queue.empty():
                self.queue.get_nowait().clear()
                self.queue.task_done()
                self.discarded += 1
            self.stop_task = asyncio.create_task(self._stop())
        return self.stop_task

    async def _stop(self):
        if self.launch_task is not None:
            await asyncio.gather(self.launch_task, return_exceptions=True)
        # Recognition cancellation drains its owned worker future before it ends.
        for task in (self.consumer_task, self.timer_task):
            if task is not None:
                task.cancel()
        if self.process is not None:
            if self.process.returncode is None:
                try:
                    self.process.stdin.write(b'{"type":"stop"}\n')
                    async with asyncio.timeout(1):
                        await self.process.stdin.drain()
                except (OSError, RuntimeError, TimeoutError):
                    pass
                self.process.stdin.close()
                try:
                    async with asyncio.timeout(5):
                        await self.process.wait()
                except TimeoutError:
                    try:
                        self.process.kill()
                    except ProcessLookupError:
                        pass
                    await self.process.wait()
            else:
                self.process.stdin.close()
            # A stop during process creation has no reader tasks yet. Drain the
            # pipes after killing/waiting so transports are still reclaimed.
            if self.reader_task is None:
                await self.process.stdout.read()
            if self.stderr_task is None:
                await self.process.stderr.read()
        tasks = [task for task in (self.reader_task, self.stderr_task, self.consumer_task, self.timer_task) if task is not None]
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.process is not None:
            try:
                await self.process.stdin.wait_closed()
            except (OSError, RuntimeError):
                pass
        self.observations.clear()
        self.permission.clear()
        self.participants.clear()
        self.cleanup_confirmed = True
        self.state = "stopped" if self.reason in NORMAL_STOPS else "failed"
