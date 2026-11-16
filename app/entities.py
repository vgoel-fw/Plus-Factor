"""Legal entities stay separate until counsel approves a mapping. A trade name, brand,
parent or distributor never silently resolves to a defendant."""
from .storage import Invalid


def add_entity(store, matter_id, legal_name, role="supplier", defendant=False, aliases=()):
    return store.put("entity", {"legal_name": legal_name, "role": role, "defendant": defendant,
                                "aliases": [{"name": a, "status": "proposed", "basis": None} for a in aliases]},
                     matter_id)


def approve_alias(store, entity_id, alias, basis, reviewer, expected_rev):
    if not basis:
        raise Invalid("an alias mapping needs a stated basis")
    e = store.get(entity_id)
    al = [dict(a, status="approved", basis=basis) if a["name"] == alias else a for a in e["aliases"]]
    return store.update(entity_id, {"aliases": al}, expected_rev, reviewer, basis, "approve_mapping")


def resolve(store, matter_id, name):
    """Exact legal name or an approved alias only. Returns (entity_id|None, proposed_candidates)."""
    n = name.strip().lower()
    cands = []
    for e in store.list("entity", matter_id):
        if e["legal_name"].lower() == n:
            return e["id"], []
        for a in e["aliases"]:
            if a["name"].lower() == n:
                if a["status"] == "approved":
                    return e["id"], []
                cands.append(e["id"])
    return None, cands


def add_relation(store, matter_id, parent, child, rtype, date_from=None, date_to=None):
    return store.put("relation", {"parent": parent, "child": child, "type": rtype, "from": date_from,
                                  "to": date_to, "attribution": "none", "basis": None}, matter_id)


def validate_relation_patch(patch):
    if patch.get("attribution") == "approved" and not patch.get("basis"):
        raise Invalid("attributing an affiliate's conduct requires a stated participation basis; "
                      "a corporate relationship alone is not one")


def attributable(store, matter_id, entity_id):
    """Entities whose conduct counsel has approved attributing to `entity_id` (itself included)."""
    out = {entity_id}
    for r in store.list("relation", matter_id):
        if r["parent"] == entity_id and r["attribution"] == "approved":
            out.add(r["child"])
    return out


def names(store, matter_id):
    return {e["id"]: e["legal_name"] for e in store.list("entity", matter_id)}
