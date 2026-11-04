from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from virtual_trade_lab.precommit_study import load,plan,run,parse,StudyStore
from virtual_trade_lab.storage import export

ROOT=Path(__file__).resolve().parents[1]/'examples/precommit-model-study'


def fixture_records(**changes):
    # Explicit synthetic test fixtures, never written to actual response files.
    p,records=load(ROOT)
    for stage,decision in changes.items():
        records[stage]={'status':'valid','parsed':{'decision':decision,'reason':'synthetic test fixture'}}
    return p,records


def execute_fixture(p,records):
    with tempfile.TemporaryDirectory() as d:
        store=StudyStore(Path(d)/'fixture.sqlite3',p,records);state=store.state()
        for action,payload in plan(p,records)['commands']:
            req=dict(epoch=state['epoch'],expected_revision=state['revision'],key='A:'+action,order_id='A',action=action,payload=payload)
            state=store.command(req)
            if StudyStore(store.path,p,records).command(req)!=state:
                raise RuntimeError('fixture retry changed state')
        return state


class PrecommitStudyTests(unittest.TestCase):
    def test_actual_six_model_replies_and_ledger_reopen(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'actual.sqlite3'
            first=run(ROOT,path);second=run(ROOT,path)
            self.assertEqual(first,second)
            self.assertEqual(first,json.loads((ROOT/'report.json').read_text()))
            self.assertEqual(first['recorded_response_count'],6)
            self.assertEqual(first['command_count'],4)
            self.assertEqual(first['state']['balances'],{'buyer':58,'seller':68,'provider':4,'escrow:A':0})
            self.assertEqual(first['plan']['handoff']['status'],'completed')
            self.assertEqual(first['state']['orders'][0]['state'],'accepted')
            self.assertEqual(len(first['state']['journal']),3)

    def test_earlier_snapshots_did_not_claim_acceptance(self):
        r=json.loads((ROOT/'snapshots/after_mutual_commit.json').read_text())
        self.assertEqual(r['state']['orders'][0]['state'],'funded')
        self.assertEqual(r['recorded_response_count'],4)
        self.assertEqual(r['state']['balances']['escrow:A'],32)
        r=json.loads((ROOT/'snapshots/after_seller_delivery.json').read_text())
        self.assertEqual(r['state']['orders'][0]['state'],'delivered')
        self.assertEqual(r['recorded_response_count'],5)
        self.assertEqual(r['plan']['handoff']['confirmations'],['seller'])

    def test_synthetic_seller_cancel_refunds_without_delivery_fee(self):
        p,r=fixture_records(seller_delivery='cancel');r['buyer_review']={'status':'missing','parsed':None}
        s=execute_fixture(p,r)
        self.assertEqual(s['orders'][0]['state'],'cancelled')
        self.assertEqual(s['balances'],{'buyer':90,'seller':40,'provider':0,'escrow:A':0})

    def test_synthetic_buyer_refund_conserved_cost_not_refunded(self):
        p,r=fixture_records(buyer_review='refund')
        s=execute_fixture(p,r)
        self.assertEqual(s['orders'][0]['state'],'rejected')
        self.assertEqual(s['balances'],{'buyer':90,'seller':36,'provider':4,'escrow:A':0})
        self.assertEqual(len(s['journal']),3)

    def test_synthetic_defer_does_not_release_escrow(self):
        p,r=fixture_records(buyer_review='defer')
        s=execute_fixture(p,r)
        self.assertEqual(s['orders'][0]['state'],'delivered')
        self.assertEqual(s['balances']['escrow:A'],32)
        self.assertEqual(plan(p,r)['handoff']['confirmations'],['seller'])

    def test_model_acceptance_does_not_override_bad_specs(self):
        p,r=fixture_records();p['delivery_fixture']=dict(p['delivery_fixture'],weight_g=320)
        s=execute_fixture(p,r)
        self.assertEqual(s['orders'][0]['state'],'delivered')
        self.assertEqual(s['balances']['escrow:A'],32)
        self.assertEqual(plan(p,r)['next_step'],'model_acceptance_conflicts_with_specs_pending')

    def test_refusal_or_missing_commit_never_funds(self):
        for choice in ('decline','defer',None):
            p,r=fixture_records()
            r['buyer_commit']={'status':'missing','parsed':None} if choice is None else {'status':'valid','parsed':{'decision':choice,'reason':'test'}}
            for stage in ('seller_delivery','buyer_review'):r[stage]={'status':'missing','parsed':None}
            self.assertEqual(plan(p,r)['commands'],[])

    def test_unpermitted_later_evidence_rejected(self):
        p,r=fixture_records(buyer_commit='decline')
        with self.assertRaisesRegex(ValueError,'unpermitted continuation'):plan(p,r)

    def test_duplicate_decision_and_tamper_rejected_before_runtime(self):
        with self.assertRaises(ValueError):parse('{"decision":"refund","decision":"accept","reason":"x"}','buyer_review')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'study';shutil.copytree(ROOT,root)
            (root/'responses/buyer_review.txt').write_text('{"decision":"refund","reason":"tamper"}')
            db=Path(d)/'runtime.sqlite3'
            with self.assertRaisesRegex(ValueError,'sealed evidence changed'):run(root,db)
            self.assertFalse(db.exists())
