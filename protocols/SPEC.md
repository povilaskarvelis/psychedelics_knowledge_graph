# Field protocol specification

Draft 0.1, 30 October 2026. Not yet read by the pipeline.

A field protocol records the decisions that make a knowledge graph specific to one research field. An engine performs the steps that are the same in every field: search execution, deduplication, metadata enrichment, full-text retrieval, model calls, normalization, validation and publication. The engine reads the protocol and contains no field content of its own.

The psychedelics protocol in [psychedelics/](psychedelics/) was drafted from the current repository to test this format. [psychedelics/MIGRATION.md](psychedelics/MIGRATION.md) measures how much field content the code holds today and where it is.

## 1. Aims

1. A domain expert can review every field decision without reading code.
2. A second field is added by writing a protocol, not by editing the engine.
3. A protocol change determines which pipeline stages must run again and whether new model calls are needed.
4. Every release reports coverage and accuracy in the same format, so graphs built by different people can be compared.

## 2. Terms

| Term | Meaning |
|---|---|
| Field protocol | The versioned set of files described here, for one field. |
| Engine | The field-agnostic code that executes a protocol. |
| Base profile | A protocol fragment that several protocols inherit, such as paper types, study designs or pharmacokinetic parameters. |
| Anchor entity | The entity type that most findings in a field are about. Compounds in the psychedelics protocol. |
| Node kind | A type of graph node other than the anchor, such as a condition, receptor target or brain region. |
| Finding shape | A template for one kind of finding: its roles (subject, object, comparison, context, result, source) and the node kinds allowed in each role. |
| Evidence domain | A part of the field with its own definition, extraction instructions and schema, such as clinical outcomes or molecular targets. |
| Concept scheme | The controlled labels for one node kind, with aliases, match rules, parents and external identifiers. |
| View | A projection of findings into the displayed graph or a page category. |
| Graph card | The quality report generated with each release (section 8). |

## 3. Requirements

**R1. Declarative content.** Protocol files hold data and instruction text. Code is allowed only under R8.

**R2. Reviewable decisions.** Files are YAML or Markdown. Any decision may carry `rationale`, `decided_by` and `decided_on`.

**R3. No field content in the engine.** The engine names no field term, no evidence domain, no node kind and no anchor type. The test is `protocols/tools/scan_field_coupling.py`: for engine code it must report zero field-term lines, zero anchor-name identifiers and no tables outside class G. Per-domain field lists are derived from schema role annotations (section 5.5), not written by hand.

**R4. Versioning.** A protocol has a semantic version. Section 7 lists which change types require which stages to run again.

**R5. Inheritance.** A protocol may list base profiles under `inherits`. A protocol value replaces an inherited value only when the protocol states the override explicitly.

**R6. Shared identifiers.** Each concept scheme names an external identifier scheme, or states `none_assigned`. The graph card reports identifier coverage per node kind.

**R7. Validation.** The protocol names its reference sets, their reviewers and its release checks. The engine computes the graph card from them.

**R8. Code hooks.** A rule that the engine's rule types cannot express may be supplied as a protocol-local Python module, called through a named interface. The coupling scan reports the size of every hook. A hook that recurs across protocols becomes a candidate for a new engine rule type.

## 4. Layout

```
protocols/
  SPEC.md                         this document
  base/                           base profiles (not yet defined; base/README.md)
  tools/                          measurement and conversion tools
  <field>/
    protocol.yaml                 manifest (required)
    scope.yaml                    eligibility rules and screening instruction parts (required)
    search.yaml                   providers, queries, update cadence, search checks (required)
    entities.yaml                 anchor, node kinds, finding shapes (required)
    domains.yaml                  evidence domains, instructions, schemas (required)
    vocabularies.yaml             index of concept schemes (required)
    vocabularies/<scheme>.yaml    one file per concept scheme
    views.yaml                    projection rules, views, facets (required)
    questions.yaml                questions the graph must answer (required)
    validation.yaml               reference sets, release checks, graph card fields (required)
    site.yaml                     names, addresses, citation, licences, presentation (required)
    instructions/                 instruction text fragments (optional; may stay in docs/ during migration)
    schemas/                      JSON Schemas with role annotations (optional; may stay in schema/)
    decisions/                    record-level curation decisions: screening, eligibility, metadata,
                                  author identity and graph-inclusion overrides (optional)
    hooks/                        protocol-local code under R8 (optional)
```

