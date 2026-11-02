from copy import deepcopy
import unittest
from virtual_trade_lab.calibration_protocol import template, validate


class CalibrationProtocolTests(unittest.TestCase):
    def test_template_reports_design_only_not_human_validation(self):
        result = validate(template())
        self.assertEqual(result['calibration_status'], 'not_evaluated')
        self.assertFalse(result['human_validation_performed'])
        self.assertEqual(result['gates_satisfied'], 0)
        self.assertEqual(result['gates_required'], 9)

    def test_price_schedule_preserves_all_four_values(self):
        phase = template()['study_designs']['phase2']
        for discount, transaction, effective in zip(phase['discount_percent'], phase['transaction_price_zmw'], phase['effective_price_zmw']):
            self.assertEqual(transaction, phase['list_price_zmw']*(100-discount)/100)
            self.assertEqual(effective, transaction-phase['cash_gift_zmw'])

    def test_effective_price_cannot_be_full_or_free_price(self):
        for field in ['effective_price_is_full_price', 'zero_effective_price_is_free_choice']:
            s=template();s['price_contract'][field]=True
            with self.assertRaises(ValueError):validate(s)

    def test_gift_outside_option_and_outcome_cannot_be_erased(self):
        for section,field in [('price_contract','outside_option'),('outcome_contract','stated_wtp'),('outcome_contract','primary')]:
            s=template();s[section][field]='stated_wtp_is_actual_payment'
            with self.assertRaises(ValueError):validate(s)

    def test_real_synthetic_and_phases_cannot_be_pooled(self):
        for field in ['merge_real_and_synthetic','phase1_phase2_pooling','fresh_blind_holdout_available']:
            s=template();s['partition_contract'][field]=True
            with self.assertRaises(ValueError):validate(s)

    def test_split_is_household_not_event(self):
        s=template();s['partition_contract']['split_unit']='event'
        with self.assertRaises(ValueError):validate(s)

    def test_calibration_claim_never_follows_design_pass(self):
        for status in ['calibrated','aligned','validated',True,None]:
            s=template();s['calibration_status']=status
            with self.assertRaises(ValueError):validate(s)

    def test_nulls_not_fake_observations_or_zero_errors(self):
        for value in [[],0,{'error':0},'observed']:
            s=template();s['unavailable_evidence']['fit_results']=value
            with self.assertRaises(ValueError):validate(s)

    def test_raw_rows_unknown_fields_and_missing_gates_rejected(self):
        s=template();s['participant_rows']=[]
        with self.assertRaises(ValueError):validate(s)
        s=template();s['gates'].pop(next(iter(s['gates'])))
        with self.assertRaises(ValueError):validate(s)

    def test_self_certification_cannot_fill_gates(self):
        s=template()
        for gate in s['gates'].values():gate.update(status='passed',evidence_ref='self-declared')
        with self.assertRaises(ValueError):validate(s)

    def test_planned_gates_remain_unfulfilled(self):
        s=template()
        for gate in s['gates'].values():gate['status']='planned'
        self.assertEqual(validate(s)['gates_satisfied'],0)

    def test_axes_require_fixed_versions_experience_and_price(self):
        s=template();s['axes']['virtual_user']['hold_fixed'].remove('real_product_version')
        with self.assertRaises(ValueError):validate(s)
