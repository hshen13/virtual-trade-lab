import hashlib
import http.client
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from virtual_trade_lab.replay_data import build
from virtual_trade_lab.server import make_server

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'examples/defect-refund-model-study'
WEB=ROOT/'virtual_trade_lab/web'


class ReplayDataTests(unittest.TestCase):
    def test_exact_projection_and_six_verbatim_model_outputs(self):
        data=build(STUDY)
        self.assertEqual(data,json.loads((WEB/'replay-data.json').read_text()))
        outputs=[x for step in data['steps'] for x in step['model_outputs']]
        self.assertEqual(len(outputs),6)
        self.assertEqual(len({x['stage'] for x in outputs}),6)
        for x in outputs:self.assertEqual(x['raw'],(STUDY/'responses'/f'{x["stage"]}.txt').read_text())
        self.assertEqual(data['summary']['real_payments'],0)
        self.assertNotIn('csrf_token',json.dumps(data))

    def test_timeline_conservation_and_no_early_refund(self):
        steps=build(STUDY)['steps']
        self.assertEqual([s['balances']['escrow'] for s in steps],[0,0,32,32,32,0])
        self.assertEqual([s['balances']['buyer'] for s in steps],[90,90,58,58,58,90])
        self.assertEqual([s['balances']['cost'] for s in steps],[0,0,0,4,4,4])
        for s in steps:self.assertEqual(sum(s['balances'].values()),130)
        self.assertEqual(steps[-1]['journal'][-1]['reason'],'reject_refund')
        self.assertEqual(steps[1]['inspection']['unit_id'],'unit-A')
        self.assertEqual(steps[4]['inspection']['unit_id'],'unit-B')
        self.assertFalse(steps[4]['money_changed'])

    def test_builder_readonly_and_not_a_false_refund_renderer(self):
        paths=list(STUDY.rglob('*'));before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
        build(STUDY)
        self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()})
        with self.assertRaises(ValueError):build(ROOT/'examples/precommit-model-study')

    def test_tampered_report_or_response_cannot_generate_page_data(self):
        with tempfile.TemporaryDirectory() as d:
            copy=Path(d)/'study';shutil.copytree(STUDY,copy)
            path=copy/'report.json';data=json.loads(path.read_text());data['state']['balances']['buyer']=999;path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):build(copy)
        with tempfile.TemporaryDirectory() as d:
            copy=Path(d)/'study';shutil.copytree(STUDY,copy)
            (copy/'responses/buyer_review.txt').write_text('{"decision":"accept","reason":"tamper"}')
            with self.assertRaises(ValueError):build(copy)

    def test_unsealed_evidence_cannot_be_presented_as_sealed(self):
        with tempfile.TemporaryDirectory() as d:
            copy=Path(d)/'study';shutil.copytree(STUDY,copy)
            (copy/'manifest.json').unlink()
            with self.assertRaisesRegex(ValueError,'sealed evidence manifest required'):build(copy)

    def test_unsealed_report_hash_cannot_override_verified_protocol(self):
        with tempfile.TemporaryDirectory() as d:
            copy=Path(d)/'study';shutil.copytree(STUDY,copy)
            path=copy/'report.json';data=json.loads(path.read_text());data['protocol_sha256']='forged';path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'report protocol hash differs'):build(copy)

    def test_assets_have_no_external_network_or_mutation_calls(self):
        js=(WEB/'replay.js').read_text();html=(WEB/'replay.html').read_text()
        self.assertNotIn('innerHTML',js)
        self.assertNotIn('/api/command',js)
        self.assertNotIn('/api/reset',js)
        self.assertNotIn('https://',js+html+(WEB/'replay.css').read_text())
        self.assertIn('纯模拟 · 无真实支付',html)


class ReplayHTTPTests(unittest.TestCase):
    def test_real_http_routes_are_readonly_and_host_restricted(self):
        with tempfile.TemporaryDirectory() as d:
            server=make_server(Path(d)/'ui.sqlite3',0)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            def get(path,host=None,method='GET'):
                c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                h={'Host':host or f'127.0.0.1:{server.server_port}'}
                if method=='POST':h.update({'Content-Type':'application/json','X-VTL-Token':server.csrf_token})
                c.request(method,path,body='{}' if method=='POST' else None,headers=h)
                r=c.getresponse();result=r.status,r.read(),dict(r.getheaders());c.close();return result
            try:
                before=server.store.state()
                for path in ('/replay','/replay.js','/replay.css','/replay-data.json'):
                    status,body,headers=get(path)
                    self.assertEqual(status,200);self.assertTrue(body)
                    self.assertIn("connect-src 'self'",headers['Content-Security-Policy'])
                self.assertEqual(get('/replay','evil.example')[0],403)
                self.assertEqual(get('/replay-data.json',method='POST')[0],404)
                self.assertEqual(server.store.state(),before)
            finally:
                server.shutdown();server.server_close();worker.join(timeout=5)
