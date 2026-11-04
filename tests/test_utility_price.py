import json
from pathlib import Path
import shutil
import tempfile
import unittest
from virtual_trade_lab.utility_price import load,result,choice,render
from virtual_trade_lab.information_contrast import branch
ROOT=Path(__file__).resolve().parents[1];STUDY=ROOT/'examples/product-utility-price-v2'

class UtilityPriceTests(unittest.TestCase):
    def test_price_is_only_v2_option_difference(self):
        p,_=load(STUDY);first=None;positions={k:[0,0,0] for k in ('old','original','v2')}
        for c in p['cases'].values():
            v=c['options']['v2'].copy();v.pop('price')
            if first is None:first=v
            self.assertEqual(v,first)
            self.assertEqual(c['options']['old']['price'],0);self.assertEqual(c['options']['original']['price'],32)
            for i,k in enumerate(c['order']):positions[k][i]+=1
        self.assertEqual(positions,dict.fromkeys(('old','original','v2'),[2,2,2]))

    def test_exact_actual_result_and_capacity_failure(self):
        r=result(STUDY);self.assertEqual(r,json.loads((STUDY/'report.json').read_text()))
        self.assertEqual(r['actual_responses'],11)
        cases={c['case']:c for c in r['cases']}
        fail=cases['adequate-32'];self.assertIsNone(fail['buyer']);self.assertEqual(fail['failure']['status'],'infrastructure_error')
        for key in ('adequate-16','adequate-24'):self.assertEqual(cases[key]['buyer']['choice'],'old')
        for price in (16,24,32):
            c=cases[f'pain-{price}'];self.assertEqual(c['buyer']['choice'],'v2');self.assertEqual(c['review']['decision'],'accept')
            self.assertEqual(c['market']['balances'],{'buyer':90-price,'seller':36+price,'provider':4,'escrow:comparison-order':0})
        for c in r['cases']:self.assertEqual(sum(c['market']['balances'].values()),130)
        self.assertEqual(render(STUDY,r),(ROOT/'virtual_trade_lab/web/utility.html').read_text())

    def test_pre_review_snapshots_did_not_settle(self):
        for path in (STUDY/'snapshots').glob('*.json'):
            r=json.loads(path.read_text())
            for c in r['cases']:
                if c['seller']:
                    self.assertIsNone(c['review']);self.assertEqual(c['market']['orders'][0]['state'],'delivered')
                    self.assertEqual(c['market']['balances']['escrow:comparison-order'],c['v2_price'])

    def test_verbatim_outputs_and_no_external_mutation_ui(self):
        r=result(STUDY)
        for key,row in r['records'].items():
            if row['status']!='missing':self.assertEqual(row['raw'],(STUDY/'responses'/f'{key}.txt').read_text())
        html=render(STUDY,r)
        self.assertNotIn('<script',html);self.assertNotIn('/api/',html)
        self.assertIsNone(r['price_elasticity']);self.assertIsNone(r['empirical_conversion'])
        self.assertFalse(r['cost_or_profit_validated'])

    def test_seal_change_or_missing_rejected(self):
        for name in ('responses/pain-16.txt','failures.json','prompts/pain-24.txt'):
            with tempfile.TemporaryDirectory() as d:
                r=Path(d)/'study';shutil.copytree(STUDY,r);(r/name).write_text('bad')
                with self.assertRaises(ValueError):load(r)
        with tempfile.TemporaryDirectory() as d:
            r=Path(d)/'study';shutil.copytree(STUDY,r);(r/'manifest.json').unlink()
            with self.assertRaises(FileNotFoundError):load(r)

    def test_parser_and_negative_rule_paths(self):
        with self.assertRaises(ValueError):choice('{"choice":"v2","choice":"old","reason":"x"}')
        with self.assertRaises(ValueError):choice('{"choice":"buy","reason":"x"}')
        p={'price':16,'delivery_cost':4,'delivery':{'id':'v2'}}
        d=lambda c:{'decision':c,'reason':'synthetic test, not actual model'}
        self.assertEqual(branch(p,d('buy'),d('decline'),None)['journal'],[])
        refund=branch(p,d('buy'),d('accept_dispatch'),d('refund'))
        self.assertEqual(refund['balances']['buyer'],90)
        self.assertEqual(sum(refund['balances'].values()),130)
        with self.assertRaises(ValueError):branch(p,d('leave'),d('accept_dispatch'),None)
