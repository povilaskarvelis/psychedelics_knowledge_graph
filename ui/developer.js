const devEls = {
  snapshot: document.getElementById("devSnapshot"),
  snapshotStamp: document.getElementById("devSnapshotStamp"),
  stageIndex: document.getElementById("devStageIndex"),
  flowScroll: document.getElementById("devFlowScroll"),
  flowMap: document.getElementById("devFlowMap"),
  flowNodes: document.getElementById("devFlowNodes"),
  connectors: document.getElementById("devFlowConnectors"),
  detail: document.getElementById("devStageDetail"),
  search: document.getElementById("devStageSearch"),
  reset: document.getElementById("devResetView"),
  artifactMatrix: document.getElementById("devArtifactMatrix"),
};

const DEV_DATASETS = ["mechanistic", "disorder"];
const DEV_LABELS = {
  mechanistic: "Mechanistic",
  disorder: "Indications",
};

const DEV_STAGES = [
  {
    id: "scope",
    title: "Scope and Registries",
    kicker: "Stage 1",
    phase: "Planning",
    depth: "core",
    variant: "scope",
    col: 1,
    row: 2,
    summary:
      "Defines the compound universe, target and indication vocabularies, and local aliases that all downstream search, screening, and normalization steps rely on.",
    implementation: [
      "Local registries are treated as the authority for public graph endpoints.",
      "Search code may use broader configured compound terms, but clean graph edges still have to resolve back to the registry.",
      "Disorder aliases are canonicalized separately so overlapping labels collapse to one public node.",
    ],
    inputs: ["docs/domain_scope.md", "pipeline/config.example.yaml", "data/curated/entity_registry.json"],
    outputs: ["Configured term blocks", "Registry-backed graph endpoint universe"],
    files: ["pipeline/config.example.yaml", "data/curated/entity_registry.json", "schema/disorder_canonicalization.json"],
    commands: [],
    snippet:
      "Entity registry -> search terms -> extraction candidates -> deterministic normalizer\n\nOnly registry-matched compound + endpoint pairs become clean public graph edges.",
    changeSignals: [
      "Add aliases here when normalization audits show repeated unmapped labels.",
      "Avoid expanding this layer with broad neuroscience terms unless they are intended graph endpoints.",
    ],
  },
  {
    id: "search-planning",
    title: "Search Planning",
    kicker: "Stage 2",
    phase: "Discovery",
    depth: "core",
    variant: "search",
    col: 2,
    row: 2,
    summary:
      "Generates the search files used for grouped literature searches and direct compound-target or compound-indication pair searches.",
    implementation: [
      "Grouped modules cover broad topic areas with structured term blocks.",
      "Direct pair searches catch rare combinations that broad grouped queries can miss.",
      "Run labels separate provenance for batches, but they are not conceptual pipeline stages.",
    ],
    inputs: ["Configured compound, target, and indication registries"],
    outputs: ["data/raw/search_strategies/<run_id>/grouped_modules/*", "data/raw/search_strategies/<run_id>/direct_pairs/*"],
    files: ["pipeline/ingest/build_boolean_search_modules.py", "pipeline/ingest/build_comprehensive_search_plan.py"],
    commands: [
      "python pipeline/ingest/build_boolean_search_modules.py --dataset all --run-id search_2026_05",
      "python pipeline/ingest/build_comprehensive_search_plan.py --dataset all --profile standard --run-id search_2026_05",
    ],
    snippet:
      "Grouped search modules = broad recall layer\nDirect pair searches = targeted recall layer\n\nBoth write generated search files before provider calls begin.",
    changeSignals: [
      "Tune grouped-module caps when noise is too high.",
      "Tune direct pair caps when rare compound/entity combinations are missing.",
    ],
  },
  {
    id: "discovery",
    title: "Provider Discovery",
    kicker: "Stage 3",
    phase: "Discovery",
    depth: "core",
    variant: "search",
    col: 3,
    row: 2,
    summary:
      "Queries scholarly providers, captures DOI candidates, and records provider/run provenance before papers are added to the corpus.",
    implementation: [
      "Provider adapters cover PubMed, PMC, OpenAlex, Crossref, Semantic Scholar, and combined modes.",
      "Batch runners make grouped and direct-pair searches resumable.",
      "Discovery is paper-level; it does not decide final evidence claims.",
    ],
    inputs: ["Generated seed files", "Provider-specific run configuration"],
    outputs: ["data/raw/doi_queue.<dataset>.discovered.txt", "data/processed/discovery_report_<dataset>.json", "data/processed/discovery_ledger_<dataset>.json"],
    files: ["pipeline/ingest/discover_literature.py", "pipeline/ingest/run_boolean_module_searches.py", "pipeline/ingest/run_pair_grid_audit.py"],
    commands: [
      "python pipeline/ingest/run_boolean_module_searches.py --run-id search_2026_05 --provider all --dataset all",
      "python pipeline/ingest/run_pair_grid_audit.py --run-id search_2026_05 --provider both",
    ],
    snippet:
      "provider results -> normalized DOI candidates -> discovery report + ledger\n\nDiscovery provenance is preserved even when a DOI is already known.",
    changeSignals: [
      "Check provider overlap and recall audits before treating a search as complete.",
      "Keep discovery reports append-only enough to diagnose why a DOI entered the corpus.",
    ],
  },
  {
    id: "doi-gate",
    title: "DOI Add Gate",
    kicker: "Stage 4",
    phase: "Corpus",
    depth: "core",
    variant: "gate",
    col: 4,
    row: 2,
    summary:
      "Normalizes DOI strings and admits only papers that are not already present in the paper corpus.",
    implementation: [
      "Deduplication happens at DOI level before expensive metadata and PDF work.",
      "Rediscovered papers are logged for provenance rather than re-added as new papers.",
      "Invalid, missing, and duplicate input rows are exported for audit.",
    ],
    inputs: ["data/raw/doi_queue.<dataset>.discovered.txt"],
    outputs: ["data/raw/doi_queue.<dataset>.new.txt", "data/processed/rediscovered_dois_<dataset>.csv", "data/processed/missing_or_invalid_dois_<dataset>.csv"],
    files: ["pipeline/ingest/add_new_dois.py"],
    commands: ["python pipeline/ingest/add_new_dois.py --dataset mechanistic --input data/raw/doi_queue.mechanistic.discovered.txt"],
    snippet:
      "normalize DOI -> compare against paper corpus -> write new DOI queue\n\nRediscovery is provenance, not a new downstream paper.",
    changeSignals: [
      "If a paper seems missing, check rediscovered DOI reports before rerunning search.",
      "If many invalid DOI rows appear, inspect provider parsing before metadata sync.",
    ],
  },
  {
    id: "metadata-sync",
    title: "Metadata and Abstract Sync",
    kicker: "Stage 5",
    phase: "Corpus",
    depth: "core",
    variant: "corpus",
    col: 5,
    row: 2,
    summary:
      "Builds the paper library with bibliographic metadata, abstracts, identifiers, open-access flags, and PDF candidate URLs.",
    implementation: [
      "Metadata providers are tried in a configured fallback order.",
      "The same script can run metadata-only or PDF retrieval depending on flags and DOI queue.",
      "The paper inventory is the reviewable paper-level database for the rest of the pipeline.",
    ],
    inputs: ["data/raw/doi_queue.<dataset>.new.txt", "pipeline/config.local.yaml"],
    outputs: ["data/processed/paper_library_<dataset>.json", "data/processed/paper_inventory_<dataset>.md", "data/processed/paper_inventory_<dataset>.csv"],
    files: ["pipeline/ingest/sync_paper_library.py"],
    commands: [
      "python pipeline/ingest/sync_paper_library.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.new.txt --skip-download --checkpoint-every 100 --progress-every 100",
    ],
    snippet:
      "provider order: pubmed, pmc, unpaywall, crossref, openalex, semantic_scholar\n\nMetadata first; PDF bytes only after screening.",
    changeSignals: [
      "Change provider order when metadata completeness or API reliability changes.",
      "Inspect paper inventory rows when downstream screening lacks abstracts.",
    ],
  },
  {
    id: "abstract-screening",
    title: "Abstract Screening",
    kicker: "Overview",
    phase: "Screening",
    depth: "overview",
    variant: "screen",
    col: 6,
    row: 2,
    summary:
      "High-recall screening cascade: deterministic exclusion only for obvious no-signal rows, then local LLM screening for retained title/abstract records.",
    implementation: [
      "Relevant and uncertain rows remain eligible for full-text retrieval and extraction preparation.",
      "LLM results require quote-supported compound/entity contexts.",
      "Screening is non-destructive and writes reports plus DOI queues.",
    ],
    inputs: ["paper_library rows with abstracts"],
    outputs: ["deterministic prescreen reports", "llm abstract screening reports", "full-text candidate DOI queues"],
    files: ["pipeline/review/run_local_llm_abstract_screening.py"],
    commands: [
      "python pipeline/review/run_local_llm_abstract_screening.py --dataset disorder --deterministic-prescreen --deterministic-prescreen-only --only-with-abstract --only-undownloaded",
      "python pipeline/review/run_local_llm_abstract_screening.py --dataset disorder --doi-file data/raw/doi_queue.disorder.deterministic_prescreen_retained.txt --model qwen3:14b --only-with-abstract --continue-on-error --timeout-sec 0 --resume-from-checkpoint --num-ctx 4096",
    ],
    snippet:
      "paper library -> deterministic pre-screen -> local LLM screening -> relevant/uncertain/full-text queues",
    changeSignals: [
      "Re-audit any future deterministic tightening against checkpointed LLM decisions.",
      "Use uncertain rows as a safety valve instead of forcing hard exclusions from abstracts.",
    ],
  },
  {
    id: "deterministic-prescreen",
    title: "Deterministic Pre-Screen",
    kicker: "Internal",
    phase: "Screening",
    depth: "detail",
    variant: "screen",
    col: 6,
    row: 1,
    summary:
      "Fast rule gate that excludes only rows with no in-scope compound/intervention signal in the title or abstract.",
    implementation: [
      "In-scope compound and intervention terms escalate a row to LLM review.",
      "Broad psychiatric treatment language also escalates to avoid brittle false negatives.",
      "Discovery contexts are not used as safety hints for deterministic exclusion.",
    ],
    inputs: ["paper library row", "configured allowed compounds", "hardcoded synonym maps"],
    outputs: ["deterministic_prescreen_report_<dataset>.json", "doi_queue.<dataset>.deterministic_prescreen_retained.txt", "doi_queue.<dataset>.deterministic_prescreen_excluded.txt"],
    files: ["pipeline/review/run_local_llm_abstract_screening.py"],
    commands: [
      "python pipeline/review/run_local_llm_abstract_screening.py --dataset mechanistic --deterministic-prescreen --deterministic-prescreen-only --only-with-abstract",
    ],
    snippet:
      "if matched_in_scope_intervention_terms(context):\n    return {\"action\": \"escalate\"}\n\nreturn {\n    \"action\": \"exclude_obvious_irrelevant\",\n    \"reason\": \"No in-scope compound/intervention term appears in title/abstract\"\n}",
    changeSignals: [
      "This gate should stay conservative; missed relevant papers here never reach the LLM.",
      "Ambiguous acronyms need supporting chemical/class language before they block exclusion.",
    ],
  },
  {
    id: "llm-screening",
    title: "Local LLM Screening",
    kicker: "Internal",
    phase: "Screening",
    depth: "detail",
    variant: "screen",
    col: 7,
    row: 1,
    summary:
      "Classifies retained abstracts as relevant, uncertain, or irrelevant and verifies exact abstract quotes for supported compound/entity contexts.",
    implementation: [
      "The default local model is qwen3:14b through Ollama.",
      "Checkpoint materialization lets long runs write reports and queues without recalling the model.",
      "Relevant and uncertain rows drive downstream PDF retrieval and extraction cohorts.",
    ],
    inputs: ["deterministic retained DOI queue", "paper_library rows with abstracts"],
    outputs: ["llm_abstract_screening_report_<dataset>*.json", "doi_queue.<dataset>.llm_fulltext_candidates*.txt", "doi_queue.<dataset>.llm_relevant*.txt", "doi_queue.<dataset>.llm_uncertain*.txt"],
    files: ["pipeline/review/run_local_llm_abstract_screening.py"],
    commands: [
      "python pipeline/review/run_local_llm_abstract_screening.py --dataset disorder --doi-file data/raw/doi_queue.disorder.deterministic_prescreen_retained.txt --model qwen3:14b --only-with-abstract --continue-on-error --timeout-sec 0 --resume-from-checkpoint --num-ctx 4096",
      "python pipeline/review/run_local_llm_abstract_screening.py --dataset disorder --materialize-checkpoint-only --only-with-abstract",
    ],
    snippet:
      "LLM relevance -> quote verification -> supported contexts -> DOI queues\n\nllm_fulltext_candidates = relevant + uncertain papers for PDF acquisition.",
    changeSignals: [
      "If quote verification drops many rows, inspect prompt/schema drift before excluding papers.",
      "Keep run labels descriptive of search batches, not method names.",
    ],
  },
  {
    id: "pdf-retrieval",
    title: "PDF Retrieval",
    kicker: "Stage 6",
    phase: "Full Text",
    depth: "core",
    variant: "fulltext",
    col: 8,
    row: 2,
    summary:
      "Downloads legally available open-access PDFs for papers screened as relevant or uncertain.",
    implementation: [
      "The downloader reuses metadata candidates from PMC, Europe PMC, Unpaywall, OpenAlex, publishers, and repositories.",
      "PDF status is retained in the paper library so unavailable full texts remain auditable.",
      "Retry and manual import tools exist for failed/no-URL rows.",
    ],
    inputs: ["doi_queue.<dataset>.llm_fulltext_candidates*.txt", "paper_library metadata"],
    outputs: ["data/raw/papers/<dataset>/pdfs/*.pdf", "pdf_download_status in paper library"],
    files: ["pipeline/ingest/sync_paper_library.py", "pipeline/ingest/retry_pdf_downloads.py", "pipeline/ingest/import_manual_pdfs.py"],
    commands: [
      "python pipeline/ingest/sync_paper_library.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.llm_fulltext_candidates.txt --metadata-provider-order pubmed,pmc,unpaywall,crossref,openalex,semantic_scholar --checkpoint-every 100 --progress-every 100",
    ],
    snippet:
      "screened DOI queue -> ranked PDF candidates -> valid local PDF or auditable unavailable status",
    changeSignals: [
      "Separate no-PDF, failed download, invalid existing PDF, and not-open-access cases.",
      "Do not treat missing full text as irrelevance; it becomes an abstract-only/needs-text readiness state.",
    ],
  },
  {
    id: "fulltext-conversion",
    title: "Full-Text Conversion",
    kicker: "Stage 7",
    phase: "Full Text",
    depth: "core",
    variant: "fulltext",
    col: 9,
    row: 2,
    summary:
      "Converts local PDFs into structured full-text artifacts with reproducible provenance for extraction and locator repair.",
    implementation: [
      "GROBID is the primary backend for scholarly articles.",
      "Managed batching can restart GROBID between batches for long conversion runs.",
      "Artifacts stay separate from curated claims; conversion alone does not edit claims.",
    ],
    inputs: ["local PDFs", "optional DOI queues"],
    outputs: ["data/processed/fulltext/<dataset>/*.json", "data/processed/fulltext/fulltext_report_<dataset>.json"],
    files: ["pipeline/fulltext/convert_pdfs.py", "pipeline/fulltext/run_fulltext_provenance.py", "pipeline/fulltext/start_grobid.py"],
    commands: [
      "python pipeline/fulltext/convert_pdfs.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.llm_fulltext_candidates.txt --backend grobid --only-missing-artifacts",
      "python pipeline/fulltext/run_fulltext_provenance.py --dataset all --backend grobid --limit 0 --include-existing-artifacts",
    ],
    snippet:
      "PDF -> GROBID TEI/sections/tables/figures -> full-text JSON artifact\n\nClaim rows are not mutated by this step.",
    changeSignals: [
      "Conversion failures should be triaged separately from PDF download failures.",
      "Use stale locator repair reports only through an explicit accepted-review apply gate.",
    ],
  },
  {
    id: "extraction-prep",
    title: "Extraction Cohort Build",
    kicker: "Stage 8",
    phase: "Extraction",
    depth: "core",
    variant: "extract",
    col: 10,
    row: 2,
    summary:
      "Combines manifest-listed screening reports into DOI-level extraction candidates and assigns readiness states.",
    implementation: [
      "The corpus manifest decides which completed screening runs are included in the current corpus.",
      "Relevant and uncertain papers are deduplicated by DOI per dataset.",
      "Each DOI is routed to full-text-ready, abstract-only, or needs-text queues.",
    ],
    inputs: ["data/processed/corpus_manifest.json", "llm abstract screening reports", "paper_library rows", "full-text artifacts"],
    outputs: ["data/processed/extraction/*_extraction_candidates.jsonl", "data/raw/doi_queue.*.extraction_fulltext_ready.txt", "data/raw/doi_queue.*.extraction_abstract_only.txt", "data/processed/extraction/extraction_readiness_report.json"],
    files: ["pipeline/extract/prepare_extraction_inputs.py"],
    commands: ["python pipeline/extract/prepare_extraction_inputs.py --dataset all"],
    snippet:
      "manifest reports + paper library + full-text status -> one extraction candidate per DOI\n\nThe candidate files are regenerated views, not hand-edited sources.",
    changeSignals: [
      "To include a new run, add its completed screening report to corpus_manifest.json.",
      "If a DOI is missing here, check the manifest before checking extraction code.",
    ],
  },
  {
    id: "packet-build",
    title: "Evidence Packet Build",
    kicker: "Internal",
    phase: "Extraction",
    depth: "detail",
    variant: "extract",
    col: 11,
    row: 1,
    summary:
      "Builds model-ready full-text packet JSONL from converted artifacts and paper-library metadata.",
    implementation: [
      "Full-text packets preserve DOI metadata and structured document sections.",
      "The lean_primary profile keeps title/abstract metadata, methods/results-like chunks, tables, and marker-matched mechanistic or clinical sections.",
      "The extraction workflow can omit prior candidate contexts so the model extracts from paper text itself.",
      "Packet reports record what was included, omitted, or missing.",
    ],
    inputs: ["data/raw/doi_queue.<dataset>.extraction_fulltext_ready.txt", "data/processed/fulltext/<dataset>/*.json"],
    outputs: ["data/processed/extraction/<dataset>_fulltext_packets.jsonl", "data/processed/extraction/<dataset>_fulltext_packets_report.json"],
    files: ["pipeline/fulltext/build_llm_evidence_packets.py"],
    commands: [
      "python pipeline/fulltext/build_llm_evidence_packets.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.extraction_fulltext_ready.txt --out-jsonl data/processed/extraction/mechanistic_fulltext_packets.jsonl --report-json data/processed/extraction/mechanistic_fulltext_packets_report.json --omit-section-text --omit-candidate-contexts --packet-profile lean_primary --max-references 0",
    ],
    snippet:
      "converted full text + paper metadata -> extraction packet\n\n--packet-profile lean_primary reduces body text before Gemini extraction.\n--omit-candidate-contexts keeps earlier hints out of the model input.",
    changeSignals: [
      "If extraction quality looks anchored to old screening contexts, verify packet flags.",
      "Use packet reports to distinguish missing artifacts from intentionally omitted content.",
    ],
  },
  {
    id: "abstract-only-path",
    title: "Abstract-Only Path",
    kicker: "Branch",
    phase: "Extraction",
    depth: "detail",
    variant: "branch",
    col: 11,
    row: 3,
    summary:
      "Retains relevant or uncertain papers without usable full text for lower-confidence abstract-only extraction or future retrieval.",
    implementation: [
      "Abstract-only candidates are explicit readiness states, not silent exclusions.",
      "The extraction protocol allows abstract inputs but keeps evidence location and access level visible.",
      "Needs-text rows remain separate when no useful abstract/full text exists.",
    ],
    inputs: ["doi_queue.<dataset>.extraction_abstract_only.txt", "paper library abstracts"],
    outputs: ["abstract input records", "readiness report counts"],
    files: ["pipeline/extract/prepare_extraction_inputs.py", "docs/extraction_v1_protocol.md"],
    commands: [],
    snippet:
      "full_text_ready -> packet extraction\nabstract_only -> abstract input extraction\nneeds_text -> wait for better source",
    changeSignals: [
      "Do not mix abstract-only claims with full-text claims without preserving access_level.",
      "High-impact abstract-only rows are good candidates for manual PDF acquisition.",
    ],
  },
  {
    id: "claim-extraction",
    title: "Extraction V1 Model Pass",
    kicker: "Stage 9",
    phase: "Extraction",
    depth: "core",
    variant: "extract",
    col: 12,
    row: 2,
    summary:
      "Runs extraction-v1 records through Gemini using a strict schema, local JSON cleanup, and resumable raw checkpoints.",
    implementation: [
      "The model returns one JSON object per paper with paper assessment, claims, and coverage mentions.",
      "Gemini sees a dataset-specific native response_json_schema view; parsed results are validated against the full canonical schema.",
      "Malformed JSON is first repaired locally, then optionally through one model repair call.",
      "Deterministic post-processing normalizes predictable slips before validation.",
    ],
    inputs: [
      "extraction_v1 pilot or production input JSONL",
      "docs/extraction_v1_prompt.md",
      "docs/extraction_v1_mechanistic_prompt.md",
      "docs/extraction_v1_disorder_prompt.md",
      "schema/extraction_v1.schema.json",
    ],
    outputs: ["data/processed/extraction/extraction_v1_outputs.jsonl", "data/processed/extraction/extraction_v1_gemini_raw.jsonl", "data/processed/extraction/extraction_v1_gemini_report.json"],
    files: [
      "pipeline/extract/run_gemini_extraction_v1.py",
      "pipeline/extract/extraction_v1_utils.py",
      "docs/extraction_v1_prompt.md",
      "docs/extraction_v1_mechanistic_prompt.md",
      "docs/extraction_v1_disorder_prompt.md",
      "schema/extraction_v1.schema.json",
    ],
    commands: [
      "python pipeline/extract/build_extraction_v1_pilot.py --dataset all --per-bucket 10",
      "python pipeline/extract/run_gemini_extraction_v1.py --input-jsonl data/processed/extraction/extraction_v1_pilot_inputs.jsonl --out-jsonl data/processed/extraction/extraction_v1_outputs.jsonl --raw-jsonl data/processed/extraction/extraction_v1_gemini_raw.jsonl --report-json data/processed/extraction/extraction_v1_gemini_report.json --limit 50 --overwrite",
    ],
    snippet:
      "system instruction = shared prompt + dataset addendum\nresponse_json_schema = compact dataset schema view\nrecord content = INPUT_RECORD_JSON\n\nparse strictly -> local cleanup -> optional model repair -> canonical schema validation",
    changeSignals: [
      "Route counts shifting toward context_only or human_review usually signal prompt or packet issues.",
      "Raw JSONL is the audit trail for response text, repair method, usage, and normalization changes.",
    ],
  },
  {
    id: "qa-projection",
    title: "QA and Projection",
    kicker: "Internal",
    phase: "Extraction",
    depth: "detail",
    variant: "validate",
    col: 13,
    row: 1,
    summary:
      "Checks extraction outputs, verifies supporting quotes against input context, and projects valid outputs into canonical claim rows.",
    implementation: [
      "QA flags schema errors, missing quote support, and rows needing review.",
      "Projection validates extraction-v1 inputs and skips invalid objects.",
      "Projected claim files are broad inspection surfaces before graph normalization.",
    ],
    inputs: ["extraction_v1_outputs.jsonl", "extraction_v1_pilot_inputs.jsonl"],
    outputs: ["extraction_v1_qa_report.json", "extraction_v1_qa_rows.csv", "mechanistic_claims.json", "disorder_claims.json", "projection_report.json"],
    files: ["pipeline/extract/qa_extraction_v1_outputs.py", "pipeline/extract/project_extraction_v1_claims.py"],
    commands: [
      "python pipeline/extract/qa_extraction_v1_outputs.py --input-jsonl data/processed/extraction/extraction_v1_outputs.jsonl --pilot-input-jsonl data/processed/extraction/extraction_v1_pilot_inputs.jsonl",
      "python pipeline/extract/project_extraction_v1_claims.py --input-jsonl data/processed/extraction/extraction_v1_outputs.jsonl --pilot-input-jsonl data/processed/extraction/extraction_v1_pilot_inputs.jsonl",
    ],
    snippet:
      "extraction output -> QA report\nvalid extraction output -> projected mechanistic/disorder claim rows\n\nProjection is broad; normalization decides clean graph eligibility.",
    changeSignals: [
      "Review rows with unsupported quotes before trusting extracted evidence locators.",
      "Projection output can be inspected without touching legacy curated files.",
    ],
  },
  {
    id: "human-review",
    title: "Human Review Queues",
    kicker: "Branch",
    phase: "Validation",
    depth: "detail",
    variant: "branch",
    col: 13,
    row: 3,
    summary:
      "Holds uncertain, invalid, unsupported, or manually flagged rows out of clean graph promotion until reviewed.",
    implementation: [
      "The extraction schema carries confidence and review flags.",
      "QA, projection, and normalization reports expose why rows were held back.",
      "Accepted repair and cleanup scripts require explicit apply flags.",
    ],
    inputs: ["QA rows", "projection report", "normalization audits", "curator decisions"],
    outputs: ["review CSVs", "audit JSON", "curated corrections"],
    files: ["pipeline/fulltext/apply_provenance_repairs.py", "pipeline/validate/*.py", "pipeline/extract/normalize_extraction_claims.py"],
    commands: [],
    snippet:
      "automatic extraction can propose rows\nclean graph promotion requires schema checks + registry normalization + review of flagged rows",
    changeSignals: [
      "High counts of human_review route suggest the model is seeing mixed primary/secondary papers.",
      "Apply scripts should stay dry-run by default unless a review file is explicitly accepted.",
    ],
  },
  {
    id: "normalization",
    title: "Deterministic Normalization",
    kicker: "Stage 10",
    phase: "Validation",
    depth: "core",
    variant: "normalize",
    col: 14,
    row: 2,
    summary:
      "Converts broad projected claims into registry-backed clean graph rows and writes audit files for every held-back claim.",
    implementation: [
      "The model's graph intent fields are suggestions, not truth.",
      "Rows must be graph candidates, have the expected endpoint type, use an allowed entity role, and match local registries.",
      "Audit files preserve non-graph, unmapped, and wrong-type rows for inspection.",
    ],
    inputs: ["data/processed/extraction/mechanistic_claims.json", "data/processed/extraction/disorder_claims.json", "data/curated/entity_registry.json"],
    outputs: ["mechanistic_graph_claims.json", "disorder_graph_claims.json", "mechanistic_normalization_audit.json", "disorder_normalization_audit.json", "normalization_report.json"],
    files: ["pipeline/extract/normalize_extraction_claims.py", "docs/normalization_layer.md"],
    commands: ["python pipeline/extract/normalize_extraction_claims.py"],
    snippet:
      "if not graph_include_candidate:\n    status = \"not_graph_candidate\"\nelif wrong endpoint type or role:\n    status = \"wrong_graph_entity_type/non_graph_entity_role\"\nelif compound or endpoint is unmapped:\n    status = \"compound_unmapped/entity_unmapped\"\nelse:\n    status = \"normalized\"",
    changeSignals: [
      "Use high-frequency unmapped labels to improve entity_registry.json.",
      "Keep external ontologies as proposal/enrichment tools, not silent graph authorities.",
    ],
  },
  {
    id: "graph-payload",
    title: "Main Graph Payloads",
    kicker: "Publish",
    phase: "Publish",
    depth: "core",
    variant: "publish",
    col: 15,
    row: 1,
    summary:
      "Exports deterministic JSON payloads consumed by the public graph UI, with stable IDs, evidence views, and manifest hashes.",
    implementation: [
      "The default claim source is the normalized KG evidence-table layer.",
      "Alternative claim sources can export projected Gemini extraction rows or legacy curated rows for comparison.",
      "Manifest hashes make payload changes easier to audit.",
    ],
    inputs: ["data/processed/kg/*.parquet", "projected or normalized claim rows", "dataset schemas"],
    outputs: ["data/processed/graph_payload_*.json", "data/processed/graph_payload_manifest.json"],
    files: ["pipeline/publish/export_graph_payload.py", "pipeline/publish/export_bibliography_payload.py"],
    commands: [
      "python pipeline/kg/build_evidence_tables.py",
      "python pipeline/publish/export_graph_payload.py",
      "python pipeline/publish/export_graph_payload.py --claim-source gemini_normalized",
    ],
    snippet:
      "claim rows -> schema validation -> deterministic external_id -> graph payload views -> manifest with SHA-256 digests",
    changeSignals: [
      "If UI counts do not match extraction counts, inspect claim_source in graph_payload_manifest.json.",
      "Use secondary-source views deliberately; protocols/commentary remain contextual by default.",
    ],
  },
  {
    id: "kg-methods",
    title: "Methods/KG Projection",
    kicker: "Publish",
    phase: "Publish",
    depth: "detail",
    variant: "publish",
    col: 15,
    row: 3,
    summary:
      "Builds the generated PRISMA-style paper flow used by the methods page.",
    implementation: [
      "This stage projects the corpus manifest, paper libraries, screening reports, full-text status, and normalized KG claims into visualization data.",
      "It does not replace the main-page graph payload exporter.",
      "Methods paper-flow analytics update by regenerating data/kg, not by editing UI files.",
    ],
    inputs: ["corpus manifest", "paper libraries", "abstract-screening reports", "full-text status", "data/processed/kg/claims.parquet"],
    outputs: ["data/kg/views/pipeline_status_graph.json", "data/kg/manifests/build_manifest.json"],
    files: ["pipeline/kg/build_methods_flow.py", "ui/methods.js"],
    commands: ["python pipeline/kg/build_methods_flow.py --refresh-kg-tables"],
    snippet:
      "corpus + screening + full-text + normalized KG claims -> methods PRISMA flow",
    changeSignals: [
      "If the methods page says data is unavailable, regenerate this stage.",
      "Add new completed screening reports to corpus_manifest.json before rebuilding.",
    ],
  },
  {
    id: "ui",
    title: "UI Consumption",
    kicker: "Interface",
    phase: "Publish",
    depth: "core",
    variant: "publish",
    col: 16,
    row: 2,
    summary:
      "Static UI pages read generated JSON artifacts for the graph, methods analytics, bibliography, and this developer workbench.",
    implementation: [
      "The public graph reads processed graph payloads and bibliography payloads.",
      "The methods page reads the data/kg pipeline-status view for the PRISMA flow.",
      "This developer page reads the same generated reports plus its own authored implementation map.",
    ],
    inputs: ["data/processed/graph_payload_*.json", "data/kg/views/pipeline_status_graph.json", "data/processed/extraction/extraction_readiness_report.json"],
    outputs: ["ui/index.html graph", "ui/methods.html analytics", "ui/developer.html pipeline workbench"],
    files: ["ui/app.js", "ui/methods.js", "ui/developer.js", "ui/styles.css"],
    commands: ["python3 -m http.server"],
    snippet:
      "generated JSON artifacts are the interface contract\n\nUI code should display provenance rather than inventing pipeline state.",
    changeSignals: [
      "If a page needs new counts, prefer adding them to generated reports over hardcoding UI values.",
      "Keep developer.html unlinked from public navigation until deployment auth/gating is added.",
    ],
  },
  {
    id: "legacy-maintenance",
    title: "Legacy Stub Maintenance",
    kicker: "Legacy",
    phase: "Maintenance",
    depth: "detail",
    variant: "legacy",
    col: 11,
    row: 4,
    summary:
      "Older DOI stub, abstract autofill, PDF autofill, and promotion path retained for maintaining first-generation graph data.",
    implementation: [
      "This path creates context-level stubs keyed by DOI plus compound plus target/disorder.",
      "Autofill scripts populate missing metadata or older schema fields.",
      "Promotion writes curated JSON/CSV only when run with explicit apply flags.",
    ],
    inputs: ["triage-relevant DOI queues", "processed stub files", "curator-reviewed ready flags"],
    outputs: ["data/curated/claims.json", "data/curated/disorder_claims.json", "promotion reports"],
    files: ["pipeline/ingest/seed_from_dois.py", "pipeline/review/autofill_stubs_from_abstracts.py", "pipeline/extract/promote_ready_stubs.py"],
    commands: [
      "python pipeline/ingest/seed_from_dois.py --dataset disorder --doi-file data/raw/doi_queue.disorder.llm_relevant.txt --replace",
      "python pipeline/extract/promote_ready_stubs.py --dataset disorder --apply",
    ],
    snippet:
      "DOI queue -> context stubs -> autofill/curation -> promote ready stubs\n\nUseful for maintenance; not the canonical extraction-v1 path.",
    changeSignals: [
      "Use legacy exports only as explicit comparison or maintenance sources.",
      "Do not let legacy stub state silently override extraction-v1 generated claims.",
    ],
  },
];

