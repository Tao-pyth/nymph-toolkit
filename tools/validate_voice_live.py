"""Explicit, content-free evidence for one operator-supervised live voice case.

This tool never obtains consent itself. Use only after the participants agree
to this particular case. Fixture tests of the tool are not live Discord proof.
"""

# SPDX-License-Identifier: Apache-2.0
import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.voice_capture import check_credential
from nymph_toolkit.contracts import HybridSettings, ModuleAdvertisement, ModuleKind, ModuleSpec, Placement
from nymph_toolkit.contracts.voice import VOICE_CONTRACT, VOICE_KEY
from nymph_toolkit.core import FileStore, HybridGroup, Runtime

CASES = ("speaker", "join", "leave", "revoke", "disconnect", "retention", "runtime-stop")
EXPECTED = dict(speaker="requested", join="participants_changed", leave="participants_changed",
                revoke="revoked", disconnect="voice_disconnected", retention="requested")
REASONS = frozenset(EXPECTED.values()) | {"runtime_stop", "consent_missing", "credential_missing",
    "helper_spawn_failed", "helper_start_write_failed", "helper_ready_timeout", "helper_start_failed",
    "startup_timeout", "dave_unavailable", "permission_missing", "channel_unavailable", "connection_failed",
    "gateway_error", "gateway_disconnected", "voice_error", "recognition_failed", "session_expired"}


@dataclass(frozen=True)
class Options:
    case: str
    seconds: float = 30
    action_after: float = 10
    participant: int = 1
    placement: Placement = Placement.PROCESS
    via_core: bool = False


def validate_inputs(config, consent, options):
    if options.case not in CASES or not 1 <= options.seconds <= 30:
        raise ValueError("Invalid probe case or duration")
    if not 0 < options.action_after < options.seconds:
        raise ValueError("Action must precede the observation deadline")
    if type(consent) is not dict or set(consent) != {"notice_ref", "participants", "retention_seconds"}:
        raise ValueError("Invalid consent input")
    participants = consent["participants"]
    if (type(participants) is not dict or not 1 <= len(participants) <= 8
            or any(type(key) is not str or not re.fullmatch(r"[1-9][0-9]{0,19}", key) for key in participants)):
        raise ValueError("Invalid consent participants")
    refs = [consent["notice_ref"], *participants.values()]
    if any(type(ref) is not str or not ref or ref.strip() != ref or "\0" in ref
           or len(ref.encode("utf-8")) > 512 for ref in refs):
        raise ValueError("Invalid consent reference")
    retention = consent["retention_seconds"]
    if type(retention) is not int or not 1 <= retention <= 300:
        raise ValueError("Invalid consent retention")
    if type(options.participant) is not int or not 1 <= options.participant <= len(participants):
        raise ValueError("Participant is a one-based index in sorted consent IDs")
    if options.case == "retention" and retention + 5 >= options.seconds:
        raise ValueError("Retention case requires an explicitly shorter retention input")
    check_credential(config)


def summary(status):
    """Never forward unknown strings, identity, transcript, or exception text."""
    status = status if type(status) is dict else {}
    state, reason = status.get("state"), status.get("reason")
    result = dict(state=state if type(state) is str and state in ("inactive", "starting", "listening", "stopping", "stopped", "failed") else "unknown",
                  reason=reason if reason is None or type(reason) is str and reason in REASONS else "other",
                  cleanup_confirmed=status.get("cleanup_confirmed") is True)
    for field in ("participant_count", "observation_count", "last_sequence", "expired_count", "discarded_segments"):
        value = status.get(field)
        result[field] = value if type(value) is int and 0 <= value <= 2**63 - 1 else None
    return result


def checkout_metadata():
    root = Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, timeout=5, check=True).stdout
        return dict(commit=commit if re.fullmatch(r"[a-f0-9]{40,64}", commit) else None, dirty=bool(dirty))
    except (OSError, subprocess.SubprocessError):
        return dict(commit=None, dirty=None)


