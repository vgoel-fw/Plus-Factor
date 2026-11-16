"""Importers. Extraction only ever *proposes*; unsupported inputs are reported, not skipped."""
import csv, io, re
from .. import entities, provenance as prov, transactions as tx
from ..storage import Invalid

TEXT_KINDS = ["price_letter", "contract", "interview_memo", "public_statement", "trade_article", "deposition",
              "complaint", "other_text"]
TABLE_KINDS = ["ap_export", "bid_tab", "discovery_export"]
UNSUPPORTED = {".pdf": "supply extracted text (optional document-processing adapter not installed)",
               ".docx": "supply extracted text", ".msg": "supply extracted text", ".xlsx": "export the sheet as CSV",
               ".dat": "native load files are not supported yet; export CSV metadata plus extracted text",
               ".opt": "native load files are not supported yet", ".pst": "not supported"}


def import_file(store, matter_id, filename, content, kind, meta=None, texts=None, **flags):
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in UNSUPPORTED:
        return {"status": "unsupported", "filename": filename, "reason": UNSUPPORTED[ext]}
    if kind not in TEXT_KINDS + TABLE_KINDS:
        return {"status": "unsupported", "filename": filename, "reason": f"unknown material type {kind!r}"}
    if kind == "discovery_export":
        return _discovery(store, matter_id, filename, content, texts or {}, flags)
    src, new = prov.add_source(store, matter_id, filename, kind, content, meta, **flags)
    out = {"status": "imported" if new else "already_imported", "source": src, "proposed_events": []}
    if not new:
        return out
    if kind in ("ap_export", "bid_tab"):
        header = next(csv.reader(io.StringIO(content)))
        out.update(status="needs_mapping", header=header, proposed_mapping=tx.guess_mapping(header),
                   proposed_formula=tx.DEFAULT_FORMULA, roles=tx.ROLES)
    elif kind == "price_letter":
        out["proposed_events"] = propose_letter_events(store, matter_id, src["id"])
    return out


def apply_mapping(store, source_id, mapping, formula, reviewer="unassigned"):
    """Confirmed column mapping + recorded formula -> transactions with row-level spans."""
    src = store.source(source_id)
    if store.q("SELECT 1 FROM transactions WHERE source_id=? LIMIT 1", (source_id,)):
        return {"status": "already_mapped", "source_id": source_id}
    for need in ("vendor", "date", "quantity", "unit", "amount"):
        if need not in mapping:
            raise Invalid(f"mapping is missing required role {need!r}")
    text, pos, errors, n = src["text"], 0, [], 0
    lines = text.splitlines(keepends=True)
    header = next(csv.reader([lines[0]]))
    pos = len(lines[0])
    for i, line in enumerate(lines[1:], start=2):
        start, pos = pos, pos + len(line)
        if not line.strip():
            continue
        orig = dict(zip(header, next(csv.reader([line]))))
        try:
            norm = tx.normalize(orig, mapping, formula)
        except (Invalid, ValueError) as e:
            errors.append({"row": i, "error": str(e)})
            continue
        sp = prov.make_span(store, source_id, start, start + len(line.rstrip("\r\n")), "csv-row-1", f"row {i}")
        norm["entity_id"], norm["entity_candidates"] = entities.resolve(store, src["matter_id"], norm["vendor"])
        store.q("INSERT INTO transactions VALUES(?,?,?,?,?,?)",
                (store.new_id("tx"), src["matter_id"], source_id, sp["id"], prov.json.dumps(orig),
                 prov.json.dumps(norm)))
        n += 1
    imp = store.put("import", {"source_id": source_id, "mapping": mapping, "formula": formula, "rows": n,
                               "row_errors": errors}, src["matter_id"], reviewer)
    return {"status": "mapped", "import": imp, "rows": n, "row_errors": errors}


def remap_entities(store, matter_id):
    """Re-resolve vendor strings after a mapping review. Unmapped vendors stay unmapped."""
    for t in store.txns(matter_id):
        n = t["norm"]
        eid, cands = entities.resolve(store, matter_id, n["vendor"])
        if eid != n.get("entity_id"):
            n["entity_id"], n["entity_candidates"] = eid, cands
            store.q("UPDATE transactions SET norm=? WHERE id=?", (prov.json.dumps(n), t["id"]))


DATE = r"([A-Z][a-z]+ \d{1,2}, \d{4})"


def propose_letter_events(store, matter_id, source_id):
    """Proposed announcement and effective-date events from a price letter. A letter can
    support an announcement and a stated effective date. It is never implementation."""
    text = store.source(source_id)["text"]
    issuer = re.search(r"^From: (.+)$", text, re.M)
    actor, cands = entities.resolve(store, matter_id, issuer[1]) if issuer else (None, [])
    amt = re.search(r"(?:increase|adjust)[^.\n]*?by (\d+(?:\.\d+)?)%", text)
    terms = store.get(matter_id).get("product_terms") or {}
    fam = next((f for f, kws in terms.items() if any(k in text.lower() for k in kws)), None) or \
        (next(iter(terms)) if len(terms) == 1 else None)
    grades = [g for g in ("food", "industrial") if re.search(g + r"[- ]grade", text.lower())]
    base = {"actor": actor, "actor_candidates": cands, "actor_text": issuer[1] if issuer else None,
            "family": fam, "grades": grades, "value": float(amt[1]) if amt else None, "value_unit": "%",
            "status": "proposed", "extraction": "letter-regex-1"}
    out = []
    for etype, pat in (("announcement", r"^Date: " + DATE), ("effective", r"Effective " + DATE)):
        m = re.search(pat, text, re.M)
        if not m:
            continue
        s, e, p = prov.parse_date(m[1])
        ls = text.rfind("\n", 0, m.start()) + 1
        le = text.find("\n", m.end())
        sp = prov.make_span(store, source_id, ls, le if le > 0 else len(text), "letter-regex-1")
        out.append(store.put("event", {**base, "type": etype, "date_start": s, "date_end": e, "precision": p,
                                       "date_basis": "letter date line" if etype == "announcement"
                                       else "stated effective date", "span_ids": [sp["id"]]}, matter_id))
    return out


def _discovery(store, matter_id, filename, content, texts, flags):
    """Relativity-style handoff: CSV metadata + extracted text. Rows without text are reported."""
    idx, _ = prov.add_source(store, matter_id, filename, "discovery_export", content, record="investigation")
    docs, missing = [], []
    for row in csv.DictReader(io.StringIO(content)):
        body = texts.get(row.get("TextPath", ""))
        if body is None:
            missing.append({"doc_id": row.get("DocID"), "reason": "extracted text not supplied"})
            continue
        meta = {"doc_id": row.get("DocID"), "bates": row.get("BegBates"), "bates_end": row.get("EndBates"),
                "custodian": row.get("Custodian"), "family_id": row.get("FamilyID"), "index_source": idx["id"],
                "text_path": row.get("TextPath")}
        priv = (row.get("Privilege") or "none").lower()
        s, _ = prov.add_source(store, matter_id, row.get("FileName") or row.get("DocID"), "other_text", body, meta,
                               confidentiality=(row.get("Confidentiality") or "confidential").lower().replace(" ", "_"),
                               privilege=priv if priv in ("none", "privileged", "withheld") else "privileged",
                               record="investigation")
        docs.append(s)
    return {"status": "imported", "source": idx, "documents": docs, "unsupported": missing}
