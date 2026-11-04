"""Adversarial evidence tests use synthetic copies, never change saved responses."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'examples'


class EvidenceIntegrityTests(unittest.TestCase):
    def check_both(self, mutate, invalid_reply=False):
        for study in ('model-order-sensitivity', 'model-order-repeats'):
            with self.subTest(study=study), tempfile.TemporaryDirectory() as tmp:
                source = ROOT / study
                path = Path(tmp) / 'evidence'
                shutil.copytree(source, path)
                spec = importlib.util.spec_from_file_location('replay', source / 'replay.py')
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                mutate(path)
                if invalid_reply:
                    result = module.summarize(path)
                    self.assertEqual(result['failures'], 1)
                    row = next(row for row in result['rows'] if row['status'] == 'invalid')
                    self.assertIsNone(row['decision'])
                    self.assertIsNone(row['raw'])
                    self.assertEqual(row['sha256'], hashlib.sha256(b'\xff').hexdigest())
                    if study.endswith('repeats'):
                        self.assertIsNone(result['cells']['L_AB']['within_prompt_disagreement'])
                    else:
                        self.assertIsNone(result['order_agreement']['L'])
                else:
                    with self.assertRaises(ValueError):
                        module.summarize(path)

    def test_empty_manifest_fails_closed(self):
        self.check_both(lambda p: (p/'freeze.sha256').write_text(''))

    def test_missing_protocol_manifest_entry_fails_closed(self):
        self.check_both(lambda p: self.edit_manifest(p, lambda lines: lines[1:]))

    def test_missing_prompt_manifest_entry_fails_closed(self):
        self.check_both(lambda p: self.edit_manifest(p, lambda lines: lines[:-1]))

    def test_duplicate_manifest_entry_rejected(self):
        self.check_both(lambda p: self.edit_manifest(p, lambda lines: lines + [lines[0]]))

    def test_unexpected_manifest_path_rejected(self):
        self.check_both(lambda p: self.edit_manifest(p, lambda lines: lines + ['0'*64+'  ../outside']))

    def test_malformed_digest_rejected(self):
        self.check_both(lambda p: self.edit_manifest(p, lambda lines: ['z'*64+'  protocol.json']+lines[1:]))

    def test_duplicate_runs_cannot_change_denominator_even_with_updated_hash(self):
        self.check_both(lambda p: self.edit_protocol(p, lambda cases: cases.__setitem__(1, cases[0])))

    def test_dropped_run_cannot_change_denominator_even_with_updated_hash(self):
        self.check_both(lambda p: self.edit_protocol(p, lambda cases: cases.pop()))

    def test_prompt_mapping_cannot_change_even_with_updated_hash(self):
        self.check_both(lambda p: self.edit_protocol(p, lambda cases: cases[0].update(prompt_file='H_BA.prompt.txt')))

    def test_condition_cannot_change_even_with_updated_hash(self):
        self.check_both(lambda p: self.edit_protocol(p, lambda cases: cases[0].update(condition='H_AB', a_price=999)))

    def test_non_utf8_response_preserved_as_failure(self):
        self.check_both(lambda p: next(p.glob('L_AB*.raw.txt')).write_bytes(b'\xff'), invalid_reply=True)

    @staticmethod
    def edit_manifest(path, transform):
        manifest = path/'freeze.sha256'
        manifest.write_text('\n'.join(transform(manifest.read_text().splitlines()))+'\n')

    @staticmethod
    def edit_protocol(path, transform):
        protocol = path/'protocol.json'
        value = json.loads(protocol.read_text())
        transform(value.get('runs', value.get('cases')))
        protocol.write_text(json.dumps(value))
        digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
        EvidenceIntegrityTests.edit_manifest(path, lambda lines: [digest+'  protocol.json']+lines[1:])
