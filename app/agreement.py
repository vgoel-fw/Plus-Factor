"""Agreement workspace: evidentiary questions per episode, not a plus-factor count."""
from . import entities, provenance as prov
from .storage import Invalid

CATEGORIES = ["future_pricing_communication", "alleged_assurance", "monitoring_or_retaliation",
              "abrupt_change_after_contact", "contrary_to_unilateral_interest", "association_contact",
              "public_signaling", "other"]
# Each rung is a different proposition; evidence for one is not evidence for the next.
LADDER = ["membership", "possible_attendance", "documented_attendance", "relevant_discussion",
          "alleged_commitment", "subsequent_conduct"]
HOW = ["original_document", "witness_firsthand", "witness_secondhand", "witness_mixed", "witness_unknown_basis",
       "allegation", "inference"]
TENSE = ["future", "historical", "unknown"]


def add_item(store, matter_id, d):
    if d.get("category") not in CATEGORIES:
        raise Invalid(f"category must be one of {CATEGORIES}")
    if d.get("how_known") not in HOW:
        raise Invalid(f"how_known must be one of {HOW}")
    if d["category"] == "contrary_to_unilateral_interest":
        for k in ("independent_strategy", "commercial_facts", "assumptions"):
            if not d.get(k):
                raise Invalid(f"'contrary to unilateral interest' requires counsel to state {k.replace('_', ' ')}; "
                              "it cannot be inferred from a price increase or a sales decline")
    if d["category"] == "association_contact":
        for a in d.get("actors", []):
            if a.get("ladder") not in LADDER:
                raise Invalid(f"each association actor needs a ladder stage from {LADDER}")
    for k in ("actors", "span_ids", "contra_span_ids", "missing", "cuts_other_way"):
        d.setdefault(k, [])
    d.setdefault("information_tense", "unknown")
    d.setdefault("status", "proposed")
    return store.put("agreement_item", d, matter_id)


def matrix(store, episode_id):
    ep = store.get(episode_id)
    nm = entities.names(store, ep["matter_id"])
    rows = []
    for it in store.list("agreement_item", ep["matter_id"]):
        if it["episode_id"] != episode_id:
            continue
        live = [s for s in it["span_ids"] if not prov.usable(store, s)]
        rows.append({**it, "actor_names": [
            {**a, "name": nm.get(a["entity_id"], a["entity_id"])} for a in it["actors"]],
            "usable_spans": live, "independent_origins": len(prov.origins(store, live)),
            "documents": len({store.span(s)["source_id"] for s in live}),
            "unusable": [{"span_id": s, "reason": r} for s in it["span_ids"] if (r := prov.usable(store, s))]})
    return rows
