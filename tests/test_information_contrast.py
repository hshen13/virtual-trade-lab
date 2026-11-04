import json
from pathlib import Path
import shutil
import tempfile
import unittest
from virtual_trade_lab.information_contrast import load,build,branch,buyer,render
ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'examples/product-information-contrast'

class InformationContrastTests(unittest.TestCase):
    def test_frozen_old_card_and_balanced_order(self):
        p,_=load(STUDY)
        self.assertEqual((STUDY/'card-X17.txt').read_bytes(),(ROOT/'examples/channel-customer-journey/product-page.txt').read_bytes())
        self.assertEqual(p['roles'],{'R1':['X17','Y62'],'R2':['Y62','X17']})
        for role,order in p['roles'].items():
            prompt=(STUDY/'prompts'/f'{role}.txt').read_text()
            self.assertLess(prompt.index('信息版本'+order[0]),prompt.index('信息版本'+order[1]))

    def test_actual_all_leave_zero_operations_and_exact_assets(self):
        r=build(STUDY)
        self.assertEqual(r,json.loads((STUDY/'report.json').read_text()))
        self.assertEqual(r['actual_calls'],2)
        for b in r['branches']:
            self.assertEqual(b['buyer']['decision'],'leave')
            self.assertIsNone(b['seller']);self.assertIsNone(b['review'])
            self.assertEqual(b['market']['balances'],{'buyer':90,'seller':40,'provider':0})
            self.assertEqual(b['market']['journal'],[]);self.assertEqual(b['market']['events'],[])
        for role in ('R1','R2'):self.assertEqual(r['records'][role]['raw'],(STUDY/'responses'/f'{role}.txt').read_text())
        html=render(STUDY,r);self.assertEqual(html,(ROOT/'virtual_trade_lab/web/information.html').read_text())
        css=(ROOT/'virtual_trade_lab/web/journey.css').read_text()
        self.assertEqual(html.replace('<link rel="stylesheet" href="/journey.css">','<style>'+css+'</style>'),(STUDY/'overview.html').read_text())

    def test_rule_branches_not_model_results(self):
        p,_=load(STUDY)
        def d(v):return {'decision':v,'reason':'synthetic regression input'}
        for review,balance in [('accept',58),('refund',90),('defer',58)]:
            state=branch(p,d('buy'),d('accept_dispatch'),d(review))
            self.assertEqual(state['balances']['buyer'],balance);self.assertEqual(sum(state['balances'].values()),130)
            self.assertEqual(len(state['journal']),2 if review=='defer' else 3)
        self.assertEqual(branch(p,d('buy'),d('decline'),None)['journal'],[])
        with self.assertRaises(ValueError):branch(p,d('leave'),d('accept_dispatch'),None)
        with self.assertRaises(ValueError):branch(p,d('buy'),None,d('accept'))

    def test_strict_parser(self):
        for raw in ('{}','{"X17":{},"X17":{},"Y62":{}}','{"X17":{"decision":"buy","reason":"x"}}'):
            with self.assertRaises(ValueError):buyer(raw)

    def test_sealed_files_cannot_change(self):
        for filename in ('card-Y62.txt','responses/R1.txt'):
            with self.subTest(filename=filename),tempfile.TemporaryDirectory() as d:
                root=Path(d)/'study';shutil.copytree(STUDY,root)
                (root/filename).write_text('changed')
                with self.assertRaises(ValueError):load(root)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'study';shutil.copytree(STUDY,root);(root/'manifest.json').unlink()
            with self.assertRaises(ValueError):load(root)
