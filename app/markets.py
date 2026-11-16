"""Competing market hypotheses as reviewable versions. A market starts from the
purchaser's requirement; supplier identity is never a transaction-inclusion rule."""
from . import transactions as tx
from .storage import Invalid

RULE_KEYS = {"requirement", "families", "grades", "origins", "regions", "customer_group", "channel", "date_from",
             "date_to", "candidate_suppliers", "potential_substitutes"}
SUB_CONDITIONS = ["technically_usable", "commercially_available", "qualified_for_application",
                  "sufficient_volume", "economically_attractive", "purchased_after_price_change"]


def check_rules(rules):
    extra = set(rules) - RULE_KEYS
    if extra:
        raise Invalid(f"unknown market rule(s): {sorted(extra)}. Markets are defined by product, place, customer "
                      "and time, not by who the defendants are.")
    if not (rules.get("requirement") or "").strip():
        raise Invalid("state the purchaser requirement this market starts from (it may be provisional)")


def live_txns(store, matter_id):
    off = {s["id"] for s in store.sources(matter_id) if s["disabled"]}
    return [t for t in store.txns(matter_id) if t["source_id"] not in off]


def versions(store, market_id):
    return [v for v in store.list("market_version") if v["market_id"] == market_id]


def create_market(store, matter_id, name, rules, rationale, reviewer, boundaries=()):
    check_rules(rules)
    m = store.put("market", {"name": name, "current_version": None}, matter_id, reviewer)
    return add_version(store, m["id"], rules, rationale, reviewer, m["rev"], list(boundaries))


def add_version(store, market_id, rules, rationale, reviewer, expected_rev, boundaries=None):
    check_rules(rules)
    m = store.get(market_id)
    prior = versions(store, market_id)
    if boundaries is None:
        boundaries = prior[-1]["boundaries"] if prior else []
    v = store.put("market_version", {"market_id": market_id, "name": m["name"], "n": len(prior) + 1, "rules": rules,
                                     "boundaries": boundaries, "rationale": rationale, "status": "draft",
                                     "reviewer": reviewer, "superseded": False}, m["matter_id"], reviewer)
    store.update(market_id, {"current_version": v["id"]}, expected_rev, reviewer, rationale, "new_version")
    for p in prior:
        if not p["superseded"]:
            store.update(p["id"], {"superseded": True, "superseded_by": v["id"]}, None, reviewer,
                         f"superseded by {v['id']}", "supersede")
    return v


def key(n):
    return n.get("entity_id") or "unmapped:" + n["vendor"]


def summary(store, matter_id, rules):
    """Descriptive only. Shares are shares of *this purchaser's observed purchases*; they are
    usable as market concentration only if the record covers the market, which it rarely does."""
    by = {}
    for t in live_txns(store, matter_id):
        n = t["norm"]
        if tx.in_market(n, rules):
            s = by.setdefault(key(n), {"lines": 0, "lb": 0.0, "first": n["date"], "last": n["date"]})
            s["lines"] += 1
            s["lb"] += n["qty_lb"] or 0
            s["first"], s["last"] = min(s["first"], n["date"]), max(s["last"], n["date"])
    total = sum(s["lb"] for s in by.values()) or 1
    for s in by.values():
        s["share"] = round(s["lb"] / total, 4)
        s["lb"] = round(s["lb"])
    cands = set(rules.get("candidate_suppliers") or [])
    no_rec = sorted(cands - set(by))
    return {"transactions": sum(s["lines"] for s in by.values()), "suppliers": by,
            "candidates_without_records": no_rec,
            "purchase_hhi": round(sum((s["share"] * 100) ** 2 for s in by.values())),
            "concentration_usable": False,
            "concentration_note": "Purchase shares of one purchaser's record"
            + (f"; {len(no_rec)} candidate supplier(s) have no records" if no_rec else "")
            + ". Not a market-share or HHI finding."}


def impact(store, version_id, proposed):
    """Preview what a boundary change does before it is saved."""
    from . import conduct, allegations
    check_rules(proposed)
    v = store.get(version_id)
    mid = v["matter_id"]
    live = live_txns(store, mid)
    cur = {t["id"] for t in live if tx.in_market(t["norm"], v["rules"])}
    new = {t["id"] for t in live if tx.in_market(t["norm"], proposed)}
    sup = lambda ids: {key(t["norm"]) for t in live if t["id"] in ids}
    events = [e for e in store.list("event", mid) if e["status"] != "rejected"]
    ev_cur = {e["id"] for e in events if conduct.applies(e, v["rules"])}
    ev_new = {e["id"] for e in events if conduct.applies(e, proposed)}
    eps = []
    for ep in store.list("episode", mid):
        if ep["market_version_id"] != version_id:
            continue
        a, b = conduct.analyze(store, ep["id"], persist=False), conduct.analyze(store, ep["id"], proposed, False)
        moved = lambda r: {k: l["implementation"]["status"] for k, l in r["lanes"].items()}
        eps.append({"episode_id": ep["id"], "question": ep["question"],
                    "before": {"denominator": a["denominator"], "statuses": moved(a)},
                    "after": {"denominator": b["denominator"], "statuses": moved(b),
                              "strongest_exception": b["exceptions"][:1]},
                    "synchronization_persists": not any(
                        l["implementation"]["status"] == "not_observed" and k not in a["lanes"]
                        for k, l in b["lanes"].items())})
    stale = [a["id"] for a in store.list("allegation", mid)
             if a.get("market_version_id") == version_id or a.get("episode_id") in {e["episode_id"] for e in eps}]
    intro = sorted(sup(new) - sup(cur))
    differ = [k for e in eps for k, s in e["after"]["statuses"].items() if k in intro and s == "not_observed"]
    names = __import__("app.entities", fromlist=["names"]).names(store, mid)
    nm = lambda k: names.get(k, k.replace("unmapped:", ""))
    text = (f"{len(new - cur)} transaction(s) added, {len(cur - new)} removed. "
            + (f"Introduces {len(intro)} supplier(s): {', '.join(map(nm, intro))}"
               + (f"; {len(set(differ))} did not follow the observed price movement. " if differ else ". ")
               if intro else "")
            + f"{len(stale)} draft allegation(s) and {len(eps)} episode(s) would require review.")
    return {"version_id": version_id, "transactions_added": len(new - cur), "transactions_removed": len(cur - new),
            "suppliers_introduced": [nm(k) for k in intro], "suppliers_removed": [nm(k) for k in sorted(sup(cur) - sup(new))],
            "events_added": sorted(ev_new - ev_cur), "events_removed": sorted(ev_cur - ev_new), "episodes": eps,
            "concentration_before": summary(store, mid, v["rules"])["purchase_hhi"],
            "concentration_after": summary(store, mid, proposed)["purchase_hhi"],
            "concentration_usable": False, "stale_allegations": stale, "summary": text}


def add_substitution(store, matter_id, data):
    """Buyer B considered product C for application D in period E. Each condition is its own
    answer (yes / no / unknown); satisfying one says nothing about the others."""
    for c in SUB_CONDITIONS:
        if data.setdefault("conditions", {}).setdefault(c, "unknown") not in ("yes", "no", "partial", "unknown"):
            raise Invalid(f"{c} must be yes, no, partial or unknown")
    for k in ("buyer", "candidate_product", "application"):
        if not data.get(k):
            raise Invalid(f"substitution record needs {k}")
    return store.put("substitution", data, matter_id)
