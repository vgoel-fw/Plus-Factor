"""Issue-specific precedent comparison over a small reviewed-by-hand manifest.
Dispositions are recorded per issue and defendant scope. No survival rates are computed."""
import json, pathlib, re

DATA = pathlib.Path(__file__).resolve().parents[1] / "data"


def load():
    return json.loads((DATA / "authority_manifest.json").read_text())["authorities"]


def get(aid):
    return next(a for a in load() if a["id"] == aid)


def search(circuit=None, posture=None, issue=None, favorable_to=None, binding=None):
    """Rows are (authority, issue) pairs so agreement rulings never blend with market or standing rulings."""
    rows = []
    for a in load():
        for i in a["issues"]:
            if (posture and a["posture"] != posture) or (issue and i["issue"] != issue) or \
                    (favorable_to and i["favorable_to"] != favorable_to):
                continue
            weight = "binding" if a["circuit"] in (binding or ["SCOTUS", circuit]) else "persuasive"
            rows.append({**{k: a[k] for k in ("id", "name", "citation", "court", "circuit", "year", "posture",
                                              "restraint", "allegation_basis", "url", "note", "review")},
                         **i, "weight": weight})
    return sorted(rows, key=lambda r: (r["weight"] != "binding", -r["year"]))


def unfavorable(side, issue, circuit=None, posture=None):
    """Deliberately surface the analogue that went the other way."""
    other = "defendant" if side == "plaintiff" else "plaintiff"
    return search(circuit, posture, issue, other)


def excerpts(aid):
    p = DATA / "authorities" / f"{aid}.excerpts.txt"
    return p.read_text() if p.exists() else None


def resolve_quote(aid, quote):
    """A legal quotation is usable only if it resolves verbatim to stored opinion text with a pin."""
    text = excerpts(aid)
    if not text:
        return {"ok": False, "reason": "no opinion text acquired for this authority"}
    i = text.find(quote)
    if i < 0:
        return {"ok": False, "reason": "quotation does not appear verbatim in the stored text"}
    ls = text.rfind("\n", 0, i) + 1
    pin = re.match(r"\[(\d+)\]", text[ls:])
    a = get(aid)
    return {"ok": True, "authority_id": aid, "offset": [i, i + len(quote)], "pin": pin[1] if pin else None,
            "cite": f"{a['name']}, {a['citation']}" + (f", {pin[1]}" if pin else "") + f" ({a['year']})",
            "text_status": "typed excerpt; unverified against official PDF"
            if "UNVERIFIED" in text else "verified"}
