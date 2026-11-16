"""Allegation ledger: defendant-specific verification, stale-dependency tracking, the
"what if this source goes away" analysis, and the work queues derived from open gaps."""
from . import conduct, entities, provenance as prov, agreement
from .storage import Invalid, now

ACTS = {"announced": "announced the price increase", "implemented": "implemented the announced increase",
        "communicated": "communicated about future pricing",
        "participated": "participated in the alleged conduct"}
CHARACTERIZATIONS = ["observed_fact", "attributed_account", "information_and_belief", "inference"]
NO_SUPPORT = {"announced": "No announcement by this entity in the record",
              "implemented": "No announcement or transactions for this entity in the record",
              "communicated": "No communication identified", "participated": "No participation facts linked"}


def create(store, matter_id, d, reviewer="unassigned"):
    if d.get("act") not in ACTS:
        raise Invalid(f"act must be one of {list(ACTS)}")
    if d.get("characterization", "observed_fact") not in CHARACTERIZATIONS:
        raise Invalid(f"characterization must be one of {CHARACTERIZATIONS}")
    if not d.get("text") or not d.get("defendants"):
        raise Invalid("an allegation needs text and at least one named defendant")
    for k in ("support_span_ids", "contra_span_ids", "authority_ids"):
        d.setdefault(k, [])
    d.update(status="draft", stale=False, stale_reasons=[], verification=None)
    d.setdefault("record", "pleading")
    d.setdefault("characterization", "observed_fact")
    if d.get("episode_id") and not d.get("market_version_id"):
        d["market_version_id"] = store.get(d["episode_id"])["market_version_id"]
    return store.put("allegation", d, matter_id, reviewer)


def _found(act, k, res, items, nm):
    """(status, evidence, basis, gap, span_ids) for entity k's own conduct, or None."""
    lane = (res or {}).get("lanes", {}).get(k)
    if act == "announced" and lane:
        ev = [e for e in lane["events"] if e["type"] == "announcement"]
        if ev:
            return ("supported", "Announcement", "Documented statement",
                    None if ev[0]["status"] == "reviewed" else "Event extraction not yet attorney-reviewed",
                    ev[0]["span_ids"])
    if act == "implemented" and lane:
        im = lane["implementation"]
        if im["status"] == "observed":
            return ("supported", f"{im['post_lines']} post-effective invoice lines", "Observed transactions", None, [])
        if im["status"] == "partial":
            exc = "; ".join(f"{g['sku']} to {g['ship_to']} {g['change_pct']:+.1f}%" for g in im["groups"]
                            if not g["followed"])
            return ("exceptions", "Invoice sample", "Observed transactions", f"Customer-specific exceptions: {exc}", [])
        if im["status"] == "not_observed":
            return ("contradicted", "Invoice sample", "Observed transactions",
                    "Matched transactions show no comparable change", [])
        if lane["has_conduct_event"]:
            # An announcement is never upgraded to implementation.
            return ("unverified", "Announcement only", "Documented statement (announcement, not implementation)",
                    "Announcement found; implementation u" + im["label"][1:], [])
    if act in ("communicated", "participated"):
        for it in items:
            me = next((x for x in it["actors"] if x["entity_id"] == k), None)
            if not me or prov_all_unusable(it):
                continue
            if it["category"] == "association_contact" and act == "communicated" and \
                    agreement.LADDER.index(me["ladder"]) < agreement.LADDER.index("relevant_discussion"):
                return ("unsupported", "Association record", "Reaches only: " + me["ladder"].replace("_", " "),
                        "No evidence of a relevant discussion; " + me["ladder"].replace("_", " ")
                        + " is a different proposition", it["usable_spans"])
            how = it["how_known"]
            st = "supported" if how == "original_document" else "attributed_account"
            gap = "; ".join(m["text"] for m in it["missing"]) or None
            return (st, it.get("source_label") or "Agreement record", how.replace("_", " ").capitalize(), gap,
                    it["usable_spans"])
        if act == "participated" and lane and (lane["events"]):
            return ("supported", "Conduct events", "Documented conduct", None, [])
    return None


def prov_all_unusable(it):
    return bool(it["span_ids"]) and not it["usable_spans"]


def _deps(store, a):
    mid = a["matter_id"]
    ep = store.get(a["episode_id"]) if a.get("episode_id") else None
    mv = store.get(a["market_version_id"]) if a.get("market_version_id") else None
    return {"allegation text or scope": [a["text"], a["defendants"], a["act"], a["characterization"], a["record"]],
            "market version": [mv["id"], mv["superseded"]] if mv else None,
            "conduct episode inputs": conduct.signature(store, ep, store.get(ep["market_version_id"])["rules"]) if ep else None,
            "source availability": [prov.usable(store, s, a["record"]) for s in a["support_span_ids"] + a["contra_span_ids"]],
            "entity or attribution mapping": [(r["id"], r["rev"]) for r in store.list("relation", mid)],
            "agreement evidence": [(i["id"], i["rev"]) for i in store.list("agreement_item", mid)]}


