"""Adapter for the built-in Jev-style engine (app/jev). Local: nothing leaves the machine."""
from .. import jev

NAME = "Plus Factor Jev (built-in, local)"
EXTERNAL = False


def available():
    return True


def classify(state):
    # The passage itself is classified; surrounding context goes in only when the span is a fragment (under four words),
    # so a neighbouring sentence cannot drown out the passage being asked about.
    passages = [s["text"] if len(s["text"].split()) >= 4 else s["context"] for s in state["spans"]]
    res = jev.system_one({"passages": passages, "assertion": state.get("assertion_text")},
                         {state["task"]: jev.Choice(state["prompt"], {l: None for l in state["labels"]})})
    a = res["choices"][state["task"]]
    return {"label": a["choice"], "score": a["confidence"], "scores": a["probabilities"], "model": NAME}
