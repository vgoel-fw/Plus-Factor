"""Deterministic local rules so the app works with no account and no network.
Uncalibrated: returns no score, so its output can only ever be a proposed tag."""
import re

NAME = "offline-rules-1"
STOP = set("the a an of to in on for and or by at is was were be been that this with from as it its will".split())
NEG = r"\b(not|never|no|denied|denies|without|exempt|unverified|declined|refused)\b"


def _words(t):
    return {w for w in re.findall(r"[a-z0-9]+", (t or "").lower()) if w not in STOP and len(w) > 2}


def classify(state):
    text = " ".join(s["text"] for s in state["spans"])
    low, task = text.lower(), state["task"]
    if task == "passage_kind":
        if re.search(r"unrelated (lawsuit|case|action)|in another (case|action|lawsuit)|\bin re\b", low):
            label = "other_case"
        elif re.search(r"\b(plausib|pleading standard|must allege|the court held)", low):
            label = "legal_standard"
        else:
            label = "party_conduct" if len(low) > 30 else "insufficient_context"
    elif task == "date_role":
        label = "effective" if "effective" in low else "announcement" if re.search(r"^date:|announc", low, re.M) \
            else "transaction" if re.search(r"invoice|shipped|inv no", low) else "unresolved"
    elif task == "knowledge_basis":
        second = bool(re.search(r"heard from|was told by|a (former )?colleague|did not attend|does not know", low))
        first = bool(re.search(r"personally|told her|told me|she asked|i saw|by phone", low))
        label = "mixed" if first and second else "hearsay" if second else "firsthand" if first else "unknown"
    else:  # assertion_support
        a = state.get("assertion_text") or ""
        ov = len(_words(a) & _words(text)) / max(1, len(_words(a)))
        if re.search(r"unrelated (lawsuit|case)|in another (case|action)", low):
            label = "does_not_address"          # another matter's allegations are not this matter's evidence
        elif ov < 0.34:
            label = "does_not_address"
        elif re.search(r"implement|paid|charged|invoiced", a.lower()) and not re.search(r"invoice|paid|charged", low):
            label = "does_not_address"          # an announcement does not show implementation
        elif bool(re.search(NEG, low)) != bool(re.search(NEG, a.lower())):
            label = "contradicts"               # a negated statement is not an affirmative fact
        else:
            label = "supports"
    return {"label": label, "score": None, "model": NAME}
