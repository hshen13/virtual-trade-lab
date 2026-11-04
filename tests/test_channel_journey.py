import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from virtual_trade_lab.channel_journey import load,execute,page,parse,CHOICES

ROOT=Path(__file__).resolve().parents[1]/'examples/channel-customer-journey'

def fixture(**decisions):
    return {k:({'status':'valid','parsed':{'decision':decisions[k],'reason':'rule fixture, not model'},'raw':json.dumps({'decision':decisions[k],'reason':'rule fixture, not model'})} if k in decisions else {'status':'missing','parsed':None}) for k in CHOICES}

class ChannelJourneyTests(unittest.TestCase):
    def test_all_early_exits_make_no_ledger_operations(self):
        p,_=load(ROOT)
        for d in ({},{'buyer_entry':'leave'},{'buyer_entry':'defer'}, {'buyer_entry':'open_product','buyer_product':'leave'}, {'buyer_entry':'open_product','buyer_product':'buy','seller_offer':'decline'}):
            r=execute(p,fixture(**d));self.assertEqual(r['market']['journal'],[]);self.assertEqual(r['market']['events'],[])
            self.assertEqual(r['market']['balances'],{'buyer':90,'seller':40,'provider':0})

    def test_both_consents_required_and_review_free(self):
        p,_=load(ROOT)
        for decision,balance,state in [('accept',58,'accepted'),('refund',90,'rejected'),('defer',58,'delivered')]:
            r=execute(p,fixture(buyer_entry='open_product',buyer_product='buy',seller_offer='accept_dispatch',buyer_review=decision))
            self.assertEqual(r['market']['balances']['buyer'],balance)
            self.assertEqual(r['market']['orders'][0]['state'],state)
            self.assertEqual(sum(r['market']['balances'].values()),130)
            self.assertEqual(len(r['market']['journal']),2 if decision=='defer' else 3)
        with self.assertRaises(ValueError):execute(p,fixture(buyer_entry='leave',seller_offer='accept_dispatch'))

    def test_actual_report_rebuild_and_verbatim(self):
        p,rows=load(ROOT);r=execute(p,rows)
        self.assertEqual(r,json.loads((ROOT/'report.json').read_text()))
        self.assertEqual(page(ROOT,r),(ROOT/'overview.html').read_text())
        for key,row in rows.items():
            if row['status']!='missing':self.assertEqual(row['raw'],(ROOT/'responses'/f'{key}.txt').read_text())
        html=page(ROOT,r);css=html.split('<style>',1)[1].split('</style>',1)[0]
        web=ROOT.parents[1]/'virtual_trade_lab/web'
        self.assertEqual((web/'journey.html').read_text(),html.replace('<style>'+css+'</style>','<link rel="stylesheet" href="/journey.css">'))
        self.assertEqual((web/'journey.css').read_text(),css)
        self.assertIsNone(r['video_views_measured']);self.assertEqual(r['real_payments'],0)

    def test_tampered_input_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'study';shutil.copytree(ROOT,root)
            (root/'advertisement.txt').write_text('forged')
            with self.assertRaises(ValueError):load(root)

    def test_missing_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'study';shutil.copytree(ROOT,root)
            (root/'manifest.json').unlink()
            with self.assertRaises(ValueError):load(root)

    def test_changed_output_seal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'study';shutil.copytree(ROOT,root)
            (root/'responses/buyer_product.txt').write_text('{"decision":"buy","reason":"forged"}')
            with self.assertRaises(ValueError):load(root)

    def test_invalid_does_not_count_as_consent(self):
        with self.assertRaises(ValueError):parse('{"decision":"leave","decision":"open_product","reason":"x"}','buyer_entry')
        with self.assertRaises(ValueError):parse('{"decision":"buy","reason":"x"}','buyer_entry')
        p,_=load(ROOT);r=fixture();r['buyer_entry']={'status':'invalid','parsed':None,'raw':'nonsense'}
        self.assertEqual(execute(p,r)['market']['journal'],[])
