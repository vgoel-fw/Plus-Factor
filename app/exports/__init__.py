"""Versioned exports (Markdown / CSV / JSON). The permissions profile is applied at the
span: restricted text is withheld from quotes *and* from fields derived from it."""
import csv, io
from .. import provenance as prov, markets, conduct, explanations, agreement, allegations, precedent, entities

TYPES = ["market_memo", "chronology", "agreement_chart", "support_ledger", "mtd_vulnerability",
         "economist_handoff", "investigation_queue", "precedent_grid", "graph"]
DEFAULT_PROFILE = {"max_confidentiality": "highly_confidential", "include_privileged": True, "mode": "annotated",
                   "record": "investigation", "approved_only": False}


class Ctx:
    def __init__(self, store, mid, profile):
        self.s, self.mid, self.p = store, mid, {**DEFAULT_PROFILE, **(profile or {})}
        self.nm = entities.names(store, mid)
        self.used = set()

    def barred(self, span_id):
        why = prov.usable(self.s, span_id, self.p["record"])
        if why:
            return why
        c = prov.cite(self.s, span_id)
        if prov.CONF.index(c["confidentiality"]) > prov.CONF.index(self.p["max_confidentiality"]):
            return f"{c['confidentiality'].replace('_', ' ')} material outside this export's profile"
        if c["privilege"] != "none" and not self.p["include_privileged"]:
            return "privileged material outside this export's profile"
        return None

    def cite(self, span_id):
        why = self.barred(span_id)
        if why:
            return f"[withheld: {why}]"
        c = prov.cite(self.s, span_id)
        self.used.add(span_id)
        ref = f"{c['filename']}, {c['locator']}"
        return f"{ref}: \"{c['text'].strip()}\"" if self.p["mode"] == "annotated" else ref

    def cites(self, ids):
        return "; ".join(self.cite(i) for i in ids) or "none linked"

    def guard(self, ids, text):
        """Free text derived from sources is withheld if any source behind it is barred."""
        return "[withheld: depends on restricted source]" if any(self.barred(i) for i in ids) else text


def _market_memo(c):
    out = ["# Market-definition memorandum", "",
           "_Competing hypotheses under review. Nothing below is a finding that any market exists._", ""]
    for v in c.s.list("market_version", c.mid):
        if v["superseded"]:
            continue
        r, sm = v["rules"], markets.summary(c.s, c.mid, v["rules"])
        out += [f"## {v['name']} (version {v['n']}, {v['id']}, {v['status']})", "",
                f"**Purchaser requirement:** {r['requirement']}", "",
                f"**Scope:** products {r.get('families') or 'any'}; grades {r.get('grades') or 'any'}; origin "
                f"{r.get('origins') or 'any'}; ship-to {r.get('regions') or 'any'}; customers "
                f"{r.get('customer_group') or 'unspecified'}; channel {r.get('channel') or 'unspecified'}.", "",
                f"**Record coverage:** {sm['transactions']} transactions from {len(sm['suppliers'])} supplier(s). "
                f"{sm['concentration_note']}", "", f"**Rationale:** {v['rationale']}", ""]
        for b in v["boundaries"]:
            out += [f"### Boundary: {b['statement']} ({b['status']})",
                    f"- Supports: {c.cites(b['support_span_ids'])}", f"- Cuts the other way: {c.cites(b['contra_span_ids'])}",
                    f"- Unresolved: {b.get('unresolved') or 'none recorded'}", ""]
    out += ["## Substitution records", ""]
    for s in c.s.list("substitution", c.mid):
        cond = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in s["conditions"].items())
        out += [f"- **{s['candidate_product']}** for {s['application']} ({s.get('period') or 'period unknown'}). "
                f"{c.guard(s['span_ids'], s.get('summary', ''))} [{cond}] Source: {c.cites(s['span_ids'])}"]
    return out