Record-level decisions differ from protocol rules: they apply to named reports or authors, not to a class of records. They belong to the protocol instance because they record expert judgments about that field's literature, but they are data, and a release reports how many were applied.

## 5. Sections

Each subsection lists the keys of one file. The psychedelics files show the current values.

### 5.1 protocol.yaml

`spec_version`, `protocol.id`, `protocol.title`, `protocol.version`, `protocol.status`, `protocol.description`, `protocol.maintainers`, `protocol.inherits`, `sections` (file per section), `snapshot` (date and repository state the values were read from).

### 5.2 scope.yaml

| Key | Content |
|---|---|
| `research_area` | One-sentence description of what the corpus covers. |
| `anchor_eligibility` | In-scope anchor classes, identity rule for unfamiliar entities, conditional inclusions, exclusions, shared-target and mixed-exposure rules, ambiguous abbreviations. |
| `qualifying_contribution` | Inclusion bases and what does not qualify. |
| `purpose_exclusions` | Research purposes excluded even when an eligible anchor is studied. |
| `reviews` | Coverage rule for reviews and scholarly analysis. |
| `publication_and_language` | Usually inherited from a base profile: languages, excluded formats, minimum abstract length. |
| `decision_values` | Screening outcomes. |
| `instructions` | Instruction text and its version hash until the engine composes it (section 6). |
| `deterministic_prescreen` | Field rules applied before model screening. |

### 5.3 search.yaml

`providers`, `start_date`, `update` (mode, overlap, limits), `strategy` (query design, anchor block, topic modules, pair lists), `calibration` (completion check, seed set, recall estimate). Provider paging and rate limits are engine settings.

### 5.4 entities.yaml

| Key | Content |
|---|---|
| `anchor` | Type name, display names, identity registry, external identifier policy, non-atomic subject forms, subject roles. `anchor` may be absent (decision D1). |
| `node_kinds` | Each kind with its evidence domains and views. |
| `finding_shapes` | Each shape with evidence type, description, roles, schema and implementation notes. |
| `evidence_types` | Usually inherited: primary study, meta-analysis, review, guideline or consensus, contextual record. |

Role names used in finding shapes: `subject`, `object`, `qualifier`, `comparison`, `population_or_model`, `experimental_system`, `study_design`, `dose_or_regimen`, `administration_route`, `timepoint`, `sample_size`, `direction`, `statistic`, `value`, `unit`, `measure`, `summary`, `evidence_location`, `evidence_locator`. A `qualifier` names the object's frame of reference, for example the model in which a fitted parameter is defined (section 10).

### 5.5 domains.yaml

Per evidence domain: `label`, `reuse` (field, discipline or general), `definition` (also the screening text for the domain), `search_modules`, `extraction.primary_prompt_profile`, `extraction.domain_instructions`, `extraction.primary_schema`, `extraction.entity_types`, `graph.default_node_kind`, `graph.views`. Also `methodological_validity_modifiers` and `paper_types`.

**Role annotations.** Every field of an extraction schema carries `x-role`, a role name from section 5.4:

```json
"compound_or_exposure": {"type": "string", "x-role": "subject"},
"subjective_construct": {"type": "string", "x-role": "object"},
"instrument_or_measure": {"type": "string", "x-role": "measure"}
```

The engine derives every per-domain field list from these annotations. In the current code the 11 primary schemas use 106 distinct field names, of which 6 occur in all 11, and the subject role has five different names. The graph builder therefore keeps hand-written lists such as `ENTITY_LABEL_FIELDS_BY_KIND` and `COMPOUND_LABEL_FIELDS`. These are the 1,028 lines of class B in the migration inventory.

### 5.6 Concept schemes

`vocabularies.yaml` indexes the schemes. Each scheme is one file:

| Key | Content |
|---|---|
| `scheme`, `title`, `node_kind` or `attaches_to` | Identity. `attaches_to: finding` marks labels that tag findings instead of creating nodes. |
| `reuse` | field, discipline or general. |
| `external_ids` | `scheme` (e.g. MONDO, ChEBI, UBERON, Cognitive Atlas) or `none_assigned`, and coverage. |
| `matching` | Key normalization and the ordered steps used for entity labels, overview labels or tags (rule types below). |
| `field_groups` | Fields read by the match steps, by role or by name. |
| `concepts` | `label`, `aliases`, `exact_keys`, `patterns` (`order`, `pattern`, `flags`), `parent`, `ids`, `status`, `defined_in`. |

