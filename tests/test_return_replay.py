import hashlib
import http.client
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from virtual_trade_lab.return_replay import build, render
from virtual_trade_lab.server import make_server

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'examples/return-custody-model-study'
WEB=ROOT/'virtual_trade_lab/web'

class ReturnReplayTests(unittest.TestCase):
    def test_exact_generated_assets(self):
        data=build(STUDY)
        self.assertEqual(data,json.loads((WEB/'returns-data.json').read_text()))
        self.assertEqual(render(data),(WEB/'returns.html').read_text())
        self.assertEqual(data['model_calls'],3)
        self.assertEqual([s['custody'] for s in data['stages']],['buyer','carrier','seller'])
        self.assertEqual([s['balances']['buyer'] for s in data['stages']],[58,58,90])
        self.assertEqual([s['balances']['provider'] for s in data['stages']],[4,8,8])
        for s in data['stages']:self.assertEqual(sum(s['balances'].values()),130)
        for s in data['stages']:
            for key,row in s['records'].items():
                if row['status']!='missing':self.assertEqual(row['raw'],(STUDY/'responses'/f'{key}.txt').read_text())

    def test_tampered_intermediate_snapshot_rejected(self):
        for field in ('market','records','protocol_sha256','observation_tick','return_protocol'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
                root=Path(d)/'study';shutil.copytree(STUDY,root)
                p=root/'snapshots/handed_off_not_received.json';r=json.loads(p.read_text());r[field]={};p.write_text(json.dumps(r))
                with self.assertRaises(ValueError):build(root)

    def test_missing_seal_and_changed_final_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'study';shutil.copytree(STUDY,root)
            p=root/'report.json';r=json.loads(p.read_text());r['market']['balances']['buyer']=91;p.write_text(json.dumps(r))
            with self.assertRaises(ValueError):build(root)
            (root/'manifest.json').unlink()
            with self.assertRaises(ValueError):build(root)

    def test_readonly_links_and_safe_text(self):
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in STUDY.rglob('*') if p.is_file()}
        data=build(STUDY);html=render(data)
        self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in STUDY.rglob('*') if p.is_file()})
        self.assertNotIn('<script',html);self.assertNotIn('/api/',html);self.assertNotIn('https://',html)
        self.assertNotIn('csrf_token',json.dumps(data))
        for i in range(1,4):
            self.assertIn(f'href="#stage-{i}"',html);self.assertIn(f'id="stage-{i}"',html)
        data['stages'][0]['records']['buyer_request']['raw']='<script>alert(1)</script>'
        self.assertIn('&lt;script&gt;',render(data))
        self.assertIn('独立退货实验',html);self.assertIn('尚无丢件',html)

    def test_http_readonly_refresh_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            server=make_server(Path(d)/'state.sqlite3',0)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            before=server.store.state()
            def request(path,method='GET',host=None):
                c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                c.request(method,path,headers={'Host':host or f'127.0.0.1:{server.server_port}','X-VTL-Token':server.csrf_token,'Content-Type':'application/json'})
                r=c.getresponse();v=(r.status,r.read());c.close();return v
            try:
                for _ in range(2):
                    for path in ('/returns','/returns.css','/returns-data.json','/journey','/journey.css','/information','/utility'):
                        self.assertEqual(request(path)[0],200)
                self.assertEqual(request('/returns','POST')[0],404)
                self.assertEqual(request('/returns',host='bad.example')[0],403)
                self.assertEqual(server.store.state(),before)
            finally:server.shutdown();server.server_close();worker.join()
