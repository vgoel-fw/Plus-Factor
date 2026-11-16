"""Transaction normalization. Original values are preserved verbatim; the formula is a
recorded analytical choice; a missing component stays missing and never becomes zero."""
from statistics import median
from .provenance import parse_date
from .storage import Invalid

TO_LB = {"lb": 1.0, "lbs": 1.0, "kg": 2.2046226218, "mt": 2204.6226218, "cwt": 100.0, "ton": 2000.0, "oz": 0.0625}
ROLES = ["vendor", "invoice_id", "line_id", "date", "sku", "description", "family", "grade", "origin", "quantity",
         "unit", "amount", "discount", "rebate", "freight", "surcharge", "tax", "ship_to", "currency"]
GUESS = {"vendor": ["vendor"], "invoice_id": ["inv no", "invoice"], "line_id": ["line"], "date": ["inv date", "date"],
         "sku": ["item", "sku"], "description": ["desc"], "family": ["family"], "grade": ["grade"],
         "origin": ["origin"], "quantity": ["qty", "quantity"], "unit": ["uom", "unit"],
         "amount": ["ext amount", "amount", "net price"], "rebate": ["rebate"], "freight": ["freight"],
         "discount": ["discount"], "surcharge": ["surcharge"], "tax": ["tax"], "ship_to": ["ship to", "ship-to"],
         "currency": ["curr"]}
DEFAULT_FORMULA = {"components": {"amount": 1, "rebate": -1, "freight": 0}, "per": "lb",
                   "text": "Invoice-line amount, less allocated rebate, divided by pounds shipped. "
                           "Freight excluded (recorded choice)."}


def guess_mapping(header):
    """A proposal for the mapping screen only; nothing is imported until counsel confirms."""
    out, used = {}, set()
    for role, keys in GUESS.items():
        for k in keys:
            hit = next((h for h in header if h.lower() == k and h not in used), None) or \
                  next((h for h in header if k in h.lower() and h not in used), None)
            if hit:
                out[role] = hit
                used.add(hit)
                break
    return out


def _num(v):
    v = (v or "").strip().replace(",", "").replace("$", "")
    return float(v) if v else None


def normalize(orig, mapping, formula):
    g = lambda role: orig.get(mapping.get(role, ""), "")
    unit = g("unit").strip().lower()
    if unit not in TO_LB:
        raise Invalid(f"unsupported unit {g('unit')!r}")
    qty = _num(g("quantity"))
    qty_lb = qty * TO_LB[unit] if qty else None
    missing, net = [], 0.0
    for comp, sign in formula["components"].items():
        if not sign:
            continue
        v = _num(g(comp)) if comp in mapping else None
        if v is None:
            missing.append(comp)
        else:
            net += sign * v
    amount = _num(g("amount"))
    d = g("date")
    return {"vendor": g("vendor").strip(), "invoice_id": g("invoice_id"), "line_id": g("line_id"),
            "date": parse_date(d)[0] if d else None, "sku": g("sku"), "description": g("description"),
            "family": g("family") or None, "grade": g("grade") or None, "origin": g("origin") or None,
            "region": g("ship_to") or None, "currency": g("currency") or None,
            "qty_lb": round(qty_lb, 4) if qty_lb else None, "unit_original": g("unit"),
            "gross_unit_price": round(amount / qty_lb, 6) if amount is not None and qty_lb else None,
            # net price exists only when every component the formula needs is present
            "net_unit_price": round(net / qty_lb, 6) if qty_lb and not missing else None,
            "missing": missing}


def in_market(n, rules):
    def ok(key, val):
        allowed = rules.get(key) or []
        return not allowed or val in allowed
    if not (ok("families", n["family"]) and ok("grades", n["grade"]) and ok("origins", n["origin"])
            and ok("regions", n["region"])):
        return False
    d = n["date"]
    return not d or ((rules.get("date_from") or "0") <= d <= (rules.get("date_to") or "9"))


def price(n, basis):
    return n["net_unit_price"] if basis == "net" else n["gross_unit_price"]


def med(xs):
    xs = [x for x in xs if x is not None]
    return median(xs) if xs else None
