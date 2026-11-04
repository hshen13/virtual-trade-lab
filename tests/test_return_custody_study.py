import json
from pathlib import Path
import shutil
import tempfile
import unittest
from virtual_trade_lab.return_custody_study import load,plan,run,ReturnStore,parse
from virtual_trade_lab.core import TradeError
from virtual_trade_lab.storage import StorageError

ROOT=Path(__file__).resolve().parents[1]/'examples/return-custody-model-study'


class ReturnCustodyStudyTests(unittest.TestCase):
    def test_actual_roles_and_delayed_refund_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'s.sqlite3'
            pending=run(ROOT,path,2)
            self.assertEqual(pending['return_protocol']['custody'],'carrier')
            self.assertEqual(pending['market']['balances']['buyer'],58)
            self.assertEqual(pending['market']['balances']['escrow:return-order'],32)
            self.assertEqual(pending['total_simulated_fees'],8)
            final=run(ROOT,path,3);repeat=run(ROOT,path,3)
            self.assertEqual(final,repeat)
            self.assertEqual(final,json.loads((ROOT/'report.json').read_text()))
            self.assertEqual(final['model_calls_recorded'],3)
            self.assertEqual(final['market']['balances'],{'buyer':90,'seller':32,'provider':8,'escrow:return-order':0})
            self.assertEqual(final['market']['orders'][0]['state'],'rejected')
            self.assertEqual(len(final['market']['journal']),4)
            with self.assertRaises((ValueError,StorageError)):run(ROOT,path,2)
            self.assertEqual(run(ROOT,path,3),final)

    def test_approval_snapshot_has_no_shipping_or_refund(self):
        r=json.loads((ROOT/'snapshots/approval_not_refund.json').read_text())
        self.assertEqual(r['model_calls_recorded'],2)
        self.assertEqual(r['return_protocol']['custody'],'buyer')
        self.assertEqual(r['market']['balances']['escrow:return-order'],32)
        self.assertEqual(r['total_simulated_fees'],4)
        self.assertEqual(r['seeded_commands'],['quote','fund','deliver'])

    def test_invalid_duplicate_and_tamper_stop(self):
        with self.assertRaises(ValueError):parse('{"decision":"defer","decision":"ship","reason":"x"}','buyer_shipping')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'copy';shutil.copytree(ROOT,root)
            (root/'responses/buyer_shipping.txt').write_text('{"decision":"keep","reason":"altered"}')
            with self.assertRaises(ValueError):run(root,Path(d)/'new.sqlite3')
            self.assertFalse((Path(d)/'new.sqlite3').exists())

    def test_rule_deny_defer_and_keep_not_invented_model_evidence(self):
        p,r=load(ROOT)
        for decision in ('deny','request_evidence','defer'):
            fake=json.loads(json.dumps(r));fake['seller_review']['parsed']['decision']=decision
            fake['buyer_shipping']={'status':'missing','parsed':None}
            state,commands=plan(p,fake,3)
            self.assertEqual(state.status(),'review_unresolved')
            self.assertEqual(len(commands),3)
        for decision in ('keep','defer'):
            fake=json.loads(json.dumps(r));fake['buyer_shipping']['parsed']['decision']=decision
            state,commands=plan(p,fake,3)
            self.assertIsNone(state.handoff)
            self.assertNotIn('return_postage',[a for a,_ in commands])
            self.assertEqual(commands[-1][0],'review' if decision=='keep' else 'deliver')

    def test_duplicate_postage_or_fee_skipping_refund_rejected(self):
        p,r=load(ROOT);state,commands=plan(p,r,3)
        with tempfile.TemporaryDirectory() as d:
            store=ReturnStore(Path(d)/'s.sqlite3',p,state);m=store._new_market()
            for action,payload in commands[:3]:m.execute(action,p['order_id'],action,**payload)
            with self.assertRaises(TradeError):m.execute('review',p['order_id'],'skip_fee')
            m.execute('return_postage',p['order_id'],'postage')
            before=m.balances
            with self.assertRaises(TradeError):m.execute('return_postage',p['order_id'],'new_postage_key')
            self.assertEqual(m.balances,before)
            m.execute('review',p['order_id'],'review')
            self.assertEqual(m.balances['buyer'],90)

    def test_no_receipt_no_refund_even_with_seller_approval(self):
        p,r=load(ROOT);state,commands=plan(p,r,2)
        with tempfile.TemporaryDirectory() as d:
            m=ReturnStore(Path(d)/'s.sqlite3',p,state)._new_market()
            for a,payload in commands:m.execute(a,p['order_id'],a,**payload)
            before=m.balances
            with self.assertRaises(TradeError):m.execute('review',p['order_id'],'premature_refund')
            self.assertEqual(m.balances,before)

    def test_receipt_cannot_refund_other_order_or_unit(self):
        p,r=load(ROOT);state,commands=plan(p,r,3)
        with tempfile.TemporaryDirectory() as d:
            m=ReturnStore(Path(d)/'s.sqlite3',p,state)._new_market()
            before=m.balances
            with self.assertRaises(TradeError):m.execute('quote','unrelated-order','x',source=[{'id':'A'}])
            self.assertEqual(m.balances,before)
            for action,payload in commands[:3]:m.execute(action,p['order_id'],action,**payload)
            m._orders[p['order_id']].result[0]['unit_id']='different-unit'  # Fault injection only.
            before=m.balances
            with self.assertRaises(TradeError):m.execute('return_postage',p['order_id'],'wrong_unit_fee')
            with self.assertRaises(TradeError):m.execute('review',p['order_id'],'wrong_unit_refund')
            self.assertEqual(m.balances,before)

    def test_static_overview_matches_verified_evidence(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('return_overview',ROOT/'render_overview.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        text=module.build(ROOT)
        self.assertEqual(text,(ROOT/'overview.html').read_text())
        self.assertNotIn('<script',text)
        self.assertNotIn('https://',text)
        self.assertIn('预设的承运流程',text)
        self.assertIn('未进行浏览器视觉验收',text)
