"""Load the SYNTHETIC demonstration matter from tests/fixtures/synthetic/.
Every party, document and number is invented test material."""
import pathlib
from . import entities as E, ingest, markets, conduct, agreement, allegations, provenance as prov, transactions as tx

FIX = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "synthetic"
ISSUES = ["standing", "antitrust_injury", "limitations", "jurisdiction", "class_issues"]


def new_matter(store, data):
    m = store.put("matter", data, None, data.get("created_by", "unassigned"))
    for i in ISSUES:
        store.put("issue", {"issue": i, "status": "open - not analyzed here", "notes": ""}, m["id"])
    return m


def load(store):
    m = new_matter(store, {
        "name": "Halcyon Beverage Co. v. Arden Chemical Co. et al.", "synthetic": True,
        "district": "D. Del.", "circuit": "3", "state_claims": "unknown", "research_cutoff": "2024-06-30",
        "stage": "amended_complaint", "restraint": "price_fixing", "theory": "per_se",
        "theory_note": "Per se asserted for the alleged naked price agreement; rule of reason pleaded in the "
                       "alternative. Market context is developed without importing merger-style analysis as a prerequisite.",
        "theory_authority_ids": ["alston", "twombly"], "purchaser_position": "direct_purchaser",
        "conduct_period": "2024-02 to unknown", "data_period": "2023-10 to 2024-09",
        "comparison_periods": "2023-10 to 2024-03 (pre); 2024-04 to 2024-09 (post)",
        "working_scope": "Food-grade citric acid; United States; beverage manufacturers; direct sales. Boundaries unknown.",
        "deliverable": "agreement_allegations", "provider_permission": "local_only",
        "product_terms": {"citric_acid": ["citric acid"], "malic_acid": ["malic acid"]}})
    mid = m["id"]
    ent = {}
    for key, name, role, d, al in [
            ("arden", "Arden Chemical Co.", "supplier", True, ["ARDEN CHEMICAL"]),
            ("bexley", "Bexley Ingredients LLC", "supplier", True, []),
            ("corvane", "Corvane Acidulants Inc.", "supplier", True, ["Corvane"]),
            ("holdings", "Corvane Holdings plc", "parent", True, ["Corvane"]),
            ("delmar", "Delmar Import Trading", "supplier", False, []),
            ("estwick", "Estwick Organics", "supplier", False, []),
            ("fenwick", "Fenwick Citrates Co.", "supplier", False, []),
            ("halcyon", "Halcyon Beverage Co.", "purchaser", False, []),
            ("naac", "North American Acidulants Council", "association", False, ["NAAC"])]:
        ent[key] = E.add_entity(store, mid, name, role, d, al)["id"]
    for k, alias, basis in (("arden", "ARDEN CHEMICAL", "Remit-to name and address on invoices match Arden Chemical Co."),
                            ("corvane", "Corvane", "Invoices are issued by, and remit to, Corvane Acidulants Inc.")):
        E.approve_alias(store, ent[k], alias, basis, "R. Associate", store.get(ent[k])["rev"])
    E.add_relation(store, mid, ent["holdings"], ent["corvane"], "parent_of", "2018-01-01")
    for k in ("arden", "bexley", "corvane"):
        E.add_relation(store, mid, ent["naac"], ent[k], "member_of")

    src = {}
    for fn, kind, conf, priv in [
            ("halcyon_ap_export.csv", "ap_export", "confidential", "none"),
            ("arden_price_letter.txt", "price_letter", "confidential", "none"),
            ("bexley_price_letter.txt", "price_letter", "confidential", "none"),
            ("corvane_price_letter.txt", "price_letter", "confidential", "none"),
            ("bexley_supply_agreement.txt", "contract", "confidential", "none"),
            ("okafor_interview_memo.txt", "interview_memo", "highly_confidential", "privileged"),
            ("trade_article_acidulant_weekly.txt", "trade_article", "public", "none"),
            ("trade_article_food_ingredient_wire.txt", "trade_article", "public", "none"),
            ("arden_q4_earnings_call.txt", "public_statement", "public", "none")]:
        r = ingest.import_file(store, mid, fn, (FIX / fn).read_text(), kind, {"synthetic": True},
                               confidentiality=conf, privilege=priv)
        src[fn.split(".")[0]] = r["source"]["id"]
        if r["status"] == "needs_mapping":
            ingest.apply_mapping(store, r["source"]["id"], r["proposed_mapping"], tx.DEFAULT_FORMULA, "R. Associate")
    sp = lambda s, needle: prov.find_span(store, src[s], needle)["id"]
    row = lambda sku, n=0: [t["span_id"] for t in store.txns(mid) if t["norm"]["sku"] == sku][n]
    for e in store.list("event", mid):  # Arden's two letter events have been attorney-reviewed
        if e["actor"] == ent["arden"]:
            store.update(e["id"], {"status": "reviewed"}, e["rev"], "R. Associate", "Checked against letter", "approve")
    conduct.add_event(store, mid, {
        "type": "decision", "actor": ent["arden"], "family": "citric_acid", "grades": ["food"], "date_text": "fall 2023",
        "date_basis": "speaker's statement on earnings call; no document dates the decision",
        "note": "Speaker describes planning that predates the association meeting",
        "span_ids": [sp("arden_q4_earnings_call", "We have been planning a price action in acidulants since fall 2023")]})
    conduct.add_event(store, mid, {
        "type": "exception", "actor": ent["corvane"], "family": "citric_acid", "grades": ["food"], "date_text": "2024-03-04",
        "date_basis": "letter date", "note": "Fixed-price customers exempt",
        "span_ids": [sp("corvane_price_letter", "Customers under fixed-price agreements through 2024 are exempt from this increase.")]})

    memo = "okafor_interview_memo"
    base = {"requirement": "Halcyon requires food-grade citric acid meeting its beverage specification, delivered to "
                           "its U.S. plants.", "families": ["citric_acid"], "grades": ["food"], "origins": ["domestic"],
            "customer_group": "U.S. beverage manufacturers", "channel": "direct",
            "candidate_suppliers": [ent[k] for k in ("arden", "bexley", "corvane", "fenwick")]}
    v1 = markets.create_market(store, mid, "Food-grade citric acid sold to U.S. beverage manufacturers", base,
                               "Starts from the client's specification and qualified sources.", "R. Associate", [
        {"id": "b1", "statement": "Exclude industrial-grade product", "status": "approved with objection retained",
         "support_span_ids": [sp(memo, "Halcyon's beverage specification prohibits the impurity level found in industrial-grade citric acid")],
         "contra_span_ids": [row("CA-IND-50", 0), row("CA-IND-50", 1)],
         "unresolved": "Whether the two industrial-grade purchases served the same application."},
        {"id": "b2", "statement": "Exclude imported product", "status": "proposed",
         "support_span_ids": [sp(memo, "qualifying an imported source takes nine months of certification testing")],
         "contra_span_ids": [row("DM-CA-IMP", 2)],
         "unresolved": "Regular imported volume begins June 2024, sooner than nine months after trials began."}])
    markets.create_market(store, mid, "All food-grade citric acid sold in the United States",
                          {**base, "origins": [], "customer_group": "All U.S. purchasers",
                           "candidate_suppliers": base["candidate_suppliers"] + [ent["delmar"]]},
                          "Tests whether imports constrain domestic pricing.", "R. Associate")
    markets.create_market(store, mid, "Acidulants available to the same purchasers",
                          {**base, "families": ["citric_acid", "malic_acid"], "origins": [],
                           "candidate_suppliers": base["candidate_suppliers"] + [ent["delmar"], ent["estwick"]]},
                          "Broadest alternative a defendant is likely to propose.", "R. Associate")
    for prod, app, per, summ, needle, cond in [
            ("Industrial-grade citric acid", "Carbonated beverage line", "2023-2024",
             "Rejected: specification prohibits the impurity level.",
             "Halcyon's beverage specification prohibits the impurity level found in industrial-grade citric acid",
             {"technically_usable": "partial", "commercially_available": "yes", "qualified_for_application": "no",
              "economically_attractive": "yes"}),
            ("Imported food-grade citric acid (Delmar)", "Carbonated beverage line", "Feb 2024 onward",
             "Trials began February 2024; qualification said to take nine months; regular purchases from June 2024.",
             "she personally began qualification trials of imported food-grade product from Delmar Import Trading in February 2024",
             {"technically_usable": "yes", "commercially_available": "yes", "qualified_for_application": "partial",
              "economically_attractive": "yes", "purchased_after_price_change": "yes"}),
            ("Malic acid", "Carbonated beverage line", "undated",
             "Rejected: changes the flavor profile.", "malic acid changes the flavor profile and was rejected",
             {"technically_usable": "partial", "commercially_available": "yes", "qualified_for_application": "no"})]:
        markets.add_substitution(store, mid, {"buyer": ent["halcyon"], "candidate_product": prod, "application": app,
                                              "period": per, "summary": summ, "conditions": cond,
                                              "span_ids": [sp(memo, needle)]})

    ep = store.put("episode", {
        "question": "Did Arden, Bexley and Corvane announce comparable increases on food-grade citric acid for the "
                    "same customers within February-April 2024?",
        "market_version_id": v1["id"], "window_from": "2023-09-01", "window_to": "2024-09-30", "price_basis": "gross",
        "threshold": 0.5, "excluded": [], "stale": False, "stale_reasons": []}, mid, "R. Associate")
    conduct.analyze(store, ep["id"])
    C, P, CP = "client_records", "public_source", "compulsory_process"
    conduct.add_explanation(store, mid, {
        "episode_id": ep["id"], "kind": "contract_escalation",
        "mechanism": "Annual April 1 index adjustment under supply contracts would produce a common effective date "
                     "without a common decision.",
        "timing": "Each April 1", "span_ids": [sp("bexley_supply_agreement", "On each April 1, the price shall be adjusted by the percentage change in the Corn Dextrose Index")],
        "affected": [{"entity_id": ent["bexley"], "status": "documented", "note": "Section 4.2 links price to the index"},
                     {"entity_id": ent["arden"], "status": "not_supplied"}, {"entity_id": ent["corvane"], "status": "not_supplied"}],
        "unresolved": [{"text": "Halcyon's supply contracts with Arden and Corvane (renewal date, escalation terms)", "route": C},
                       {"text": "Corn Dextrose Index movement for the twelve months before April 2024", "route": P}]})
    conduct.add_explanation(store, mid, {
        "episode_id": ep["id"], "kind": "energy_freight",
        "mechanism": "Energy and freight cost increases stated as the reason for Arden's adjustment.",
        "timing": "unknown", "span_ids": [sp("arden_price_letter", "This adjustment is due to sustained increases in energy and freight costs.")],
        "affected": [{"entity_id": ent["arden"], "status": "asserted", "note": "Stated in letter; not independently documented"},
                     {"entity_id": ent["bexley"], "status": "not_supplied"}, {"entity_id": ent["corvane"], "status": "not_supplied"}],
        "assumptions": "Pass-through is not assumed uniform: hedging, inventory and input intensity may differ by firm.",
        "unresolved": [{"text": "Published energy and freight indices for 2023-2024", "route": P}]})
    store.log(mid, mid, "matter", "partner_review", None, None, "J. Partner", "Reviewed market v1 and episode")

    agreement.add_item(store, mid, {
        "episode_id": ep["id"], "category": "future_pricing_communication", "source_label": "Interview memorandum",
        "summary": "Bexley sales representative told Halcyon that all suppliers were increasing by eight percent.",
        "actors": [{"entity_id": ent["bexley"], "person": "Unidentified sales representative", "employer_at_time": "Bexley (per witness)"}],
        "recipients": "Maria Okafor, Halcyon (a customer, not a competitor)",
        "language": "Everyone is going up eight. You won't find it cheaper elsewhere.",
        "information_tense": "future", "when_text": "March 2024 (day unknown); after the Arden and Bexley letters",
        "how_known": "witness_firsthand", "followed": "Corvane announced 7.5% on March 4, 2024.",
        "cuts_other_way": ["Arden's and Bexley's letters were already with customers; the remark may repeat public announcements",
                           "Made to a customer; it is not itself a competitor-to-competitor communication"],
        "missing": [{"text": "Identity of the Bexley representative and the date of the call", "route": "interview"},
                    {"text": "How the representative knew competitors' pricing intentions", "route": CP}],
        "span_ids": [sp(memo, "Okafor stated that a Bexley sales representative told her by phone in March 2024: \"Everyone is going up eight. You won't find it cheaper elsewhere.\"")],
        "contra_span_ids": [sp("corvane_price_letter", "Corvane has not discussed this adjustment with any competitor.")]})
    art = "The North American Acidulants Council held its annual meeting on January 23-24, 2024 in Phoenix.\nExecutives from Arden Chemical Co. and Bexley Ingredients LLC appeared as panelists on the outlook session.\nCorvane Acidulants Inc. is a member of the Council."
    agreement.add_item(store, mid, {
        "episode_id": ep["id"], "category": "association_contact", "source_label": "Trade press",
        "summary": "NAAC annual meeting, January 23-24, 2024, about three weeks before the first announcement.",
        "actors": [{"entity_id": ent["arden"], "ladder": "documented_attendance"},
                   {"entity_id": ent["bexley"], "ladder": "documented_attendance"},
                   {"entity_id": ent["corvane"], "ladder": "membership"}],
        "information_tense": "unknown", "when_text": "January 23-24, 2024", "how_known": "original_document",
        "followed": "Announcements on Feb 12, Feb 20 and Mar 4, 2024.",
        "cuts_other_way": ["Arden's CFO dates its planning to fall 2023, before the meeting",
                           "The only account of a pricing discussion is secondhand; the witness did not attend"],
        "missing": [{"text": "Attendee list and agenda for the January 2024 NAAC meeting", "route": P},
                    {"text": "Whether pricing was discussed at or around the meeting", "route": CP}],
        "span_ids": [sp("trade_article_acidulant_weekly", art), sp("trade_article_food_ingredient_wire", art)],
        "contra_span_ids": [sp(memo, "She did not attend and does not know who was present.")]})

    letters = [sp(f"{k}_price_letter", "Effective April 1, 2024") for k in ("arden", "bexley", "corvane")]
    defs = [ent[k] for k in ("arden", "bexley", "corvane")]
    for d in [
        {"text": "Defendants announced price increases of 7.5 to 8 percent on food-grade citric acid between February 12 "
                 "and March 4, 2024, each effective April 1, 2024.", "act": "announced", "defendants": defs,
         "support_span_ids": letters, "authority_ids": ["twombly"]},
        {"text": "Each Defendant implemented the announced increase on April 1, 2024.", "act": "implemented",
         "defendants": defs + [ent["holdings"]], "support_span_ids": letters,
         "contra_span_ids": [sp("corvane_price_letter", "Customers under fixed-price agreements through 2024 are exempt from this increase.")],
         "authority_ids": ["sd3"]},
        {"text": "Defendants communicated with one another about future prices before announcing the increases.",
         "act": "communicated", "defendants": defs, "characterization": "information_and_belief",
         "belief_basis": "Statement of a Bexley sales representative to Plaintiff's procurement director in March 2024.",
         "support_span_ids": [sp(memo, "Everyone is going up eight. You won't find it cheaper elsewhere.")],
         "contra_span_ids": [sp("corvane_price_letter", "Corvane has not discussed this adjustment with any competitor."),
                             sp("arden_q4_earnings_call", "We have been planning a price action in acidulants since fall 2023")],
         "authority_ids": ["twombly", "text_messaging", "musical_instruments"]}]:
        d["episode_id"] = ep["id"]
        allegations.verify(store, allegations.create(store, mid, d, "R. Associate")["id"])
    return store.get(mid)