const DEV_EDGES = [
  ["scope", "search-planning", "both"],
  ["search-planning", "discovery", "both"],
  ["discovery", "doi-gate", "both"],
  ["doi-gate", "metadata-sync", "both"],
  ["metadata-sync", "abstract-screening", "overview"],
  ["abstract-screening", "pdf-retrieval", "overview"],
  ["metadata-sync", "deterministic-prescreen", "detail"],
  ["deterministic-prescreen", "llm-screening", "detail"],
  ["llm-screening", "pdf-retrieval", "detail"],
  ["pdf-retrieval", "fulltext-conversion", "both"],
  ["fulltext-conversion", "extraction-prep", "both"],
  ["llm-screening", "extraction-prep", "detail", "branch"],
  ["extraction-prep", "packet-build", "detail"],
  ["extraction-prep", "abstract-only-path", "detail", "branch"],
  ["packet-build", "claim-extraction", "detail"],
  ["abstract-only-path", "claim-extraction", "detail", "branch"],
  ["extraction-prep", "claim-extraction", "overview"],
  ["claim-extraction", "qa-projection", "detail"],
  ["qa-projection", "human-review", "detail", "branch"],
  ["qa-projection", "normalization", "detail"],
  ["claim-extraction", "normalization", "overview"],
  ["normalization", "graph-payload", "both"],
  ["normalization", "kg-methods", "detail", "branch"],
  ["graph-payload", "ui", "both"],
  ["kg-methods", "ui", "detail", "branch"],
  ["metadata-sync", "legacy-maintenance", "detail", "legacy"],
  ["legacy-maintenance", "graph-payload", "detail", "legacy"],
].map(([source, target, mode, kind = "main"]) => ({ source, target, mode, kind }));

