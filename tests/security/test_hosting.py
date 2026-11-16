import json, os, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from app import hosting, server


class Hosted(unittest.TestCase):
    def setUp(self):
        self.env = dict(os.environ)
        os.environ.update(PLUSFACTOR_SECRET="test-secret", PLUSFACTOR_USERS=";".join(
            f"{u}:{hosting.hash_password('correct horse battery')}" for u in ("a@firm.com", "b@firm.com")))
        server.HOSTED = True
        server.Handler.spaces = hosting.Workspaces()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        server.HOSTED = False
        os.environ.clear()
        os.environ.update(self.env)

    def call(self, path, body=None, cookie=None):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode() if body is not None else None,
                                     {"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})})
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            r = op.open(req)
            return r.status, json.load(r), r.headers.get("Set-Cookie")
        except urllib.error.HTTPError as e:
            return e.code, json.load(e), None

    def sign_in(self, who):
        st, _, ck = self.call("/api/login", {"email": who, "password": "correct horse battery"})
        self.assertEqual(st, 200)
        self.assertIn("HttpOnly", ck)
        self.assertIn("SameSite=Strict", ck)
        return ck.split(";")[0]

    def test_requires_sign_in(self):
        self.assertEqual(self.call("/api/sample", {})[0], 401)
        self.assertEqual(self.call("/api/login", {"email": "a@firm.com", "password": "wrong"})[0], 401)
        self.assertEqual(self.call("/api/me", cookie="pf_session=forged")[0], 401)

    def test_users_cannot_see_each_others_documents(self):
        a, b = self.sign_in("a@firm.com"), self.sign_in("b@firm.com")
        st, res, _ = self.call("/api/sample", {}, a)
        self.assertEqual(st, 200)
        src = res["files"][0]["id"]
        self.assertEqual(self.call(f"/api/sources/{src}", cookie=a)[0], 200)
        self.assertEqual(self.call(f"/api/sources/{src}", cookie=b)[0], 404)
        self.call("/api/logout", {}, a)
        self.assertNotIn("a@firm.com", server.Handler.spaces.stores)  # workspace discarded on sign-out


class OpenAccess(Hosted):
    def setUp(self):
        super().setUp()
        os.environ.pop("PLUSFACTOR_USERS")

    def test_no_sign_in_but_visitors_are_isolated(self):
        st, me, a = self.call("/api/me")
        self.assertEqual(st, 200)
        st, res, a2 = self.call("/api/sample", {})
        self.assertEqual(st, 200)
        a = a2.split(";")[0]  # visitor cookie issued on first use
        src = res["files"][0]["id"]
        _, _, b = self.call("/api/me")
        self.assertEqual(self.call(f"/api/sources/{src}", cookie=a)[0], 200)                   # own document
        self.assertEqual(self.call(f"/api/sources/{src}", cookie=b.split(";")[0])[0], 404)   # another visitor cannot see it

    test_requires_sign_in = None
    test_users_cannot_see_each_others_documents = None


if __name__ == "__main__":
    unittest.main()
