"""Evidence-state construction: resolve approved span IDs to exact text plus the context
a qualification might live in. Nothing is truncated silently; omissions are recorded and
make the request ineligible for a decisive classification."""
from .. import provenance as prov
from .questions import QUESTIONS, VERSION
from ..storage import Invalid

CONTEXT_BUDGET = 4000


def build(store, req):
    q = QUESTIONS.get(req.get("task"))
    if not q:
        raise Invalid(f"unknown task {req.get('task')!r}")
    if req.get("allowed_labels") and list(req["allowed_labels"]) != q["labels"]:
        raise Invalid("allowed_labels must match the task's typed choices")
    blockers, spans, omitted = [], [], []
    for sid in req.get("source_span_ids", []):
        v = prov.verify_span(store, sid)
        if not v["ok"]:
            blockers.append(f"{sid}: {v['reason']}")
            continue
        why = prov.usable(store, sid)
        if why:
            blockers.append(f"{sid}: {why}")
            continue
        sp = store.span(sid)
        src = store.source(sp["source_id"])
        text = src["text"]
        ps = text.rfind("\n", 0, text.rfind("\n", 0, sp["start"]) if "\n" in text[:sp["start"]] else 0) + 1
        ne = text.find("\n", sp["end"])
        pe = text.find("\n", ne + 1) if ne >= 0 else -1
        ctx = text[ps:pe if pe >= 0 else len(text)]
        head = "\n".join(text.splitlines()[:5])  # speaker identity / document header
        if len(ctx) + len(head) > CONTEXT_BUDGET:
            omitted.append(f"{sid}: surrounding context exceeds budget; neighbors not sent")
            ctx = sp["text"]
        spans.append({"span_id": sid, "text": sp["text"], "context": ctx, "document_header": head,
                      "filename": src["filename"], "document_type": src["kind"], "locator": sp["locator"],
                      "confidentiality": src["confidentiality"], "privilege": src["privilege"]})
    if not req.get("source_span_ids"):
        blockers.append("no source spans supplied")
    return {"task": req["task"], "question_version": VERSION, "prompt": q["prompt"], "labels": q["labels"],
            "assertion_id": req.get("assertion_id"), "assertion_text": req.get("assertion_text"),
            "matter_version": req.get("matter_version"), "spans": spans, "blockers": blockers,
            "omitted_context": omitted,
            "context_complete": bool(req.get("context_complete")) and not omitted,
            "unresolved_attribution": bool(req.get("unresolved_attribution"))}


def input_hash(state):
    return prov.sha(prov.json.dumps(state, sort_keys=True))
