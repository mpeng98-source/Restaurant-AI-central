"""Offline state-machine prototype. No network, subprocesses, credentials or publisher.

Caller inputs (clock, costs, runtime digest) are synthetic trusted fixtures here.
This is NOT a security boundary or production spending control.
"""
from contextlib import contextmanager
import re
import sqlite3


class Denied(ValueError):
    pass


def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise Denied("invalid integer")
    return value


class Controller:
    # Deliberately small, immutable simulation policy; USD microdollars.
    LIMIT = 10_000_000
    CALL_BOUND = 1_000_000
    CALLS = 2
    JOB_SECONDS = 120
    LEASE_SECONDS = 30
    COST_AGE = 60

    def __init__(self, path, *, runtime_digest):
        if not re.fullmatch(r"[a-f0-9]{64}", runtime_digest):
            raise Denied("missing runtime fixture digest")
        self.db = sqlite3.connect(path, isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS control (
            id INTEGER PRIMARY KEY CHECK(id=1), stopped INTEGER NOT NULL,
            clock INTEGER NOT NULL, runtime TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS costs (
            day INTEGER PRIMARY KEY, amount INTEGER NOT NULL, observed INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS jobs (
            task TEXT PRIMARY KEY, digest TEXT NOT NULL, state TEXT NOT NULL,
            fence INTEGER NOT NULL DEFAULT 0, deadline INTEGER, lease INTEGER,
            reserve INTEGER NOT NULL DEFAULT 0, calls INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS requests (
            task TEXT NOT NULL, fence INTEGER NOT NULL, sequence INTEGER NOT NULL,
            state TEXT NOT NULL, PRIMARY KEY(task,fence,sequence));
        """)
        self.db.execute("INSERT OR IGNORE INTO control VALUES(1,0,0,?)", (runtime_digest,))
        if self.db.execute("SELECT runtime FROM control").fetchone()[0] != runtime_digest:
            self.db.close()
            raise Denied("runtime differs from durable policy")

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def clock(self, now):
        integer(now)
        old = self.db.execute("SELECT clock FROM control").fetchone()[0]
        if now < old:
            raise Denied("clock rollback")
        self.db.execute("UPDATE control SET clock=?", (now,))

    def live(self, now):
        self.clock(now)
        if self.db.execute("SELECT stopped FROM control").fetchone()[0]:
            raise Denied("stop latched")

    def enqueue(self, task, digest):
        if not re.fullmatch(r"[a-z0-9-]{1,80}", task) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise Denied("invalid task fixture")
        with self.transaction():
            row = self.db.execute("SELECT digest FROM jobs WHERE task=?", (task,)).fetchone()
            if row and row[0] != digest:
                raise Denied("task changed; new scope review required")
            self.db.execute("INSERT OR IGNORE INTO jobs(task,digest,state) VALUES(?,?,'queued')", (task, digest))

    def fixture_cost(self, now, amount):
        """Synthetic evidence ONLY; no production authentication is implemented."""
        integer(amount)
        with self.transaction():
            self.clock(now)
            day = now // 86400
            row = self.db.execute("SELECT amount FROM costs WHERE day=?", (day,)).fetchone()
            if row and amount < row[0]:
                raise Denied("cost decrease needs reconciliation")
            self.db.execute("INSERT INTO costs VALUES(?,?,?) ON CONFLICT(day) DO UPDATE SET amount=excluded.amount, observed=excluded.observed", (day, amount, now))

    def evidence(self, now):
        row = self.db.execute("SELECT * FROM costs WHERE day=?", (now // 86400,)).fetchone()
        if row is None or not 0 <= now - row['observed'] <= self.COST_AGE:
            raise Denied("missing or stale daily costs")
        return row['amount']

    def claim(self, task, digest, now):
        with self.transaction():
            self.live(now)
            reported = self.evidence(now)
            row = self.db.execute("SELECT * FROM jobs WHERE task=?", (task,)).fetchone()
            if row is None or row['state'] != 'queued' or row['digest'] != digest:
                raise Denied("task unavailable or changed")
            if self.db.execute("SELECT 1 FROM jobs WHERE state='running'").fetchone():
                raise Denied("one worker at a time")
            held = self.db.execute("SELECT COALESCE(SUM(reserve),0) FROM jobs").fetchone()[0]
            bound = self.CALL_BOUND * self.CALLS
            if reported + held + bound > self.LIMIT:
                raise Denied("exposure ceiling")
            deadline = min(now + self.JOB_SECONDS, (now // 86400 + 1) * 86400)
            fence = row['fence'] + 1
            self.db.execute("UPDATE jobs SET state='running',fence=?,deadline=?,lease=?,reserve=? WHERE task=?", (fence, deadline, min(now+self.LEASE_SECONDS, deadline), bound, task))
            return fence

    def running(self, task, fence, now):
        self.live(now)
        row = self.db.execute("SELECT * FROM jobs WHERE task=?", (task,)).fetchone()
        if (row is None or row['state'] != 'running' or row['fence'] != fence
                or now >= row['lease'] or now >= row['deadline']):
            raise Denied("expired or fenced worker")
        return row

    def heartbeat(self, task, fence, now):
        with self.transaction():
            row = self.running(task, fence, now)
            self.db.execute("UPDATE jobs SET lease=? WHERE task=?", (min(now+self.LEASE_SECONDS, row['deadline']), task))

    def request_ticket(self, task, fence, now, *, runtime_digest):
        """Burn one simulated request slot before hypothetical IO, including retries."""
        with self.transaction():
            row = self.running(task, fence, now)
            self.evidence(now)
            expected = self.db.execute("SELECT runtime FROM control").fetchone()[0]
            if runtime_digest != expected or row['calls'] >= self.CALLS:
                raise Denied("runtime mismatch or request bound")
            if self.db.execute("SELECT 1 FROM requests WHERE state='pending'").fetchone():
                raise Denied("in-flight or uncertain request requires reconciliation")
            self.db.execute("UPDATE jobs SET calls=calls+1 WHERE task=?", (task,))
            ticket = (task, fence, row['calls']+1)
            self.db.execute("INSERT INTO requests VALUES(?,?,?,'pending')", ticket)
            return ticket

    def record_response(self, ticket):
        """Trusted fixture broker only. Known response never refunds exposure."""
        with self.transaction():
            changed = self.db.execute("UPDATE requests SET state='responded' WHERE task=? AND fence=? AND sequence=? AND state='pending'", ticket).rowcount
            if changed != 1:
                raise Denied("unknown or duplicate response")

    def complete(self, task, fence, now):
        with self.transaction():
            self.running(task, fence, now)
            if self.db.execute("SELECT 1 FROM requests WHERE task=? AND state='pending'", (task,)).fetchone():
                raise Denied("uncertain request cannot complete")
            self.db.execute("UPDATE jobs SET state='awaiting_review' WHERE task=?", (task,))
            # Never release reservation on success or failure; no settlement API.

    def watchdog(self, now):
        with self.transaction():
            self.clock(now)
            count = self.db.execute("UPDATE jobs SET state='uncertain',fence=fence+1 WHERE state='running' AND (lease<=? OR deadline<=?)", (now, now)).rowcount
            if count:
                self.db.execute("UPDATE control SET stopped=1")
            return count

    def stop(self):
        with self.transaction():
            self.db.execute("UPDATE control SET stopped=1")
            self.db.execute("UPDATE jobs SET state='uncertain',fence=fence+1 WHERE state='running'")
            # Intentionally no automatic resume, reclaim, refund or requeue.
