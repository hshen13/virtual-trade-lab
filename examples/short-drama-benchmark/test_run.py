import hashlib
import struct
import json
import tempfile
import unittest
from pathlib import Path
from run import build, candidates, simulate

class FixtureTests(unittest.TestCase):
    def test_duration_and_negative_control(self):
        c = candidates()
        self.assertEqual([sum(s['duration'] for s in x) for x in c.values()], [60,60,60])
        for p in ('pace', 'clarity', 'quiet'):
            self.assertLess(simulate(c['negative_control'], p), simulate(c['revision'], p))
    def test_sensitivity_reverses_conclusion(self):
        c = candidates()
        self.assertGreater(simulate(c['revision'], 'pace'), simulate(c['baseline'], 'pace'))
        self.assertLess(simulate(c['revision'], 'quiet'), simulate(c['baseline'], 'quiet'))
    def test_reproducible_and_no_real_evidence(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            r = build(Path(a)); self.assertEqual(r, build(Path(b)))
            self.assertEqual(r['human_participants'], 0)
            self.assertIsNone(r['watch_retention'])
            self.assertEqual(len((Path(a)/'human-ratings-empty.csv').read_text().splitlines()), 1)
            self.assertTrue(all('revision' not in p.read_text() for p in Path(a).glob('clip-*.json')))
            assignments = json.loads((Path(a)/'planned-assignments.json').read_text())
            self.assertEqual(sum(x['first'] == assignments[0]['first'] for x in assignments),6)
    def test_repeat_output_stable(self):
        with tempfile.TemporaryDirectory() as a:
            self.assertEqual(build(Path(a)), build(Path(a)))

class AssetTests(unittest.TestCase):
    def test_generated_image_integrity_and_honest_manifest(self):
        root = Path(__file__).parent / 'assets'
        manifest = json.loads((root / 'generation-manifest.json').read_text())
        raw = (root / manifest['artifact']).read_bytes()
        self.assertEqual(raw[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest['sha256'])
        self.assertEqual(struct.unpack('>II',raw[16:24]), (manifest['width'],manifest['height']))
        self.assertEqual(manifest['native_image_generation_calls'],1)
        self.assertEqual(manifest['video_generation_calls'],0)
        self.assertEqual(manifest['human_audience_evaluations'],0)
        self.assertEqual(manifest['billing_status'],'not_inspected')


if __name__ == '__main__':
    unittest.main()
