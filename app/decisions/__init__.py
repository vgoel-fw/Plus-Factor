"""Decision runner: state -> (permission check) -> adapter -> pure policy -> DecisionRun."""
import json, pathlib
from . import state as st, policy, offline_adapter, jev_adapter
from .. import provenance as prov

THRESHOLDS = pathlib.Path(__file__).resolve().parents[2] / "data" / "taxonomies" / "decision_thresholds.json"


def thresholds():
    return {k: v for k, v in json.loads(THRESHOLDS.read_text()).items() if k != "note"}


def preview(store, req):
    """Exactly what would leave the machine if an external provider were used."""
    s = st.build(store, req)
    return {"excerpts": [{k: x[k] for k in ("span_id", "filename", "locator", "context", "document_header",
                                             "confidentiality", "privilege")} for x in s["spans"]],
            "assertion_text": s["assertion_text"], "blockers": s["blockers"]}


def run(store, matter_id, req, adapter=jev_adapter):
    s = st.build(store, req)
    h = st.input_hash(s)
    name = adapter.NAME
    for old in store.list("decision_run", matter_id):  # replay
        if old["input_hash"] == h and old["adapter"] == name and not old.get("invalidated") and not old.get("error"):
            return {**old, "replayed": True}
    resp = None
    if not s["blockers"]:
        m = store.get(matter_id)
        if getattr(adapter, "EXTERNAL", False) and not _external_ok(m, s):
            resp = {"error": "external provider not permitted for this matter or these excerpts"}
        else:
            try:
                resp = adapter.classify(s)
            except Exception as e:  # timeout, network, SDK error: never an approval
                resp = {"error": f"{type(e).__name__}: {e}"}
    route = policy.decide(s, resp, thresholds())
    return store.put("decision_run", {
        "task": s["task"], "question_version": s["question_version"], "adapter": name,
        "model": (resp or {}).get("model"), "input_hash": h, "span_ids": req.get("source_span_ids", []),
        "assertion_id": s["assertion_id"], "label": (resp or {}).get("label"), "score": (resp or {}).get("score"), "scores": (resp or {}).get("scores"),
        "error": (resp or {}).get("error"), "omitted_context": s["omitted_context"], **route}, matter_id)


def _external_ok(matter, s):
    if matter.get("provider_permission") != "external_allowed":
        return False
    cap = prov.CONF.index(matter.get("external_max_confidentiality", "public"))
    return all(prov.CONF.index(x["confidentiality"]) <= cap and x["privilege"] == "none" for x in s["spans"])
