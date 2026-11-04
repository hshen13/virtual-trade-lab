import json
import unittest
from virtual_trade_lab.precommit_inspection import Precommit


class PrecommitTests(unittest.TestCase):
    def prepared(self,choice='inspect',available=True):
        p=Precommit(available,{'weight_g':220,'synthetic':True})
        p.apply('b','buyer','inspection_choice',choice)
        p.apply('s','seller','inspection_choice',choice)
        return p

    def test_both_inspection_consents_required_no_purchase(self):
        p=Precommit(True,{'weight_g':220})
        p.apply('b','buyer','inspection_choice','inspect')
        self.assertIsNone(p.report())
        with self.assertRaises(ValueError):p.apply('c','buyer','commit','accept')
        p.apply('s','seller','inspection_choice','inspect')
        self.assertEqual(p.report(),{'weight_g':220})
        self.assertEqual(p.status(),'ready_inspected')
        self.assertEqual(p.snapshot()['ledger_operations'],0)

    def test_optional_skip_requires_both_and_no_report(self):
        p=self.prepared('skip')
        self.assertEqual(p.status(),'ready_uninspected')
        self.assertIsNone(p.report())
        p.apply('bc','buyer','commit','accept')
        self.assertEqual(p.status(),'awaiting_other_commit')
        p.apply('sc','seller','commit','accept')
        self.assertEqual(p.status(),'committed')

    def test_mismatch_defer_and_exit_never_commit(self):
        for choice in ('skip','defer','exit'):
            p=Precommit(True,{'weight_g':220})
            p.apply('b','buyer','inspection_choice','inspect')
            p.apply('s','seller','inspection_choice',choice)
            self.assertIsNone(p.report())
            with self.assertRaises(ValueError):p.apply('c','buyer','commit','accept')

    def test_stock_false_blocks_even_two_consents(self):
        p=self.prepared(available=False)
        self.assertEqual(p.status(),'unavailable')
        self.assertIsNone(p.report())
        with self.assertRaises(ValueError):p.apply('c','buyer','commit','accept')

    def test_decline_defer_and_withdraw_kept(self):
        for choice in ('decline','defer'):
            p=self.prepared();p.apply('bc','buyer','commit',choice)
            with self.assertRaises(ValueError):p.apply('sc','seller','commit','accept')
        p=self.prepared();p.apply('bc','buyer','commit','accept')
        p.apply('w','seller','withdraw','cannot_handoff')
        self.assertEqual(p.status(),'withdrawn')
        with self.assertRaises(ValueError):p.apply('sc','seller','commit','accept')

    def test_replay_retry_conflict_and_invalid_actor(self):
        p=self.prepared();snap=p.snapshot()
        r=Precommit.replay(True,{'weight_g':220,'synthetic':True},json.loads(json.dumps(p.events)))
        self.assertEqual(r.snapshot(),snap)
        for e in p.events:self.assertFalse(r.apply(**e))
        with self.assertRaises(ValueError):r.apply('b','buyer','inspection_choice','skip')
        with self.assertRaises(ValueError):r.apply('x','coordinator','commit','accept')
        self.assertEqual(r.snapshot(),snap)

    def test_report_is_detached_and_not_mutable_consent(self):
        p=self.prepared();r=p.report();r['weight_g']=320
        self.assertEqual(p.report()['weight_g'],220)
        with self.assertRaises(ValueError):p.apply('x','buyer','inspection_choice','skip')

    def test_no_report_cannot_be_called_inspected(self):
        p=Precommit(True,None)
        p.apply('b','buyer','inspection_choice','inspect')
        p.apply('s','seller','inspection_choice','inspect')
        self.assertEqual(p.status(),'inspection_unavailable')
        with self.assertRaises(ValueError):p.apply('c','buyer','commit','accept')
