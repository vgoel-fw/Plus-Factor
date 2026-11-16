"""Deterministic routing. Pure: no I/O, no model, no clock.

Follows jev-tools' triage core (github.com/CMaintz/jev-tools, packages/triage/src/core/decide.ts,
MIT, commit 43cbece): Jev is a first-pass judge, so the confidence gate *is* the design and nothing is
applied below `escalate_below`. Plus Factor adds legal-workflow guards in front of that gate and never
has an 'approved' route: only an attorney review action creates a reviewed tag. Confidence concerns a
classification task, not whether an allegation is true or will survive a motion."""

ESCALATE_BELOW = 0.8  # jev-tools' gate; not yet validated on attorney-labeled antitrust examples


def decide(state, response, thresholds):
    def out(route, reason, label=None):
        return {"route": route, "reason": reason, "proposed_label": label, "review_required": True}

    if state["blockers"]:
        return out("blocked", "invalid locator, checksum, or unusable source: " + "; ".join(state["blockers"]))
    if response is None or response.get("error"):
        return out("abstain", f"provider error: {(response or {}).get('error', 'no response')}")
    label, conf = response.get("label"), response.get("score")
    if label not in state["labels"]:
        return out("abstain", f"label outside the typed choices: {label!r}")
    if not state["context_complete"]:
        return out("review_required", "required context missing or omitted")
    if state["unresolved_attribution"]:
        return out("review_required", "speaker or party attribution unresolved")
    if label == "insufficient_context":
        return out("review_required", "insufficient context")
    if conf is not None:
        gate = (thresholds or {}).get(state["task"]) or ESCALATE_BELOW
        if conf < gate:
            return out("abstain", f"low confidence ({conf:.2f} < {gate:.2f}): held")
    return out("proposed", "proposed tag, pending attorney review", label)
