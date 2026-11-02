from dataclasses import replace
import unittest
from virtual_trade_lab.realism import Offer, Person, people, simulate, compare, utility, campaign


class RealismTests(unittest.TestCase):
    def test_null_and_label_swap(self):
        a, b, cohort = Offer(), replace(Offer(), price=25), people(5)
        self.assertTrue(all(v == 0 for v in compare(a, a, cohort, 5)['delta'].values()))
        forward, backward = compare(a, b, cohort, 5), compare(b, a, cohort, 5)
        self.assertEqual(forward['baseline'], backward['candidate'])
        self.assertEqual(forward['delta'], {k: -v for k, v in backward['delta'].items()})

    def test_order_invariance(self):
        self.assertEqual(simulate(Offer(), people(5), 5), simulate(Offer(), list(reversed(people(5))), 5))

    def test_no_buy_and_no_view_controls(self):
        self.assertEqual(simulate(replace(Offer(), price=1000), people(5), 5)['purchases'], 0)
        self.assertEqual(simulate(replace(Offer(), relevance=0), people(5), 5)['views'], 0)
        self.assertEqual(simulate(Offer(), [replace(p, outside=100) for p in people(5)], 5)['purchases'], 0)

    def test_price_monotonic_utility(self):
        for p in people(8):
            self.assertLess(utility(p, replace(Offer(), price=30)), utility(p, Offer()))

    def test_fatigue_does_not_improve_attention(self):
        p = Person(1, 'test', 100, 1, 1, 0, 1)
        low = simulate(Offer(), [p], 5, fatigue=0)
        high = simulate(Offer(), [p], 5, fatigue=1)
        self.assertLessEqual(high['rows'][1]['attention'], low['rows'][1]['attention'])

    def test_refunds_costs_and_repeat_exposure(self):
        report = simulate(replace(Offer(), quality=0), people(5), 5)
        self.assertLessEqual(report['refunds'], report['paid'])
        self.assertAlmostEqual(report['net'], report['paid']-report['refunds']-report['costs'])
        past = set()
        for row in report['rows']:
            if row['repeat']:
                self.assertIn(row['person'], past)
            if row['bought']:
                self.assertTrue(row['viewed']); past.add(row['person'])
        empty = simulate(Offer(), people(5), 5, demand=0)
        self.assertEqual(empty['paid'], 0)
        self.assertGreater(empty['costs'], 0)

    def test_bad_experience_replaces_promise_for_later_decisions(self):
        person = Person(1, 'test', 100, 2, 1, 0, 1)
        offer = replace(Offer(), quality=0, price=1, repetition=0, clarity=1, relevance=1)
        rows = simulate(offer, [person], 5)['rows']
        self.assertTrue(rows[0]['bought'])
        self.assertEqual(rows[0]['refund'], 1)
        self.assertEqual(rows[0]['expected_quality'], offer.promised_quality)
        self.assertEqual([r['expected_quality'] for r in rows[1:]], [0, 0])
        self.assertLess(rows[1]['utility'], rows[0]['utility'])

    def test_frozen_complete_design_not_calibrated(self):
        a, b = campaign(), campaign()
        self.assertEqual(a, b)
        self.assertEqual(len(a['cells']), 24)
        self.assertFalse(a['empirically_calibrated'])
        self.assertFalse(set(a['config']['development_seeds']) & set(a['config']['holdout_seeds']))
        self.assertEqual(a['robustness'], 'not_demonstrated')
