# Base profiles (not yet defined)

A base profile holds protocol content that several fields share (SPEC.md section 9). It should be written after a second protocol exists, from the content both protocols actually use.

Candidates measured in the psychedelics code (class E and discipline-level class V in [../psychedelics/migration/code_tables.csv](../psychedelics/migration/code_tables.csv)):

| Candidate | Current location |
|---|---|
| Paper types and publication-format exclusions | `pipeline/review/run_deterministic_prescreen.py`; screening instruction section 5 and paper-type rules |
| Paper-type extraction instructions | `docs/extraction_profiles/paper_type/` |
| Meta-analysis and review extraction schemas and instructions | `schema/meta_analysis_evidence_v2.schema.json`, `schema/review_relationships_v2.bundle.schema.json`, `docs/extraction_profiles/meta_analysis_v2/`, `docs/extraction_profiles/review_relationships_v2/` |
| Shared observation role fields | `pipeline/extract/primary_observation_contract.py` (candidate, not production) |
| Study designs, population and model categories, experimental systems | `ui/app.js`, `pipeline/kg/build_evidence_tables.py` |
| Comparators and follow-up windows | `ui/app.js`, `pipeline/extract/clinical_comparator.py`, `pipeline/extract/clinical_followup_window.py` |
| Assay families and mechanistic relationship types | `pipeline/extract/assay_family.py`, `ui/app.js` |
| Pharmacokinetic parameters, relations, routes and matrices | `pipeline/kg/pk_relationships.py`, `ui/app.js` |
| Result-direction vocabulary | `pipeline/kg/convert_routed_extractions_to_evidence_rows.py` `DIRECTION_NORMALIZATION` |
| Section markers for article-text selection | `pipeline/fulltext/build_llm_evidence_packets.py` |
