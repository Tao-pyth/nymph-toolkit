"""Disk invariants: atomic settings, replayable batches, verified scoped archival."""

# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nymph_toolkit.contracts import BindingKey, BindingRecord, ContractKey, StorageCorruptionError
from nymph_toolkit.core import _storage_io
from nymph_toolkit.core._storage_io import Disk


class StorageIOTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ntk-io-test-")
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.disk = Disk(base / "primary", base / "archive", timedelta(days=2))
        self.disk.initialize()
        self.now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
        self.record = BindingRecord(BindingKey("a", ContractKey("read", "1")), "b")

    def event(self, sequence=1, days=5, run_id="a" * 32):
        return {"format": "ntk.history.v1", "run_id": run_id, "sequence": sequence,
                "at": (self.now - timedelta(days=days)).isoformat(), "kind": "usage", "data": {"active": sequence}}

    def write_history(self, event):
        batch = self.disk.history_batch((event,))
        batch.write()
        return next(iter(batch.protected))

    def test_settings_round_trip_and_failed_replace_preserves_original(self):
        self.assertEqual(self.disk.load_bindings(), ())
        self.disk.save_bindings((self.record,))
        before = self.disk.settings.read_bytes()
        with patch.object(_storage_io.os, "replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.disk.save_bindings(())
        self.assertEqual(self.disk.settings.read_bytes(), before)
        self.assertEqual(self.disk.load_bindings(), (self.record,))
        self.assertFalse(list(self.disk.root.glob(".ntk-settings-*.tmp")))

    def test_corrupt_duplicate_unknown_settings_are_not_silently_reset(self):
        for raw in (b"", b"{", b'{"schema_version":1,"schema_version":1,"bindings":[]}',
                    b'{"schema_version":true,"bindings":[]}', b'{"schema_version":99,"bindings":[]}',
                    b'{"schema_version":1,"bindings":{},"extra":0}'):
            with self.subTest(raw=raw):
                self.disk.settings.write_bytes(raw)
                with self.assertRaises(StorageCorruptionError):
                    self.disk.load_bindings()
                self.assertEqual(self.disk.settings.read_bytes(), raw)
        self.disk.save_bindings((self.record,))
        data = json.loads(self.disk.settings.read_text())
        data["bindings"] *= 2
        self.disk.settings.write_text(json.dumps(data))
        with self.assertRaises(StorageCorruptionError):
            self.disk.load_bindings()

    def test_partial_batch_retry_does_not_duplicate_committed_prefix(self):
        path = self.write_history(self.event(1))
        next_day = self.event(3, days=4)
        batch = self.disk.history_batch((self.event(2), next_day))
        original = _storage_io._append
        writes = 0
        def partial(target, baseline, content):
            nonlocal writes
            writes += 1
            if writes == 2:
                with target.open("wb") as stream:
                    stream.write(content[:9])
                raise OSError("partial write")
            original(target, baseline, content)
        with patch.object(_storage_io, "_append", side_effect=partial):
            with self.assertRaises(OSError):
                batch.write()
        batch.write()
        sequences = []
        for history in sorted(batch.protected | {path}):
            sequences.extend(json.loads(line)["sequence"] for line in history.read_text().splitlines())
        self.assertEqual(sequences, [1, 2, 3])

    def test_archive_moves_only_expired_owned_and_unprotected_history(self):
        old = self.write_history(self.event(1, days=5))
        protected = self.write_history(self.event(2, days=4))
        recent = self.write_history(self.event(3, days=1))
        foreign = self.disk.root / ("history-2026-11-01-" + "c" * 32 + ".jsonl")
        foreign.write_text('{"user":"data"}\n')
        self.disk.save_bindings((self.record,))
        content = old.read_bytes()
        self.assertEqual(self.disk.archive_old(self.now, frozenset({protected})), 1)
        self.assertFalse(old.exists())
        self.assertEqual((self.disk.archive / old.name).read_bytes(), content)
        self.assertTrue(protected.exists() and recent.exists() and foreign.exists())
        self.assertEqual(self.disk.load_bindings(), (self.record,))

    def test_failed_copy_keeps_source_and_no_final_archive(self):
        source = self.write_history(self.event())
        before = source.read_bytes()
        with patch.object(_storage_io.shutil, "copyfileobj", side_effect=OSError("archive full")):
            with self.assertRaises(OSError):
                self.disk.archive_old(self.now)
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse((self.disk.archive / source.name).exists())
        self.assertFalse(list(self.disk.archive.glob(".ntk-archive-*.tmp")))

    def test_archive_collision_never_overwrites_different_history(self):
        source = self.write_history(self.event())
        self.disk.archive.mkdir()
        destination = self.disk.archive / source.name
        destination.write_bytes(b"different history")
        with self.assertRaises(FileExistsError):
            self.disk.archive_old(self.now)
        self.assertTrue(source.exists())
        self.assertEqual(destination.read_bytes(), b"different history")
        destination.write_bytes(source.read_bytes())
        self.assertEqual(self.disk.archive_old(self.now), 1)
        self.assertFalse(source.exists())

    def test_primary_archive_overlap_and_invalid_retention_are_rejected(self):
        with self.assertRaises(ValueError):
            Disk(self.disk.root, self.disk.root / "archive", timedelta(days=1))
        with self.assertRaises(ValueError):
            Disk(self.disk.root, self.disk.root.parent, timedelta(days=1))
        with self.assertRaises(ValueError):
            Disk(self.disk.root, self.disk.archive, timedelta(days=-1))

    def test_period_boundary_uses_end_of_utc_day(self):
        source = self.write_history(self.event(days=2))
        self.assertEqual(self.disk.archive_old(self.now), 0)
        self.assertTrue(source.exists())
        self.assertEqual(self.disk.archive_old(self.now + timedelta(hours=12)), 1)


if __name__ == "__main__":
    unittest.main()
