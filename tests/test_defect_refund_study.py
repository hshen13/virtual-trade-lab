from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from virtual_trade_lab.precommit_study import load,plan,run,StudyStore,DEFECT_PIN,spec_issues

ROOT=Path(__file__).resolve().parents[1]/'examples/defect-refund-model-study'


def fixture(review):
    # Synthetic UNIT TEST replies only. Actual model files are never modified.
    p,r=load(ROOT)
    for stage,choice in [('buyer_inspection','inspect'),('seller_inspection','inspect'),('buyer_commit','accept'),('seller_commit','accept'),('seller_delivery','deliver'),('buyer_review',review)]:
        r[stage]={'status':'valid','parsed':{'decision':choice,'reason':'synthetic test fixture'}}
    return p,r


def execute(p,r):
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'fixture.sqlite3';store=StudyStore(path,p,r);state=store.state()
        for a,payload in plan(p,r)['commands']:
            request=dict(epoch=state['epoch'],expected_revision=state['revision'],key='A:'+a,order_id='A',action=a,payload=payload)
            state=store.command(request)
            if StudyStore(path,p,r).command(request)!=state:raise RuntimeError('duplicate changed state')
        return state


class DefectRefundTests(unittest.TestCase):
    def test_frozen_information_partition(self):
        p,_=load(ROOT)
        self.assertEqual(p['inspection_fixture']['unit_id'],'unit-A')
        self.assertEqual(p['delivery_fixture']['unit_id'],'unit-B')
        dispatch=(ROOT/'prompts/seller_delivery_actual.txt').read_text()
        self.assertNotIn('unit-B',dispatch)
        self.assertNotIn('320',dispatch)
        self.assertIn('content_rechecked',dispatch)
        self.assertEqual(spec_issues(p),['unit_identifier_mismatch','listing_weight_mismatch'])

    def test_rule_buyer_can_refund_without_fabricated_seller_approval(self):
        p,r=fixture('refund');s=execute(p,r)
        self.assertEqual(s['orders'][0]['state'],'rejected')
        self.assertEqual(s['balances'],{'buyer':90,'seller':36,'provider':4,'escrow:A':0})
        self.assertEqual([j['reason'] for j in s['journal']],['fund','compute','reject_refund'])

    def test_rule_disclosed_mismatch_acceptance_is_not_forced_refund(self):
        p,r=fixture('accept');s=execute(p,r)
        self.assertEqual(s['orders'][0]['state'],'accepted')
        self.assertEqual(s['balances'],{'buyer':58,'seller':68,'provider':4,'escrow:A':0})
        self.assertTrue(spec_issues(p))
        self.assertEqual(plan(p,r)['handoff']['inspection'],0)

    def test_rule_defer_retains_escrow(self):
        p,r=fixture('defer');s=execute(p,r)
        self.assertEqual(s['orders'][0]['state'],'delivered')
        self.assertEqual(s['balances']['escrow:A'],32)

    def test_old_no_waiver_policy_still_blocks_acceptance(self):
        p,r=fixture('accept');p['allow_buyer_disclosed_mismatch_acceptance']=False
        s=execute(p,r)
        self.assertEqual(s['orders'][0]['state'],'delivered')
        self.assertEqual(s['balances']['escrow:A'],32)

    def test_original_and_defect_schema_distinct(self):
        p,r=load(ROOT)
        oldp,oldr=load(ROOT.parent/'precommit-model-study')
        with tempfile.TemporaryDirectory() as d:
            a=StudyStore(Path(d)/'a.sqlite3',p,r)
            b=StudyStore(Path(d)/'b.sqlite3',oldp,oldr)
            self.assertNotEqual(a.SCHEMA,b.SCHEMA)

    def test_actual_model_refund_restart_repeat_exact_report(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'actual.sqlite3';first=run(ROOT,path);second=run(ROOT,path)
            self.assertEqual(first,second)
            self.assertEqual(first,json.loads((ROOT/'report.json').read_text()))
            self.assertEqual(first['recorded_response_count'],6)
            self.assertEqual(first['records']['buyer_review']['parsed']['decision'],'refund')
            self.assertEqual(first['state']['balances'],{'buyer':90,'seller':36,'provider':4,'escrow:A':0})
            self.assertEqual(first['state']['orders'][0]['state'],'rejected')
            self.assertFalse(first['defect_assessment']['mismatch_waived_by_buyer'])
            self.assertEqual(first['plan']['handoff']['confirmations'],['seller'])
            self.assertEqual(len(first['state']['journal']),3)

    def test_actual_prompt_derivation_cannot_leak_hidden_result(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'study';shutil.copytree(ROOT,root)
            target=root/'prompts/seller_delivery_actual.txt'
            target.write_text(target.read_text()+'hidden contents320g')
            with self.assertRaisesRegex(ValueError,'frozen derivation'):load(root)

    def test_snapshots_do_not_pretend_refund_before_request(self):
        first=json.loads((ROOT/'snapshots/after_mutual_commit.json').read_text())
        second=json.loads((ROOT/'snapshots/after_seller_delivery.json').read_text())
        self.assertEqual(first['recorded_response_count'],4)
        self.assertEqual(second['recorded_response_count'],5)
        self.assertEqual(first['state']['balances']['escrow:A'],32)
        self.assertEqual(second['state']['balances']['escrow:A'],32)
        self.assertEqual(second['records']['buyer_review']['status'],'missing')
