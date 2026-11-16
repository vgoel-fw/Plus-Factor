"""Common-cause register (kept beside the conduct, see conduct.add_explanation)."""
from . import entities
from .conduct import add_explanation  # noqa: F401

KINDS = ["raw_material", "energy_freight", "tariff_regulatory", "supply_outage", "demand_shock",
         "contract_escalation", "negotiation_cycle", "public_competitor_announcement", "mix_change"]


def register(store, episode_id):
    ep = store.get(episode_id)
    nm = entities.names(store, ep["matter_id"])
    out = []
    for x in store.list("explanation", ep["matter_id"]):
        if x["episode_id"] != episode_id:
            continue
        doc = [nm.get(a["entity_id"], a["entity_id"]) for a in x["affected"] if a["status"] == "documented"]
        miss = [nm.get(a["entity_id"], a["entity_id"]) for a in x["affected"] if a["status"] != "documented"]
        out.append({**x, "reach_text": (f"Documented for {', '.join(doc)}. " if doc else "Not documented for any firm. ")
                    + (f"Equivalent support has not been supplied for {', '.join(miss)}." if miss else "")})
    return out
