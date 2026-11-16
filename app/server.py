"""Local HTTP server (stdlib only). Binds to 127.0.0.1; this is a single-user local tool,
not a hardened hosted service. Document text is data: nothing read from a source can
trigger a tool call, a network request, or a change to review rules."""
import json, mimetypes, os, pathlib, re, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from . import (allegations, agreement, conduct, decisions, entities, explanations, exports, ingest, markets,
               courtlistener, precedent, provenance as prov, quick, seed, transactions as tx)
from .storage import Store, Conflict, NotFound, Invalid
from . import hosting
from http.cookies import SimpleCookie

HOSTED = os.environ.get("PLUSFACTOR_HOSTED") == "1"
MAX_BODY = 30 * 1024 * 1024

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"
ROUTES = []
CREATABLE = {"entity": lambda s, m, d: entities.add_entity(s, m, d["legal_name"], d.get("role", "supplier"),
                                                           bool(d.get("defendant")), d.get("aliases", [])),
             "relation": lambda s, m, d: entities.add_relation(s, m, d["parent"], d["child"], d["type"], d.get("from"), d.get("to")),
             "event": conduct.add_event, "explanation": conduct.add_explanation, "agreement_item": agreement.add_item,
             "substitution": markets.add_substitution,
             "issue": lambda s, m, d: s.put("issue", {"issue": d["issue"], "status": d.get("status", "open"), "notes": d.get("notes", "")}, m)}


def route(method, pattern):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn))
        return fn
    return deco


def need(b, *keys):
    for k in keys:
        if b.get(k) in (None, ""):
            raise Invalid(f"missing required field: {k}")
    return [b[k] for k in keys]


@route("GET", "/api/matters")
def _matters(s, a, b, q):
    return [{k: m.get(k) for k in ("id", "name", "stage", "district", "theory", "synthetic")} for m in s.list("matter")]


@route("POST", "/api/matters")
def _new_matter(s, a, b, q):
    need(b, "name")
    return seed.new_matter(s, b)


@route("POST", "/api/demo")
def _demo(s, a, b, q):
    return seed.load(s)


@route("POST", "/api/analyze")
def _analyze_files(s, a, b, q):
    """Files and/or pasted details in, chart-ready result out."""
    files = b.get("files", []) + quick.from_form(b.get("form") or {})
    if not files and not (b.get("details") or "").strip():
        raise Invalid("Upload a file, fill in the table, or describe what happened.")
    adapter, consent = _adapter(b.get("use_jev"))
    out = quick.run(s, files, b.get("details", ""), adapter, consent)
    return {**out, "cases": {t: courtlistener.search(t) for t in ("agreement", "attribution")},
            "unfavorable": courtlistener.unfavorable()}


def _adapter(wanted):
    """Built-in local Jev engine by default; hosted TypeSafe Jev only if keyed and explicitly requested."""
    from .decisions import jev_adapter, typesafe_adapter
    if wanted == "typesafe" and typesafe_adapter.available():
        return typesafe_adapter, True
    return jev_adapter, False


@route("GET", "/api/status")
def _status(s, a, b, q):
    from .decisions import jev_adapter
    return {"engine": jev_adapter.NAME}


@route("POST", "/api/sample")
def _sample(s, a, b, q):
    out = quick.sample(s)
    return {**out, "cases": {t: courtlistener.search(t) for t in ("agreement", "attribution")},
            "unfavorable": courtlistener.unfavorable()}


@route("GET", "/api/taxonomies")
def _tax(s, a, b, q):
    d = precedent.DATA
    return {"matter": json.loads((d / "taxonomies" / "matter.json").read_text()), "import_kinds": ingest.TEXT_KINDS + ingest.TABLE_KINDS,
            "roles": tx.ROLES, "event_types": conduct.EVENT_TYPES, "acts": allegations.ACTS,
            "characterizations": allegations.CHARACTERIZATIONS, "explanation_kinds": explanations.KINDS,
            "ladder": agreement.LADDER, "sub_conditions": markets.SUB_CONDITIONS, "export_types": exports.TYPES,
            "circuits": json.loads((d / "jurisdiction_profiles" / "circuits.json").read_text())}


