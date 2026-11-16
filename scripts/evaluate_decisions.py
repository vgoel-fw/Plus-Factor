"""Leave-one-out evaluation of the built-in Jev-style engine on data/jev/*.jsonl.
Prints n, accuracy, Brier score and every disagreement. Small hand-labelled set: this measures
the harness, not legal accuracy. Add attorney-labelled examples and re-run."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app import jev
from app.decisions.questions import QUESTIONS

for task, q in QUESTIONS.items():
    rows, ok, brier = jev.examples(task), 0, 0.0
    for i, r in enumerate(rows):
        p = jev.train(task, q["labels"], rows[:i] + rows[i + 1:]).predict(jev._feats(task, r))
        best = max(p, key=p.get)
        ok += best == r["y"]
        brier += sum((p[l] - (l == r["y"])) ** 2 for l in q["labels"])
        if best != r["y"]:
            print(f"  DISAGREE {task}: predicted {best}, labelled {r['y']}: {r['t'][:70]}")
    print(f"{task}: n={len(rows)} accuracy={ok}/{len(rows)} ({ok / len(rows):.0%}) brier={brier / len(rows):.3f}")
