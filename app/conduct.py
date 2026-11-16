"""Parallel-conduct reconstruction. Everything here is a transparent descriptive
calculation: dates, lags, matched-product price changes, coverage. None of it is an
agreement finding, and an empty lane is absence of an observed event, not proof of none."""
from datetime import date
from . import transactions as tx, provenance as prov, entities
from .markets import live_txns, key
from .storage import Invalid

EVENT_TYPES = ["decision", "announcement", "customer_receipt", "effective", "first_transaction", "reversal",
               "discount", "exception", "failed_implementation"]
IMPL_LABEL = {"observed": "Observed in matched transactions",
              "partial": "Observed with exceptions",
              "not_observed": "Transactions show no comparable change",
              "unverified": "Unverified: no matched pre/post transactions in the record",
              "no_transactions": "No transactions in the record"}


def add_event(store, matter_id, d):
    if d.get("type") not in EVENT_TYPES:
        raise Invalid(f"event type must be one of {EVENT_TYPES}")
    if d.get("date_text"):
        d["date_start"], d["date_end"], d["precision"] = prov.parse_date(d["date_text"])
    if not d.get("date_start"):
        raise Invalid("event needs a date or date interval")
    d.setdefault("date_end", d["date_start"])
    d.setdefault("precision", "day")
    d.setdefault("status", "proposed")
    d.setdefault("span_ids", [])
    d.setdefault("grades", [])
    return store.put("event", d, matter_id)


def applies(e, rules):
    fam, gr = rules.get("families") or [], rules.get("grades") or []
    return (not fam or not e.get("family") or e["family"] in fam) and \
           (not gr or not e.get("grades") or bool(set(gr) & set(e["grades"])))


def _months(a, b):
    y, m = int(a[:4]), int(a[5:7])
    out = []
    while f"{y}-{m:02d}" <= b[:7]:
        out.append(f"{y}-{m:02d}")
        y, m = y + (m == 12), m % 12 + 1
    return out


def implementation(lines, ref, pct, basis, thr):
    """Matched-product (SKU x ship-to) median price before vs after the reference date."""
    if not lines:
        return {"status": "no_transactions", "label": IMPL_LABEL["no_transactions"], "groups": []}
    pre = [n for n in lines if n["date"] < ref and prov.days(n["date"], ref) <= 183]
    post = [n for n in lines if n["date"] >= ref and prov.days(ref, n["date"]) <= 183]
    unpriced = sum(1 for n in pre + post if tx.price(n, basis) is None)
    groups = []
    for g in sorted({(n["sku"], n["region"]) for n in pre} & {(n["sku"], n["region"]) for n in post}):
        a = tx.med([tx.price(n, basis) for n in pre if (n["sku"], n["region"]) == g])
        b = tx.med([tx.price(n, basis) for n in post if (n["sku"], n["region"]) == g])
        if a and b:
            ch = round((b / a - 1) * 100, 2)
            groups.append({"sku": g[0], "ship_to": g[1], "pre_median": round(a, 4), "post_median": round(b, 4),
                           "change_pct": ch, "followed": pct is not None and ch >= thr * pct})
    if not groups:
        st = "unverified"
    else:
        f = sum(g["followed"] for g in groups)
        st = "observed" if f == len(groups) else "partial" if f else "not_observed"
    return {"status": st, "label": IMPL_LABEL[st], "groups": groups, "pre_lines": len(pre), "post_lines": len(post),
            "lines_without_price": unpriced, "announced_pct": pct, "reference_date": ref,
            "rule": f"a matched product 'follows' if its median unit price ({basis}) rises by at least "
                    f"{int(thr * 100)}% of the announced amount within 183 days"}


def _spread(evs):
    """Spread in days across actors as [min, max], honoring date uncertainty."""
    if len(evs) < 2:
        return None
    lo = max(0, prov.days(min(e["date_end"] for e in evs), max(e["date_start"] for e in evs)))
    hi = prov.days(min(e["date_start"] for e in evs), max(e["date_end"] for e in evs))
    return [lo, hi]