const devState = {
  mode: "detail",
  query: "",
  selectedId: "scope",
  live: {
    pipelineStatus: null,
    extractionReadiness: null,
    graphManifest: null,
    errors: [],
  },
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "n/a";
  const number = Number(value);
  if (!Number.isFinite(number)) return "n/a";
  return new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format(number);
}

function normalizeText(value) {
  return String(value || "").trim().toLowerCase();
}

function stageById(id) {
  return DEV_STAGES.find((stage) => stage.id === id);
}

function stageMatchesQuery(stage, query) {
  if (!query) return true;
  const haystack = [
    stage.title,
    stage.kicker,
    stage.phase,
    stage.summary,
    ...(stage.files || []),
    ...(stage.inputs || []),
    ...(stage.outputs || []),
    ...(stage.commands || []),
    ...(stage.implementation || []),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function stageVisible(stage) {
  const modeOk = stage.depth === "core" || stage.depth === devState.mode || (devState.mode === "detail" && stage.depth === "detail");
  return modeOk && stageMatchesQuery(stage, devState.query);
}

function visibleStages() {
  return DEV_STAGES.filter(stageVisible);
}

function edgeVisible(edge, visibleIds) {
  const modeOk = edge.mode === "both" || edge.mode === devState.mode;
  return modeOk && visibleIds.has(edge.source) && visibleIds.has(edge.target);
}

async function fetchJsonFromCandidates(candidates) {
  const errors = [];
  const dataFetchOptions =
    ["", "localhost", "127.0.0.1", "::1"].includes(window.location.hostname) ? { cache: "no-store" } : {};
  for (const url of candidates) {
    try {
      const response = await fetch(url, dataFetchOptions);
      if (!response.ok) {
        errors.push(`${url}: HTTP ${response.status}`);
        continue;
      }
      return await response.json();
    } catch (error) {
      errors.push(`${url}: ${error.message}`);
    }
  }
  throw new Error(errors.join("; "));
}

async function loadLiveData() {
  const requests = [
    ["pipelineStatus", ["../data/kg/views/pipeline_status_graph.json", "/data/kg/views/pipeline_status_graph.json"]],
    ["extractionReadiness", ["../data/processed/extraction/extraction_readiness_report.json", "/data/processed/extraction/extraction_readiness_report.json"]],
    ["graphManifest", ["../data/processed/graph_payload_manifest.json", "/data/processed/graph_payload_manifest.json"]],
  ];
  const results = await Promise.allSettled(requests.map(([, candidates]) => fetchJsonFromCandidates(candidates)));
  results.forEach((result, index) => {
    const key = requests[index][0];
    if (result.status === "fulfilled") {
      devState.live[key] = result.value;
    } else {
      devState.live.errors.push(`${key}: ${result.reason.message}`);
    }
  });
}

function statusCount(dataset, group, key) {
  return Number(devState.live.pipelineStatus?.counts?.[`${dataset}:${group}`]?.[key] || 0);
}

function sumStatus(group, keys) {
  return DEV_DATASETS.reduce(
    (sum, dataset) => sum + keys.reduce((inner, key) => inner + statusCount(dataset, group, key), 0),
    0,
  );
}

function readinessDataset(dataset) {
  return (devState.live.extractionReadiness?.datasets || []).find((item) => item.dataset === dataset) || null;
}

function sumReadiness(path) {
  return DEV_DATASETS.reduce((sum, dataset) => {
    const report = readinessDataset(dataset);
    if (!report) return sum;
    return sum + Number(path(report) || 0);
  }, 0);
}

function graphRowsTotal() {
  const datasets = devState.live.graphManifest?.datasets || {};
  return DEV_DATASETS.reduce((sum, dataset) => sum + Number(datasets?.[dataset]?.row_count || 0), 0);
}

function stageMetrics(stageId) {
  const selectedCandidates = sumReadiness((report) => report.summary?.selected_unique_dois);
  const fullTextReady = sumReadiness((report) => report.summary?.by_readiness_status?.full_text_ready);
  const abstractOnly = sumReadiness((report) => report.summary?.by_readiness_status?.abstract_only_needs_pdf_access);
  const metrics = {
    "deterministic-prescreen": [
      ["Excluded", sumStatus("screening", ["excluded_deterministic_prescreen"])],
      ["Retained", sumStatus("screening", ["retained_for_llm_screening"])],
    ],
    "llm-screening": [
      ["Relevant", sumStatus("screening", ["included_llm_relevant"])],
      ["Uncertain", sumStatus("screening", ["included_llm_uncertain"])],
      ["Errors", sumStatus("screening", ["llm_screening_error"])],
    ],
    "abstract-screening": [
      ["Relevant", sumStatus("screening", ["included_llm_relevant"])],
      ["Uncertain", sumStatus("screening", ["included_llm_uncertain"])],
    ],
    "pdf-retrieval": [
      ["Downloaded", sumStatus("pdf", ["downloaded"])],
      ["Failed", sumStatus("pdf", ["download_failed"])],
      ["Not OA", sumStatus("pdf", ["not_open_access"])],
    ],
    "fulltext-conversion": [
      ["Converted", sumStatus("fulltext", ["converted"])],
      ["Not converted", sumStatus("fulltext", ["not_converted"])],
    ],
    "extraction-prep": [
      ["Candidates", selectedCandidates],
      ["Full text ready", fullTextReady],
      ["Abstract only", abstractOnly],
    ],
    "packet-build": [["Full text ready", fullTextReady]],
    "abstract-only-path": [["Abstract only", abstractOnly]],
    "claim-extraction": [
      ["Claim available", sumStatus("llm_extraction", ["claim_available"])],
      ["Not started", sumStatus("llm_extraction", ["not_started"])],
    ],
    "normalization": [["Published rows", graphRowsTotal()]],
    "graph-payload": [["Payload rows", graphRowsTotal()]],
    "ui": [["Payload rows", graphRowsTotal()]],
  };
  return metrics[stageId] || [];
}

function compactMetric(stageId) {
  const metrics = stageMetrics(stageId).filter(([, value]) => Number(value) > 0);
  if (!metrics.length) return "";
  const [label, value] = metrics[0];
  return `${formatNumber(value)} ${label.toLowerCase()}`;
}

function renderSnapshot() {
  const selectedCandidates = sumReadiness((report) => report.summary?.selected_unique_dois);
  const fullTextReady = sumReadiness((report) => report.summary?.by_readiness_status?.full_text_ready);
  const abstractOnly = sumReadiness((report) => report.summary?.by_readiness_status?.abstract_only_needs_pdf_access);
  const extracted = sumStatus("llm_extraction", ["claim_available"]);
  const published = graphRowsTotal();
  const generatedAt =
    devState.live.extractionReadiness?.generated_at_utc ||
    devState.live.pipelineStatus?.generated_at ||
    devState.live.graphManifest?.generated_at ||
    "";

  if (devEls.snapshotStamp) {
    devEls.snapshotStamp.textContent = generatedAt
      ? `Generated artifact snapshot: ${generatedAt}`
      : "Generated artifact snapshot unavailable.";
  }

  const cards = [
    ["Extraction candidates", selectedCandidates],
    ["Full-text ready", fullTextReady],
    ["Abstract-only", abstractOnly],
    ["Claim available", extracted],
    ["Published graph rows", published],
  ];

  devEls.snapshot.innerHTML = cards
    .map(
      ([label, value]) => `
        <article>
          <span>${escapeHtml(label)}</span>
          <strong>${formatNumber(value)}</strong>
        </article>
      `,
    )
    .join("");
}

function renderStageNode(stage) {
  const selected = stage.id === devState.selectedId;
  const metric = compactMetric(stage.id);
  return `
    <button
      class="dev-node dev-node-${escapeHtml(stage.variant)}${selected ? " selected" : ""}"
      type="button"
      data-stage-id="${escapeHtml(stage.id)}"
      style="grid-column: ${stage.col}; grid-row: ${stage.row};"
    >
      <span class="dev-node-kicker">${escapeHtml(stage.kicker)}</span>
      <strong>${escapeHtml(stage.title)}</strong>
      <span>${escapeHtml(stage.summary)}</span>
      ${metric ? `<em>${escapeHtml(metric)}</em>` : ""}
    </button>
  `;
}

function renderStageIndex() {
  const stages = visibleStages();
  devEls.stageIndex.innerHTML = stages
    .map((stage) => {
      const selected = stage.id === devState.selectedId;
      return `
        <button class="${selected ? "selected" : ""}" type="button" data-stage-id="${escapeHtml(stage.id)}">
          <span>${escapeHtml(stage.kicker)}</span>
          <strong>${escapeHtml(stage.title)}</strong>
        </button>
      `;
    })
    .join("");
  devEls.stageIndex.querySelectorAll("[data-stage-id]").forEach((button) => {
    button.addEventListener("click", () => selectStage(button.dataset.stageId, true));
  });
}

function renderFlow() {
  const stages = visibleStages();
  if (!stages.some((stage) => stage.id === devState.selectedId)) {
    devState.selectedId = stages[0]?.id || "scope";
  }
  devEls.flowNodes.innerHTML = stages.map(renderStageNode).join("");
  devEls.flowNodes.querySelectorAll("[data-stage-id]").forEach((button) => {
    button.addEventListener("click", () => selectStage(button.dataset.stageId, false));
  });
  requestAnimationFrame(drawConnectors);
}

function connectorPoint(sourceEl, targetEl, mapRect) {
  const sourceRect = sourceEl.getBoundingClientRect();
  const targetRect = targetEl.getBoundingClientRect();
  const sourceCenter = {
    x: sourceRect.left - mapRect.left + sourceRect.width / 2,
    y: sourceRect.top - mapRect.top + sourceRect.height / 2,
  };
  const targetCenter = {
    x: targetRect.left - mapRect.left + targetRect.width / 2,
    y: targetRect.top - mapRect.top + targetRect.height / 2,
  };
  const horizontal = targetCenter.x >= sourceCenter.x;
  return {
    x1: horizontal ? sourceRect.right - mapRect.left : sourceRect.left - mapRect.left,
    y1: sourceCenter.y,
    x2: horizontal ? targetRect.left - mapRect.left : targetRect.right - mapRect.left,
    y2: targetCenter.y,
  };
}

function drawConnectors() {
  const svg = devEls.connectors;
  const map = devEls.flowMap;
  if (!svg || !map) return;
  const visibleIds = new Set(visibleStages().map((stage) => stage.id));
  const mapRect = map.getBoundingClientRect();
  const width = map.scrollWidth;
  const height = map.scrollHeight;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.innerHTML = `
    <defs>
      <marker id="devArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z"></path>
      </marker>
    </defs>
  `;

  DEV_EDGES.filter((edge) => edgeVisible(edge, visibleIds)).forEach((edge) => {
    const sourceEl = devEls.flowNodes.querySelector(`[data-stage-id="${edge.source}"]`);
    const targetEl = devEls.flowNodes.querySelector(`[data-stage-id="${edge.target}"]`);
    if (!sourceEl || !targetEl) return;
    const { x1, y1, x2, y2 } = connectorPoint(sourceEl, targetEl, mapRect);
    const distance = Math.max(70, Math.abs(x2 - x1) * 0.45);
    const c1 = x2 >= x1 ? x1 + distance : x1 - distance;
    const c2 = x2 >= x1 ? x2 - distance : x2 + distance;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("class", `dev-edge dev-edge-${edge.kind}`);
    path.setAttribute("d", `M ${x1} ${y1} C ${c1} ${y1}, ${c2} ${y2}, ${x2} ${y2}`);
    path.setAttribute("marker-end", "url(#devArrow)");
    svg.appendChild(path);
  });
}

function renderList(items) {
  if (!items || !items.length) return `<p class="dev-empty">None specified.</p>`;
  return `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function renderCommands(commands) {
  if (!commands || !commands.length) return `<p class="dev-empty">No regular command for this node.</p>`;
  return commands
    .map(
      (command, index) => `
        <div class="dev-command">
          <button class="ghost small" type="button" data-copy-command="${index}">Copy</button>
          <pre><code>${escapeHtml(command)}</code></pre>
        </div>
      `,
    )
    .join("");
}

function renderMetrics(metrics) {
  if (!metrics.length) return "";
  return `
    <div class="dev-detail-metrics">
      ${metrics
        .map(
          ([label, value]) => `
            <span>
              <strong>${formatNumber(value)}</strong>
              ${escapeHtml(label)}
            </span>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderDetail() {
  const stage = stageById(devState.selectedId) || visibleStages()[0] || DEV_STAGES[0];
  const metrics = stageMetrics(stage.id);
  devEls.detail.innerHTML = `
    <div class="dev-detail-heading">
      <span>${escapeHtml(stage.phase)} / ${escapeHtml(stage.kicker)}</span>
      <h2>${escapeHtml(stage.title)}</h2>
      <p>${escapeHtml(stage.summary)}</p>
    </div>
    ${renderMetrics(metrics)}
    <details open>
      <summary>Implementation</summary>
      ${renderList(stage.implementation)}
    </details>
    <details open>
      <summary>Inputs</summary>
      ${renderList(stage.inputs)}
    </details>
    <details open>
      <summary>Outputs</summary>
      ${renderList(stage.outputs)}
    </details>
    <details>
      <summary>Source Files</summary>
      ${renderList(stage.files)}
    </details>
    <details ${stage.commands.length ? "open" : ""}>
      <summary>Commands</summary>
      ${renderCommands(stage.commands)}
    </details>
    <details open>
      <summary>Code / Logic Focus</summary>
      <pre class="dev-snippet"><code>${escapeHtml(stage.snippet)}</code></pre>
    </details>
    <details open>
      <summary>Watch Points</summary>
      ${renderList(stage.changeSignals)}
    </details>
  `;
  devEls.detail.querySelectorAll("[data-copy-command]").forEach((button) => {
    button.addEventListener("click", async () => {
      const command = stage.commands[Number(button.dataset.copyCommand)];
      if (!command) return;
      try {
        await navigator.clipboard.writeText(command);
        button.textContent = "Copied";
        setTimeout(() => {
          button.textContent = "Copy";
        }, 1200);
      } catch (_) {
        button.textContent = "Select";
      }
    });
  });
}

function selectStage(stageId, scrollToNode) {
  if (!stageId || !stageById(stageId)) return;
  devState.selectedId = stageId;
  renderStageIndex();
  renderFlow();
  renderDetail();
  if (scrollToNode) {
    requestAnimationFrame(() => {
      devEls.flowNodes.querySelector(`[data-stage-id="${stageId}"]`)?.scrollIntoView({
        block: "nearest",
        inline: "center",
        behavior: "smooth",
      });
    });
  }
}

function setMode(mode) {
  devState.mode = mode === "overview" ? "overview" : "detail";
  document.querySelectorAll("[data-dev-mode]").forEach((button) => {
    const active = button.dataset.devMode === devState.mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  renderAll();
}

function datasetTableRow(dataset) {
  const readiness = readinessDataset(dataset);
  const graphRows = Number(devState.live.graphManifest?.datasets?.[dataset]?.row_count || 0);
  const values = [
    readiness?.summary?.selected_unique_dois,
    readiness?.summary?.by_best_llm_relevance?.relevant,
    readiness?.summary?.by_best_llm_relevance?.uncertain,
    readiness?.summary?.by_readiness_status?.full_text_ready,
    readiness?.summary?.by_readiness_status?.abstract_only_needs_pdf_access,
    statusCount(dataset, "pdf", "downloaded"),
    statusCount(dataset, "fulltext", "converted"),
    statusCount(dataset, "llm_extraction", "claim_available"),
    graphRows,
  ];
  return `
    <tr>
      <th scope="row">${escapeHtml(DEV_LABELS[dataset])}</th>
      ${values.map((value) => `<td>${formatNumber(value)}</td>`).join("")}
    </tr>
  `;
}

function renderArtifactMatrix() {
  if (!devEls.artifactMatrix) return;
  const hasAnyData = devState.live.pipelineStatus || devState.live.extractionReadiness || devState.live.graphManifest;
  if (!hasAnyData) {
    devEls.artifactMatrix.innerHTML = `
      <div class="methods-error">
        No generated pipeline reports could be loaded.
        <span>${escapeHtml(devState.live.errors.join("; "))}</span>
      </div>
    `;
    return;
  }
  devEls.artifactMatrix.innerHTML = `
    <table>
      <thead>
        <tr>
          <th scope="col">Dataset</th>
          <th scope="col">Candidates</th>
          <th scope="col">Relevant</th>
          <th scope="col">Uncertain</th>
          <th scope="col">Full text ready</th>
          <th scope="col">Abstract only</th>
          <th scope="col">PDF downloaded</th>
          <th scope="col">Converted full text</th>
          <th scope="col">Claim available</th>
          <th scope="col">Graph rows</th>
        </tr>
      </thead>
      <tbody>
        ${DEV_DATASETS.map(datasetTableRow).join("")}
      </tbody>
    </table>
  `;
}

function renderAll() {
  renderSnapshot();
  renderStageIndex();
  renderFlow();
  renderDetail();
  renderArtifactMatrix();
}

function initEvents() {
  document.querySelectorAll("[data-dev-mode]").forEach((button) => {
    button.addEventListener("click", () => setMode(button.dataset.devMode));
  });
  devEls.search?.addEventListener("input", () => {
    devState.query = normalizeText(devEls.search.value);
    renderAll();
  });
  devEls.reset?.addEventListener("click", () => {
    devState.query = "";
    devState.mode = "detail";
    devState.selectedId = "scope";
    if (devEls.search) devEls.search.value = "";
    setMode("detail");
  });
  window.addEventListener("resize", () => requestAnimationFrame(drawConnectors));
  devEls.flowScroll?.addEventListener("scroll", () => requestAnimationFrame(drawConnectors), { passive: true });
}

async function initDeveloperPipeline() {
  initEvents();
  renderAll();
  await loadLiveData();
  renderAll();
}

initDeveloperPipeline();
