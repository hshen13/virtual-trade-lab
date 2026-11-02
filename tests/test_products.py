"""Original generated unit fixtures; structural test deck is NOT a user deliverable."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from virtual_trade_lab.core import TradeError
from virtual_trade_lab.products import build_bundle, check_bundle, configuration, file_digest, instantiate_pptx, run_campaign


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.template = self.root / 'original-unit-fixture.pptx'
        # XML package fixture supports parser tests, not visual/openability certification.
        ns = 'http://schemas.openxmlformats.org/presentationml/2006/main'
        drawing = 'http://schemas.openxmlformats.org/drawingml/2006/main'
        with ZipFile(self.template, 'w') as deck:
            deck.writestr('[Content_Types].xml', '<Types/>')
            deck.writestr('_rels/.rels', '<Relationships/>')
            deck.writestr('ppt/_rels/presentation.xml.rels', '<Relationships/>')
            deck.writestr('ppt/presentation.xml', f'<p:presentation xmlns:p="{ns}"><p:sldIdLst>' + ''.join(f'<p:sldId id="{i}"/>' for i in range(5)) + '</p:sldIdLst></p:presentation>')
            for i in range(1, 6):
                deck.writestr(f'ppt/slides/slide{i}.xml', f'<p:sld xmlns:p="{ns}" xmlns:a="{drawing}"><a:t>纸舟计划卡 虚构示例 纸质周计划 留白记录</a:t></p:sld>')
        self.output = self.root / 'output'
        self.manifest = build_bundle(self.output, template=self.template)

    def offered(self, vertical):
        return [{"path": f, "sha256": file_digest(self.output / f)} for f in configuration()['verticals'][vertical]['files']]

    def test_all_three_verticals_have_actual_inspectable_files(self):
        for vertical in configuration()['verticals']:
            self.assertEqual(check_bundle(self.output, vertical, self.offered(vertical)), [])
        self.assertTrue(self.manifest['generated_artifact'])
        self.assertFalse(self.manifest['real_market_validated'])
        self.assertFalse(self.manifest['video_rendered'])
        self.assertFalse(self.manifest['broadcast_started'])

    def test_campaign_all_cases_expected_and_conserved(self):
        report = run_campaign(self.output, seeds=[0, 1])
        self.assertEqual(report['total_cases'], 36)
        self.assertEqual(report['expectations_met'], 36)
        self.assertEqual(report['unexpected_failures'], [])
        self.assertEqual(report, run_campaign(self.output, seeds=[0, 1]))
        for row in report['cases']:
            self.assertEqual(row['final_total_credits'], 130)
            self.assertTrue(row['synthetic_only'])
            self.assertFalse(row['real_market_validated'])
            if row['case'] in ('rejected', 'crash_refunded'):
                self.assertEqual(row['buyer_final_credits'], 100)
                self.assertLess(row['seller_net_credits'], 0)
                self.assertTrue(row['failure_evidence'])

    def test_template_name_instantiation_is_bounded_and_repeatable(self):
        second = self.root / 'second'
        build_bundle(second, template=self.template, name='折页记录卡')
        offered = [{'path': 'promo.pptx', 'sha256': file_digest(second / 'promo.pptx')}]
        self.assertEqual(check_bundle(second, 'promo', offered, '折页记录卡'), [])
        copy = self.root / 'repeat.pptx'
        instantiate_pptx(self.template, copy, '折页记录卡')
        self.assertEqual(copy.read_bytes(), (second / 'promo.pptx').read_bytes())
        for name in ['', '<script>', '../name', 'a' * 13, '  ']:
            with self.assertRaises(TradeError):
                build_bundle(self.root / 'bad', template=self.template, name=name)

    def test_no_template_means_error_not_fake_ppt(self):
        with self.assertRaises(TradeError):
            build_bundle(self.root / 'missing', template=self.root / 'missing.pptx')

    def test_bad_digest_missing_extra_and_path_escape_rejected(self):
        original = self.offered('promo')
        variants = [[], original + original, [{'path': '../original-unit-fixture.pptx', 'sha256': file_digest(self.template)}],
                    [{'path': 'promo.pptx', 'sha256': '0' * 64}], [{'path': [], 'sha256': False}]]
        for offered in variants:
            with self.subTest(offered=offered):
                self.assertTrue(check_bundle(self.output, 'promo', offered))
        (self.output / 'promo.pptx').unlink()
        self.assertTrue(check_bundle(self.output, 'promo', original))

    def test_fake_broadcast_or_real_audience_is_not_accepted(self):
        path = self.output / 'livestream-events.json'
        original = json.loads(path.read_text())
        for changes in [{'broadcast_started': True}, {'real_viewers': 10000}, {'audience_is_synthetic': False}, {'rehearsal_only': False}]:
            path.write_text(json.dumps({**original, **changes}), encoding='utf-8')
            self.assertTrue(check_bundle(self.output, 'livestream', self.offered('livestream')))
        path.write_text(json.dumps(original), encoding='utf-8')
        script = self.output / 'livestream-script.md'
        script.write_text(script.read_text() + '\n已售1000件\n', encoding='utf-8')
        self.assertTrue(any('unsupported claim' in issue for issue in check_bundle(self.output, 'livestream', self.offered('livestream'))))

    def test_timing_gaps_and_missing_recovery_are_rejected(self):
        sheet = self.output / 'run-sheet.csv'
        sheet.write_text(sheet.read_text().replace('130,160,recovery', '131,160,recovery'))
        self.assertTrue(check_bundle(self.output, 'livestream', self.offered('livestream')))
        path = self.output / 'livestream-events.json'
        data = json.loads(path.read_text()); data['events'].pop(4)
        path.write_text(json.dumps(data))
        self.assertTrue(check_bundle(self.output, 'livestream', self.offered('livestream')))

    def test_commerce_disclosures_and_funnel_are_enforced(self):
        path = self.output / 'channel-experience.json'
        original = json.loads(path.read_text())
        for field in ['real_payment', 'promotion_posted', 'real_inventory_known']:
            path.write_text(json.dumps({**original, field: True}))
            self.assertTrue(check_bundle(self.output, 'commerce', self.offered('commerce')))
        data = deepcopy(original); data['actors'][0]['synthetic'] = False
        path.write_text(json.dumps(data))
        self.assertTrue(check_bundle(self.output, 'commerce', self.offered('commerce')))
        data = deepcopy(original); data['journey'].pop(1)
        path.write_text(json.dumps(data))
        self.assertTrue(check_bundle(self.output, 'commerce', self.offered('commerce')))

    def test_template_cannot_overwrite_itself(self):
        original = self.template.read_bytes()
        with self.assertRaises(TradeError):
            instantiate_pptx(self.template, self.template, '纸舟计划卡')
        self.assertEqual(self.template.read_bytes(), original)

    def test_external_ppt_relationship_is_not_accepted(self):
        path = self.output / 'promo.pptx'
        with ZipFile(path) as archive:
            parts = {n: archive.read(n) for n in archive.namelist()}
        parts['ppt/slides/_rels/slide1.xml.rels'] = b'<Relationships><Relationship TargetMode="External" Target="https://example.invalid/" /></Relationships>'
        with ZipFile(path, 'w') as archive:
            for name, content in parts.items():
                archive.writestr(name, content)
        self.assertIn('unreviewed external relationship', check_bundle(self.output, 'promo', self.offered('promo')))

    def test_business_acceptance_never_follows_mock_pass(self):
        manifest = build_bundle(self.output, template=self.template)
        self.assertEqual(manifest["business_acceptance"]["status"], "not_evaluated")
        self.assertTrue(all(v == "unverified" for k, v in manifest["business_acceptance"].items() if k != "status"))
        self.assertFalse(manifest["real_market_validated"])

    def test_declared_seeds_are_not_silently_duplicated(self):
        for seeds in [[], [0, 0], [-1], [True]]:
            with self.assertRaises(TradeError):
                run_campaign(self.output, seeds=seeds)


if __name__ == '__main__':
    unittest.main()
