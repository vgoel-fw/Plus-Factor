"""Built-in Jev-style engine. Pure Python, no download, no account, runs on the user's machine.

Mirrors the shape of TypeSafe's Jev API and the jev-tools split (github.com/CMaintz/jev-tools,
MIT, commit 43cbece): a `state` plus named typed `Choice` questions go in; each answer comes back
as {choice, confidence, probabilities}. Routing on confidence stays in decisions/policy.py.

The model is a multinomial naive Bayes classifier per question, trained at start-up on the
labelled examples in data/jev/<question>.jsonl. Features are words, bigrams and a handful of
legal-evidence markers (negation, secondhand knowledge, references to another lawsuit,
announcement-versus-implementation). It is small and transparent: run
scripts/evaluate_decisions.py for leave-one-out accuracy and Brier score. Probabilities are not
calibrated on attorney-labelled matters; the 0.8 gate in policy.py is the safeguard."""
import json, math, pathlib, re
from dataclasses import dataclass, field

DATA = pathlib.Path(__file__).resolve().parents[2] / "data" / "jev"
STOP = set("the a an of to in on for and or by at is was were be been that this with from as it its will "
           "their there they he she his her we our you your i me my".split())
MARKERS = [
    ("NEG", r"\b(not|never|no|denied|denies|without|exempt|declined|refused|did not|has not|does not)\b"),
    ("HEARD", r"heard from|was told by|according to a|a (former )?colleague|rumou?r|did not attend|does not know who"),
    ("FIRST", r"\b(personally|told (her|me|him)|i saw|she saw|he saw|saw the|by phone|in person|attended|asked|myself|herself|himself|reviewed|received|was on the call|on the call)\b"),
    ("OTHERCASE", r"unrelated (lawsuit|case|action|litigation)|in another (case|action|lawsuit)|\bin re\b|\bv\.\s"),
    ("STANDARD", r"plausib|pleading|must allege|rule 12|the court held|standard|section 1 claim|motion to dismiss"),
    ("EFFECTIVE", r"\beffective\b|takes effect|will apply from|beginning on"),
    ("ANNOUNCE", r"^date:|announc|letter dated|notified|press release|we wrote"),
    ("TXN", r"invoice|shipped|purchase order|\bpo\b|inv no|paid|billed|delivered"),
    ("QUOTE", r"[\"“].{6,}[\"”]"),
    ("DATE", r"(january|february|march|april|may|june|july|august|september|october|november|december) \d{1,2}|\d{4}-\d{2}-\d{2}"),
]


@dataclass
class Choice:
    instructions: str
    criteria: dict = field(default_factory=dict)


def _tokens(text):
    low = (text or "").lower()
    words = [w for w in re.findall(r"[a-z][a-z0-9']+", low) if w not in STOP]
    toks = words + [a + "_" + b for a, b in zip(words, words[1:])]
    return toks + [name for name, rx in MARKERS if re.search(rx, low, re.M)] * 3  # markers weigh more


SYN = {"incr": r"rais|rise|rose|increas|hike|went up|going up|up \d", "bill": r"charg|bill|invoic|collect|paid",
       "talk": r"discuss|spoke|speak|communicat|talk|call", "attend": r"attend|appear|panel|present at",
       "exempt": r"exempt|except|excluded|carve", "price": r"price|pricing|list price|surcharge"}


def _norm(text):
    low = text.lower()
    for k, rx in SYN.items():
        low = re.sub(rx + r"\w*", " " + k.upper() + " ", low)
    return {w[:5] for w in re.findall(r"[a-zA-Z0-9]+", low) if w.lower() not in STOP and len(w) > 2}


