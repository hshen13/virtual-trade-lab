"""Synthetic fixtures ONLY: patched clocks do not establish observed market facts."""
from copy import deepcopy
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from virtual_trade_lab.core import TradeError
from virtual_trade_lab.experiments import EVENT_FIELDS, ExperimentRegistry, load_events


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'registry.sqlite3'
        self.clock = patch('virtual_trade_lab.experiments.now_utc', return_value=datetime(2020, 1, 11, tzinfo=timezone.utc))
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.registry = ExperimentRegistry(self.path)
        self.counter = 0
        self.plan = dict(currency='USD', calibration_end='2020-01-01T00:00:00Z',
                         exposure_end='2020-01-05T00:00:00Z', observation_end='2020-01-10T00:00:00Z',
                         holdout_subjects=['h1'], min_holdout=1)
        self.registry.create_campaign('c', **self.plan)

    def event(self, kind='exposure', subject='a', domain='simulated', partition='calibration', time=None, **kwargs):
        self.counter += 1
        monetary = kind in {'paid', 'refunded', 'cost'}
        result = dict(event_id=f'e{self.counter}', campaign_id='c', subject_id=subject,
                      domain=domain, partition=partition, event_type=kind,
                      occurred_at=time or ('2020-01-03T00:00:00Z' if partition == 'holdout' else '2019-12-31T00:00:00Z'),
                      amount_minor=100 if monetary else 0, currency='USD', source_id='synthetic-test-fixture',
                      evidence_ref=f'synthetic-row-{self.counter}', transaction_id=f'tx-{subject}' if monetary else '')
        result.update(kwargs)
        return result

    def complete(self, subject='a', domain='simulated', partition='calibration', accepted=True):
        stages = ['exposure', 'interest', 'quote', 'order', 'paid', 'fulfilled', 'accepted'] if accepted else ['exposure']
        day = '2020-01-03' if partition == 'holdout' else '2019-12-31'
        rows = [self.event(stage, subject, domain, partition, f'{day}T0{i}:00:00Z') for i, stage in enumerate(stages)]
        close = '2020-01-10T00:00:00Z' if partition == 'holdout' else '2020-01-01T00:00:00Z'
        rows.append(self.event('followup_closed', subject, domain, partition, close))
        return rows

    def freeze(self, probability=0.5):
        prediction = self.registry.predict('c', method='manual', probability=probability, rationale='Synthetic test baseline only')
        self.now.return_value = datetime(2020, 1, 2, tzinfo=timezone.utc)
        result = self.registry.freeze('c', prediction['version'])
        self.now.return_value = datetime(2020, 1, 11, tzinfo=timezone.utc)
        return result

    def group(self, domain='simulated', partition='calibration'):
        return self.registry.report('c')['groups'][domain][partition]

    def test_no_data_is_not_evaluated_and_all_gates_unresolved(self):
        report = self.registry.report('c')
        self.assertEqual(report['evaluation']['status'], 'not_evaluated')
        self.assertEqual(report['overall_goal'], 'not_completed')
        self.assertTrue(all(v in {'unverified', 'unresolved'} for v in report['completion_gates'].values()))
        self.assertIn('not independently verified', report['authenticity'])
        self.assertIsNone(self.group()['acceptance_rate'])
        self.assertIsNone(self.group()['wilson_95'])
        self.freeze()
        self.assertEqual(self.registry.report('c')['evaluation']['status'], 'not_evaluated')

    def test_complete_observed_claim_without_threshold_is_unassessed(self):
        self.freeze()
        before = self.registry.report('c')['observation_snapshot']['version']
        rows = self.complete('h1', 'observed', 'holdout')
        self.registry.import_events(rows)
        report = self.registry.report('c')
        self.assertNotEqual(before, report['observation_snapshot']['version'])
        self.registry.import_events(rows)
        self.assertEqual(report['observation_snapshot'], self.registry.report('c')['observation_snapshot'])
        self.assertEqual(report['evaluation']['absolute_error'], 0.5)
        self.assertEqual(report['evaluation']['brier_score'], 0.25)
        self.assertEqual(report['evaluation']['status'], 'unassessed')
        self.assertEqual(report['evaluation']['denominator'], 1)
        self.assertEqual(report['overall_goal'], 'not_completed')
        self.assertEqual(report['groups']['simulated']['holdout']['exposed_subjects'], 0)

    def test_no_conversion_with_closed_followup_counts_in_denominator(self):
        self.freeze()
        self.registry.import_events(self.complete('h1', 'observed', 'holdout', accepted=False))
        holdout = self.group('observed', 'holdout')
        self.assertEqual(holdout['exposed_subjects'], 1)
        self.assertEqual(holdout['acceptance_rate'], 0)
        self.assertEqual(holdout['pending_exposed_subjects'], 0)
        self.assertEqual(self.registry.report('c')['evaluation']['status'], 'unassessed')

    def test_plan_immutable_and_identical_replay_allowed(self):
        self.registry.create_campaign('c', **self.plan)
        with self.assertRaises(TradeError):
            self.registry.create_campaign('c', **{**self.plan, 'min_holdout': 2})
        for change in [{'currency':'usd'}, {'min_holdout':True}, {'tolerance':0.1},
                       {'tolerance':float('nan'), 'plan_rationale':'test'}, {'holdout_subjects':['h1','h1']},
                       {'holdout_subjects':['']}, {'calibration_end':'2020-01-12T00:00:00Z'}]:
            with self.subTest(change=change), self.assertRaises(TradeError):
                self.registry.create_campaign('new', **{**self.plan, **change})

    def test_invalid_missing_false_fields_and_unknown_values_atomic(self):
        base = self.event()
        variants = [{k:v for k,v in base.items() if k != 'source_id'}, {**base,'observed':True},
                    {**base,'subject_id':''}, {**base,'campaign_id':'unknown'}, {**base,'source_id':False},
                    {**base,'domain':True}, {**base,'domain':'real'}, {**base,'partition':'train'},
                    {**base,'event_type':'profit'}, {**base,'amount_minor':True}, {**base,'amount_minor':-1},
                    {**base,'currency':'EUR'}, {**base,'evidence_ref':' '}, {**base,'evidence_ref':'ref '}, {**base,'occurred_at':'2020-01-01'},
                    {**base,'transaction_id':'forbidden'}, {**base,'amount_minor':1}]
        for row in variants:
            with self.subTest(row=row), self.assertRaises(TradeError):
                self.registry.import_events([row])
        for rows in [[], None, {}, [None]]:
            with self.assertRaises(TradeError):
                self.registry.import_events(rows)
        self.assertEqual(self.group()['subject_count'], 0)

    def test_idempotent_import_and_conflicting_batch_rollback(self):
        row = self.event()
        self.assertEqual(self.registry.import_events([row])['inserted'], 1)
        self.assertEqual(self.registry.import_events([row])['exact_duplicates_ignored'], 1)
        fresh = self.event(subject='fresh')
        conflict = {**row, 'subject_id':'changed'}
        with self.assertRaises(TradeError):
            self.registry.import_events([fresh, conflict])
        self.assertEqual(self.group()['exposed_subjects'], 1)
        with self.assertRaises(TradeError):
            self.registry.import_events([{**row, 'event_id':'different'}])

    def test_domain_and_partition_contamination_blocked(self):
        self.registry.import_events([self.event()])
        for change in [{'domain':'observed'}, {'partition':'holdout'}]:
            with self.assertRaises(TradeError):
                self.registry.import_events([self.event(**change)])
        with self.assertRaises(TradeError):
            self.registry.import_events([self.event(subject='h1')])

    def test_holdout_requires_freeze_and_planned_observed_subject(self):
        with self.assertRaises(TradeError):
            self.registry.import_events([self.event(partition='holdout')])
        self.freeze()
        with self.assertRaises(TradeError):
            self.registry.import_events([self.event('exposure','unplanned','observed','holdout')])

    def test_retrospective_future_and_outside_enrollment_observed_rejected(self):
        self.freeze()
        for time in ['2020-01-01T00:00:00Z','2020-01-02T00:00:00Z', '2020-01-06T00:00:00Z', '2020-01-12T00:00:00Z']:
            with self.subTest(time=time), self.assertRaises(TradeError):
                self.registry.import_events([self.event('exposure','h1','observed','holdout',time)])
        with self.assertRaises(TradeError):
            self.registry.import_events([self.event(domain='observed',time='2021-01-01T00:00:00Z')])

    def test_missing_followup_and_early_close_remain_pending(self):
        self.freeze()
        rows = self.complete('h1','observed','holdout')[:-1]
        self.registry.import_events(rows)
        self.assertEqual(self.registry.report('c')['evaluation']['status'], 'insufficient_data')
        self.registry.import_events([self.event('followup_closed','h1','observed','holdout','2020-01-09T00:00:00Z')])
        self.assertEqual(self.group('observed','holdout')['pending_exposed_subjects'], 1)

    def test_observation_window_must_end(self):
        self.freeze()
        self.registry.import_events(self.complete('h1','observed','holdout'))
        self.now.return_value = datetime(2020,1,9,tzinfo=timezone.utc)
        self.assertEqual(self.registry.report('c')['evaluation']['status'], 'insufficient_data')

    def test_missing_planned_subject_and_minimum_cohort(self):
        self.registry.create_campaign('two', **{**self.plan,'holdout_subjects':['h1','h2'],'min_holdout':2})
        p = self.registry.predict('two',method='manual',probability=.5,rationale='Synthetic')
        self.now.return_value = datetime(2020,1,2,tzinfo=timezone.utc)
        self.registry.freeze('two',p['version'])
        self.now.return_value = datetime(2020,1,11,tzinfo=timezone.utc)
        rows=self.complete('h1','observed','holdout')
        for row in rows: row['campaign_id']='two'
        self.registry.import_events(rows)
        self.assertEqual(self.registry.report('two')['evaluation']['status'],'insufficient_data')

    def test_missing_preceding_stages_and_out_of_order_funnel_flagged(self):
        self.registry.import_events([self.event('exposure'), self.event('accepted')])
        self.assertTrue(self.group()['quality_issues'])
        self.registry.import_events([self.event('exposure','b',time='2019-12-31T02:00:00Z'),
                                     self.event('interest','b',time='2019-12-31T01:00:00Z')])
        self.assertTrue(any('out of order' in x for x in self.group()['quality_issues']))
        with self.assertRaises(TradeError):
            self.registry.predict('c',method='simulation_calibration',rationale='Synthetic')

    def test_empirical_prediction_snapshot_change_before_freeze(self):
        self.registry.import_events(self.complete())
        pred=self.registry.predict('c',method='simulation_calibration',rationale='Synthetic')
        self.assertEqual(pred['probability'],1)
        self.assertEqual(pred['calibration_subjects'],1)
        self.registry.import_events([self.event('cost',time='2020-01-01T01:00:00Z')])
        self.now.return_value = datetime(2020,1,2,tzinfo=timezone.utc)
        with self.assertRaises(TradeError): self.registry.freeze('c',pred['version'])
        updated=self.registry.predict('c',method='simulation_calibration',rationale='Updated synthetic snapshot')
        self.assertEqual(updated['version'],2)
        self.registry.freeze('c',2)
        self.assertEqual(self.registry.freeze('c',2)['locked_version'],2)
        with self.assertRaises(TradeError): self.registry.freeze('c',1)
        with self.assertRaises(TradeError): self.registry.predict('c',method='manual',probability=.2,rationale='No')
        with self.assertRaises(TradeError): self.registry.import_events([self.event(subject='new')])

    def test_prediction_parameter_validation_and_freeze_window(self):
        for kwargs in [{'method':'manual','probability':None},{'method':'manual','probability':True},
                       {'method':'manual','probability':1.1},{'method':'observed_calibration'},
                       {'method':'simulation_calibration','probability':.1},{'method':'unknown'}]:
            with self.assertRaises(TradeError): self.registry.predict('c',rationale='Synthetic',**kwargs)
        p=self.registry.predict('c',method='manual',probability=.2,rationale='Synthetic')
        for day in [1,5,11]:
            self.now.return_value=datetime(2020,1,day,tzinfo=timezone.utc)
            with self.assertRaises(TradeError): self.registry.freeze('c',p['version'])
        for version in [True,0,99]:
            with self.assertRaises(TradeError): self.registry.freeze('c',version)

    def test_financial_reference_reconciliation_and_batch_rollback(self):
        payment=self.event('paid',time='2019-12-31T03:00:00Z',amount_minor=100)
        self.registry.import_events([payment])
        for changes in [{'transaction_id':'unknown'}, {'amount_minor':101}, {'time':'2019-12-31T02:00:00Z'}]:
            time=changes.pop('time','2019-12-31T04:00:00Z')
            with self.assertRaises(TradeError): self.registry.import_events([self.event('refunded',time=time,**changes)])
        with self.assertRaises(TradeError): self.registry.import_events([self.event('paid')])
        self.registry.import_events([self.event('refunded',amount_minor=60,time='2019-12-31T04:00:00Z')])
        with self.assertRaises(TradeError): self.registry.import_events([self.event('refunded',amount_minor=41,time='2019-12-31T05:00:00Z')])
        money=self.group()['declared_money_minor']
        self.assertEqual(money['refunds'],60)
        self.assertEqual(money['net_receipts_after_refunds'],40)

    def test_late_refunds_and_costs_included_without_late_acceptance(self):
        self.freeze()
        self.registry.import_events(self.complete('h1','observed','holdout'))
        self.registry.import_events([self.event('refunded','h1','observed','holdout','2020-01-11T00:00:00Z',amount_minor=40),
                                     self.event('cost','h1','observed','holdout','2020-01-11T00:30:00+01:00',amount_minor=10)])
        group=self.group('observed','holdout')
        self.assertEqual(group['acceptance_rate'],1)
        self.assertEqual(group['declared_money_minor']['net_after_declared_costs'],50)
        self.assertIn('unknown',group['cost_coverage'])
        self.assertEqual(group['refunded_subjects'], 1)
        self.assertEqual(group['money_as_of'], '2020-01-11T00:00:00+00:00')

    def test_terminal_conflict_and_cross_subject_refund_rejected(self):
        self.registry.import_events([self.event('accepted')])
        with self.assertRaises(TradeError): self.registry.import_events([self.event('cancelled')])
        self.registry.import_events([self.event('paid','b')])
        with self.assertRaises(TradeError): self.registry.import_events([self.event('refunded','c',transaction_id='tx-b')])

    def test_observed_and_simulated_never_pooled_and_restart_equal(self):
        self.registry.import_events(self.complete('sim','simulated'))
        self.registry.import_events(self.complete('obs','observed',accepted=False))
        report=self.registry.report('c')
        self.assertEqual(report['groups']['simulated']['calibration']['acceptance_rate'],1)
        self.assertEqual(report['groups']['observed']['calibration']['acceptance_rate'],0)
        self.assertEqual(ExperimentRegistry(self.path).report('c'),report)

    def test_csv_json_loading_and_header_validation(self):
        row=self.event()
        js=Path(self.tmp.name)/'events.json'
        js.write_text(json.dumps([row]),encoding='utf-8')
        self.assertEqual(load_events(js),[row])
        csvpath=Path(self.tmp.name)/'events.csv'
        with csvpath.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=sorted(EVENT_FIELDS));writer.writeheader();writer.writerow(row)
        self.assertEqual(load_events(csvpath),[row])
        for content in ['event_id,event_id\na,b\n','event_id\na\n','']:
            csvpath.write_text(content)
            with self.assertRaises(TradeError):load_events(csvpath)
        with csvpath.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=sorted(EVENT_FIELDS));writer.writeheader();writer.writerow({**row,'amount_minor':'1.0'})
        with self.assertRaises(TradeError):load_events(csvpath)
        other=Path(self.tmp.name)/'events.txt';other.write_text('[]')
        with self.assertRaises(TradeError):load_events(other)

    def test_payment_transaction_cannot_inflate_receipts_across_subjects(self):
        self.registry.import_events([self.event('paid','a',transaction_id='same-payment')])
        with self.assertRaises(TradeError):
            self.registry.import_events([self.event('paid','b',transaction_id='same-payment')])
        self.assertEqual(self.group()['declared_money_minor']['receipts'],100)

    def test_duplicate_cost_identity_cannot_inflate_costs(self):
        self.registry.import_events([self.event('cost','a',transaction_id='source:cost-1')])
        with self.assertRaises(TradeError):
            self.registry.import_events([self.event('cost','b',transaction_id='source:cost-1')])
        self.assertEqual(self.group()['declared_money_minor']['costs'],100)

    def test_duplicate_json_fields_rejected(self):
        path=Path(self.tmp.name)/'duplicate.json'
        path.write_text('[{"event_id":"one","event_id":"two"}]')
        with self.assertRaises(TradeError):load_events(path)

    def test_changed_stored_event_body_fails_closed(self):
        row=self.event()
        self.registry.import_events([row])
        row['subject_id']='corrupted'
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE events SET body=? WHERE id=?',(json.dumps(row),row['event_id']))
        with self.assertRaises(TradeError): self.registry.report('c')

    def test_threshold_interval_outcomes_still_do_not_complete_goal(self):
        scenarios=[('within',50,25,.5,.2,'within_declared_tolerance'),
                   ('outside',50,0,.9,.1,'outside_declared_tolerance'),
                   ('uncertain',1,0,.5,.1,'inconclusive')]
        for campaign,n,successes,p,tol,expected in scenarios:
            with self.subTest(campaign=campaign):
                subjects=[f'{campaign}-{i}' for i in range(n)]
                self.registry.create_campaign(campaign,**{**self.plan,'holdout_subjects':subjects,
                    'min_holdout':n,'tolerance':tol,'plan_rationale':'Synthetic test threshold; no empirical justification claimed'})
                pred=self.registry.predict(campaign,method='manual',probability=p,rationale='Synthetic fixed baseline')
                self.now.return_value=datetime(2020,1,2,tzinfo=timezone.utc)
                self.registry.freeze(campaign,pred['version'])
                self.now.return_value=datetime(2020,1,11,tzinfo=timezone.utc)
                rows=[]
                for index,subject in enumerate(subjects):
                    rows.extend(self.complete(subject,'observed','holdout',accepted=index<successes))
                for row in rows: row['campaign_id']=campaign
                self.registry.import_events(rows)
                report=self.registry.report(campaign)
                self.assertEqual(report['evaluation']['status'],expected)
                self.assertEqual(report['overall_goal'],'not_completed')
                self.assertTrue(all(v in {'unverified','unresolved'} for v in report['completion_gates'].values()))

    def test_cli_reports_errors_without_traceback(self):
        for args in [['report','missing'], ['import',str(Path(self.tmp.name)/'missing.json')],
                     ['predict','c','--method','manual','--probability','nan','--rationale','Synthetic']]:
            proc=subprocess.run([sys.executable,'-m','virtual_trade_lab.experiments','--db',str(self.path),*args],capture_output=True,text=True)
            self.assertEqual(proc.returncode,2)
            self.assertNotIn('Traceback',proc.stderr)
        proc=subprocess.run([sys.executable,'-m','virtual_trade_lab.experiments','--db',str(self.path),'report','c'],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0)
        self.assertEqual(json.loads(proc.stdout)['overall_goal'],'not_completed')


if __name__=='__main__': unittest.main()