@route("GET", "/api/matters/([\\w-]+)/graph")
def _graph(s, a, b, q):
    mid = a[0]
    g = exports.graph(s, mid)
    g.pop("spans")
    for v in g["market_versions"]:
        v["summary"] = markets.summary(s, mid, v["rules"])
    g["registers"] = {e["id"]: explanations.register(s, e["id"]) for e in g["episodes"]}
    g["matrices"] = {e["id"]: agreement.matrix(s, e["id"]) for e in g["episodes"]}
    g["investigation_queue"] = allegations.investigation_queue(s, mid)
    g["review_queue"] = allegations.review_queue(s, mid)
    g["diff"] = allegations.diff_since_partner_review(s, mid)
    g["transaction_count"] = len(s.txns(mid))
    cited = {i for k in ("events", "substitutions", "explanations", "agreement_items", "allegations", "market_versions")
             for o in g[k] for i in allegations._span_ids(o)}
    g["cites"] = {i: prov.cite(s, i) for i in cited}
    return g


@route("GET", "/api/sources/([\\w-]+)")
def _source(s, a, b, q):
    src = s.source(a[0])
    return {**src, "spans": s.spans_of(a[0]), "history": s.reviews(src["matter_id"], a[0]),
            "integrity": prov.sha(src["text"]) == src["sha256"]}


@route("POST", "/api/sources/([\\w-]+)/disable")
def _disable(s, a, b, q):
    if not b.get("dry_run"):
        need(b, "reviewer", "reason")
    return allegations.set_source_disabled(s, a[0], b.get("disabled", True), b.get("reviewer"), b.get("reason"), bool(b.get("dry_run")))


@route("POST", "/api/sources/([\\w-]+)/flags")
def _flags(s, a, b, q):
    need(b, "reviewer")
    src = s.source(a[0], text=False)
    for k in ("reviewed", "record", "confidentiality", "privilege", "origin_group"):
        if k in b:
            s.q(f"UPDATE sources SET {k}=? WHERE id=?", (b[k], a[0]))
            s.log(src["matter_id"], a[0], "source", "flag", {k: src[k]}, {k: b[k]}, b["reviewer"], b.get("reason"))
    return s.source(a[0], text=False)


@route("POST", "/api/matters/([\\w-]+)/imports")
def _import(s, a, b, q):
    fn, content, kind = need(b, "filename", "content", "kind")
    flags = {k: b[k] for k in ("confidentiality", "privilege", "record") if b.get(k)}
    return ingest.import_file(s, a[0], fn, content, kind, b.get("meta"), b.get("texts"), **flags)


@route("POST", "/api/imports/([\\w-]+)/mappings")
def _mapping(s, a, b, q):
    mapping, formula = need(b, "mapping", "formula")
    return ingest.apply_mapping(s, a[0], mapping, formula, b.get("reviewer", "unassigned"))


@route("POST", "/api/matters/([\\w-]+)/markets")
def _market(s, a, b, q):
    name, rules, rat, rev = need(b, "name", "rules", "rationale", "reviewer")
    return markets.create_market(s, a[0], name, rules, rat, rev, b.get("boundaries", []))


@route("POST", "/api/markets/([\\w-]+)/versions")
def _version(s, a, b, q):
    rules, rat, rev, exp = need(b, "rules", "rationale", "reviewer", "expected_rev")
    return markets.add_version(s, a[0], rules, rat, rev, exp, b.get("boundaries"))


@route("POST", "/api/market-versions/([\\w-]+)/impact")
def _impact(s, a, b, q):
    return markets.impact(s, a[0], need(b, "rules")[0])


@route("POST", "/api/matters/([\\w-]+)/episodes")
def _episode(s, a, b, q):
    need(b, "question", "market_version_id", "window_from", "window_to")
    ep = s.put("episode", {"price_basis": "gross", "threshold": 0.5, "excluded": [], "stale": False,
                           "stale_reasons": [], **b}, a[0], b.get("reviewer", "unassigned"))
    conduct.analyze(s, ep["id"])
    return s.get(ep["id"])


@route("POST", "/api/episodes/([\\w-]+)/analyze")
def _analyze(s, a, b, q):
    return conduct.analyze(s, a[0])


@route("POST", "/api/matters/([\\w-]+)/allegations")
def _allegation(s, a, b, q):
    return allegations.verify(s, allegations.create(s, a[0], b, b.pop("reviewer", "unassigned"))["id"])


