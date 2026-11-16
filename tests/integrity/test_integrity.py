import json, threading, unittest, urllib.request, urllib.error
from http.server import ThreadingHTTPServer
from tests.base import Base
from app import allegations, decisions, ingest, precedent, provenance as prov, server
from app.decisions import policy
from app.storage import Conflict, Invalid


class Integrity(Base):
    def test_removing_a_source_identifies_every_dependent(self):
        memo = self.src("okafor")
        dep = allegations.set_source_disabled(self.s, memo["id"], True, None, None, dry_run=True)["dependents"]
        self.assertIn(self.al["communicated"]["id"], [a["id"] for a in dep["allegations"]])
        self.assertEqual(len(dep["substitution_records"]), 3)
        self.assertEqual(len(dep["market_boundaries"]), 2)
        self.assertFalse(self.s.get(self.al["communicated"]["id"])["stale"])  # dry run changes nothing
        allegations.set_source_disabled(self.s, memo["id"], True, "t", "witness recanted")
        a = self.s.get(self.al["communicated"]["id"])
        self.assertTrue(a["stale"])
        allegations.verify(self.s, a["id"])
        self.assertEqual(self.row("communicated", "bexley")["status"], "unsupported")

    def test_disabling_source_invalidates_cached_classification(self):
        memo = self.src("okafor")
        sp = prov.find_span(self.s, memo["id"], "She did not attend and does not know who was present.")["id"]
        req = {"task": "knowledge_basis", "source_span_ids": [sp], "context_complete": True}
        r1 = decisions.run(self.s, self.mid, req)
        self.assertEqual(r1["label"], "hearsay")
        self.assertTrue(decisions.run(self.s, self.mid, req).get("replayed"))
        allegations.set_source_disabled(self.s, memo["id"], True, "t", "x")
        self.assertTrue(self.s.get(r1["id"])["invalidated"])
        self.assertEqual(decisions.run(self.s, self.mid, req)["route"], "blocked")

    def test_provider_timeout_abstains(self):
        class Slow:
            NAME = "slow"

            @staticmethod
            def classify(state):
                raise TimeoutError("timed out")
        sp = self.al["announced"]["support_span_ids"]
        r = decisions.run(self.s, self.mid, {"task": "date_role", "source_span_ids": sp, "context_complete": True}, Slow)
        self.assertEqual((r["route"], r["label"], r["proposed_label"]), ("abstain", None, None))
        self.assertIn("TimeoutError", r["error"])

    def test_policy_never_approves(self):
        st = {"blockers": [], "labels": ["a", "b"], "context_complete": True, "unresolved_attribution": False, "task": "t"}
        self.assertEqual(policy.decide(st, {"label": "a", "score": 0.99}, {"t": None})["route"], "proposed")
        self.assertEqual(policy.decide(st, {"label": "a", "score": 0.5}, {"t": 0.8})["route"], "abstain")
        self.assertEqual(policy.decide(st, {"label": "a", "score": 0.9}, {"t": 0.8})["route"], "proposed")
        self.assertEqual(policy.decide(st, {"label": "zzz"}, {})["route"], "abstain")
        self.assertEqual(policy.decide({**st, "context_complete": False}, {"label": "a"}, {})["route"], "review_required")
        self.assertEqual(policy.decide({**st, "blockers": ["bad checksum"]}, {"label": "a"}, {})["route"], "blocked")

    def test_tampered_span_blocks_promotion(self):
        sp = self.al["announced"]["support_span_ids"][0]
        self.s.q("UPDATE spans SET text='Effective May 1, 2024' WHERE id=?", (sp,))
        self.assertFalse(prov.verify_span(self.s, sp)["ok"])
        a = allegations.verify(self.s, self.al["announced"]["id"])
        self.assertTrue(a["verification"]["blocking"])
        with self.assertRaises(Invalid):
            allegations.guard_review(self.s, a, {"status": "approved"}, "fine")

    def test_quotation_must_exist_verbatim(self):
        with self.assertRaises(Invalid):
            prov.find_span(self.s, self.src("arden_price")["id"], "will increase prices by 9%")

    def test_legal_quotation_resolves_to_text_and_pin(self):
        r = precedent.resolve_quote("twombly", "an allegation of parallel conduct and a bare assertion of conspiracy will not suffice")
        self.assertTrue(r["ok"])
        self.assertEqual(r["pin"], "556")
        self.assertIn("550 U.S. 544, 556", r["cite"])
        self.assertFalse(precedent.resolve_quote("twombly", "parallel conduct is always enough")["ok"])
        self.assertFalse(precedent.resolve_quote("sd3", "anything")["ok"])

    def test_precedent_rows_are_issue_and_defendant_specific(self):
        sd3 = [r for r in precedent.search(circuit="4") if r["id"] == "sd3"]
        self.assertEqual({r["favorable_to"] for r in sd3}, {"plaintiff", "defendant"})
        self.assertTrue(all(r["favorable_to"] == "defendant" for r in precedent.unfavorable("plaintiff", "agreement_plausibility")))
        self.assertFalse(any("rate" in k or "percent" in k for r in precedent.search() for k in r))

    def test_imports_are_idempotent_and_unsupported_is_reported(self):
        f = self.src("arden_price")
        text = self.s.source(f["id"])["text"]
        n = len(self.s.sources(self.mid))
        r = ingest.import_file(self.s, self.mid, f["filename"], text, "price_letter")
        self.assertEqual(r["status"], "already_imported")
        self.assertEqual(len(self.s.sources(self.mid)), n)
        self.assertEqual(ingest.import_file(self.s, self.mid, "prod001.dat", "x", "discovery_export")["status"], "unsupported")

    def test_stale_edit_conflicts_over_http(self):
        server.Handler.store = self.s
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def post(path, body):
            req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
            try:
                return 200, json.load(opener.open(req))
            except urllib.error.HTTPError as e:
                return e.code, json.load(e)
        try:
            g = json.load(opener.open(f"{base}/api/matters/{self.mid}/graph"))
            self.assertEqual(len(g["allegations"]), 3)
            iss = g["issues"][0]
            body = {"target": iss["id"], "patch": {"status": "analyzed"}, "expected_rev": iss["rev"], "reviewer": "t"}
            self.assertEqual(post("/api/reviews", body)[0], 200)
            self.assertEqual(post("/api/reviews", body)[0], 409)
            self.assertEqual(post("/api/reviews", {**body, "expected_rev": None})[0], 422)
        finally:
            httpd.shutdown()

    def test_every_change_is_logged(self):
        with self.assertRaises(Conflict):
            self.s.update(self.ep["id"], {"question": "x"}, 1, "t")
        acts = self.s.reviews(self.mid)
        self.assertTrue(any(a["action"] == "approve_mapping" and a["reviewer"] == "R. Associate" for a in acts))


if __name__ == "__main__":
    unittest.main()
