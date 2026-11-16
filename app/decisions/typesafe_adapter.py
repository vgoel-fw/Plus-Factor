"""Jev via the official TypeSafe Python SDK (typesafe-sdk 0.7.5, from
github.com/typesafe-ai/typesafe-sdk-python). The only file that talks to the provider.

Call shape verified against the SDK source: `TypeSafeClient().system_one(state=..., questions={name: Choice(
instructions=..., criteria={label: None, ...})})` -> `response.choices[name]` with `.choice`, `.confidence`
and `.probabilities`. Reads TYPESAFE_API_KEY from the environment.
"""
import os

NAME = "jev (typesafe system_one)"
EXTERNAL = True


def available():
    try:
        import typesafe_sdk  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("TYPESAFE_API_KEY"))


def classify(state, timeout=20):
    from typesafe_sdk import Choice, TypeSafeClient
    passages = [{"file": s["filename"], "locator": s["locator"], "header": s["document_header"], "passage": s["context"]}
                for s in state["spans"]]
    payload = {"untrusted_document_text": passages}  # data, never instructions
    if state.get("assertion_text"):
        payload["assertion"] = state["assertion_text"]
    with TypeSafeClient() as client:
        res = client.system_one(state=payload, timeout=timeout, questions={
            state["task"]: Choice(instructions=state["prompt"], criteria={l: None for l in state["labels"]})})
    ans = res.choices[state["task"]]
    return {"label": ans.choice, "score": ans.confidence, "scores": dict(ans.probabilities), "model": NAME}