Rule types the engine must provide, taken from the current code:

| Rule type | Behaviour | Current example |
|---|---|---|
| `labels_and_aliases`, exact | Normalized key equals a label or alias. | `match_vocabulary_entity` |
| `labels_and_aliases`, contained | Text contains labels; one match is assigned, several are marked as a combination. | `match_vocabulary_entity` |
| `exact_keys` | Lookup table from normalized key to label. | `SUBJECTIVE_EXPERIENCE_LABEL_FALLBACKS` |
| `patterns`, first match | Regexes tried in declared order; the first match wins. | `SUBJECTIVE_EXPERIENCE_RULES` |
| `patterns`, earliest in text | The match that starts earliest in the text wins; summary labels rank last. | `safety_category_for_text` |
| `patterns`, all | Every matching label is assigned once. | `PUBLIC_HEALTH_USE_CONTEXT_RULES` |
| `constraints` | A label is suppressed when another is present. | Self-treatment and Clinical care |
| `not_graphable` | Keys kept in detail views but excluded from the overview graph. | `GENERIC_BEHAVIOR_NOT_GRAPHABLE_KEYS` |
| `parent` | Concepts grouped under a parent in the overview. | `MOLECULAR_SUBTOPIC_RULES_BY_PARENT` |
| `display_override` | A different label shown in the interface. | `CONDITION_GRAPH_LABEL_OVERRIDES` |

[psychedelics/vocabularies/subjective_experience_construct.yaml](psychedelics/vocabularies/subjective_experience_construct.yaml) and [real_world_use_context.yaml](psychedelics/vocabularies/real_world_use_context.yaml) are generated from the current sources by `tools/export_concept_scheme.py`. The tool checks that the regexes, labels and order read back identically.

### 5.7 views.yaml

`projection` (graph admission, presentation and API eligibility as three separate decisions; report thresholds; unit counted; subject and parent grouping), `graph_views` (labels, object kinds, label filters), page categories, `facets`, `presentation`. One grouping definition should serve the graph, entity pages and the analysis workspace.

### 5.8 questions.yaml

Per question: `id`, `question`, `needs` (finding shapes, domains, fields, facets), `answered_by` (view or API operation), `status` (supported, partial, not supported), `gap`, `test`. Schema and view decisions should be traceable to at least one question.

### 5.9 validation.yaml

| Stage | Required content |
|---|---|
| Search | Completion check; an independently assembled seed set (for example the included studies of recent systematic reviews, or reports named by experts before the search) and the share retrieved. |
| Screening | Reference set drawn at random from both included and excluded records, its size and its reviewer. |
| Extraction | Development sets and a separate holdout set, error categories, coverage measure, reviewer. |
| Normalization | Replay of saved extractions before and after a change, with positive controls. |
| Release | Checks that must pass before publication. |
| Open issues | Known limits that the graph card must state. |

Reviewer type is one of `human_expert`, `human_non_expert`, `ai_model` or `mixed`, with names or model identifiers. A set reviewed by an AI model is reported as such and is not described as a gold standard.

### 5.10 site.yaml

Names, addresses, citation, licences, identifiers used inside service contracts (derived from the protocol id), presentation tokens and the pages that contain field text.

## 6. How the engine uses the protocol

**Screening instructions** are composed from two parts. The engine part covers record handling, publication format, language, identity conflicts, the decision object and paper types. The protocol part covers research area, anchor eligibility, qualifying contribution, purpose exclusions, the review coverage rule, domain definitions and validity modifiers. In the current v6.1 text these parts are 8,213 and 14,680 characters.

**Extraction instructions** are composed from the paper-type instruction (base profile), the domain instruction (protocol) and the schema. The schema combines the base observation fields with the domain fields, and every field carries a role annotation. Paper-level schemas for meta-analyses and reviews are base-profile content, except for their list of evidence domains, which the engine inserts from `domains.yaml` (today the list is written into both schemas as an enum).

**Normalization** applies the concept schemes and the anchor registry. Field bindings are derived from role annotations.

**Projection and publication** follow `views.yaml` and `site.yaml`. API resource names and schema version strings are built from the protocol id.

## 7. Change management

