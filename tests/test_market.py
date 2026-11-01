import json
import random
import subprocess
import sys
import unittest
from dataclasses import asdict

from virtual_trade_lab import CatalogBuyer, CatalogSeller, Criteria, Market, Quote, TradeError
from virtual_trade_lab.__main__ import SOURCE, run_scenario


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.m = Market(CatalogSeller(), CatalogBuyer())
        self.i = 0

    def do(self, action, order="o", **payload):
        self.i += 1
        return self.m.execute(action, order, str(self.i), **payload)

    def quote(self, **criteria):
        return self.do("quote", source=SOURCE, criteria=criteria)

    def snapshot(self):
        return (self.m.balances, self.m.journal, self.m.events,
                {k: asdict(v) for k, v in self.m._orders.items()})

    def test_happy_path(self):
        self.quote()
        self.do("fund")
        self.do("deliver")
        result = self.do("review")
        self.assertEqual(result["state"], "accepted")
        self.assertEqual(self.m.balances, {"buyer": 80, "seller": 46, "provider": 4, "escrow:o": 0})
        self.assertEqual(result["result"][0]["title"], "Ceramic cup")

    def test_six_demo_outcomes_and_costs(self):
        expected = {"happy": ("accepted", 4, 16), "revision": ("accepted", 8, 12),
                    "reject": ("rejected", 8, -8), "cancel": ("cancelled", 0, 0),
                    "budget": ("cancelled", 0, 0), "crash": ("rejected", 8, -8)}
        for name, values in expected.items():
            with self.subTest(name=name):
                report = run_scenario(name)
                self.assertEqual((report["order"]["state"], report["seller"]["cost_credits"],
                                  report["seller"]["net_credits"]), values)
                self.assertEqual(report["final_total"], 130)
                self.assertEqual(report, run_scenario(name))

    def test_all_successful_commands_are_idempotent(self):
        for action, payload in [("quote", {"source": SOURCE}), ("fund", {}),
                                ("deliver", {"mode": "defective"}), ("review", {}),
                                ("deliver", {}), ("review", {})]:
            self.i += 1
            key = str(self.i)
            first = self.m.execute(action, "o", key, **payload)
            before = self.snapshot()
            for _ in range(3):
                self.assertEqual(self.m.execute(action, "o", key, **payload), first)
                self.assertEqual(self.snapshot(), before)
            first["state"] = "tampered"  # receipts must not alias internal cache
            self.assertNotEqual(self.m.execute(action, "o", key, **payload)["state"], "tampered")

    def test_cancel_idempotent(self):
        self.quote()
        self.do("fund")
        self.m.execute("cancel", "o", "cancel")
        before = self.snapshot()
        self.m.execute("cancel", "o", "cancel")
        self.assertEqual(self.snapshot(), before)

    def test_key_conflicts_do_not_mutate(self):
        self.m.execute("quote", "o", "key", source=SOURCE)
        before = self.snapshot()
        with self.assertRaisesRegex(TradeError, "conflict"):
            self.m.execute("fund", "o", "key")
        self.assertEqual(before, self.snapshot())

    def test_budget_and_insufficient_buyer(self):
        for budget, funds, message in [(19, 100, "budget"), (40, 19, "insufficient")]:
            with self.subTest(budget=budget):
                self.m = Market(CatalogSeller(), CatalogBuyer(), buyer_credits=funds)
                self.quote(budget=budget)
                before = self.snapshot()
                with self.assertRaisesRegex(TradeError, message):
                    self.do("fund")
                self.assertEqual(before, self.snapshot())

    def test_insufficient_seller_cost_is_atomic(self):
        self.m = Market(CatalogSeller(), CatalogBuyer(), seller_credits=3)
        self.quote()
        self.do("fund")
        before = self.snapshot()
        with self.assertRaisesRegex(TradeError, "insufficient seller"):
            self.do("deliver")
        self.assertEqual(before, self.snapshot())
        self.do("cancel")
        self.assertEqual(self.m.balances["buyer"], 100)

    def test_cancel_after_revision_keeps_cost(self):
        self.quote()
        self.do("fund")
        self.do("deliver", mode="defective")
        self.do("review")
        self.do("cancel")
        self.assertEqual(self.m.balances["buyer"], 100)
        self.assertEqual(self.m.balances["seller"], 26)

    def test_no_revisions_rejects_immediately(self):
        self.quote(max_revisions=0)
        self.do("fund")
        self.do("deliver", mode="defective")
        self.assertEqual(self.do("review")["state"], "rejected")

    def test_buyer_can_fail_normal_seller(self):
        self.quote(max_title_length=3, max_revisions=0)
        self.do("fund")
        self.do("deliver")
        result = self.do("review")
        self.assertEqual(result["state"], "rejected")
        self.assertIn("CUP-01: title too long", result["issues"])

    def test_invalid_transitions_are_atomic(self):
        self.quote()
        for action in ["review", "deliver"]:
            before = self.snapshot()
            with self.assertRaises(TradeError):
                self.do(action)
            self.assertEqual(before, self.snapshot())
        self.do("fund")
        self.do("deliver")
        with self.assertRaises(TradeError):
            self.do("cancel")
        self.do("review")
        for action in ["fund", "deliver", "review", "cancel", "quote"]:
            before = self.snapshot()
            with self.assertRaises(TradeError):
                self.do(action)
            self.assertEqual(before, self.snapshot())

    def test_malformed_inputs(self):
        for criteria in [{"budget": -1}, {"budget": True}, {"max_revisions": 1.5},
                         {"max_title_length": 0}, {"unexpected": 1}]:
            with self.subTest(criteria=criteria), self.assertRaises(TradeError):
                self.quote(**criteria)
        bad_sources = [[], None, [1], [{}], SOURCE + SOURCE,
                       [{"sku": "a", "title": "x", "price_cents": -1}],
                       [{"sku": "a", "title": "x", "price_cents": True}]]
        for source in bad_sources:
            with self.subTest(source=source), self.assertRaises(TradeError):
                self.do("quote", source=source)
        self.assertEqual(self.m.events, [])
        for value in [-1, True, 1.1]:
            with self.assertRaises(TradeError):
                Market(CatalogSeller(), CatalogBuyer(), buyer_credits=value)

    def test_unknown_fields_and_commands(self):
        for action, payload in [("delete", {}), ("quote", {"extra": 1}), ("fund", {})]:
            with self.assertRaises(TradeError):
                self.do(action, **payload)
        with self.assertRaises(TradeError):
            self.m.execute("quote", "", "key", source=SOURCE)

    def test_mutation_isolation(self):
        source = json.loads(json.dumps(SOURCE))
        self.do("quote", source=source)
        source[0]["title"] = "tamper"
        self.m.order("o").source[0]["title"] = "tamper"
        self.m.balances["buyer"] = 999
        self.assertEqual(self.m.order("o").source, SOURCE)
        self.assertEqual(self.m.balances["buyer"], 100)

    def test_failed_key_can_be_retried(self):
        self.quote()
        with self.assertRaises(TradeError):
            self.m.execute("deliver", "o", "retry")
        self.do("fund")
        self.assertEqual(self.m.execute("deliver", "o", "retry")["state"], "delivered")

    def test_multiple_orders_have_isolated_escrow(self):
        self.quote()
        self.do("quote", order="other", source=SOURCE)
        self.do("fund")
        self.do("fund", order="other")
        self.do("cancel")
        self.assertEqual(self.m.balances["escrow:other"], 20)
        self.do("deliver", order="other")
        self.do("review", order="other")
        self.m.assert_invariants()

    def test_randomized_transition_sequences(self):
        rng = random.Random(2026)
        for run in range(30):
            self.m = Market(CatalogSeller(), CatalogBuyer())
            self.quote(max_revisions=rng.randrange(3))
            for step in range(60):
                action = rng.choice(["fund", "deliver", "review", "cancel"])
                payload = {"mode": rng.choice(["normal", "defective", "crash"])} if action == "deliver" else {}
                before = self.snapshot()
                try:
                    self.do(action, **payload)
                except TradeError:
                    self.assertEqual(before, self.snapshot())
                self.m.assert_invariants()

    def test_adapter_exception_is_charged_failure(self):
        self.quote(max_revisions=0)
        self.do("fund")
        result = self.do("deliver", mode="crash")
        self.assertEqual(result["cost"], 4)
        self.assertEqual(result["issues"], ["seller failure: RuntimeError"])
        self.assertEqual(self.do("review")["state"], "rejected")

    def test_alternative_service_and_buyer(self):
        class EchoSeller:
            name = "echo"
            def quote(self, source):
                return Quote(5, 1, self.name)
            def fulfill(self, source, attempt, mode):
                return source
        class EchoBuyer:
            def assess(self, source, result, criteria):
                return [] if source == result else ["not equal"]
        self.m = Market(EchoSeller(), EchoBuyer())
        self.do("quote", source=[{"message": "hello"}])
        self.do("fund")
        self.do("deliver")
        self.assertEqual(self.do("review")["state"], "accepted")

    def test_evaluator_error_rolls_back_review(self):
        class BrokenBuyer:
            def assess(self, *args):
                raise RuntimeError("broken oracle")
        self.m = Market(CatalogSeller(), BrokenBuyer())
        self.quote()
        self.do("fund")
        self.do("deliver")
        before = self.snapshot()
        with self.assertRaises(RuntimeError):
            self.do("review")
        self.assertEqual(before, self.snapshot())

    def test_wrong_command_types(self):
        with self.assertRaises(TradeError):
            self.m.execute([], "o", "bad")
        self.quote()
        self.do("fund")
        before = self.snapshot()
        with self.assertRaises(TradeError):
            self.do("deliver", mode=[])
        self.assertEqual(before, self.snapshot())

    def test_evaluator_issues_are_detached(self):
        class RetainingBuyer:
            issues = ["quality failure"]
            def assess(self, *args):
                return self.issues
        buyer = RetainingBuyer()
        self.m = Market(CatalogSeller(), buyer)
        self.quote()
        self.do("fund")
        self.do("deliver")
        self.do("review")
        buyer.issues.clear()
        self.assertEqual(self.m.order("o").issues, ["quality failure"])
        self.assertEqual(self.m.events[-1]["issues"], ["quality failure"])

    def test_malformed_adapter_output_is_failure(self):
        class BadSeller(CatalogSeller):
            def fulfill(self, *args):
                return {"invalid": "not a list"}
        self.m = Market(BadSeller(), CatalogBuyer())
        self.quote(max_revisions=0)
        self.do("fund")
        self.do("deliver")
        result = self.do("review")
        self.assertEqual(result["state"], "rejected")
        self.assertEqual(result["cost"], 4)

    def test_invariant_detects_conserved_but_unjournaled_mutation(self):
        self.m._balances["buyer"] -= 1
        self.m._balances["seller"] += 1
        with self.assertRaisesRegex(RuntimeError, "journal does not reconcile"):
            self.m.assert_invariants()

    def test_cli_json(self):
        output = subprocess.check_output([sys.executable, "-m", "virtual_trade_lab", "--json"], text=True)
        self.assertEqual(len(json.loads(output)), 6)


class BuyerTests(unittest.TestCase):
    def test_independent_bad_artifacts(self):
        buyer = CatalogBuyer()
        valid = CatalogSeller().fulfill(SOURCE, 1, "normal")
        candidates = [[], valid + valid, [{"sku": "bad"}],
                      [{**valid[0], "sku": []}, valid[1]],
                      [{**valid[0], "title": 1}, valid[1]],
                      [{**valid[0], "title": "Invented product"}, valid[1]],
                      [{**valid[0], "price_cents": True}, valid[1]]]
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertTrue(buyer.assess(SOURCE, candidate, Criteria()))


if __name__ == "__main__":
    unittest.main()
