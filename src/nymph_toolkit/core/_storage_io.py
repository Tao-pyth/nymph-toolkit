"""Serialized disk operations. The asynchronous owner supplies retry and admission."""

# SPDX-License-Identifier: Apache-2.0
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from uuid import uuid4

from nymph_toolkit.contracts import BindingKey, BindingRecord, ContractKey, StorageCorruptionError


_HISTORY = re.compile(r"history-(\d{4}-\d{2}-\d{2})-([a-f0-9]{32})\.jsonl\Z")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _json(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


def _digest(path: Path) -> tuple[int, bytes]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.digest()


def _append(path: Path, baseline: int, data: bytes) -> None:
    with path.open("r+b" if path.exists() else "w+b") as stream:
        stream.seek(baseline)
        stream.truncate()
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


@dataclass
class HistoryBatch:
    data: dict[Path, bytes]
    baselines: dict[Path, int] = field(default_factory=dict)

    @property
    def protected(self) -> frozenset[Path]:
        return frozenset(self.data)

    def write(self) -> None:
        for path in self.data:
            if path.is_symlink():
                raise OSError("Refusing to write history through a symbolic link")
            if path not in self.baselines:
                self.baselines[path] = path.stat().st_size if path.exists() else 0
        for path, data in self.data.items():
            _append(path, self.baselines[path], data)


class Disk:
    """Own only NTK configuration and identifiable history in a dedicated directory."""

    def __init__(self, root: Path, archive: Path, retention: timedelta) -> None:
        self.root = Path(root).resolve()
        self.archive = Path(archive).resolve()
        if (self.root == self.archive or self.root.is_relative_to(self.archive)
                or self.archive.is_relative_to(self.root)):
            raise ValueError("Primary and archive directories must be separate and non-nested")
        if not isinstance(retention, timedelta) or retention < timedelta(0):
            raise ValueError("retention must be a nonnegative timedelta")
        self.retention = retention
        self.settings = self.root / "connections.json"

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def load_bindings(self) -> tuple[BindingRecord, ...]:
        if self.settings.is_symlink():
            raise StorageCorruptionError("Settings must not be a symbolic link")
        try:
            raw = self.settings.read_bytes()
        except FileNotFoundError:
            return ()
        try:
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
            if not isinstance(data, dict) or set(data) != {"schema_version", "bindings"}:
                raise ValueError("Invalid settings envelope")
            if type(data["schema_version"]) is not int or data["schema_version"] != 1:
                raise ValueError("Unknown settings schema")
            if not isinstance(data["bindings"], list):
                raise ValueError("bindings must be a list")
            records = []
            for item in data["bindings"]:
                if not isinstance(item, dict) or set(item) != {"requester_id", "contract_id", "contract_version", "provider_id"}:
                    raise ValueError("Invalid binding record")
                records.append(BindingRecord(BindingKey(item["requester_id"], ContractKey(item["contract_id"], item["contract_version"])), item["provider_id"]))
            if len({r.key for r in records}) != len(records):
                raise ValueError("Duplicate binding key")
            return tuple(sorted(records, key=lambda r: r.key))
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise StorageCorruptionError(f"Invalid connection settings: {exc}") from exc

    def save_bindings(self, records: tuple[BindingRecord, ...]) -> None:
        if not all(isinstance(r, BindingRecord) for r in records):
            raise TypeError("records must contain BindingRecord values")
        if len({r.key for r in records}) != len(records):
            raise ValueError("Duplicate binding key")
        if self.settings.is_symlink():
            raise StorageCorruptionError("Settings must not be a symbolic link")
        content = _json({"schema_version": 1, "bindings": [
            {"requester_id": r.key.requester_id, "contract_id": r.key.contract.contract_id,
             "contract_version": r.key.contract.version, "provider_id": r.provider_id}
            for r in sorted(records, key=lambda r: r.key)
        ]})
        temporary = self.root / (".ntk-settings-" + uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.settings)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def history_batch(self, records: tuple[dict, ...]) -> HistoryBatch:
        data = defaultdict(bytearray)
        for record in records:
            if record.get("format") != "ntk.history.v1" or not re.fullmatch("[a-f0-9]{32}", record["run_id"]):
                raise ValueError("Invalid internal history identity")
            timestamp = datetime.fromisoformat(record["at"])
            if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
                raise ValueError("History timestamps must be UTC")
            name = f"history-{timestamp.date().isoformat()}-{record['run_id']}.jsonl"
            data[self.root / name].extend(_json(record))
        return HistoryBatch({path: bytes(content) for path, content in data.items()})

    def archive_old(self, now: datetime, protected: frozenset[Path] = frozenset()) -> int:
        if now.tzinfo is None:
            raise ValueError("Rescue time must be timezone-aware")
        cutoff = now.astimezone(timezone.utc) - self.retention
        if not self.root.exists():
            return 0
        count = 0
        for source in sorted(self.root.iterdir()):
            match = _HISTORY.fullmatch(source.name)
            if match is None or source in protected or source.is_symlink() or not source.is_file():
                continue
            if source.resolve().parent != self.root:
                continue
            try:
                end = datetime.fromisoformat(match[1]).replace(tzinfo=timezone.utc) + timedelta(days=1)
            except ValueError:
                continue
            if end > cutoff:
                continue
            try:
                with source.open("rb") as stream:
                    first = json.loads(stream.readline())
                if first.get("format") != "ntk.history.v1" or first.get("run_id") != match[2]:
                    continue
            except (ValueError, AttributeError, UnicodeError):
                continue
            self.archive.mkdir(parents=True, exist_ok=True)
            destination = self.archive / source.name
            if destination.is_symlink():
                raise OSError("Refusing an archive symbolic link")
            signature = _digest(source)
            if destination.exists():
                if _digest(destination) != signature:
                    raise FileExistsError("Archive has different content: " + destination.name)
            else:
                temporary = self.archive / (".ntk-archive-" + uuid4().hex + ".tmp")
                try:
                    with source.open("rb") as original, temporary.open("xb") as copy:
                        shutil.copyfileobj(original, copy)
                        copy.flush()
                        os.fsync(copy.fileno())
                    if _digest(temporary) != signature:
                        raise OSError("Archive verification failed")
                    os.replace(temporary, destination)
                finally:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass
            # Verify the final name, and the source again, before removing it.
            if (_digest(destination) != signature or source.is_symlink()
                    or source.resolve().parent != self.root or _digest(source) != signature):
                raise OSError("History changed during archival")
            source.unlink()
            count += 1
        return count