def _chronology(c, rows_only=False):
    rows = []
    for e in sorted(c.s.list("event", c.mid), key=lambda e: e["date_start"]):
        if e["status"] == "rejected" or (c.p["approved_only"] and e["status"] != "reviewed"):
            continue
        d = e["date_start"] if e["precision"] == "day" else f"{e['date_start']} to {e['date_end']} ({e['precision']})"
        rows.append([c.nm.get(e.get("actor"), e.get("actor_text") or "unresolved"), d, e["type"],
                     f"{e['value']}{e.get('value_unit', '')}" if e.get("value") else "", e["status"], e["id"],
                     c.cites(e["span_ids"])])
    if rows_only:
        return rows
    out = ["# Defendant-by-defendant chronology", "",
           "_Announcement, effective and transaction dates are distinct events and are listed separately._", ""]
    for actor in sorted({r[0] for r in rows}):
        out += [f"## {actor}", "", "| Date | Event | Value | Review | Source |", "|---|---|---|---|---|"]
        out += [f"| {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[6]} |" for r in rows if r[0] == actor] + [""]
    return out


def _agreement(c):
    out = ["# Agreement allegation chart", "", "_Organized by episode and evidentiary question; not a count of plus factors._", ""]
    for ep in c.s.list("episode", c.mid):
        out += [f"## Episode {ep['id']}: {ep['question']}", "",
                "| Who | What | When | How we know | What followed | Cuts the other way | Missing |", "|---|---|---|---|---|---|---|"]
        for it in agreement.matrix(c.s, ep["id"]):
            ids = it["span_ids"]
            who = "; ".join(a["name"] + (f" ({a['ladder'].replace('_', ' ')})" if a.get("ladder") else "") for a in it["actor_names"])
            out.append(f"| {who} | {c.guard(ids, it.get('language') or it.get('summary'))} ({it['information_tense']} information) "
                       f"| {it.get('when_text') or ''} | {it['how_known'].replace('_', ' ')}; {c.cites(ids)}; "
                       f"{it['documents']} document(s), {it['independent_origins']} independent origin(s) "
                       f"| {c.guard(ids, it.get('followed') or '')} | {'; '.join(it['cuts_other_way']) or 'none recorded'} "
                       f"| {'; '.join(m['text'] for m in it['missing']) or 'none recorded'} |")
        out.append("")
    return out


def _ledger_rows(c):
    for a in c.s.list("allegation", c.mid):
        if a["record"] != "pleading" and c.p["record"] == "pleading":
            continue
        if c.p["approved_only"] and (a["status"] != "approved" or a["stale"]):
            continue
        yield a


def _ledger(c):
    out = ["# Paragraph-level support ledger", ""]
    for a in _ledger_rows(c):
        v = a.get("verification") or {}
        out += [f"## {a['id']}: {a['status']}{' / STALE' if a['stale'] else ''}", "", f"> {a['text']}", "",
                f"Characterization: {a['characterization'].replace('_', ' ')}. Market version: {a.get('market_version_id')}. "
                f"Episode: {a.get('episode_id')}.", ""]
        if a["stale"]:
            out += ["**Stale:** " + "; ".join(a["stale_reasons"]), ""]
        if c.p["mode"] == "clean":
            continue
        out += ["| Defendant | Alleged act | Evidence | Basis | Gap |", "|---|---|---|---|---|"]
        out += [f"| {r['name']} | {r['act']} | {r['evidence']} | {r['basis']}{' (' + r['via'] + ')' if r['via'] else ''} "
                f"| {r['gap'] or ''} |" for r in v.get("rows", [])]
        out += ["", f"Supports: {c.cites(a['support_span_ids'])}", "", f"Cuts the other way: {c.cites(a['contra_span_ids'])}", ""]
        if v.get("proposed"):
            out += [f"Proposed narrower wording: {v['proposed']['text']}", ""]
    return out


