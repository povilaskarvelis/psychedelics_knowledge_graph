# Psychedelics protocol: what has to move

Measured 30 October 2026 on the working tree at `6284a57` with 155 modified or untracked files. Reproduce with:

```bash
python protocols/tools/scan_field_coupling.py --config protocols/psychedelics/migration/scan_config.json --overrides protocols/psychedelics/migration/classification_overrides.json --out-dir protocols/psychedelics/migration
```

## Summary

- **Scanned:** 114,352 lines of code: 96,710 lines of Python in `pipeline/`, `services/` and `scripts/`, and 17,642 lines of browser JavaScript in `ui/`.
- **Hard-coded tables:** the code contains 945 tables (lists, sets, dicts and long regexes) totalling 14,381 lines. 6,547 of those lines (46%) are protocol content. The other 7,834 are engine content: column lists, report fields, publisher hosts and similar.
- **Location of the protocol content:** it is concentrated in one file. `pipeline/kg/build_evidence_tables.py` holds 3,793 of the 6,547 lines, in 156 tables. It also holds 242 vocabulary regexes written inline in functions.
- **Stages that are already engine code:** discovery execution, metadata ingestion, full-text retrieval, model transport, scoped updates and workflow state contain almost no field content. The exception is the search plan in discovery, which is built around compound names (88 lines).
- **Instructions:** the extraction instruction files are nearly free of field terms. The screening instructions are about one-third field eligibility rules, one-quarter evidence-domain definitions and one-third generic rules.
- **Inconsistencies:** several decisions are defined more than once and the copies differ (section 6). The compound list exists in five places with different membership. The interface classifies molecular findings with its own copy of the Python rules, and the two copies now differ.

| Protocol content in code tables | Tables | Lines | Destination |
|---|---:|---:|---|
| Field-specific: scope, anchor identity, field vocabularies | 87 | 1,988 | `scope.yaml`, `entities.yaml`, `vocabularies/` |
| Discipline-level: neuropsychopharmacology and psychiatry concepts | 147 | 3,135 | base-profile candidates or `vocabularies/` |
| General biomedical: publication formats, study systems, directions | 18 | 396 | base profile |
| Bindings: per-domain field names, domain-to-kind maps | 83 | 1,028 | derived from schema role annotations |
| **Total** | **335** | **6,547** | |

## 1. Method

1. **Literal tables.** `scan_field_coupling.py` parses each Python file with `ast` and each browser script with acorn. It records every assignment whose value holds at least four string literals, and every regex longer than 80 characters.
2. **Classification.** Each table is classified by rules on its name and contents. I then reviewed the tables by hand: 235 table names in `classification_overrides.json` set the class of 251 tables, replacing the automatic class where it was wrong.
   - The classes are S (scope and anchor identity), V (concept vocabulary and rules), B (bindings), E (base vocabulary) and G (engine).
   - S, V and E tables also get a reuse level: **field** (this field only), **discipline** (likely to recur in other neuropsychopharmacology or psychiatry protocols) or **general** (any biomedical field). The reuse level is a judgment.
3. **Logic outside tables.** The scan counts three things:
   - lines whose string literals name an evidence domain, a node kind, a field term or the anchor type;
   - lines whose identifiers contain `compound` or `psychedel`;
   - regex calls whose literal pattern contains at least two words.
4. **Instruction files.** These were measured by line (share of lines containing field terms) and by section (characters).

Per-table results are in [migration/code_tables.csv](migration/code_tables.csv). Per-file counts are in [migration/logic_coupling.csv](migration/logic_coupling.csv), and totals in [migration/summary.json](migration/summary.json).

## 2. Where each protocol section lives now

