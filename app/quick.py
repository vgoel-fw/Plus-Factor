"""One-shot analysis: files or pasted details in, chart-ready result out.

No intake, no manual mapping. Everything the pipeline assumes on the user's behalf
(file types, column meanings, name matches, market candidates) is returned in
`assumptions` so it can be seen and challenged."""
import csv, io, re
from . import conduct, decisions, entities, ingest, markets, provenance as prov, seed, transactions as tx
from .markets import key, live_txns
from .storage import now

SUFFIX = {"co", "inc", "llc", "ltd", "plc", "corp", "company", "the", "corporation", "lp"}


def detect(filename, content):
    low = content.lower()
    if filename.lower().endswith((".csv", ".tsv")) or low.count(",") > 8 * max(1, low.count("\n")) / 2 and "\n" in low[:400] and "," in low[:200]:
        return "discovery_export" if "textpath" in low[:400] else "ap_export"
    if re.search(r"^from:", low, re.M) and "effective" in low and re.search(r"increase|adjust", low):
        return "price_letter"
    if "interview" in low[:400] or "stated that" in low:
        return "interview_memo"
    if re.search(r"agreement|contract", low[:300]) and "section" in low:
        return "contract"
    return "public_statement" if "earnings call" in low[:300] else "other_text"


def _norm(name):
    return [w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in SUFFIX]


def _same(a, b):
    a, b = _norm(a), _norm(b)
    n = min(len(a), len(b))
    return n > 0 and a[:n] == b[:n]


def from_form(form):
    """No documents? The table becomes the same inputs: one notice per supplier, plus
    invoice lines when prices before and after were given. Nothing is invented."""
    out, rows = [], [r for r in form.get("suppliers", []) if (r.get("name") or "").strip()]
    prod = (form.get("product") or "the product").strip()
    for r in rows:
        if r.get("announced") or r.get("effective"):
            txt = f"From: {r['name'].strip()}\n" + (f"Date: {_long(r['announced'])}\n" if r.get("announced") else "")
            txt += (f"Effective {_long(r['effective'])}, " if r.get("effective") else "") + \
                   f"prices for {prod} will increase" + (f" by {r['pct']}%" if r.get("pct") else "") + ".\n"
            if r.get("note"):
                txt += r["note"].strip() + "\n"
            out.append({"filename": f"entered_{re.sub(r'\W+', '_', r['name'].strip().lower())}.txt", "content": txt})
    priced = [r for r in rows if r.get("before") and r.get("after") and r.get("effective")]
    if priced:
        lines = ["Vendor,Inv Date,Item,Family,Qty,UOM,Ext Amount"]
        fam = re.sub(r"\W+", "_", prod.lower())
        for r in priced:
            y, m, d = map(int, r["effective"].split("-"))
            pre, post = f"{y - (m == 1)}-{(m - 2) % 12 + 1:02d}-15", f"{y}-{m:02d}-{max(d, 15):02d}"
            lines += [f"{r['name']},{pre},{fam},{fam},1,LB,{float(r['before'])}", f"{r['name']},{post},{fam},{fam},1,LB,{float(r['after'])}"]
        out.append({"filename": "entered_prices.csv", "content": "\n".join(lines) + "\n"})
    return out


def _long(iso):
    from datetime import date
    d = date.fromisoformat(iso)
    return d.strftime("%B ") + str(d.day) + d.strftime(", %Y")