def _mtd(c):
    m = c.s.get(c.mid)
    out = ["# Motion-to-dismiss vulnerability memorandum", "",
           "_Lists factual connections and gaps. It does not score plausibility or predict a ruling._", "",
           f"Asserted framework: **{m.get('theory', 'unresolved')}**. Issue register (analyzed separately): "
           + "; ".join(f"{i['issue'].replace('_', ' ')}: {i['status']}" for i in c.s.list("issue", c.mid)) + ".", ""]
    for a in _ledger_rows(c):
        v = a.get("verification")
        if not v:
            out += [f"- {a['id']}: not yet verified against the record."]
            continue
        for r in v["rows"]:
            if r["status"] != "supported" or r["gap"]:
                out.append(f"- {a['id']} / **{r['name']}**: {r['status'].replace('_', ' ')}: {r['gap'] or r['basis']}")
        out += [f"- {a['id']}: {p}" for p in v["problems"] + v["blocking"]]
    for ep in c.s.list("episode", c.mid):
        res = ep.get("result") or {}
        out += ["", f"## Episode {ep['id']}", "", f"Coverage: {res.get('denominator', {}).get('text', 'not analyzed')}", ""]
        out += [f"- Flag: {f['text']}" for f in res.get("flags", [])]
        out += [f"- Exception: {x['text']}" for x in res.get("exceptions", [])]
        out += [f"- Common cause ({x['kind'].replace('_', ' ')}): {x['mechanism']} {x['reach_text']}"
                for x in explanations.register(c.s, ep["id"])]
    out += ["", "## Unfavorable analogues (unreviewed manifest entries)", ""]
    out += [f"- {r['name']}, {r['citation']} ({r['court']} {r['year']}): {r['disposition']} as to {r['defendant_scope']}. {r['paraphrase']}"
            for r in precedent.unfavorable("plaintiff", "agreement_plausibility", m.get("circuit"))]
    return out


def _handoff(c):
    eps = c.s.list("episode", c.mid)
    imps = c.s.list("import", c.mid)
    sample = []
    for ep in eps:
        rules = c.s.get(ep["market_version_id"])["rules"]
        for t in markets.live_txns(c.s, c.mid):
            from ..transactions import in_market
            sample.append({"episode_id": ep["id"], "transaction_id": t["id"], "source_span": t["span_id"],
                           "included": in_market(t["norm"], rules), "original": t["original"], "normalized": t["norm"]})
    return {"notice": "Data bundle for a testifying or consulting economist. Contains no elasticity, causal or damages "
                      "estimates; none were generated.",
            "transformations": [{"source_id": i["source_id"], "mapping": i["mapping"], "formula": i["formula"],
                                 "row_errors": i["row_errors"]} for i in imps],
            "episodes": [{"id": e["id"], "question": e["question"], "market_version_id": e["market_version_id"],
                          "rules": c.s.get(e["market_version_id"])["rules"], "price_basis": e.get("price_basis"),
                          "threshold": e.get("threshold"), "excluded_events": e.get("excluded", [])} for e in eps],
            "proposed_controls": [{"kind": x["kind"], "mechanism": x["mechanism"], "assumptions": x.get("assumptions"),
                                   "unresolved": x["unresolved"]} for x in c.s.list("explanation", c.mid)],
            "sample": sample}


def _queue(c):
    out = ["# Investigation queue", "", "## Available before discovery", ""]
    q = allegations.investigation_queue(c.s, c.mid)
    out += [f"- [{t['route_label']}] {t['need']}: {t['why']} ({t['ref']})" for t in q if t["before_discovery"]]
    out += ["", "## Likely requires compulsory process", ""]
    out += [f"- {t['need']}: {t['why']} ({t['ref']})" for t in q if not t["before_discovery"]]
    return out


