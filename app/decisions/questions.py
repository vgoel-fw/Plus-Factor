"""Typed, narrow classification questions. There is deliberately no question asking
whether an agreement existed or whether a pleading is sufficient."""
VERSION = "q-1"
QUESTIONS = {
    "passage_kind": {
        "prompt": "What does this passage describe?",
        "labels": ["party_conduct", "legal_standard", "other_case", "insufficient_context"]},
    "date_role": {
        "prompt": "What role does the date in this passage play?",
        "labels": ["announcement", "effective", "transaction", "unresolved"]},
    "assertion_support": {
        "prompt": "Does the passage support, contradict, or fail to address the proposed assertion?",
        "labels": ["supports", "contradicts", "mixed", "does_not_address", "insufficient_context"]},
    "knowledge_basis": {
        "prompt": "What is the speaker's basis of knowledge for the account?",
        "labels": ["firsthand", "hearsay", "mixed", "unknown"]},
}
