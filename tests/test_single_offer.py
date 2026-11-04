from copy import deepcopy
import json
from pathlib import Path
import unittest
from virtual_trade_lab.single_offer import validate,choice_context,record
from virtual_trade_lab.realism import people,Offer,simulate,campaign
ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/'examples/synthetic-single-offer/offer.json'

def spec():return json.loads(SPEC.read_text())

class SingleOfferTests(unittest.TestCase):
    def test_old_default_budget_mismatch_mechanical_not_behavior(self):
        cohort=people(42)
        self.assertTrue(all(p.budget<=45 for p in cohort))
        self.assertEqual(simulate(Offer(price=50),cohort,42)['purchases'],0)
        # This diagnoses the old arbitrary-unit model, not any observed sample.

    def test_original_amounts_and_gift_not_discounted_payment(self):
        s=spec();r=record(s,'buy')
        self.assertEqual(r,json.loads((ROOT/'examples/synthetic-single-offer/buy.json').read_text()))
        self.assertEqual(r['recorded_simulated_payment'],'75.00')
        self.assertEqual(r['price_minus_gift'],'55.00');self.assertEqual(r['total_cash_after'],'5.00')
        d=record(s,'decline');self.assertEqual(d['total_cash_after'],'80.00');self.assertEqual(d['gift_retained_on_decline'],'20.00')
        self.assertEqual(d,json.loads((ROOT/'examples/synthetic-single-offer/decline.json').read_text()))

    def test_zero_effective_price_is_not_free(self):
        s=spec();s.update(transaction_price='20.00',own_spendable_before_gift='0.00')
        a,d=record(s,'buy'),record(s,'decline')
        self.assertEqual(a['price_minus_gift'],'0.00');self.assertEqual(a['recorded_simulated_payment'],'20.00')
        self.assertEqual(a['total_cash_after'],'0.00');self.assertEqual(d['total_cash_after'],'20.00')

    def test_gift_exceeds_price_does_not_disappear(self):
        s=spec();s.update(transaction_price='15.00',own_spendable_before_gift='0.00')
        r=record(s,'buy');self.assertEqual(r['total_cash_after'],'5.00');self.assertEqual(r['price_minus_gift'],'-5.00')
        self.assertEqual(r['own_funds_needed_if_buy'],'0.00')

    def test_unknown_budget_not_imputed_zero_or_false_decline(self):
        s=spec();s.update(own_spendable_before_gift=None,budget_source='unknown')
        r=record(s,'buy');self.assertEqual(r['status'],'pending_budget_evidence');self.assertIsNone(r['budget_affordable']);self.assertIsNone(r['total_cash_after'])
        self.assertEqual(r['choice'],'buy');self.assertEqual(r['recorded_simulated_payment'],'0.00')
        self.assertEqual(record(s,'decline')['status'],'declined')
        s['transaction_price']='20.00'
        r=record(s,'buy');self.assertTrue(r['budget_affordable']);self.assertEqual(r['recorded_simulated_payment'],'20.00')
        self.assertIsNone(r['total_cash_after'])

    def test_declared_buy_with_explicit_shortfall_not_silently_refusal(self):
        s=spec();s['own_spendable_before_gift']='1.00';r=record(s,'buy')
        self.assertEqual(r['status'],'infeasible_declared_buy');self.assertEqual(r['choice'],'buy');self.assertEqual(r['recorded_simulated_payment'],'0.00')
        self.assertEqual(record(s,'defer')['status'],'deferred')

    def test_replay_and_conflicting_offer(self):
        s=spec();r=record(s,'buy');self.assertEqual(r,record(s,'buy',previous=json.loads(json.dumps(r))))
        with self.assertRaises(ValueError):record(s,'decline',previous=r)
        s['transaction_price']='74.00'
        with self.assertRaises(ValueError):record(s,'buy',previous=r)

    def test_replay_rejects_boolean_type_corruption_and_accepts_equal_money(self):
        s=spec();r=record(s,'buy');bad=deepcopy(r);bad['real_payment']=0
        with self.assertRaises(ValueError):record(s,'buy',previous=bad)
        bad=deepcopy(r);bad['budget_affordable']=1
        with self.assertRaises(ValueError):record(s,'buy',previous=bad)
        s['transaction_price']='75'
        self.assertEqual(record(s,'buy',previous=r),r)

    def test_no_observed_labels_or_scaling_or_mixed_currency(self):
        for key,value in [('domain','observed'),('currency','USD'),('unit','minor'),('price_basis','net_effective'),('budget_source','fit_from_observed_choices')]:
            with self.subTest(key=key):
                s=spec();s[key]=value
                with self.assertRaises(ValueError):validate(s)
        for key in ('observed_purchase_rate','actual_purchase','calibrated','exchange_rate'):
            s=spec();s[key]=0
            with self.assertRaises(ValueError):choice_context(s)

    def test_numeric_and_experience_rejection(self):
        for value in (75,75.0,'NaN','Infinity','-1','0.001'):
            s=spec();s['transaction_price']=value
            with self.assertRaises(ValueError):validate(s)
        s=spec();s['experience']={'status':'real_prior_use','days':14}
        with self.assertRaises(ValueError):validate(s)
        s=spec();s['decline_retains_gift']=False
        with self.assertRaises(ValueError):validate(s)

    def test_prompt_allowlist_and_no_utility_or_real_validation(self):
        c=choice_context(spec());self.assertEqual(c['full_transaction_price'],'75.00');self.assertEqual(c['currency'],'ZMW')
        self.assertFalse(c['price_minus_gift_is_payment']);self.assertEqual(c['choices'],['buy','decline','defer'])
        r=record(spec(),'buy');self.assertFalse(r['observed_outcomes_used']);self.assertFalse(r['realism_utility_used']);self.assertFalse(r['real_payment']);self.assertEqual(r['calibration_status'],'not_evaluated')