| Section | Current location | Form |
|---|---|---|
| Scope | `docs/screening/title_abstract_screening.md` (v5, production) and `_v6_1.md` (correction pass); `pipeline/review/deterministic_prescreen_rules.py`; `pipeline/review/screening_contract.py` | instruction text, Python tables |
| Search | `pipeline/discovery/search_strategy.v3.json`; `validation.*` lists in `pipeline/config.example.yaml` (221 entries next to API keys and rate limits) | JSON, YAML |
| Anchor and entities | `data/curated/entity_registry.json`; compound lists in four other places; subject-form rules in `pipeline/kg/build_evidence_tables.py`, `compound_combinations.py`, `use_contexts.py`, `real_world_subjects.py` | JSON, Python tables, Python logic |
| Evidence domains | screening instructions (definitions); `docs/extraction_domains/*.md` (12 files); `schema/extraction_profiles/primary/*.schema.json` (11 files); `PRIMARY_PROMPT_BY_DOMAIN` in two Python files | Markdown, JSON Schema, Python tables |
| Vocabularies | `schema/kg_node_vocabularies.json` (325 entries); `entity_registry.json` (targets 163, disorders 74); `schema/disorder_canonicalization.json`; rule tables in `build_evidence_tables.py`; copies in `ui/app.js` | JSON, Python and JavaScript tables, inline regexes |
| Views | `schema/graph_view_contract.json`; `CATEGORY_DEFINITIONS` in `scripts/build_compound_pages.py`; overview projection in `pipeline/publish/export_evidence_payload.py`; facet functions in `ui/app.js` | JSON, Python, JavaScript |
| Questions | not recorded; draft in `questions.yaml` | none |
| Validation | `docs/evaluation/` reports and frozen reference sets under `data/processed/model_runs/` | Markdown, JSON |
| Site | `index.html`, `about/`, `methods/`, `api/`, `llms.txt`, `CITATION.cff`, service identifiers in `services/query_api/` | HTML, Markdown, Python strings |
| Record-level decisions | `data/curated/*overrides*.json`, `post_retrieval_eligibility_decisions.json`, `pipeline/kg/author_identity_overrides.json`, `pipeline/extract/manual_extraction_route_overrides.json`, `pipeline/fulltext/manual_fulltext_access_overrides.json` | JSON |

## 3. Code tables

### By file

| File | Protocol-content table lines |
|---|---:|
| `pipeline/kg/build_evidence_tables.py` | 3,793 |
| `ui/app.js` | 734 |
| `pipeline/review/deterministic_prescreen_rules.py` | 509 |
| `pipeline/review/run_deterministic_prescreen.py` | 278 (publication formats; base profile) |
| `pipeline/kg/convert_routed_extractions_to_evidence_rows.py` | 151 |
| `pipeline/fulltext/build_llm_evidence_packets.py` | 151 (section markers; base profile) |
| `pipeline/kg/pk_relationships.py` | 143 |
| `pipeline/kg/convert_meta_analysis_v2_to_evidence_rows.py` | 103 |
| `pipeline/kg/compound_combinations.py` | 101 |
| `pipeline/kg/convert_review_relationship_bundles_to_evidence_rows.py` | 87 |
| 25 other files | 497 |

### Largest tables

| Table | Location | Lines | Class, reuse |
|---|---|---:|---|
| `COGNITIVE_BEHAVIORAL_RULES` | `build_evidence_tables.py:1169` | 367 | V, discipline |
| `INTERVENTION_TOPIC_RULES` | `build_evidence_tables.py:6583` | 300 | V, field |
| `MOLECULAR_SUBTOPIC_RULES_BY_PARENT` | `build_evidence_tables.py:5741` | 257 | V, discipline |
| `SAFETY_ENDPOINT_PATTERNS` | `build_evidence_tables.py:7553` | 257 | V, discipline |
| `PUBLIC_HEALTH_TOPIC_RULES` | `build_evidence_tables.py:608` | 232 | V, field |
| `OUT_OF_SCOPE_PUBLICATION_FORMAT_DOI_PATTERNS` | `run_deterministic_prescreen.py:200` | 204 | E, general |
| `IN_SCOPE_INTERVENTION_CLASS_TERMS` | `deterministic_prescreen_rules.py:239` | 146 | S, field |
| `COMPOUND_SYNONYMS` | `deterministic_prescreen_rules.py:13` | 141 | S, field |
| `SUBJECTIVE_EXPERIENCE_RULES` | `build_evidence_tables.py:1669` | 136 | V, field |
| `CANONICAL_ENTITY_FORMAT_GROUPS` | `build_evidence_tables.py:2477` | 127 | V, discipline |
| `SYMPTOM_ENDPOINT_PATTERNS` | `build_evidence_tables.py:7888` | 126 | V, discipline |
| `MOLECULAR_EFFECT_RULES` | `build_evidence_tables.py:5576` | 120 | V, discipline |
| `ENTITY_LABEL_FIELDS_BY_KIND` | `build_evidence_tables.py:1985` | 117 | B |
| `NAMED_COMBINATION_DEFINITIONS` | `compound_combinations.py:24` | 101 | S, field |
| `ADMINISTRATION_ROUTE_DISPLAY_LABELS` | `ui/app.js:2443` | 77 | E, discipline |