def run(store, files, details="", adapter=decisions.jev_adapter, consent=False):
    m = seed.new_matter(store, {"name": f"Analysis {now()}", "product_terms": {}, "quick": True,
                                "provider_permission": "external_allowed" if consent else "local_only",
                                "external_max_confidentiality": "highly_confidential"})
    mid, notes, skipped = m["id"], [], []
    if details.strip():
        files = list(files) + [{"filename": "pasted_details.txt", "content": details}]
    typed = []
    for f in files:
        ext = "." + f["filename"].rsplit(".", 1)[-1].lower() if "." in f["filename"] else ""
        if ext in ingest.UNSUPPORTED:
            skipped.append({"file": f["filename"], "reason": ingest.UNSUPPORTED[ext]})
        else:
            typed.append((f["filename"], f["content"], detect(f["filename"], f["content"])))
    # 1. names: letter issuers are legal names; invoice vendor strings are matched to them and the match is disclosed
    issuers = [mm[1].strip() for _, c, k in typed if k == "price_letter" for mm in [re.search(r"^From: (.+)$", c, re.M)] if mm]
    ids = {n: entities.add_entity(store, mid, n, defendant=True)["id"] for n in dict.fromkeys(issuers)}
    fams = set()
    for fn, c, k in typed:
        if k != "ap_export":
            continue
        rows = list(csv.DictReader(io.StringIO(c)))
        mp = tx.guess_mapping(list(rows[0].keys()) if rows else [])
        fams |= {r[mp["family"]] for r in rows if mp.get("family") and r.get(mp["family"])}
        for v in dict.fromkeys(r[mp["vendor"]].strip() for r in rows if mp.get("vendor")):
            hit = next((n for n in ids if _same(n, v)), None)
            if hit and hit.lower() != v.lower():
                e = store.get(ids[hit])
                store.update(e["id"], {"aliases": e["aliases"] + [{"name": v, "status": "approved", "basis": "auto-matched by name"}]}, e["rev"])
                notes.append(f"Invoice vendor “{v}” treated as {hit} (name match; confirm before relying on it).")
            elif not hit:
                ids[v] = entities.add_entity(store, mid, v)["id"]
    store.update(mid, {"product_terms": {f: [f.replace("_", " ")] for f in fams}}, None)
    # 2. import
    for fn, c, k in sorted(typed, key=lambda t: t[2] != "ap_export"):
        r = ingest.import_file(store, mid, fn, c, k)
        if r["status"] == "needs_mapping":
            mp = r["proposed_mapping"]
            lack = [x for x in ("vendor", "date", "quantity", "unit", "amount") if x not in mp]
            if lack:
                skipped.append({"file": fn, "reason": "could not identify column(s): " + ", ".join(lack)})
                continue
            out = ingest.apply_mapping(store, r["source"]["id"], mp, tx.DEFAULT_FORMULA, "auto")
            notes.append(f"{fn}: read {out['rows']} invoice lines; columns matched automatically ("
                         + ", ".join(f"{a} ← {b}" for a, b in list(mp.items())[:6]) + ", …).")
            skipped += [{"file": fn, "reason": f"row {e['row']}: {e['error']}"} for e in out["row_errors"][:5]]
        elif r["status"] == "unsupported":
            skipped.append({"file": fn, "reason": r["reason"]})
    # 3. Jev: narrow typed questions about passages
    checks = []

    def ask(task, span, src, expect=None):
        d = decisions.run(store, mid, {"task": task, "source_span_ids": [span["id"]], "context_complete": True}, adapter)
        checks.append({"question": decisions.st.QUESTIONS[task]["prompt"], "passage": span["text"][:240], "span_id": span["id"],
                       "source_id": src["id"], "file": src["filename"], "locator": span["locator"], "label": d["label"],
                       "route": d["route"], "task": task, "confidence": d.get("score"), "probabilities": d.get("scores") or {}, "agrees": None if expect is None else d["label"] == expect, "expected": expect})
        return d["label"]
    srcs = {s["id"]: s for s in store.sources(mid)}
    for e in store.list("event", mid):
        sp = store.span(e["span_ids"][0])
        ask("date_role", sp, srcs[sp["source_id"]], e["type"])
    statements = []
    for s in store.sources(mid, text=True):
        if s["kind"] in ("ap_export", "price_letter", "discovery_export"):
            continue
        pos = 0
        for line in s["text"].splitlines(keepends=True):
            body = line.strip()
            if len(body) > 45 and not body.startswith("["):
                sp = prov.make_span(store, s["id"], pos + line.find(body), pos + line.find(body) + len(body), "line-1")
                kind = ask("passage_kind", sp, s)
                basis = ask("knowledge_basis", sp, s) if s["kind"] in ("interview_memo", "other_text") else None
                price = bool(re.search(r"pric|going up|increase|surcharge", body.lower()))
                if kind == "other_case" or price or basis == "hearsay":
                    statements.append({"text": body, "file": s["filename"], "locator": sp["locator"], "source_id": s["id"],
                                       "span_id": sp["id"], "kind": kind, "basis": basis, "about_pricing": price})
            pos += len(line)
    # 4. candidate markets from what the purchaser actually bought
    live = [t["norm"] for t in live_txns(store, mid)]
    cands = []
    if live:
        def top(dim):
            vol = {}
            for n in live:
                if n[dim]:
                    vol[n[dim]] = vol.get(n[dim], 0) + (n["qty_lb"] or 0)
            return sorted(vol, key=vol.get, reverse=True)
        fam, gr, org = top("family"), top("grade"), top("origin")
        base = {"requirement": "Derived from the purchase record: the product the purchaser buys most.",
                "families": fam[:1], "grades": gr[:1], "origins": org[:1]}
        label = lambda r: " · ".join(x for x in (", ".join(r["families"]).replace("_", " ") or "all products",
                                                     ("/".join(r["grades"]) + " grade") if r["grades"] else "any grade",
                                                     "/".join(r["origins"]) if r["origins"] else "any origin") if x)
        cands = [("Narrowest", base)]
        if len(org) > 1:
            cands.append(("Add other origins", {**base, "origins": []}))
        if len(gr) > 1:
            cands.append(("Add other grades", {**base, "grades": []}))
        if len(fam) > 1:
            cands.append(("Add other products", {**base, "families": [], "grades": [], "origins": []}))
        vers = [markets.create_market(store, mid, f"{n}: {label(r)}", r, "auto-generated candidate", "auto") for n, r in cands]
        dates = [n["date"] for n in live] + [e["date_start"] for e in store.list("event", mid)]
        store.put("episode", {"question": "Did suppliers change prices in parallel?", "market_version_id": vers[0]["id"],
                              "window_from": min(dates)[:8] + "01", "window_to": max(dates), "price_basis": "gross",
                              "threshold": 0.5, "excluded": [], "stale": False, "stale_reasons": []}, mid, "auto")
        notes.append("Candidate markets were generated from the purchase record by relaxing one boundary at a time. "
                     "They are hypotheses to test, not findings.")
    elif store.list("event", mid):
        notes.append("No invoice data supplied: announcements are shown, but implementation and market candidates need purchase records.")
    store.update(mid, {"quick_meta": {"assumptions": notes, "skipped": skipped, "checks": checks, "statements": statements,
                                      "adapter": adapter.NAME, "jev_live": True}}, None)
    return result(store, mid)


