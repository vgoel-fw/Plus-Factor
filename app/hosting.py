"""Hosted (multi-user) mode: named users, signed session cookies, and a private in-memory
workspace per user that is never written to disk and is discarded after inactivity.

Configuration (environment):
  PLUSFACTOR_HOSTED=1          enable hosted mode
  PLUSFACTOR_USERS             "email:pbkdf2$...;email2:pbkdf2$..."  (make lines with scripts/add_user.py)
  PLUSFACTOR_SECRET            long random string used to sign sessions
  PLUSFACTOR_IDLE_HOURS        workspace lifetime after last use (default 4)
"""
import base64, hashlib, hmac, os, secrets, threading, time
from .storage import Store

ITER = 240_000
COOKIE = "pf_session"


def hash_password(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), ITER).hex()
    return f"pbkdf2${salt}${dk}"


def users():
    out = {}
    for item in (os.environ.get("PLUSFACTOR_USERS") or "").split(";"):
        name, sep, h = item.strip().partition(":")
        if sep and h.startswith("pbkdf2$"):
            out[name.strip().lower()] = h.strip()
    return out


def check(user, pw):
    h = users().get((user or "").strip().lower())
    if not h:
        hash_password(pw or "x")  # equalize timing for unknown users
        return False
    _, salt, _ = h.split("$")
    return hmac.compare_digest(hash_password(pw or "", salt), h)


_RANDOM_SECRET = secrets.token_hex(32)


def open_mode():
    """No PLUSFACTOR_USERS configured: anyone with the link can use it, each visitor in a private workspace."""
    return not users()


def _secret():
    return (os.environ.get("PLUSFACTOR_SECRET") or _RANDOM_SECRET).encode()


def sign(user, hours=12):
    payload = f"{user}|{int(time.time()) + hours * 3600}"
    mac = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{mac}".encode()).decode()


def verify(token):
    try:
        user, exp, mac = base64.urlsafe_b64decode(token.encode()).decode().rsplit("|", 2)
    except Exception:
        return None
    good = hmac.new(_secret(), f"{user}|{exp}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, good) or int(exp) < time.time():
        return None
    if user.startswith("visitor-") and open_mode():
        return user
    if user not in users():
        return None
    return user


class Workspaces:
    """One private in-memory Store per user. Isolation is structural: a request can only ever
    reach the store belonging to its signed-in user."""
    def __init__(self):
        self.stores, self.seen, self.lock = {}, {}, threading.Lock()

    def get(self, user):
        idle = float(os.environ.get("PLUSFACTOR_IDLE_HOURS", 4)) * 3600
        now = time.time()
        with self.lock:
            for u in [u for u, t in self.seen.items() if now - t > idle]:
                self.stores.pop(u).db.close()
                self.seen.pop(u)
            if user not in self.stores:
                self.stores[user] = Store(":memory:")
            self.seen[user] = now
            return self.stores[user]

    def drop(self, user):
        with self.lock:
            st = self.stores.pop(user, None)
            self.seen.pop(user, None)
        if st:
            st.db.close()
