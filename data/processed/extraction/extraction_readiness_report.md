# Extraction Readiness

Generated: `2026-05-19T15:28:38.185844+00:00`

This report combines papers marked `relevant` or `uncertain` by LLM abstract screening across the screening reports included in the corpus manifest. Each DOI appears once per dataset. Final graph claims are not taken from these files; they will be extracted from the paper text in the next stage.

## Mechanistic

- Candidate papers: `4947`
- Relevance: `{'relevant': 4541, 'uncertain': 406}`
- Readiness: `{'abstract_only_needs_pdf_access': 3236, 'full_text_ready': 1711}`
- Seen in multiple included runs: `0`

Outputs:
- Candidates JSONL: `/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/extraction/mechanistic_extraction_candidates.jsonl`
- Candidates CSV: `/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/extraction/mechanistic_extraction_candidates.csv`
- Full-text-ready DOI queue: `/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/raw/doi_queue.mechanistic.extraction_fulltext_ready.txt`
- Abstract-only DOI queue: `/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/raw/doi_queue.mechanistic.extraction_abstract_only.txt`

## Disorder

- Candidate papers: `6596`
- Relevance: `{'relevant': 6109, 'uncertain': 487}`
- Readiness: `{'abstract_only_needs_pdf_access': 3317, 'full_text_ready': 3279}`
- Seen in multiple included runs: `1`

Outputs:
- Candidates JSONL: `/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/extraction/disorder_extraction_candidates.jsonl`
- Candidates CSV: `/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/extraction/disorder_extraction_candidates.csv`
- Full-text-ready DOI queue: `/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/raw/doi_queue.disorder.extraction_fulltext_ready.txt`
- Abstract-only DOI queue: `/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/raw/doi_queue.disorder.extraction_abstract_only.txt`

