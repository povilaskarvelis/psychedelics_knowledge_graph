# Comprehensive Search Protocol

This protocol defines the literature search for the psychedelic knowledge
graph.

## Goal

Find literature and source-database records that may support either:

- psychedelic compound -> molecular target evidence
- psychedelic compound -> brain region, circuit, network, or
  cognitive-behavioral task evidence
- psychedelic compound -> clinical evidence

The search is deliberately broad. Relevance is decided later by screening and
extraction, not by assuming that every retrieved DOI belongs in the KG.

## Source Of Truth

The search is generated from the current registries in
`pipeline/config.example.yaml`:

- `validation.allowed_compounds`
- `validation.allowed_targets`
- `validation.allowed_brain_regions_and_networks`
- `validation.allowed_cognitive_behavioral_tasks`
- `validation.allowed_disorders` for clinical evidence concepts

If the scope changes, update those registries first and regenerate the search
files. Do not hand-edit generated seed files.

## Generated Files

The exact search files and manifests are:

- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/mechanistic_boolean_openalex_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/mechanistic_boolean_pubmed_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/disorder_boolean_openalex_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/disorder_boolean_pubmed_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/boolean_search_modules_manifest.json`
- `data/raw/search_strategies/comprehensive_baseline_v1/mechanistic_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/mechanistic_search_manifest.json`
- `data/raw/search_strategies/comprehensive_baseline_v1/disorder_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/disorder_search_manifest.json`
- `data/raw/search_strategies/comprehensive_baseline_v1/search_strategy_summary.json`
- `data/raw/search_strategies/systems_neuroscience_2026_05/grouped_modules/mechanistic_grouped_openalex_systems_neuroscience_seeds.csv`
- `data/raw/search_strategies/systems_neuroscience_2026_05/grouped_modules/mechanistic_grouped_pubmed_systems_neuroscience_seeds.csv`
- `data/raw/search_strategies/systems_neuroscience_2026_05/grouped_modules/grouped_search_modules_manifest.json`
- `data/raw/search_strategies/systems_neuroscience_2026_05/direct_pairs/mechanistic_search_manifest.json`
- `data/raw/search_strategies/systems_neuroscience_2026_05/grouped_module_run/grouped_search_run_summary.md`

Regenerate the generated seed files with:

```bash
python pipeline/ingest/build_boolean_search_modules.py --dataset all
python pipeline/ingest/build_comprehensive_search_plan.py --dataset all --profile baseline
python pipeline/ingest/build_boolean_search_modules.py --run-id systems_neuroscience_2026_05 --dataset mechanistic
python pipeline/ingest/build_comprehensive_search_plan.py --run-id systems_neuroscience_2026_05 --dataset mechanistic --profile standard
```

The current command-line interface still uses existing dataset flags in
generated filenames and commands. The methods framing treats the generated
files as domain-specific search instruments in one discovery pipeline.

## Query Construction

Searches are run in PubMed for curated biomedical indexing and OpenAlex for
broader scholarly coverage.

Each query module is generated from three concept blocks:

```text
(compound or drug-class synonyms)
AND (domain-specific entity, endpoint, or outcome synonyms)
AND (evidence-context terms)
```

Terms inside each block are joined with OR. PubMed queries use
`[Title/Abstract]` fields. Clinical population and outcome modules apply
`NOT (animals[MeSH Terms] NOT humans[MeSH Terms])`; molecular, brain-system,
cognitive-behavioral, and preclinical/translational modules retain animal, in
vitro, assay, and neurophysiology records when those records are in scope.
OpenAlex modules submit the generated query text through the OpenAlex works
API. No publication-date or language restriction is applied during discovery.

Clinical evidence terms include clinical trial, randomized/randomised, placebo,
open-label/open label, phase 2, phase 3, treatment, therapy, efficacy, safety,
tolerability, outcome, and follow-up. Molecular target terms include binding,
affinity, Ki, Kd, IC50, EC50, radioligand, functional assay, agonist,
antagonist, partial agonist, and signaling. Brain-system and
cognitive-behavioral terms include fMRI, BOLD, functional connectivity, PET,
receptor occupancy, EEG, MEG, neural oscillations, electrophysiology, c-Fos,
brain-region activation, circuit dynamics, and cognitive or behavioral task
paradigms. Molecular-pathway, clinical-symptom/functioning, safety, and
clinical endpoint modules add endpoint-specific terms for pathways, gene or
protein expression, safety outcomes, functioning outcomes, and clinical links to
brain, molecular, cognitive, behavioral, or neurophysiology endpoints.

## Search Module Families

| Evidence domain | Module type | Modules | Cap per source/module |
|---|---|---|---:|
| Targets | Primary broad | serotonin receptors; monoamine transporters; glutamate/NMDA/AMPA/mGluR2 targets; opioid, sigma, and TAAR targets; TrkB and target-linked plasticity evidence | 500 |
| Targets | Dense topic | LSD-5-HT2A; psilocin/psilocybin-5-HT2A; MDMA transporters; ketamine-NMDA; salvinorin A-kappa opioid receptor | 1,000 |
| Pathways and readouts | Primary broad | molecular plasticity pathways; gene-expression/transcriptomics; inflammatory and neuroendocrine molecular readouts | 500 |
| Pathways and readouts | Dense topic | ketamine/psychedelic mTOR-synaptogenesis; immediate early genes | 1,000 |
| Brain systems, circuits, and neurophysiology | Primary broad | systems neuroimaging/connectivity; brain regions and circuits; PET/receptor occupancy/metabolism; EEG/MEG/neurophysiology | 500 |
| Brain systems, circuits, and neurophysiology | Dense topic | psilocybin-default mode connectivity; LSD-thalamocortical connectivity; DMT-EEG/fMRI dynamics; ayahuasca-default mode connectivity; psilocybin-PET/5-HT2A occupancy; ketamine-prefrontal/hippocampal circuitry | 1,000 |
| Cognitive and behavioral function | Primary broad | cognitive-affective tasks; translational behavioral assays | 500 |
| Cognitive and behavioral function | Dense topic | MDMA-social reward/cognition; psychedelic fear extinction/flexibility | 1,000 |
| Clinical outcomes, symptoms, functioning, and safety | Primary broad | clinical class core; depression spectrum; PTSD and trauma; substance use and addiction; anxiety, distress, and palliative care; pain, headache, and migraine; OCD, eating disorders, and autism; clinical symptoms/functioning/quality of life; clinical safety/tolerability/adverse events | 500 |
| Clinical outcomes, symptoms, functioning, and safety | Dense topic | psilocybin-depression; MDMA-PTSD; ketamine-depression-suicidality; ibogaine-opioid/substance use disorder; LSD-alcohol/anxiety; suicidality/anhedonia/sleep/function; craving/relapse/functioning; cardiovascular/mania/psychosis/HPPD safety | 1,000 |
| Clinical studies with biological and behavioral endpoints | Primary broad | clinical population modules with brain, molecular, cognitive, and behavioral endpoints; clinical outcome endpoint modules | 500 |
| Clinical studies with biological and behavioral endpoints | Dense topic | psilocybin depression brain and molecular endpoints; ketamine depression molecular endpoints; psilocybin depression brain/molecular endpoints; MDMA PTSD social-brain endpoints | 1,000 |

Generated files preserve run IDs and source-specific seed files for audit, but
the modules above are interpreted as one first-build discovery strategy.

## Pairwise Search Scope

The search plan also includes generated pairwise search files. These files
search selected compound-entity and compound-outcome combinations directly
alongside the query modules. The direct-pair layer is supplementary to the
grouped domain searches: it is used most densely where the pair space is
bounded, and later domain additions use targeted pair checks rather than an
exhaustive cross-product of every possible compound and concept.

| Direct-pair domain | Focused direct pairs | Pair-core search seeds |
|---|---:|---:|
| Molecular target pairs included in the target/brain/task layer | 1,840 | 5,520 |
| Target, brain/network, and task pairs | 5,440 | 16,320 |
| Clinical evidence pairs | 1,240 | 3,717 |

The expanded direct-pair instrument also contains class-level, compound-broad,
entity-broad, and sentinel default seeds, giving 16,876 total generated strings
for molecular target, brain/network, and task entities.

After the additional domain searches, a targeted direct-pair check was run in
PubMed and OpenAlex for selected compound/entity/outcome combinations. Any
records identified through that check enter the same candidate corpus and carry
search-run provenance through downstream metadata enrichment and screening.

## Literature Databases

The literature discovery run uses OpenAlex and PubMed query modules.
PubMed/PMC, Crossref, Semantic Scholar, and open-access
metadata sources are used after DOI discovery to add bibliographic details,
check open-access status, and identify available full text.

The searches start with the query-module files:

```bash
python pipeline/ingest/discover_literature.py \
  --dataset mechanistic \
  --provider openalex \
  --seed-file data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/mechanistic_boolean_openalex_seeds.csv \
  --max-results-per-seed 500 \
  --max-results 0 \
  --disable-ledger \
  --disable-protected-retention \
  --skip-unpaywall-enrichment