@route("POST", "/api/allegations/([\\w-]+)/verify")
def _verify(s, a, b, q):
    return allegations.verify(s, a[0])


@route("POST", "/api/matters/([\\w-]+)/objects")
def _create(s, a, b, q):
    kind, data = need(b, "kind", "data")
    if kind not in CREATABLE:
        raise Invalid(f"kind must be one of {sorted(CREATABLE)}")
    return CREATABLE[kind](s, a[0], data)


@route("POST", "/api/matters/([\\w-]+)/spans")
def _span(s, a, b, q):
    sid, quote = need(b, "source_id", "quote")
    return prov.find_span(s, sid, quote)


@route("POST", "/api/reviews")
def _review(s, a, b, q):
    """Every reviewed mutation: who, expected revision, old/new values, reason."""
    target, reviewer = need(b, "target", "reviewer")
    obj = s.get(target)
    if b.get("action") == "partner_review":
        s.log(obj["matter_id"], target, obj["kind"], "partner_review", None, None, reviewer, b.get("reason"))
        return {"ok": True}
    patch, exp = need(b, "patch", "expected_rev")
    for k in ("verification", "result", "stale", "stale_reasons", "superseded", "market_id", "n"):
        if k in patch:
            raise Invalid(f"{k} is computed and cannot be edited")
    if obj["kind"] == "market_version" and "rules" in patch:
        raise Invalid("market rules are immutable within a version; create a new version")
    if b.get("alias"):
        out = entities.approve_alias(s, target, b["alias"], b.get("reason"), reviewer, exp)
        ingest.remap_entities(s, obj["matter_id"])
        return out
    allegations.guard_review(s, obj, patch, b.get("reason"))
    return s.update(target, patch, exp, reviewer, b.get("reason"), b.get("action", "edit"))


@route("GET", "/api/matters/([\\w-]+)/history")
def _history(s, a, b, q):
    return s.reviews(a[0], (q.get("target") or [None])[0])[-200:]


@route("POST", "/api/matters/([\\w-]+)/decisions")
def _decide(s, a, b, q):
    if b.get("preview"):
        return decisions.preview(s, b["request"])
    adapter = decisions.offline_adapter
    if b.get("adapter") == "typesafe":
        from .decisions import typesafe_adapter as adapter
    return decisions.run(s, a[0], need(b, "request")[0], adapter)


@route("GET", "/api/authorities")
def _auth(s, a, b, q):
    g = lambda k: (q.get(k) or [None])[0]
    if g("unfavorable_for"):
        return precedent.unfavorable(g("unfavorable_for"), g("issue") or "agreement_plausibility", g("circuit"), g("posture"))
    return precedent.search(g("circuit"), g("posture"), g("issue"), g("favorable_to"))


@route("POST", "/api/authorities/([\\w-]+)/quote")
def _quote(s, a, b, q):
    return precedent.resolve_quote(a[0], need(b, "quote")[0])


@route("POST", "/api/matters/([\\w-]+)/exports")
def _export(s, a, b, q):
    etype = need(b, "type")[0]
    if etype not in exports.TYPES:
        raise Invalid(f"type must be one of {exports.TYPES}")
    return exports.export(s, a[0], etype, b.get("format", "md"), b.get("profile"), b.get("reviewer", "unassigned"))


