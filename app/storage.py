"""SQLite persistence. Sources, spans and transactions are typed tables; every other
analytical object is a revisioned JSON document in `objects`. All reviewed mutations
go through `update`, which enforces optimistic concurrency and writes a ReviewAction."""
import json, sqlite3, threading
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS objects(id TEXT PRIMARY KEY, kind TEXT, matter_id TEXT, rev INTEGER,
  data TEXT, created TEXT, updated TEXT);
CREATE INDEX IF NOT EXISTS ix_obj ON objects(kind, matter_id);
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, matter_id TEXT, sha256 TEXT, filename TEXT, kind TEXT,
  meta TEXT, confidentiality TEXT, privilege TEXT, record TEXT, dup_group TEXT, origin_group TEXT,
  disabled INTEGER DEFAULT 0, reviewed INTEGER DEFAULT 0, text TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS spans(id TEXT PRIMARY KEY, source_id TEXT, locator TEXT, start INTEGER, end INTEGER,
  text TEXT, checksum TEXT, extraction TEXT);
CREATE TABLE IF NOT EXISTS transactions(id TEXT PRIMARY KEY, matter_id TEXT, source_id TEXT, span_id TEXT,
  original TEXT, norm TEXT);
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT, matter_id TEXT, target TEXT, kind TEXT,
  action TEXT, old TEXT, new TEXT, reviewer TEXT, reason TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS counters(prefix TEXT PRIMARY KEY, n INTEGER);
"""
PREFIX = {"matter": "m", "entity": "ent", "relation": "rel", "market": "mkt", "market_version": "mv",
          "substitution": "sub", "event": "ev", "episode": "ep", "explanation": "ex", "agreement_item": "ag",
          "allegation": "a", "issue": "iss", "decision_run": "run", "export": "exp", "import": "imp",
          "job": "job"}


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


class Invalid(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.db.executescript(SCHEMA)

    def q(self, sql, args=()):
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def new_id(self, prefix):
        with self.lock:
            self.db.execute("INSERT INTO counters VALUES(?,1) ON CONFLICT(prefix) DO UPDATE SET n=n+1", (prefix,))
            n = self.db.execute("SELECT n FROM counters WHERE prefix=?", (prefix,)).fetchone()[0]
        return f"{prefix}-{n:04d}"

    # ---- revisioned objects -------------------------------------------------
    @staticmethod
    def _obj(r):
        return {**json.loads(r["data"]), "id": r["id"], "kind": r["kind"], "matter_id": r["matter_id"],
                "rev": r["rev"], "created": r["created"], "updated": r["updated"]}

    def put(self, kind, data, matter_id=None, reviewer="system"):
        oid = self.new_id(PREFIX.get(kind, kind[:3]))
        t = now()
        self.q("INSERT INTO objects VALUES(?,?,?,?,?,?,?)",
               (oid, kind, matter_id or oid, 1, json.dumps(data), t, t))
        self.log(matter_id or oid, oid, kind, "create", None, None, reviewer, None)
        return self.get(oid)

    def get(self, oid):
        r = self.q("SELECT * FROM objects WHERE id=?", (oid,))
        if not r:
            raise NotFound(oid)
        return self._obj(r[0])

    def list(self, kind, matter_id=None):
        rows = self.q("SELECT * FROM objects WHERE kind=? AND (? IS NULL OR matter_id=?) ORDER BY id", (kind, matter_id, matter_id))
        return [self._obj(r) for r in rows]

    def update(self, oid, patch, expected_rev=None, reviewer="system", reason=None, action="edit"):
        """expected_rev is mandatory for user edits (server enforces); None is system-only."""
        with self.lock:
            cur = self.get(oid)
            if expected_rev is not None and int(expected_rev) != cur["rev"]:
                raise Conflict(f"{oid} is at revision {cur['rev']}, edit was based on {expected_rev}")
            meta = ("id", "kind", "matter_id", "rev", "created", "updated")
            data = {k: v for k, v in cur.items() if k not in meta}
            old = {k: data.get(k) for k in patch if data.get(k) != patch[k]}
            if not old and action == "edit":
                return cur
            data.update(patch)
            self.q("UPDATE objects SET data=?, rev=rev+1, updated=? WHERE id=?", (json.dumps(data), now(), oid))
            self.log(cur["matter_id"], oid, cur["kind"], action, old, {k: patch[k] for k in old}, reviewer, reason)
            return self.get(oid)

    def log(self, matter_id, target, kind, action, old, new, reviewer, reason):
        self.q("INSERT INTO reviews(matter_id,target,kind,action,old,new,reviewer,reason,ts) VALUES(?,?,?,?,?,?,?,?,?)",
               (matter_id, target, kind, action, json.dumps(old), json.dumps(new), reviewer, reason, now()))

    def reviews(self, matter_id, target=None):
        rows = self.q("SELECT * FROM reviews WHERE matter_id=? AND (? IS NULL OR target=?) ORDER BY id",
                      (matter_id, target, target))
        return [{**dict(r), "old": json.loads(r["old"]), "new": json.loads(r["new"])} for r in rows]

    # ---- immutable sources, spans, transactions -----------------------------
    @staticmethod
    def _src(r, text=False):
        d = dict(r)
        d["meta"] = json.loads(d["meta"] or "{}")
        if not text:
            d.pop("text")
        return d

    def source(self, sid, text=True):
        r = self.q("SELECT * FROM sources WHERE id=?", (sid,))
        if not r:
            raise NotFound(sid)
        return self._src(r[0], text)

    def sources(self, matter_id, text=False):
        return [self._src(r, text) for r in self.q("SELECT * FROM sources WHERE matter_id=? ORDER BY id", (matter_id,))]

    def span(self, span_id):
        r = self.q("SELECT * FROM spans WHERE id=?", (span_id,))
        if not r:
            raise NotFound(span_id)
        return dict(r[0])

    def spans_of(self, source_id):
        return [dict(r) for r in self.q("SELECT * FROM spans WHERE source_id=? ORDER BY start", (source_id,))]

    def txns(self, matter_id):
        return [{"id": r["id"], "source_id": r["source_id"], "span_id": r["span_id"],
                 "original": json.loads(r["original"]), "norm": json.loads(r["norm"])}
                for r in self.q("SELECT * FROM transactions WHERE matter_id=? ORDER BY id", (matter_id,))]
