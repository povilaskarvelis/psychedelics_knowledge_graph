# UI Demo

Goal: simple graph visualization + claim cards with provenance.

Run
- Start a static server from the project root:
  `python3 -m http.server`
- Open:
  `http://localhost:8000/ui/`
- Methods page:
  `http://localhost:8000/ui/methods.html`

Ideas
- Graph view: compounds and targets/indications with edges for claims
- Claim cards: show study, assay/outcome, provenance, and factual chips such as `rct`, `full text`, and `positive`
- Bibliography: render citation-style entries from `bibliography_payload_*`
  when available, falling back to claim-derived papers
- Filters: compound, target/indication, year, full text, and optional secondary
  sources for reviews/systematic reviews/meta-analyses