def signature(store, ep, rules):
    mid = ep["matter_id"]
    return prov.sha(prov.json.dumps([
        ep["market_version_id"], rules, ep.get("excluded"), ep.get("price_basis"), ep.get("threshold"),
        [(e["id"], e["rev"]) for e in store.list("event", mid)],
        [(e["id"], e["rev"]) for e in store.list("entity", mid)],
        [(s["id"], s["disabled"]) for s in store.sources(mid)], len(store.txns(mid))], sort_keys=True))[:16]


def analyze(store, ep_id, rules=None, persist=True):
    ep = store.get(ep_id)
    mid = ep["matter_id"]
    mv = store.get(ep["market_version_id"])
    rules = rules or mv["rules"]
    basis, thr = ep.get("price_basis", "gross"), ep.get("threshold", 0.5)
    nm = entities.names(store, mid)
    name = lambda k: nm.get(k, k.replace("unmapped:", "") + " (unmapped vendor)")
    txns = [t["norm"] for t in live_txns(store, mid) if tx.in_market(t["norm"], rules)]
    excluded = {x["event_id"]: x["reason"] for x in ep.get("excluded", [])}
    evs, dropped = [], []
    for e in store.list("event", mid):
        why = None
        if e["status"] == "rejected":
            continue
        if e["id"] in excluded:
            why = excluded[e["id"]]
        elif not applies(e, rules):
            why = "outside this market version's product scope"
        elif not e.get("actor"):
            why = "actor unresolved: entity mapping not approved"
        elif not e["span_ids"]:
            why = "no source span"
        else:
            why = next((r for s in e["span_ids"] if (r := prov.usable(store, s))), None)
        if not why and (e["date_end"] < ep["window_from"] or e["date_start"] > ep["window_to"]):
            why = "outside episode window"
        (dropped.append({"event_id": e["id"], "type": e["type"], "actor": name(e.get("actor") or "?"),
                         "reason": why}) if why else evs.append(e))
    eff = [e for e in evs if e["type"] == "effective"]
    modal = max({e["date_start"] for e in eff}, key=[e["date_start"] for e in eff].count) if eff else None
    pcts = [e["value"] for e in eff if e.get("value")]
    typical = tx.med(pcts)
    months = _months(ep["window_from"], ep["window_to"])
    lanes = {}
    for k in sorted({e["actor"] for e in evs} | {key(n) for n in txns} | set(rules.get("candidate_suppliers") or [])):
        mine = [e for e in evs if e["actor"] == k]
        lines = [n for n in txns if key(n) == k]
        own = next((e for e in mine if e["type"] == "effective"), None)
        ref = own["date_start"] if own else modal
        pct = (own or {}).get("value") or next((e["value"] for e in mine if e.get("value")), None) or typical
        impl = implementation(lines, ref, pct, basis, thr) if ref else \
            {"status": "unverified", "label": "No reference date in episode", "groups": []}
        have = {n["date"][:7] for n in lines}
        lanes[k] = {"name": name(k), "events": [{k2: e.get(k2) for k2 in (
            "id", "type", "date_start", "date_end", "precision", "value", "value_unit", "status", "span_ids",
            "date_basis", "note")} for e in sorted(mine, key=lambda e: e["date_start"])],
            "has_conduct_event": any(e["type"] in ("announcement", "effective") for e in mine),
            "implementation": impl, "transactions": len(lines),
            "coverage": {"months_with_invoices": len(have & set(months)), "months_in_window": len(months),
                         "gap_months": [m for m in months if m not in have] if lines else months},
            "records": "none supplied" if not lines and not mine else "partial" if not lines or not mine else "both"}
    lags = {t: _spread([e for e in evs if e["type"] == t]) for t in ("decision", "announcement", "effective")}
    with_ev = [k for k, l in lanes.items() if l["has_conduct_event"]]
    no_ev = [k for k, l in lanes.items() if not l["has_conduct_event"] and l["transactions"]]
    no_rec = [k for k, l in lanes.items() if l["records"] == "none supplied"]
    exceptions = []
    for k, l in lanes.items():
        im = l["implementation"]
        if k in no_ev and im["status"] == "not_observed":
            g = im["groups"][0]
            exceptions.append({"rank": 1, "actor": k, "kind": "supplier moved differently",
                               "text": f"{l['name']}: no announcement in the record and matched-product price "
                                       f"changed {g['change_pct']:+.1f}% across {im['reference_date']}."})
        for g in im["groups"]:
            if k in with_ev and not g["followed"]:
                exceptions.append({"rank": 2, "actor": k, "kind": "customer- or product-specific exception",
                                   "text": f"{l['name']}: {g['sku']}" + (f" shipped to {g['ship_to']}" if g['ship_to'] else "") + " changed "
                                           f"{g['change_pct']:+.1f}% against an announced {im['announced_pct']}%."})
        for e in l["events"]:
            if e["type"] in ("reversal", "discount", "exception", "failed_implementation"):
                exceptions.append({"rank": 3, "actor": k, "kind": e["type"], "event_id": e["id"],
                                   "text": f"{l['name']}: {e['type'].replace('_', ' ')} on {e['date_start']}."})
    exceptions.sort(key=lambda x: x["rank"])
    flags = []
    es, an, de = lags["effective"], lags["announcement"], [e for e in evs if e["type"] == "decision"]
    if es and es[1] <= 7 and ((an and an[0] >= 14) or de):
        flags.append({"flag": "same_effective_date_different_decisions",
                      "text": ("Stated effective dates coincide" if not es[1] else f"Stated effective dates fall within {es[1]} days of each other")
                              + (f", but the announcements are spread over {an[0] if an[0] == an[1] else f'{an[0]}-{an[1]}'} days" if an else "")
                              + (f" and {len(de)} decision-date event(s) precede them" if de else "")
                              + ". A shared effective date can reflect contract cycles rather than a shared decision."})
    res = {"episode_id": ep_id, "market_version_id": mv["id"], "market_version_n": mv["n"], "price_basis": basis,
           "lanes": lanes, "lags_days": lags, "flags": flags, "exceptions": exceptions,
           "uncertain_dates": [{"event_id": e["id"], "actor": name(e["actor"]), "type": e["type"],
                                "interval": [e["date_start"], e["date_end"]], "precision": e["precision"]}
                               for e in evs if e["precision"] != "day"],
           "excluded_events": dropped,
           "denominator": {"candidates": len(lanes), "with_event": len(with_ev), "records_but_no_event": len(no_ev),
                           "no_records": len(no_rec), "no_records_names": [lanes[k]["name"] for k in no_rec],
                           "text": f"{len(with_ev)} of {len(with_ev) + len(no_ev)} suppliers with records show a "
                                   f"comparable announcement; records are missing for {len(no_rec)} other "
                                   f"candidate supplier(s)."},
           "signature": signature(store, ep, rules),
           "disclaimer": "Descriptive observations only. Clustered timing is not an agreement finding."}
    if persist:
        store.update(ep_id, {"result": res, "stale": False, "stale_reasons": []}, None, "system", "analyze", "analyze")
    return res


def add_explanation(store, matter_id, d):
    """Common-cause register entry. Pass-through is recorded per firm, never assumed uniform."""
    for k in ("episode_id", "kind", "mechanism"):
        if not d.get(k):
            raise Invalid(f"explanation needs {k}")
    d.setdefault("affected", [])       # [{entity_id, status: documented|asserted|not_supplied, note, span_ids}]
    d.setdefault("unresolved", [])
    d.setdefault("span_ids", [])
    return store.put("explanation", d, matter_id)
