# Evaluation

- Acceptance cases from the product spec are tests in `tests/analytical`, `tests/integrity`, `tests/security`.
- `scripts/evaluate_decisions.py` scores an adapter against labeled examples, grouped by matter or opinion (never split by sentence), and prints sample sizes, per-task accuracy and disagreements. With scores it also reports Brier score and a threshold sweep.
- `scripts/evaluate_extraction.py` reports date-role and actor-attribution errors for letter extraction against the fixtures' known answers.
- Current labeled set: the synthetic matter only (tiny, n printed by the scripts). It demonstrates the harness; it validates nothing. Thresholds in `data/taxonomies/decision_thresholds.json` stay null until attorney-labeled examples exist.
- A classification score is confidence in a labeling task. It is never the probability that an allegation is true or will survive a motion.