def _grid(c):
    m = c.s.get(c.mid)
    out = ["# Precedent comparison grid", "", "_Manifest entries are unreviewed working notes. No outcome rates are computed._", "",
           "| Authority | Weight | Posture | Issue | Scope | Disposition | Note |", "|---|---|---|---|---|---|---|"]
    out += [f"| {r['name']}, {r['citation']} ({r['court']} {r['year']}) | {r['weight']} | {r['posture'].replace('_', ' ')} "
            f"| {r['issue'].replace('_', ' ')} | {r['defendant_scope']} | {r['disposition']} | {r['paraphrase']} |"
            for r in precedent.search(circuit=m.get("circuit"))]
    return out


def graph(store, mid):
    kinds = ["entity", "relation", "market", "market_version", "substitution", "event", "episode", "explanation",
             "agreement_item", "allegation", "issue", "import", "decision_run"]
    srcs = store.sources(mid)
    return {"matter": store.get(mid), **{("entities" if k == "entity" else k + "s"): store.list(k, mid) for k in kinds}, "sources": srcs,
            "spans": [sp for s in srcs for sp in store.spans_of(s["id"])]}


def _withhold(c, o):
    from ..allegations import _span_ids
    if not isinstance(o, dict) or not any(c.barred(i) for i in _span_ids(o)):
        return o
    keep = {k: o[k] for k in ("id", "kind", "rev", "status", "episode_id", "market_version_id") if k in o}
    if o["kind"] == "allegation":  # counsel's own sentence stays; everything derived from the source goes
        keep.update(text=o["text"], defendants=o["defendants"], act=o["act"])
    if o["kind"] == "market_version":
        keep.update({k: o[k] for k in ("name", "n", "rules", "rationale")})
    return {**keep, "withheld": "depends on source material outside this export's profile"}


def export(store, mid, etype, fmt="md", profile=None, reviewer="unassigned"):
    c = Ctx(store, mid, profile)
    if etype == "graph" or etype == "economist_handoff":
        fmt = "json"
        if etype == "graph":
            g = graph(store, mid)
            g["spans"] = [s if not c.barred(s["id"]) else {**s, "text": "[withheld]"} for s in g["spans"]]
            for k, objs in g.items():  # restrictions follow the document into derived objects
                if isinstance(objs, list) and k not in ("spans", "sources"):
                    g[k] = [_withhold(c, o) for o in objs]
            body = prov.json.dumps(g, indent=1)
        else:
            body = prov.json.dumps(_handoff(c), indent=1)
    elif fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        if etype == "chronology":
            w.writerow(["actor", "date", "event_type", "value", "review_status", "event_id", "source"])
            w.writerows(_chronology(c, True))
        else:
            w.writerow(["allegation_id", "status", "stale", "defendant", "act", "support_status", "evidence", "basis",
                        "gap", "market_version", "episode", "support_span_ids"])
            for a in _ledger_rows(c):
                for r in (a.get("verification") or {}).get("rows", []):
                    w.writerow([a["id"], a["status"], a["stale"], r["name"], r["act"], r["status"], r["evidence"],
                                r["basis"], r["gap"], a.get("market_version_id"), a.get("episode_id"),
                                " ".join(a["support_span_ids"])])
        body = buf.getvalue()
    else:
        fn = {"market_memo": _market_memo, "chronology": _chronology, "agreement_chart": _agreement,
              "support_ledger": _ledger, "mtd_vulnerability": _mtd, "investigation_queue": _queue,
              "precedent_grid": _grid}[etype]
        m = store.get(mid)
        body = "\n".join(fn(c) + ["", "---", f"Matter {m['name']} (rev {m['rev']}). Profile: {c.p}. "
                                  f"Internal draft for attorney review; not legal advice."])
    snap = store.put("export", {"type": etype, "format": fmt, "profile": c.p, "matter_rev": store.get(mid)["rev"],
                                "span_ids": sorted(c.used), "content_hash": prov.sha(body), "content": body}, mid, reviewer)
    return snap