```

```bash
python pipeline/ingest/discover_literature.py \
  --dataset disorder \
  --provider pubmed \
  --seed-file data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/disorder_boolean_pubmed_seeds.csv \
  --max-results-per-seed 500 \
  --max-results 0
```

The pair-grid files run direct searches for rare corners of the
compound-entity and compound-clinical evidence space. Records already present
in the paper library are reported but not re-added as new papers.

The brain-system grouped modules run through the grouped-module runner
so the module scope is explicit:

```bash
python pipeline/ingest/run_boolean_module_searches.py \
  --run-id systems_neuroscience_2026_05 \
  --dataset mechanistic \
  --provider all \
  --module-type all \
  --module-scope systems_neuroscience \
  --openalex-search-field title_and_abstract \
  --skip-existing
```

For the full search, query modules should run deeper than pairwise search
seeds:

| Search layer | Recommended cap |
|---|---:|
| Primary query modules | 500 |
| Dense-topic query modules | 1,000 |
| Pairwise searches, molecular target/brain/task | 20-50 |
| Pairwise searches, clinical evidence | 10-20 |

The generated query CSV files include `recommended_max_results_per_seed` so
dense topics can be run deeper than broad primary modules if we split execution
by module type.

The query-module builder also writes module-type-specific seed files, for
example:

- `mechanistic_boolean_openalex_primary_boolean_seeds.csv` at cap 500
- `mechanistic_boolean_openalex_dense_topic_seeds.csv` at cap 1,000
- `disorder_boolean_pubmed_primary_boolean_seeds.csv` at cap 500
- `disorder_boolean_pubmed_dense_topic_seeds.csv` at cap 1,000

## Search Execution Outputs

Search execution outputs are stored under
`data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/full_boolean_v1/`.
The brain-system grouped output is stored under
`data/raw/search_strategies/systems_neuroscience_2026_05/grouped_module_run/`.
Run summaries and PRISMA-style flow outputs report records identified,
duplicate DOI records, invalid DOI records, screening outcomes, full-text
access status, and extraction status. These counts describe the flow of records
through the workflow; they do not define graph inclusion. A DOI becomes graph
evidence only after screening, full-text or abstract-only labeling, structured
extraction, and validation.

## Source-Specific Supplements

Some sources are not ordinary literature-search engines and should be handled as
source-specific supplements:

- ChEMBL for assay-level compound-target activity
- BindingDB for binding-affinity cross-checks
- ClinicalTrials.gov for registered clinical studies and linked publications

These supplement outputs should be linked to papers and evidence records, but
not treated as ordinary DOI search seeds.

## Quality Checks

Quality checks focus on reproducibility and downstream eligibility:

- generated search files are derived from the versioned registries,
- discovered records are normalized by DOI before insertion,
- duplicate DOI records are logged instead of re-added,
- relevance is decided by deterministic pre-screening, LLM abstract screening,
  full-text access status, structured extraction, and validation.

## Search Design Notes

This strategy follows core high-recall literature discovery principles:
explicit scope, documented sources, reproducible query generation, DOI
deduplication, and supplement layers. The search design separates three roles:

1. **Query-family searches**: source-specific query blocks that combine
   compound/class synonyms, domain-specific entity or outcome synonyms, and
   evidence terms.
2. **Pairwise searches**: compound-entity and compound-outcome pairs run
   directly so rare combinations are represented in the search.
3. **Source-specific supplements**: ChEMBL, BindingDB, ClinicalTrials.gov, and
   citation chasing, because those sources are not ordinary ranked DOI search
   results.

The all-pairs grid is useful because it tests every compound-entity or
compound-outcome combination in the registry. Retrieved records still require
screening and extraction before they can support graph evidence.

## Brain/Circuit/Network And Cognitive-Behavioral Layer

The brain-system and cognitive-behavioral domain is defined in
`docs/brain_cognition_search_strategy.md`. It uses the same discovery,
deduplication, screening, extraction, and KG publication pipeline as the rest of
the search. The domain adds grouped query modules and direct pair-search
instruments for brain regions, named circuits, functional networks,
neuroimaging and neurophysiology modalities, and cognitive-behavioral task
domains.

Brain-system evidence should not collapse into molecular-target evidence.
Region/network/task entities should carry their own entity kind through
screening, extraction, normalization, and graph export.

## Updates

Later literature updates should be documented as date-bounded update searches
using the same protocol version. If a major missing entity family is added,
update the registries, regenerate the search files, and record that as a
protocol revision.
