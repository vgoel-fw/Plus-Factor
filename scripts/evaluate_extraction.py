"""Letter-extraction check against the synthetic fixtures' known answers."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.storage import Store
from app import seed, entities

WANT = {("Arden Chemical Co.", "announcement"): "2024-02-12", ("Bexley Ingredients LLC", "announcement"): "2024-02-20",
        ("Corvane Acidulants Inc.", "announcement"): "2024-03-04", ("Arden Chemical Co.", "effective"): "2024-04-01",
        ("Bexley Ingredients LLC", "effective"): "2024-04-01", ("Corvane Acidulants Inc.", "effective"): "2024-04-01"}
s = Store()
mid = seed.load(s)["id"]
nm = entities.names(s, mid)
got = {(nm.get(e["actor"]), e["type"]): e["date_start"] for e in s.list("event", mid) if e.get("extraction")}
tp = sum(1 for k, v in WANT.items() if got.get(k) == v)
print(f"n={len(WANT)} expected events; extracted={len(got)}; correct={tp}; "
      f"precision={tp / max(1, len(got)):.2f} recall={tp / len(WANT):.2f}; "
      f"date-role or attribution errors={len(got) - tp}; promoted to implementation=0 (by construction)")
