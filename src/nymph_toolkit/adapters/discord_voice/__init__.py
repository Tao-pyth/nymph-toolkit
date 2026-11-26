"""Explicit, consented Discord capture with ephemeral local recognition."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import subprocess
import time

from nymph_toolkit.contracts import ModuleContextProtocol, OperatingState, OperationFailure, RuntimeService, TemporaryUnavailable, Usage
from nymph_toolkit.contracts.voice import VOICE_KEY
from ._audio import Processor
from ._model import configuration, consent as validate_consent, fingerprint, integer, snapshot, text, user_id as validate_user_id
from ._session import Session, _CredentialUnavailable

__all__ = ["factory"]


async def _settled(future):
    cancelled = False
    while not future.done():
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            break
    if cancelled:
        if not future.cancelled():
            future.exception()
        raise asyncio.CancelledError
    return future.result()


class _Voice:
    def __init__(self, context, config):
        self.context, self.config = context, configuration(config)
        if context.settings.max_frame_bytes < 65536:
            raise ValueError("Voice requires max_frame_bytes >= 65536")
        self.pool = self.processor = self.stop_task = self.current = None
        self.started = self.ready = self.closing = False
        self.history = {}
        self.clock = time.monotonic
        self.processor_factory = Processor
        context.provide(VOICE_KEY, {name: getattr(self, name) for name in ("start_session", "stop_session", "status", "read", "revoke")})

    async def work(self, function, *args):
        return await _settled(asyncio.get_running_loop().run_in_executor(self.pool, function, *args))

    async def _check_node(self):
        process = await asyncio.create_subprocess_exec(self.config["node_executable"], "--version", stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            async with asyncio.timeout(5):
                output, _ = await process.communicate()
            match = re.fullmatch(rb"v(\d+)\.(\d+)\.(\d+)\s*", output)
            if process.returncode or not match or tuple(map(int, match.groups())) < (24, 17, 0):
                raise ValueError("Discord Voice requires Node.js 24.17 or newer")
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    async def start(self):
        if self.started or self.closing:
            raise RuntimeError("Voice cannot be started twice")
        self.started = True
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ntk-voice-asr")
        try:
            await self._check_node()
            self.processor = await self.work(self.processor_factory, self.config["model_path"])
            usage = Usage(OperatingState.RUNNING, True, 0, 32)
            await self.context.core.publish_usage(usage, contracts={VOICE_KEY: usage})
            self.ready = True
        except BaseException:
            await self.stop()
            raise

    async def run(self):
        try:
            await asyncio.Event().wait()
        finally:
            self.ready = False
            self.closing = True
            if self.current is not None:
                await _settled(self.current.request_stop("runtime_stop"))

    async def spawn(self):
        # A small environment prevents unrelated credentials and NODE_OPTIONS
        # from reaching the helper. The token is never a command-line argument.
        environment = {key: value for key, value in os.environ.items()
                       if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL"}}
        token = os.environ.get(self.config["token_env"])
        if not token or len(token) > 4096:
            raise _CredentialUnavailable("The configured Bot credential is unavailable")
        environment["NTK_DISCORD_TOKEN"] = token
        return await asyncio.create_subprocess_exec(self.config["node_executable"], str(Path(__file__).with_name("bridge.mjs")),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            limit=131072, env=environment, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    def _remember(self):
        if self.current is not None:
            self.history[self.current.key]["summary"] = self.current.summary()

    def _status(self):
        self._remember()
        if self.current is None:
            return dict(session_id=None, state="inactive", reason=None, cleanup_confirmed=True, participant_count=0,
                        observation_count=0, last_sequence=0, expired_count=0, discarded_segments=0, asr_model="vosk-model-small-ja-0.22")
        return snapshot(self.history[self.current.key]["summary"])

    async def status(self):
        return self._status()

    async def start_session(self, session_id, consent):
        try:
            text(session_id)
            permission = validate_consent(consent)
            digest = fingerprint(permission)
        except (ValueError, TypeError, OverflowError, RecursionError):
            return OperationFailure("voice.invalid", "Invalid session identifier or consent")
        if not self.ready or self.closing:
            return TemporaryUnavailable("Voice is not accepting a new session")
        self._remember()
        previous = self.history.get(session_id)
        if previous is not None:
            if previous["fingerprint"] != digest:
                return OperationFailure("voice.session_conflict", "Session identifier has different consent")
            return snapshot(previous["summary"])
        if self.current is not None and not self.current.cleanup_confirmed:
            return TemporaryUnavailable("A voice session or its cleanup is still active")
        if len(self.history) >= 64:
            return OperationFailure("voice.session_limit", "This Runtime has already tracked 64 sessions")
        session = Session(self, session_id, permission)
        self.current = session
        self.history[session_id] = dict(fingerprint=digest, summary=session.summary())
        try:
            await session.launch()
        except asyncio.CancelledError:
            await _settled(session.request_stop("start_cancelled"))
            raise
        except Exception:
            await _settled(session.request_stop("helper_start_failed"))
        if session.stop_task is not None:
            await _settled(session.stop_task)
        return self._status()

    async def _stop_session(self, session_id, reason):
        try:
            text(session_id)
        except (ValueError, TypeError):
            return OperationFailure("voice.invalid", "Invalid session identifier")
        self._remember()
        if session_id not in self.history:
            return OperationFailure("voice.not_found", "Unknown session identifier")
        if self.current is None or session_id != self.current.key:
            return snapshot(self.history[session_id]["summary"])
        await _settled(self.current.request_stop(reason))
        return self._status()

    async def stop_session(self, session_id):
        return await self._stop_session(session_id, "requested")

    async def revoke(self, session_id, user_id):
        try:
            validate_user_id(user_id)
        except (ValueError, TypeError):
            return OperationFailure("voice.invalid", "Invalid participant identifier")
        if self.current is not None and self.current.key == session_id and not self.current.closing and user_id not in self.current.permission["participants"]:
            return OperationFailure("voice.not_found", "Participant is not in this consent set")
        return await self._stop_session(session_id, "revoked")

    async def read(self, session_id, *, after=0, limit=4):
        try:
            text(session_id); integer(after, 0, 2**63 - 1); integer(limit, 1, 4)
        except (ValueError, TypeError):
            return OperationFailure("voice.invalid", "Invalid voice read page")
        self._remember()
        if session_id not in self.history:
            return OperationFailure("voice.not_found", "Unknown session identifier")
        if self.current is not None and self.current.key == session_id:
            return self.current.read(after, limit)
        old = self.history[session_id]["summary"]
        return dict(session_id=session_id, state=old["state"], observations=[], next_after=None,
                    last_sequence=old["last_sequence"], expired_count=old["expired_count"])

    async def stop(self):
        self.ready = False
        self.closing = True
        if self.stop_task is None:
            self.stop_task = asyncio.create_task(self._close())
        await _settled(self.stop_task)

    async def _close(self):
        try:
            if self.current is not None:
                await _settled(self.current.request_stop("runtime_stop"))
        finally:
            if self.pool is not None:
                self.processor = None
                self.pool.shutdown(wait=True)
                self.pool = None
            self.history.clear()
            self.current = None


def factory(context: ModuleContextProtocol, config: object) -> RuntimeService[object]:
    return _Voice(context, config)