def verify(store, aid):
    a = store.get(aid)
    mid, nm = a["matter_id"], entities.names(store, a["matter_id"])
    res = conduct.analyze(store, a["episode_id"]) if a.get("episode_id") else None
    items = agreement.matrix(store, a["episode_id"]) if a.get("episode_id") else []
    rows = []
    for d in a["defendants"]:
        r, via = _found(a["act"], d, res, items, nm), None
        if not r:
            for c in entities.attributable(store, mid, d) - {d}:
                r = _found(a["act"], c, res, items, nm)
                if r:
                    via = f"attributed from {nm[c]} under an approved mapping"
                    break
        if not r:
            kids = [x["child"] for x in store.list("relation", mid) if x["parent"] == d and x["attribution"] != "approved"]
            hit = next((c for c in kids if _found(a["act"], c, res, items, nm)), None)
            r = ("unsupported_attribution", "None linked", "Unsupported attribution",
                 f"Relationship alone supplied; the conduct in the record is {nm[hit]}'s", []) if hit else \
                ("unsupported", "None linked", "-", NO_SUPPORT[a["act"]], [])
        rows.append({"defendant": d, "name": nm.get(d, d), "act": a["act"], "status": r[0], "evidence": r[1],
                     "basis": r[2], "gap": r[3], "span_ids": r[4], "via": via})
    spans = [{**prov.cite(store, s), "role": role, "problem": prov.usable(store, s, a["record"])}
             for role, ids in (("supports", a["support_span_ids"]), ("contrary", a["contra_span_ids"])) for s in ids]
    good = [s["span_id"] for s in spans if s["role"] == "supports" and not s["problem"]]
    problems, blocking = [], []
    for s in spans:
        if s["problem"]:
            (blocking if "locator" in s["problem"] or "checksum" in s["problem"] or "match" in s["problem"]
             else problems).append(f"{s['filename']} {s['locator']}: {s['problem']}")
    sts = {r["status"] for r in rows}
    if a["characterization"] == "observed_fact" and sts & {"attributed_account", "unverified"}:
        problems.append("Characterized as observed fact, but support for at least one defendant is an attributed "
                        "account or an announcement only")
    if a["characterization"] == "information_and_belief" and not a.get("belief_basis"):
        problems.append("Information-and-belief allegation has no stated basis")
    mv = store.get(a["market_version_id"]) if a.get("market_version_id") else None
    if mv and mv["superseded"]:
        problems.append(f"Depends on superseded market version {mv['id']}")
    proposed = None
    if sts - {"supported"}:
        g = lambda *st: [r["name"] for r in rows if r["status"] in st]
        j = lambda xs: ", ".join(xs[:-1]) + " and " + xs[-1] if len(xs) > 1 else xs[0]
        parts = []
        if g("supported"):
            parts.append(f"{j(g('supported'))} {ACTS[a['act']]}.")
        if g("exceptions"):
            parts.append(f"{j(g('exceptions'))} {ACTS[a['act']]} for some customers but not others.")
        if g("attributed_account"):
            parts.append(f"According to a witness account, {j(g('attributed_account'))} {ACTS[a['act']]}.")
        if g("unverified"):
            parts.append(f"{j(g('unverified'))} announced the increase; the present record does not show whether "
                         "it was implemented.")
        om = g("unsupported", "unsupported_attribution", "contradicted")
        proposed = {"text": " ".join(parts) or None,
                    "omitted": om, "note": "Proposed narrower wording. Counsel resolves the characterization."}
    v = {"rows": rows, "spans": spans, "problems": problems, "blocking": blocking, "proposed": proposed,
         "corroboration": {"documents": len({s["source_id"] for s in spans if s["span_id"] in good}),
                           "independent_origins": len(prov.origins(store, good))},
         "inputs": {"market_version_id": a.get("market_version_id"), "episode_id": a.get("episode_id"),
                    "episode_signature": res["signature"] if res else None},
         "deps": _deps(store, a), "verified_at": now()}
    return store.update(aid, {"verification": v, "stale": False, "stale_reasons": []}, None, "system", "verify", "verify")


