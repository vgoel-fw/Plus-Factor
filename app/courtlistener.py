"""Real opinions from CourtListener (Free Law Project), REST API v4 search.

Live results are retrieved, not reviewed: the search cannot tell you the holding, so they are
shown as related opinions with the court's own snippet. Set COURTLISTENER_TOKEN for higher rate
limits. When CourtListener is unreachable the bundled manifest of real cases is used instead."""
import json, os, re, urllib.parse, urllib.request
from . import precedent

API = "https://www.courtlistener.com/api/rest/v4/search/"
SITE = "https://www.courtlistener.com"
QUERIES = {
    "agreement": '"parallel conduct" AND ("plus factor" OR "plus factors") AND Twombly',
    "attribution": '"parallel conduct" AND (parent OR subsidiary) AND "each defendant" AND Twombly',
    "market": '"relevant market" AND ("reasonable interchangeability" OR "cross-elasticity") AND "price-fixing"',
}


_CACHE = {}


def search(topic, extra="", limit=6, timeout=8):
    q = QUERIES[topic] + (f" AND ({extra})" if extra else "")
    if q in _CACHE:
        return _CACHE[q]
    params = urllib.parse.urlencode({"q": q, "type": "o", "order_by": "score desc", "stat_Precedential": "on"})
    headers = {"User-Agent": "plus-factor (local research tool)"}
    if os.environ.get("COURTLISTENER_TOKEN"):
        headers["Authorization"] = "Token " + os.environ["COURTLISTENER_TOKEN"]
    data, err = None, None
    for base in (API, API.replace("/v4/", "/v3/")):  # v3 still serves anonymous search
        try:
            data = json.load(urllib.request.urlopen(urllib.request.Request(base + "?" + params, headers=headers), timeout=timeout))
            break
        except Exception as e:
            err = f"{type(e).__name__}: {getattr(e, 'code', '')}".strip(": ")
    if data is None:
        return {"live": False, "error": err, "results": fallback(topic)}
    rows = []
    for r in data.get("results", [])[:limit]:
        snip = r.get("snippet") or " ".join((o.get("snippet") or "") for o in r.get("opinions", [])[:1])
        snip = re.sub(r"</?mark>|<[^>]+>", "", snip)
        rows.append({"name": r.get("caseName"), "court": r.get("court_citation_string") or r.get("court"),
                     "date": (r.get("dateFiled") or "")[:10], "citation": ", ".join(r.get("citation") or []),
                     "url": SITE + (r.get("absolute_url") or ""), "snippet": snip.strip()[:400],
                     "status": "retrieved from CourtListener, not reviewed"})
    out = {"live": True, "query": q, "results": rows or fallback(topic)}
    _CACHE[q] = out
    return out


def fallback(topic):
    issue = {"agreement": "agreement_plausibility", "attribution": "defendant_specific_participation",
             "market": "market_definition"}[topic]
    return [{"name": r["name"], "court": r["court"], "date": str(r["year"]), "citation": r["citation"],
             "url": r["url"] or SITE + "/?" + urllib.parse.urlencode({"q": f'"{r["name"]}"'}),
             "snippet": r["paraphrase"], "disposition": r["disposition"], "favorable_to": r["favorable_to"],
             "scope": r["defendant_scope"], "status": "bundled working note; verify against the opinion"}
            for r in {r["name"]: r for r in reversed(precedent.search(issue=issue))}.values()]


def unfavorable(topic="agreement"):
    """Find the unfavorable analogue: cases where similar allegations failed."""
    return [r for r in fallback(topic) if r.get("favorable_to") == "defendant"]