def _series(txns, names):
    by = {}
    for n in txns:
        if n["gross_unit_price"] is not None:
            by.setdefault(key(n), {}).setdefault(n["date"][:7], []).append(n["gross_unit_price"])
    return [{"key": k, "name": names(k), "points": [[m, round(tx.med(v), 4)] for m, v in sorted(ms.items())]}
            for k, ms in sorted(by.items())]


def result(store, mid):
    m = store.get(mid)
    nm = entities.names(store, mid)
    names = lambda k: nm.get(k, k.replace("unmapped:", ""))
    eps = store.list("episode", mid)
    out = {"id": mid, **m["quick_meta"], "conduct": None, "markets": [],
           "files": [{"id": s["id"], "name": s["filename"], "kind": s["kind"]} for s in store.sources(mid)]}
    if not eps:
        evs = store.list("event", mid)
        out["events"] = [{"actor": names(e.get("actor") or e.get("actor_text") or "?"), "type": e["type"], "date": e["date_start"],
                          "value": e.get("value"), "span_id": e["span_ids"][0], "source_id": store.span(e["span_ids"][0])["source_id"]}
                         for e in evs]
        return out
    ep = eps[0]
    base = None
    for i, v in enumerate(v for v in store.list("market_version", mid) if not v["superseded"]):
        res = conduct.analyze(store, ep["id"], v["rules"], persist=False)
        live = [t["norm"] for t in live_txns(store, mid) if tx.in_market(t["norm"], v["rules"])]
        if i == 0:
            for l in res["lanes"].values():
                for e in l["events"]:
                    e["source_id"] = store.span(e["span_ids"][0])["source_id"]
            out["conduct"] = {**res, "window": [ep["window_from"], ep["window_to"]], "series": _series(live, names)}
        sm = markets.summary(store, mid, v["rules"])
        moved = [l for l in res["lanes"].values() if l["implementation"]["status"] in ("observed", "partial")]
        base = base if base is not None else set(res["lanes"])
        added = [k for k in res["lanes"] if k not in base]
        flat = [res["lanes"][k]["name"] for k in added if res["lanes"][k]["implementation"]["status"] == "not_observed"]
        out["markets"].append({
            "name": v["name"], "rules": v["rules"], "transactions": sm["transactions"],
            "suppliers": [{"key": k, "name": names(k), "share": s["share"], "lb": s["lb"],
                           "status": res["lanes"][k]["implementation"]["status"],
                           "announced": res["lanes"][k]["has_conduct_event"]} for k, s in sm["suppliers"].items()],
            "announcers": res["denominator"]["with_event"], "with_records": res["denominator"]["with_event"] + res["denominator"]["records_but_no_event"],
            "moved": len(moved), "did_not_move": flat, "pattern_holds": not flat, "baseline": i == 0,
            "added": [res["lanes"][k]["name"] for k in added],
            "reading": ("Baseline: the narrowest market the purchase record supports." if i == 0 else
                        f"Adds {', '.join(res['lanes'][k]['name'] for k in added)}; " + (
                        f"{', '.join(flat)} did not move. The parallel pattern weakens if the market is this broad." if flat
                        else "each added supplier with invoices moved too.") if added else "Adds no new suppliers in this record.")})
    return out


def sample(store):
    files = [{"filename": p.name, "content": p.read_text()} for p in sorted(seed.FIX.iterdir()) if p.suffix in (".csv", ".txt")]
    return run(store, files)
