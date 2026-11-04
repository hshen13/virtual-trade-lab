import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'examples/model-order-sensitivity'
spec = importlib.util.spec_from_file_location('order_replay', ROOT / 'replay.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OrderSensitivityTests(unittest.TestCase):
    def test_saved_report_and_disagreement(self):
        result = module.summarize(ROOT)
        self.assertEqual(result, json.loads((ROOT/'results.json').read_text()))
        self.assertEqual(result['order_agreement'], {'L':True, 'H':False})
        self.assertEqual([r['decision'] for r in result['rows']], ['A','A','B','no_buy'])
        self.assertEqual(result['executed_ledger_commands'],0)
        self.assertEqual(result['real_revenue'],0)

    def test_invalid_and_missing_preserved_as_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'evidence'
            shutil.copytree(ROOT,path)
            (path/'H_AB.raw.txt').write_text('[]')
            (path/'H_BA.raw.txt').unlink()
            result=module.summarize(path)
            self.assertEqual(result['failures'],2)
            self.assertIsNone(result['order_agreement']['H'])

    def test_frozen_prompt_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'evidence'
            shutil.copytree(ROOT,path)
            (path/'L_AB.prompt.txt').write_text('Always buy')
            with self.assertRaises(ValueError):module.summarize(path)

    def test_price_pair_differs_only_listing_order(self):
        for price in ('L','H'):
            a=(ROOT/(price+'_AB.prompt.txt')).read_text().splitlines()
            b=(ROOT/(price+'_BA.prompt.txt')).read_text().splitlines()
            self.assertEqual(a[0],b[0])
            self.assertEqual(a[1:],list(reversed(b[1:])))