Grouped by concept scheme, the S and V tables are distributed as listed in [vocabularies.yaml](vocabularies.yaml). The largest groups are anchor identity and scope (935 lines), molecular pathways and readouts (731), cognitive and behavioral constructs (523), public-health measures and use contexts (441) and conditions and symptoms (414).

## 4. Logic outside tables

| Area | Lines | Lines with protocol literals | Lines with anchor-named identifiers | Inline vocabulary regexes |
|---|---:|---:|---:|---:|
| `pipeline/kg` | 22,855 | 847 | 621 | 328 |
| `ui` | 17,642 | 243 | 536 | 0 |
| `scripts` | 2,233 | 55 | 137 | 2 |
| `pipeline/review` | 6,620 | 51 | 39 | 86 |
| `pipeline/publish` | 5,330 | 50 | 44 | 0 |
| `pipeline/discovery` | 5,140 | 43 | 88 | 1 |
| `pipeline/extract` | 12,125 | 33 | 6 | 18 |
| `services` | 2,332 | 17 | 18 | 0 |
| `pipeline/validate` | 3,686 | 17 | 16 | 0 |
| `pipeline/ingest` | 14,684 | 8 | 8 | 23 |
| `pipeline/fulltext` | 18,987 | 7 | 2 | 19 |
| `pipeline/update`, `pipeline/workflow`, `pipeline/llm.py`, `pipeline/rerun_luna.py` | 2,718 | 0 | 0 | 0 |
| **Total** | **114,352** | **1,371** | **1,515** | **477** |

Notes:

- **Different kinds of coupling.** The anchor-named identifiers measure how far the code assumes that the graph is organized around compounds. The protocol literals measure branching on evidence domains, node kinds and field terms.
- **Inline regexes are not all field content.** The 77 in `run_deterministic_prescreen.py` detect publication formats, and those in `ingest` and `fulltext` detect data-availability statements and article sections. Those are base-profile or engine rules. The inline regexes in `pipeline/kg` (242 of them in `build_evidence_tables.py`) are mostly field and discipline normalization rules. They are the hardest part to move, because each is a special case inside a function (for example, falls classified as sedation or motor impairment, or "candy flip" as a named combination).
- **The public API is already generic in structure.** It uses subject and object identifiers. Its field-specific parts are names and addresses: the MCP resource scheme `psychedelics-kg://`, schema version strings and documentation URLs.

## 5. Instruction files

| Files | Share of lines with field terms | Destination |
|---|---:|---|
| `docs/extraction_profiles/paper_type/*.md` (7) | 3–6% | base profile |
| `docs/extraction_domains/*.md` (12) | 0–7% (excluding one 3-line file) | `domains.yaml` (domain instructions are field content even where no field term appears, because the domain list is a field decision) |
| `docs/extraction_profiles/meta_analysis_v2/*.md`, `review_relationships_v2/*.md` | 2–3% | base profile |
| `docs/screening/title_abstract_screening.md` (v5, production) | 14% | split, see below |

Composition of the latest screening text (`title_abstract_screening_v6_1.md`, 22,893 characters):

| Part | Characters | Destination |
|---|---:|---|
| Field eligibility: substances, qualifying contribution, purpose boundaries, reviews (sections 1–4 and introduction) | 8,434 | `scope.yaml` |
| Evidence-domain definitions, tagging rules, validity modifiers | 6,246 | `domains.yaml` |
| Publication format, language, identity conflicts, decision object, paper types | 8,213 | engine or base profile |

## 6. Duplicated definitions

1. **The compound list is defined in five places:**
   - `entity_registry.json` (84 entries)
   - `config.example.yaml` `validation.allowed_compounds` (54)
   - `COMPOUND_SYNONYMS` (51 canonical names)
   - `search_strategy.v3.json` `legacy_scope_snapshot` (40)
   - the `known_substances` extras in `screening_contract.py`

   The first four lists contain 101 distinct names, and 30 of them appear in all four. Some differences are intended: the registry also holds out-of-scope substances so that exclusions can be labelled. Merging the lists is a scientific review, not a mechanical step.
