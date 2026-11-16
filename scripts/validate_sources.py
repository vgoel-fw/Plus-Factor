"""Integrity check: every span in a database still matches its source, and every stored
authority excerpt file is flagged if unverified. Usage: validate_sources.py [db path]"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.storage import Store
from app import provenance as prov, precedent

s = Store(sys.argv[1] if len(sys.argv) > 1 else "plusfactor.db")
bad = 0
for r in s.q("SELECT id FROM spans"):
    v = prov.verify_span(s, r["id"])
    if not v["ok"]:
        bad += 1
        print(f"FAIL {r['id']}: {v['reason']}")
print(f"{len(s.q('SELECT id FROM spans'))} spans checked, {bad} failed")
for a in precedent.load():
    t = precedent.excerpts(a["id"])
    print(f"{a['id']}: " + ("no stored text" if not t else "excerpts UNVERIFIED against official text" if "UNVERIFIED" in t else "verified"))
sys.exit(1 if bad else 0)
