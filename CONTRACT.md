# Contract: invariants the code must keep

Each is enforced in code and covered by a test in `tests/`.

1. **Sources are immutable.** Text is hashed on import; spans store offsets, exact text and a checksum. A span that no longer matches blocks promotion.
2. **A quotation must exist verbatim** in its source (documents and authorities alike) or it is refused.
3. **An announcement is never implementation.** Implementation comes only from matched transactions.
4. **Entities stay separate.** Trade names resolve only through an approved alias; a parent is reached only through an approved attribution with a stated participation basis.
5. **Missing stays missing.** A blank rebate is not zero; absent invoices are a coverage gap; an empty lane is not proof of no event.
6. **Dates are intervals with a precision.** "Spring 2024" never becomes a day.
7. **Markets are not defined by the defendants.** Rules cover product, place, customer and time; a purchaser requirement is mandatory.
8. **Every result names its inputs.** A new market version, changed event, entity mapping or source status marks dependent episodes and allegations stale.
9. **Repetition is not corroboration.** Near-identical documents share one origin and count once.
10. **The model boundary is narrow.** Only typed classification questions; routing is a pure function; routes are blocked, abstain, review required, or proposed. Nothing but an attorney review action approves anything. Provider errors abstain.
11. **Restrictions follow the document** into quotes, derived text, cached classifications and exports.
12. **Mutations need an expected revision and a named reviewer**; stale edits return 409; every change is logged with old and new values.
13. **No legal-strength number anywhere.** No plausibility score, no outcome percentages.
14. **Document text is data.** It cannot trigger tools, network access or rule changes. External calls are off by default and previewable.