| Change | Version part | Stages that run again | New model calls |
|---|---|---|---|
| Site text or presentation | patch | site build | none |
| Views, thresholds, facets, display labels | minor | graph build, site | none |
| Concept scheme aliases, patterns, parents | minor | normalization replay, graph build | none |
| Anchor registry synonyms | minor | prescreen and screening of affected records; search for new names | for affected records |
| Domain instruction or schema | minor or major | extraction for that domain, then downstream | for that domain |
| Search modules or terms | minor | discovery of new records, then downstream for them | for new records |
| Eligibility rules | major | screening of affected candidates, then downstream | for affected records |
| Evidence domain added or removed | major | screening classification and extraction | yes |
| Base profile change | per inheriting protocol | as above, by change type | as above |

The repository already has the parts this needs: the scoped updater (`pipeline/update/run_scoped_paper_update.py`), saved intermediate extractions, the replay tool (`pipeline/kg/replay_extraction_release.py`) and input fingerprints. A protocol diff would select the stages and records to process.

## 8. Graph card

Each release produces a graph card with these fields. Unknown values are reported as unknown.

| Group | Fields |
|---|---|
| Release | release id, protocol version, literature date, engine version, model identifiers |
| Corpus | records retrieved, records screened, reports included by type, share with full text |
| Search | seed set size, share of seed set retrieved |
| Screening | reference set size, reviewer type, error share among included and among excluded records |
| Extraction | reference set size, reviewer type, central-finding coverage, share of papers with a material error |
| Normalization | mapped share per node kind, unresolved mappings, external identifier coverage per node kind |
| Graph | findings, relationships, relationships outside all views, unit counted (report or study) |
| Cost | model cost per stage, expert hours per stage |
| Limitations | free text |

## 9. Base profiles

A base profile holds content shared by protocols in a discipline. Examples are paper types, publication-format exclusions, study designs, population and model categories, experimental systems, comparators, follow-up windows, assay families, administration routes, pharmacokinetic parameters and matrices, result-direction vocabulary and the shared observation role fields. The migration inventory marks about 1,300 lines of code tables as base-profile candidates (class E) and a further 2,200 lines of concept rules as discipline-level (class V, reuse discipline).

The base profile should be defined after a second protocol exists. Content that both protocols actually use goes into the base profile; content used by one stays in that protocol.

## 10. Format check against a second field: computational psychiatry

This example tests whether the format can describe a field with a different finding shape. The content is illustrative and needs review by a domain expert.

```yaml
anchor: null                         # decision D1: no single anchor type
node_kinds:
  model_parameter: {qualifier: computational_model}   # a parameter is defined within a model
  computational_model: {}
  task: {external_ids: Cognitive Atlas}
  condition: {external_ids: MONDO}
  symptom_dimension: {}
finding_shapes:
  group_difference_in_parameter:
    roles:
      subject: population contrast (condition versus comparison group) or symptom dimension
      object: model_parameter
      qualifier: computational_model
      context: [task, estimation_method, model_comparison_result, parameter_recovery_reported, sample_size]
      result: [direction, statistic, value]
  intervention_effect_on_parameter:   # links to the psychedelics protocol through shared drug and task identifiers
    roles: {subject: drug or other intervention, object: model_parameter, qualifier: computational_model, context: [task, dose_or_regimen]}
  parameter_reliability:
    roles: {object: model_parameter, qualifier: computational_model, context: [task, retest_interval], result: [reliability_coefficient]}
```

The check shows two requirements that the psychedelics protocol did not expose: a protocol may have no anchor type, and an object may need a qualifier. It also shows a primary finding whose subject is a population contrast rather than an exposure. The role list in section 5.4 covers all three cases.

## 11. Open decisions

| Id | Decision | Proposal |
|---|---|---|
| D1 | Must every protocol declare one anchor type? | No. The anchor is optional; finding shapes carry roles. |
| D2 | Concept match rules as regexes or as term lists? | Term lists by default, generated into regexes by the engine; regexes allowed with test cases. |
| D3 | Are protocol code hooks (R8) allowed? | Yes, with size reported in the graph card and a review when a hook recurs. |
| D4 | Which external identifier schemes are required per node kind? | Compounds PubChem/ChEMBL, conditions MONDO, targets HGNC and UniProt, anatomy UBERON, tasks Cognitive Atlas; others optional. |
| D5 | Where do base profiles live and who maintains them? | In `protocols/base/`, maintained with the engine. |
| D6 | Does the interface compute facets or read them from the build? | Read them from the build, so classification exists in one place. |
| D7 | Licence for protocol files | CC0, the same as project data, so others can reuse protocols. |
