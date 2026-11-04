import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'examples/model-order-repeats'
spec = importlib.util.spec_from_file_location('repeats_replay', ROOT / 'replay.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OrderRepeatTests(unittest.TestCase):
    def test_report_all_eight_and_within_prompt_disagreement(self):
        result = module.summarize(ROOT)
        self.assertEqual(result, json.loads((ROOT/'results.json').read_text()))
        self.assertEqual(len(result['rows']),8)
        for key in ('L_AB','L_BA'):
            self.assertEqual(result['cells'][key]['counts'],{'A':2,'B':0,'no_buy':0})
            self.assertFalse(result['cells'][key]['within_prompt_disagreement'])
        for key in ('H_AB','H_BA'):
            self.assertEqual(result['cells'][key]['counts'],{'A':0,'B':1,'no_buy':1})
            self.assertTrue(result['cells'][key]['within_prompt_disagreement'])
        self.assertEqual(result['executed_ledger_commands'],0)

    def test_missing_invalid_not_reclassified_no_buy(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'evidence';shutil.copytree(ROOT,p)
            (p/'H_AB_r1.raw.txt').unlink()
            (p/'H_BA_r1.raw.txt').write_text('null')
            result=module.summarize(p)
            self.assertEqual(result['failures'],2)
            self.assertIsNone(result['cells']['H_AB']['within_prompt_disagreement'])
            self.assertEqual(result['cells']['H_AB']['counts']['no_buy'],0)

    def test_protocol_tamper_rejected_under_optimized_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'evidence';shutil.copytree(ROOT,p)
            (p/'protocol.json').write_text('{}')
            with self.assertRaises(ValueError):module.summarize(p)

    def test_exactly_two_repetitions_and_original_prompt_bytes(self):
        protocol=json.loads((ROOT/'protocol.json').read_text())
        self.assertEqual(len({r['id'] for r in protocol['runs']}),8)
        for condition in ('L_AB','L_BA','H_AB','H_BA'):
            self.assertEqual(sum(r['condition']==condition for r in protocol['runs']),2)
            self.assertEqual((ROOT/(condition+'.prompt.txt')).read_bytes(),
                             (ROOT.parent/'model-order-sensitivity'/(condition+'.prompt.txt')).read_bytes())
