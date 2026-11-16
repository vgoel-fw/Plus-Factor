import unittest
from tests.base import Base
from app import allegations, conduct, decisions, entities, markets, provenance as prov, transactions as tx
from app.storage import Invalid


class Analytical(Base):
    def test_announcement_is_never_implementation(self):
        r = self.row("implemented", "bexley")
        self.assertEqual(r["status"], "unverified")
        self.assertIn("implementation unverified", r["gap"])
        ev = next(e for e in self.s.list("event", self.mid) if e["type"] == "announcement")
        with self.assertRaises(Invalid):
            allegations.guard_review(self.s, ev, {"type": "first_transaction"}, None)
        self.assertFalse(any(e["type"] == "first_transaction" for e in self.s.list("event", self.mid)))

    def test_parent_not_attributed_without_approved_basis(self):
        self.assertEqual(self.row("implemented", "corvane_h")["status"], "unsupported_attribution")
        rel = next(r for r in self.s.list("relation", self.mid) if r["type"] == "parent_of")
        with self.assertRaises(Invalid):
            allegations.guard_review(self.s, rel, {"attribution": "approved"}, None)
        self.s.update(rel["id"], {"attribution": "approved", "basis": "Parent set subsidiary list prices"}, rel["rev"], "t")
        allegations.verify(self.s, self.al["implemented"]["id"])
        r = self.row("implemented", "corvane_h")
        self.assertEqual(r["status"], "exceptions")
        self.assertIn("approved mapping", r["via"])

    def test_trade_name_does_not_resolve_without_approval(self):
        self.assertEqual(entities.resolve(self.s, self.mid, "NAAC")[0], None)
        self.assertEqual(entities.resolve(self.s, self.mid, "Corvane")[0], self.ent["corvane"])

    def test_missing_invoices_remain_a_coverage_gap(self):
        lanes = self.ep["result"]["lanes"]
        b = lanes[self.ent["bexley"]]
        self.assertEqual(b["implementation"]["status"], "unverified")
        self.assertIn("2024-05", b["coverage"]["gap_months"])
        self.assertEqual(lanes[self.ent["fenwick"]]["records"], "none supplied")
        self.assertEqual(self.ep["result"]["denominator"]["no_records"], 1)

    def test_missing_rebate_is_not_zero(self):
        miss = [t["norm"] for t in self.s.txns(self.mid) if "rebate" in t["norm"]["missing"]]
        self.assertEqual(len(miss), 3)
        self.assertTrue(all(n["net_unit_price"] is None and n["gross_unit_price"] for n in miss))

    def test_equivalent_units_compare_equal(self):
        m = {"vendor": "v", "date": "d", "quantity": "q", "unit": "u", "amount": "a"}
        f = {"components": {"amount": 1}, "per": "lb"}
        kg = tx.normalize({"v": "X", "d": "2024-01-01", "q": "1000", "u": "KG", "a": "1760"}, m, f)
        lb = tx.normalize({"v": "X", "d": "2024-01-01", "q": "2204.6226218", "u": "LB", "a": "1760"}, m, f)
        self.assertAlmostEqual(kg["net_unit_price"], lb["net_unit_price"], places=5)
        with self.assertRaises(Invalid):
            tx.normalize({"v": "X", "d": "2024-01-01", "q": "1", "u": "drums", "a": "1"}, m, f)

    def test_common_effective_date_distinct_from_common_decision(self):
        r = self.ep["result"]
        self.assertEqual(r["lags_days"]["effective"], [0, 0])
        self.assertEqual(r["lags_days"]["announcement"], [21, 21])
        self.assertEqual(r["flags"][0]["flag"], "same_effective_date_different_decisions")
        self.assertEqual({e["type"] for l in r["lanes"].values() for e in l["events"]} >= {"decision", "announcement", "effective"}, True)

    def test_uncertain_dates_stay_intervals(self):
        self.assertEqual(prov.parse_date("Spring 2024"), ("2024-03-01", "2024-05-31", "season"))
        u = self.ep["result"]["uncertain_dates"][0]
        self.assertEqual(u["interval"], ["2023-09-01", "2023-11-30"])

    def test_market_revision_marks_dependents_stale(self):
        v = self.s.get(self.ep["market_version_id"])
        mk = self.s.get(v["market_id"])
        prev = markets.impact(self.s, v["id"], {**v["rules"], "origins": []})
        self.assertEqual(prev["suppliers_introduced"], ["Delmar Import Trading"])
        self.assertEqual(len(prev["stale_allegations"]), 3)
        self.assertFalse(prev["episodes"][0]["synchronization_persists"])
        markets.add_version(self.s, mk["id"], {**v["rules"], "origins": []}, "add imports", "t", mk["rev"])
        allegations.refresh(self.s, self.mid)
        self.assertTrue(self.s.get(self.ep["id"])["stale"])
        self.assertTrue(all(a["stale"] for a in self.s.list("allegation", self.mid)))
        with self.assertRaises(Invalid):
            allegations.guard_review(self.s, self.s.get(self.al["announced"]["id"]), {"status": "approved"}, "ok")

    def test_market_cannot_be_defined_by_defendants(self):
        with self.assertRaises(Invalid):
            markets.check_rules({"requirement": "x", "suppliers": ["ent-0001"]})
        with self.assertRaises(Invalid):
            markets.check_rules({"families": ["citric_acid"]})

    def test_duplicate_reporting_is_one_origin(self):
        a, b = self.src("acidulant_weekly"), self.src("food_ingredient_wire")
        self.assertEqual(a["origin_group"], b["origin_group"])
        from app import agreement
        it = next(i for i in agreement.matrix(self.s, self.ep["id"]) if i["category"] == "association_contact")
        self.assertEqual((it["documents"], it["independent_origins"]), (2, 1))

    def test_association_ladder_is_not_communication(self):
        self.assertEqual(self.row("communicated", "arden")["status"], "unsupported")
        self.assertIn("different proposition", self.row("communicated", "corvane")["gap"])
        self.assertEqual(self.row("communicated", "bexley")["status"], "attributed_account")

    def test_negation_and_other_lawsuits(self):
        sp = lambda part, q: prov.find_span(self.s, self.src(part)["id"], q)["id"]
        run = lambda task, span, text=None: decisions.run(self.s, self.mid, {
            "task": task, "assertion_text": text, "source_span_ids": [span], "context_complete": True})
        neg = run("assertion_support", sp("corvane_price", "Corvane has not discussed this adjustment with any competitor."),
                  "Corvane discussed this adjustment with a competitor.")
        self.assertEqual(neg["label"], "contradicts")
        other = sp("acidulant_weekly", "In an unrelated lawsuit concerning lysine, plaintiffs alleged that producers agreed to fix prices.")
        self.assertEqual(run("passage_kind", other)["label"], "other_case")
        self.assertEqual(run("assertion_support", other, "Producers agreed to fix prices.")["label"], "does_not_address")
        ann = run("assertion_support", sp("bexley_price", "Effective April 1, 2024, prices for food-grade citric acid will increase by 8%."),
                  "Bexley implemented the increase on April 1, 2024.")
        self.assertEqual(ann["label"], "does_not_address")
        self.assertTrue(all(r["route"] != "approved" and r["review_required"] for r in (neg, ann)))