def guard_review(store, obj, patch, reason):
    """Kind-specific guards for reviewed mutations (called by POST /api/reviews)."""
    if obj["kind"] == "relation":
        entities.validate_relation_patch(patch)
    if obj["kind"] == "allegation" and patch.get("status") == "approved":
        v = obj.get("verification")
        if not v or obj["stale"]:
            raise Invalid("verify the allegation against the current record before approving it")
        if v["blocking"]:
            raise Invalid("promotion blocked: " + "; ".join(v["blocking"]))
        if (v["problems"] or any(r["status"] != "supported" or r["gap"] for r in v["rows"])) and not reason:
            raise Invalid("open gaps remain; approval requires the reviewer's stated reason for retaining them")
    if obj["kind"] == "event" and patch.get("type") == "first_transaction" and obj["type"] in ("announcement", "effective"):
        raise Invalid("an announcement or effective-date event cannot be relabeled as observed implementation; "
                      "implementation is established from transactions")


def refresh(store, matter_id):
    """Mark results stale when their declared inputs changed. Runs after every mutation."""
    for ep in store.list("episode", matter_id):
        if not ep.get("result") or ep.get("stale"):
            continue
        mv = store.get(ep["market_version_id"])
        why = f"market version {mv['id']} was superseded by {mv.get('superseded_by')}" if mv["superseded"] else \
            "inputs changed since last analysis (events, entity mappings, sources or transactions)" \
            if conduct.signature(store, ep, mv["rules"]) != ep["result"]["signature"] else None
        if why:
            store.update(ep["id"], {"stale": True, "stale_reasons": [why]}, None, "system", why, "mark_stale")
    for a in store.list("allegation", matter_id):
        v = a.get("verification")
        if not v or a.get("stale"):
            continue
        cur = _deps(store, a)
        why = [f"{k} changed since verification" for k in cur if _plain(cur[k]) != _plain(v["deps"].get(k))]
        if why:
            store.update(a["id"], {"stale": True, "stale_reasons": why}, None, "system", "; ".join(why), "mark_stale")


def _plain(x):  # JSON round-trip turns tuples into lists; compare like with like
    return prov.json.loads(prov.json.dumps(x))


def _span_ids(o):
    out = []
    if isinstance(o, dict):
        for k, v in o.items():
            out += v if k.endswith("span_ids") and isinstance(v, list) else _span_ids(v) if k != "verification" and k != "result" else []
    elif isinstance(o, list):
        for v in o:
            out += _span_ids(v)
    return out


def source_dependents(store, source_id):
    """Everything that leans on a source, directly or through events/transactions."""
    src = store.source(source_id, text=False)
    mid, mine = src["matter_id"], {s["id"] for s in store.spans_of(source_id)}
    hit = lambda o: bool(mine & set(_span_ids(o)))
    out = {k: [] for k in ("events", "market_boundaries", "substitution_records", "explanations", "agreement_items",
                           "episodes", "allegations")}
    evs = [e for e in store.list("event", mid) if hit(e)]
    out["events"] = [{"id": e["id"], "label": f"{e['type']} {e['date_start']}"} for e in evs]
    for v in store.list("market_version", mid):
        out["market_boundaries"] += [{"id": v["id"], "label": f"{v['name']} v{v['n']}: {b['statement']}"}
                                     for b in v["boundaries"] if hit(b)]
    for kind, k in (("substitution", "substitution_records"), ("explanation", "explanations"),
                    ("agreement_item", "agreement_items")):
        out[k] = [{"id": o["id"], "label": o.get("summary") or o.get("mechanism") or o.get("candidate_product")}
                  for o in store.list(kind, mid) if hit(o)]
    has_tx = bool(store.q("SELECT 1 FROM transactions WHERE source_id=? LIMIT 1", (source_id,)))
    eps = [ep for ep in store.list("episode", mid)
           if has_tx or any(e["id"] in {x["id"] for l in (ep.get("result") or {}).get("lanes", {}).values()
                                        for x in l["events"]} for e in evs)]
    out["episodes"] = [{"id": e["id"], "label": e["question"]} for e in eps]
    dep_items = {o["id"] for o in out["agreement_items"]}
    for a in store.list("allegation", mid):
        if hit(a) or a.get("episode_id") in {e["id"] for e in eps} or any(
                i["id"] in dep_items and i["episode_id"] == a.get("episode_id") for i in store.list("agreement_item", mid)):
            out["allegations"].append({"id": a["id"], "label": a["text"]})
    return out


def set_source_disabled(store, source_id, disabled, reviewer, reason, dry_run=False):
    dep = source_dependents(store, source_id)
    if dry_run:
        return {"dry_run": True, "dependents": dep}
    src = store.source(source_id, text=False)
    store.q("UPDATE sources SET disabled=? WHERE id=?", (int(disabled), source_id))
    store.log(src["matter_id"], source_id, "source", "disable" if disabled else "enable", None, None, reviewer, reason)
    mine = {s["id"] for s in store.spans_of(source_id)}
    for run in store.list("decision_run", src["matter_id"]):  # cached model output must not outlive the source
        if mine & set(run.get("span_ids", [])) and not run.get("invalidated"):
            store.update(run["id"], {"invalidated": True}, None, "system", "source disabled", "invalidate")
    refresh(store, src["matter_id"])
    return {"dry_run": False, "dependents": dep}


