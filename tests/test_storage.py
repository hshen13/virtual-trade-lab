"""Durability and concurrency tests; no external services or real payments."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from virtual_trade_lab import TradeError
from virtual_trade_lab.__main__ import SOURCE
from virtual_trade_lab.storage import Conflict, StorageError, Store


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.store = Store(self.path)
        self.key = 0

    def request(self, action, payload=None, state=None, order="one"):
        state = state or self.store.state()
        self.key += 1
        return {"epoch": state["epoch"], "expected_revision": state["revision"],
                "key": f"request-{self.key}", "action": action,
                "order_id": order, "payload": payload or {}}

    def execute(self, action, **payload):
        request = self.request(action, payload)
        return request, self.store.command(request)

    def quote(self):
        return self.execute("quote", source=SOURCE)

    def sql(self, command):
        with sqlite3.connect(self.path) as db:
            db.execute(command)

    def test_restart_replays_all_states_without_duplicate_transfers(self):
        for action, payload in [("quote", {"source": SOURCE}), ("fund", {}),
                                ("deliver", {}), ("review", {})]:
            request = self.request(action, payload)
            result = self.store.command(request)
            restarted = Store(self.path)
            self.assertEqual(restarted.state(), result)
            # Retry a request whose response was lost before shutdown.
            self.assertEqual(restarted.command(request), result)
            self.assertEqual(restarted.state(), result)
            self.store = restarted
        self.assertEqual(result["balances"]["buyer"], 80)
        self.assertEqual(result["balances"]["seller"], 46)
        self.assertEqual(len(result["journal"]), 3)

    def test_historical_retry_returns_current_state_without_new_effect(self):
        old, _ = self.quote()
        self.execute("fund")
        current = self.store.state()
        self.assertEqual(Store(self.path).command(old), current)
        self.assertEqual(self.store.state(), current)

    def test_changed_payload_same_key_conflicts(self):
        request, _ = self.quote()
        request["payload"]["criteria"] = {"budget": 1}
        before = self.store.state()
        with self.assertRaises(Conflict):
            self.store.command(request)
        self.assertEqual(self.store.state(), before)

    def test_stale_store_action_is_rejected_atomically(self):
        self.quote()
        other = Store(self.path)
        stale = self.request("cancel", state=other.state())
        self.execute("fund")
        before = self.store.state()
        with self.assertRaises(Conflict):
            other.command(stale)
        self.assertEqual(other.state(), before)

    def test_simultaneous_distinct_commands_serialize(self):
        self.quote()
        state = self.store.state()
        requests = [self.request("fund", state=state), self.request("cancel", state=state)]
        stores = [Store(self.path), Store(self.path)]
        barrier = threading.Barrier(2)

        def act(index):
            barrier.wait(timeout=5)
            try:
                return stores[index].command(requests[index])
            except Conflict:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(act, range(2)))
        self.assertEqual(results.count("conflict"), 1)
        final = self.store.state()
        self.assertEqual(final["revision"], 2)
        self.assertEqual(sum(final["balances"].values()), 130)

    def test_simultaneous_duplicate_commands_commit_once(self):
        self.quote()
        request = self.request("fund")
        stores = [Store(self.path), Store(self.path)]
        barrier = threading.Barrier(2)

        def act(index):
            barrier.wait(timeout=5)
            return stores[index].command(request)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(act, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.store.state()["journal"]), 1)

    def test_reset_archives_history_and_rejects_old_epoch(self):
        quote_request, _ = self.quote()
        self.execute("fund")
        before = self.store.state()
        reset = {"epoch": before["epoch"], "expected_revision": before["revision"], "key": "reset-1"}
        after = self.store.reset(reset)
        self.assertNotEqual(before["epoch"], after["epoch"])
        self.assertEqual(after["revision"], 0)
        self.assertEqual(after["balances"], {"buyer": 100, "seller": 30, "provider": 0})
        self.assertEqual(after["orders"], [])
        self.assertEqual(Store(self.path).reset(reset), after)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM runs").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT count(*) FROM commands").fetchone()[0], 2)
        with self.assertRaises(Conflict):
            self.store.command(quote_request)
        self.assertEqual(self.store.state(), after)

    def test_reset_retry_ignores_updated_revision_precondition(self):
        before = self.store.state()
        reset = {"epoch": before["epoch"], "expected_revision": 0, "key": "reset"}
        after = self.store.reset(reset)
        reset["expected_revision"] = 42
        self.assertEqual(self.store.reset(reset), after)

    def test_stale_reset_is_rejected(self):
        before = self.store.state()
        self.quote()
        with self.assertRaises(Conflict):
            self.store.reset({"epoch": before["epoch"], "expected_revision": 0, "key": "reset"})
        self.assertEqual(self.store.state()["revision"], 1)

    def test_old_reset_retry_after_another_reset_is_rejected(self):
        before = self.store.state()
        first = {"epoch": before["epoch"], "expected_revision": 0, "key": "first-reset"}
        middle = self.store.reset(first)
        second = {"epoch": middle["epoch"], "expected_revision": 0, "key": "second-reset"}
        after = self.store.reset(second)
        with self.assertRaises(Conflict):
            self.store.reset(first)
        self.assertEqual(self.store.state(), after)

    def test_out_of_order_and_failed_commands_not_persisted(self):
        self.quote()
        before = self.store.state()
        request = self.request("deliver")
        with self.assertRaises(TradeError):
            self.store.command(request)
        self.assertEqual(Store(self.path).state(), before)
        self.execute("fund")
        request["expected_revision"] = self.store.state()["revision"]
        self.assertEqual(self.store.command(request)["orders"][0]["state"], "delivered")

    def test_write_failure_rolls_back_generated_market_state(self):
        self.quote()
        before = self.store.state()
        self.sql("CREATE TRIGGER stop_insert BEFORE INSERT ON commands BEGIN SELECT RAISE(ABORT, 'injected disk write failure'); END")
        with self.assertRaises(StorageError):
            self.execute("fund")
        self.assertEqual(Store(self.path).state(), before)

    def test_invalid_requests_leave_state_unchanged(self):
        request = self.request("quote", {"source": SOURCE})
        invalid = [None, [], {}, {**request, "extra": True},
                   {**request, "expected_revision": True}, {**request, "expected_revision": -1},
                   {**request, "payload": []}, {**request, "action": []},
                   {**request, "key": ""}, {**request, "order_id": "x" * 129},
                   {**request, "payload": {"nan": float("nan")}},
                   {**request, "payload": {"large": "x" * 65536}}]
        before = self.store.state()
        for value in invalid:
            with self.subTest(value=str(value)[:100]), self.assertRaises(TradeError):
                self.store.command(value)
            self.assertEqual(self.store.state(), before)

    def test_existing_empty_and_non_sqlite_files_fail_closed(self):
        for data in [b"", b"not a SQLite database"]:
            path = Path(self.temp.name) / f"invalid-{len(data)}.sqlite3"
            path.write_bytes(data)
            with self.subTest(data=data), self.assertRaises(StorageError):
                Store(path)
            self.assertEqual(path.read_bytes(), data)

    def test_unsupported_schema_fails_closed(self):
        self.sql("UPDATE meta SET schema='future-version'")
        with self.assertRaises(StorageError):
            Store(self.path)

    def test_checksum_mismatch_fails_closed(self):
        self.quote()
        self.sql("UPDATE commands SET digest='wrong'")
        with self.assertRaises(StorageError):
            Store(self.path)

    def test_invalid_stored_json_fails_closed(self):
        self.quote()
        self.sql("UPDATE commands SET request='not json'")
        with self.assertRaises(StorageError):
            Store(self.path)

    def test_missing_middle_command_fails_closed(self):
        self.quote()
        self.execute("fund")
        self.sql("DELETE FROM commands WHERE seq=1")
        with self.assertRaises(StorageError):
            Store(self.path)

    def test_missing_final_command_fails_closed(self):
        self.quote()
        self.execute("fund")
        self.sql("DELETE FROM commands WHERE seq=2")
        with self.assertRaises(StorageError):
            Store(self.path)

    def test_missing_active_run_fails_closed(self):
        self.sql("DELETE FROM runs")
        with self.assertRaises(StorageError):
            Store(self.path)

    def test_physically_truncated_database_fails_closed(self):
        self.quote()
        original = self.path.read_bytes()
        self.path.write_bytes(original[:120])
        with self.assertRaises(StorageError):
            Store(self.path)
        self.assertEqual(self.path.read_bytes(), original[:120])

    def test_mutable_return_values_do_not_change_persisted_state(self):
        _, result = self.quote()
        expected = deepcopy(result)
        result["orders"][0]["source"][0]["title"] = "changed"
        result["balances"]["buyer"] = 10000
        self.assertEqual(Store(self.path).state(), expected)

    def test_command_limit_rejects_new_work_but_allows_reset(self):
        self.quote()
        self.store.MAX_COMMANDS = 1
        with self.assertRaises(TradeError):
            self.execute("fund")
        state = self.store.state()
        self.assertEqual(self.store.reset({"epoch": state["epoch"], "expected_revision": 1,
                                         "key": "reset-at-limit"})["revision"], 0)


if __name__ == "__main__":
    unittest.main()
