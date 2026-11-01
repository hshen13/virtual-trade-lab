import unittest
from dataclasses import replace
from itertools import permutations
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from refund_lab import Ledger, Provider
from demo import run


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.p = Provider(self.root / 'provider.db')
        self.p.add_payment('p', 10000)
        self.l = Ledger(self.root / 'ledger.db')

    def tearDown(self):
        self.l.close()
        self.p.close()
        self.tmp.cleanup()

    def restart(self):
        self.l.close()
        self.p.close()
        self.p = Provider(self.root / 'provider.db')
        self.l = Ledger(self.root / 'ledger.db')

    def send(self, op='a', amount=2000, **kw):
        return self.l.send(self.p, op, 'p', amount, **kw)

    def test_baseline_is_positive_control(self):
        result = run()
        self.assertEqual(result['baseline']['provider_refunds'], 2)
        self.assertEqual(result['baseline']['refunded_minor_units'], 4000)
        self.assertEqual(result['durable']['provider_refunds'], 1)
        self.assertEqual(result['durable']['refunded_minor_units'], 2000)

    def test_lost_response_restart_same_key_different_attempts(self):
        self.assertEqual(self.send(lose_response=True)['status'], 'unknown')
        self.restart()
        self.assertEqual(self.send()['status'], 'accepted')
        self.assertEqual(len(self.p.events()), 1)
        self.assertEqual(self.l.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 2)
        self.assertEqual(self.p.total('p'), 0)  # accepted != succeeded

    def test_crash_before_local_receipt(self):
        with self.assertRaises(RuntimeError):
            self.send(crash_after_response=True)
        self.restart()
        self.assertEqual(self.send()['refund_id'], 'refund-1')
        self.assertEqual(len(self.p.events()), 1)

    def test_crash_before_provider_call(self):
        self.l.intent('a', 'p', 2000)
        self.restart()
        self.assertEqual(self.send()['status'], 'accepted')
        self.assertEqual(len(self.p.events()), 1)

    def test_stale_reads_do_not_imply_failure(self):
        self.send(lose_response=True)
        for _ in range(5):
            self.assertEqual(self.l.observe(self.p, 'a', visible=False)['status'], 'unknown')
        self.assertEqual(self.l.observe(self.p, 'a')['status'], 'accepted')

    def _assert_missing_terminal_webhook_read_fallback(self, fail):
        # No test calls Ledger.reconcile or delivers a provider event/webhook.
        # settle() changes only provider state; its return value is discarded.
        unknown = self.send(lose_response=True)
        self.assertEqual(unknown['status'], 'unknown')
        self.assertIsNone(unknown['refund_id'])
        refund_id = self.p.events()[0].refund_id
        self.p.settle(refund_id, fail=fail)
        expected = 'failed' if fail else 'succeeded'
        expected_total = 0 if fail else 2000
        self.restart()

        for _ in range(3):
            self.assertEqual(self.l.observe(self.p, 'a', visible=False), unknown)
            self.assertEqual(self.p.total('p'), expected_total)
            self.assertEqual(len(self.p.events()), 1)
            self.assertEqual(self.l.db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)
        self.assertEqual(self.l.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 1)

        # The first positive authoritative read is the sole terminal evidence.
        terminal = self.l.observe(self.p, 'a', visible=True)
        self.assertEqual(terminal['status'], expected)
        self.assertEqual(terminal['version'], 2)
        self.assertEqual(terminal['refund_id'], refund_id)
        self.assertEqual(terminal['key'], unknown['key'])
        self.assertEqual(self.l.db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 1)
        self.restart()
        self.assertEqual(self.l.get('a'), terminal)

        # Once terminal, retry must not even invoke submit, let alone refund twice.
        with patch.object(self.p, 'submit', side_effect=AssertionError('terminal retry submitted')):
            for _ in range(3):
                self.assertEqual(self.l.observe(self.p, 'a', visible=False), terminal)
                self.assertEqual(self.l.observe(self.p, 'a', visible=True), terminal)
                self.assertEqual(self.send(), terminal)
                self.assertEqual(self.p.total('p'), expected_total)
                self.assertEqual(len(self.p.events()), 1)
                self.assertEqual(self.l.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 1)
                self.assertEqual(self.l.db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 1)

    def test_missing_success_webhook_recovers_by_authoritative_read_after_restart(self):
        self._assert_missing_terminal_webhook_read_fallback(fail=False)

    def test_missing_failure_webhook_recovers_by_authoritative_read_after_restart(self):
        self._assert_missing_terminal_webhook_read_fallback(fail=True)

    def test_unknown_stays_unknown_without_evidence(self):
        self.l.intent('a', 'p', 2000)
        self.assertEqual(self.l.observe(self.p, 'a')['status'], 'unknown')

    def test_terminal_webhook_before_acceptance(self):
        self.send(lose_response=True)
        accepted = self.p.events()[0]
        final = self.p.settle(accepted.refund_id)
        self.assertEqual(self.l.reconcile(final), 'applied')
        self.assertEqual(self.l.reconcile(accepted), 'late')
        self.assertEqual(self.l.reconcile(final), 'duplicate')
        self.restart()
        self.assertEqual(self.send()['status'], 'succeeded')
        self.assertEqual(self.p.total('p'), 2000)

    def test_distinct_equal_amount_operations_not_collapsed(self):
        self.send('a')
        self.send('b')
        for e in self.p.events():
            self.l.reconcile(self.p.settle(e.refund_id))
        self.assertEqual(len(self.p.events()), 2)
        self.assertEqual(self.p.total('p'), 4000)
        self.assertNotEqual(self.l.get('a')['key'], self.l.get('b')['key'])

    def test_failed_outcome_durable_and_no_automatic_new_refund(self):
        row = self.send()
        self.l.reconcile(self.p.settle(row['refund_id'], fail=True))
        self.restart()
        self.assertEqual(self.send()['status'], 'failed')
        self.assertEqual(len(self.p.events()), 1)
        self.assertEqual(self.p.total('p'), 0)

    def test_accepted_over_balance_fails_later(self):
        self.send('a', 10000)
        second = self.send('b', 10000)
        self.assertEqual(second['status'], 'accepted')
        finals = [self.p.settle(e.refund_id) for e in self.p.events()]
        for e in finals:
            self.l.reconcile(e)
        self.assertEqual([e.status for e in finals], ['succeeded', 'failed'])
        self.assertEqual(self.p.total('p'), 10000)

    def test_amount_validation(self):
        for amount in [0, -1, 1.2, True, '20']:
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.send(amount=amount)
        self.assertEqual(len(self.p.events()), 0)

    def test_changed_operation_payload_rejected(self):
        self.send()
        with self.assertRaises(ValueError):
            self.send(amount=3000)
        with self.assertRaises(ValueError):
            self.l.send(self.p, 'a', 'other-payment', 2000)
        self.assertEqual(len(self.p.events()), 1)

    def test_provider_rejects_same_key_changed_payload(self):
        self.p.submit('p', 2000, 'key')
        with self.assertRaises(ValueError):
            self.p.submit('p', 3000, 'key')

    def test_event_conflicts_rejected_without_state_change(self):
        self.send()
        accepted = self.p.events()[0]
        final = self.p.settle(accepted.refund_id)
        self.l.reconcile(final)
        bad = [replace(final, status='failed'),
               replace(final, event_id='conflict', status='failed'),
               replace(final, event_id='bad-amount', amount=999),
               replace(final, event_id='bad-id', refund_id='refund-2'),
               replace(final, event_id='unknown-key', key='unknown'),
               replace(final, event_id='bad-version', version=3)]
        for e in bad:
            with self.subTest(event=e.event_id), self.assertRaises(ValueError):
                self.l.reconcile(e)
        self.assertEqual(self.l.get('a')['status'], 'succeeded')

    def test_event_order_permutations_and_redelivery(self):
        # Both outcomes, all six delivery orders, duplicated events, restart each time.
        for fail in [False, True]:
            for i, order in enumerate(permutations(range(3))):
                op = f'{fail}-{i}'
                self.send(op, 1, lose_response=True)
                accepted = self.p.read('logical:' + op)
                final = self.p.settle(accepted.refund_id, fail=fail)
                events = [accepted, final, replace(accepted, event_id=accepted.event_id + ':redelivery')]
                for index in order:
                    self.l.reconcile(events[index])
                    self.l.reconcile(events[index])
                    self.restart()
                self.assertEqual(self.l.get(op)['status'], 'failed' if fail else 'succeeded')
        self.assertEqual(self.p.total('p'), 6)


if __name__ == '__main__':
    unittest.main()
