# Architecture

```
original files -> sources + spans (provenance.py) -> proposed events / mapped transactions (ingest/, transactions.py)
 -> attorney review (POST /api/reviews) -> market versions (markets.py) -> conduct episodes (conduct.py)
 -> agreement matrix (agreement.py) -> allegation verification (allegations.py) -> exports (exports/)
                      decisions/: state.py -> adapter -> policy.py (pure) -> DecisionRun
```

- **Storage** (`storage.py`): SQLite. `sources`, `spans`, `transactions` are typed tables. Other objects (matter, entity, relation, market, market_version, substitution, event, episode, explanation, agreement_item, allegation, issue, decision_run, export, import) are revisioned JSON rows in `objects`. `reviews` is the append-only ReviewAction log. This keeps the first version small; promote a kind to a typed table when it needs indexed queries.
- **Staleness** (`allegations.refresh`): runs after every POST. Episodes compare an input signature (market rules, event and entity revisions, source status, transaction count); allegations compare a named dependency map and report which dependency changed.
- **Server** (`server.py`): stdlib `http.server`, bound to 127.0.0.1, Host-header check, strict CSP. Endpoints follow the product spec, plus `/api/matters/:id/objects`, `/spans`, `/decisions`, `/api/sources/:id/disable|flags`, `/api/authorities`.
- **Web** (`web/`): vanilla JS, no build step. `app.js` is the shell and source pane; `views/` holds the workspaces.
- **Jobs**: synchronous for now. The import and analysis functions are idempotent, which is the property a resumable job runner will need.
