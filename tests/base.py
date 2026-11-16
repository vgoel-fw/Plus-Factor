"""Shared fixture: the SYNTHETIC demonstration matter in an in-memory database."""
import unittest
from app.storage import Store
from app import seed


class Base(unittest.TestCase):
    def setUp(self):
        self.s = Store()
        self.m = seed.load(self.s)
        self.mid = self.m["id"]
        self.ent = {e["legal_name"].split()[0].lower() + ("_h" if "Holdings" in e["legal_name"] else ""): e["id"]
                    for e in self.s.list("entity", self.mid)}
        self.ep = self.s.list("episode", self.mid)[0]
        self.al = {a["act"]: a for a in self.s.list("allegation", self.mid)}

    def tearDown(self):
        self.s.db.close()

    def src(self, part):
        return next(x for x in self.s.sources(self.mid) if part in x["filename"])

    def row(self, act, who):
        a = self.s.get(self.al[act]["id"])
        return next(r for r in a["verification"]["rows"] if r["defendant"] == self.ent[who])