# ---- work queues ---------------------------------------------------------------
ROUTES = {"client_records": "Client-record request", "interview": "Interview", "public_source": "Public-source research",
          "compulsory_process": "Likely requires compulsory process"}


def investigation_queue(store, matter_id):
    q, nm = [], entities.names(store, matter_id)
    add = lambda need, why, route, ref: q.append({"need": need, "why": why, "route": route,
                                                  "route_label": ROUTES[route], "ref": ref,
                                                  "before_discovery": route != "compulsory_process"})
    for ep in store.list("episode", matter_id):
        for k, l in ((ep.get("result") or {}).get("lanes") or {}).items():
            if l["has_conduct_event"] and l["implementation"]["status"] == "unverified":
                add(f"Invoices from {l['name']} after the stated effective date",
                    "Announcement found; implementation unverified", "client_records", ep["id"])
            if l["records"] == "none supplied":
                add(f"Any purchase records or price notices from {l['name']}",
                    "Candidate supplier with no records: a coverage gap, not evidence of no price change",
                    "client_records", ep["id"])
    for kind in ("agreement_item", "explanation"):
        for o in store.list(kind, matter_id):
            for m in o.get("missing", []) + o.get("unresolved", []):
                add(m["text"], o.get("summary") or o.get("mechanism"), m.get("route", "interview"), o["id"])
    for a in store.list("allegation", matter_id):
        for r in (a.get("verification") or {}).get("rows", []):
            if r["status"] in ("unsupported", "unsupported_attribution") and r["act"] in ("communicated", "participated"):
                add(f"Participation facts specific to {r['name']}", r["gap"], "compulsory_process", a["id"])
    q.sort(key=lambda t: not t["before_discovery"])
    return q


def review_queue(store, matter_id):
    """Why this document next: rank unreviewed sources by the open dependencies they could settle."""
    out = []
    for s in store.sources(matter_id):
        if s["reviewed"] or s["disabled"]:
            continue
        mine = {x["id"] for x in store.spans_of(s["id"])}
        hit = lambda o: bool(mine & set(_span_ids(o)))
        ev = sum(1 for e in store.list("event", matter_id) if e["status"] == "proposed" and hit(e))
        ex = [x for x in store.list("explanation", matter_id) if hit(x)]
        firms = sum(len(x["affected"]) for x in ex)
        ag = sum(len(i.get("missing", [])) for i in store.list("agreement_item", matter_id) if hit(i))
        al = sum(1 for a in store.list("allegation", matter_id) if hit(a) and a["status"] != "approved")
        score = ev * 2 + firms * 3 + ag * 2 + al * 3
        why = [t for n, t in ((ev, f"{ev} proposed event(s) awaiting date-role review"),
                              (firms, f"bears on a common-cause explanation touching {firms} firm(s)"),
                              (ag, f"{ag} open question(s) in the agreement record"),
                              (al, f"cited by {al} unapproved allegation(s)")) if n]
        if score:
            out.append({"source_id": s["id"], "filename": s["filename"], "kind": s["kind"], "score": score, "why": why})
    return sorted(out, key=lambda x: -x["score"])


def diff_since_partner_review(store, matter_id):
    acts = store.reviews(matter_id)
    marks = [a for a in acts if a["action"] == "partner_review"]
    since = marks[-1]["id"] if marks else 0
    groups = {"entity_mappings": [], "market_boundaries": [], "counter_evidence": [], "newly_stale_or_unsupported": [],
              "sources": [], "other": []}
    for a in acts:
        if a["id"] <= since or a["action"] in ("create", "analyze", "verify", "import"):
            continue
        new = a["new"] or {}
        k = "entity_mappings" if a["kind"] in ("entity", "relation") else \
            "market_boundaries" if a["kind"] in ("market", "market_version") else \
            "newly_stale_or_unsupported" if a["action"] == "mark_stale" else \
            "sources" if a["kind"] == "source" else \
            "counter_evidence" if any("contra" in f for f in new) else "other"
        groups[k].append({"target": a["target"], "action": a["action"], "reviewer": a["reviewer"],
                          "reason": a["reason"], "ts": a["ts"], "fields": sorted(new)})
    return {"since": marks[-1]["ts"] if marks else None, "by": marks[-1]["reviewer"] if marks else None,
            "changes": groups}
