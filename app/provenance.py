"""Immutable sources, exact-text spans with locators, duplicate/origin clustering,
uncertain-date parsing, and the single gate (`usable`) that decides whether a span may
support anything at all."""
import hashlib, json, re
from datetime import date, timedelta
from .storage import now, Invalid

CONF = ["public", "confidential", "highly_confidential"]


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def add_source(store, matter_id, filename, kind, text, meta=None, confidentiality="confidential",
               privilege="none", record="pleading"):
    """Idempotent on (matter, hash, filename). Same hash under another name is kept as a
    separate record in the same duplicate group."""
    h = sha(text)
    same = store.q("SELECT id, filename, dup_group FROM sources WHERE matter_id=? AND sha256=?", (matter_id, h))
    for r in same:
        if r["filename"] == filename:
            return store.source(r["id"], text=False), False
    sid = store.new_id("src")
    dup = same[0]["dup_group"] if same else sid
    store.q("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?,?,0,0,?,?)",
            (sid, matter_id, h, filename, kind, json.dumps(meta or {}), confidentiality, privilege, record,
             dup, _origin(store, matter_id, text, dup), text, now()))
    store.log(matter_id, sid, "source", "import", None, {"sha256": h, "filename": filename}, "system", None)
    return store.source(sid, text=False), True


def _shingles(text):
    body = "\n".join(text.splitlines()[3:]) or text  # ignore mastheads/banners when comparing reports
    w = re.findall(r"[a-z0-9]+", body.lower())
    return {" ".join(w[i:i + 5]) for i in range(max(1, len(w) - 4))}


def _origin(store, matter_id, text, default):
    """Near-identical bodies (syndication, forwards, recycled allegations) share one
    underlying origin: repetition is not independent corroboration."""
    a = _shingles(text)
    for r in store.q("SELECT origin_group, text, kind FROM sources WHERE matter_id=?", (matter_id,)):
        if r["kind"] in ("ap_export", "discovery_export"):
            continue
        b = _shingles(r["text"])
        if a and b and len(a & b) / len(a | b) >= 0.6:
            return r["origin_group"]
    return default


def locator(text, start, end, meta=None):
    l1 = text.count("\n", 0, start) + 1
    l2 = text.count("\n", 0, max(start, end - 1)) + 1
    loc = f"ln {l1}" if l1 == l2 else f"ln {l1}-{l2}"
    bates = (meta or {}).get("bates")
    return f"{bates} {loc}" if bates else loc


def make_span(store, source_id, start, end, extraction="manual", loc=None):
    src = store.source(source_id)
    text = src["text"][start:end]
    if not text.strip():
        raise Invalid("empty span")
    hit = store.q("SELECT id FROM spans WHERE source_id=? AND start=? AND end=?", (source_id, start, end))
    if hit:
        return store.span(hit[0]["id"])
    sid = store.new_id("span")
    store.q("INSERT INTO spans VALUES(?,?,?,?,?,?,?,?)",
            (sid, source_id, loc or locator(src["text"], start, end, src["meta"]), start, end, text, sha(text),
             extraction))
    return store.span(sid)


def find_span(store, source_id, needle, extraction="manual"):
    """Anchor a quotation: it must occur verbatim in the source or we refuse."""
    i = store.source(source_id)["text"].find(needle)
    if i < 0:
        raise Invalid(f"quotation not found verbatim in {source_id}: {needle[:60]!r}")
    return make_span(store, source_id, i, i + len(needle), extraction)


def verify_span(store, span_id):
    try:
        sp = store.span(span_id)
        src = store.source(sp["source_id"])
    except Exception:
        return {"ok": False, "reason": "invalid locator: span or source not found"}
    if sha(src["text"]) != src["sha256"]:
        return {"ok": False, "reason": "source checksum mismatch"}
    if src["text"][sp["start"]:sp["end"]] != sp["text"] or sha(sp["text"]) != sp["checksum"]:
        return {"ok": False, "reason": "span text no longer matches source at locator"}
    return {"ok": True, "reason": None}


def usable(store, span_id, record=None):
    """Why a span may not be relied on (None if usable). `record='pleading'` also rejects
    material counsel has not placed in the pleading record (e.g. post-filing discovery)."""
    v = verify_span(store, span_id)
    if not v["ok"]:
        return v["reason"]
    src = store.source(store.span(span_id)["source_id"], text=False)
    if src["disabled"]:
        return "source disabled"
    if src["privilege"] == "withheld":
        return "source withheld as privileged"
    if record == "pleading" and src["record"] != "pleading":
        return "source is investigation-record only (not in the pleading record)"
    return None


def origins(store, span_ids):
    """Distinct underlying origins behind a set of spans."""
    out = set()
    for s in span_ids:
        try:
            out.add(store.source(store.span(s)["source_id"], text=False)["origin_group"])
        except Exception:
            pass
    return out


def cite(store, span_id):
    sp = store.span(span_id)
    src = store.source(sp["source_id"], text=False)
    return {"span_id": span_id, "source_id": src["id"], "filename": src["filename"], "locator": sp["locator"],
            "text": sp["text"], "confidentiality": src["confidentiality"], "privilege": src["privilege"],
            "disabled": bool(src["disabled"]), "record": src["record"], "origin_group": src["origin_group"]}


# ---- dates as intervals ------------------------------------------------------
MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october november december".split())}
SEASONS = {"spring": (3, 5), "summer": (6, 8), "fall": (9, 11), "autumn": (9, 11), "winter": (12, 2)}


def _eom(y, m):
    return (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))


def parse_date(text):
    """Return (start, end, precision) ISO strings. 'Spring 2024' stays a three-month
    interval; it never collapses to a day."""
    t = text.strip().lower().replace(",", "")
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return t, t, "day"
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)
    if m:
        d = date(int(m[3]), int(m[1]), int(m[2])).isoformat()
        return d, d, "day"
    m = re.fullmatch(r"([a-z]+) (\d{1,2}) (\d{4})", t)
    if m and m[1] in MONTHS:
        d = date(int(m[3]), MONTHS[m[1]], int(m[2])).isoformat()
        return d, d, "day"
    m = re.fullmatch(r"([a-z]+) (\d{4})", t)
    if m and m[1] in MONTHS:
        y, mo = int(m[2]), MONTHS[m[1]]
        return date(y, mo, 1).isoformat(), _eom(y, mo).isoformat(), "month"
    if m and m[1] in SEASONS:
        y, (a, b) = int(m[2]), SEASONS[m[1]]
        return date(y, a, 1).isoformat(), _eom(y + (b < a), b).isoformat(), "season"
    m = re.fullmatch(r"(\d{4})", t)
    if m:
        return f"{t}-01-01", f"{t}-12-31", "year"
    raise Invalid(f"unparseable date: {text!r}")


def days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days