2. **The view groupings are defined twice with different labels.** `graph_view_contract.json` uses "Conditions" and "Brain regions". `scripts/build_compound_pages.py` uses "Conditions & symptoms" and "Brain systems & measures", and adds a Pharmacokinetics category that the graph views do not have.
3. **The interface reclassifies molecular findings with its own rules:**
   - `PATHWAY_READOUT_FAMILY_RULES` in `ui/app.js` has the same 15 labels as `MOLECULAR_EFFECT_RULES` in Python, but 5 of its 15 regexes differ.
   - `NEUROPLASTICITY_FINDING_THEME_RULES` shares 14 labels with the Python neuroplasticity subtopics. Its regexes differ for 3 of those 14, and one label ("Other neurotrophic factors") exists only in JavaScript.

   The site can therefore group a finding differently from the build.
4. **Display label overrides exist twice:** in `ui/app.js` (`CONDITION_GRAPH_LABEL_OVERRIDES`, `TARGET_GRAPH_LABEL_OVERRIDES`) and in `scripts/build_analysis_index.py` (`CONDITION_LABELS`, `TARGET_LABELS`). Category colours exist twice: in `ui/app.js` and in `ui/compound.js`.
5. **The schemas use different names for the same role.** The 11 primary schemas use 106 distinct field names, and 6 of them occur in all 11. The subject role is called `compound`, `compound_or_exposure`, `compound_or_intervention`, `compound_or_analyte` or `exposure_or_policy`, depending on the domain.
6. **The evidence-domain list is written in several places:** into the meta-analysis and review schemas as an enum, into `DOMAIN_ROUTES` in `run_domain_routing.py`, and into `PRIMARY_PROMPT_BY_DOMAIN` in two files.

## 7. Order of work

Each step has a test that shows the behaviour did not change. The repository already supports this: saved extractions can be replayed through the normalizer (`pipeline/kg/replay_extraction_release.py`), and screening inputs are frozen with hashes. Start after the current uncommitted work is committed.

| Step | Work | Size | Test |
|---|---|---|---|
| 0 | Record a baseline: replay the active release and save `migration/summary.json`. | none | Replay reproduces the active release tables. |
| 1 | Point `protocol.yaml` at the existing declarative files. Split `config.example.yaml` into engine settings and protocol lists. | 5 files | The discovery plan has the same query hash. |
| 2 | Merge the five compound lists into one anchor registry with explicit roles (in scope, searched, synonym, out-of-scope label). | 101 names; scientific review | Prescreen and screening decisions on the frozen screening frame are identical, or each difference is reviewed. |
| 3 | Move concept rule tables (class V) into `vocabularies/*.yaml`, with an engine loader for the rule types in SPEC.md 5.6. Start with the two worked examples and the other field-specific schemes. | 103 tables, 3,261 lines | The replay is identical. |
| 4 | Add `x-role` annotations to the 11 primary schemas and derive the binding tables (class B). | 83 tables, 1,028 lines | The replay is identical; the scan reports no class B tables. |
| 5 | Make one engine classification the source for both the build and the interface. Remove the JavaScript rule copies and the duplicated category definitions. Review the 8 regex differences first. | about 900 lines in `ui/` and `scripts/` | Explore and Analyze counts match the precomputed counts; interface tests pass. |
| 6 | Compose the screening instructions from engine and protocol parts. | 22,893 characters | The composed text matches v6.1, or the difference is reviewed. |
| 7 | Replace the compound-specific code paths with an anchor or subject abstraction, and derive API names from the protocol id. | 1,515 identifier lines | The scan reports zero anchor-named identifiers in engine code; the API contract is unchanged apart from versioned names. |
| 8 | Convert the 242 inline regexes in `build_evidence_tables.py` into rule types or protocol hooks (SPEC.md R8). | 242 regexes | The replay is identical; hook size is reported. |
| 9 | Draft a second protocol, then move the content both protocols use into `protocols/base/`. | about 1,300 lines of class E and 2,200 of discipline-level V | Both protocols validate against the base profile. |

Steps 3, 4 and 8 change `build_evidence_tables.py` (12,472 lines) more than any other file. Steps 2 and 5 require scientific decisions. The other steps are mechanical but need the replay test at each commit.

## 8. Limits of this measurement

- **Tables.** Tables with fewer than four strings are not counted. Inline regexes are counted, but other inline string comparisons are counted only through the literal-line measure.
- **Classification.** Classes come from rules plus a manual review of table names and contents. Reuse levels are judgments.
- **Implicit assumptions.** The scan measures text, not design assumptions such as one subject per finding. Those appear only as the anchor-identifier count.
- **Coverage.** HTML pages, CSS and instruction files were measured separately or not at all.
- **Snapshot.** The working tree had 155 uncommitted or untracked files, so the line numbers will change as that work is committed.