class Evidence:
    def __init__(self, config, consent, options):
        self.config, self.options = config, options
        self.people = sorted(consent["participants"])
        self.last = self.count = self.asr_count = self.word_count = 0
        self.speakers = [0] * len(self.people)
        self.source_matches = True
        self.first_seen = self.first_sequence = None
        self.retention_verified = False
        self.read_timed_out = False
        self.started = False
        self.initial_status = None
        self.action_applied = False

    def observe(self, page, session_id, now):
        if type(page) is not dict or page.get("session_id") != session_id or type(page.get("observations")) is not list:
            raise ValueError("Unexpected observation page")
        for item in page["observations"]:
            sequence = item["sequence"]
            if type(sequence) is not int or sequence <= 0:
                raise ValueError("Invalid observation sequence")
            if sequence <= self.last:
                continue
            self.last = sequence
            self.count += 1
            user = item.get("user_id")
            valid_source = (user in self.people and item.get("session_id") == session_id
                and item.get("guild_id") == self.config["guild_id"]
                and item.get("voice_channel_id") == self.config["voice_channel_id"]
                and item.get("source_kind") == "observed")
            self.source_matches &= valid_source
            if user in self.people:
                self.speakers[self.people.index(user)] += 1
            words = item["asr"]["words"]
            if type(words) is not list:
                raise ValueError("Invalid ASR metadata")
            self.asr_count += bool(words)
            self.word_count += len(words)
            if self.first_seen is None:
                self.first_seen, self.first_sequence = now, sequence

    def result(self):
        return dict(observations=self.count, asr_observations=self.asr_count, word_count=self.word_count,
                    participant_observations=self.speakers, source_matches=self.source_matches,
                    retention_verified=self.retention_verified, read_timed_out=self.read_timed_out)


def build_group(root, config, placement):
    store = FileStore(root / "core", root / "archive", retention=timedelta(days=1), batch_size=16, flush_interval=.1)
    group = HybridGroup(HybridSettings(60, 30, 60, 65536, 32, 4), store)
    group.register_module(ModuleSpec("voice", ModuleKind.ADAPTER), ModuleAdvertisement("voice", "1.10.0", (VOICE_CONTRACT,)),
        "nymph_toolkit.adapters.discord_voice:factory", config, placement)
    group.register_module(ModuleSpec("observer", ModuleKind.SUBSYSTEM, ("voice",)), ModuleAdvertisement("observer", "probe", ()),
        "examples.voice_capture:requester", {}, Placement.LOCAL)
    return group


async def exercise(call, runtime, evidence, consent, session_id, announce):
    options = evidence.options
    started = await call("start_session", session_id, consent)
    evidence.initial_status = summary(started)
    evidence.started = (type(started) is dict and started.get("state") == "listening"
                        and started.get("session_id") == session_id and type(started.get("participant_count")) is int
                        and 0 < started["participant_count"] <= len(evidence.people))
    if not evidence.started:
        return started
    announce("Voice probe started; only counts and checks are reported.")
    clock = asyncio.get_running_loop().time
    start = clock()
    while clock() - start < options.seconds:
        now = clock()
        try:
            async with asyncio.timeout(max(.001, start + options.seconds - now)):
                page = await call("read", session_id, after=evidence.last)
        except TimeoutError:
            evidence.read_timed_out = True
            break
        evidence.observe(page, session_id, now)
        if page.get("state") != "listening":
            break
        if options.case == "retention" and evidence.first_seen is not None:
            if now - evidence.first_seen > consent["retention_seconds"] + .2:
                try:
                    async with asyncio.timeout(max(.001, start + options.seconds - clock())):
                        old = await call("read", session_id, after=0)
                except TimeoutError:
                    evidence.read_timed_out = True
                    break
                evidence.retention_verified = (old.get("state") == "listening" and old.get("expired_count", 0) > 0
                    and all(item["sequence"] != evidence.first_sequence for item in old["observations"]))
                if evidence.retention_verified:
                    break
        if options.case in ("revoke", "runtime-stop") and now - start >= options.action_after:
            evidence.action_applied = True
            if options.case == "revoke":
                return await call("revoke", session_id, evidence.people[options.participant - 1])
            await runtime.stop()
            return None
        await asyncio.sleep(.05)
    return await call("stop_session", session_id)


