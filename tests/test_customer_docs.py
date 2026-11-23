"""Regression checks for stale customer guidance and changed deliverables."""

# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.check_customer_docs import RECORD, artifacts, compact_text, digest, inputs, validate


class CustomerDocsChecks(unittest.TestCase):
    def test_cjk_pdf_title_normalization_keeps_different_text_distinct(self):
        self.assertEqual(compact_text('契約・利用ガイド'), compact_text('契約・利⽤\nガイド'))
        self.assertNotEqual(compact_text('契約・利用ガイド'), compact_text('契約・停止ガイド'))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.put('pyproject.toml', '[project]\nversion="1.3.0"\n')
        self.put('docs/customer-guide.md', '# Guide\n\n**Nymph Toolkit / 対象 v1.3.0（開発候補） / 公開版 v1.2.0 / 2026-11-23**\n')
        self.put('docs/contracts-v1.json', '{}\n')
        self.put('docs/architecture.md', 'Current architecture\n')
        self.put('docs/adr/0030-test.md', 'Decision\n')
        self.put('src/example.py', 'value = 1\n')
        self.put('examples/demo.py', 'print(1)\n')
        self.record = dict(schema=1, version='1.3.0', status='development', published_version='1.2.0',
                           reviewed_on='2026-11-23', review_note='Reviewed fixture', sources=inputs(self.root))
        self.save()

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def save(self):
        self.put(RECORD, json.dumps(self.record, ensure_ascii=False))

    def test_reviewed_inputs_pass_but_changed_source_is_rejected(self):
        validate(self.root)
        self.put('src/example.py', 'value = 2\n')
        with self.assertRaisesRegex(AssertionError, 'src/example.py'):
            validate(self.root)

    def test_new_or_removed_modules_cannot_escape_inventory(self):
        new = self.put('src/new_module.py', 'new = True\n')
        with self.assertRaisesRegex(AssertionError, 'new_module'):
            validate(self.root)
        new.unlink()
        (self.root / 'src/example.py').unlink()
        with self.assertRaisesRegex(AssertionError, 'example.py'):
            validate(self.root)

    def test_major_docs_and_decisions_trigger_review(self):
        self.put('docs/adr/0030-test.md', 'New decision\n')
        with self.assertRaisesRegex(AssertionError, '0030-test.md'):
            validate(self.root)

    def test_old_target_or_release_state_is_rejected(self):
        self.record['version'] = '1.2.0'; self.save()
        with self.assertRaisesRegex(AssertionError, 'target version'):
            validate(self.root)
        self.record['version'] = '1.3.0'; self.record['status'] = 'released'; self.save()
        with self.assertRaises(AssertionError):
            validate(self.root)

    def test_hash_refresh_does_not_hide_stale_cover(self):
        self.put('docs/customer-guide.md', '# Guide\nOld v0.9 guide\n')
        self.record['sources'] = inputs(self.root); self.save()
        with self.assertRaisesRegex(AssertionError, 'cover metadata'):
            validate(self.root)

    def test_changed_artifacts_or_sources_are_rejected_before_pdf_parsing(self):
        out = self.root / 'output'; out.mkdir()
        stem = 'NTK-v1.3.0-Customer-Guide-ja'
        generator = ('build.mjs', 'print.css', 'package.json', 'pnpm-lock.yaml')
        for name in generator:
            self.put('tools/customer-docs/' + name, 'fixture')
        manifest = dict(source_sha256=digest(self.root / 'docs/customer-guide.md'), review_sha256=digest(self.root / RECORD),
                        version='1.3.0', status='development', reference='a'*40, working_tree_dirty=False,
                        generator_inputs={'tools/customer-docs/'+name: digest(self.root/'tools/customer-docs'/name) for name in generator})
        for ext in ('.md', '.pdf', '.html'):
            (out / (stem + ext)).write_bytes(b'original')
        manifest['files'] = {stem+ext: digest(out/(stem+ext)) for ext in ('.md', '.pdf', '.html')}
        target = out / (stem + '.json')
        target.write_text(json.dumps(manifest))
        with patch('tools.check_customer_docs.subprocess.check_output', return_value='b'*40):
            with self.assertRaisesRegex(AssertionError, 'checked-out commit'):
                artifacts(out, self.root, require_clean=True)
        (out / (stem + '.pdf')).write_bytes(b'modified')
        with self.assertRaisesRegex(AssertionError, 'Artifact missing or modified'):
            artifacts(out, self.root)
        manifest['source_sha256'] = '0'*64
        target.write_text(json.dumps(manifest))
        with self.assertRaises(AssertionError):
            artifacts(out, self.root)