class Quick(unittest.TestCase):
    def test_files_in_charts_out(self):
        from app.storage import Store
        from app import quick
        s = Store()
        r = quick.sample(s)
        self.assertEqual(len(r["conduct"]["series"]), 3)
        self.assertEqual([(m["baseline"], m["pattern_holds"]) for m in r["markets"]], [(True, True), (False, False), (False, True), (False, False)])
        self.assertEqual(r["markets"][1]["added"], ["Delmar Import Trading"])
        self.assertIn("Delmar Import Trading", r["markets"][1]["did_not_move"])
        self.assertTrue(any("ARDEN CHEMICAL" in a for a in r["assumptions"]))   # name match is disclosed
        self.assertTrue(all(c["route"] != "approved" for c in r["checks"]))
        self.assertTrue(any(x["kind"] == "other_case" for x in r["statements"]))
        only = quick.run(s, [{"filename": "scan.pdf", "content": "x"}], "From: Acme Co.\nDate: May 1, 2024\nEffective June 1, 2024 prices increase by 5%.")
        self.assertIsNone(only["conduct"])
        self.assertEqual(only["skipped"][0]["file"], "scan.pdf")
        self.assertEqual(len(only["events"]), 2)
        s.db.close()

    def test_no_documents_needed(self):
        from app.storage import Store
        from app import quick
        s = Store()
        rows = [{"name": "Arden", "announced": "2024-02-12", "effective": "2024-04-01", "pct": "8", "before": "0.80", "after": "0.864"},
                {"name": "Bexley", "announced": "2024-02-20", "effective": "2024-04-01", "pct": "8"},
                {"name": "Corvane", "announced": "2024-03-04", "effective": "2024-04-01", "pct": "7.5", "before": "0.82", "after": "0.82"}]
        r = quick.run(s, quick.from_form({"product": "citric acid", "suppliers": rows}))
        st = {l["name"]: l["implementation"]["status"] for l in r["conduct"]["lanes"].values()}
        self.assertEqual(st, {"Arden": "observed", "Bexley": "no_transactions", "Corvane": "not_observed"})
        self.assertTrue(r["markets"][0]["baseline"] and r["markets"][0]["pattern_holds"])
        s.db.close()

    def test_jev_gate_follows_jev_tools(self):
        from app.decisions import policy
        st = {"blockers": [], "labels": ["a"], "context_complete": True, "unresolved_attribution": False, "task": "t"}
        self.assertEqual(policy.decide(st, {"label": "a", "score": 0.79}, {})["route"], "abstain")
        self.assertEqual(policy.decide(st, {"label": "a", "score": 0.81}, {})["route"], "proposed")


class BuiltInJev(unittest.TestCase):
    def test_jev_shaped_answers(self):
        from app import jev
        r = jev.system_one({"passages": ["She stated that she heard from a former colleague that suppliers discussed pricing."]},
                           {"knowledge_basis": jev.Choice("basis?", {"firsthand": None, "hearsay": None, "mixed": None, "unknown": None})})
        a = r["choices"]["knowledge_basis"]
        self.assertEqual(a["choice"], "hearsay")
        self.assertAlmostEqual(sum(a["probabilities"].values()), 1, places=2)
        self.assertEqual(a["confidence"], max(a["probabilities"].values()))

    def test_leave_one_out_is_reported_honestly(self):
        from app import jev
        from app.decisions.questions import QUESTIONS
        for task, q in QUESTIONS.items():
            rows = jev.examples(task)
            hits = sum(max((m := jev.train(task, q["labels"], rows[:i] + rows[i + 1:]).predict(jev._feats(task, r))), key=m.get) == r["y"]
                       for i, r in enumerate(rows))
            self.assertGreater(hits / len(rows), 0.5, task)  # far above chance; not a validation of legal accuracy

if __name__ == "__main__":
    unittest.main()