def _pair_tokens(passage, assertion):
    """assertion_support uses relational features only, so it generalizes beyond the training words."""
    p, a = (passage or "").lower(), (assertion or "").lower()
    pw, aw = _norm(p), _norm(a)
    ov = len(pw & aw) / max(1, len(aw))
    neg = MARKERS[0][1]
    qual = bool(re.search(r"\bbut\b|\bhowever\b|\bexcept|exempt|exceptions|not repriced|kept prices flat for", p))
    negmis = bool(re.search(neg, p)) != bool(re.search(neg, a))
    t = ["OVL_" + ("hi" if ov >= .5 else "mid" if ov >= .25 else "lo")]
    if negmis and not qual:
        t += ["NEG_MISMATCH"] * 2
    if qual and ov >= .25:
        t += ["QUALIFIED_OVERLAP"] * 2
    if re.search(r"all customers|across the board|without exception|every customer", a) and qual:
        t += ["UNIVERSAL_VS_EXCEPTION"] * 2
    if re.search(r"implement|paid|charg|invoic|collect", a) and not re.search(MARKERS[7][1], p):
        t += ["IMPL_NO_TXN"] * 3
    if re.search(MARKERS[3][1], p):
        t += ["OTHERCASE"] * 3
    if len([w for w in re.findall(r"[a-z]+", p) if w not in STOP]) < 3:
        t += ["SHORT"] * 3
    if not negmis and not qual and ov >= .5:
        t.append("CLEAN_MATCH")
    return t


class _NB:
    def __init__(self, rows, labels):
        self.labels = labels
        self.prior = {l: 1.0 for l in labels}
        self.counts = {l: {} for l in labels}
        self.total = {l: 0 for l in labels}
        vocab = set()
        for toks, y in rows:
            self.prior[y] += 1
            for t in toks:
                self.counts[y][t] = self.counts[y].get(t, 0) + 1
                self.total[y] += 1
                vocab.add(t)
        self.v = max(1, len(vocab))
        n = sum(self.prior.values())
        self.prior = {l: math.log(c / n) for l, c in self.prior.items()}

    def predict(self, toks):
        known = [t for t in toks if any(t in c for c in self.counts.values())]
        if not known:
            return {l: 1 / len(self.labels) for l in self.labels}
        s = {l: self.prior[l] + sum(math.log((self.counts[l].get(t, 0) + 1) / (self.total[l] + self.v)) for t in known)
             for l in self.labels}
        temp = max(1.0, math.sqrt(len(known)))  # tame naive Bayes overconfidence on long passages
        m = max(s.values())
        e = {l: math.exp((v - m) / temp) for l, v in s.items()}
        z = sum(e.values())
        return {l: e[l] / z for l in self.labels}


_MODELS = {}


def examples(task):
    return [json.loads(l) for l in (DATA / f"{task}.jsonl").read_text().splitlines() if l.strip()]


def _feats(task, ex):
    if task == "assertion_support":
        return _pair_tokens(ex["t"], ex.get("a"))
    toks, low = _tokens(ex["t"]), (ex["t"] or "").lower()
    has = {n for n, rx in MARKERS if re.search(rx, low, re.M)}
    if len([w for w in re.findall(r"[a-z]+", low) if w not in STOP]) < 3:
        toks += ["SHORT"] * 6
    if task == "knowledge_basis":  # the basis question turns on who perceived what, so markers dominate
        toks += [("BOTH" if {"FIRST", "HEARD"} <= has else "FIRST_ONLY" if "FIRST" in has
                  else "HEARD_ONLY" if "HEARD" in has else "NO_BASIS")] * 8
    if task == "date_role" and not has & {"DATE", "EFFECTIVE", "ANNOUNCE", "TXN"}:
        toks += ["VAGUE_DATE"] * 6
    return toks


def train(task, labels, rows=None):
    rows = examples(task) if rows is None else rows
    return _NB([(_feats(task, r), r["y"]) for r in rows], labels)


def system_one(state, questions):
    """Jev-shaped call. state: {"passages": [...], "assertion": optional}. Returns {"choices": {...}}."""
    text = "\n".join(state.get("passages", []))
    out = {}
    for name, q in questions.items():
        labels = list(q.criteria)
        if name not in _MODELS:
            _MODELS[name] = train(name, labels)
        probs = _MODELS[name].predict(_feats(name, {"t": text, "a": state.get("assertion")}))
        best = max(probs, key=probs.get)
        out[name] = {"choice": best, "confidence": round(probs[best], 4),
                     "probabilities": {k: round(v, 4) for k, v in probs.items()}}
    return {"choices": out}