async def probe(config, consent, options, *, announce=print):
    validate_inputs(config, consent, options)
    evidence = Evidence(config, consent, options)
    report = dict(schema=1, case=options.case, placement=options.placement.value,
                  route="core" if options.via_core else "direct", observation_seconds=options.seconds,
                  checked_at=datetime.now(timezone.utc).isoformat(), python=platform.python_version(),
                  system=platform.system(), candidate_version="1.10.0", evidence_kind="operator-supervised-live",
                  started=False, initial_status=None, cleared=False, same_session_not_reconnected=False, runtime_cleanup=False,
                  restart_inactive=False, passed=False, error=None, status=None)
    with tempfile.TemporaryDirectory(prefix="ntk-voice-probe-") as directory:
        root = Path(directory).resolve()
        group = build_group(root, config, options.placement)
        runtime, link = Runtime(group), None
        session_id = "probe-" + uuid4().hex
        call = None
        try:
            await runtime.start()
            client = group.client("observer")
            await client.bind(VOICE_KEY, "voice", timeout=10)
            link = await client.prepare(VOICE_KEY, timeout=10)

            async def call(name, *args, **kwargs):
                if options.via_core:
                    return await client.invoke(VOICE_KEY, name, *args, **kwargs, timeout=40)
                return await link.acall(name, *args, **kwargs, timeout=40)

            try:
                status = await exercise(call, runtime, evidence, consent, session_id, announce)
            finally:
                if not (options.case == "runtime-stop" and evidence.action_applied):
                    # Also stop on failure/cancellation; never leave a live session running.
                    status = await call("stop_session", session_id)
            report["started"] = evidence.started
            if status is not None:
                report["status"] = summary(status)
                page = await call("read", session_id, after=0)
                report["cleared"] = (type(page) is dict and page.get("session_id") == session_id
                    and page.get("state") == status.get("state") and page.get("observations") == []
                    and status.get("participant_count") == 0 and status.get("observation_count") == 0)
                replay = await call("start_session", session_id, consent)
                report["same_session_not_reconnected"] = (type(replay) is dict and replay.get("session_id") == session_id
                    and summary(replay) == summary(status)
                    and summary(replay)["state"] in ("stopped", "failed") and summary(replay)["cleanup_confirmed"])
        except Exception:
            report["error"] = "probe_failed"
        finally:
            try:
                if link is not None:
                    await link.close()
            finally:
                try:
                    await runtime.stop()
                    report["runtime_cleanup"] = all(group.process(name).cleanup_confirmed for name in group.modules)
                except Exception:
                    report["error"] = "runtime_cleanup_failed"
        if options.case == "runtime-stop" and evidence.action_applied and report["runtime_cleanup"]:
            fresh = build_group(root, config, options.placement)
            restarted = Runtime(fresh)
            try:
                await restarted.start()
                client = fresh.client("observer")
                await client.bind(VOICE_KEY, "voice", timeout=10)
                status = await client.invoke(VOICE_KEY, "status", timeout=40)
                report["restart_inactive"] = (type(status) is dict and status.get("state") == "inactive"
                    and status.get("session_id") is None and status.get("observation_count") == 0
                    and status.get("participant_count") == 0 and status.get("cleanup_confirmed") is True)
            except Exception:
                report["error"] = "restart_check_failed"
            finally:
                try:
                    await restarted.stop()
                    report["runtime_cleanup"] &= all(fresh.process(name).cleanup_confirmed for name in fresh.modules)
                except Exception:
                    report["error"] = "restart_cleanup_failed"
    report.update(evidence.result())
    report["initial_status"] = evidence.initial_status
    report["retention_seconds"] = consent["retention_seconds"]
    report["participant_index"] = options.participant
    good = (report["started"] and evidence.count > 0 and evidence.source_matches and not evidence.read_timed_out
            and report["runtime_cleanup"] and report["error"] is None)
    if options.case == "runtime-stop":
        good &= evidence.action_applied and report["restart_inactive"]
    else:
        end = report["status"] or {}
        good &= (end.get("reason") == EXPECTED[options.case] and end.get("cleanup_confirmed") is True
                 and report["cleared"] and report["same_session_not_reconnected"])
    if options.case == "speaker":
        good &= evidence.speakers[options.participant - 1] == evidence.count
    if options.case == "retention":
        good &= evidence.retention_verified
    report["passed"] = bool(good)
    report["checkout"] = checkout_metadata()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--consent", required=True, type=Path)
    parser.add_argument("--case", required=True, choices=CASES)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--action-after", type=float, default=10)
    parser.add_argument("--participant", type=int, default=1)
    parser.add_argument("--placement", choices=[p.value for p in Placement], default="process")
    parser.add_argument("--via-core", action="store_true")
    parser.add_argument("--output", type=Path, help="Save only the same non-content summary printed to the terminal")
    args = parser.parse_args(argv)
    try:
        if args.config.stat().st_size > 32768 or args.consent.stat().st_size > 32768:
            raise ValueError("Input too large")
        config = json.loads(args.config.read_text(encoding="utf-8-sig"))
        consent = json.loads(args.consent.read_text(encoding="utf-8-sig"))
        options = Options(args.case, args.seconds, args.action_after, args.participant, Placement(args.placement), args.via_core)
        report = asyncio.run(probe(config, consent, options))
    except KeyboardInterrupt:
        report = dict(passed=False, error="interrupted")
    except Exception:
        report = dict(passed=False, error="input_or_runtime_failed")
    encoded = json.dumps(report, ensure_ascii=True, allow_nan=False)
    print(encoded)
    if args.output:
        try:
            # Do not replace earlier evidence or an input/configuration file.
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded + "\n")
        except (OSError, ValueError):
            print('{"passed": false, "error": "summary_not_saved"}')
            return 1
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
