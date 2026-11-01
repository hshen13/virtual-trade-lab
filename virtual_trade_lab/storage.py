"""SQLite-backed command replay, atomic commits, and stale-tab protection.

Persistence supports only the bundled deterministic catalog-v1 implementation.
A different adapter/version needs an explicit migration, not silent replay.
"""
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from . import CatalogBuyer, CatalogSeller, Market, TradeError


class Conflict(TradeError):
    pass


class StorageError(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def export(market):
    return {"balances": market.balances, "initial_total": market.initial_total,
            "orders": [asdict(market.order(k)) for k in market._orders],
            "events": market.events, "journal": market.journal}


def digest(market):
    return hashlib.sha256(canonical(export(market)).encode()).hexdigest()


class Store:
    SCHEMA = "catalog-v1/schema-1"
    MAX_COMMANDS = 1000

    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Never silently recreate an existing empty/damaged database.
        create = not self.path.exists()
        if create:
            try:
                self.path.touch(mode=0o600, exist_ok=False)
            except FileExistsError:
                create = False
        try:
            with self._connection() as db:
                if create:
                    db.execute("CREATE TABLE meta (id INTEGER PRIMARY KEY CHECK(id=1), schema TEXT NOT NULL, active TEXT NOT NULL)")
                    db.execute("CREATE TABLE runs (epoch TEXT PRIMARY KEY, parent TEXT, reset_key TEXT UNIQUE, revision INTEGER NOT NULL, digest TEXT NOT NULL)")
                    db.execute("CREATE TABLE commands (epoch TEXT NOT NULL REFERENCES runs(epoch), seq INTEGER NOT NULL, key TEXT NOT NULL, request TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(epoch,seq), UNIQUE(epoch,key))")
                    epoch = str(uuid.uuid4())
                    db.execute("INSERT INTO runs VALUES (?,NULL,NULL,0,?)", (epoch, digest(Market(CatalogSeller(), CatalogBuyer()))))
                    db.execute("INSERT INTO meta VALUES (1,?,?)", (self.SCHEMA, epoch))
                self._load(db)
        except (sqlite3.Error, ValueError, TypeError, KeyError, RuntimeError) as exc:
            if isinstance(exc, StorageError):
                raise
            raise StorageError("Local database invalid or unavailable; preserve it and choose a new --db path.") from exc

    @contextmanager
    def _connection(self):
        db = None
        try:
            db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except sqlite3.Error as exc:
            if db and db.in_transaction:
                db.rollback()
            raise StorageError("Local database unavailable or damaged; no change committed.") from exc
        except Exception:
            if db and db.in_transaction:
                db.rollback()
            raise
        finally:
            if db:
                db.close()

    def _load(self, db):
        try:
            if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise StorageError("Database integrity check failed; no automatic reset.")
            meta = db.execute("SELECT schema,active FROM meta WHERE id=1").fetchone()
            if not meta or meta[0] != self.SCHEMA:
                raise StorageError("Unknown database schema; explicit migration required.")
            epoch = meta[1]
            head = db.execute("SELECT revision,digest FROM runs WHERE epoch=?", (epoch,)).fetchone()
            if not head:
                raise StorageError("Missing active run.")
            market = Market(CatalogSeller(), CatalogBuyer())
            rows = db.execute("SELECT seq,key,request,digest FROM commands WHERE epoch=? ORDER BY seq", (epoch,)).fetchall()
            if len(rows) > self.MAX_COMMANDS:
                raise StorageError("Run exceeds supported replay limit.")
            for expected, (seq, key, request, checksum) in enumerate(rows, 1):
                if seq != expected:
                    raise StorageError("Missing command sequence.")
                command = json.loads(request)
                market.execute(command["action"], command["order_id"], key, **command["payload"])
                if digest(market) != checksum:
                    raise StorageError("Replay mismatch; preserve database, do not overwrite it.")
            if head != (len(rows), digest(market)):
                raise StorageError("Run head mismatch; command history is incomplete.")
            return epoch, len(rows), market
        except StorageError:
            raise
        except (TradeError, TypeError, ValueError, KeyError, RuntimeError) as exc:
            raise StorageError("Stored command cannot be replayed; no automatic reset.") from exc

    def _state(self, epoch, revision, market):
        return {"epoch": epoch, "revision": revision, **export(market)}

    def state(self):
        with self._connection() as db:
            return self._state(*self._load(db))

    def _validate(self, request, reset=False):
        fields = {"epoch", "expected_revision", "key"} | (set() if reset else {"action", "order_id", "payload"})
        if not isinstance(request, dict) or set(request) != fields:
            raise TradeError("Request has missing or unexpected fields.")
        for name in ["epoch", "key"] + ([] if reset else ["action", "order_id"]):
            if not isinstance(request[name], str) or not 1 <= len(request[name]) <= 128:
                raise TradeError(f"{name} must be 1–128 characters.")
        if type(request["expected_revision"]) is not int or request["expected_revision"] < 0:
            raise TradeError("expected_revision must be a nonnegative integer.")
        if not reset and not isinstance(request["payload"], dict):
            raise TradeError("payload must be an object.")
        try:
            if len(canonical(request).encode()) > 65536:
                raise TradeError("Request exceeds 64 KiB.")
        except (ValueError, TypeError) as exc:
            raise TradeError("Request must contain finite JSON values.") from exc

    def command(self, request):
        self._validate(request)
        command = {k: request[k] for k in ["action", "order_id", "payload"]}
        encoded = canonical(command)
        with self._connection() as db:
            epoch, revision, market = self._load(db)
            if epoch != request["epoch"]:
                raise Conflict("This run was reset in another tab. Refresh before acting.")
            previous = db.execute("SELECT request FROM commands WHERE epoch=? AND key=?", (epoch, request["key"])).fetchone()
            if previous:
                if previous[0] != encoded:
                    raise Conflict("Idempotency key conflict.")
                # A lost HTTP response can be retried after restart, even at an old revision.
                return self._state(epoch, revision, market)
            if revision != request["expected_revision"]:
                raise Conflict("Another action changed this run. Refresh before acting.")
            if revision >= self.MAX_COMMANDS:
                raise TradeError("Run command limit reached; start a new run.")
            market.execute(command["action"], command["order_id"], request["key"], **command["payload"])
            db.execute("INSERT INTO commands VALUES (?,?,?,?,?)", (epoch, revision + 1, request["key"], encoded, digest(market)))
            db.execute("UPDATE runs SET revision=?,digest=? WHERE epoch=?", (revision + 1, digest(market), epoch))
            return self._state(epoch, revision + 1, market)

    def reset(self, request):
        self._validate(request, reset=True)
        with self._connection() as db:
            epoch, revision, market = self._load(db)
            previous = db.execute("SELECT epoch,parent FROM runs WHERE reset_key=?", (request["key"],)).fetchone()
            if previous:
                if previous != (epoch, request["epoch"]):
                    raise Conflict("Reset key belongs to a different run. Refresh.")
                return self._state(epoch, revision, market)
            if epoch != request["epoch"] or revision != request["expected_revision"]:
                raise Conflict("Run changed. Refresh before starting a new run.")
            new_epoch = str(uuid.uuid4())
            db.execute("INSERT INTO runs VALUES (?,?,?,0,?)", (new_epoch, epoch, request["key"], digest(Market(CatalogSeller(), CatalogBuyer()))))
            db.execute("UPDATE meta SET active=? WHERE id=1", (new_epoch,))
            return self._state(new_epoch, 0, Market(CatalogSeller(), CatalogBuyer()))