class Handler(BaseHTTPRequestHandler):
    store = None
    spaces = hosting.Workspaces()

    def _user(self):
        c = SimpleCookie(self.headers.get("Cookie") or "")
        return hosting.verify(c[hosting.COOKIE].value) if hosting.COOKIE in c else None

    def _cookie(self, value, age):
        local = (self.headers.get("Host") or "").split(":")[0] in ("127.0.0.1", "localhost")
        secure = "" if local else " Secure;"  # HTTPS-only everywhere except a local preview over http
        self._extra = [("Set-Cookie", f"{hosting.COOKIE}={value}; Path=/; HttpOnly; SameSite=Strict;{secure} Max-Age={age}")]

    def _auth(self, path, body):
        """Hosted-mode session endpoints. Returns True if the request was handled here."""
        if path == "/api/login":
            if not hosting.check(body.get("email"), body.get("password")):
                time.sleep(1)
                self._send(401, {"error": "Email or password not recognised."})
                return True
            self._cookie(hosting.sign(body["email"].strip().lower()), 12 * 3600)
            self._send(200, {"email": body["email"].strip().lower()})
            return True
        if path == "/api/logout":
            u = self._user()
            if u:
                self.spaces.drop(u)  # discard the workspace immediately
            self._cookie("", 0)
            self._send(200, {"ok": True})
            return True
        if path == "/api/me":
            u = self._user()
            self._send(200 if u else 401, {"email": u, "hosted": True} if u else {"error": "sign in required"})
            return True
        return False

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        if HOSTED:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        for k, v in getattr(self, "_extra", []):
            self.send_header(k, v)
        self._extra = []
        self.end_headers()
        self.wfile.write(data)

    def _handle(self, method):
        host = (self.headers.get("Host") or "").split(":")[0]
        if not HOSTED and host not in ("127.0.0.1", "localhost"):
            return self._send(403, {"error": "local access only"})
        u = urlparse(self.path)
        if not u.path.startswith("/api/"):
            if method != "GET":
                return self._send(405, {"error": "method not allowed"})
            f = (WEB / (u.path.lstrip("/") or "index.html")).resolve()
            if WEB not in f.parents or not f.is_file():
                return self._send(404, {"error": "not found"})
            return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._send(413, {"error": "Upload exceeds 30 MB."})
            body = json.loads(self.rfile.read(n) or b"{}") if method == "POST" else {}
            store = self.store
            if HOSTED:
                user = self._user()
                if not user and hosting.open_mode():  # no accounts: give this visitor a private workspace
                    user = "visitor-" + hosting.secrets.token_hex(12)
                    self._cookie(hosting.sign(user, 24), 24 * 3600)
                if u.path == "/api/me" and hosting.open_mode():
                    return self._send(200, {"email": None, "hosted": True, "open": True})
                if self._auth(u.path, body):
                    return
                if not user:
                    return self._send(401, {"error": "sign in required"})
                store = self.spaces.get(user)
            elif u.path == "/api/me":
                return self._send(200, {"email": None, "hosted": False})
            for m, rx, fn in ROUTES:
                hit = rx.match(u.path)
                if m == method and hit:
                    out = fn(store, hit.groups(), body, parse_qs(u.query))
                    if method == "POST":
                        for mt in store.list("matter"):
                            allegations.refresh(store, mt["id"])
                    return self._send(200, out)
            self._send(404, {"error": "no such endpoint"})
        except Conflict as e:
            self._send(409, {"error": str(e), "conflict": True})
        except NotFound as e:
            self._send(404, {"error": f"not found: {e}"})
        except (Invalid, KeyError, ValueError) as e:
            self._send(422, {"error": str(e)})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


def _load_env():
    """Read KEY=value lines from a local .env file (git-ignored) without overriding the shell."""
    p = pathlib.Path(__file__).resolve().parents[1] / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            k, sep, v = line.strip().partition("=")
            if sep and k and not k.startswith("#"):
                os.environ.setdefault(k.strip().removeprefix("export ").strip(), v.strip().strip('"').strip("'"))


def main():
    _load_env()
    global HOSTED
    HOSTED = os.environ.get("PLUSFACTOR_HOSTED") == "1"
    port = int(os.environ.get("PORT") or os.environ.get("PLUSFACTOR_PORT", 8765))
    if HOSTED:
        who = "open to anyone with the link" if hosting.open_mode() else f"{len(hosting.users())} named user(s)"
        print(f"Plus Factor (hosted, {who}) listening on 0.0.0.0:{port}")
        ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
        return
    Handler.store = Store(os.environ.get("PLUSFACTOR_DB", "plusfactor.db"))
    if "--demo" in sys.argv and not Handler.store.list("matter"):
        seed.load(Handler.store)
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        if e.errno in (48, 98):  # macOS / Linux "address already in use"
            sys.exit(f"Port {port} is already in use (an earlier Plus Factor is probably still running).\n"
                     f"Stop it with:  lsof -ti:{port} | xargs kill\n"
                     f"or use another port:  PLUSFACTOR_PORT=8766 python3 -m app.server")
        raise
    print(f"Plus Factor on http://127.0.0.1:{port} (local only)")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
