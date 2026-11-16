# Plus Factor

Market-definition and parallel-conduct analysis for U.S. antitrust litigators. Local, single-user, no account, no network by default.

Plus Factor organizes the materials a plaintiff-side team actually has before discovery (invoices, price letters, contracts, interview notes, public statements) into competing market hypotheses and defendant-specific conduct episodes. Every inference carries its source passage, its gaps, and the evidence cutting the other way. It does **not** produce a "Twombly score", predict rulings, or decide legal sufficiency.

## Run

```bash
python3 scripts/make_synthetic_fixtures.py   # already committed; regenerates tests/fixtures/synthetic
python3 -m app.server --demo                 # http://127.0.0.1:8765, loads the SYNTHETIC demo matter
python3 -m unittest discover -s tests -t .   # acceptance and integrity tests
python3 scripts/evaluate_decisions.py                 # leave-one-out accuracy of the decision model
export COURTLISTENER_TOKEN=...               # optional: higher CourtListener rate limits
```

Python 3.11+ standard library only. Data lives in `plusfactor.db` (git-ignored). `PLUSFACTOR_DB` and `PLUSFACTOR_PORT` override defaults.

## How it is used

Open the page and either upload documents or **enter it yourself** (supplier, announced date, effective date, increase, price before and after; leave unknowns blank). Then drop files (CSV purchase exports, price letters, contracts, notes as text) or paste details, and press Analyze. `POST /api/analyze` detects each file's type, maps columns, matches vendor names, runs Jev's typed classification questions on the passages, and returns:

- **Parallel conduct**: a price chart per supplier with announcement and effective-date markers, who moved in the invoices, and the strongest exception.
- **Market definition**: candidate markets built from the purchase record and widened one boundary at a time, each marked by whether the parallel pattern holds.
- **What Jev read**: statements tagged as this matter or another case, and firsthand or hearsay.
- **Assumptions made for you**: every automatic choice, so it can be challenged.

There is no intake form and no matter management in the interface. The deeper engine (reviewed mutations, allegation verification, exports, authority grid) remains available through the API.

## Not yet built (stated plainly)

- PDF/DOCX/MSG parsing and native load files: reported as unsupported; supply extracted text.
- DOCX/XLSX export adapters.
- Background jobs: imports and analysis run synchronously.
- The TypeSafe/Jev adapter is written against the SDK README and is **unverified**; the offline rule-based adapter is the default. No decision thresholds are validated yet, so scored model output routes to review.
- Authority manifest entries are unreviewed working notes; only Twombly has stored excerpt text, typed and not yet checked against the official PDF.
- Labor restraints, algorithmic pricing and two-sided platforms are reserved extension points.
- Multi-user hosting (auth, encryption, matter ACLs) is out of scope.

See `CONTRACT.md` for the invariants and `docs/` for architecture, doctrine, data, design and evaluation notes.

## Jev and case law

- **Built-in Jev-style decision model (default)**: `app/jev/` mirrors Jev's interface (state plus typed `Choice` questions in; choice, confidence and per-label probabilities out) and the jev-tools state/questions/decide split. It is a transparent naive Bayes model trained on `data/jev/*.jsonl`, written in standard-library Python: no install, no account, nothing transmitted. Answers below 0.80 confidence are withheld for review. Leave-one-out accuracy on the bundled examples is printed by `scripts/evaluate_decisions.py`; add attorney-labelled examples to improve it.
- **Jev (paid, optional)**: `app/decisions/typesafe_adapter.py` calls `TypeSafeClient.system_one` with typed `Choice` questions (SDK pinned to commit `f36e685`, tag v0.7.5). Routing in `app/decisions/policy.py` follows jev-tools' triage core (`decide.ts`, MIT, commit `43cbece`): nothing is applied below a 0.8 confidence gate, and Jev is never asked whether an agreement existed. Excerpts leave the machine only when the user ticks the Jev box for that run. Without a key, a local rule-based stand-in is used and labelled as such.
- **Cases**: `app/courtlistener.py` queries CourtListener's v4 search (Free Law Project) live for parallel-conduct and defendant-attribution opinions. Live results are marked "retrieved, not reviewed". If CourtListener is unreachable, a bundled list of real cases (working notes, to verify) is shown instead.

## Sharing it with others

Deployed, Plus Factor opens straight to the tool for anyone with the link; there is no sign-in. Each visitor automatically gets a private, in-memory workspace: uploads are never written to disk, no visitor can reach another's documents, and a workspace is discarded after `PLUSFACTOR_IDLE_HOURS` (default 4) of inactivity.

1. On render.com: New > Blueprint > select this repository and branch. It reads `render.yaml` and the `Dockerfile`; nothing else is required.
2. Optional: add `COURTLISTENER_TOKEN` under the service's Environment settings.
3. Share the `https://…onrender.com` address.

Anyone with the link can use it, so treat the address accordingly. To restrict access later, set `PLUSFACTOR_USERS` (lines from `scripts/add_user.py`) and a sign-in page appears. Before uploading client material, confirm the host meets your firm's confidentiality requirements.
