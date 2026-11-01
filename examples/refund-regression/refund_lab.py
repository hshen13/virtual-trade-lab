"""Original offline state-machine fixture; not an Adyen adapter or production ledger."""
import json
import sqlite3
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Event:
    event_id: str
    refund_id: str
    key: str
    payment: str
    amount: int
    status: str
    version: int


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA synchronous=FULL')
    return db


class Provider:
    """Accept asynchronously, settle serially, replay durable keys forever in this fixture."""
    def __init__(self, path):
        self.db = connect(path)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS payments(id TEXT PRIMARY KEY, captured INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS refunds(
          id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE,
          payment TEXT REFERENCES payments(id), amount INTEGER NOT NULL,
          status TEXT NOT NULL, version INTEGER NOT NULL);
        ''')

    def add_payment(self, payment, captured):
        if type(captured) is not int or captured <= 0:
            raise ValueError('positive integer minor units required')
        with self.db:
            self.db.execute('INSERT INTO payments VALUES (?,?)', (payment, captured))

    def _event(self, row):
        rid = f"refund-{row['id']}"
        return Event(f"{rid}:v{row['version']}", rid, row['key'] or '',
                     row['payment'], row['amount'], row['status'], row['version'])

    def submit(self, payment, amount, key=None, lose_response=False):
        if type(amount) is not int or amount <= 0:
            raise ValueError('positive integer minor units required')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT * FROM refunds WHERE key=?', (key,)).fetchone()
            if row and (row['payment'], row['amount']) != (payment, amount):
                raise ValueError('idempotency key payload conflict')
            if not row:
                cur = self.db.execute("INSERT INTO refunds(key,payment,amount,status,version) VALUES (?,?,?,'accepted',1)", (key, payment, amount))
                row = self.db.execute('SELECT * FROM refunds WHERE id=?', (cur.lastrowid,)).fetchone()
        if lose_response:
            raise TimeoutError('response lost; outcome unknown')
        return self._event(row)

    def settle(self, refund_id, fail=False):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT * FROM refunds WHERE id=?', (int(refund_id.removeprefix('refund-')),)).fetchone()
            if row is None:
                raise ValueError('unknown refund')
            if row['status'] == 'accepted':
                captured = self.db.execute('SELECT captured FROM payments WHERE id=?', (row['payment'],)).fetchone()[0]
                paid = self.total(row['payment'])
                status = 'failed' if fail or paid + row['amount'] > captured else 'succeeded'
                self.db.execute('UPDATE refunds SET status=?,version=2 WHERE id=?', (status, row['id']))
                row = self.db.execute('SELECT * FROM refunds WHERE id=?', (row['id'],)).fetchone()
        return self._event(row)

    def read(self, key, visible=True):
        # Empty stale reads are deliberately possible, not evidence of failure.
        row = self.db.execute('SELECT * FROM refunds WHERE key=?', (key,)).fetchone()
        return self._event(row) if row and visible else None

    def total(self, payment):
        return self.db.execute("SELECT COALESCE(SUM(amount),0) FROM refunds WHERE payment=? AND status='succeeded'", (payment,)).fetchone()[0]

    def events(self):
        return [self._event(r) for r in self.db.execute('SELECT * FROM refunds ORDER BY id')]

    def close(self):
        self.db.close()


class Ledger:
    def __init__(self, path):
        self.db = connect(path)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS operations(
          op TEXT PRIMARY KEY, key TEXT UNIQUE NOT NULL, payment TEXT NOT NULL,
          amount INTEGER NOT NULL, refund_id TEXT UNIQUE, status TEXT NOT NULL,
          version INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS attempts(
          id INTEGER PRIMARY KEY AUTOINCREMENT, op TEXT REFERENCES operations(op));
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        ''')

    def intent(self, op, payment, amount):
        if not isinstance(op, str) or not op or type(amount) is not int or amount <= 0:
            raise ValueError('explicit logical operation id and positive minor units required')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO operations(op,key,payment,amount,status) VALUES (?,?,?,?,?)', (op, 'logical:' + op, payment, amount, 'unknown'))
            row = self.get(op)
            if (row['payment'], row['amount']) != (payment, amount):
                raise ValueError('logical operation payload conflict')
        return row

    def get(self, op):
        row = self.db.execute('SELECT * FROM operations WHERE op=?', (op,)).fetchone()
        return dict(row) if row else None

    def send(self, provider, op, payment, amount, lose_response=False, crash_after_response=False):
        row = self.intent(op, payment, amount)  # committed before any provider call
        if row['status'] != 'unknown':
            return row  # accepted is pending, never a new refund
        with self.db:
            self.db.execute('INSERT INTO attempts(op) VALUES (?)', (op,))
        try:
            event = provider.submit(payment, amount, row['key'], lose_response)
        except TimeoutError:
            return self.get(op)  # never label timeout as failed
        if crash_after_response:
            raise RuntimeError('injected crash after provider acceptance, before local receipt')
        self.reconcile(event)
        return self.get(op)

    def observe(self, provider, op, visible=True):
        event = provider.read(self.get(op)['key'], visible)
        if event is not None:
            self.reconcile(event)
        return self.get(op)

    def reconcile(self, event):
        # Trust boundary: caller supplies already authenticated, schema-normalized events.
        if (event.status, event.version) not in {('accepted', 1), ('succeeded', 2), ('failed', 2)}:
            raise ValueError('unsupported event state/version')
        payload = json.dumps(asdict(event), sort_keys=True)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old = self.db.execute('SELECT payload FROM events WHERE id=?', (event.event_id,)).fetchone()
            if old:
                if old[0] != payload:
                    raise ValueError('event id reused with changed payload')
                return 'duplicate'
            row = self.db.execute('SELECT * FROM operations WHERE key=?', (event.key,)).fetchone()
            if not row or (row['payment'], row['amount']) != (event.payment, event.amount):
                raise ValueError('unmatched event; requires investigation')
            if row['refund_id'] not in (None, event.refund_id):
                raise ValueError('one logical operation mapped to multiple refunds')
            if row['version'] == event.version and row['status'] != event.status:
                raise ValueError('conflicting terminal outcome; requires investigation')
            self.db.execute('INSERT INTO events VALUES (?,?)', (event.event_id, payload))
            if event.version > row['version']:
                self.db.execute('UPDATE operations SET refund_id=?,status=?,version=? WHERE op=?', (event.refund_id, event.status, event.version, row['op']))
                return 'applied'
            return 'late'

    def close(self):
        self.db.close()
