import unittest
from virtual_trade_lab.return_custody import ReturnProtocol


def ready():
    p=ReturnProtocol();p.apply('b','buyer','request','request_refund');p.apply('s','seller','review','approve_return');p.apply('ship','buyer','shipping','ship');return p


def evidence(tick=1,**kw):return dict(order='return-order',label='return-A',unit='unit-B',tick=tick,**kw)


class ReturnCustodyTests(unittest.TestCase):
    def test_approval_not_receipt_or_refund(self):
        p=ReturnProtocol();p.apply('b','buyer','request','request_refund');p.apply('s','seller','review','approve_return')
        self.assertFalse(p.snapshot()['refund_ready']);self.assertEqual(p.snapshot()['custody'],'buyer')

    def test_matched_handoff_then_delayed_receipt(self):
        p=ready();p.apply('h','carrier','handoff',evidence())
        self.assertEqual(p.status(),'awaiting_receipt');self.assertFalse(p.snapshot()['refund_ready'])
        with self.assertRaises(ValueError):p.apply('r','carrier','receipt',evidence(2))
        p.apply('r','carrier','receipt',evidence(3))
        self.assertTrue(p.snapshot()['refund_ready']);self.assertEqual(p.snapshot()['custody'],'seller')

    def test_wrong_unit_label_order_and_tick_fail_without_mutation(self):
        p=ready();before=p.snapshot()
        for k,v in [('unit','other'),('label','other'),('order','other'),('tick',True),('tick',3)]:
            bad=evidence();bad[k]=v
            with self.assertRaises(ValueError):p.apply('x','carrier','handoff',bad)
            self.assertEqual(p.snapshot(),before)

    def test_no_shipping_consent_no_carrier_evidence(self):
        p=ReturnProtocol()
        with self.assertRaises(ValueError):p.apply('h','carrier','handoff',evidence())
        p=ready()
        with self.assertRaises(ValueError):p.apply('h','seller','handoff',evidence())
        with self.assertRaises(ValueError):p.apply('r','carrier','receipt',evidence(3))

    def test_decline_keep_defer_preserved(self):
        for choice in ('deny','request_evidence','defer'):
            p=ReturnProtocol();p.apply('b','buyer','request','request_refund');p.apply('s','seller','review',choice)
            with self.assertRaises(ValueError):p.apply('x','buyer','shipping','ship')
            self.assertFalse(p.snapshot()['refund_ready'])
        p=ReturnProtocol();p.apply('b','buyer','request','keep');self.assertEqual(p.status(),'buyer_keeps')

    def test_replay_and_idempotency(self):
        p=ready();p.apply('h','carrier','handoff',evidence());p.apply('r','carrier','receipt',evidence(3))
        r=ReturnProtocol.replay(p.events)
        for e in p.events:self.assertFalse(r.apply(**e))
        self.assertEqual(r.snapshot(),p.snapshot())
        with self.assertRaises(ValueError):r.apply('r','carrier','receipt',evidence(4))

    def test_custom_identity_and_timing_explicit_replay(self):
        p=ReturnProtocol(order='other',label='label2',unit='unit2',deadline=5,arrival=8)
        p.apply('b','buyer','request','request_refund');p.apply('s','seller','review','approve_return');p.apply('ship','buyer','shipping','ship')
        p.apply('h','carrier','handoff',dict(order='other',label='label2',unit='unit2',tick=4))
        p.apply('r','carrier','receipt',dict(order='other',label='label2',unit='unit2',tick=8))
        self.assertEqual(ReturnProtocol.replay(p.events,p.configuration()).snapshot(),p.snapshot())
