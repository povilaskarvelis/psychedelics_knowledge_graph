# UI Demo

Goal: simple graph visualization + findings with provenance.

Run
- Start a static server from the project root:
  `python3 -m http.server`
- Open:
  `http://localhost:8000/ui/`
- Methods page:
  `http://localhost:8000/ui/methods.html`
- Developer pipeline workbench:
  `http://localhost:8000/ui/developer.html`

Ideas
- Graph view: compounds and targets/indications with edges for findings
- Findings: show study, assay/outcome, provenance, and factual chips such as `rct`, `full text`, and `positive`
- Bibliography: render citation-style entries from `bibliography_payload_*`
  when available, falling back to finding-derived papers
- Filters: compound, target/indication, year, full text, and optional secondary
  sources for reviews/systematic reviews/meta-analyses
