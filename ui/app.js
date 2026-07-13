const graphEl = document.getElementById("graph");
const cardsEl = document.getElementById("cards");
const yearMinFilter = document.getElementById("yearMinFilter");
const yearMaxFilter = document.getElementById("yearMaxFilter");
const yearStepButtons = document.querySelectorAll(".year-step");
const searchInput = document.getElementById("searchInput");
const bibliographySearchInput = document.getElementById("bibliographySearchInput");
const tooltip = document.getElementById("tooltip");
const detailTitle = document.querySelector("#graphDetail h3");
const detailBody = document.getElementById("detailBody");
const claimLayerButtons = document.querySelectorAll("[data-claim-layer]");
const evidenceViewButtons = document.querySelectorAll("[data-evidence-view]");
const entityKindToggle = document.querySelector("[data-entity-kind-toggle]");
const studyListEl = document.getElementById("studyList");
const dataFetchOptions =
  ["", "localhost", "127.0.0.1", "::1"].includes(window.location.hostname) ? { cache: "no-store" } : {};

if (tooltip && tooltip.parentElement !== document.body) {
  document.body.appendChild(tooltip);
}

const stats = {
  primaryStudies: document.querySelector('[data-stat="primary-studies"]'),
  reviews: document.querySelector('[data-stat="reviews"]'),
  metaAnalyses: document.querySelector('[data-stat="meta-analyses"]'),
  totalPapers: document.querySelector('[data-stat="total-papers"]'),
};
const statDetails = {
  primaryStudies: document.querySelector('[data-stat-detail="primary-studies"]'),
  reviews: document.querySelector('[data-stat-detail="reviews"]'),
  metaAnalyses: document.querySelector('[data-stat-detail="meta-analyses"]'),
  totalPapers: document.querySelector('[data-stat-detail="total-papers"]'),
};

const HERO_STAT_KEYS = ["primaryStudies", "reviews", "metaAnalyses", "totalPapers"];
const evidenceRank = { low: 1, medium: 2, high: 3 };
const MAIN_FINDING_MAX_CHARS = 260;
const SAMPLE_YEAR_TARGET_BUCKET_COUNT = 14;
/** Chunk size for progressive rendering (IntersectionObserver loads more while scrolling). */
const LIST_CHUNK_SIZE = 120;
const FINDING_SEARCH_DEBOUNCE_MS = 70;

let cardsLoadObserver = null;
let bibliographyLoadObserver = null;
const GRAPH_COLOR_STOPS = [
  { r: 73, g: 214, b: 200 },
  { r: 119, g: 217, b: 141 },
  { r: 216, g: 210, b: 111 },
  { r: 241, g: 166, b: 106 },
  { r: 232, g: 117, b: 141 },
];
const CATEGORY_COLORS = [
  "#6fa79f",
  "#c0a160",
  "#b96c8b",
  "#7893b6",
  "#b98278",
  "#9ac5ae",
  "#a393b1",
  "#98ad8e",
  "#b29599",
  "#99a3c1",
  "#b397c5",
  "#72b899",
  "#c8807c",
  "#80a6c1",
  "#b2ab77",
  "#d698ae",
  "#9cb272",
  "#8eabd5",
  "#9c8ea9",
  "#8d939f",
  "#7da7a0",
  "#9b88b7",
  "#86abcb",
  "#b2be80",
  "#b49c84",
];
const PALETTE_BLUE_FIRST = CATEGORY_COLORS;
const PALETTE_TEAL_FIRST = CATEGORY_COLORS;
const PALETTE_ROSE_FIRST = CATEGORY_COLORS;
const PALETTE_SAGE_FIRST = CATEGORY_COLORS;
const PALETTE_GOLD_FIRST = CATEGORY_COLORS;
const OTHER_CATEGORY_COLOR = "#8f9ba8";
const PUBLICATION_YEAR_COLOR = "#3faea6";
const SAMPLE_SIZE_HEATMAP_COLOR = "#b89a5b";
const COGNITION_NODE_LABELS = [
  "Anhedonia",
  "Associative memory",
  "Attention",
  "Autobiographical memory",
  "Avoidance learning",
  "Cognitive flexibility",
  "Creativity",
  "Decentering",
  "Declarative memory",
  "Emotional processing",
  "Episodic memory",
  "Executive function",
  "Fear extinction",
  "Fear memory",
  "Global cognition",
  "Inhibitory control",
  "Memory",
  "Memory consolidation",
  "Memory retrieval",
  "Mindfulness",
  "Motivation",
  "Perceptual processing",
  "Processing speed",
  "Prospective memory",
  "Psychological flexibility",
  "Recognition memory",
  "Reversal learning",
  "Reward learning",
  "Reward processing",
  "Reward responsiveness",
  "Semantic memory",
  "Sensory memory",
  "Set shifting",
  "Short-term memory",
  "Social cognition",
  "Spatial memory",
  "Time perception",
  "Verbal memory",
  "Visual memory",
  "Visuospatial memory",
  "Working memory",
];
const BEHAVIORAL_EFFECT_NODE_LABELS = [
  "Anxiety-like behavior",
  "Conditioned place preference",
  "Compulsivity",
  "Craving",
  "Drug discrimination",
  "Drug cue reactivity",
  "Drug motivation",
  "Drug reinstatement",
  "Drug seeking",
  "Drug self-administration",
  "Head-twitch response",
  "Motor coordination",
  "Pain behavior",
  "Psychomotor sensitization",
  "Relapse",
  "Sensorimotor gating",
  "Social interaction",
  "Stress-coping behavior",
  "Threat avoidance",
];
const ENTITY_CATEGORY_OPTIONS = [
  { key: "condition_indication", label: "Conditions", singular: "Condition", lowerPlural: "conditions", lowerSingular: "condition" },
  {
    key: "safety_adverse_event",
    label: "Safety",
    singular: "Safety outcome",
    lowerPlural: "safety outcomes",
    lowerSingular: "safety outcome",
  },
  {
    key: "cognitive_behavioral_construct",
    label: "Cognition",
    singular: "Cognitive construct",
    lowerPlural: "cognitive constructs",
    lowerSingular: "cognitive construct",
    labels: COGNITION_NODE_LABELS,
  },
  {
    key: "behavioral_effect",
    kinds: ["cognitive_behavioral_construct"],
    label: "Behavior",
    singular: "Behavior",
    lowerPlural: "behavior",
    lowerSingular: "behavior",
    labels: BEHAVIORAL_EFFECT_NODE_LABELS,
  },
  {
    key: "subjective_experience_construct",
    label: "Subjective effects",
    singular: "Subjective effect",
    lowerPlural: "subjective effects",
    lowerSingular: "subjective effect",
  },
  {
    key: "intervention_component",
    label: "Treatment context",
    singular: "Treatment context",
    lowerPlural: "treatment context factors",
    lowerSingular: "treatment context factor",
  },
  {
    key: "public_health_measure",
    kinds: ["public_health_measure", "exposure_context"],
    domains: ["real_world_public_health"],
    label: "Real-world use",
    singular: "Real-world topic",
    lowerPlural: "real-world topics",
    lowerSingular: "real-world topic",
  },
  {
    key: "brain_system",
    kinds: ["brain_region", "brain_network", "neural_circuit"],
    label: "Brain regions",
    singular: "Brain region",
    lowerPlural: "brain regions",
    lowerSingular: "brain region",
  },
  {
    key: "pathway_readout",
    kinds: ["pathway_process", "biomarker_readout"],
    domains: ["molecular_pathway_readout", "pharmacokinetics_exposure"],
    label: "Molecular effects",
    singular: "Molecular effect",
    lowerPlural: "molecular effects",
    lowerSingular: "molecular effect",
  },
  {
    key: "target_system",
    kinds: ["target", "system_family"],
    label: "Targets",
    singular: "Target",
    lowerPlural: "targets",
    lowerSingular: "target",
  },
];
const ENTITY_CATEGORY_OPTION_SPECS = new Map(
  ENTITY_CATEGORY_OPTIONS.map((option) => [
    option.key,
    {
      kinds: new Set(Array.isArray(option.kinds) && option.kinds.length ? option.kinds : [option.key]),
      domains: new Set((Array.isArray(option.domains) ? option.domains : []).map(normalizeValue).filter(Boolean)),
      labels: new Set((Array.isArray(option.labels) ? option.labels : []).map(normalizeValue).filter(Boolean)),
    },
  ])
);
const CONDITION_GRAPH_LABEL_OVERRIDES = new Map([
  ["attention-deficit/hyperactivity disorder", "ADHD"],
  ["distress associated with life-threatening disease", "Distress in life-threatening illness"],
  ["nicotine dependence", "Tobacco use disorder"],
  ["suicidality", "Suicidal ideation & behavior"],
]);
const CONDITION_GRAPH_CLARIFIERS = new Map([
  ["bipolar disorder", "Umbrella or subtype-unspecified bipolar diagnosis."],
  ["bipolar i disorder", "Bipolar subtype defined by manic episodes."],
  ["bipolar ii disorder", "Bipolar subtype defined by hypomanic and depressive episodes."],
  ["bipolar depression", "Depressive episode or treatment phase within bipolar disorder."],
  ["mood disorders", "Broad category retained only when the source does not identify a more specific mood disorder."],
  ["eating disorders", "Broad or unspecified eating-disorder evidence; specific diagnoses remain separate."],
  ["headache disorders", "Broad or unspecified headache evidence; migraine and cluster headache remain separate."],
  ["substance use disorder", "Broad, mixed, or substance-unspecified evidence; named use disorders remain separate."],
  ["tobacco use disorder", "Includes literature using nicotine-dependence terminology."],
]);
const DETAIL_PANEL_PROFILE_DEFAULT = {
  experimentalSystem: false,
  sampleSizes: false,
  populationModel: false,
  comparators: false,
  followUpWindows: false,
  assayFamilies: false,
  brainMeasures: false,
  mechanisticRelationshipTypes: false,
  safetyContexts: false,
  doseRouteSessionContexts: false,
  studyDesigns: true,
  outcomeScales: false,
  publicHealthTopics: false,
  publicHealthContexts: false,
  publicHealthDataSources: false,
  trialRegistration: false,
};
const DETAIL_PANEL_PROFILE_BY_VIEW = {
  clinical_default: {
    sampleSizes: true,
    comparators: true,
    followUpWindows: true,
    trialRegistration: true,
  },
  mechanistic_default: {
    experimentalSystem: true,
    assayFamilies: true,
    mechanisticRelationshipTypes: true,
  },
  condition_indication: {
    sampleSizes: true,
    doseRouteSessionContexts: true,
    comparators: true,
    followUpWindows: true,
    outcomeScales: true,
    trialRegistration: true,
  },
  symptom_problem: {
    sampleSizes: true,
    doseRouteSessionContexts: true,
    comparators: true,
    followUpWindows: true,
    outcomeScales: true,
    trialRegistration: true,
  },
  safety_adverse_event: {
    sampleSizes: true,
    safetyContexts: true,
    doseRouteSessionContexts: true,
    trialRegistration: true,
  },
  cognitive_behavioral_construct: {
    sampleSizes: true,
    doseRouteSessionContexts: true,
    comparators: true,
    followUpWindows: true,
    trialRegistration: true,
  },
  behavioral_effect: {
    sampleSizes: true,
    doseRouteSessionContexts: true,
    comparators: true,
    followUpWindows: true,
    trialRegistration: true,
  },
  subjective_experience_construct: {
    sampleSizes: true,
    doseRouteSessionContexts: true,
    followUpWindows: true,
    trialRegistration: true,
  },
  intervention_component: {
    sampleSizes: true,
    doseRouteSessionContexts: true,
    trialRegistration: true,
  },
  public_health_measure: {
    sampleSizes: true,
    publicHealthContexts: true,
    publicHealthDataSources: true,
    trialRegistration: true,
  },
  target_system: {
    experimentalSystem: true,
    assayFamilies: true,
    mechanisticRelationshipTypes: true,
  },
  pathway_readout: {
    experimentalSystem: true,
    assayFamilies: true,
    mechanisticRelationshipTypes: true,
  },
  brain_system: {
    experimentalSystem: true,
    assayFamilies: true,
    brainMeasures: true,
    mechanisticRelationshipTypes: true,
  },
  brain_measure: {
    experimentalSystem: true,
    assayFamilies: true,
    brainMeasures: true,
    mechanisticRelationshipTypes: true,
  },
};
const REVIEW_DESIGN_LABELS = {
  systematic_review: "Systematic review",
  scoping_review: "Scoping review",
  umbrella_review: "Umbrella review",
  rapid_review: "Rapid review",
  narrative_or_literature_review: "Narrative or literature review",
  conceptual_or_theoretical_review: "Conceptual or theoretical review",
  critical_review: "Critical review",
  historical_review: "Historical review",
  bibliometric_or_landscape_review: "Bibliometric or landscape review",
  other_or_unclear: "Other review approach",
};
const REVIEW_CONTRIBUTION_LABELS = {
  evidence_synthesis: "Evidence synthesis",
  mechanistic_or_conceptual_review: "Mechanistic or conceptual",
  methodological_framework: "Methods or framework",
  research_landscape: "Research landscape",
  translational_or_practice_agenda: "Translation or practice",
  broad_topic_review: "Broad topic review",
  mixed: "Mixed focus",
};
const REVIEW_EVIDENCE_STRATUM_LABELS = {
  human: "Human evidence",
  preclinical: "Preclinical evidence",
  human_and_preclinical: "Human and preclinical",
  field_or_method: "Research field or methods",
  unclear: "Unclear evidence base",
};
const REVIEW_RELATIONSHIP_TYPE_LABELS = {
  review_synthesis: "Synthesis conclusion",
  reviewed_relationship: "Relationship reviewed",
  methodological_contribution: "Method or framework",
  research_landscape: "Research landscape",
  evidence_gap: "Evidence gap",
};
const REVIEW_COVERAGE_FOCUS_LABELS = {
  paper_defining: "Main focus",
  major_supporting: "Major supporting topic",
  secondary_context: "Context only",
};
const REVIEW_COVERAGE_FOCUS_ORDER = ["Main focus", "Major supporting topic", "Context only"];
const META_ANALYSIS_DESIGN_LABELS = {
  pairwise_meta_analysis: "Pairwise meta-analysis",
  network_meta_analysis: "Network meta-analysis",
  multilevel_meta_analysis: "Multilevel meta-analysis",
  dose_response_meta_analysis: "Dose-response meta-analysis",
  individual_participant_data_meta_analysis: "Individual-participant-data meta-analysis",
  umbrella_review: "Umbrella review",
  other_quantitative_synthesis: "Other quantitative synthesis",
};
const META_ANALYSIS_DESIGN_ORDER = [
  "Pairwise meta-analysis",
  "Network meta-analysis",
  "Multilevel meta-analysis",
  "Dose-response meta-analysis",
  "Individual-participant-data meta-analysis",
  "Umbrella review",
  "Other quantitative synthesis",
];
const META_ANALYSIS_RESULT_ROLE_LABELS = {
  primary_synthesis: "Primary pooled result",
  secondary_synthesis: "Secondary pooled result",
  subgroup_analysis: "Subgroup analysis",
  sensitivity_analysis: "Sensitivity analysis",
  meta_regression: "Meta-regression",
  dose_response: "Dose-response result",
  network_comparison: "Network comparison",
  network_ranking: "Network ranking",
  publication_bias_analysis: "Publication-bias analysis",
  other: "Other analysis",
};
const META_ANALYSIS_STUDY_COUNT_BINS = [
  { label: "1-5 studies", min: 1, max: 5 },
  { label: "6-10 studies", min: 6, max: 10 },
  { label: "11-20 studies", min: 11, max: 20 },
  { label: "21-50 studies", min: 21, max: 50 },
  { label: "More than 50 studies", min: 51, max: Number.POSITIVE_INFINITY },
];
let claims = [];
const claimStores = {
  normalized: { all: [], bySource: {} },
  extracted: { all: [] },
};
let bibliographyBySource = {
  all: [],
};
let selected = null;
let isolateSelection = false;
let claimLayer = "normalized";
let evidenceView = "primary";
const EVIDENCE_VIEW_KEYS = ["primary", "meta_analyses", "reviews", "secondary"];
const SECONDARY_EVIDENCE_VIEW_KEYS = new Set(["meta_analyses", "reviews", "secondary"]);
const META_ANALYSIS_SOURCE_KEYS = new Set(["meta_analyses"]);
const REVIEW_SOURCE_KEYS = new Set(["reviews", "secondary"]);
const META_ANALYSIS_SOURCE_TYPES = new Set(["meta_analysis", "network_meta_analysis"]);
const REVIEW_SOURCE_TYPES = new Set([
  "review",
  "systematic_review",
  "scoping_review",
  "narrative_review",
  "literature_review",
  "umbrella_review",
]);
let entityViewKey = "condition_indication";
let renderScheduled = false;
let findingSearchTimer = 0;
let findingSearchRenderToken = 0;
let findingSearchWarmupToken = 0;
let findingSearchWarmupState = null;
let centerGraphAfterRender = false;
let centerGraphFrame = 0;
let activeDetailItems = [];
let activeDetailAllAccessItems = [];
let detailGraphFilter = null;
let accessView = "open";
const expandedChartKeys = new Set();
let currentDataLoadToken = 0;
let heroStatsSnapshot = null;
let graphManifestPromise = null;
let graphPayloadConfigPromise = null;
const graphBootstrapPayloadPromises = new Map();
const graphBootstrapClaimsBySource = new Map();
const detailBootstrapPayloadPromises = new Map();
const expandedUseContextClaimsCache = new WeakMap();
let activeClaimsMemo = null;
let entityCategoryCountsMemo = null;
let globalFindingSearchClaimsMemo = null;
let paperContextClaimsByStudyMemo = null;
const graphDomCache = new Map();
const GRAPH_DOM_CACHE_LIMIT = 4;
const overviewDetailCache = new Map();
const OVERVIEW_DETAIL_CACHE_LIMIT = 48;
const overviewDetailPrewarmScheduled = new Set();
const claimArrayIds = new WeakMap();
let nextClaimArrayId = 1;
let deferredSurfaceRenderToken = 0;
let activeOverviewDetailCacheKey = "";
let graphSwapToken = 0;
let retainVisibleBootstrapGraph = false;
let bibliographyPayloadsPromise = null;
let tooltipFrame = 0;
let tooltipMeasureFrame = 0;
let pendingTooltipPoint = null;
let tooltipSize = { width: 240, height: 40 };
const yearFilterState = {};

const COMPOUND_CLASS_LABEL_RE =
  /\b(classic(?:al)? psychedelics?|serotonergic psychedelics?|psychedelic(?: assisted)? (?:medicines?|drugs?|substances?|compounds?|therap(?:y|ies))|psychedelics?|hallucinogenic drugs?|hallucinogens?|arylcyclohexylamines?|synthetic cathinones?|iboga alkaloids?|nbome drugs?|5[- ]*ht2a?r? agonists?)\b/;
const COMPOUND_LIST_LABEL_RE = /\b(?:and|or)\b|[;&]/;
const REFERENCE_COMPOUND_LABEL_RE =
  /\b(5 ht|5 hydroxytryptamine|8 oh dpat|clozapine|d serine|ifenprodil|ketanserin|m100907|memantine|methysergide|mk 801|pcp|phencyclidine|ritanserin|serotonin|way100635)\b/;
const DEFAULT_SAMPLE_SIZE_BINS = [
  { label: "1", min: 1, max: 1 },
  { label: "2-10", min: 2, max: 10 },
  { label: "11-25", min: 11, max: 25 },
  { label: "26-50", min: 26, max: 50 },
  { label: "51-100", min: 51, max: 100 },
  { label: "101-250", min: 101, max: 250 },
  { label: "251-500", min: 251, max: 500 },
  { label: ">500", min: 501, max: Number.POSITIVE_INFINITY },
];
const REAL_WORLD_SAMPLE_SIZE_BINS = [
  { label: "1-100", min: 1, max: 100 },
  { label: "101-500", min: 101, max: 500 },
  { label: "501-1k", min: 501, max: 1000 },
  { label: "1k-5k", min: 1001, max: 5000 },
  { label: "5k-10k", min: 5001, max: 10000 },
  { label: "10k-50k", min: 10001, max: 50000 },
  { label: "50k-250k", min: 50001, max: 250000 },
  { label: "250k-1M", min: 250001, max: 1000000 },
  { label: ">1M", min: 1000001, max: Number.POSITIVE_INFINITY },
];
const GRAPH_LEFT_LABEL_MAX_WIDTH_PX = 210;
const GRAPH_RIGHT_LABEL_MAX_WIDTH_PX = 180;
const GRAPH_RIGHT_LABEL_GUTTER_PX = 24;
const GRAPH_LABEL_MARGIN_BUFFER_PX = 36;
const GRAPH_UNBROKEN_LABEL_WRAP_CHAR_LIMIT = 22;
const GRAPH_BASE_HEIGHT_PX = 820;
const GRAPH_COMPACT_BASE_HEIGHT_PX = 560;
const GRAPH_MIN_NODE_SPACING_PX = 40;
const GRAPH_COMPACT_MIN_NODE_SPACING_PX = 38;
const HIDDEN_MAIN_GRAPH_DOMAINS = new Set(["pharmacokinetics_exposure"]);
const AUTHOR_LABEL_FILTER_PREFIX = "author_label:";

function normalizeValue(value) {
  return (value || "").toString().trim().toLowerCase();
}

function cleanDisplayText(value) {
  return (value ?? "")
    .toString()
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function graphDomainForItem(item) {
  return normalizeValue(item?.kg_domain || item?.domain || item?.finding_type);
}

function isHiddenMainGraphItem(item) {
  const domain = graphDomainForItem(item);
  return domain ? HIDDEN_MAIN_GRAPH_DOMAINS.has(domain) : false;
}

function isMainGraphAdmitted(item) {
  const admission = normalizeValue(item?.graph_admission_status);
  return !admission || admission === "main_graph";
}

function uniqueGraphPropositionClaims(items) {
  const seen = new Set();
  return items.filter((claim) => {
    const propositionId = normalizeValue(claim?.proposition_group_id);
    if (!propositionId) return true;
    if (seen.has(propositionId)) return false;
    seen.add(propositionId);
    return true;
  });
}

function unique(values) {
  return Array.from(new Set(values)).sort();
}

const rawSearchTextCache = new WeakMap();
const rawClaimSearchTextCache = new WeakMap();
const claimSearchTextCache = new WeakMap();
const graphOverviewSubjectsCache = new WeakMap();
const graphUseContextProjectionsCache = new WeakMap();

function normalizeSearchText(value) {
  return normalizeValue(value).replace(/\s+/g, " ").trim();
}

function normalizeFindingSearchText(value) {
  return normalizeSearchText(value)
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[._/|\u2013\u2014-]+/g, " ")
    .replace(/[{}\[\]",:]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function addSearchTextAliases(parts, value) {
  const text = meaningfulText(value);
  if (!text) return;
  parts.push(text);

  const expanded = text
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[._/|\u2013\u2014-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (expanded && normalizeValue(expanded) !== normalizeValue(text)) {
    parts.push(expanded);
  }
}

function collectSearchTextParts(value, parts, seen = new WeakSet()) {
  if (value === null || value === undefined) return;
  if (Array.isArray(value)) {
    value.forEach((item) => collectSearchTextParts(item, parts, seen));
    return;
  }
  if (typeof value === "object") {
    if (seen.has(value)) return;
    seen.add(value);
    Object.values(value).forEach((item) => collectSearchTextParts(item, parts, seen));
    return;
  }
  if (["string", "number", "bigint", "boolean"].includes(typeof value)) {
    addSearchTextAliases(parts, value);
  }
}

function compactSearchTextParts(parts) {
  const seen = new Set();
  return parts.filter((part) => {
    const key = normalizeSearchText(part);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function rawSearchTextForObject(value) {
  if (value && typeof value === "object") {
    const cached = rawSearchTextCache.get(value);
    if (cached !== undefined) return cached;
  }

  const parts = [];
  collectSearchTextParts(value, parts);
  const text = normalizeSearchText(compactSearchTextParts(parts).join(" "));
  if (value && typeof value === "object") {
    rawSearchTextCache.set(value, text);
  }
  return text;
}

function rawSearchTextForClaim(claim) {
  if (!claim || typeof claim !== "object") return rawSearchTextForObject(claim);
  const cached = rawClaimSearchTextCache.get(claim);
  if (cached !== undefined) return cached;

  const parts = [];
  Object.entries(claim).forEach(([field, value]) => {
    if (["graph_overview_subjects_json", "graph_use_context_projections_json"].includes(field)) return;
    if (value === null || value === undefined) return;
    if (["string", "number", "bigint", "boolean"].includes(typeof value)) {
      const text = String(value).trim();
      if (text) parts.push(text);
      return;
    }
    try {
      const serialized = JSON.stringify(value);
      if (serialized) parts.push(serialized);
    } catch (_error) {
      // Ignore non-serializable metadata; derived display labels are indexed below.
    }
  });
  const text = normalizeFindingSearchText(parts.join(" "));
  rawClaimSearchTextCache.set(claim, text);
  return text;
}

function claimDerivedSearchParts(claim) {
  return compactSearchTextParts([
    compoundGraphLabelForClaim(claim),
    ...graphOverviewSubjectsForClaim(claim).map((subject) => subject.label),
    ...graphOverviewSubjectsForClaim(claim).flatMap((subject) => subject.aliases || []),
    ...(Array.isArray(claim?.compound_aliases) ? claim.compound_aliases : []),
    graphRightLabelForClaim(claim),
    claimMainFindingText(claim),
    paperTypeLabel(claim.paper_type),
    publicationTypeFacetLabel(claim),
    studyDesignFacetLabel(claim),
    specificPathwayReadoutLabel(claim),
  ]);
}

function claimSearchHaystack(claim) {
  if (!claim || typeof claim !== "object") {
    return normalizeFindingSearchText([rawSearchTextForObject(claim), ...claimDerivedSearchParts(claim)].join(" "));
  }

  const contextKey = `${claimLayer}|${currentEntityViewKey()}|${evidenceView}`;
  const cachedByContext = claimSearchTextCache.get(claim);
  if (cachedByContext?.has(contextKey)) return cachedByContext.get(contextKey);

  const text = normalizeFindingSearchText([rawSearchTextForClaim(claim), ...claimDerivedSearchParts(claim)].join(" "));
  const nextCache = cachedByContext || new Map();
  nextCache.set(contextKey, text);
  claimSearchTextCache.set(claim, nextCache);
  return text;
}

function graphLabel(value) {
  return meaningfulText(value);
}

function compoundGraphLabel(value) {
  const text = meaningfulText(value);
  if (!text) return "";
  const normalized = normalizeValue(text).replace(/[-_]+/g, " ");
  if (COMPOUND_CLASS_LABEL_RE.test(normalized)) return "";
  if (REFERENCE_COMPOUND_LABEL_RE.test(normalized)) return "";
  if (COMPOUND_LIST_LABEL_RE.test(normalized)) return "";
  return text;
}

function compoundGraphLabelForClaim(claim) {
  const overview = meaningfulText(claim?.graph_overview_subject_label);
  if (overview) return overview;
  return compoundGraphLabel(claim?.compound);
}

function graphOverviewSubjectsForClaim(claim) {
  if (claim && typeof claim === "object") {
    const cached = graphOverviewSubjectsCache.get(claim);
    if (cached) return cached;
  }
  let raw = claim?.graph_overview_subjects_json;
  if (typeof raw === "string" && raw.trim()) {
    try {
      raw = JSON.parse(raw);
    } catch (_error) {
      raw = null;
    }
  }
  if (Array.isArray(raw)) {
    const subjects = raw
      .filter((item) => item && typeof item === "object")
      .map((item) => ({
        label: meaningfulText(item.label),
        kind: meaningfulText(item.kind) || "atomic_compound",
        reason: meaningfulText(item.reason),
        aliases: Array.isArray(item.aliases)
          ? item.aliases.map(meaningfulText).filter(Boolean)
          : [],
      }))
      .filter((item) => item.label);
    if (subjects.length) {
      if (claim && typeof claim === "object") graphOverviewSubjectsCache.set(claim, subjects);
      return subjects;
    }
  }
  const label = compoundGraphLabelForClaim(claim);
  const subjects = label
    ? [{
        label,
        kind: meaningfulText(claim?.graph_overview_subject_kind || claim?.graph_subject_kind) || "atomic_compound",
        reason: meaningfulText(claim?.graph_overview_subject_reason),
        aliases: Array.isArray(claim?.compound_aliases)
          ? claim.compound_aliases.map(meaningfulText).filter(Boolean)
          : [],
      }]
    : [];
  if (claim && typeof claim === "object") graphOverviewSubjectsCache.set(claim, subjects);
  return subjects;
}

function graphUseContextProjectionsForClaim(claim) {
  if (claim && typeof claim === "object") {
    const cached = graphUseContextProjectionsCache.get(claim);
    if (cached) return cached;
  }
  let raw = claim?.graph_use_context_projections_json;
  if (typeof raw === "string" && raw.trim()) {
    try {
      raw = JSON.parse(raw);
    } catch (_error) {
      raw = null;
    }
  }
  const projections = Array.isArray(raw)
    ? raw
        .filter((item) => item && typeof item === "object")
        .map((item) => ({
          projectionType: meaningfulText(item.projection_type) || "use_context",
          subjectLabel: meaningfulText(item.subject_label),
          subjectKind: meaningfulText(item.subject_kind) || "atomic_compound",
          subjectAliases: Array.isArray(item.subject_aliases)
            ? item.subject_aliases.map(meaningfulText).filter(Boolean)
            : [],
          contextLabel: meaningfulText(item.context_label),
          contextKind: meaningfulText(item.context_kind) || "exposure_context",
          contextAliases: Array.isArray(item.context_aliases)
            ? item.context_aliases.map(meaningfulText).filter(Boolean)
            : [],
          contextParentLabel: meaningfulText(item.context_parent_label),
          contextParentKind: meaningfulText(item.context_parent_kind),
          contextParentEntityId: meaningfulText(item.context_parent_entity_id),
          relationType: meaningfulText(item.relation_type) || "reported_in_use_context",
          reason: meaningfulText(item.reason),
        }))
        .filter((item) => item.subjectLabel && item.contextLabel)
    : [];
  if (claim && typeof claim === "object") graphUseContextProjectionsCache.set(claim, projections);
  return projections;
}

function expandClaimsWithUseContextProjections(data) {
  return data.flatMap((claim) => {
    if (meaningfulText(claim?.projection_type) === "use_context") return [claim];
    const projections = graphUseContextProjectionsForClaim(claim);
    return [
      claim,
      ...projections.map((projection) => ({
        ...claim,
        projection_type: "use_context",
        relation_type: projection.relationType,
        kg_relation_type: projection.relationType,
        compound: projection.subjectLabel,
        compound_aliases: projection.subjectAliases,
        graph_subject_label: projection.subjectLabel,
        graph_subject_kind: projection.subjectKind,
        graph_overview_subject_label: projection.subjectLabel,
        graph_overview_subject_kind: projection.subjectKind,
        graph_overview_subject_reason: projection.reason,
        graph_overview_subjects_json: JSON.stringify([
          {
            label: projection.subjectLabel,
            kind: projection.subjectKind,
            reason: projection.reason,
            aliases: projection.subjectAliases,
          },
        ]),
        entity_label: projection.contextLabel,
        graph_entity_label: projection.contextLabel,
        entity_kind: projection.contextKind,
        kg_entity_kind: projection.contextKind,
        graph_parent_label: projection.contextParentLabel,
        graph_parent_kind: projection.contextParentKind,
        graph_parent_entity_id: projection.contextParentEntityId,
        use_context_aliases: projection.contextAliases,
        __use_context_projection: true,
      })),
    ];
  });
}

function expandedClaimsWithUseContextProjections(data) {
  if (!Array.isArray(data)) return [];
  const cached = expandedUseContextClaimsCache.get(data);
  if (cached) return cached;
  const expanded = expandClaimsWithUseContextProjections(data);
  expandedUseContextClaimsCache.set(data, expanded);
  return expanded;
}

function expandClaimsForGraph(data) {
  return data.flatMap((claim) => {
    const subjects = graphOverviewSubjectsForClaim(claim);
    if (subjects.length <= 1) return subjects.length ? [claim] : [];
    return subjects.map((subject) => ({
      ...claim,
      graph_overview_subject_label: subject.label,
      graph_overview_subject_kind: subject.kind,
      graph_overview_subject_reason: subject.reason,
      compound_aliases: subject.aliases || [],
      __graph_subject_projection: true,
    }));
  });
}

const PATHWAY_READOUT_FAMILY_RULES = [
  {
    label: "Gut microbiome",
    pattern: /\b(gut|microbiome|microbiota|microbial|bacteri\w*|fecal|faecal|short chain fatty acids?|scfa)\b/,
  },
  {
    label: "Neuroinflammation & immune signaling",
    pattern:
      /\b(inflamm\w*|cytokine\w*|interleukin\w*|il[- ]?\d+\w*|tnf|nf[- ]?kappa[- ]?b|nf[- ]?kb|cox[- ]?2|prostaglandin\w*|microglia\w*|astrocyt\w*|glial|gfap|iba[- ]?1|complement|crp|hmgb1|tlr[- ]?4|tgf[- ]?beta)\b/,
  },
  {
    label: "Cell injury & survival",
    pattern:
      /\b(cell injury|cell survival|cell viability|cell death|neuronal (?:injury|damage|loss|survival)|neuroprotection|neuroaxonal injury|apoptosis|caspase|necrosis|cytotox\w*|neurotox\w*|toxicity|toxic marker|neurofilament|\bnfl\b|s100b)\b/,
  },
  {
    label: "Cellular stress & mitochondrial function",
    pattern:
      /\b(cellular stress|oxidative stress|reactive oxygen|\bros\b|lipid peroxidation|malondialdehyde|glutathione|\bgsh\b|\bsod\b|catalase|redox|hsp[- ]?70|heat shock|mitochondri\w*|mitophagy|protein folding|endoplasmic reticulum|er stress|dna damage)\b/,
  },
  {
    label: "Neurogenesis",
    pattern: /\b(neurogenesis|doublecortin|\bdcx\b|newborn neurons?|granule cell proliferation)\b/,
  },
  {
    label: "Neuroplasticity",
    pattern:
      /\b(neuroplasticity|bdnf|trkb|trk b|ngf|gdnf|vegf|igf[- ]?1|insulin[- ]like growth factor|neurotroph\w*|growth factor\w*|plasticity|synaptic (?:plasticity|protein|density|remodeling)|synapse (?:formation|density)|dendritic|spine|neurite|synaptogenesis|paired[- ]pulse facilitation|ppf|long[- ]?term potentiation|ltp|long[- ]?term depression|ltd|psd[- ]?95|synaptophysin|arc|sv2a|synaptic vesicle|perineuronal net|gap[- ]?43|growth associated protein|myelin basic protein|myelination)\b/,
  },
  {
    label: "Intracellular signal transduction",
    pattern:
      /\b(intracellular signaling|erk|mapk|mtor|mtorc1|akt|camp|creb|pka|pkc|plc|pi3k|gsk[- ]?3|p70s6k|stat3|jnk|rac1|phosphorylation|phosphorylated|phospho|second messenger\w*|kinase\w*|signal(?:ing|ling)|phosphoinositide)\b/,
  },
  {
    label: "Genetic moderators",
    pattern: /\b(polymorphism\w*|genotype\w*|phenotype interaction|allele\w*|rs\d+)\b/,
  },
  {
    label: "Epigenetic regulation",
    pattern: /\b(epigen\w*|dna methylation|methylation|histone\w*|chromatin|cpg)\b/,
  },
  {
    label: "Gene expression & activity markers",
    pattern:
      /\b(c[- ]?fos|fosb|egr[- ]?1|immediate early|neuronal activation|neural activation|neural activity|neuronal activity|gene expression|transcript\w*|transcriptom\w*|mrna|rna|mirna|microrna)\b/,
  },
  {
    label: "Receptor regulation & trafficking",
    pattern:
      /\b(receptor\w*|5[- ]?ht\d?[a-z]?|sert|slc6a4|\bdat\b|slc6a3|slc6a2|d[1-5][ -]?receptor|ampa|nmda|nmdar|ampar|mglur\d?[a-z]?|mglu\d?|glua\d?|glun\d?|gabr|transport(?:er|ers)|availability|binding potential|densit(?:y|ies)|occupancy|trafficking|surface expression|internalization|uptake site|p[- ]?glycoprotein|abcb1|pmat|slc29a4|vmat\d?)\b/,
  },
  {
    label: "Drug metabolism",
    pattern: /\b(drug metabolism|cyp\d+\w*|cytochrome p450|ugt\d*\w*|monoamine oxidase|mao[- ]?[ab]?|comt|metabolic enzyme\w*|in vitro metabolism)\b/,
  },
  {
    label: "Endocrine response",
    pattern: /\b(endocrine response|cortisol|corticosterone|acth|prolactin|hormone\w*|endocrine|melatonin|oxytocin|vasopressin)\b/,
  },
  {
    label: "Neuronal excitability & synaptic transmission",
    pattern:
      /\b(neuronal excitability|excitability|firing rate|spik(?:e|ing)|calcium imaging|calcium flux|electrophysiolog\w*|oscillation\w*|gamma|theta|field potential\w*|currents?|\bepscs?\b|\bipscs?\b|\bmepscs?\b|\bmipscs?\b|action potential|membrane potential|ion channel modulation|synaptic transmission|neurotransmission)\b/,
  },
  {
    label: "Neurotransmitter release, uptake & turnover",
    pattern:
      /\b(serotonin signaling|serotonin|5[- ]?hydroxytryptamine|5[- ]?hiaa|dopamine signaling|dopamine|\bdopa\b|dopac|\bhva\b|glutamate signaling|glutamate|glutamatergic|gaba signaling|gaba|gabaergic|norepinephrine signaling|norepinephrine|noradrenaline|acetylcholine|monoamine releas\w*|monoamine neurotransmission|modulat\w* monoamine|neurotransmitter\w*|transmitter releas\w*|releas\w*|uptake|reuptake|turnover|metabolite levels?|vesicular monoamine transporter|tph[- ]?2|tryptophan hydroxylase|dopaminergic system marker|choline acetyltransferase|\bchat\b|cholinergic system marker)\b/,
  },
];
const PATHWAY_READOUT_FAMILY_LABELS = new Map(
  PATHWAY_READOUT_FAMILY_RULES.map((item) => [normalizeValue(item.label), item.label]),
);

function usesPathwayReadoutFamilies() {
  return claimLayer === "normalized" && currentEntityViewKey() === "pathway_readout";
}

function usesBrainParentFamilies() {
  return claimLayer === "normalized" && currentEntityViewKey() === "brain_system";
}

function usesInterventionParentFamilies() {
  return claimLayer === "normalized" && currentEntityViewKey() === "intervention_component";
}

function pathwayReadoutMatchText(values) {
  return values
    .map((value) => cleanDisplayText(value))
    .filter(Boolean)
    .join(" ")
    .replace(/[()[\]{}_,;/]+/g, " ")
    .replace(/\s+/g, " ")
    .toLowerCase();
}

function pathwayReadoutFamilyFromText(value) {
  const text = pathwayReadoutMatchText([value]);
  if (!text) return "";
  const exactLabel = PATHWAY_READOUT_FAMILY_LABELS.get(normalizeValue(text));
  if (exactLabel) return exactLabel;
  const rule = PATHWAY_READOUT_FAMILY_RULES.find((item) => item.pattern.test(text));
  return rule?.label || "";
}

const NEUROPLASTICITY_FINDING_THEME_RULES = [
  {
    label: "BDNF–TrkB signaling",
    pattern: /\b(?:m|pro)?bdnf\b|\btrkb\b|\bntrk2\b|\bptrkb\b/,
  },
  {
    label: "Dendritic & spine remodeling",
    pattern: /dendrit|spine|spinogenesis|dendritogenesis|neurite|arbori[sz]|soma size|growth cone|cytoskeletal|f-actin|pruning|mossy fiber sprouting/,
  },
  {
    label: "Synaptic potentiation & depression",
    pattern: /long[- ]?term potentiation|\bltp\b|long[- ]?term depression|\bltd\b|short[- ]?term potentiation|\bstp\b|paired[- ]?pulse|\bppf\b|synaptic potentiation|synaptic depression|fepsp|synaptic efficacy|postsynaptic efficacy|synaptic scaling|ocular dominance|reconsolidation/,
  },
  {
    label: "Synaptic proteins & vesicle remodeling",
    pattern: /psd[- ]?95|dlg4|sv2a|synaptophysin|synapsin|synaptotagmin|synaptophluorin|\bsyt\d|\bsyn1\b|synaptic (?:protein|marker|vesicle|density|remodel|ultrastructure|defect|activity)|synapse (?:formation|density|number)|synaptogenesis|synaptogenic|vesicle recycling|drebrin|homer1|shank3|rims1|narp|neuronal pentraxin|presynaptic|readily releasable pool|synaptozip/,
  },
  {
    label: "Glutamatergic receptor plasticity",
    pattern: /ampa|nmda|glua|glur|gria|glun|nmdar|ampar|glutamate receptor/,
  },
  {
    label: "Activity-dependent plasticity genes",
    pattern: /\barc\b|c[- ]?fos|fosb|egr\d?|zif268|immediate early|cebp|npas4|fra1|neurod1/,
  },
  {
    label: "Other neurotrophic factors",
    pattern: /\bngf\b|\bgdnf\b|\bvegf\w*\b|vascular endothelial growth factor|\bigf[- ]?1\b|insulin[- ]like growth factor|neurotrophin|\bnt[- ]?[34]\b|\bntf3\b|\btrkc?\b|fgf[- ]?2|neurotrophic factor|\bp75\b/,
  },
  {
    label: "Plasticity-related intracellular signaling",
    pattern: /\bmtor|\berk\b|\bcreb\b|\bakt\b|gsk[- ]?3|p70s6k|rps6|mapk|rac1|camkii|pi3k|kinase|phosphoinositide|intracellular signaling/,
  },
  {
    label: "Myelination & extracellular plasticity",
    pattern: /myelin|\bmbp\b|perineuronal|extracellular matrix|chondroitin|mmp[- ]?9|nogo/,
  },
  {
    label: "Neurogenesis & cell proliferation",
    pattern: /cell(?:ular)? proliferation|progenitor proliferation|cell growth|neural progenitor|neural stem|new neurons?|neuronal maturation|\bbrdu\b|\bpcna\b|ki[- ]?67/,
  },
  {
    label: "Structural imaging markers",
    pattern: /cortical thickness|\bvolume\b|dti|diffusivity|white matter|gr[ae]y matter|neuronal volume|neuronal density/,
  },
  {
    label: "Functional synaptic transmission",
    pattern: /epsc|ipsc|fipsp|\blfp\b|field potential|local field|membrane potential|plateau potential|excitability|electrophysiolog|synaptic transmission|synaptic current|synaptic strength|action potential|calcium event|calcium response|calcium transient|gamma oscillation/,
  },
  {
    label: "General neuroplasticity measures",
    pattern: /neuroplastic|synaptic plasticity|plasticity marker|functional cellular plasticity|structural plasticity|plasticity-related|protein synthesis|gap[- ]?43|\bmap2\b|axon development/,
  },
  {
    label: "Interneuron & circuit remodeling",
    pattern: /parvalbumin|\bpv\b|interneuron|fiber density|fiber connectivity|laminar connectivity|engram|projection density|synaptic input/,
  },
  {
    label: "Circuit connectivity & plasticity",
    pattern: /functional connectivity|\bdfc\b|coherence|pathway plasticity|circuit connectivity|connection strength/,
  },
];

function specificPathwayReadoutLabel(claim) {
  const normalizedSubtopic = meaningfulText(claim?.molecular_finding_subtopic);
  if (normalizedSubtopic) return normalizedSubtopic;
  const specific =
    graphLabel(claim?.target) ||
    meaningfulText(claim?.graph_entity_label) ||
    meaningfulText(claim?.raw_entity_label) ||
    meaningfulText(claim?.canonical_entity);
  const text = pathwayReadoutMatchText([specific]);
  if (!text) return "";
  const parent = normalizeValue(
    meaningfulText(claim?.graph_parent_label) ||
      meaningfulText(claim?.molecular_effect_label) ||
      pathwayReadoutFamilyFromText(specific),
  );
  if (parent === normalizeValue("Neuroplasticity")) {
    const theme = NEUROPLASTICITY_FINDING_THEME_RULES.find((item) => item.pattern.test(text));
    if (theme) return theme.label;
  }
  if (/\bbdnf\b/.test(text)) return "BDNF";
  if (/\bpsd[- ]?95\b|\bdlg4\b/.test(text)) return "PSD-95";
  if (/\blong[- ]?term potentiation\b|\bltp\b/.test(text)) return "Long-term potentiation";
  if (/\blong[- ]?term depression\b|\bltd\b/.test(text)) return "Long-term depression";
  if (/\bcorticosterone\b/.test(text)) return "Corticosterone";
  if (/\bcortisol\b/.test(text)) return "Cortisol";
  if (/\bprolactin\b/.test(text)) return "Prolactin";
  if (/\boxytocin\b/.test(text)) return "Oxytocin";
  if (/\bc[- ]?fos\b/.test(text)) return "c-Fos";
  if (/\berk\b/.test(text)) return "ERK";
  if (/\bmtorc?1?\b/.test(text)) return text.includes("mtorc1") ? "mTORC1" : "mTOR";
  if (/\bakt\b/.test(text)) return "Akt";
  if (/\bcreb\b/.test(text)) return "CREB";
  return specific;
}

function pathwayReadoutFamilyForClaim(claim) {
  const nativeLabel = meaningfulText(claim?.graph_parent_label) || meaningfulText(claim?.molecular_effect_label);
  if (nativeLabel) return nativeLabel;
  const specificLabel = specificPathwayReadoutLabel(claim);
  if (!specificLabel) return "";
  const labelText = pathwayReadoutMatchText([
    specificLabel,
    claim?.graph_entity_label,
    claim?.raw_entity_label,
    claim?.canonical_entity,
  ]);
  const exactLabel = PATHWAY_READOUT_FAMILY_LABELS.get(normalizeValue(specificLabel));
  if (exactLabel) return exactLabel;
  const labelRule = PATHWAY_READOUT_FAMILY_RULES.find((item) => item.pattern.test(labelText));
  if (labelRule) return labelRule.label;
  const text = pathwayReadoutMatchText([
    specificLabel,
    claim?.graph_entity_label,
    claim?.raw_entity_label,
    claim?.canonical_entity,
    claim?.assay_type,
    claim?.assay_family,
    claim?.mechanism_type,
    claim?.action_type,
  ]);
  const rule = PATHWAY_READOUT_FAMILY_RULES.find((item) => item.pattern.test(text));
  return rule?.label || "";
}

function graphRightLabelForClaim(claim) {
  const right = graphLabel(graphRightRawLabel(claim));
  if (!right) return "";
  if (usesPathwayReadoutFamilies()) return pathwayReadoutFamilyForClaim(claim);
  if (usesBrainParentFamilies()) return graphLabel(claim?.graph_parent_label) || right;
  if (usesInterventionParentFamilies()) return graphLabel(claim?.graph_parent_label) || right;
  if (currentEntityViewKey() === "condition_indication") {
    return CONDITION_GRAPH_LABEL_OVERRIDES.get(normalizeValue(right)) || right;
  }
  return right;
}

function conditionGraphClarifier(label) {
  if (currentEntityViewKey() !== "condition_indication") return "";
  return CONDITION_GRAPH_CLARIFIERS.get(normalizeValue(label)) || "";
}

function graphRightLabelForContextEntity(entity) {
  const right = graphLabel(entity);
  if (!right) return "";
  if (usesPathwayReadoutFamilies()) return pathwayReadoutFamilyFromText(right);
  return right;
}

function sameGraphLabel(left, right) {
  return normalizeValue(left) === normalizeValue(right);
}

function claimMatchesGraphCompound(claim, compound) {
  return graphOverviewSubjectsForClaim(claim).some((subject) => sameGraphLabel(subject.label, compound));
}

function claimMatchesGraphRight(claim, right) {
  return sameGraphLabel(graphRightLabelForClaim(claim), right);
}

function claimMatchesGraphEdge(claim, compound, right) {
  return claimMatchesGraphCompound(claim, compound) && claimMatchesGraphRight(claim, right);
}

function claimMatchesIsolatedGraphProjection(claim) {
  if (!selected || !isolateSelection) return true;

  const compound = compoundGraphLabelForClaim(claim);
  const right = graphRightLabelForClaim(claim);
  if (selected.type === "edge") {
    return sameGraphLabel(compound, selected.compound) && sameGraphLabel(right, selected.target);
  }
  if (selected.type === "compound") {
    return sameGraphLabel(compound, selected.name);
  }
  if (selected.type === "target") {
    return sameGraphLabel(right, selected.name);
  }
  return true;
}

function graphRightRawLabel(claim) {
  return (
    meaningfulText(claim?.graph_entity_label) ||
    meaningfulText(claim?.entity_label) ||
    meaningfulText(claim?.raw_entity_label) ||
    meaningfulText(claim?.target) ||
    meaningfulText(claim?.disorder)
  );
}

function rightEntityKey() {
  return "graph_entity_label";
}

function currentEntityViewKey() {
  if (ENTITY_CATEGORY_OPTIONS.some((option) => option.key === entityViewKey)) return entityViewKey;
  return ENTITY_CATEGORY_OPTIONS[0]?.key || "";
}

function currentEntityViewOption() {
  const key = currentEntityViewKey();
  return ENTITY_CATEGORY_OPTIONS.find((option) => option.key === key) || null;
}

function detailPanelProfileForKey(key) {
  return {
    ...DETAIL_PANEL_PROFILE_DEFAULT,
    ...(DETAIL_PANEL_PROFILE_BY_VIEW[key] || {}),
  };
}

function currentDetailPanelProfile() {
  if (claimLayer !== "normalized") return detailPanelProfileForKey("clinical_default");
  return detailPanelProfileForKey(currentEntityViewKey() || "clinical_default");
}

function entityKindsForViewOption(option) {
  if (!option) return [];
  return Array.isArray(option.kinds) && option.kinds.length ? option.kinds : [option.key];
}

function entityDomainsForViewOption(option) {
  if (!option) return [];
  return Array.isArray(option.domains) ? option.domains : [];
}

function entityLabelsForViewOption(option) {
  if (!option) return [];
  return Array.isArray(option.labels) ? option.labels : [];
}

function currentEntityViewKinds() {
  return entityKindsForViewOption(currentEntityViewOption());
}

function claimMatchesEntityViewOption(claim, option) {
  const spec = ENTITY_CATEGORY_OPTION_SPECS.get(option?.key);
  if (!spec) return false;
  if (spec.kinds.size && !spec.kinds.has(entityKindForClaim(claim))) return false;
  if (
    spec.domains.size &&
    !spec.domains.has(normalizeValue(claim.kg_domain || claim.domain || claim.finding_type))
  ) {
    return false;
  }
  if (spec.labels.size && !spec.labels.has(normalizeValue(graphRightLabelForClaim(claim)))) return false;
  return true;
}

function rightEntityLabel(plural = true) {
  if (claimLayer !== "normalized") {
    return plural ? "Graph nodes" : "Graph node";
  }
  const option = currentEntityViewOption();
  if (!option) return plural ? "Graph nodes" : "Graph node";
  return plural ? option.label : option.singular;
}

function lowerRightEntityLabel(plural = true) {
  if (claimLayer !== "normalized") {
    return plural ? "graph nodes" : "graph node";
  }
  const option = currentEntityViewOption();
  if (!option) return plural ? "graph nodes" : "graph node";
  return plural ? option.lowerPlural : option.lowerSingular;
}

function entityKindForClaim(claim) {
  return normalizeValue(claim.kg_entity_kind || claim.entity_kind);
}

function claimsForEntityView(baseClaims) {
  if (claimLayer !== "normalized") return baseClaims;
  const option = currentEntityViewOption();
  if (!option) return baseClaims;
  return baseClaims.filter((claim) => claimMatchesEntityViewOption(claim, option));
}

function activeClaimsForMode() {
  const key = `${claimLayer}|${evidenceView}|${currentEntityViewKey()}`;
  if (activeClaimsMemo?.source === claims && activeClaimsMemo.key === key) {
    return activeClaimsMemo.value;
  }
  const value = graphViewClaims(claimsForEntityView(expandedClaimsWithUseContextProjections(claims)));
  activeClaimsMemo = { source: claims, key, value };
  return value;
}

function passesAccessAndYearFilters(claim, yearRange, options = {}) {
  if (!options.ignoreAccess && accessView === "open" && !isOpenAccessClaim(claim)) {
    return false;
  }
  if (yearRange?.constrained) {
    const year = parseYearValue(claim.study_year);
    if (year === null) return false;
    if (year < yearRange.min || year > yearRange.max) return false;
  }
  return true;
}

function activeOutcomeScaleClaims(options = {}) {
  if (evidenceView !== "primary") return [];
  const yearRange = activeYearRange(activeClaimsForMode());
  return graphViewClaims(claims)
    .filter((claim) => isOutcomeScaleClaim(claim))
    .filter((claim) => passesAccessAndYearFilters(claim, yearRange, options));
}

function studyJoinKey(claim) {
  const doi = normalizeDoi(claim.study_doi);
  if (doi) return `doi:${doi}`;
  const openalex = normalizeValue(claim.openalex_id);
  if (openalex) return `openalex:${openalex}`;
  const title = normalizeValue(claim.study_title);
  const year = parseYearValue(claim.study_year);
  if (title || year !== null) return `title:${title}|${year || ""}`;
  return "";
}

function evidenceScopeKey(claim) {
  const study = studyJoinKey(claim);
  const compound = normalizeValue(compoundGraphLabelForClaim(claim));
  if (!study || !compound) return "";
  return `${study}|compound:${compound}`;
}

function outcomeScaleClaimsForChart(items, options = {}) {
  const scaleItems = items.filter((claim) => isOutcomeScaleClaim(claim));
  if (scaleItems.length) return scaleItems;

  const activeScaleClaims = activeOutcomeScaleClaims(options);
  const scopeKeys = new Set(items.map(evidenceScopeKey).filter(Boolean));
  if (!scopeKeys.size) return activeScaleClaims;
  return activeScaleClaims.filter((claim) => scopeKeys.has(evidenceScopeKey(claim)));
}

function setDetailGraphFilter(items) {
  retainVisibleBootstrapGraph = false;
  detailGraphFilter = {
    items: new Set(items),
  };
  refreshMainViews();
}

function clearDetailGraphFilter() {
  detailGraphFilter = null;
}

function claimSourceAccessLevel(claim) {
  const sourceAccess = normalizeValue(claim.source_access_level);
  if (sourceAccess) return sourceAccess;
  const accessLevel = normalizeValue(claim.access_level);
  return accessLevel === "secondary_summary" ? "" : accessLevel;
}

function isOpenAccessClaim(claim) {
  return claimSourceAccessLevel(claim) === "full_text_seen";
}

function applyClaimLayerStore() {
  const store = claimStores[claimLayer] || claimStores.normalized;
  if (claimLayer === "normalized" && store.bySource) {
    claims = store.bySource[currentSourceKey()] || [];
  } else {
    claims = store.all || [];
  }
  activeClaimsMemo = null;
  entityCategoryCountsMemo = null;
  globalFindingSearchClaimsMemo = null;
  paperContextClaimsByStudyMemo = null;
}

function primaryEvidenceClaims(baseClaims) {
  return baseClaims.filter(
    (claim) =>
      (normalizeValue(claim.paper_assessment_route) === "primary_evidence" ||
        (normalizeValue(claim.paper_type) === "primary_results" &&
          normalizeValue(claim.source_type) === "primary_study")) &&
      normalizeValue(claim.access_level) !== "secondary_summary",
  );
}

function isSecondaryLiteratureClaim(claim) {
  const route = normalizeValue(claim.paper_assessment_route);
  const accessLevel = normalizeValue(claim.access_level);
  if (route === "secondary_literature" || accessLevel === "secondary_summary") return true;
  if (route === "primary_evidence") return false;

  const evidenceType = normalizeValue(claim.kg_evidence_type);
  const sourceFamily = normalizeValue(claim.source_family);
  const sourceType = normalizeValue(claim.source_type);
  const paperType = normalizeValue(claim.paper_type);
  return (
    evidenceType === "evidence_synthesis" ||
    sourceFamily === "evidence_synthesis" ||
    ["secondary_evidence", "review", "systematic_review", "scoping_review", "meta_analysis"].includes(sourceType) ||
    ["systematic_review", "scoping_review", "meta_analysis", "review"].includes(paperType) ||
    sourceType.includes("review") ||
    sourceType.includes("meta_analysis") ||
    paperType.includes("review") ||
    paperType.includes("meta_analysis")
  );
}

function sourceTypeToken(value) {
  return normalizeValue(value).replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

function literatureSourceTypeTokens(claim) {
  return [claim.paper_type, claim.source_type, claim.publication_type]
    .map(sourceTypeToken)
    .filter(Boolean);
}

function isMetaAnalysisClaim(claim) {
  return literatureSourceTypeTokens(claim).some(
    (token) => META_ANALYSIS_SOURCE_TYPES.has(token) || token.includes("meta_analysis")
  );
}

function isReviewLiteratureClaim(claim) {
  if (!isSecondaryLiteratureClaim(claim) || isMetaAnalysisClaim(claim)) return false;
  const tokens = literatureSourceTypeTokens(claim);
  if (!tokens.length) return true;
  return tokens.some((token) => REVIEW_SOURCE_TYPES.has(token) || token.includes("review"));
}

function secondaryLiteratureClaims(baseClaims, view = evidenceView) {
  if (META_ANALYSIS_SOURCE_KEYS.has(view)) {
    return baseClaims.filter((claim) => isSecondaryLiteratureClaim(claim) && isMetaAnalysisClaim(claim));
  }
  if (REVIEW_SOURCE_KEYS.has(view)) {
    return baseClaims.filter(isReviewLiteratureClaim);
  }
  return baseClaims.filter(isSecondaryLiteratureClaim);
}

function isSecondaryEvidenceView(view = evidenceView) {
  return SECONDARY_EVIDENCE_VIEW_KEYS.has(view);
}

function isReviewEvidenceView(view = evidenceView) {
  return REVIEW_SOURCE_KEYS.has(view);
}

function recordLabelsForItems(items = []) {
  const metaAnalyses =
    items.length > 0 ? items.every(isMetaAnalysisClaim) : META_ANALYSIS_SOURCE_KEYS.has(evidenceView);
  if (metaAnalyses) {
    return {
      summary: "Meta-analytic records",
      section: "Meta-analyses",
      empty: "No meta-analytic records in this selection.",
      lowerSingular: "meta-analytic record",
      lowerPlural: "meta-analytic records",
    };
  }
  const secondary =
    items.length > 0 ? items.every(isSecondaryLiteratureClaim) : isSecondaryEvidenceView();
  return secondary
    ? {
        summary: "Coverage records",
        section: "Literature coverage",
        empty: "No literature coverage in this selection.",
        lowerSingular: "coverage record",
        lowerPlural: "coverage records",
      }
    : {
        summary: "Findings",
        section: "Findings",
        empty: "No findings in this selection.",
        lowerSingular: "finding",
        lowerPlural: "findings",
      };
}

function graphViewClaims(baseClaims) {
  const visibleClaims = baseClaims.filter((claim) => !isHiddenMainGraphItem(claim));
  if (isSecondaryEvidenceView()) return secondaryLiteratureClaims(visibleClaims, evidenceView);
  return primaryEvidenceClaims(visibleClaims);
}

function parseYearValue(raw) {
  const text = (raw || "").toString().trim();
  if (!text) return null;

  const yearMatch = text.match(/\b(18|19|20)\d{2}\b/);
  if (yearMatch) return Number(yearMatch[0]);

  const numeric = Number(text);
  if (!Number.isFinite(numeric)) return null;
  const year = Math.trunc(numeric);
  if (year < 1800 || year > 3000) return null;
  return year;
}

function yearBoundsFromClaims(data) {
  let minYear = Number.POSITIVE_INFINITY;
  let maxYear = Number.NEGATIVE_INFINITY;

  data.forEach((claim) => {
    const year = parseYearValue(claim.study_year);
    if (year === null) return;
    if (year < minYear) minYear = year;
    if (year > maxYear) maxYear = year;
  });

  if (!Number.isFinite(minYear) || !Number.isFinite(maxYear)) return null;
  return { min: minYear, max: maxYear };
}

function syncYearFilterControls(data, forceReset = false) {
  if (!yearMinFilter || !yearMaxFilter) return;
  const filterKey = currentEntityViewKey();

  const bounds = yearBoundsFromClaims(data);
  if (!bounds) {
    yearMinFilter.value = "";
    yearMaxFilter.value = "";
    yearMinFilter.disabled = true;
    yearMaxFilter.disabled = true;
    yearFilterState[filterKey] = { min: "", max: "" };
    return;
  }

  yearMinFilter.disabled = false;
  yearMaxFilter.disabled = false;
  yearMinFilter.min = String(bounds.min);
  yearMinFilter.max = String(bounds.max);
  yearMaxFilter.min = String(bounds.min);
  yearMaxFilter.max = String(bounds.max);

  const state = yearFilterState[filterKey] || { min: "", max: "" };
  let minYear = parseYearValue(forceReset ? "" : state.min);
  let maxYear = parseYearValue(forceReset ? "" : state.max);

  if (minYear === null) minYear = bounds.min;
  if (maxYear === null) maxYear = bounds.max;

  minYear = clampNumber(minYear, bounds.min, bounds.max);
  maxYear = clampNumber(maxYear, bounds.min, bounds.max);
  if (minYear > maxYear) {
    [minYear, maxYear] = [maxYear, minYear];
  }

  yearFilterState[filterKey] = { min: String(minYear), max: String(maxYear) };
  yearMinFilter.value = String(minYear);
  yearMaxFilter.value = String(maxYear);
}

function activeYearRange(data) {
  if (!yearMinFilter || !yearMaxFilter) {
    return { constrained: false, min: null, max: null };
  }

  const bounds = yearBoundsFromClaims(data);
  if (!bounds) {
    return { constrained: false, min: null, max: null };
  }

  let minYear = parseYearValue(yearMinFilter.value);
  let maxYear = parseYearValue(yearMaxFilter.value);
  if (minYear === null) minYear = bounds.min;
  if (maxYear === null) maxYear = bounds.max;

  minYear = clampNumber(minYear, bounds.min, bounds.max);
  maxYear = clampNumber(maxYear, bounds.min, bounds.max);
  if (minYear > maxYear) {
    [minYear, maxYear] = [maxYear, minYear];
  }

  yearMinFilter.value = String(minYear);
  yearMaxFilter.value = String(maxYear);
  yearFilterState[currentEntityViewKey()] = { min: String(minYear), max: String(maxYear) };

  const constrained = minYear > bounds.min || maxYear < bounds.max;
  return {
    constrained,
    min: minYear,
    max: maxYear,
  };
}

const textMeasureCanvas = document.createElement("canvas");
const textMeasureContext = textMeasureCanvas.getContext("2d");

function clampNumber(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function edgeWidthForCount(count, maxCount) {
  const minWidth = 1.5;
  const maxWidth = 10.5;
  const safeCount = Math.max(1, Number(count) || 1);
  const safeMax = Math.max(1, Number(maxCount) || 1);
  if (safeMax <= 1) return 3.0;
  const normalized = (Math.sqrt(safeCount) - 1) / (Math.sqrt(safeMax) - 1);
  return minWidth + normalized * (maxWidth - minWidth);
}

function interpolateNumber(start, end, ratio) {
  return Math.round(start + (end - start) * ratio);
}

function graphColorForIndex(index, total) {
  if (total <= 1) return GRAPH_COLOR_STOPS[0];
  const clampedIndex = clampNumber(index, 0, total - 1);
  const position = (clampedIndex / (total - 1)) * (GRAPH_COLOR_STOPS.length - 1);
  const lower = Math.floor(position);
  const upper = Math.min(GRAPH_COLOR_STOPS.length - 1, lower + 1);
  const ratio = position - lower;
  const start = GRAPH_COLOR_STOPS[lower];
  const end = GRAPH_COLOR_STOPS[upper];
  return {
    r: interpolateNumber(start.r, end.r, ratio),
    g: interpolateNumber(start.g, end.g, ratio),
    b: interpolateNumber(start.b, end.b, ratio),
  };
}

function rgbString(color) {
  return `rgb(${color.r}, ${color.g}, ${color.b})`;
}

function rgbaString(color, alpha) {
  return `rgba(${color.r}, ${color.g}, ${color.b}, ${alpha})`;
}

function applyGraphNodeColor(node, color) {
  node.style.setProperty("--node-color", rgbString(color));
  node.style.setProperty("--node-fill", rgbaString(color, 0.2));
  node.style.setProperty("--node-glow", rgbaString(color, 0.34));
}

function estimateLabelWidth(label) {
  const text = (label || "").toString();
  return Math.max(40, Math.ceil(text.length * 6.8));
}

function truncateLabel(label, maxChars) {
  const text = (label || "").toString();
  if (text.length <= maxChars) return text;
  if (maxChars <= 1) return text.slice(0, 1);
  return `${text.slice(0, Math.max(1, maxChars - 3))}...`;
}

function measureLabelWidth(text) {
  if (!textMeasureContext) {
    return estimateLabelWidth(text);
  }
  textMeasureContext.font = '16px "IBM Plex Sans", sans-serif';
  return textMeasureContext.measureText((text || "").toString()).width;
}

function fitLabelToWidth(label, maxWidthPx) {
  const text = (label || "").toString();
  if (maxWidthPx <= 18) return "";
  if (measureLabelWidth(text) <= maxWidthPx) return text;

  const suffix = "...";
  const suffixWidth = measureLabelWidth(suffix);
  let low = 0;
  let high = text.length;
  let best = "";

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const candidate = `${text.slice(0, mid)}${suffix}`;
    if (measureLabelWidth(candidate) <= maxWidthPx) {
      best = candidate;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  if (best) return best;
  if (suffixWidth <= maxWidthPx) return suffix;
  return "";
}

function wrapUnbrokenLabelToLines(label, maxWidthPx, maxLines = 2) {
  const text = (label || "").toString();
  if (maxLines < 2 || text.length < 4) return [fitLabelToWidth(text, maxWidthPx)];

  const candidates = [];
  for (let index = 2; index <= text.length - 2; index += 1) {
    const prefix = text.slice(0, index);
    const firstLine = prefix.endsWith("-") ? prefix : `${prefix}-`;
    const secondLine = text.slice(index);
    const firstWidth = measureLabelWidth(firstLine);
    const secondWidth = measureLabelWidth(secondLine);
    if (firstWidth > maxWidthPx || secondWidth > maxWidthPx) continue;
    candidates.push({
      lines: [firstLine, secondLine],
      naturalBreak: prefix.endsWith("-"),
      balance: Math.abs(firstWidth - secondWidth),
    });
  }

  const best = candidates.sort((a, b) => {
    if (a.naturalBreak !== b.naturalBreak) return a.naturalBreak ? -1 : 1;
    return a.balance - b.balance;
  })[0];
  if (best) return best.lines;

  const splitIndex = Math.ceil(text.length / 2);
  return [
    fitLabelToWidth(`${text.slice(0, splitIndex)}-`, maxWidthPx),
    fitLabelToWidth(text.slice(splitIndex), maxWidthPx),
  ];
}

function wrapLabelToLines(label, maxWidthPx, maxLines = 2) {
  const rawText = (label || "").toString().trim();
  if (!rawText) return [""];
  const words = rawText.split(/\s+/).filter(Boolean);
  const forceUnbrokenWrap =
    words.length === 1 && rawText.length > GRAPH_UNBROKEN_LABEL_WRAP_CHAR_LIMIT && maxLines > 1;
  if (!forceUnbrokenWrap && measureLabelWidth(rawText) <= maxWidthPx) return [rawText];

  if (words.length === 1) {
    return wrapUnbrokenLabelToLines(rawText, maxWidthPx, maxLines);
  }

  const lines = [];
  let current = "";

  for (let i = 0; i < words.length; i += 1) {
    const word = words[i];
    const candidate = current ? `${current} ${word}` : word;

    if (measureLabelWidth(candidate) <= maxWidthPx) {
      current = candidate;
      continue;
    }

    if (!current) {
      lines.push(fitLabelToWidth(word, maxWidthPx));
      if (lines.length === maxLines - 1) {
        const remainder = words.slice(i + 1).join(" ");
        if (remainder) lines.push(fitLabelToWidth(remainder, maxWidthPx));
        return lines.slice(0, maxLines);
      }
      current = "";
      continue;
    }

    lines.push(current);
    current = word;

    if (lines.length === maxLines - 1) {
      const remainder = [current, ...words.slice(i + 1)].join(" ");
      lines.push(fitLabelToWidth(remainder, maxWidthPx));
      return lines.slice(0, maxLines);
    }
  }

  if (current) {
    lines.push(fitLabelToWidth(current, maxWidthPx));
  }

  return lines.slice(0, maxLines);
}

function setWrappedSvgLabel(textNode, fullLabel, maxWidthPx, x, centerY, maxLines = 2) {
  const lines = wrapLabelToLines(fullLabel, maxWidthPx, maxLines);
  const lineHeight = 17;
  const startY = centerY - ((lines.length - 1) * lineHeight) / 2 + 4;
  textNode.textContent = "";

  lines.forEach((line, index) => {
    const tspan = document.createElementNS("http://www.w3.org/2000/svg", "tspan");
    tspan.setAttribute("x", x);
    tspan.setAttribute("y", startY + index * lineHeight);
    tspan.textContent = line;
    textNode.appendChild(tspan);
  });
}

function studyId(claim) {
  return claim.study_doi || claim.openalex_id || "unknown";
}

function countStudies(items) {
  return new Set(items.map(studyId)).size;
}

function labelFromSlug(value) {
  return (value || "")
    .toString()
    .split(/[_\s]+/)
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function paperTypeLabel(paperType) {
  const normalized = normalizeValue(paperType);
  const labels = {
    primary_results: "Primary research",
    conference_or_poster_abstract: "Conference/poster",
    journal_article: "Journal article",
    journalarticle: "Journal article",
    preprint: "Preprint",
    case_report: "Case report",
    systematic_review: "Systematic review",
    scoping_review: "Scoping review",
    meta_analysis: "Meta-analysis",
    review: "Review",
  };
  if (labels[normalized]) return labels[normalized];
  if (!normalized) return "Paper type unknown";
  return displayFieldLabel(normalized);
}

const STUDY_DESIGN_CATEGORY_LABELS = {
  rct: "RCT",
  phase_2_rct: "RCT",
  phase_3_rct: "RCT",
  open_label: "Open-label trial",
  single_arm_trial: "Single-arm trial",
  clinical_trial: "Clinical trial",
  human_experimental_study: "Human experimental study",
  experimental_study: "Experimental study",
  observational: "Observational study",
  retrospective: "Retrospective study",
  case_report: "Case report",
  case_series: "Case series",
  qualitative: "Qualitative",
  preclinical_experiment: "Preclinical experiment",
  ex_vivo_experiment: "Ex vivo experiment",
  in_vitro_assay: "In vitro assay",
  binding_assay: "Binding assay",
  functional_assay: "Functional assay",
  computational: "Computational",
  pharmacovigilance: "Pharmacovigilance",
  wastewater_surveillance: "Wastewater surveillance",
  dose_finding: "Dose-finding trial",
  post_hoc: "Secondary analysis",
  follow_up: "Follow-up study",
  review: "Review",
  systematic_review: "Systematic review",
  meta_analysis: "Meta-analysis",
};

function studyDesignLabel(design, claim = null) {
  const raw = meaningfulText(design);
  const normalized = normalizeValue(raw);
  if (
    !normalized ||
    ["unknown", "pending_curation", "not_reported", "not_applicable", "not reported", "not applicable"].includes(
      normalized
    )
  ) {
    return "";
  }

  const context = claim
    ? [
        raw,
        claim.system,
        claim.experimental_system,
        claim.population_model_category,
        claim.population,
        claim.sample_description,
        claim.model_or_system,
        claim.species,
        claim.study_title,
      ]
        .map(cleanDisplayText)
        .filter(Boolean)
        .join(" ")
    : raw;
  const text = normalizeValue(context).replace(/[_/()+–—-]+/g, " ").replace(/\s+/g, " ").trim();
  const explicitClinicalSystem = /\bclinical\b/.test(text);
  const humanPopulation =
    explicitClinicalSystem ||
    /\b(human|humans|participant|participants|volunteer|volunteers|patient|patients|subject|subjects|healthy adult|healthy male|healthy female)\b/.test(
      text
    );
  const preclinicalSystem =
    /\b(preclinical|animal model|animal|mouse|mice|rat|rats|rodent|zebrafish|nonhuman primate|non human primate|marmoset|rhesus|c57bl|sprague dawley|wistar|knockout|genotype|saline controlled|vehicle controlled|in vivo|conditioned place preference|\bcpp\b|head twitch|\bhtr\b|forced swim|tail suspension|open field|fear conditioning|monocular deprivation|chronic mild stress|\bcums\b|self administration|yoked triad|microdialysis|extracellular recording|systemic injection|intraperitoneal|i\.p\.|subcutaneous|s\.c\.)\b/.test(
      text
    ) && !humanPopulation;
  const exVivoSystem = /\b(ex vivo|slice|slices|brain slice|hippocampal slice|patch clamp|whole cell|voltage clamp|current clamp|electrophysiolog)\b/.test(
    text
  );
  const inVitroSystem = /\b(in vitro|cell based|cell-based|cell culture|cultured cells|enzyme assay|pharmacology study|receptor assay|binding assay|radioligand|competition binding|functional assay|uptake assay)\b/.test(
    text
  );

  if (/network meta|meta analysis|meta-analysis/.test(text)) return "Meta-analysis";
  if (/systematic review/.test(text)) return "Systematic review";
  if (/scoping review/.test(text)) return "Scoping review";
  if (/narrative review|literature review|\breview\b/.test(text)) return "Review";
  if (/case report/.test(text)) return "Case report";
  if (/case series/.test(text)) return "Case series";
  if (/qualitative|ethnographic|user generated|reddit|interview/.test(text)) return "Qualitative";
  if (/computational|in silico|modeling|modelling|admet/.test(text)) return "Computational";
  if (exVivoSystem) return "Ex vivo experiment";
  if (/binding|radioligand|competition/.test(text)) return "Binding assay";
  if (/functional receptor|potency|uptake/.test(text)) return "Functional assay";
  if (inVitroSystem) return "In vitro assay";
  if (preclinicalSystem) return "Preclinical experiment";
  if (/dose finding|dose response|dose ranging|rising tolerance|ascending dose|escalating concentration|concentration controlled infusion/.test(text)) {
    return "Dose-finding trial";
  }
  if (/post hoc|post-hoc|secondary analysis|exploratory analysis|correlation analysis|correlational analysis|voxel based analysis|\bspm\b/.test(text)) {
    return "Secondary analysis";
  }
  if (/follow up|followup|follow-up|longitudinal follow/.test(text)) return "Follow-up study";
  if (/wastewater|wbe\b|sewage/.test(text)) return "Wastewater surveillance";
  if (/pharmacovigilance|disproportionality|faers|adverse event reporting/.test(text)) return "Pharmacovigilance";
  if (/case control|cross sectional|observational|naturalistic|survey|internet survey|prospective|real world|real-world|cohort|registry|medical records?|target trial/.test(text)) {
    return "Observational study";
  }
  if (/retrospective|chart review|single arm effectiveness/.test(text)) return "Retrospective study";
  if (/randomi[sz]ed|randomised|double blind|controlled trial|placebo controlled|crossover|cross over/.test(text)) return "RCT";
  if (/open label|open-label/.test(text)) return "Open-label trial";
  if (/single arm|single-arm|uncontrolled pilot|pre post|pre-post|phase\s*1/.test(text)) return "Single-arm trial";
  if (
    humanPopulation &&
    /\b(first in human|first-in-human|first in humans|first-in-humans|pharmacological challenge|drug challenge|pet|positron emission tomography|fmri|mri|mrs|eeg|meg|within subject|within subjects|between subject|between subjects|placebo controlled|controlled experimental|experimental study|imaging study|pilot study|proof of principle|proof-of-principle|interventional study|repeated measures|longitudinal repeated measures)\b/.test(
      text
    )
  ) {
    return "Human experimental study";
  }
  if (/clinical trial/.test(text)) return "Clinical trial";
  if (/pka|pk a|pka determination|chemical/.test(text)) return "Chemical assay";
  if (/experimental|within subject|within subjects|between subject|between subjects|controlled study|controlled experimental|pharmacological challenge|pretreatment|challenge study|imaging study|interventional study|mechanism of action study|positron emission tomography|repeated measures|longitudinal repeated measures/.test(text)) {
    return "Experimental study";
  }
  return "";
}

function studyDesignFacetLabel(claim) {
  const explicit = controlledCategoryLabel(claim.study_design_category, STUDY_DESIGN_CATEGORY_LABELS);
  if (explicit) return explicit;
  const raw = meaningfulText(claim.study_design);
  if (!raw) return "";
  const normalized = normalizeValue(raw).replace(/[_/()-]+/g, " ").replace(/\s+/g, " ").trim();
  if (!normalized || normalized === "secondary literature") return "";
  if (/network meta|meta analysis|meta-analysis/.test(normalized)) return "Meta-analysis";
  if (/systematic review/.test(normalized)) return "Systematic review";
  if (/scoping review/.test(normalized)) return "Scoping review";
  if (/narrative review|literature review|\breview\b/.test(normalized)) return "Review";
  const label = studyDesignLabel(raw, claim);
  if (label) return label;

  const populationModel = populationModelFacetLabel(claim);
  if (populationModel === "Preclinical animals") return "Preclinical experiment";
  if (populationModel === "Cell & tissue studies") return "In vitro assay";
  return displayFieldLabel(raw);
}

const STUDY_DESIGN_ORDER = [
  "RCT",
  "Open-label trial",
  "Single-arm trial",
  "Dose-finding trial",
  "Clinical trial",
  "Human experimental study",
  "Experimental study",
  "Observational study",
  "Retrospective study",
  "Case report",
  "Case series",
  "Qualitative",
  "Preclinical experiment",
  "Ex vivo experiment",
  "In vitro assay",
  "Binding assay",
  "Functional assay",
  "Computational",
  "Pharmacovigilance",
  "Wastewater surveillance",
  "Secondary analysis",
  "Follow-up study",
  "Review",
  "Systematic review",
  "Meta-analysis",
];

function publicationTypeFacetLabel(claim) {
  const paperType = normalizeValue(claim.paper_type);
  if (
    isSecondaryLiteratureClaim(claim) ||
    ["meta_analysis", "systematic_review", "scoping_review", "review"].includes(paperType)
  ) {
    return literatureTypeLabel(claim);
  }

  const raw = meaningfulText(claim.publication_type);
  if (!raw) return "";
  const normalized = normalizeValue(raw).replace(/[_/()-]+/g, " ").replace(/\s+/g, " ").trim();
  if (!normalized) return "";
  if (/network meta|meta analysis|meta-analysis/.test(normalized)) return "Meta-analysis";
  if (/systematic review/.test(normalized)) return "Systematic review";
  if (/\breview\b/.test(normalized)) return "Review";
  if (/case report/.test(normalized)) return "Case report";
  if (/posted content|preprint/.test(normalized)) return "Preprint";
  if (/book chapter/.test(normalized)) return "Book chapter";
  if (/dissertation|thesis/.test(normalized)) return "Dissertation";
  if (/journal article|journalarticle|article/.test(normalized)) return "Journal article";
  return displayFieldLabel(raw);
}

function reviewDesignFacetLabel(claim) {
  return controlledCategoryLabel(claim.review_design_category, REVIEW_DESIGN_LABELS);
}

function reviewContributionFacetLabel(claim) {
  return controlledCategoryLabel(claim.review_contribution_type, REVIEW_CONTRIBUTION_LABELS);
}

function reviewEvidenceStratumFacetLabel(claim) {
  if (["", "not_applicable", "not applicable"].includes(normalizeValue(claim.evidence_level))) return "";
  return controlledCategoryLabel(claim.evidence_level, REVIEW_EVIDENCE_STRATUM_LABELS);
}

function reviewRelationshipTypeFacetLabel(claim) {
  return controlledCategoryLabel(claim.coverage_type, REVIEW_RELATIONSHIP_TYPE_LABELS);
}

function reviewCoverageFocusFacetLabel(claim) {
  return meaningfulText(claim.coverage_focus_normalized) ||
    controlledCategoryLabel(claim.coverage_focus, REVIEW_COVERAGE_FOCUS_LABELS);
}

function openAccessFacetLabel(claim) {
  const isOpen = normalizeValue(claim.open_access_is_oa || claim.unpaywall_is_oa);
  const status = normalizeValue(claim.open_access_status || claim.unpaywall_oa_status);
  if (isOpen === "true" || ["gold", "green", "hybrid", "bronze", "diamond"].includes(status)) return "Open access";
  if (isOpen || status) return "Paywalled";
  return "";
}

function controlledCategoryLabel(value, labels) {
  const key = normalizeValue(value);
  if (!key || key === "not_reported") return "";
  return labels[key] || "";
}

function orderedFacetEntries(entries, preferredLabels = []) {
  if (!preferredLabels.length) return entries;
  const order = new Map(preferredLabels.map((label, index) => [normalizeValue(label), index]));
  return [...entries].sort((a, b) => {
    const aIndex = order.has(normalizeValue(a.label)) ? order.get(normalizeValue(a.label)) : 999;
    const bIndex = order.has(normalizeValue(b.label)) ? order.get(normalizeValue(b.label)) : 999;
    if (aIndex !== bIndex) return aIndex - bIndex;
    const byStudies = b.studies - a.studies;
    if (byStudies !== 0) return byStudies;
    const byClaims = b.claims - a.claims;
    if (byClaims !== 0) return byClaims;
    return a.label.localeCompare(b.label);
  });
}

function entryOrderIndex(entry, order = new Map()) {
  if (!order.size) return 999;
  const key = normalizeValue(entry?.displayLabel || entry?.label || "");
  return order.has(key) ? order.get(key) : 999;
}

function entrySortValue(entry, valueKey = "studies") {
  return (
    Number(entry?.[valueKey]) ||
    Number(entry?.studies) ||
    Number(entry?.count) ||
    Number(entry?.claims) ||
    0
  );
}

function isOtherEntry(entry) {
  const label = normalizeValue(entry?.displayLabel || entry?.label || "");
  return (
    Boolean(entry?.isAggregate) ||
    label === "other" ||
    label === "other findings" ||
    label.startsWith("other/mixed") ||
    label.startsWith("other / mixed") ||
    label.includes("mixed_unclear")
  );
}

function sortEntriesByValue(entries, valueKey = "studies", preferredLabels = []) {
  const order = new Map(preferredLabels.map((label, index) => [normalizeValue(label), index]));
  return [...entries].sort((a, b) => {
    if (isOtherEntry(a) !== isOtherEntry(b)) return isOtherEntry(a) ? 1 : -1;
    const byValue = entrySortValue(b, valueKey) - entrySortValue(a, valueKey);
    if (byValue !== 0) return byValue;
    const byStudies = Number(b.studies || 0) - Number(a.studies || 0);
    if (byStudies !== 0) return byStudies;
    const byClaims = Number((b.claims ?? b.count) || 0) - Number((a.claims ?? a.count) || 0);
    if (byClaims !== 0) return byClaims;
    const byPreferredOrder = entryOrderIndex(a, order) - entryOrderIndex(b, order);
    if (byPreferredOrder !== 0) return byPreferredOrder;
    return String(a.label || "").localeCompare(String(b.label || ""));
  });
}

function trialRegistrationFacetLabel(claim) {
  return meaningfulText(claim.trial_registry_ids) ? "Registered trial" : "Registration not reported";
}

const POPULATION_MODEL_CATEGORY_LABELS = {
  clinical_population: "Human participants",
  healthy_volunteers: "Human participants",
  human_participants: "Human participants",
  community_sample: "Human participants",
  veterans: "Human participants",
  adolescents_youth: "Human participants",
  older_adults: "Human participants",
  mouse_model: "Preclinical animals",
  rat_model: "Preclinical animals",
  animal_model: "Preclinical animals",
  in_vitro_cell_model: "Cell & tissue studies",
  ex_vivo_tissue_model: "Cell & tissue studies",
  computational_model: "In silico studies",
};

function populationModelFacetLabel(claim) {
  const explicit = controlledCategoryLabel(claim.population_model_category, POPULATION_MODEL_CATEGORY_LABELS);
  if (explicit) return explicit;

  const system = normalizeValue(meaningfulText(claim.system));
  const species = normalizeValue(meaningfulText(claim.species));
  const model = normalizeValue(meaningfulText(claim.model_or_system));
  const population = normalizeValue(meaningfulText(claim.population || claim.population_or_subgroup));
  const text = [population, species, model, system].filter(Boolean).join(" ");

  if (!text) return "";

  const hasInSilico = /\b(admet|computational|in silico|docking|modeling|modelling)\b/.test(text);
  const hasCellOrTissue =
    /\b(hek|cho|hela|cell|cells|cell lines?|transfected|culture|cultured|organoid|ex vivo|slice|slices|synaptosome|tissue|brain tissue|cortical tissue)\b/.test(
      text
    ) || system === "in_vitro" || system === "ex_vivo";
  const hasAnimalSignal =
    /\b(rat|rats|rattus|mouse|mice|murine|mus musculus|c57bl\/?6j?|animal|animals|rodent|rodents|preclinical|zebrafish|drosophila|marmoset|marmosets|callithrix|cat|cats|kitten|kittens|feline|nonhuman primate|non-human primate|monkey|monkeys|macaque|macaques|rhesus|baboon|baboons|papio|squirrel monkey|saimiri|rabbit|rabbits|piglet|piglets|porcine|canine|dog|dogs)\b/.test(
      text
    ) || (/\bin vivo\b/.test(text) && !system.includes("clinical"));
  const hasAnimalAndCellMix =
    hasCellOrTissue &&
    /\b(rat|rats|mouse|mice|animal|animals|marmoset|marmosets|cat|cats|monkey|monkeys|baboon|baboons|piglet|piglets)\b[^.;,]*(?:\band\b|&)[^.;,]*\b(cell|cells|culture|cultured|in vitro)\b|\b(cell|cells|culture|cultured|in vitro)\b[^.;,]*(?:\band\b|&)[^.;,]*\b(rat|rats|mouse|mice|animal|animals|marmoset|marmosets|cat|cats|monkey|monkeys|baboon|baboons|piglet|piglets)\b/.test(
      text
    );
  const hasAnimal = hasAnimalSignal && (!hasCellOrTissue || hasAnimalAndCellMix);
  const hasHumanParticipantMarkers = /\b(humans|human(?!\s+(?:cell|cells|cell lines?|tissue|placenta|hepatocytes?|neurons?|neuronal|brain library))|human exposure|volunteers?|participants?|patients?|respondents?|people|users?|consumers?|smokers?|abusers?|veterans?|attendees?|immigrants?|refugees?|clients?|students?|staff|workers?|first responders?|facilitators?|psychiatrists?|drivers?|decedents?|residents?|civilians?|westerners?|members?|cohort|normal volunteers?|clinical controls?)\b/.test(
    text
  );
  const hasHumanDemographicMarkers =
    /\b(adults?|subjects?|individuals?|men|women|males?|females?|man|woman|person|parturients?|case|cases|adolescents?|youth|children|pediatric|paediatric|seniors?|healthy controls?)\b/.test(
      text
    );
  const hasHumanClinicalContext = /\b(clinical|diagnos|disorder|depression|depressive|treatment resistant|treatment-resistant|trd|mdd|ptsd|anxiety|pain|cancer|terminal|life-threatening|substance|dependence|addiction|parkinson|schizophrenia|schizophrenic|bipolar|ocd|migraine|cluster headache|fibromyalgia|restless legs|syndrome|anorexia|eating disorder|body dysmorphic|bdd|borderline|suicid\w*|ceremon(?:y|ies|ial)|retreat|recreational|community|population|poison control|faers|medical records?)\b/.test(
      text
    );
  const hasHuman =
    system === "clinical" ||
    hasHumanParticipantMarkers ||
    (!hasAnimalSignal && !hasCellOrTissue && (hasHumanDemographicMarkers || hasHumanClinicalContext));

  const buckets = [
    hasHuman && !hasCellOrTissue ? "Human participants" : "",
    hasAnimal ? "Preclinical animals" : "",
    hasCellOrTissue ? "Cell & tissue studies" : "",
    hasInSilico && !hasHuman && !hasAnimal && !hasCellOrTissue ? "In silico studies" : "",
  ].filter(Boolean);
  const uniqueBuckets = [...new Set(buckets)];
  if (uniqueBuckets.length === 1) return uniqueBuckets[0];
  return "Other";
}

const POPULATION_MODEL_ORDER = [
  "Human participants",
  "Preclinical animals",
  "Cell & tissue studies",
  "In silico studies",
  "Other",
];

const SAFETY_CONTEXT_ORDER = [
  "Serious/medical intervention",
  "Discontinuation",
  "Acute transient",
  "Persistent/delayed",
  "Preclinical toxicity",
  "Case report/toxicology",
  "Other safety context",
];

function safetyContextFacetLabel(claim) {
  const signalText = [
    claim.entity_label,
    claim.graph_entity_label,
    claim.raw_entity_label,
    claim.normalized_entity_label,
    claim.effect_size,
    claim.support,
  ]
    .map(cleanDisplayText)
    .filter(Boolean)
    .join(" ");
  const evidenceText = [
    claim.study_design,
    claim.publication_type,
    claim.paper_type,
    claim.setting,
    claim.population,
    claim.sample_description,
    claim.model_or_system,
    claim.species,
  ]
    .map(cleanDisplayText)
    .filter(Boolean)
    .join(" ");
  const text = `${signalText} ${evidenceText}`
    .replace(/[_/()+-]+/g, " ")
    .replace(/\s+/g, " ")
    .toLowerCase();

  if (!text.trim()) return "";

  const seriousPattern =
    /\b(serious adverse|serious event|serious safety|sae|medical intervention|hospitali[sz]|emergency department|ed visit|intensive care|critical care|icu|intubat\w*|respiratory support|coma|death|fatal|fatalit\w*|seizure|convulsion|serotonin syndrome|suicid\w*|mania|hypomania|psychosis|psychotic)\b/;
  const discontinuationPattern =
    /\b(discontinuation|discontinue\w*|withdrawal due to|withdrew due to|dropout due to|drop out due to|drop-out due to|treatment cessation|stopped treatment|ceased treatment)\b/;
  const persistentPattern =
    /\b(persistent|persisting|delayed|late onset|late-onset|lasting|long term|long-term|chronic|protracted|flashbacks?|hppd|hallucinogen persisting|sequelae|residual)\b/;
  const preclinicalPattern =
    /\b(preclinical|animal|mouse|mice|rat|rats|rodent|zebrafish|cell culture|in vitro|ex vivo|in vivo|neuronal cells?|cultured cells?|hepatocytes?)\b/;
  const toxicityPattern =
    /\b(neurotox\w*|cytotox\w*|toxicity|toxic|cell viability|cell death|apoptosis|necrosis|lesions?|damage|developmental toxicity|terat\w*|fetal|hepat\w*|liver|renal|kidney|urinary|bladder|cystitis|cardiotox\w*)\b/;
  const toxicologyPattern =
    /\b(case reports?|case series|toxicology|toxicological|toxicosurveillance|poison centers?|poison centres?|poison control|forensic|intoxication|poisoning|overdose|hair analysis|blood analysis|urine analysis|serum concentration|postmortem|post mortem)\b/;
  const acutePattern =
    /\b(acute|transient|short term|short-term|same day|during session|post dose|postdose|immediate|temporary|resolved|nausea|vomiting|headache|anxiety|panic|dissociation|sedation|cognitive or motor|cardiovascular|blood pressure|heart rate|body temperature|sleep disturbance|tolerability|adverse events?)\b/;
  const isPreclinicalToxicity = preclinicalPattern.test(text) && toxicityPattern.test(text);

  if (isPreclinicalToxicity) return "Preclinical toxicity";
  if (seriousPattern.test(text)) return "Serious/medical intervention";
  if (discontinuationPattern.test(text)) return "Discontinuation";
  if (persistentPattern.test(text)) return "Persistent/delayed";
  if (toxicologyPattern.test(text)) return "Case report/toxicology";
  if (acutePattern.test(text)) return "Acute transient";
  return "Other safety context";
}

const DOSE_ROUTE_SESSION_CONTEXT_ORDER = [
  "Intravenous infusion or injection",
  "Intranasal",
  "Subcutaneous or intramuscular injection",
  "Oral or sublingual",
  "Smoked or vaporized",
  "Therapy-assisted session",
  "Clinical administration",
  "Ceremony & retreat",
  "Naturalistic use",
  "Microdosing",
  "Dose-ranging",
  "Repeated dosing",
  "Single-dose session",
  "Preclinical injection",
];
const ADMINISTRATION_ROUTE_LABELS = {
  oral_or_sublingual: "Oral or sublingual",
  intravenous: "Intravenous infusion or injection",
  intranasal: "Intranasal",
  subcutaneous_or_intramuscular: "Subcutaneous or intramuscular injection",
  smoked_or_vaporized: "Smoked or vaporized",
  preclinical_injection: "Preclinical injection",
};
const ADMINISTRATION_ROUTE_DISPLAY_LABELS = {
  oral: "Oral",
  "p.o.": "Oral",
  "per os": "Oral",
  peroral: "Oral",
  ingestion: "Oral",
  "oral (ayahuasca)": "Oral",
  "oral (accidental ingestion)": "Oral",
  "oral (dietary fortification)": "Oral",
  "oral (prolonged-release tablet)": "Oral",
  intragastric: "Oral",
  gavage: "Oral gavage",
  "oral gavage": "Oral gavage",
  "gastric gavage": "Oral gavage",
  sublingual: "Sublingual",
  "sublingual or buccal": "Sublingual or buccal",
  intravenous: "Intravenous",
  infusion: "Intravenous",
  "intravenous infusion": "Intravenous",
  "intravenous bolus": "Intravenous",
  intravenous_infusion: "Intravenous",
  "iv bolus": "Intravenous",
  iv: "Intravenous",
  "i.v.": "Intravenous",
  "intravenous infusion (30 min)": "Intravenous",
  intranasal: "Intranasal",
  insufflation: "Intranasal",
  inhalation: "Inhaled",
  inhaled: "Inhaled",
  smoking: "Smoked",
  vaporization: "Vaporized",
  "dry powder inhalation": "Inhaled",
  subcutaneous: "Subcutaneous",
  "s.c.": "Subcutaneous",
  sc: "Subcutaneous",
  intramuscular: "Intramuscular",
  "intramuscular injection": "Intramuscular",
  "i.m.": "Intramuscular",
  im: "Intramuscular",
  intraperitoneal: "Intraperitoneal",
  "intraperitoneal injection": "Intraperitoneal",
  "i.p.": "Intraperitoneal",
  ip: "Intraperitoneal",
  "intravenous, subcutaneous, intramuscular": "Multiple injection routes",
  "intravenous and subcutaneous": "Multiple injection routes",
  "intranasal, sublingual, oral": "Multiple routes",
  "subcutaneous vs intraperitoneal": "Multiple injection routes",
  "subcutaneous, intramuscular": "Multiple injection routes",
  "s.c. and i.v.": "Multiple injection routes",
  "iv, im, sc": "Multiple injection routes",
  injection: "Injection",
  "unintentional intake": "Unintentional intake",
  immersion: "Immersion",
  "immersion (medium treatment)": "Immersion",
  perfusion: "Perfusion",
  "intracerebral perfusion": "Intracerebral perfusion",
  systemic: "Systemic",
  transdermal: "Transdermal",
  "transdermal (hydrogel-forming microneedle array with lw3 lyophilised reservoir)": "Transdermal",
  "transdermal (hydrogel-forming microneedle array with f3 film reservoir)": "Transdermal",
  "in utero": "In utero",
  "in vitro": "",
  in_vitro: "",
  "in vitro incubation": "",
  "in vitro application (apical)": "",
  "in vitro / ex vivo": "",
  "in vitro (microfluidic droplet)": "",
  "in vitro medium enrichment": "",
  "bath application (in vitro)": "",
  "bath incubation": "",
  extracellular_bath: "",
  "co-administered with voriconazole": "",
  "recreational (various)": "",
  "unknown (intoxication case)": "",
  "in vivo (human)": "",
  "self-reported use": "",
};
const DOSING_SCHEDULE_LABELS = {
  single_dose: "Single-dose session",
  repeated_dosing: "Repeated dosing",
  dose_ranging: "Dose-ranging",
  microdosing: "Microdosing",
  maintenance_or_course: "Repeated dosing",
};
const SESSION_CONTEXT_LABELS = {
  therapy_assisted_session: "Therapy-assisted session",
  ceremony_or_retreat: "Ceremony & retreat",
  clinical_administration: "Clinical administration",
  naturalistic_use: "Naturalistic use",
  preclinical_experiment: "Preclinical injection",
};

function doseRouteSessionFacetLabels(claim) {
  const doseText = [
    claim.dose,
    claim.route,
    claim.route_of_administration,
    claim.intervention_or_exposure,
    claim.exposure_or_intervention,
  ]
    .map(cleanDisplayText)
    .filter(Boolean)
    .join(" ")
    .replace(/[_/()+–—-]+/g, " ")
    .replace(/\s+/g, " ")
    .toLowerCase();
  const metaText = [
    claim.study_design,
    claim.setting,
    claim.sample_description,
    claim.model_or_system,
    claim.species,
    claim.system,
  ]
    .map(cleanDisplayText)
    .filter(Boolean)
    .join(" ")
    .replace(/[_/()+–—-]+/g, " ")
    .replace(/\s+/g, " ")
    .toLowerCase();
  const text = `${doseText} ${metaText}`.trim();
  const microdosingText = [
    doseText,
    metaText,
    claim.study_title,
    claim.support,
    claim.supporting_quote,
  ]
    .map(cleanDisplayText)
    .filter(Boolean)
    .join(" ")
    .replace(/\s+/g, " ")
    .toLowerCase();
  const hasAdministrationSignal =
    Boolean(doseText) ||
    /\b(microdos\w*|assisted therapy|therapy assisted|psychotherapy|ceremon\w*|ritual\w*|retreat|ayahuasca consumption|brew|shamanic)\b/.test(
      microdosingText
    );
  if (!text && !hasAdministrationSignal) return [];

  const labels = [];
  const addLabel = (label) => {
    if (!label) return;
    if (!labels.includes(label)) labels.push(label);
  };
  [
    controlledCategoryLabel(claim.administration_route, ADMINISTRATION_ROUTE_LABELS),
    controlledCategoryLabel(claim.dosing_schedule, DOSING_SCHEDULE_LABELS),
    controlledCategoryLabel(claim.session_context, SESSION_CONTEXT_LABELS),
  ].forEach(addLabel);
  const animalMetaPattern =
    /\b(preclinical|animal|mouse|mice|rats?|rattus|rodent|zebrafish|cell culture|cultured cells?|in vitro|ex vivo)\b/;
  const preclinicalRoutePattern =
    /(?:\bi\.p\.|\bip\b|\bintraperitoneal\b|\bintra (?:bla|vlpag|mpfc|nac|acc|brain|hippocamp\w*|amygdala|pag|pfc|striat\w*|cortex)\b|\bintra(?:bla|vlpag|mpfc|nac|acc)\b)/;
  const injectionPattern = /(?:\bsystemic injection\b|\binjection\b|\bmg kg\b|\bs\.c\.|\bsc\b|\bsubcutaneous\b)/;
  const isPreclinicalInjection =
    preclinicalRoutePattern.test(doseText) || (animalMetaPattern.test(metaText) && injectionPattern.test(doseText));

  if (/\bmicrodos\w*\b/.test(microdosingText)) addLabel("Microdosing");
  if (
    /\b(assisted therapy|therapy assisted|psychotherapy|pap\b|psychological support|therapeutic support|recovery based therapy|timber psychotherapy|integrative therapy|preparatory|integration sessions?)\b/.test(
      microdosingText
    )
  ) {
    addLabel("Therapy-assisted session");
  }
  if (/\b(ceremon\w*|ritual\w*|retreat|naturalistic setting|ayahuasca consumption|brew|shamanic)\b/.test(microdosingText)) {
    addLabel("Ceremony & retreat");
  }
  if (/\b(intranasal|nasal spray|nasal|spravato|in esketamine)\b/.test(doseText)) addLabel("Intranasal");
  if (/(?:\bintravenous\b|\biv\b|\bi\.v\.|\binfusion\b|\binfused\b|\bbolus injection\b)/.test(doseText)) {
    addLabel("Intravenous infusion or injection");
  }
  if (/(?:\bintramuscular\b|\bim\b|\bi\.m\.|\bsubcutaneous\b|\bs\.c\.|\bsc\b)/.test(doseText) && !isPreclinicalInjection) {
    addLabel("Subcutaneous or intramuscular injection");
  }
  if (/\b(smoked|smoking|vaporized|vaporised|vaporization|vaporisation|inhaled|inhalation|freebase)\b/.test(doseText)) {
    addLabel("Smoked or vaporized");
  }
  if (/(?:\boral\b|\borally\b|\bp\.o\.|\bpo\b|\bcapsule\b|\btablet\b|\bingestion\b|\bingested\b|\bsublingual\b|\blingual\b|\bbuccal\b|\bbrew\b|\bdrink\b|\btea\b|\bayahuasca\b)/.test(doseText)) {
    addLabel("Oral or sublingual");
  }
  if (isPreclinicalInjection) addLabel("Preclinical injection");
  if (
    /\b(dose finding|dose response|dose ranging|dose escalation|titrat\w*|flexible dose|variable dose|various doses|escalating|multiple dose levels?|\d+(?:\.\d+)?\s*(?:,|and)\s*\d+(?:\.\d+)?\s*(?:,|and)\s*\d+(?:\.\d+)?)\b/.test(
      text
    )
  ) {
    addLabel("Dose-ranging");
  }

  const repeatedPattern =
    /\b(repeated|multiple|maintenance|course|series|weekly|twice weekly|twice-weekly|daily|consecutive days|over \d+ (?:days?|weeks?|months?)|\d+ sessions?|\d+ infusions?|\d+ doses?|redosing|booster|supplemental dose|2 3 times a week|separated by|once weekly|three months treatment)\b/;
  const singlePattern = /\b(single|one time|one-time|first administration|single dose|single administration|single session)\b/;
  const isRepeated = repeatedPattern.test(text);
  if (isRepeated) addLabel("Repeated dosing");
  if (singlePattern.test(text) && !isRepeated) addLabel("Single-dose session");
  return labels;
}

function normalizedAdministrationRouteText(value) {
  const route = meaningfulText(value);
  if (!route) return "";
  const routeKey = normalizeValue(route);
  if (routeKey === "other") return "";
  if (Object.prototype.hasOwnProperty.call(ADMINISTRATION_ROUTE_DISPLAY_LABELS, routeKey)) {
    return ADMINISTRATION_ROUTE_DISPLAY_LABELS[routeKey];
  }
  return controlledCategoryLabel(route, ADMINISTRATION_ROUTE_LABELS) || displayFieldLabel(route, "");
}

function administrationRouteText(rawRoute, normalizedRoute) {
  const raw = meaningfulText(rawRoute);
  if (raw) return normalizedAdministrationRouteText(raw);
  return normalizedAdministrationRouteText(normalizedRoute);
}

function routeAddsAdministrationDetail(doseText, routeText) {
  const route = normalizeValue(routeText);
  if (!route || route === "other") return false;
  if (!doseText) return true;

  const dose = normalizeValue(doseText).replace(/[_/()+–—-]+/g, " ").replace(/\s+/g, " ").trim();
  if (!dose) return true;

  const routePatterns = {
    oral_or_sublingual:
      /\b(oral|orally|p\.?o\.?|per os|peroral|ingest\w*|drinking|drink|brew|ayahuasca|capsule|tablet|sublingual|buccal|gavage)\b/,
    oral: /\b(oral|orally|p\.?o\.?|per os|peroral|ingest\w*|capsule|tablet|gavage)\b/,
    sublingual: /\b(sublingual|buccal)\b/,
    intravenous: /\b(intravenous|i\.?v\.?|iv\b|infusion|infused|bolus)\b/,
    intravenous_infusion: /\b(intravenous|i\.?v\.?|iv\b|infusion|infused)\b/,
    intranasal: /\b(intranasal|nasal|spray|spravato)\b/,
    smoked_or_vaporized: /\b(smok\w*|vapori[sz]\w*|vapouri[sz]\w*|inhal\w*)\b/,
    inhalation: /\b(inhal\w*|smok\w*|vapori[sz]\w*|vapouri[sz]\w*)\b/,
    inhaled: /\b(inhal\w*|smok\w*|vapori[sz]\w*|vapouri[sz]\w*)\b/,
    subcutaneous_or_intramuscular: /\b(subcutaneous|s\.?c\.?|sc\b|intramuscular|i\.?m\.?|im\b|injection|injected)\b/,
    subcutaneous: /\b(subcutaneous|s\.?c\.?|sc\b|injection|injected)\b/,
    intramuscular: /\b(intramuscular|i\.?m\.?|im\b|injection|injected)\b/,
    intraperitoneal: /\b(intraperitoneal|i\.?p\.?|ip\b|injection|injected)\b/,
    preclinical_injection:
      /\b(injection|injected|intraperitoneal|i\.?p\.?|ip\b|subcutaneous|s\.?c\.?|sc\b|intramuscular|i\.?m\.?|im\b|systemic|mg\s*kg|mg\/kg)\b/,
    "p.o.": /\b(oral|orally|p\.?o\.?|per os|peroral|ingest\w*|capsule|tablet|gavage)\b/,
    "per os": /\b(oral|orally|p\.?o\.?|per os|peroral|ingest\w*|capsule|tablet|gavage)\b/,
    "i.v.": /\b(intravenous|i\.?v\.?|iv\b|infusion|infused|bolus)\b/,
    "s.c.": /\b(subcutaneous|s\.?c\.?|sc\b|injection|injected)\b/,
    "i.m.": /\b(intramuscular|i\.?m\.?|im\b|injection|injected)\b/,
    "i.p.": /\b(intraperitoneal|i\.?p\.?|ip\b|injection|injected)\b/,
    ip: /\b(intraperitoneal|i\.?p\.?|ip\b|injection|injected)\b/,
    im: /\b(intramuscular|i\.?m\.?|im\b|injection|injected)\b/,
    sc: /\b(subcutaneous|s\.?c\.?|sc\b|injection|injected)\b/,
  };

  const pattern = routePatterns[route];
  if (pattern && pattern.test(dose)) return false;

  const routeWords = route
    .replace(/_/g, " ")
    .split(/\s+/)
    .filter((word) => word.length > 3);
  if (routeWords.length && routeWords.every((word) => dose.includes(word))) return false;

  return true;
}

function administrationSummaryText(claim) {
  const dose = meaningfulText(claim.dose);
  const rawRoute = meaningfulText(claim.route || claim.route_of_administration);
  const normalizedRoute = meaningfulText(claim.administration_route);
  const route = rawRoute || normalizedRoute;
  const routeLabel = administrationRouteText(rawRoute, normalizedRoute);
  if (!dose) return routeLabel;
  if (!routeLabel || !routeAddsAdministrationDetail(dose, route)) return dose;
  return compactUniqueParts([dose, routeLabel]).join(" • ");
}

const PUBLIC_HEALTH_TOPIC_ORDER = [
  "Population use & trends",
  "Use patterns & practices",
  "Motivations & intentions",
  "Predictors & correlates",
  "Perceived benefits & harms",
  "Health & functioning outcomes",
  "Problematic use & dependence",
  "Acute harms & healthcare use",
  "Treatment effectiveness & care outcomes",
  "Harm reduction practices",
  "Drug composition & adulteration",
  "Availability & market trends",
  "Access & equity",
  "Implementation & acceptability",
  "Economic & resource impacts",
  "Ethics & governance",
  "Commercialization & public communication",
  "Environmental sustainability",
  "Policy & legal outcomes",
  "Research landscape",
  "Other real-world topics",
];
const PUBLIC_HEALTH_CONTEXT_ORDER = [
  "Microdosing",
  "Recreational/nightlife",
  "Self-treatment",
  "Ceremonial/retreat",
  "Polysubstance",
  "Clinical care",
];
const PUBLIC_HEALTH_DATA_SOURCE_ORDER = [
  "Survey",
  "Poison center/toxicology",
  "Wastewater",
  "Drug checking",
  "Administrative/registry",
  "Qualitative/interview",
  "Observational cohort",
  "Other/unclear source",
];
const PUBLIC_HEALTH_DATA_SOURCE_LABELS = {
  survey: "Survey",
  poison_center_toxicology: "Poison center/toxicology",
  wastewater: "Wastewater",
  drug_checking: "Drug checking",
  administrative_registry: "Administrative/registry",
  qualitative_interview: "Qualitative/interview",
  observational_cohort: "Observational cohort",
  other_or_unclear: "Other/unclear source",
};

function publicHealthTopicFacetLabel(claim) {
  const graphLabel = meaningfulText(claim.public_health_graph_label || claim.graph_entity_label || claim.entity_label);
  const canonical = PUBLIC_HEALTH_TOPIC_ORDER.find(
    (label) => normalizeValue(label) === normalizeValue(graphLabel)
  );
  return canonical || "Other real-world topics";
}

function publicHealthUseContextFacetLabels(claim) {
  return cleanDisplayText(claim.real_world_use_context)
    .split(/\s*[;|]\s*/)
    .map((value) => PUBLIC_HEALTH_CONTEXT_ORDER.find((label) => normalizeValue(label) === normalizeValue(value)))
    .filter(Boolean);
}

function publicHealthDataSourceFacetLabel(claim) {
  return controlledCategoryLabel(claim.data_source_type, PUBLIC_HEALTH_DATA_SOURCE_LABELS) || "Other/unclear source";
}

const MECHANISTIC_ASSAY_FAMILY_ORDER = [
  "Binding assays",
  "Receptor activity",
  "fMRI",
  "PET",
  "SPECT",
  "MRI",
  "MRS",
  "EEG",
  "MEG",
  "LFP",
  "Electrophysiology",
  "Calcium imaging",
  "Fiber photometry",
  "Behavioral assays",
  "Protein assays",
  "Proteomics",
  "Neurochemical assays",
  "Gene expression assays",
  "Immunoassays",
  "Histology",
  "Computational modeling",
  "Uptake assays",
  "Signaling assays",
  "Enzyme assays",
  "Other methods",
];
const ASSAY_FAMILY_DISPLAY_LABELS = {
  "binding / affinity": "Binding assays",
  "functional activity": "Receptor activity",
  "imaging / connectivity": "Other methods",
  electrophysiology: "Electrophysiology",
  "behavioral assay": "Behavioral assays",
  "protein expression / proteomics": "Protein assays",
  "neurochemical levels": "Neurochemical assays",
  "gene expression": "Gene expression assays",
  "immunoassay / histology": "Immunoassays",
  "computational / in silico": "Computational modeling",
  "transporter / uptake": "Uptake assays",
  "signaling / phosphorylation": "Signaling assays",
  "enzyme / metabolism": "Enzyme assays",
  "other / mixed method": "Other methods",
};
for (const label of MECHANISTIC_ASSAY_FAMILY_ORDER) {
  ASSAY_FAMILY_DISPLAY_LABELS[normalizeValue(label)] = label;
}
const BRAIN_MEASURE_ORDER = [
  "Functional connectivity",
  "BOLD response",
  "Cerebral blood flow",
  "Glucose metabolism",
  "Receptor occupancy",
  "Neurochemical levels",
  "Oscillatory power",
  "MMN",
  "P300",
  "ERP",
  "Calcium activity",
  "c-Fos",
  "Brain structure",
  "White matter integrity",
];
const MECHANISTIC_RELATIONSHIP_TYPE_ORDER = [
  "Binding/affinity",
  "Agonism/antagonism",
  "Transporter uptake",
  "Metabolism/transport",
  "Neurotransmitter release",
  "Expression change",
  "Connectivity change",
  "Plasticity marker",
  "Toxicity marker",
  "Other/mixed relationship",
];
const MECHANISTIC_RELATIONSHIP_TYPE_LABELS = {
  binding_affinity: "Binding/affinity",
  agonism_antagonism: "Agonism/antagonism",
  transporter_uptake: "Transporter uptake",
  neurotransmitter_release: "Neurotransmitter release",
  expression_change: "Expression change",
  connectivity_change: "Connectivity change",
  plasticity_marker: "Plasticity marker",
  toxicity_marker: "Toxicity marker",
  metabolism_or_transport: "Metabolism/transport",
  other_or_mixed: "Other/mixed relationship",
};

function mechanisticRelationshipTypeFacetLabel(claim) {
  const explicit = controlledCategoryLabel(claim.mechanistic_relationship_type, MECHANISTIC_RELATIONSHIP_TYPE_LABELS);
  if (explicit) return explicit;

  const text = [
    claim.action_type,
    claim.affinity_type,
    claim.assay_family_normalized,
    claim.assay_type,
    claim.entity_label,
    claim.graph_entity_label,
    claim.effect_size,
    claim.support,
  ]
    .map(cleanDisplayText)
    .filter(Boolean)
    .join(" ")
    .replace(/[_/()+-]+/g, " ")
    .replace(/\s+/g, " ")
    .toLowerCase();

  if (!text) return "";
  if (
    /\b(neurotox\w*|cytotox\w*|toxicity|toxic|cell viability|cell death|apoptosis|necrosis|oxidative stress|ros|dna damage|mitochondri\w*|er stress|endoplasmic reticulum stress|lesions?|neurodegener\w*)\b/.test(
      text
    )
  ) {
    return "Toxicity marker";
  }
  if (
    /\b(functional connectivity|connectivity|network|default mode|dmn|salience network|frontoparietal|functional coupling|bold|fmri|phmri|brain activation|regional activity|cerebral blood flow)\b/.test(
      text
    )
  ) {
    return "Connectivity change";
  }
  if (
    /\b(plasticity|synaptic|synapse|dendritic|spines?|neurogenesis|long term potentiation|ltp|long term depression|ltd|bdnf|trkb|trk b|arc|c fos|cfos|egr|psd 95|synaptophysin|neurite|structural remodeling)\b/.test(
      text
    )
  ) {
    return "Plasticity marker";
  }
  if (
    /\b(transporter|transport|uptake|reuptake|efflux|sert|dat|net|slc6a|substrate|serotonin transport|dopamine transport)\b/.test(text)
  ) {
    return "Transporter uptake";
  }
  if (
    /\b(release|releaser|extracellular|microdialysis|neurochemical levels?|serotonin levels?|dopamine levels?|noradrenaline levels?|norepinephrine levels?|5 ht levels?|5 hiaa|glutamate levels?|gaba levels?|monoamine levels?|depletion)\b/.test(
      text
    )
  ) {
    return "Neurotransmitter release";
  }
  if (
    /\b(agonis\w*|antagonis\w*|partial agonist|inverse agonist|modulat\w*|allosteric|inhibitor|inhibition|activation|efficacy|potency|functional activity|g protein|beta arrestin|arrestin|camp|ip1|calcium mobilization)\b/.test(
      text
    )
  ) {
    return "Agonism/antagonism";
  }
  if (
    /\b(binding|affinity|radioligand|ki\b|kd\b|ic50|ec50|pki|occupancy|receptor density|bp nd|displacement|competition binding)\b/.test(
      text
    )
  ) {
    return "Binding/affinity";
  }
  if (
    /\b(expression|mrna|rna|transcript|gene expression|protein expression|protein levels?|western blot|immunoblot|qpcr|qrt pcr|rt pcr|proteomics?|elisa|immunohistochemistry|histology)\b/.test(
      text
    )
  ) {
    return "Expression change";
  }
  return "Other/mixed relationship";
}

function assayFamilyText(claim) {
  return [
    claim.assay_family,
    claim.assay_type,
    claim.modality,
    claim.modality_or_evidence_type,
    claim.model_or_method,
  ]
    .map(meaningfulText)
    .filter(Boolean)
    .join(" ")
    .replace(/&/g, " and ")
    .replace(/[_/()+-]+/g, " ")
    .replace(/\s+/g, " ")
    .toLowerCase()
    .trim();
}

function assayFamilyFromText(text) {
  if (!text || ["none", "not applicable", "not_applicable", "not reported", "not_reported", "unknown", "uncertain"].includes(text)) {
    return "";
  }

  if (/\b(fmri|rs\s?fmri|phmri|functional mri|functional magnetic resonance|asl|pcasl|arterial spin labell?ing)\b/.test(text)) {
    return "fMRI";
  }
  if (/\b(spect|single photon)\b/.test(text)) {
    return "SPECT";
  }
  if (
    /\b(pet|fdg|h2?15o|15o labeled|18f|radiotracer|positron emission)\b/.test(
      text
    )
  ) {
    return "PET";
  }
  if (/\b(meg|magnetoencephalograph\w*)\b/.test(text)) {
    return "MEG";
  }
  if (
    /\b(eeg|erp|event related|event related potential|p300|p3a|p3b|mmn|mismatch negativity|eloreta|sloreta|ecog|ieeg)\b/.test(
      text
    )
  ) {
    return "EEG";
  }
  if (/\b(lfp|local field potential)\b/.test(text)) {
    return "LFP";
  }
  if (
    /\b(electrophysiolog\w*|patch clamp|voltage clamp|current clamp|field potential|field potentials|f?epsp|ipsc|epsc|tevc|whole cell|extracellular recording|single unit|multiunit|mua|synaptic transmission|synaptic plasticity|theta burst)\b/.test(
      text
    )
  ) {
    return "Electrophysiology";
  }
  if (/\b(fiber photometry|fibre photometry|photometry)\b/.test(text)) {
    return "Fiber photometry";
  }
  if (
    /\b(calcium imaging|gcamp|two photon|2 photon|light sheet|functional ultrasound|fusi)\b/.test(
      text
    )
  ) {
    return "Calcium imaging";
  }
  if (/\b(mrs|magnetic resonance spectroscopy|nmr spectroscopy|spectroscopy|7t mrs)\b/.test(text)) {
    return "MRS";
  }
  if (/\b(structural mri|dti|diffusion tensor|diffusion mri|mri|7t mri)\b/.test(text)) {
    return "MRI";
  }
  if (
    /\b(radioligand|binding|affinity|competition|displacement|scatchard|autoradiograph|autoradiography|receptor density|receptor occupancy|binding potential|bpnd|bp nd)\b/.test(
      text
    )
  ) {
    return "Binding assays";
  }
  if (
    /\b(behavior\w*|behaviour\w*|behavioral pharmacology|drug discrimination|head twitch|htr|locomot|nocicept|antinocicept|forced swim|tail suspension|open field|prepulse)\b/.test(
      text
    )
  ) {
    return "Behavioral assays";
  }
  if (
    /\b(microdialysis|hplc|uhplc|neurotransmitter|monoamine|dopamine|serotonin|norepinephrine|noradrenaline|glutamate|gaba|release|metabolite|tissue content|neurochemical assay|electrochemical|voltammetry|fscv)\b/.test(
      text
    )
  ) {
    return "Neurochemical assays";
  }
  if (/\b(transport|transporter|uptake|reuptake|efflux|sert|dat|net)\b/.test(text)) return "Uptake assays";
  if (
    /\b(gene expression|mrna|qpcr|qrt pcr|rt qpcr|rna seq|rnaseq|transcript|microarray|in situ hybridization|in situ hybridisation|genomic|immediate early gene|fos|arc|rnascope|snrna seq|single nucleus rna)\b/.test(
      text
    )
  ) {
    return "Gene expression assays";
  }
  if (/\b(phosphoproteomics?|proteomics?|proteomic|mass spectrometry)\b/.test(text)) {
    return "Proteomics";
  }
  if (
    /\b(western|immunoblot|protein expression|protein levels?|protein quantification|measurement of protein|synaptic expression|brain derived neurotrophic factor|bdnf|psd)\b/.test(
      text
    )
  ) {
    return "Protein assays";
  }
  if (/\b(histolog|staining|confocal|microscopy|golgi|stereology)\b/.test(text)) {
    return "Histology";
  }
  if (
    /\b(elisa|immunoassay|immunohistochemistry|immunocytochemistry|immunofluorescence|cytometric bead array|flow cytometry|cytokine production|cytokine assay|milliplex|chemokine)\b/.test(
      text
    )
  ) {
    return "Immunoassays";
  }
  if (/\b(expression assay|expression measurement|expression in|expression analysis|detection of expression|gene expression|mrna|transcript)\b/.test(text)) {
    return "Gene expression assays";
  }
  if (/\b(phosphorylation|phospho|phosphoinositide|kinase|mtor|erk|akt|camp pathway|signal transduction|pathway activation)\b/.test(text)) {
    return "Signaling assays";
  }
  if (/\b(biochemical activity assay|proteasome|trypsin like|chymotrypsin like|ups activity)\b/.test(text)) {
    return "Enzyme assays";
  }
  if (
    /\b(functional|activity|activation|agonis\w*|antagonis\w*|pharmacological antagonism|pharmacological blockade|pharmacological classification|g protein|beta arrestin|arrestin|bret|camp|ip1|inositol|calcium|recruitment|potency|efficacy|modulation)\b/.test(
      text
    )
  ) {
    return "Receptor activity";
  }
  if (/\b(computational|in silico|docking|modeling|modelling|prediction|admet|simulation|molecular dynamics)\b/.test(text)) {
    return "Computational modeling";
  }
  if (/\b(enzyme|enzymatic|metabolic|metabolism|esterase|pka|pk a|chemical assay|pka determination)\b/.test(text)) {
    return "Enzyme assays";
  }
  return "Other methods";
}

function mechanisticAssayFamilyFacetLabel(claim) {
  const refined = assayFamilyFromText(assayFamilyText(claim));
  if (refined && refined !== "Other methods") return refined;
  const normalized = meaningfulText(claim.assay_family_normalized || claim.normalized_assay_family);
  if (normalized) return ASSAY_FAMILY_DISPLAY_LABELS[normalizeValue(normalized)] || normalized;
  return refined;
}

function assayFamilySummaryLabel(claim) {
  const refined = assayFamilyFromText(assayFamilyText(claim));
  if (refined && refined !== "Other methods") return refined;
  const normalized = meaningfulText(claim.assay_family_normalized || claim.normalized_assay_family);
  if (normalized) return ASSAY_FAMILY_DISPLAY_LABELS[normalizeValue(normalized)] || normalized;
  const raw = meaningfulText(claim.assay_family);
  return raw ? ASSAY_FAMILY_DISPLAY_LABELS[normalizeValue(raw)] || cleanDisplayText(raw) : "";
}

function brainMeasureText(claim) {
  return [
    claim.readout,
    claim.readout_or_measure,
    claim.outcome_measure,
    claim.modality,
    claim.modality_or_evidence_type,
    claim.assay_type,
    claim.assay_family,
    claim.assay_family_normalized,
    claim.graph_entity_label,
    claim.entity_label,
    claim.effect_size,
    claim.support,
  ]
    .map(meaningfulText)
    .filter(Boolean)
    .join(" ")
    .replace(/&/g, " and ")
    .replace(/[_/()+-]+/g, " ")
    .replace(/\s+/g, " ")
    .toLowerCase()
    .trim();
}

function brainMeasureFacetLabels(claim) {
  const domain = graphDomainForItem(claim);
  if (domain && domain !== "brain_system") return [];

  const text = brainMeasureText(claim);
  if (!text) return [];

  const labels = [];
  const add = (condition, label) => {
    if (condition) labels.push(label);
  };
  const hasMRS = /\b(mrs|magnetic resonance spectroscopy|nmr spectroscopy|1h mrs|7t mrs)\b/.test(text);

  add(/\b(functional connectivity|resting state connectivity|resting state|connectivity|coupling|connectome|within network|between network|network integration|network segregation)\b/.test(text), "Functional connectivity");
  add(/\b(bold|blood oxygen level dependent)\b/.test(text), "BOLD response");
  add(/\b(cbf|rcbf|cerebral blood flow|regional cerebral blood flow|blood perfusion|perfusion|arterial spin labell?ing|asl|pcasl|hmpao)\b/.test(text), "Cerebral blood flow");
  add(/\b(fdg|glucose metabolism|metabolic activity|2dg|2 dg|deoxyglucose|deoxy glucose)\b/.test(text), "Glucose metabolism");
  add(/\b(receptor occupancy|binding potential|bpnd|bp nd|receptor availability|receptor binding|receptor density)\b/.test(text), "Receptor occupancy");
  add(hasMRS && /\b(mrs|magnetic resonance spectroscopy|glutamate|glutamine|glx|gaba|n acetyl|nacetyl|naa)\b/.test(text), "Neurochemical levels");
  add(/\b(oscillation\w*|oscillatory|power density|band power|gamma|alpha|theta|delta|beta|desynchroni[sz]ation|current source density|source density)\b/.test(text), "Oscillatory power");
  add(/\b(mmn|mismatch negativity)\b/.test(text), "MMN");
  add(/\b(p300|p3a|p3b|novelty p3)\b/.test(text), "P300");
  add(/\b(erp|event related potential|event related potentials)\b/.test(text), "ERP");
  add(/\b(calcium|ca2|ca 2|gcamp|fiber photometry|fibre photometry|photometry)\b/.test(text), "Calcium activity");
  add(/\b(c fos|cfos|fos\b|egr\b|arc\b|immediate early gene)\b/.test(text), "c-Fos");
  add(
    !hasMRS &&
      /\b(neurochemical|neurotransmitter|microdialysis|monoamine|dopamine|serotonin|glutamate|gaba|norepinephrine|noradrenaline|5 ht|5 hiaa)\b/.test(
        text
      ),
    "Neurochemical levels"
  );
  add(/\b(dti|diffusion tensor|fractional anisotropy|white matter|tract integrity)\b/.test(text), "White matter integrity");
  add(/\b(structural mri|cortical thickness|gray matter|grey matter|brain volume|regional volume|morphometry)\b/.test(text), "Brain structure");

  return compactUniqueParts(labels);
}

const CLINICAL_COMPARATOR_ORDER = [
  "Placebo",
  "Active placebo",
  "Baseline",
  "No comparator",
  "Dose or route comparison",
  "Active treatment",
  "Standard care",
  "Observational controls",
  "Not reported",
  "Not applicable",
  "Other",
];

const CLINICAL_COMPARATOR_LABEL_ALIASES = {
  "placebo vehicle": "Placebo",
  "baseline pre post": "Baseline",
  "no comparator single arm": "No comparator",
  "dose route comparison": "Dose or route comparison",
  "active treatment comparator": "Active treatment",
  "treatment as usual standard care": "Standard care",
  "observational matched controls": "Observational controls",
  "comparator not reported": "Not reported",
  "other mixed comparator": "Other",
};

function clinicalComparatorDisplayLabel(value) {
  const label = meaningfulText(value);
  if (!label) return "";
  const key = normalizeValue(label)
    .replace(/[_/()+-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return CLINICAL_COMPARATOR_LABEL_ALIASES[key] || label;
}

const CLINICAL_FOLLOW_UP_WINDOW_ORDER = [
  "Acute / same day",
  "Early follow-up (1-7 days)",
  "Short follow-up (1-4 weeks)",
  "Medium follow-up (1-3 months)",
  "Long follow-up (4-12 months)",
  "Extended follow-up (>12 months)",
  "During treatment",
  "Treatment endpoint",
  "Baseline / pre-treatment",
  "Retrospective / lifetime",
  "Follow-up not reported",
  "Not applicable",
  "Other / mixed follow-up",
];

const FOLLOW_UP_NUMBER_WORDS = {
  one: "1",
  first: "1",
  two: "2",
  second: "2",
  three: "3",
  third: "3",
  four: "4",
  fourth: "4",
  five: "5",
  fifth: "5",
  six: "6",
  sixth: "6",
  seven: "7",
  seventh: "7",
  eight: "8",
  ninth: "9",
  nine: "9",
  ten: "10",
  eleven: "11",
  twelve: "12",
  twelfth: "12",
};

function clinicalComparatorFacetLabel(claim) {
  const normalized = meaningfulText(claim.comparator_normalized || claim.normalized_comparator);
  if (normalized) return clinicalComparatorDisplayLabel(normalized);

  const text = normalizeValue(meaningfulText(claim.comparator))
    .replace(/[_/()+-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!text || ["not_reported", "not reported", "unknown", "uncertain"].includes(text)) return "Not reported";
  if (["not_applicable", "not applicable", "n/a", "na"].includes(text)) return "Not applicable";
  if (/\b(no comparator|no control|no comparative|uncontrolled|single arm|no treatment|no ketamine|no analgesia|none)\b/.test(text)) {
    return "No comparator";
  }
  if (
    /\b(baseline|pre treatment|pre intervention|pre retreat|pre dose|previous treatments?|retrospective pre|pre operation|preoperation|pretreatment|before infusion|preinfusion|before psychedelic|intake|time period before|pre study|study exit|after first pap|post dosing|before the second infusion)\b/.test(
      text
    )
  ) {
    return "Baseline";
  }
  if (/\b(midazolam|niacin|diphenhydramine|active placebo|psychoactive placebo|1 mg psilocybin|5 mg psilocybin|low dose)\b/.test(text)) {
    return "Active placebo";
  }
  if (/\b(placebo|saline|normal saline|isotonic saline|0\.9% saline|vehicle|lactose|nitrogen|water)\b/.test(text)) {
    return "Placebo";
  }
  if (
    /\b(\d+(?:\.\d+)?\s*(?:mg|mcg|ug|μg|µg|g|ml)|dose|doses?)\b/.test(text) &&
    /\b(ket|ketamine|esketamine|psilocybin|comp360|mdma|dmt|lsd|nitrous|cannabidiol)\b/.test(text)
  ) {
    return "Dose or route comparison";
  }
  if (
    /\b(iv ketamine|intravenous ketamine|intranasal esketamine|in esketamine|esketamine alone|ketamine alone|ketamine therapy|es ketamine therapy|r s ketamine|oral ketamine|subcutaneous versus intranasal|four infusion|injectable r s ketamine|racemic ketamine|s ketamine|r ketamine|esk in|mdma alone|psilocybin alone|intrathecal psilocin|ketamine only|2r 6r hnk|ibogaine|other routes of administration)\b/.test(
      text
    )
  ) {
    return "Dose or route comparison";
  }
  if (
    /\b(treatment as usual|treatment-as-usual|standard care|standard of care|usual care|conventional|community of practice|mbsr|routine treatment|rwt|standard postpartum care|linkage alone|outpatient medication management|waitlist)\b/.test(
      text
    )
  ) {
    return "Standard care";
  }
  if (
    /\b(healthy comparison|comparison group|matched controls?|control group|controls?|non users?|non mdma users?|non responders?|nonresponders?|younger patients?|unmedicated|anxious mdd|no change|non aia|patients without|patients with no|non early improvers?|no lifetime|subjects who had no|normative sample|reference category|men|women|unipolar depression|low trauma|trauma type absent|without pain|other chronic pain|mild pain|non pain|healthy individuals?|males?|female|socially isolated|with low insomnia|non obese|without comorbid|do not suffer|without diabetes|without hyperlipidemia|did not have|did not receive|responders?|abstinent users?|neuroleptic free|adults without)\b/.test(
      text
    )
  ) {
    return "Observational controls";
  }
  if (
    /\b(ect|electro convulsive|electroconvulsive|escitalopram|antidepressants?|ssri|oad|quetiapine|lithium|rtms|methadone|ketorolac|fentanyl|sufentanil|remifentanil|acetaminophen|hydromorphone|morphine|opioid|analgesic|propofol|etomidate|bupivacaine|dexamethasone|gabapentin|tramadol|diclofenac|metoclopramide|psychotherapy|therapy alone|thiopental|methohexital|dexmedetomidine|lorazepam|prochlorperazine|aminophylline|lidocaine|anaesthetic|benzodiazepines?|medication management|valproate|lexapro|ketamine|esketamine|mdma|lsd|ayahuasca|dextromethorphan|pethidine|imipramine|duloxetine|sertraline|magnesium sulfate|budesonide|methamphetamine|opiates|psychostimulants|antidepressivos)\b/.test(
      text
    )
  ) {
    return "Active treatment";
  }
  return "Other";
}

function followUpTextFromClaim(claim) {
  return normalizeValue([claim.follow_up_duration, claim.timepoint].map(meaningfulText).filter(Boolean).join(" "))
    .replace(
      /\b(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth|seven|seventh|eight|ninth|nine|ten|eleven|twelve|twelfth)\b/g,
      (match) => FOLLOW_UP_NUMBER_WORDS[match] || match
    )
    .replace(/\b(\d+)(?:st|nd|rd|th)\b/g, "$1")
    .replace(/[_/()+-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function followUpWindowFromDays(days) {
  if (days <= 1) return "Acute / same day";
  if (days <= 7) return "Early follow-up (1-7 days)";
  if (days <= 31) return "Short follow-up (1-4 weeks)";
  if (days <= 93) return "Medium follow-up (1-3 months)";
  if (days <= 366) return "Long follow-up (4-12 months)";
  return "Extended follow-up (>12 months)";
}

function followUpDurationDays(text) {
  const durations = [];
  const patterns = [
    [/\b(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|min)\b/g, 1 / 1440],
    [/\b(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|hr|h)\b/g, 1 / 24],
    [/\b(?:days?|d|pod)\s*(\d+(?:\.\d+)?)\b|\b(\d+(?:\.\d+)?)\s*(?:days?|d)\b/g, 1],
    [/\b(?:week|weeks|wk|w)\s*(\d+(?:\.\d+)?)\b|\b(\d+(?:\.\d+)?)\s*(?:weeks?|wks?|wk)\b/g, 7],
    [/\b(?:month|mo)\s*(\d+(?:\.\d+)?)\b|\b(\d+(?:\.\d+)?)\s*(?:months?|mos?|mo)\b/g, 30.44],
    [/\b(?:year|yr)\s*(\d+(?:\.\d+)?)\b|\b(\d+(?:\.\d+)?)\s*(?:years?|yrs?|yr)\b/g, 365.25],
  ];
  patterns.forEach(([pattern, multiplier]) => {
    let match = pattern.exec(text);
    while (match) {
      const value = match.slice(1).find(Boolean);
      const number = Number(value);
      if (Number.isFinite(number)) durations.push(number * multiplier);
      match = pattern.exec(text);
    }
  });
  [
    [/\bdays?\s+([0-9][0-9.,\sandto-]+)/g, 1],
    [/\bweeks?\s+([0-9][0-9.,\sandto-]+)/g, 7],
    [/\bmonths?\s+([0-9][0-9.,\sandto-]+)/g, 30.44],
    [/\byears?\s+([0-9][0-9.,\sandto-]+)/g, 365.25],
  ].forEach(([pattern, multiplier]) => {
    let match = pattern.exec(text);
    while (match) {
      const values = match[1].match(/\d+(?:\.\d+)?/g) || [];
      values.forEach((value) => {
        const number = Number(value);
        if (Number.isFinite(number)) durations.push(number * multiplier);
      });
      match = pattern.exec(text);
    }
  });
  return durations.length ? Math.max(...durations) : null;
}

function clinicalFollowUpWindowFacetLabel(claim) {
  const normalized = meaningfulText(claim.follow_up_window_normalized || claim.normalized_follow_up_window);
  if (normalized) return normalized;

  const text = followUpTextFromClaim(claim);
  if (!text || ["not_reported", "not reported", "unknown", "uncertain"].includes(text)) return "Follow-up not reported";
  if (["not_applicable", "not applicable", "n/a", "na"].includes(text)) return "Not applicable";
  if (/\b(lifetime|past year|past month|past week|past use|prior use|history of|retrospective|previous year)\b/.test(text)) {
    return "Retrospective / lifetime";
  }
  if (/\b(baseline|pre treatment|pretreatment|pre dose|pre infusion|preinfusion|before treatment|before infusion|from baseline)\b/.test(text)) {
    return "Baseline / pre-treatment";
  }
  if (
    /\b(during|throughout|within|across)\b.*\b(treatment|infusions?|sessions?|administration|study|course|maintenance|series)\b|\bover (?:the )?(?:treatment )?course\b|\bover the course of\b.*\b(treatment|infusions?|sessions?|study|course)\b|\b(intraoperative|intra operative|within session)\b/.test(
      text
    )
  ) {
    return "During treatment";
  }
  if (
    /\b(end of treatment|end treatment|treatment endpoint|endpoint|post treatment|after treatment|posttreatment|post therapy|after therapy|study exit|on discharge|after induction|conclusion of|pre to post intervention|after .* treatment|after completed treatment|after completion of|after the treatment series|after induction phase|after (?:the )?\d+(?:st|nd|rd|th)?.*(?:infusions?|treatments?|sessions?)|after the \d+(?:st|nd|rd|th)? (?:infusions?|treatments?|sessions?)|by the \d+(?:st|nd|rd|th)? (?:treatment|session)|treatment \d+|final .*(?:infusion|treatment|session)|following (?:each |\d+ )?infusions?|after repeated infusions?)\b/.test(
      text
    )
  ) {
    const days = followUpDurationDays(text);
    return days === null ? "Treatment endpoint" : followUpWindowFromDays(days);
  }
  if (
    /\b(acut\w*|rapid\w*|immediate|same day|postoperative\w*|post operative\w*|postinfusion|post infusion|post administration|post dosing|after dosing|after first infusion|after each infusion)\b/.test(
      text
    )
  ) {
    const days = followUpDurationDays(text);
    return days === null ? "Acute / same day" : followUpWindowFromDays(days);
  }
  const days = followUpDurationDays(text);
  if (days !== null) return followUpWindowFromDays(days);
  if (/\b(short term)\b/.test(text)) return "Short follow-up (1-4 weeks)";
  return "Other / mixed follow-up";
}

function accessLevelLabel(accessLevel) {
  const normalized = normalizeValue(accessLevel);
  const labels = {
    full_text_seen: "full text",
    abstract_only: "abstract only",
  };
  return labels[normalized] || labelFromSlug(normalized);
}

function classToken(value) {
  return normalizeValue(value).replace(/_/g, "-").replace(/[^a-z0-9-]+/g, "-") || "unknown";
}

function chipHtml(kind, label, token = label) {
  if (!label) return "";
  return `<span class="badge ${kind} ${classToken(token)}">${label}</span>`;
}

function paperTypeBadgeHtml(paperType) {
  const normalized = normalizeValue(paperType) || "other";
  return chipHtml("paper-type", paperTypeLabel(normalized), normalized);
}

function literatureTypeLabel(claim) {
  const text = [
    claim.paper_type,
    claim.source_type,
    claim.study_design,
    claim.publication_type,
    claim.study_title,
  ]
    .map(normalizeValue)
    .filter(Boolean)
    .join(" ")
    .replace(/[-_]+/g, " ");

  if (/\b(network\s+)?meta\s+analysis\b/.test(text)) return "Meta-analysis";
  if (/\bsystematic\s+review\b/.test(text)) return "Systematic review";
  if (/\bscoping\s+review\b/.test(text)) return "Scoping review";
  if (/\breview\b/.test(text) || normalizeValue(claim.source_family) === "evidence_synthesis") return "Review";
  return paperTypeLabel(claim.paper_type || claim.source_type || "review");
}

function literatureTypeBadgeHtml(claim) {
  const label = literatureTypeLabel(claim);
  return chipHtml("literature-type", label, label);
}

function studyDesignBadgeHtml(design, claim = null) {
  const label = studyDesignLabel(design, claim);
  return chipHtml("study-design", label, label);
}

function accessLevelBadgeHtml(accessLevel) {
  const normalized = normalizeValue(accessLevel);
  if (normalized !== "abstract_only") return "";
  return chipHtml("access-level", accessLevelLabel(accessLevel), accessLevel);
}

function systemBadgeHtml(system) {
  const normalized = normalizeValue(system);
  if (!normalized || ["unknown", "not_applicable", "not applicable"].includes(normalized)) return "";
  return chipHtml("system", displayFieldLabel(normalized), normalized);
}

function supportLabel(support) {
  const normalized = normalizeValue(support);
  if (normalized === "not_supported") return "not supported";
  if (!normalized) return "support unknown";
  return labelFromSlug(normalized);
}

function supportBadgeHtml(support) {
  return chipHtml("support", supportLabel(support), support || "unknown");
}

function claimBadgeHtml(claim) {
  const secondary = isSecondaryLiteratureClaim(claim);
  return [
    secondary ? "" : systemBadgeHtml(claim.system),
    secondary ? "" : studyDesignBadgeHtml(claim.study_design, claim),
    accessLevelBadgeHtml(claim.access_level),
    secondary ? literatureTypeBadgeHtml(claim) : "",
  ]
    .filter(Boolean)
    .join("");
}

function stashActiveOverviewDetail() {
  const cacheKey = activeOverviewDetailCacheKey;
  activeOverviewDetailCacheKey = "";
  if (!cacheKey) return;
  const entry = overviewDetailCache.get(cacheKey);
  if (!entry || !detailBody.childNodes.length) return;
  entry.container.replaceChildren(...Array.from(detailBody.childNodes));
}

function setDetailHeader(title) {
  stashActiveOverviewDetail();
  detailTitle.textContent = title;
}

function clearDetailForTransition() {
  stashActiveOverviewDetail();
  activeDetailItems = [];
  activeDetailAllAccessItems = [];
  detailTitle.textContent = "";
  detailBody.replaceChildren();
}

function clearSelectedStyles() {
  graphEl.querySelectorAll(".selected").forEach((el) => el.classList.remove("selected"));
}

function clearSelection() {
  selected = null;
  isolateSelection = false;
  detailGraphFilter = null;
  clearSelectedStyles();
  clearDetailForTransition();
  hideTooltip();
  scheduleRender();
}

function showTooltip(content, event) {
  if (tooltip.innerHTML !== content) {
    tooltip.innerHTML = content;
    scheduleTooltipMeasure();
  }
  tooltip.style.opacity = "1";
  tooltip.style.transform = "translateY(0)";
  positionTooltipNow(event.clientX, event.clientY);
}

function moveTooltip(event) {
  positionTooltip(event);
}

function hideTooltip() {
  pendingTooltipPoint = null;
  if (tooltipFrame) {
    window.cancelAnimationFrame(tooltipFrame);
    tooltipFrame = 0;
  }
  if (tooltipMeasureFrame) {
    window.cancelAnimationFrame(tooltipMeasureFrame);
    tooltipMeasureFrame = 0;
  }
  tooltip.style.opacity = "0";
  tooltip.style.transform = "translateY(6px)";
}

function showTooltipForElement(content, element) {
  const rect = element.getBoundingClientRect();
  showTooltip(content, {
    clientX: rect.left + rect.width / 2,
    clientY: rect.top + rect.height / 2,
  });
}

function positionTooltip(event) {
  pendingTooltipPoint = { clientX: event.clientX, clientY: event.clientY };
  if (tooltipFrame) return;
  tooltipFrame = window.requestAnimationFrame(() => {
    tooltipFrame = 0;
    if (!pendingTooltipPoint) return;
    positionTooltipNow(pendingTooltipPoint.clientX, pendingTooltipPoint.clientY);
  });
}

function scheduleTooltipMeasure() {
  if (tooltipMeasureFrame) return;
  tooltipMeasureFrame = window.requestAnimationFrame(() => {
    tooltipMeasureFrame = 0;
    const rect = tooltip.getBoundingClientRect();
    tooltipSize = {
      width: rect.width || tooltipSize.width,
      height: rect.height || tooltipSize.height,
    };
    if (pendingTooltipPoint) {
      positionTooltipNow(pendingTooltipPoint.clientX, pendingTooltipPoint.clientY);
    }
  });
}

function positionTooltipNow(clientX, clientY) {
  const gap = 25;
  const padding = 8;
  const maxLeft = Math.max(padding, window.innerWidth - tooltipSize.width - padding);
  const maxTop = Math.max(padding, window.innerHeight - tooltipSize.height - padding);
  const centeredLeft = clientX - tooltipSize.width / 2;
  const desiredTop = clientY + gap;

  tooltip.style.left = `${clampNumber(centeredLeft, padding, maxLeft)}px`;
  tooltip.style.top = `${clampNumber(desiredTop, padding, maxTop)}px`;
}

function openAlexUrl(openalexId) {
  const id = (openalexId || "").toString().trim();
  if (!id) return "";
  if (id.startsWith("http://") || id.startsWith("https://")) return id;
  return `https://openalex.org/${id}`;
}

function doiUrl(doiValue) {
  const raw = (doiValue || "").toString().trim();
  if (!raw) return "";
  if (raw.startsWith("http://") || raw.startsWith("https://")) return raw;
  const normalized = raw.replace(/^doi:\s*/i, "").replace(/^https?:\/\/doi\.org\//i, "");
  if (!normalized) return "";
  return `https://doi.org/${encodeURI(normalized)}`;
}

function normalizeAuthors(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => (item || "").toString().trim())
      .filter(Boolean)
      .join(", ");
  }
  if (value && typeof value === "object") {
    const candidates = [];
    if (value.name) candidates.push(value.name);
    if (value.display_name) candidates.push(value.display_name);
    if (value.author) candidates.push(value.author);
    if (candidates.length) {
      return candidates
        .map((item) => (item || "").toString().trim())
        .filter(Boolean)
        .join(", ");
    }
  }
  return (value || "").toString().trim();
}

function claimAuthors(claim) {
  const authorFields = [
    claim.authors,
    claim.author_list,
    claim.study_authors,
    claim.author,
    claim.first_author,
  ];
  for (const field of authorFields) {
    const normalized = normalizeAuthors(field);
    if (normalized) return normalized;
  }
  return "";
}

function authorDisplayName(author) {
  if (!author || typeof author !== "object") return "";
  return meaningfulAuthorName(
    author.name || author.display_name || author.displayName || author.author || author.label || ""
  );
}

function authorStableId(author) {
  if (!author || typeof author !== "object") return "";
  return cleanDisplayText(
    author.id || author.author_id || author.authorId || author.openalex_author_id || author.openalexAuthorId || author.orcid || ""
  );
}

function meaningfulAuthorName(name) {
  const text = cleanDisplayText(name);
  const normalized = normalizeValue(text);
  if (!normalized || ["unknown", "unknown author", "unknown authors"].includes(normalized)) return "";
  return text;
}

function authorRoleIdentity(claim, role) {
  const value = claim?.[`${role}_author`];
  if (value && typeof value === "object") {
    const name = authorDisplayName(value);
    const id = authorStableId(value);
    if (name || id) {
      return {
        id: id || name,
        name: name || id,
        source: "structured",
      };
    }
  }

  const authors = splitAuthorNames(claimAuthors(claim)).map(meaningfulAuthorName).filter(Boolean);
  const name = role === "last" ? authors[authors.length - 1] || "" : authors[0] || "";
  return name ? { id: name, name, source: "fallback" } : { id: "", name: "", source: "none" };
}

function firstAuthorName(claim) {
  return authorRoleIdentity(claim, "first").name;
}

function lastAuthorName(claim) {
  return authorRoleIdentity(claim, "last").name;
}

function authorRoleLabelKey(label) {
  const text = cleanDisplayText(label);
  if (!text) return "";
  const normalized = typeof text.normalize === "function" ? text.normalize("NFKC") : text;
  return normalized
    .replace(/[\u2010-\u2015\u2212]/g, "-")
    .replace(/[\u2018-\u201B]/g, "'")
    .replace(/[\u201C-\u201F]/g, '"')
    .replace(/\s+/g, " ")
    .trim()
    .toLocaleLowerCase("en-US");
}

function buildAuthorRoleAliasMap(items) {
  const candidates = new Map();
  items.forEach((claim) => {
    ["first", "last"].forEach((role) => {
      const author = authorRoleIdentity(claim, role);
      const labelKey = authorRoleLabelKey(author.name);
      if (!labelKey || author.source !== "structured") return;
      const valueKey = normalizeValue(author.id);
      if (!valueKey || valueKey === labelKey) return;
      const entry = candidates.get(labelKey) || { ids: new Set() };
      entry.ids.add(author.id);
      candidates.set(labelKey, entry);
    });
  });

  const aliases = new Map();
  candidates.forEach((entry, labelKey) => {
    if (entry.ids.size === 1) {
      aliases.set(labelKey, Array.from(entry.ids)[0]);
    }
  });
  return aliases;
}

function authorRoleLabelFilterValue(label) {
  const labelKey = authorRoleLabelKey(label);
  return labelKey ? `${AUTHOR_LABEL_FILTER_PREFIX}${labelKey}` : "";
}

function authorRoleLabelFromFilterValue(value) {
  const text = (value || "").toString();
  return text.startsWith(AUTHOR_LABEL_FILTER_PREFIX) ? text.slice(AUTHOR_LABEL_FILTER_PREFIX.length) : "";
}

function authorFacetValueForRole(claim, role, aliases = null) {
  const author = authorRoleIdentity(claim, role);
  if (!author.name) return "";
  const labelKey = authorRoleLabelKey(author.name);
  let value = author.id || author.name;
  if (labelKey && aliases?.has(labelKey) && author.source !== "structured") {
    value = aliases.get(labelKey);
  }
  return { value, label: author.name };
}

function firstAuthorFacetValue(claim, aliases = null) {
  return authorFacetValueForRole(claim, "first", aliases);
}

function lastAuthorFacetValue(claim, aliases = null) {
  return authorFacetValueForRole(claim, "last", aliases);
}

function normalizeDoi(value) {
  return (value || "")
    .toString()
    .trim()
    .replace(/^doi:\s*/i, "")
    .replace(/^https?:\/\/doi\.org\//i, "");
}

function splitAuthorNames(value) {
  const text = cleanDisplayText(normalizeAuthors(value));
  if (!text) return [];
  if (text.includes(";")) {
    return text
      .split(";")
      .map((part) => cleanDisplayText(part))
      .filter(Boolean);
  }
  return [text];
}

function citationAuthors(value) {
  const authors = splitAuthorNames(value);
  if (!authors.length) return "Unknown authors";
  if (authors.length <= 3) return authors.join(", ");
  return `${authors.slice(0, 3).join(", ")}, et al.`;
}

function sentencePart(value) {
  const text = cleanDisplayText(value);
  if (!text) return "";
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

function normalizedKgClaims() {
  return (claimStores.normalized.all || []).filter((claim) => !isHiddenMainGraphItem(claim));
}

function loadedHeroStats() {
  const totalClaims = normalizedKgClaims();
  const primaryClaims = totalClaims.filter((claim) => !isSecondaryLiteratureClaim(claim));
  const metaAnalysisClaims = totalClaims.filter(isMetaAnalysisClaim);
  const reviewClaims = totalClaims.filter(isReviewLiteratureClaim);
  return {
    primaryStudies: uniqueStudyCount(primaryClaims),
    reviews: uniqueStudyCount(reviewClaims),
    metaAnalyses: uniqueStudyCount(metaAnalysisClaims),
    totalPapers: uniqueStudyCount(totalClaims),
  };
}

function statNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) return null;
  return Math.trunc(number);
}

function heroStatsFromGraphManifest(manifest) {
  const summaryStats = manifest?.summary_stats;
  const primarySummary =
    summaryStats?.sources?.primary ||
    summaryStats?.default ||
    summaryStats?.views?.primary_with_secondary ||
    summaryStats;
  if (!primarySummary || typeof primarySummary !== "object") return null;

  const paperCounts = summaryStats?.paper_counts || {};
  const reviewSummary = summaryStats?.sources?.reviews || {};
  const metaAnalysisSummary = summaryStats?.sources?.meta_analyses || {};
  const awaitingCounts = paperCounts.awaiting_graph_inclusion || {};
  const primaryStudies = statNumber(
    paperCounts.primary_studies ?? primarySummary.study_count ?? primarySummary.studies
  );
  const reviews = statNumber(paperCounts.reviews ?? reviewSummary.study_count ?? reviewSummary.studies);
  const metaAnalyses = statNumber(
    paperCounts.meta_analyses ?? metaAnalysisSummary.study_count ?? metaAnalysisSummary.studies
  );
  const primaryStudiesAwaiting = statNumber(awaitingCounts.primary_studies);
  const reviewsAwaiting = statNumber(awaitingCounts.reviews);
  const metaAnalysesAwaiting = statNumber(awaitingCounts.meta_analyses);
  const values = {
    primaryStudies,
    reviews,
    metaAnalyses,
    totalPapers: statNumber(
      paperCounts.total ??
        (primaryStudies !== null && reviews !== null && metaAnalyses !== null
          ? primaryStudies + reviews + metaAnalyses
          : summaryStats?.default?.study_count)
    ),
    primaryStudiesAwaiting,
    reviewsAwaiting,
    metaAnalysesAwaiting,
    totalPapersAwaiting: statNumber(
      awaitingCounts.total ??
        (primaryStudiesAwaiting !== null && reviewsAwaiting !== null && metaAnalysesAwaiting !== null
          ? primaryStudiesAwaiting + reviewsAwaiting + metaAnalysesAwaiting
          : summaryStats?.default?.normalized_finding_coverage?.without_findings_count)
    ),
  };
  return HERO_STAT_KEYS.some((key) => values[key] !== null) ? values : null;
}

function completeHeroStats(values) {
  const needsFallback = !values || HERO_STAT_KEYS.some((key) => values[key] === null || values[key] === undefined);
  const fallback = needsFallback ? loadedHeroStats() : {};
  const completed = HERO_STAT_KEYS.reduce((acc, key) => {
    acc[key] = values?.[key] ?? fallback[key] ?? 0;
    return acc;
  }, {});
  completed.primaryStudiesAwaiting = values?.primaryStudiesAwaiting ?? null;
  completed.reviewsAwaiting = values?.reviewsAwaiting ?? null;
  completed.metaAnalysesAwaiting = values?.metaAnalysesAwaiting ?? null;
  completed.totalPapersAwaiting = values?.totalPapersAwaiting ?? null;
  return completed;
}

function setHeroStatValues(values) {
  const completeValues = completeHeroStats(values);
  HERO_STAT_KEYS.forEach((key) => {
    if (!stats[key]) return;
    stats[key].textContent = formatCompactNumber(completeValues[key]);
  });
  const awaitingByKey = {
    primaryStudies: completeValues.primaryStudiesAwaiting,
    reviews: completeValues.reviewsAwaiting,
    metaAnalyses: completeValues.metaAnalysesAwaiting,
    totalPapers: completeValues.totalPapersAwaiting,
  };
  HERO_STAT_KEYS.forEach((key) => {
    const detail = statDetails[key];
    const awaiting = awaitingByKey[key];
    if (detail) {
      detail.textContent = awaiting !== null ? `${formatCompactNumber(awaiting)} awaiting graph inclusion` : "";
    }
  });
}

function updateStats() {
  setHeroStatValues(heroStatsSnapshot);
}

function setAccessView(nextView) {
  if (!new Set(["all", "open"]).has(nextView) || accessView === nextView) return;
  retainVisibleBootstrapGraph = false;
  accessView = nextView;
  clearDetailGraphFilter();
  if (!restoreCachedOverviewDetail()) clearDetailForTransition();
  scheduleRender();
  scheduleOverviewDetailPrewarmForSource(currentSourceKey(), 300);
}

function applyFilters(options = {}) {
  return applyFiltersToClaims(activeClaimsForMode(), null, options);
}

function applyFiltersToClaims(activeClaims, yearRangeOverride = null, options = {}) {
  const yearRange = yearRangeOverride || activeYearRange(activeClaims);
  const openAccessOnly = !options.ignoreAccess && accessView === "open";
  const searchValue = options.ignoreSearch ? "" : normalizeFindingSearchText(searchInput?.value);

  const baseFiltered = activeClaims.filter((claim) => {
    if (openAccessOnly && !isOpenAccessClaim(claim)) {
      return false;
    }

    if (searchValue && !claimSearchHaystack(claim).includes(searchValue)) {
      return false;
    }

    if (yearRange.constrained) {
      const year = parseYearValue(claim.study_year);
      if (year === null) return false;
      if (year < yearRange.min || year > yearRange.max) return false;
    }

    return true;
  });

  const detailFiltered = detailGraphFilter?.items
    ? baseFiltered.filter((claim) => detailGraphFilter.items.has(claim))
    : baseFiltered;

  if (!selected || !isolateSelection) return detailFiltered;

  // A graph selection represents the admitted graph projection. Detail-only
  // rows may share the same normalized labels, but including them here makes
  // the drawer/card totals disagree with the edge or node that was clicked.
  const selectedGraphClaims = detailFiltered.filter(isMainGraphAdmitted);

  if (selected.type === "edge") {
    return uniqueGraphPropositionClaims(
      selectedGraphClaims.filter((claim) =>
        claimMatchesGraphEdge(claim, selected.compound, selected.target)
      )
    );
  }
  if (selected.type === "compound") {
    return selectedGraphClaims.filter((claim) => claimMatchesGraphCompound(claim, selected.name));
  }
  if (selected.type === "target") {
    return selectedGraphClaims.filter((claim) => claimMatchesGraphRight(claim, selected.name));
  }
  return selectedGraphClaims;
}

function applyGlobalFindingSearchFilters(options = {}) {
  const activeViewClaims = activeClaimsForMode();
  const currentYearRange = activeYearRange(activeViewClaims);
  return applyFiltersToClaims(
    globalFindingSearchClaims(),
    currentYearRange,
    options
  );
}

function globalFindingSearchClaims() {
  const key = `${claimLayer}|${evidenceView}`;
  if (globalFindingSearchClaimsMemo?.source === claims && globalFindingSearchClaimsMemo.key === key) {
    return globalFindingSearchClaimsMemo.value;
  }
  const value = graphViewClaims(expandedClaimsWithUseContextProjections(claims));
  globalFindingSearchClaimsMemo = { source: claims, key, value };
  return value;
}

function hasFindingSearchQuery() {
  return Boolean(normalizeFindingSearchText(searchInput?.value));
}

function findingCardResults(graphFiltered) {
  if (!hasFindingSearchQuery()) return graphFiltered.filter(isMainGraphAdmitted);
  if (selected || detailGraphFilter) return applyFilters();
  return applyGlobalFindingSearchFilters();
}

function selectionIsValid(data) {
  if (!selected) return true;
  const admittedData = data.filter(isMainGraphAdmitted);
  if (selected.type === "edge") {
    return admittedData.some((claim) => claimMatchesGraphEdge(claim, selected.compound, selected.target));
  }
  if (selected.type === "compound") {
    return admittedData.some((claim) => claimMatchesGraphCompound(claim, selected.name));
  }
  if (selected.type === "target") {
    return admittedData.some((claim) => claimMatchesGraphRight(claim, selected.name));
  }
  return false;
}

function disconnectCardsLoadObserver() {
  if (cardsLoadObserver) {
    cardsLoadObserver.disconnect();
    cardsLoadObserver = null;
  }
}

function disconnectBibliographyLoadObserver() {
  if (bibliographyLoadObserver) {
    bibliographyLoadObserver.disconnect();
    bibliographyLoadObserver = null;
  }
}

function paperFindingContextSummaryHtml(siblingCount) {
  if (!siblingCount) return "";
  const label = siblingCount === 1 ? "Other finding from this paper" : "Other findings from this paper";
  return `
    <details class="paper-findings-context">
      <summary>
        <span>${escapeHtml(label)}</span>
        <span class="paper-findings-count">${formatCompactNumber(siblingCount)}</span>
      </summary>
      <div class="paper-findings-list" aria-live="polite"></div>
    </details>
  `;
}

function paperFindingContextListHtml(siblingClaims) {
  const relationshipGroups = new Map();
  siblingClaims.forEach((sibling) => {
    const relation = claimRelationText(sibling);
    const key = normalizeValue(relation);
    const entry = relationshipGroups.get(key) || { relation, count: 0 };
    entry.count += 1;
    relationshipGroups.set(key, entry);
  });

  return Array.from(relationshipGroups.values())
    .map(({ relation, count }) => {
      return `
        <div class="paper-finding-context-item">
          <div class="paper-finding-context-relation">${escapeHtml(relation)}</div>
          ${
            count > 1
              ? `<span class="paper-finding-context-multiplier" aria-label="${formatCompactNumber(count)} findings">×${formatCompactNumber(count)}</span>`
              : ""
          }
        </div>
      `;
    })
    .join("");
}

function claimCardInnerHtml(claim, referenceClass = "card-reference", siblingCount = 0) {
  const secondary = isSecondaryLiteratureClaim(claim);
  const metaAnalysis = isMetaAnalysisClaim(claim);
  const badges = claimBadgeHtml(claim);

  const relation = claimRelationText(claim);
  const doseRouteSummary = administrationSummaryText(claim);
  const pkAnalyte = compactUniqueParts([claim.metabolite_or_analyte, claim.compound_or_analyte]).join(" • ");
  const pkMatrix = compactUniqueParts([claim.matrix, claim.matrix_or_sample_type]).join(" • ");
  const pkMethod = compactUniqueParts([claim.model_or_method, claim.study_design]).join(" • ");
  const pkObject = compactUniqueParts([claim.pk_graph_object_label, claim.pk_graph_object_kind]).join(" • ");
  const publicHealthEstimate = compactUniqueParts([claim.estimate_value, claim.estimate_unit]).join(" ");
  const systemSummary = compactUniqueParts([displayFieldLabel(claim.system, ""), claim.species]).join(" • ");
  const mainFinding = claimMainFindingText(claim);
  const mainFindingLabel = secondary ? literatureMainFindingLabel(claim) : "Finding";
  const mainFindingLine = mainFinding
    ? `<div class="card-main-finding"><span class="card-field-label">${escapeHtml(mainFindingLabel)}:</span> ${escapeHtml(mainFinding)}</div>`
    : "";
  const exactExposure = meaningfulText(claim.graph_subject_label);
  const overviewExposure = meaningfulText(claim.graph_overview_subject_label || claim.compound);
  const exactExposureLine =
    exactExposure && normalizeValue(exactExposure) !== normalizeValue(overviewExposure)
      ? claimFieldLineFromValue("Exact exposure", exactExposure)
      : "";
  const specificEntityLine = claimSpecificEntityLine(claim);
  const paperFindingContext = paperFindingContextSummaryHtml(siblingCount);
  const referenceLine = studyReferenceHtml(claim, referenceClass);

  const metaAnalysisEvidenceLines = metaAnalysis
    ? [
        claimFieldLineFromValue("Result role", metaAnalysisResultRoleFacetLabel(claim)),
        claimFieldLineFromValue("Population", claim.population),
        claimFieldLineFromValue("Comparator", claim.comparator_normalized || claim.comparator),
        claimFieldLineFromValue("Time window", claim.follow_up_window_normalized || claim.follow_up_duration),
        claimFieldLineFromValue("Estimate", compactUniqueParts([claim.effect_size, claim.p_value]).join(" · ")),
        claimFieldLineFromValue(
          "Included studies",
          claim.meta_analysis_study_count || claim.meta_analysis_overall_study_count
        ),
        claimFieldLineFromValue(
          "Heterogeneity",
          compactUniqueParts([claim.heterogeneity_i_squared, claim.heterogeneity_tau_squared, claim.heterogeneity_interpretation]).join(" · ")
        ),
        claimFieldLineFromValue("Subgroup/moderator", claim.meta_analysis_subgroup_or_moderator),
        claimFieldLineFromValue("Risk of bias", claim.risk_of_bias_summary),
        claimFieldLineFromValue("Certainty", claim.evidence_strength),
      ].join("")
    : "";

  const evidenceLines = secondary
    ? metaAnalysisEvidenceLines
    : isRealWorldPublicHealthClaim(claim)
      ? [
          claimFieldLineFromValue("Topic", claim.public_health_graph_label || claim.graph_entity_label),
          claimFieldLineFromValue("Use context", claim.real_world_use_context),
          claimFieldLineFromValue("Measure", claim.public_health_measure),
          claimFieldLineFromValue("Estimate", publicHealthEstimate),
          claimFieldLineFromValue("Setting", claim.setting),
          claimFieldLineFromValue("Population", claim.population),
          claimFieldLineFromValue("Time window", claim.time_window),
        ].join("")
      : isPharmacokineticsClaim(claim)
        ? [
            claimFieldLineFromValue("Relation", claim.pk_relationship_label),
            claimFieldLineFromValue("Focus", pkObject),
            claimFieldLineFromValue("Analyte", pkAnalyte),
            claimFieldLineFromValue("Matrix", pkMatrix),
            claimFieldLineFromValue("Dose/route", doseRouteSummary),
            claimFieldLineFromValue("Sampling", claim.sampling_time_or_window),
            claimFieldLineFromValue("Method", pkMethod),
          ].join("")
        : isMechanisticDomainClaim(claim)
          ? [
            claimFieldLineFromValue("System", systemSummary),
            claimFieldLineFromValue("Administration", doseRouteSummary),
          ].join("")
          : [
              claimFieldLineFromValue("Population", claim.population),
              claimFieldLineFromValue("Sample", sampleSizeText(claim)),
              claimFieldLineFromValue("Condition", claim.clinical_context_condition),
              claimFieldLineFromValue("Timepoint", claim.timepoint),
              claimFieldLineFromValue("Comparator", claim.comparator_normalized || claim.comparator),
              claimFieldLineFromValue("Administration", doseRouteSummary),
            ].join("");

  return `
      <div class="card-header">
        <h3>${relation}</h3>
        <div class="badge-row">${badges}</div>
      </div>
      <div class="meta">
        ${mainFindingLine}
        ${exactExposureLine}
        ${specificEntityLine}
        ${evidenceLines}
        ${secondary ? "" : claimFieldLineFromValue("Trial registry", claim.trial_registry_ids)}
        ${referenceLine}
        ${paperFindingContext}
      </div>
    `;
}

function createClaimCardElement(claim, siblingClaims = []) {
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = claimCardInnerHtml(claim, "card-reference", siblingClaims.length);

  const paperContext = card.querySelector(".paper-findings-context");
  if (paperContext) {
    paperContext.addEventListener("toggle", () => {
      if (paperContext.open && paperContext.dataset.loaded !== "true") {
        const list = paperContext.querySelector(".paper-findings-list");
        if (list) list.innerHTML = paperFindingContextListHtml(siblingClaims);
        paperContext.dataset.loaded = "true";
      }
    });
  }

  return card;
}

function paperContextClaimsByStudy() {
  const contextClaims = graphViewClaims(claims);
  const yearRange = activeYearRange(contextClaims);
  const key = [
    claimLayer,
    evidenceView,
    accessView,
    yearRange.constrained ? yearRange.min : "all",
    yearRange.constrained ? yearRange.max : "all",
  ].join("|");
  if (paperContextClaimsByStudyMemo?.source === claims && paperContextClaimsByStudyMemo.key === key) {
    return paperContextClaimsByStudyMemo.value;
  }
  const byStudy = new Map();

  contextClaims
    .filter((claim) => passesAccessAndYearFilters(claim, yearRange))
    .forEach((claim) => {
      const key = studyJoinKey(claim);
      if (!key) return;
      const items = byStudy.get(key) || [];
      items.push(claim);
      byStudy.set(key, items);
    });

  paperContextClaimsByStudyMemo = { source: claims, key, value: byStudy };
  return byStudy;
}

function cardsMasonryColumnCount() {
  const width = cardsEl?.clientWidth || window.innerWidth;
  return width <= 640 ? 1 : width <= 860 ? 2 : 4;
}

function createCardsMasonryColumns() {
  const columnCount = cardsMasonryColumnCount();
  cardsEl.style.setProperty("--cards-masonry-column-count", String(columnCount));
  return Array.from({ length: columnCount }, (_, index) => {
    const column = document.createElement("div");
    column.className = "cards-masonry-column";
    column.dataset.masonryColumn = String(index + 1);
    cardsEl.appendChild(column);
    return column;
  });
}

function appendCardToMasonryColumn(columns, card, index) {
  const column = columns[index % columns.length];
  column.appendChild(card);
}

function renderCards(data) {
  const cardData = data;

  disconnectCardsLoadObserver();
  cardsEl.innerHTML = "";
  cardsEl.removeAttribute("aria-busy");

  if (!cardData.length) {
    return;
  }

  const contextClaimsByStudy = paperContextClaimsByStudy();
  let rendered = 0;
  const cardColumns = createCardsMasonryColumns();

  function appendCardsChunk() {
    const end = Math.min(rendered + LIST_CHUNK_SIZE, cardData.length);
    for (let i = rendered; i < end; i += 1) {
      const claim = cardData[i];
      const paperKey = studyJoinKey(claim);
      const siblingClaims = paperKey
        ? (contextClaimsByStudy.get(paperKey) || []).filter((candidate) => candidate !== claim)
        : [];
      appendCardToMasonryColumn(cardColumns, createClaimCardElement(claim, siblingClaims), i);
    }
    rendered = end;
  }

  function removeCardsSentinel() {
    cardsEl.querySelector(".cards-load-sentinel")?.remove();
  }

  function attachCardsSentinelIfNeeded() {
    disconnectCardsLoadObserver();
    removeCardsSentinel();
    if (rendered >= cardData.length) return;

    const sentinel = document.createElement("div");
    sentinel.className = "cards-load-sentinel";
    sentinel.setAttribute("aria-hidden", "true");
    cardsEl.appendChild(sentinel);

    cardsLoadObserver = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting) return;
        disconnectCardsLoadObserver();
        appendCardsChunk();
        attachCardsSentinelIfNeeded();
      },
      { root: cardsEl, rootMargin: "360px", threshold: 0 }
    );
    cardsLoadObserver.observe(sentinel);
  }

  appendCardsChunk();
  attachCardsSentinelIfNeeded();
}

function bibliographyEntryId(entry, index = 0) {
  if (entry.id) return entry.id;
  if (entry.doi) return `doi:${normalizeValue(entry.doi)}`;
  if (entry.openalexId) return `openalex:${normalizeValue(entry.openalexId)}`;
  const titleKey = normalizeValue(entry.title);
  if (titleKey || entry.year) return `title:${titleKey}|${entry.year || ""}`;
  return `bibliography-entry-${index}`;
}

function normalizeBibliographyPaper(item, index = 0) {
  const year = parseYearValue(item?.year ?? item?.study_year ?? item?.publication_date);
  const entry = {
    id: cleanDisplayText(item?.id),
    doi: normalizeDoi(item?.doi ?? item?.study_doi),
    openalexId: cleanDisplayText(item?.openalex_id ?? item?.openalexId),
    title: cleanDisplayText(item?.title ?? item?.study_title) || "Untitled study",
    authors: cleanDisplayText(item?.authors ?? item?.author_list ?? item?.author ?? item?.first_author),
    year: year ?? "",
    journal: cleanDisplayText(item?.journal ?? item?.study_journal),
    publicationDate: cleanDisplayText(item?.publication_date ?? item?.publicationDate),
    publicationType: cleanDisplayText(item?.publication_type ?? item?.publicationType),
    publisher: cleanDisplayText(item?.publisher),
    trialRegistryIds: cleanDisplayText(item?.trial_registry_ids ?? item?.trialRegistryIds),
    keywords: cleanDisplayText(item?.keywords),
    meshTerms: cleanDisplayText(item?.mesh_terms ?? item?.meshTerms),
    searchText: rawSearchTextForObject(item),
    contexts: Array.isArray(item?.contexts)
      ? item.contexts
          .map((context) => ({
            compound: cleanDisplayText(context?.compound),
            entity: cleanDisplayText(context?.entity ?? context?.target ?? context?.disorder),
          }))
          .filter((context) => context.compound || context.entity)
      : [],
  };
  entry.id = bibliographyEntryId(entry, index);
  return entry;
}

function bibliographyFromPayload(payload) {
  const papers = Array.isArray(payload?.papers) ? payload.papers : [];
  return papers.map((paper, index) => normalizeBibliographyPaper(paper, index));
}

function bibliographyLookup() {
  const rows = bibliographyBySource.all || [];
  const byDoi = new Map();
  const byOpenAlex = new Map();
  rows.forEach((entry) => {
    const doiKey = normalizeValue(normalizeDoi(entry.doi));
    if (doiKey && !byDoi.has(doiKey)) byDoi.set(doiKey, entry);
    const openAlexKey = normalizeValue(entry.openalexId);
    if (openAlexKey && !byOpenAlex.has(openAlexKey)) byOpenAlex.set(openAlexKey, entry);
  });
  return { byDoi, byOpenAlex };
}

function enrichClaimsWithBibliographyMetadata(items) {
  const lookup = bibliographyLookup();
  return items.map((claim) => {
    const doiKey = normalizeValue(normalizeDoi(claim.study_doi));
    const openAlexKey = normalizeValue(claim.openalex_id);
    const entry = (doiKey && lookup.byDoi.get(doiKey)) || (openAlexKey && lookup.byOpenAlex.get(openAlexKey));
    if (!entry) return claim;
    const enriched = {
      ...claim,
      study_journal: claim.study_journal || entry.journal,
      publication_type: claim.publication_type || entry.publicationType,
      publication_date: claim.publication_date || entry.publicationDate,
      publisher: claim.publisher || entry.publisher,
      trial_registry_ids: claim.trial_registry_ids || entry.trialRegistryIds,
      authors: claimAuthors(claim) ? claim.authors : entry.authors,
    };
    const bibliographySearchText = normalizeFindingSearchText(
      [
        entry.title,
        entry.authors,
        entry.journal,
        entry.publicationDate,
        entry.publicationType,
        entry.publisher,
        entry.trialRegistryIds,
        entry.keywords,
        entry.meshTerms,
        entry.doi,
        entry.openAlexId,
      ].join(" ")
    );
    const cachedRawSearchText = rawClaimSearchTextCache.get(claim);
    if (cachedRawSearchText !== undefined) {
      rawClaimSearchTextCache.set(
        enriched,
        bibliographySearchText ? `${cachedRawSearchText} ${bibliographySearchText}` : cachedRawSearchText
      );
    }
    const cachedSearchTextByContext = claimSearchTextCache.get(claim);
    if (cachedSearchTextByContext) {
      const enrichedSearchTextByContext = new Map();
      cachedSearchTextByContext.forEach((text, contextKey) => {
        enrichedSearchTextByContext.set(contextKey, bibliographySearchText ? `${text} ${bibliographySearchText}` : text);
      });
      claimSearchTextCache.set(enriched, enrichedSearchTextByContext);
    }
    return enriched;
  });
}

function addBibliographyContext(entry, compound, entity) {
  const compoundText = cleanDisplayText(compound);
  const entityText = cleanDisplayText(entity);
  if (!compoundText && !entityText) return;
  const key = `${normalizeValue(compoundText)}|${normalizeValue(entityText)}`;
  const exists = entry.contexts.some(
    (context) => `${normalizeValue(context.compound)}|${normalizeValue(context.entity)}` === key
  );
  if (!exists) entry.contexts.push({ compound: compoundText, entity: entityText });
}

function bibliographyRowsFromClaims(data) {
  const rightKey = rightEntityKey();
  const studies = new Map();

  data.forEach((claim, index) => {
    const baseEntry = normalizeBibliographyPaper(
      {
        id: studyKey(claim, index),
        doi: claim.study_doi,
        openalex_id: claim.openalex_id,
        title: claim.study_title,
        authors: claimAuthors(claim),
        year: claim.study_year,
        journal: claim.study_journal ?? claim.journal,
        publication_type: claim.publication_type,
        publication_date: claim.publication_date,
        publisher: claim.publisher,
        trial_registry_ids: claim.trial_registry_ids,
      },
      index
    );
    baseEntry.searchText = normalizeSearchText([baseEntry.searchText, claimSearchHaystack(claim)].join(" "));
    addBibliographyContext(baseEntry, compoundGraphLabelForClaim(claim), graphRightLabelForClaim(claim) || claim[rightKey]);
    const id = bibliographyEntryId(baseEntry, index);
    const existing = studies.get(id);
    if (!existing) {
      studies.set(id, baseEntry);
      return;
    }

    ["doi", "openalexId", "title", "authors", "year", "journal", "publicationDate", "publicationType", "publisher", "trialRegistryIds"].forEach(
      (field) => {
        if (!existing[field] && baseEntry[field]) existing[field] = baseEntry[field];
      }
    );
    existing.searchText = normalizeSearchText([existing.searchText, baseEntry.searchText].join(" "));
    baseEntry.contexts.forEach((context) => addBibliographyContext(existing, context.compound, context.entity));
  });

  return Array.from(studies.values()).sort((a, b) => {
    const yearDiff = (Number(b.year) || 0) - (Number(a.year) || 0);
    if (yearDiff !== 0) return yearDiff;
    return (a.title || "").localeCompare(b.title || "");
  });
}

function currentBibliographyYearRange() {
  if (!yearMinFilter || !yearMaxFilter) return { constrained: false, min: null, max: null };
  const bounds = yearBoundsFromClaims(activeClaimsForMode());
  if (!bounds) return { constrained: false, min: null, max: null };
  const minYear = parseYearValue(yearMinFilter.value) ?? bounds.min;
  const maxYear = parseYearValue(yearMaxFilter.value) ?? bounds.max;
  return {
    constrained: minYear > bounds.min || maxYear < bounds.max,
    min: Math.min(minYear, maxYear),
    max: Math.max(minYear, maxYear),
  };
}

function bibliographyPaperMatchesSelection(entry) {
  if (!selected || !isolateSelection) return true;
  const contexts = entry.contexts || [];
  if (!contexts.length) return false;

  if (selected.type === "edge") {
    return contexts.some(
      (context) =>
        sameGraphLabel(context.compound, selected.compound) &&
        sameGraphLabel(graphRightLabelForContextEntity(context.entity), selected.target)
    );
  }
  if (selected.type === "compound") {
    return contexts.some((context) => sameGraphLabel(context.compound, selected.name));
  }
  if (selected.type === "target") {
    return contexts.some((context) => sameGraphLabel(graphRightLabelForContextEntity(context.entity), selected.name));
  }
  return true;
}

function bibliographyRowsForCurrentView(data) {
  const payloadRows = bibliographyBySource.all || [];
  const rows = payloadRows.length ? payloadRows : bibliographyRowsFromClaims(data);
  const yearRange = payloadRows.length ? currentBibliographyYearRange() : { constrained: false };
  return rows.filter((entry) => {
    if (yearRange.constrained) {
      const year = parseYearValue(entry.year || entry.publicationDate);
      if (year === null) return false;
      if (year < yearRange.min || year > yearRange.max) return false;
    }
    return bibliographyPaperMatchesSelection(entry);
  });
}

function bibliographyHaystack(entry) {
  const contextText = (entry.contexts || [])
    .map((context) => `${context.compound} ${context.entity}`)
    .join(" ");
  return normalizeSearchText(
    [
      entry.searchText,
      entry.title,
      entry.authors,
      entry.journal,
      entry.year,
      entry.publicationDate,
      entry.publicationType,
      entry.publisher,
      entry.trialRegistryIds,
      entry.keywords,
      entry.meshTerms,
      entry.doi,
      entry.openalexId,
      contextText,
    ].join(" ")
  );
}

function bibliographyCitationHtml(entry) {
  const authors = citationAuthors(entry.authors);
  const year = parseYearValue(entry.year || entry.publicationDate) ?? "n.d.";
  const title = sentencePart(entry.title || "Untitled study");
  const journal = sentencePart(entry.journal);
  const doiHref = doiUrl(entry.doi);
  const openAlexHref = !doiHref && entry.openalexId ? openAlexUrl(entry.openalexId) : "";
  const yearHtml = `<span>(${escapeHtml(String(year))}).</span>`;
  const titleHtml = `<span>${escapeHtml(title)}</span>`;

  return `
    <p class="study-citation">
      <span>${escapeHtml(authors)}</span>
      ${yearHtml}
      ${titleHtml}
      ${journal ? `<em>${escapeHtml(journal)}</em>` : ""}
      ${doiHref ? `<a href="${doiHref}" target="_blank" rel="noopener noreferrer">${escapeHtml(doiHref)}</a>` : ""}
      ${openAlexHref ? `<a href="${openAlexHref}" target="_blank" rel="noopener noreferrer">OpenAlex</a>` : ""}
    </p>
  `;
}

function renderBibliography(data) {
  if (!studyListEl) return;

  const rows = bibliographyRowsForCurrentView(data);
  const bibliographyQuery = normalizeSearchText(bibliographySearchInput?.value);
  const filteredRows = !bibliographyQuery
    ? rows
    : rows.filter((entry) => bibliographyHaystack(entry).includes(bibliographyQuery));

  if (!filteredRows.length) {
    disconnectBibliographyLoadObserver();
    studyListEl.innerHTML = '<div class="detail-empty">No bibliography entries in the current view.</div>';
    return;
  }

  disconnectBibliographyLoadObserver();
  studyListEl.innerHTML = "";

  function studyArticleHtml(entry) {
    return `
        <article class="study-item">
          ${bibliographyCitationHtml(entry)}
        </article>
      `;
  }

  let bibliographyRendered = 0;

  function appendBibliographyChunk() {
    const end = Math.min(bibliographyRendered + LIST_CHUNK_SIZE, filteredRows.length);
    const slice = filteredRows.slice(bibliographyRendered, end);
    bibliographyRendered = end;
    const html = slice.map((entry) => studyArticleHtml(entry)).join("");
    studyListEl.insertAdjacentHTML("beforeend", html);
  }

  function removeBibliographySentinel() {
    studyListEl.querySelector(".bibliography-load-sentinel")?.remove();
  }

  function attachBibliographySentinelIfNeeded() {
    disconnectBibliographyLoadObserver();
    removeBibliographySentinel();
    if (bibliographyRendered >= filteredRows.length) return;

    const sentinel = document.createElement("div");
    sentinel.className = "bibliography-load-sentinel";
    sentinel.setAttribute("aria-hidden", "true");
    studyListEl.appendChild(sentinel);

    bibliographyLoadObserver = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting) return;
        disconnectBibliographyLoadObserver();
        appendBibliographyChunk();
        attachBibliographySentinelIfNeeded();
      },
      { root: studyListEl, rootMargin: "360px", threshold: 0 }
    );
    bibliographyLoadObserver.observe(sentinel);
  }

  appendBibliographyChunk();
  attachBibliographySentinelIfNeeded();
}

function summarizeConnections(items, key) {
  const map = new Map();
  items.forEach((item) => {
    const label =
      key === "compound"
        ? compoundGraphLabelForClaim(item)
        : key === rightEntityKey()
          ? graphRightLabelForClaim(item)
          : graphLabel(item[key]);
    if (!label) return;
    const entry = map.get(label) || { count: 0 };
    entry.count += 1;
    map.set(label, entry);
  });
  return Array.from(map.entries())
    .map(([label, entry]) => ({ label, ...entry }))
    .sort((a, b) => b.count - a.count);
}

function escapeHtml(value) {
  return (value ?? "")
    .toString()
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Label ends with colon; bold styling comes from `.card-field-label` in CSS. */
function claimFieldLine(label, valueHtml) {
  return `<div><span class="card-field-label">${escapeHtml(label)}:</span> ${valueHtml}</div>`;
}

function formatCompactNumber(value) {
  const number = Number(value) || 0;
  return number.toLocaleString("en-US");
}

function displayFieldLabel(value, fallback = "Unknown") {
  const normalized = normalizeValue(value);
  if (!normalized) return fallback;
  if (normalized === "null") return "Null";
  return labelFromSlug(normalized).replace(/\b\w/g, (char) => char.toUpperCase());
}

const EMPTY_FIELD_VALUES = new Set([
  "",
  "not_reported",
  "not reported",
  "not_applicable",
  "not applicable",
  "unknown",
  "none",
  "n/a",
  "na",
]);

function meaningfulText(value) {
  const text = cleanDisplayText(value);
  if (EMPTY_FIELD_VALUES.has(normalizeValue(text))) return "";
  return text;
}

function claimFieldLineFromValue(label, value) {
  const text = meaningfulText(value);
  return text ? claimFieldLine(label, escapeHtml(text)) : "";
}

function linkedStudyIdentifierHtml(claim) {
  const doiValue = meaningfulText(claim.study_doi);
  const doiHref = doiUrl(doiValue);
  if (doiValue && doiHref) {
    return `<a href="${doiHref}" target="_blank" rel="noopener noreferrer">doi:${escapeHtml(doiValue)}</a>`;
  }

  const openAlexId = meaningfulText(claim.openalex_id);
  const openAlexHref = openAlexUrl(openAlexId);
  if (openAlexId && openAlexHref) {
    return `<a href="${openAlexHref}" target="_blank" rel="noopener noreferrer">OpenAlex</a>`;
  }

  return "";
}

function studyReferenceHtml(claim, className = "card-reference") {
  const authors = citationAuthors(claimAuthors(claim));
  const year = meaningfulText(claim.study_year);
  const title = meaningfulText(claim.study_title) || "Untitled study";
  const journal = meaningfulText(claim.study_journal || claim.journal);
  const source = linkedStudyIdentifierHtml(claim);
  const authorYear = compactUniqueParts([
    authors && authors !== "Unknown authors" ? authors : "",
    year ? `(${year})` : "",
  ]).join(" ");
  const citation = [
    authorYear ? escapeHtml(sentencePart(authorYear)) : "",
    escapeHtml(sentencePart(title)),
    journal ? `<span class="card-reference-journal">${escapeHtml(sentencePart(journal))}</span>` : "",
    source,
  ]
    .filter(Boolean)
    .join(" ");

  return citation ? `<div class="${className}">${citation}</div>` : "";
}

function claimRelationText(claim) {
  const compound = meaningfulText(claim.compound) || "Unknown compound";
  const graphEntity =
    meaningfulText(graphRightLabelForClaim(claim)) ||
    meaningfulText(claim.raw_entity_label) ||
    meaningfulText(claim.graph_entity_label) ||
    `Non-graph ${lowerRightEntityLabel(false)}`;
  return `${compound} → ${graphEntity}`;
}

function hierarchicalSpecificFieldLabel() {
  if (claimLayer !== "normalized") return "";
  const view = currentEntityViewKey();
  if (view === "intervention_component") return "Specific context";
  if (view === "brain_system") return "Specific brain region/network";
  if (view === "pathway_readout") return "Specific molecular finding";
  return "";
}

function claimSpecificEntityLine(claim) {
  const fieldLabel = hierarchicalSpecificFieldLabel();
  if (!fieldLabel) return "";
  const topic = meaningfulText(graphRightLabelForClaim(claim));
  const specific = meaningfulText(graphRightRawLabel(claim));
  if (!topic || !specific || sameGraphLabel(topic, specific)) return "";
  return claimFieldLineFromValue(fieldLabel, specific);
}

function isPharmacokineticsClaim(claim) {
  return normalizeValue(claim?.kg_domain || claim?.domain || claim?.finding_type) === "pharmacokinetics_exposure";
}

function isMechanisticDomainClaim(claim) {
  return ["molecular_target", "molecular_pathway_readout", "brain_system"].includes(
    normalizeValue(claim?.kg_domain || claim?.domain || claim?.finding_type)
  );
}

function isRealWorldPublicHealthClaim(claim) {
  return normalizeValue(claim?.kg_domain || claim?.domain || claim?.finding_type) === "real_world_public_health";
}

function sampleSizeText(claim) {
  return meaningfulText(claim.sample_size_total) || meaningfulText(claim.sample_size_by_arm);
}

function secondaryCoverageText(claim) {
  const notes = normalizeValue(claim.notes);
  const literatureType = literatureTypeLabel(claim);
  if (notes.includes("coverage_type=meta_analyzes") || literatureType === "Meta-analysis") {
    return "Synthesizes literature on relationship";
  }
  if (notes.includes("coverage_type=summarizes") || literatureType === "Systematic review") {
    return "Summarizes literature on relationship";
  }
  return "Discusses relationship";
}

function literatureMainFindingLabel(claim) {
  return isMetaAnalysisClaim(claim) ? "Result" : "Summary";
}

function evidenceLocationText(claim) {
  const location = meaningfulText(claim.evidence_location);
  if (location) return displayFieldLabel(location);
  const locator = meaningfulText(claim.evidence_locator);
  if (!locator) return "";
  return locator.replace(/^(abstract|full text|metadata\/title)\s+snippet:\s*/i, "$1").trim();
}

function compactUniqueParts(values) {
  const seen = new Set();
  return values
    .map((value) => meaningfulText(value))
    .filter(Boolean)
    .filter((value) => {
      const key = normalizeValue(value);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function displayOutcomeType(value) {
  const text = meaningfulText(value);
  return text ? labelFromSlug(text) : "";
}

function conciseFindingText(value, maxChars = MAIN_FINDING_MAX_CHARS) {
  const text = meaningfulText(value).replace(/\s+/g, " ").trim();
  if (!text) return "";

  const emptyKey = normalizeValue(text.replace(/[.?!]+$/g, ""));
  if (EMPTY_FIELD_VALUES.has(emptyKey)) return "";
  if (text.length <= maxChars) return text;

  const preview = text.slice(0, Math.max(1, maxChars - 3)).trimEnd();
  const sentenceEnd = Math.max(preview.lastIndexOf(". "), preview.lastIndexOf("; "));
  if (sentenceEnd >= 100) return preview.slice(0, sentenceEnd + 1);
  return `${preview.replace(/[,\s;:]+$/g, "")}...`;
}

function resultDetailText(claim) {
  const text = meaningfulText(claim.effect_size).replace(/\s+/g, " ").trim();
  if (!text) return "";

  const normalized = normalizeValue(text);
  const genericDetailPatterns = [
    /^qualitative summary(?: of scores)?$/,
    /^mean\s*(?:\u00b1|\+\/-|plus minus)?\s*(?:sem|sd)?$/,
    /^descriptive(?: statistics)?$/,
    /^count$/,
    /^serum concentration$/,
    /^(?:one|two)-way anova(?:\b|$)/,
    /^anova(?:\b|$)/,
  ];
  if (genericDetailPatterns.some((pattern) => pattern.test(normalized))) return "";
  if (normalizeValue(claim.support) === normalized) return "";
  return conciseFindingText(text, 180);
}

function outcomeMeasureSummaryText(claim) {
  const outcome = meaningfulText(claim.outcome_measure) || displayOutcomeType(claim.outcome_type);
  const scale = meaningfulText(claim.outcome_measure_normalized);
  return compactUniqueParts([outcome, scale]).join(" · ");
}

function claimMainFindingText(claim) {
  const support = conciseFindingText(claim.support);
  if (support) return support;

  const resultDetail = resultDetailText(claim);
  if (resultDetail) return resultDetail;

  if (isMechanisticDomainClaim(claim)) {
    const value = [
      meaningfulText(claim.affinity_value),
      meaningfulText(claim.affinity_unit),
    ]
      .filter(Boolean)
      .join(" ");
    if (value) {
      return compactUniqueParts([claim.affinity_type, value]).join(" · ");
    }
    return compactUniqueParts([claim.mechanism_type, claim.action_type, claim.assay_type]).join(" · ");
  }

  if (isRealWorldPublicHealthClaim(claim)) {
    const estimate = compactUniqueParts([claim.estimate_value, claim.estimate_unit]).join(" ");
    return compactUniqueParts([claim.public_health_measure, estimate, claim.association_or_trend]).join(" · ");
  }

  return outcomeMeasureSummaryText(claim);
}

function sampleSizeBinsForItems(items = []) {
  if (currentEntityViewKey() === "public_health_measure") return REAL_WORLD_SAMPLE_SIZE_BINS;
  const realWorldCount = items.filter((claim) => isRealWorldPublicHealthClaim(claim)).length;
  return realWorldCount > 0 && realWorldCount >= items.length / 2 ? REAL_WORLD_SAMPLE_SIZE_BINS : DEFAULT_SAMPLE_SIZE_BINS;
}

function sampleSizeNumberText(value) {
  const text = meaningfulText(value);
  if (!text) return "";
  const withoutWeightedFragments = text
    .replace(/\([^)]*\bweight(?:ed|ing)?\b[^)]*\)/gi, " ")
    .replace(/\bweight(?:ed|ing)?\s*(?:n|sample|count|population|estimate)?\s*(?:=|:)?\s*\d{1,3}(?:,\d{3})*(?:\.\d+)?/gi, " ");
  return meaningfulText(withoutWeightedFragments) || text;
}

function parseSampleSize(value) {
  const text = sampleSizeNumberText(value);
  if (!text) return null;
  const matches = text.match(/\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?/g) || [];
  const numbers = matches
    .map((match) => Number(match.replace(/,/g, "")))
    .filter((number) => Number.isFinite(number) && number >= 1);
  if (!numbers.length) return null;
  return Math.round(Math.max(...numbers));
}

function sampleSizeBucket(value, bins = DEFAULT_SAMPLE_SIZE_BINS) {
  const size = parseSampleSize(value);
  if (size === null) return "";
  return bins.find((bin) => size >= bin.min && size <= bin.max)?.label || "";
}

function sampleSizeBinForSize(size, bins = DEFAULT_SAMPLE_SIZE_BINS) {
  if (!Number.isFinite(size) || size < 1) return null;
  return bins.find((bin) => size >= bin.min && size <= bin.max) || null;
}

function splitNormalizedOutcomeMeasures(value) {
  return meaningfulText(value)
    .split(/\s*;\s*/)
    .map((part) => meaningfulText(part))
    .filter(Boolean);
}

function isOutcomeScaleClaim(claim) {
  return entityKindForClaim(claim) === "outcome_scale";
}

function outcomeScaleLabelsForClaim(claim) {
  if (isOutcomeScaleClaim(claim)) {
    return [graphRightLabelForClaim(claim)].filter(Boolean);
  }
  return splitNormalizedOutcomeMeasures(claim.outcome_measure_normalized);
}

function studyKey(claim, index) {
  const id = studyId(claim);
  if (id && id !== "unknown") return id;

  const title = normalizeValue(claim.study_title);
  const year = parseYearValue(claim.study_year);
  if (title || year !== null) return `${title}|${year || ""}`;

  return `claim-${index}`;
}

function uniqueStudyEntries(items) {
  const seen = new Set();
  const entries = [];

  items.forEach((claim, index) => {
    const key = studyKey(claim, index);
    if (seen.has(key)) return;
    seen.add(key);
    entries.push({
      key,
      year: parseYearValue(claim.study_year),
      claim,
    });
  });

  return entries;
}

function uniqueStudyCount(items) {
  return uniqueStudyEntries(items).length;
}

function graphRecordCount(claim) {
  if (claim?.__graph_bootstrap && accessView === "open") {
    const fullTextCount = Number(claim?.graph_full_text_claim_count);
    return Number.isFinite(fullTextCount) && fullTextCount > 0 ? fullTextCount : 1;
  }
  const count = Number(claim?.graph_claim_count ?? claim?.finding_count);
  return Number.isFinite(count) && count > 0 ? count : 1;
}

function graphRecordCountForItems(items) {
  return items.reduce((sum, claim) => sum + graphRecordCount(claim), 0);
}

function graphStudyCountForItems(items) {
  if (!items.some((claim) => claim?.__graph_bootstrap)) return uniqueStudyCount(items);
  return items.reduce((sum, claim) => {
    const count =
      claim?.__graph_bootstrap && accessView === "open"
        ? Number(claim?.graph_full_text_study_count)
        : Number(claim?.graph_study_count ?? claim?.study_count);
    return sum + (Number.isFinite(count) && count > 0 ? count : graphRecordCount(claim));
  }, 0);
}

function evidenceCountTooltipHtml(items) {
  const studyCount = graphStudyCountForItems(items);
  const recordCount = graphRecordCountForItems(items);
  const labels = recordLabelsForItems(items);
  const recordLabel = recordCount === 1 ? labels.lowerSingular : labels.lowerPlural;
  return `<span class="tooltip-meta">${formatCompactNumber(studyCount)} stud${
    studyCount === 1 ? "y" : "ies"
  } · ${formatCompactNumber(recordCount)} ${escapeHtml(recordLabel)}</span>`;
}

function yearStats(items) {
  const years = uniqueStudyEntries(items)
    .map((entry) => entry.year)
    .filter((year) => year !== null)
    .sort((a, b) => a - b);

  if (!years.length) {
    return { first: null, last: null, spanLabel: "No publication years" };
  }

  const first = years[0];
  const last = years[years.length - 1];
  return {
    first,
    last,
    spanLabel: first === last ? String(first) : `${first}-${last}`,
  };
}

function buildYearBuckets(items) {
  const entries = uniqueStudyEntries(items).filter((entry) => entry.year !== null);
  if (!entries.length) return [];

  const years = entries.map((entry) => entry.year);
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  const step = 1;
  const startYear = Math.floor(minYear / step) * step;
  const buckets = [];

  for (let start = startYear; start <= maxYear; start += step) {
    buckets.push({
      start,
      end: Math.min(start + step - 1, maxYear),
      count: 0,
      claims: 0,
    });
  }

  entries.forEach((entry) => {
    const index = Math.floor((entry.year - startYear) / step);
    if (buckets[index]) buckets[index].count += 1;
  });
  items.forEach((claim) => {
    const year = parseYearValue(claim.study_year);
    if (year === null) return;
    const index = Math.floor((year - startYear) / step);
    if (buckets[index]) buckets[index].claims += 1;
  });

  return buckets.map((bucket) => ({
    ...bucket,
    label: bucket.start === bucket.end ? String(bucket.start) : `${bucket.start}-${bucket.end}`,
  }));
}

function summarizeConnectionEvidence(items, key) {
  const map = new Map();

  items.forEach((claim, index) => {
    const label = key === "compound" ? compoundGraphLabelForClaim(claim) : graphLabel(claim[key]);
    if (!label) return;
    const entry = map.get(label) || { label, claims: 0, studies: new Set() };
    entry.claims += 1;
    entry.studies.add(studyKey(claim, index));
    map.set(label, entry);
  });

  return Array.from(map.values())
    .map((entry) => ({
      label: entry.label,
      claims: entry.claims,
      studies: entry.studies.size,
    }))
    .sort((a, b) => {
      const byStudies = b.studies - a.studies;
      if (byStudies !== 0) return byStudies;
      const byClaims = b.claims - a.claims;
      if (byClaims !== 0) return byClaims;
      return a.label.localeCompare(b.label);
    });
}

function summarizeFieldEvidence(items, field, options = {}) {
  const map = new Map();
  const seen = new Set();

  items.forEach((claim, index) => {
    const labels = options.splitValues
      ? splitNormalizedOutcomeMeasures(claim[field])
      : [meaningfulText(claim[field])].filter(Boolean);
    if (!labels.length) return;
    const study = studyKey(claim, index);
    labels.forEach((label) => {
      const seenKey = options.uniqueStudies ? `${study}|${label}` : "";
      if (seenKey) {
        if (seen.has(seenKey)) return;
        seen.add(seenKey);
      }
      const entry = map.get(label) || { label, count: 0, studies: new Set() };
      entry.count += 1;
      entry.studies.add(study);
      map.set(label, entry);
    });
  });

  return Array.from(map.values())
    .map((entry) => ({
      label: entry.label,
      count: entry.count,
      studies: entry.studies.size,
    }))
    .sort((a, b) => {
      const byCount = b.count - a.count;
      if (byCount !== 0) return byCount;
      const byStudies = b.studies - a.studies;
      if (byStudies !== 0) return byStudies;
      return a.label.localeCompare(b.label);
    });
}

function summarizeFacetEvidence(items, valueForClaim) {
  const map = new Map();

  items.forEach((claim, index) => {
    const rawValue = valueForClaim(claim);
    const label =
      rawValue && typeof rawValue === "object"
        ? meaningfulText(rawValue.label || rawValue.name || rawValue.displayLabel || rawValue.value)
        : meaningfulText(rawValue);
    if (!label) return;
    const value =
      rawValue && typeof rawValue === "object"
        ? meaningfulText(rawValue.value || rawValue.id || rawValue.key || label)
        : label;
    const study = studyKey(claim, index);
    const entry = map.get(value) || { label, value, claims: 0, studies: new Set() };
    entry.label = preferredFacetLabel(entry.label, label);
    entry.claims += 1;
    entry.studies.add(study);
    map.set(value, entry);
  });

  return Array.from(map.values())
    .map((entry) => ({
      label: entry.label,
      value: entry.value,
      claims: entry.claims,
      studies: entry.studies.size,
    }))
    .sort((a, b) => {
      const byStudies = b.studies - a.studies;
      if (byStudies !== 0) return byStudies;
      const byClaims = b.claims - a.claims;
      if (byClaims !== 0) return byClaims;
      return a.label.localeCompare(b.label);
    });
}

function summarizeMultiFacetEvidence(items, valuesForClaim) {
  const map = new Map();

  items.forEach((claim, index) => {
    const values = valuesForClaim(claim);
    const labels = Array.isArray(values) ? values : [values];
    const study = studyKey(claim, index);
    labels.forEach((rawValue) => {
      const label =
        rawValue && typeof rawValue === "object"
          ? meaningfulText(rawValue.label || rawValue.name || rawValue.displayLabel || rawValue.value)
          : meaningfulText(rawValue);
      if (!label) return;
      const value =
        rawValue && typeof rawValue === "object"
          ? meaningfulText(rawValue.value || rawValue.id || rawValue.key || label)
          : label;
      const entry = map.get(value) || { label, value, claims: 0, studies: new Set() };
      entry.label = preferredFacetLabel(entry.label, label);
      entry.claims += 1;
      entry.studies.add(study);
      map.set(value, entry);
    });
  });

  return Array.from(map.values())
    .map((entry) => ({
      label: entry.label,
      value: entry.value,
      claims: entry.claims,
      studies: entry.studies.size,
    }))
    .sort((a, b) => {
      const byStudies = b.studies - a.studies;
      if (byStudies !== 0) return byStudies;
      const byClaims = b.claims - a.claims;
      if (byClaims !== 0) return byClaims;
      return a.label.localeCompare(b.label);
    });
}

function facetLabelCaseScore(label) {
  const text = meaningfulText(label);
  if (!text) return 0;
  const letters = text.match(/[A-Za-z]/g) || [];
  if (!letters.length) return text.length / 1000;
  const uppercaseCount = letters.filter((letter) => letter === letter.toUpperCase()).length;
  const lowercaseCount = letters.length - uppercaseCount;
  const isAllLowercase = uppercaseCount === 0 && lowercaseCount > 0;
  const isAllUppercase = lowercaseCount === 0 && uppercaseCount > 0;
  const hasMixedCase = uppercaseCount > 0 && lowercaseCount > 0;
  return (
    (hasMixedCase ? 100 : 0) +
    (isAllUppercase ? 40 : 0) -
    (isAllLowercase ? 40 : 0) +
    uppercaseCount / 100 +
    text.length / 1000
  );
}

function preferredFacetLabel(currentLabel, candidateLabel) {
  const current = meaningfulText(currentLabel);
  const candidate = meaningfulText(candidateLabel);
  if (!candidate) return current;
  if (!current) return candidate;
  return facetLabelCaseScore(candidate) > facetLabelCaseScore(current) ? candidate : current;
}

function journalFacetKey(value) {
  return meaningfulText(value).toLocaleLowerCase("en-US").replace(/\s+/g, " ");
}

function journalFacetValue(claim) {
  const label = meaningfulText(claim.study_journal || claim.journal);
  const value = journalFacetKey(label);
  return label && value ? { label, value } : "";
}

function summarizeAuthorRoleEvidence(items) {
  const map = new Map();
  const authorAliases = buildAuthorRoleAliasMap(items);

  items.forEach((claim, index) => {
    const study = studyKey(claim, index);
    const claimKey = claim.kg_claim_id || claim.external_id || `${study}|${index}`;
    [
      ["first", firstAuthorFacetValue(claim, authorAliases)],
      ["last", lastAuthorFacetValue(claim, authorAliases)],
    ].forEach(([role, rawValue]) => {
      const label = rawValue && typeof rawValue === "object" ? meaningfulText(rawValue.label || rawValue.value) : "";
      const value = rawValue && typeof rawValue === "object" ? meaningfulText(rawValue.value || label) : "";
      if (!label || !value) return;
      const entry =
        map.get(value) ||
        {
          label,
          value,
          studies: new Set(),
          claims: new Set(),
          firstStudies: new Set(),
          lastStudies: new Set(),
        };
      entry.label = preferredFacetLabel(entry.label, label);
      entry.studies.add(study);
      entry.claims.add(claimKey);
      if (role === "first") entry.firstStudies.add(study);
      if (role === "last") entry.lastStudies.add(study);
      map.set(value, entry);
    });
  });

  return Array.from(map.values())
    .map((entry) => ({
      label: entry.label,
      value: entry.value,
      studies: entry.studies.size,
      claims: entry.claims.size,
      firstStudies: entry.firstStudies.size,
      lastStudies: entry.lastStudies.size,
      roleStudies: entry.firstStudies.size + entry.lastStudies.size,
    }))
    .sort((a, b) => {
      const byRoleStudies = b.roleStudies - a.roleStudies;
      if (byRoleStudies !== 0) return byRoleStudies;
      const byStudies = b.studies - a.studies;
      if (byStudies !== 0) return byStudies;
      const byClaims = b.claims - a.claims;
      if (byClaims !== 0) return byClaims;
      return a.label.localeCompare(b.label);
    });
}

function renderFacetChipChart(entries, title, filterField, options = {}) {
  if (!entries.length) {
    if (options.hideWhenEmpty) return "";
    return trendCardHtml(title, "", `<div class="trend-empty">${escapeHtml(options.emptyText || "No metadata in this selection.")}</div>`);
  }

  const orderedEntries = orderedFacetEntries(entries, options.order || []);
  const chips = orderedEntries
    .map((entry) => {
      const claims = Number(entry.claims ?? entry.count ?? 0) || 0;
      const studies = Number(entry.studies ?? claims) || 0;
      const filterValue = entry.value || entry.label;
      return `
        <button class="scale-chip facet-chip" type="button"
          data-filter-field="${escapeHtml(filterField)}"
          data-filter-value="${escapeHtml(filterValue)}"
          data-filter-label="${escapeHtml(entry.label)}"
          data-study-count="${escapeHtml(String(studies))}"
          data-claim-count="${escapeHtml(String(claims))}"
          title="${escapeHtml(entry.label)}: ${formatCompactNumber(studies)} studies, ${formatCompactNumber(claims)} findings">
          <strong>${escapeHtml(entry.label)}</strong>
          <em>${formatCompactNumber(studies)}</em>
        </button>
      `;
    })
    .join("");

  return trendCardHtml(title, "", `<div class="scale-chip-grid">${chips}</div>`, options.extraClass || "");
}

function renderFacetCompositionChart(entries, title, filterField, options = {}) {
  if (!entries.length) {
    if (options.hideWhenEmpty) return "";
    return trendCardHtml(
      title,
      "",
      `<div class="trend-empty">${escapeHtml(options.emptyText || "No metadata in this selection.")}</div>`,
      "metadata-composition-card"
    );
  }

  const valueKey = options.valueKey || "studies";
  const preparedEntries = entries
    .map((entry) => {
      const claims = Number(entry.claims ?? entry.count ?? 0) || 0;
      const studies = Number(entry.studies ?? claims) || 0;
      return {
        label: entry.label,
        value: entry.value || entry.label,
        displayLabel: entry.displayLabel || entry.label,
        count: claims,
        studies,
      };
    })
    .filter((entry) => entry.studies || entry.count);
  const rankedEntries = sortEntriesByValue(preparedEntries, valueKey, options.order || []);
  const maxEntries = options.maxEntries || 7;
  const displayEntries =
    options.aggregateOther === false && rankedEntries.length > maxEntries
      ? rankedEntries.slice(0, maxEntries)
      : limitCompositionEntries(rankedEntries, maxEntries);
  const limitedEntries = displayEntries.map((entry) =>
    entry.isAggregate ? { ...entry, displayLabel: options.aggregateLabel || "Other" } : entry
  );
  const total = limitedEntries.reduce((sum, entry) => sum + (Number(entry[valueKey]) || 0), 0);
  if (!total) {
    if (options.hideWhenEmpty) return "";
    return trendCardHtml(
      title,
      "",
      `<div class="trend-empty">${escapeHtml(options.emptyText || "No metadata in this selection.")}</div>`,
      "metadata-composition-card"
    );
  }

  const palette = options.palette || CATEGORY_COLORS;
  const colorsForEntry = (entry, index) => {
    const color = colorForEntry(entry, index, palette);
    return {
      fill: chartFillSoft(color, isOtherEntry(entry) ? 0.82 : 0.9),
      glow: chartFillSoft(color, isOtherEntry(entry) ? 0.17 : 0.3),
    };
  };
  const segments = limitedEntries
    .map((entry, index) => {
      const value = Number(entry[valueKey]) || 0;
      const width = (value / total) * 100;
      const label = entry.displayLabel || entry.label;
      const colors = colorsForEntry(entry, index);
      return `<span class="trend-stack-segment${compositionTargetClass(entry)}" ${compositionFilterAttrs(
        entry,
        filterField
      )} style="width: ${width.toFixed(2)}%; --bar-fill: ${colors.fill}; --bar-glow: ${colors.glow}; background: var(--bar-fill)" title="${escapeHtml(
        `${label}: ${formatCompactNumber(entry.studies)} studies, ${formatCompactNumber(entry.count)} findings`
      )}"></span>`;
    })
    .join("");
  const legend = limitedEntries
    .map((entry, index) => {
      const value = Number(entry[valueKey]) || 0;
      const label = entry.displayLabel || entry.label;
      const colors = colorsForEntry(entry, index);
      return `
        <span class="trend-legend-item${compositionTargetClass(entry)}" ${compositionFilterAttrs(entry, filterField)}>
          <i style="--bar-fill: ${colors.fill}; --bar-glow: ${colors.glow}; background: var(--bar-fill)"></i>
          ${escapeHtml(label)} <strong>${formatCompactNumber(value)}</strong>
        </span>
      `;
    })
    .join("");

  return trendCardHtml(
    title,
    "",
    `
      <div class="metadata-composition">
        <div class="trend-stack">${segments}</div>
        <div class="trend-legend">${legend}</div>
      </div>
    `,
    "metadata-composition-card"
  );
}

function hasRegisteredTrial(items) {
  return items.some((claim) => trialRegistrationFacetLabel(claim) === "Registered trial");
}

function renderMetadataFacetCharts(items) {
  const profile = currentDetailPanelProfile();
  const shouldShowTrialRegistration = evidenceView === "primary" && profile.trialRegistration && hasRegisteredTrial(items);
  const trialEntries = shouldShowTrialRegistration
    ? summarizeFacetEvidence(items, trialRegistrationFacetLabel).filter(
        (entry) => normalizeValue(entry.label) === "registered trial"
      )
    : [];
  const trialRegistrationChart =
    trialEntries.length
      ? renderFacetChipChart(trialEntries, "Trial registration", "trial_registration_facet", {
          order: ["Registered trial"],
          extraClass: "chip-tone-pink",
          emptyText: "No trial-registration metadata in this selection.",
        })
      : "";

  return `
    ${trialRegistrationChart}
    ${renderAuthorRoleChart(items)}
    ${renderJournalChart(items)}
  `;
}

function renderAuthorRoleChart(items) {
  const entries = summarizeAuthorRoleEvidence(items);
  if (!entries.length) {
    return trendCardHtml("Authors", "", '<div class="trend-empty">No author metadata in this selection.</div>');
  }

  const maxEntries = 10;
  const visibleEntries = entries.slice(0, maxEntries);
  const rows = visibleEntries
    .map((entry) => {
      const studiesLabel = `${formatCompactNumber(entry.studies)} stud${entry.studies === 1 ? "y" : "ies"}`;
      const title = `${entry.label}: ${formatCompactNumber(
        entry.studies
      )} studies; first author in ${formatCompactNumber(entry.firstStudies)}, last author in ${formatCompactNumber(
        entry.lastStudies
      )}`;
      return `
        <div class="author-rank-row interactive-bar" role="button" tabindex="0"
          data-filter-field="author_role"
          data-filter-value="${escapeHtml(entry.value)}"
          data-filter-label="${escapeHtml(entry.label)}"
          data-study-count="${escapeHtml(String(entry.studies))}"
          data-claim-count="${escapeHtml(String(entry.claims))}"
          title="${escapeHtml(title)}">
          <div class="author-rank-main">
            <span>${escapeHtml(entry.label)}</span>
            <strong>${escapeHtml(studiesLabel)}</strong>
          </div>
          <div class="author-role-counts">
            <span>First author <b>${formatCompactNumber(entry.firstStudies)}</b></span>
            <span>Last author <b>${formatCompactNumber(entry.lastStudies)}</b></span>
          </div>
        </div>
      `;
    })
    .join("");

  return trendCardHtml("Authors", "", `<div class="author-rank-list">${rows}</div>`, "author-role-card");
}

function renderJournalChart(items) {
  const journalEntries = summarizeFacetEvidence(items, journalFacetValue);
  return renderHorizontalBarChart(journalEntries, "Journals", "", {
    filterField: "study_journal",
    emptyText: "No journal metadata in this selection.",
    expandKey: "journals",
    maxEntries: 10,
    extraClass: "bar-tone-gray",
  });
}

function renderMechanisticAssayFamilyChart(items) {
  if (evidenceView !== "primary" || !currentDetailPanelProfile().assayFamilies) return "";
  const assayEntries = summarizeFacetEvidence(items, mechanisticAssayFamilyFacetLabel);
  return renderFacetCompositionChart(assayEntries, "Assay families", "assay_family_facet", {
    hideWhenEmpty: true,
    order: MECHANISTIC_ASSAY_FAMILY_ORDER,
    maxEntries: 12,
    palette: PALETTE_BLUE_FIRST,
    emptyText: "No assay-family metadata in this selection.",
  });
}

function renderBrainMeasureChart(items) {
  if (evidenceView !== "primary" || !currentDetailPanelProfile().brainMeasures) return "";
  const measureEntries = summarizeMultiFacetEvidence(items, brainMeasureFacetLabels);
  return renderFacetCompositionChart(measureEntries, "Measures", "brain_measure_facet", {
    hideWhenEmpty: true,
    order: BRAIN_MEASURE_ORDER,
    maxEntries: 12,
    palette: PALETTE_BLUE_FIRST,
    emptyText: "No neural-measure metadata in this selection.",
  });
}

function renderMechanisticRelationshipTypeChart(items) {
  if (evidenceView !== "primary" || !currentDetailPanelProfile().mechanisticRelationshipTypes) return "";
  const relationshipEntries = summarizeFacetEvidence(items, mechanisticRelationshipTypeFacetLabel);
  return renderFacetCompositionChart(relationshipEntries, "Relationship types", "mechanistic_relationship_type_facet", {
    hideWhenEmpty: true,
    order: MECHANISTIC_RELATIONSHIP_TYPE_ORDER,
    maxEntries: 9,
    palette: PALETTE_TEAL_FIRST,
    emptyText: "No relationship-type metadata in this selection.",
  });
}

function renderSafetyContextChart(items) {
  if (evidenceView !== "primary" || !currentDetailPanelProfile().safetyContexts) return "";
  const contextEntries = summarizeFacetEvidence(items, safetyContextFacetLabel);
  return renderFacetCompositionChart(contextEntries, "Safety context", "safety_context_facet", {
    hideWhenEmpty: true,
    order: SAFETY_CONTEXT_ORDER,
    maxEntries: 7,
    palette: PALETTE_ROSE_FIRST,
    emptyText: "No safety-context metadata in this selection.",
  });
}

function renderDoseRouteSessionContextChart(items) {
  if (evidenceView !== "primary" || !currentDetailPanelProfile().doseRouteSessionContexts) return "";
  const contextEntries = summarizeMultiFacetEvidence(items, doseRouteSessionFacetLabels);
  return renderFacetCompositionChart(contextEntries, "Administration context", "dose_route_session_facet", {
    hideWhenEmpty: true,
    order: DOSE_ROUTE_SESSION_CONTEXT_ORDER,
    maxEntries: 12,
    palette: PALETTE_TEAL_FIRST,
    emptyText: "No administration-context metadata in this selection.",
  });
}

function renderClinicalComparatorChart(items) {
  if (evidenceView !== "primary" || !currentDetailPanelProfile().comparators) return "";
  const comparatorEntries = summarizeFacetEvidence(items, clinicalComparatorFacetLabel);
  return renderFacetCompositionChart(comparatorEntries, "Comparators", "comparator_facet", {
    hideWhenEmpty: true,
    order: CLINICAL_COMPARATOR_ORDER,
    maxEntries: 10,
    palette: PALETTE_BLUE_FIRST,
    emptyText: "No comparator metadata in this selection.",
  });
}

function renderClinicalFollowUpWindowChart(items) {
  if (evidenceView !== "primary" || !currentDetailPanelProfile().followUpWindows) return "";
  const followUpEntries = summarizeFacetEvidence(items, clinicalFollowUpWindowFacetLabel);
  return renderFacetCompositionChart(followUpEntries, "Follow-up windows", "follow_up_window_facet", {
    hideWhenEmpty: true,
    order: CLINICAL_FOLLOW_UP_WINDOW_ORDER,
    maxEntries: 10,
    palette: PALETTE_TEAL_FIRST,
    emptyText: "No follow-up window metadata in this selection.",
  });
}

function renderPublicHealthTopicChart(items) {
  if (evidenceView !== "primary" || !currentDetailPanelProfile().publicHealthTopics) return "";
  const topicEntries = summarizeFacetEvidence(items, publicHealthTopicFacetLabel);
  return renderFacetCompositionChart(topicEntries, "Real-world topics", "public_health_topic_facet", {
    hideWhenEmpty: true,
    order: PUBLIC_HEALTH_TOPIC_ORDER,
    maxEntries: 8,
    palette: CATEGORY_COLORS,
    emptyText: "No real-world topic metadata in this selection.",
  });
}

function renderPublicHealthContextChart(items) {
  if (evidenceView !== "primary" || !currentDetailPanelProfile().publicHealthContexts) return "";
  const contextEntries = summarizeMultiFacetEvidence(items, publicHealthUseContextFacetLabels);
  return renderFacetCompositionChart(contextEntries, "Use contexts", "public_health_context_facet", {
    hideWhenEmpty: true,
    order: PUBLIC_HEALTH_CONTEXT_ORDER,
    maxEntries: 8,
    palette: PALETTE_TEAL_FIRST,
    emptyText: "No real-world use-context metadata in this selection.",
  });
}

function renderPublicHealthDataSourceChart(items) {
  if (evidenceView !== "primary" || !currentDetailPanelProfile().publicHealthDataSources) return "";
  const sourceEntries = summarizeFacetEvidence(items, publicHealthDataSourceFacetLabel);
  return renderFacetCompositionChart(sourceEntries, "Data sources", "public_health_data_source_facet", {
    hideWhenEmpty: true,
    order: PUBLIC_HEALTH_DATA_SOURCE_ORDER,
    maxEntries: 8,
    palette: PALETTE_BLUE_FIRST,
    emptyText: "No data-source metadata in this selection.",
  });
}

function renderReviewContextCharts(items) {
  if (!isReviewEvidenceView()) return "";
  const designEntries = summarizeFacetEvidence(items, reviewDesignFacetLabel);
  const contributionEntries = summarizeFacetEvidence(items, reviewContributionFacetLabel);
  const evidenceEntries = summarizeFacetEvidence(items, reviewEvidenceStratumFacetLabel);
  const relationshipEntries = summarizeFacetEvidence(items, reviewRelationshipTypeFacetLabel);
  const coverageFocusEntries = summarizeFacetEvidence(items, reviewCoverageFocusFacetLabel);

  const chart = (entries, title, filterField, options = {}) =>
    entries.length
      ? renderFacetCompositionChart(entries, title, filterField, {
          hideWhenEmpty: true,
          maxEntries: options.maxEntries || 10,
          aggregateOther: false,
          palette: options.palette || CATEGORY_COLORS,
        })
      : "";

  return `
    ${chart(designEntries, "Review approaches", "review_design_facet")}
    ${chart(contributionEntries, "Overall review focus", "review_contribution_facet", { maxEntries: 7 })}
    ${chart(evidenceEntries, "Evidence base", "review_evidence_stratum_facet", { maxEntries: 5 })}
    ${chart(relationshipEntries, "Relationship types", "review_relationship_type_facet", { maxEntries: 5 })}
    ${coverageFocusEntries.length ? renderFacetCompositionChart(
      orderedFacetEntries(coverageFocusEntries, REVIEW_COVERAGE_FOCUS_ORDER),
      "Coverage within each paper",
      "review_coverage_focus_facet",
      { hideWhenEmpty: true, maxEntries: 3, aggregateOther: false, palette: PALETTE_TEAL_FIRST }
    ) : ""}
  `;
}

function isNetworkMetaAnalysisClaim(claim) {
  return (
    normalizeValue(claim.paper_type || claim.source_type).replace(/\s+/g, "_") === "network_meta_analysis" ||
    /\bnetwork meta[- ]analysis\b/.test(normalizeValue(claim.publication_type || claim.study_design))
  );
}

function metaAnalysisDesignFacetLabel(claim) {
  const values = meaningfulText(claim.study_design)
    .split(/\s*;\s*/)
    .map((value) => normalizeValue(value).replace(/\s+/g, "_"))
    .filter(Boolean);
  if (isNetworkMetaAnalysisClaim(claim) || values.includes("network_meta_analysis")) {
    return "Network meta-analysis";
  }
  const key = values.find((value) => META_ANALYSIS_DESIGN_LABELS[value]);
  return key ? META_ANALYSIS_DESIGN_LABELS[key] : "Other quantitative synthesis";
}

function metaAnalysisResultRoleFacetLabel(claim) {
  const key = normalizeValue(claim.meta_analysis_result_role).replace(/\s+/g, "_");
  return META_ANALYSIS_RESULT_ROLE_LABELS[key] || "Other analysis";
}

function metaAnalysisStudyCountFacetLabel(claim) {
  const value = claim.meta_analysis_overall_study_count || claim.meta_analysis_study_count;
  const count = parseSampleSize(value);
  if (count === null) return "";
  return META_ANALYSIS_STUDY_COUNT_BINS.find((bin) => count >= bin.min && count <= bin.max)?.label || "";
}

function renderMetaAnalysisContextCharts(items) {
  if (evidenceView !== "meta_analyses") return "";
  const chart = (entries, title, filterField, options = {}) =>
    entries.length
      ? renderFacetCompositionChart(entries, title, filterField, {
          hideWhenEmpty: true,
          maxEntries: options.maxEntries || 12,
          aggregateOther: false,
          order: options.order || [],
          palette: options.palette || CATEGORY_COLORS,
        })
      : "";

  return `
    ${chart(summarizeFacetEvidence(items, metaAnalysisDesignFacetLabel), "Synthesis designs", "meta_analysis_design_facet", {
      order: META_ANALYSIS_DESIGN_ORDER,
      palette: PALETTE_GOLD_FIRST,
    })}
    ${chart(summarizeFacetEvidence(items, clinicalComparatorFacetLabel), "Comparators", "comparator_facet", {
      order: CLINICAL_COMPARATOR_ORDER,
      palette: PALETTE_BLUE_FIRST,
    })}
    ${chart(summarizeFacetEvidence(items, clinicalFollowUpWindowFacetLabel), "Follow-up windows", "follow_up_window_facet", {
      order: CLINICAL_FOLLOW_UP_WINDOW_ORDER,
      palette: PALETTE_TEAL_FIRST,
    })}
    ${chart(summarizeFacetEvidence(items, metaAnalysisStudyCountFacetLabel), "Studies included", "meta_analysis_study_count_facet", {
      order: META_ANALYSIS_STUDY_COUNT_BINS.map((bin) => bin.label),
      palette: PALETTE_GOLD_FIRST,
    })}
  `;
}

function renderEvidenceCompositionFacetCharts(items) {
  if (evidenceView !== "primary") return "";
  const profile = currentDetailPanelProfile();

  const populationModelEntries = profile.populationModel ? summarizeFacetEvidence(items, populationModelFacetLabel) : [];
  const designEntries = profile.studyDesigns ? summarizeFacetEvidence(items, studyDesignFacetLabel) : [];

  return `
    ${renderPublicHealthDataSourceChart(items)}
    ${renderPublicHealthContextChart(items)}
    ${renderPublicHealthTopicChart(items)}
    ${renderSafetyContextChart(items)}
    ${renderDoseRouteSessionContextChart(items)}
    ${
      profile.populationModel
        ? renderFacetCompositionChart(populationModelEntries, "Population", "population_model_facet", {
            hideWhenEmpty: true,
            order: POPULATION_MODEL_ORDER,
            maxEntries: 15,
            palette: PALETTE_SAGE_FIRST,
          })
        : ""
    }
    ${renderClinicalComparatorChart(items)}
    ${renderClinicalFollowUpWindowChart(items)}
    ${renderMechanisticRelationshipTypeChart(items)}
    ${renderBrainMeasureChart(items)}
    ${renderMechanisticAssayFamilyChart(items)}
    ${
      profile.studyDesigns
        ? renderFacetCompositionChart(designEntries, "Study designs", "study_design_facet", {
            hideWhenEmpty: true,
            order: STUDY_DESIGN_ORDER,
            maxEntries: 12,
            palette: PALETTE_GOLD_FIRST,
            emptyText: "No study-design metadata in this selection.",
          })
        : ""
    }
  `;
}

function summarizeOutcomeScaleEvidence(items) {
  const map = new Map();

  items.forEach((claim, index) => {
    const labels = outcomeScaleLabelsForClaim(claim);
    if (!labels.length) return;
    const study = studyKey(claim, index);
    labels.forEach((label) => {
      const entry = map.get(label) || { label, count: 0, studies: new Set() };
      entry.count += 1;
      entry.studies.add(study);
      map.set(label, entry);
    });
  });

  return Array.from(map.values())
    .map((entry) => ({
      label: entry.label,
      count: entry.count,
      studies: entry.studies.size,
    }))
    .sort((a, b) => {
      const byStudies = b.studies - a.studies;
      if (byStudies !== 0) return byStudies;
      const byCount = b.count - a.count;
      if (byCount !== 0) return byCount;
      return a.label.localeCompare(b.label);
    });
}

function aggregateSparseOutcomeScaleEntries(entries, maxStudiesForOther = 3) {
  const commonEntries = [];
  const sparseEntries = [];

  entries.forEach((entry) => {
    const studies = Number(entry.studies || 0);
    if (studies > 0 && studies <= maxStudiesForOther) {
      sparseEntries.push(entry);
    } else {
      commonEntries.push(entry);
    }
  });

  if (!sparseEntries.length) return commonEntries;

  return [
    ...commonEntries,
    {
      label: "other",
      value: "other",
      displayLabel: "Other",
      count: sparseEntries.reduce((sum, entry) => sum + (Number(entry.count) || 0), 0),
      studies: sparseEntries.reduce((sum, entry) => sum + (Number(entry.studies) || 0), 0),
      isAggregate: true,
    },
  ];
}

function summarizeSampleSizeBuckets(items) {
  const bins = sampleSizeBinsForItems(items);
  const bucketOrder = bins.map((bin) => bin.label);
  const buckets = new Map(bucketOrder.map((label) => [label, new Set()]));

  items.forEach((claim, index) => {
    const bucket = sampleSizeBucket(claim.sample_size_total, bins);
    if (!bucket) return;
    buckets.get(bucket)?.add(studyKey(claim, index));
  });

  return bucketOrder
    .map((label) => ({ label, count: buckets.get(label)?.size || 0 }))
    .filter((entry) => entry.count > 0);
}

function sampleSizeStudyEntries(items) {
  const byStudy = new Map();
  items.forEach((claim, index) => {
    const sampleSize = parseSampleSize(sampleSizeText(claim));
    const year = parseYearValue(claim.study_year);
    if (sampleSize === null || year === null) return;
    const key = studyKey(claim, index);
    const existing = byStudy.get(key);
    const relation = `${claim.compound || "Unknown"} -> ${claim.disorder || "Unknown"}`;

    if (!existing) {
      byStudy.set(key, {
        key,
        sampleSize,
        sampleText: sampleSizeText(claim) || String(sampleSize),
        year,
        label: relation,
        studyTitle: cleanDisplayText(claim.study_title) || "Unknown study",
        claimCount: 1,
        relations: new Set([relation]),
      });
      return;
    }

    existing.claimCount += 1;
    existing.relations.add(relation);
    if (existing.sampleSize < sampleSize) {
      existing.sampleSize = sampleSize;
      existing.sampleText = sampleSizeText(claim) || String(sampleSize);
      existing.label = relation;
    }
  });
  return Array.from(byStudy.values())
    .map((entry) => ({
      ...entry,
      relationSummary: Array.from(entry.relations).slice(0, 3).join("; "),
    }))
    .sort((a, b) => {
      const byYear = a.year - b.year;
      if (byYear !== 0) return byYear;
      const bySampleSize = b.sampleSize - a.sampleSize;
      if (bySampleSize !== 0) return bySampleSize;
      return a.label.localeCompare(b.label);
    });
}

function sampleYearBucketStep(minYear, maxYear) {
  const span = maxYear - minYear + 1;
  return Math.max(1, Math.ceil(span / SAMPLE_YEAR_TARGET_BUCKET_COUNT));
}

function sampleYearBuckets(minYear, maxYear) {
  const step = sampleYearBucketStep(minYear, maxYear);
  const startYear = Math.floor(minYear / step) * step;
  const buckets = [];
  for (let start = startYear; start <= maxYear; start += step) {
    const end = Math.min(start + step - 1, maxYear);
    buckets.push({
      start,
      end,
      label: start === end ? String(start) : `${start}-${end}`,
    });
  }
  return buckets;
}

function countByField(items, field, options = {}) {
  const counts = new Map();
  const studySeen = new Set();
  const studiesByValue = new Map();

  items.forEach((claim, index) => {
    const value = normalizeValue(claim[field]) || "unknown";
    const study = studyKey(claim, index);
    if (options.uniqueStudies) {
      const key = `${study}|${value}`;
      if (studySeen.has(key)) return;
      studySeen.add(key);
    }
    if (!studiesByValue.has(value)) studiesByValue.set(value, new Set());
    studiesByValue.get(value).add(study);
    counts.set(value, (counts.get(value) || 0) + 1);
  });

  return Array.from(counts.entries()).map(([label, count]) => ({
    label,
    count,
    studies: studiesByValue.get(label)?.size || count,
  }));
}

function sortCompositionEntries(entries, field) {
  const orders = {
    system: ["clinical", "preclinical", "in_vitro", "in_vivo", "ex_vivo", "observational", "unknown"],
  };
  const order = orders[field] || [];
  return sortEntriesByValue(entries, "count", order);
}

function limitCompositionEntries(entries, maxEntries = 5) {
  if (entries.length <= maxEntries) return entries;
  const visible = entries.slice(0, maxEntries - 1);
  const otherCount = entries.slice(maxEntries - 1).reduce((sum, entry) => sum + entry.count, 0);
  const otherStudies = entries.slice(maxEntries - 1).reduce((sum, entry) => sum + (entry.studies || 0), 0);
  return [...visible, { label: "other", count: otherCount, studies: otherStudies, isAggregate: true }];
}

function colorForEntry(entry, index, palette = CATEGORY_COLORS) {
  return isOtherEntry(entry) ? OTHER_CATEGORY_COLOR : palette[index % palette.length];
}

function compositionFilterAttrs(entry, field) {
  if (!field || !entry?.label || entry.isAggregate) return "";
  const label = entry.displayLabel || displayFieldLabel(entry.label);
  const filterValue = entry.value || entry.label;
  const studies = Number(entry.studies ?? entry.count ?? 0) || 0;
  const claims = Number(entry.count ?? studies) || 0;
  return `role="button" tabindex="0" data-filter-field="${escapeHtml(field)}" data-filter-value="${escapeHtml(
    filterValue
  )}" data-filter-label="${escapeHtml(label)}" data-study-count="${escapeHtml(String(studies))}" data-claim-count="${escapeHtml(
    String(claims)
  )}" aria-label="${escapeHtml(`${label}: ${studies} studies, ${claims} findings`)}"`;
}

function compositionTargetClass(entry) {
  return entry?.isAggregate ? "" : " composition-filter-target";
}

/** Overview trend charts (#rrggbb only): soften fills while keeping a slight luminous edge in the dark UI. */
function chartFillSoft(hexColor, alpha = 0.88) {
  const s = (hexColor || "").trim();
  if (!s.startsWith("#")) return s;
  const hex = s.slice(1);
  let r;
  let g;
  let b;
  if (hex.length === 6) {
    r = parseInt(hex.slice(0, 2), 16);
    g = parseInt(hex.slice(2, 4), 16);
    b = parseInt(hex.slice(4, 6), 16);
  } else if (hex.length === 3) {
    r = parseInt(hex.slice(0, 1).repeat(2), 16);
    g = parseInt(hex.slice(1, 2).repeat(2), 16);
    b = parseInt(hex.slice(2, 3).repeat(2), 16);
  } else {
    return s;
  }
  if ([r, g, b].some((n) => Number.isNaN(n))) return s;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function trendCardHtml(title, subtitle, body, extraClass = "") {
  const className = ["trend-card", extraClass].filter(Boolean).join(" ");
  return `
    <section class="${escapeHtml(className)}">
      <div class="trend-card-header">
        <h4>${escapeHtml(title)}</h4>
        ${subtitle ? `<span>${escapeHtml(subtitle)}</span>` : ""}
      </div>
      ${body}
    </section>
  `;
}

function accessSummaryLabels() {
  if (evidenceView === "meta_analyses") {
    return { all: "All meta-analyses", plural: "meta-analyses" };
  }
  if (isReviewEvidenceView()) {
    return { all: "All reviews", plural: "reviews" };
  }
  return { all: "All studies", plural: "studies" };
}

function renderTrendStats(
  items,
  extraStats = [],
  allAccessItems = activeDetailAllAccessItems.length ? activeDetailAllAccessItems : items
) {
  const allItems = allAccessItems;
  const allStudyCount = uniqueStudyCount(allItems);
  const openAccessStudyCount = uniqueStudyCount(allItems.filter(isOpenAccessClaim));
  const openAccessPercent = allStudyCount ? Math.round((openAccessStudyCount / allStudyCount) * 100) : 0;
  const labels = accessSummaryLabels();
  const stats = extraStats;

  return `
    <div class="trend-summary-grid">
      <button
        class="trend-stat trend-stat-access ${accessView === "all" ? "active" : ""}"
        type="button"
        data-access-view="all"
        aria-pressed="${accessView === "all" ? "true" : "false"}"
        aria-label="Show all ${escapeHtml(labels.plural)}. ${formatCompactNumber(allStudyCount)} available."
      >
        <span>${escapeHtml(labels.all)}</span>
        <strong>${formatCompactNumber(allStudyCount)}</strong>
      </button>
      <button
        class="trend-stat trend-stat-access ${accessView === "open" ? "active" : ""}"
        type="button"
        data-access-view="open"
        aria-pressed="${accessView === "open" ? "true" : "false"}"
        aria-label="Show open access ${escapeHtml(labels.plural)}. ${formatCompactNumber(
          openAccessStudyCount
        )}, ${openAccessPercent}% of ${escapeHtml(labels.plural)}."
      >
        <span>Open access</span>
        <strong>${formatCompactNumber(openAccessStudyCount)}</strong>
        <small>${openAccessPercent}% of ${escapeHtml(labels.plural)}</small>
      </button>
      ${stats
        .map(
          (stat) => `
            <div class="trend-stat">
              <span>${escapeHtml(stat.label)}</span>
              <strong>${escapeHtml(stat.value)}</strong>
            </div>
          `
        )
        .join("")}
    </div>
  `;
}

function renderAnnualPublicationChart(items) {
  const buckets = buildYearBuckets(items);
  if (!buckets.length) {
    return trendCardHtml("Publications per year", "", '<div class="trend-empty">No publication years available.</div>');
  }

  const recordLabels = recordLabelsForItems(items);
  const width = 280;
  const height = 132;
  const margin = { top: 12, right: 10, bottom: 24, left: 10 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const maxCount = Math.max(1, ...buckets.map((bucket) => bucket.count));
  const slotWidth = plotWidth / buckets.length;
  const barWidth = Math.max(3, Math.min(16, slotWidth * 0.68));
  const step = buckets.length > 1 ? (plotWidth - barWidth) / (buckets.length - 1) : 0;
  const bars = buckets
    .map((bucket, index) => {
      if (!bucket.count) return "";
      const x = buckets.length > 1 ? margin.left + index * step : margin.left + (plotWidth - barWidth) / 2;
      const barHeight = (bucket.count / maxCount) * plotHeight;
      const y = margin.top + plotHeight - barHeight;
      const hitWidth = Math.max(12, Math.min(step, barWidth + 10));
      const hitX = clampNumber(x - (hitWidth - barWidth) / 2, margin.left, width - margin.right - hitWidth);
      const ariaRecordLabel = bucket.claims === 1 ? recordLabels.lowerSingular : recordLabels.lowerPlural;
      const aria = `${bucket.label}. ${bucket.count} studies. Open ${bucket.claims} ${ariaRecordLabel}.`;
      return `
        <g class="publication-year-target" tabindex="0" role="button" focusable="true"
          aria-label="${escapeHtml(aria)}"
          data-year-start="${escapeHtml(String(bucket.start))}"
          data-year-end="${escapeHtml(String(bucket.end))}"
          data-year-label="${escapeHtml(bucket.label)}"
          data-study-count="${escapeHtml(String(bucket.count))}"
          data-claim-count="${escapeHtml(String(bucket.claims))}"
          data-record-label="${escapeHtml(recordLabels.lowerPlural)}"
          data-record-singular="${escapeHtml(recordLabels.lowerSingular)}">
          <rect class="publication-year-hit" x="${hitX.toFixed(2)}" y="${margin.top}" width="${hitWidth.toFixed(2)}" height="${plotHeight}" rx="3"></rect>
          <rect class="publication-year-bar" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${barWidth.toFixed(2)}" height="${barHeight.toFixed(2)}" rx="2" fill="${chartFillSoft(
            PUBLICATION_YEAR_COLOR,
            0.92
          )}"></rect>
        </g>
      `;
    })
    .join("");
  const firstLabel = buckets[0].label;
  const lastLabel = buckets[buckets.length - 1].label;

  return trendCardHtml(
    "Publications per year",
    "",
    `
      <svg class="trend-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Publications per year">
        <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" class="trend-axis-line" />
        ${bars}
        <text x="${margin.left}" y="${height - 5}" class="trend-axis-label" text-anchor="start">${escapeHtml(firstLabel)}</text>
        <text x="${width - margin.right}" y="${height - 5}" class="trend-axis-label" text-anchor="end">${escapeHtml(lastLabel)}</text>
      </svg>
    `
  );
}

function renderHorizontalBarChart(entries, title, subtitle, options = {}) {
  if (!entries.length) {
    return trendCardHtml(
      title,
      subtitle,
      `<div class="trend-empty">${escapeHtml(options.emptyText || "No connected evidence in this selection.")}</div>`
    );
  }

  const valueKey = options.valueKey || "studies";
  const maxEntries = Number(options.maxEntries) || entries.length;
  const expandKey = options.expandKey || "";
  const rankedEntries = sortEntriesByValue(entries, valueKey);
  const canExpand = Boolean(expandKey && rankedEntries.length > maxEntries);
  const isExpanded = canExpand && expandedChartKeys.has(expandKey);
  const visibleEntries = canExpand && !isExpanded ? rankedEntries.slice(0, maxEntries) : rankedEntries;
  const maxValue = Math.max(1, ...rankedEntries.map((entry) => Number(entry[valueKey]) || 0));
  const expandControl = canExpand
    ? `
      <div class="trend-chart-actions">
        <button class="chart-expand-toggle" type="button"
          data-chart-expand-key="${escapeHtml(expandKey)}"
          aria-expanded="${escapeHtml(String(isExpanded))}">
          ${isExpanded ? `Show top ${formatCompactNumber(maxEntries)}` : `Show all ${formatCompactNumber(rankedEntries.length)}`}
        </button>
      </div>
    `
    : "";
  const body = `
    <div class="trend-bars">
      ${visibleEntries
        .map((entry, index) => {
          const value = Number(entry[valueKey]) || 0;
          const width = Math.max(4, (value / maxValue) * 100);
          const claims = Number(entry.claims ?? entry.count ?? value) || 0;
          const studies = Number(entry.studies ?? value) || 0;
          const filterValue = entry.value || entry.label;
          const isInteractive = Boolean(options.filterField && entry.label);
          const rowClass = ["trend-bar-row", isInteractive ? "interactive-bar" : ""].filter(Boolean).join(" ");
          const interactiveAttrs = isInteractive
            ? `role="button" tabindex="0" data-filter-field="${escapeHtml(options.filterField)}" data-filter-value="${escapeHtml(
                filterValue
              )}" data-filter-label="${escapeHtml(entry.label)}" data-study-count="${escapeHtml(
                String(studies)
              )}" data-claim-count="${escapeHtml(String(claims))}"`
            : "";
          return `
            <div class="${escapeHtml(rowClass)}" style="--bar-width: ${width.toFixed(2)}%" ${interactiveAttrs}>
              <div class="trend-bar-topline">
                <span title="${escapeHtml(entry.label)}">${escapeHtml(entry.label)}</span>
                <strong>${formatCompactNumber(value)}</strong>
              </div>
              <div class="trend-bar-track"><span></span></div>
            </div>
          `;
        })
        .join("")}
    </div>
    ${expandControl}
  `;

  return trendCardHtml(title, subtitle, body, options.extraClass || "");
}

function renderOutcomeMeasureChart(items) {
  if (evidenceView !== "primary") return "";
  if (!currentDetailPanelProfile().outcomeScales) return "";
  const scaleItems = outcomeScaleClaimsForChart(items);
  const entries = aggregateSparseOutcomeScaleEntries(summarizeOutcomeScaleEvidence(scaleItems), 3);
  return renderFacetCompositionChart(entries, "Outcome scales", "outcome_scale_facet", {
    hideWhenEmpty: true,
    maxEntries: Math.max(entries.length, 1),
    aggregateOther: false,
    palette: PALETTE_BLUE_FIRST,
    emptyText: "No outcome-scale metadata in this selection.",
  });
}

function renderSampleSizePlotBody(items) {
  const entries = sampleSizeStudyEntries(items);
  if (!entries.length) {
    return '<div class="trend-empty">No sample sizes with publication years available.</div>';
  }

  const width = 280;
  const height = 156;
  const margin = { top: 8, right: 8, bottom: 19, left: 48 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const minYear = Math.min(...entries.map((entry) => entry.year));
  const maxYear = Math.max(...entries.map((entry) => entry.year));
  const yearBuckets = sampleYearBuckets(minYear, maxYear);
  const sizeBins = [...sampleSizeBinsForItems(items)].reverse();
  const gap = 2;
  const cellWidth = Math.max(4, (plotWidth - gap * (yearBuckets.length - 1)) / yearBuckets.length);
  const cellHeight = Math.max(7, (plotHeight - gap * (sizeBins.length - 1)) / sizeBins.length);
  const cells = new Map();

  entries.forEach((entry) => {
    const yearIndex = yearBuckets.findIndex((bucket) => entry.year >= bucket.start && entry.year <= bucket.end);
    const sizeBin = sampleSizeBinForSize(entry.sampleSize, sizeBins);
    if (yearIndex < 0 || !sizeBin) return;
    const key = `${yearIndex}|${sizeBin.label}`;
    const cell =
      cells.get(key) ||
      {
        yearIndex,
        yearBucket: yearBuckets[yearIndex],
        sizeBin,
        count: 0,
        claims: 0,
      };
    cell.count += 1;
    cell.claims += entry.claimCount;
    cells.set(key, cell);
  });

  const maxCount = Math.max(1, ...Array.from(cells.values()).map((cell) => cell.count));
  const heatmapCells = yearBuckets
    .flatMap((yearBucket, yearIndex) =>
      sizeBins.map((sizeBin, sizeIndex) => {
        const x = margin.left + yearIndex * (cellWidth + gap);
        const y = margin.top + sizeIndex * (cellHeight + gap);
        const cell = cells.get(`${yearIndex}|${sizeBin.label}`);
        if (!cell) {
          return `<rect class="sample-heatmap-cell empty" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${cellWidth.toFixed(
            2
          )}" height="${cellHeight.toFixed(2)}" rx="2"></rect>`;
        }
        const alpha = 0.16 + 0.76 * Math.sqrt(cell.count / maxCount);
        const maxValue = Number.isFinite(sizeBin.max) ? String(sizeBin.max) : "";
        const aria = `${yearBucket.label}, sample size ${sizeBin.label}: ${cell.count} studies, ${cell.claims} findings.`;
        return `
          <g class="sample-heatmap-target" tabindex="0" role="button" focusable="true"
            aria-label="${escapeHtml(aria)}"
            data-year-start="${escapeHtml(String(yearBucket.start))}"
            data-year-end="${escapeHtml(String(yearBucket.end))}"
            data-year-label="${escapeHtml(yearBucket.label)}"
            data-sample-min="${escapeHtml(String(sizeBin.min))}"
            data-sample-max="${escapeHtml(maxValue)}"
            data-sample-label="${escapeHtml(sizeBin.label)}"
            data-study-count="${escapeHtml(String(cell.count))}"
            data-claim-count="${escapeHtml(String(cell.claims))}">
            <rect class="sample-heatmap-hit" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${cellWidth.toFixed(
              2
            )}" height="${cellHeight.toFixed(2)}" rx="2"></rect>
            <rect class="sample-heatmap-cell" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${cellWidth.toFixed(
              2
            )}" height="${cellHeight.toFixed(2)}" rx="2" fill="${chartFillSoft(SAMPLE_SIZE_HEATMAP_COLOR, alpha)}"></rect>
          </g>
        `;
      })
    )
    .join("");
  const yLabels = sizeBins
    .map((bin, index) => {
      const y = margin.top + index * (cellHeight + gap) + cellHeight / 2 + 3;
      return `<text x="${margin.left - 7}" y="${y.toFixed(2)}" class="trend-axis-label" text-anchor="end">${escapeHtml(
        bin.label
      )}</text>`;
    })
    .join("");
  const firstYear = String(minYear);
  const lastYear = String(maxYear);

  return `
    <svg class="sample-heatmap-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Sample sizes by publication year">
      ${yLabels}
      ${heatmapCells}
      <text x="${margin.left}" y="${height - 5}" class="trend-axis-label" text-anchor="start">${escapeHtml(firstYear)}</text>
      <text x="${width - margin.right}" y="${height - 5}" class="trend-axis-label" text-anchor="end">${escapeHtml(lastYear)}</text>
    </svg>
  `;
}

function renderSampleSizeHeatmap(items) {
  if (evidenceView !== "primary") return "";
  if (!currentDetailPanelProfile().sampleSizes) return "";
  return trendCardHtml(
    "Sample sizes",
    "",
    renderSampleSizePlotBody(items),
    "evidence-card sample-card"
  );
}

function renderEvidenceDetailGroup(items) {
  return `
    ${renderExperimentalSystemChart(items)}
    ${renderSampleSizeHeatmap(items)}
    ${renderEvidenceCompositionFacetCharts(items)}
    ${renderOutcomeMeasureChart(items)}
    ${renderReviewContextCharts(items)}
    ${renderMetaAnalysisContextCharts(items)}
  `;
}

function renderExperimentalSystemChart(items) {
  if (evidenceView !== "primary") return "";
  if (!currentDetailPanelProfile().experimentalSystem) return "";
  const entries = sortCompositionEntries(countByField(items, "system"), "system").map((entry) => ({
    label: displayFieldLabel(entry.label),
    value: entry.label,
    claims: entry.count,
    studies: entry.studies,
  }));
  return renderFacetCompositionChart(entries, "Experimental system", "system", {
    emptyText: "No experimental-system metadata in this selection.",
    maxEntries: 6,
  });
}

function renderSpecificPathwayReadoutChart(items) {
  if (!usesPathwayReadoutFamilies()) return "";
  const entries = summarizeFacetEvidence(items, specificPathwayReadoutLabel);
  return renderFacetCompositionChart(entries, "Specific molecular findings", "specific_pathway_readout", {
    maxEntries: 15,
    aggregateLabel: "Other findings",
    palette: PALETTE_TEAL_FIRST,
    emptyText: "No specific labels in this selection.",
  });
}

function sampleHeatmapTooltipHtml(target) {
  const studyCount = Number(target.dataset.studyCount || 0);
  const claimCount = Number(target.dataset.claimCount || 0);
  return `
    <strong class="tooltip-title">${escapeHtml(target.dataset.yearLabel || "Unknown years")}</strong>
    <span class="tooltip-meta">N=${escapeHtml(target.dataset.sampleLabel || "unknown")} · ${formatCompactNumber(
      studyCount
    )} stud${studyCount === 1 ? "y" : "ies"} · ${formatCompactNumber(claimCount)} finding${
      claimCount === 1 ? "" : "s"
    }</span>
  `;
}

function publicationYearTooltipHtml(target) {
  const studyCount = Number(target.dataset.studyCount || 0);
  const claimCount = Number(target.dataset.claimCount || 0);
  const recordLabel =
    claimCount === 1 ? target.dataset.recordSingular || "finding" : target.dataset.recordLabel || "findings";
  return `
    <strong class="tooltip-title">${escapeHtml(target.dataset.yearLabel || "Unknown year")}</strong>
    <span class="tooltip-meta">${formatCompactNumber(studyCount)} stud${
      studyCount === 1 ? "y" : "ies"
    } · ${formatCompactNumber(claimCount)} ${escapeHtml(recordLabel)}</span>
  `;
}

function horizontalBarTooltipHtml(target) {
  const studyCount = Number(target.dataset.studyCount || 0);
  const claimCount = Number(target.dataset.claimCount || 0);
  return `
    <strong class="tooltip-title">${escapeHtml(target.dataset.filterLabel || "Unknown")}</strong>
    <span class="tooltip-meta">${formatCompactNumber(studyCount)} stud${
      studyCount === 1 ? "y" : "ies"
    } · ${formatCompactNumber(claimCount)} finding${claimCount === 1 ? "" : "s"}</span>
  `;
}

function claimsForStudyKey(studyKeyValue, items = activeDetailItems) {
  return items.filter((claim, index) => studyKey(claim, index) === studyKeyValue);
}

function claimsForFieldValue(field, value, items = activeDetailItems) {
  if (!field || !value) return [];
  const normalizedValue = normalizeValue(value);
  if (field === "author_role") {
    const labelValue = authorRoleLabelFromFilterValue(value);
    if (labelValue) {
      return items.filter((claim) =>
        ["first", "last"].some((role) => authorRoleLabelKey(authorRoleIdentity(claim, role).name) === labelValue)
      );
    }
    const authorAliases = buildAuthorRoleAliasMap(items);
    return items.filter((claim) =>
      ["first", "last"].some((role) => {
        const author = authorFacetValueForRole(claim, role, authorAliases);
        return normalizeValue(author.value) === normalizedValue || normalizeValue(author.label) === normalizedValue;
      })
    );
  }
  return items.filter((claim) => {
    const value = fieldValueForClaim(claim, field);
    if (Array.isArray(value)) return value.some((item) => normalizeValue(item) === normalizedValue);
    return normalizeValue(value) === normalizedValue;
  });
}

function fieldValueDetailTitle(field, value) {
  if (field === "compound") return `Compound: ${value}`;
  if (field === "disorder" || field === "target") return `${rightEntityLabel(false)}: ${value}`;
  if (field === "author_role") return `Author: ${value}`;
  if (field === "first_author") return `First author: ${value}`;
  if (field === "last_author") return `Last author: ${value}`;
  if (field === "study_journal") return `Journal: ${value}`;
  if (field === "specific_pathway_readout") return `Specific finding: ${value}`;
  if (field === "trial_registration_facet") return `Trial registration: ${value}`;
  if (field === "population_model_facet") return `Population: ${value}`;
  if (field === "assay_family_facet") return `Assay family: ${value}`;
  if (field === "brain_measure_facet") return `Measure: ${value}`;
  if (field === "mechanistic_relationship_type_facet") return `Relationship type: ${value}`;
  if (field === "safety_context_facet") return `Safety context: ${value}`;
  if (field === "dose_route_session_facet") return `Administration context: ${value}`;
  if (field === "comparator_facet") return `Comparator: ${value}`;
  if (field === "follow_up_window_facet") return `Follow-up window: ${value}`;
  if (field === "study_design_facet") return `Study design: ${value}`;
  if (field === "public_health_topic_facet") return `Real-world topic: ${value}`;
  if (field === "public_health_context_facet") return `Use context: ${value}`;
  if (field === "public_health_data_source_facet") return `Data source: ${value}`;
  if (field === "publication_type_facet") return `Publication type: ${value}`;
  if (field === "review_design_facet") return `Review approach: ${value}`;
  if (field === "review_contribution_facet") return `Overall review focus: ${value}`;
  if (field === "review_evidence_stratum_facet") return `Evidence base: ${value}`;
  if (field === "review_relationship_type_facet") return `Relationship type: ${value}`;
  if (field === "review_coverage_focus_facet") return `Coverage within paper: ${value}`;
  if (field === "meta_analysis_design_facet") return `Synthesis design: ${value}`;
  if (field === "meta_analysis_study_count_facet") return `Studies included: ${value}`;
  return `${displayFieldLabel(field)}: ${value}`;
}

function fieldValueForClaim(claim, field) {
  if (field === "trial_registration_facet") return trialRegistrationFacetLabel(claim);
  if (field === "population_model_facet") return populationModelFacetLabel(claim);
  if (field === "assay_family_facet") return mechanisticAssayFamilyFacetLabel(claim);
  if (field === "brain_measure_facet") return brainMeasureFacetLabels(claim);
  if (field === "mechanistic_relationship_type_facet") return mechanisticRelationshipTypeFacetLabel(claim);
  if (field === "safety_context_facet") return safetyContextFacetLabel(claim);
  if (field === "dose_route_session_facet") return doseRouteSessionFacetLabels(claim);
  if (field === "comparator_facet") return clinicalComparatorFacetLabel(claim);
  if (field === "follow_up_window_facet") return clinicalFollowUpWindowFacetLabel(claim);
  if (field === "study_design_facet") return studyDesignFacetLabel(claim);
  if (field === "public_health_topic_facet") return publicHealthTopicFacetLabel(claim);
  if (field === "public_health_context_facet") return publicHealthUseContextFacetLabels(claim);
  if (field === "public_health_data_source_facet") return publicHealthDataSourceFacetLabel(claim);
  if (field === "publication_type_facet") return publicationTypeFacetLabel(claim);
  if (field === "review_design_facet") return reviewDesignFacetLabel(claim);
  if (field === "review_contribution_facet") return reviewContributionFacetLabel(claim);
  if (field === "review_evidence_stratum_facet") return reviewEvidenceStratumFacetLabel(claim);
  if (field === "review_relationship_type_facet") return reviewRelationshipTypeFacetLabel(claim);
  if (field === "review_coverage_focus_facet") return reviewCoverageFocusFacetLabel(claim);
  if (field === "meta_analysis_design_facet") return metaAnalysisDesignFacetLabel(claim);
  if (field === "meta_analysis_study_count_facet") return metaAnalysisStudyCountFacetLabel(claim);
  if (field === "specific_pathway_readout") return specificPathwayReadoutLabel(claim);
  if (field === "first_author") return authorRoleIdentity(claim, "first").id || firstAuthorName(claim);
  if (field === "last_author") return authorRoleIdentity(claim, "last").id || lastAuthorName(claim);
  if (field === "study_journal") return journalFacetKey(claim.study_journal || claim.journal);
  return cleanDisplayText(claim[field]);
}

function claimsForPublicationYearRange(startValue, endValue, items = activeDetailItems) {
  const start = Number(startValue);
  const end = Number(endValue || startValue);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return [];
  return items.filter((claim) => {
    const year = parseYearValue(claim.study_year);
    return year !== null && year >= start && year <= end;
  });
}

function claimsForSampleHeatmapCell(startValue, endValue, minValue, maxValue, items = activeDetailItems) {
  const start = Number(startValue);
  const end = Number(endValue || startValue);
  const min = Number(minValue);
  const parsedMax = maxValue === "" ? Number.POSITIVE_INFINITY : Number(maxValue);
  const max = Number.isFinite(parsedMax) ? parsedMax : Number.POSITIVE_INFINITY;
  if (!Number.isFinite(start) || !Number.isFinite(end) || !Number.isFinite(min)) return [];

  const matchingStudies = new Set();
  items.forEach((claim, index) => {
    const year = parseYearValue(claim.study_year);
    const sampleSize = parseSampleSize(sampleSizeText(claim));
    if (year === null || sampleSize === null) return;
    if (year < start || year > end || sampleSize < min || sampleSize > max) return;
    matchingStudies.add(studyKey(claim, index));
  });
  if (!matchingStudies.size) return [];
  return items.filter((claim, index) => matchingStudies.has(studyKey(claim, index)));
}

function claimsForOutcomeScale(scaleValue, items = activeDetailItems, options = {}) {
  const scaleKey = normalizeValue(scaleValue);
  if (!scaleKey) return [];
  return outcomeScaleClaimsForChart(items, options).filter((claim) =>
    outcomeScaleLabelsForClaim(claim).some((scale) => normalizeValue(scale) === scaleKey)
  );
}

function restoreCurrentDetailPanel() {
  clearDetailGraphFilter();
  const filtered = applyFilters({ ignoreSearch: true }).filter(isMainGraphAdmitted);
  const allAccessFiltered = applyFilters({ ignoreAccess: true, ignoreSearch: true }).filter(
    isMainGraphAdmitted
  );
  refreshMainViews();
  if (selected) {
    renderSelectedDetailFromData(filtered, allAccessFiltered);
    return;
  }
  renderOverviewDetail(filtered, allAccessFiltered);
}

function renderStudyDetail(studyKeyValue) {
  const studyClaims = claimsForStudyKey(studyKeyValue);
  if (!studyClaims.length) return;
  const allAccessStudyClaims = claimsForStudyKey(
    studyKeyValue,
    activeDetailAllAccessItems.length ? activeDetailAllAccessItems : activeDetailItems
  );

  activeDetailItems = studyClaims;
  activeDetailAllAccessItems = allAccessStudyClaims;
  setDetailGraphFilter(studyClaims);
  const firstClaim = studyClaims[0];
  const rightKey = rightEntityKey();
  const title = cleanDisplayText(firstClaim.study_title) || "Study detail";
  const year = parseYearValue(firstClaim.study_year);
  const doiHref = doiUrl(firstClaim.study_doi);
  const source = doiHref
    ? `<a href="${doiHref}" target="_blank" rel="noopener noreferrer">${escapeHtml(firstClaim.study_doi)}</a>`
    : firstClaim.openalex_id
      ? `<a href="${openAlexUrl(firstClaim.openalex_id)}" target="_blank" rel="noopener noreferrer">${escapeHtml(
          firstClaim.openalex_id
        )}</a>`
      : "";
  const context = [
    year ? String(year) : "",
    cleanDisplayText(firstClaim.study_journal),
    cleanDisplayText(firstClaim.study_design),
  ]
    .filter(Boolean)
    .join(" · ");
  const sample = sampleSizeText(firstClaim);

  setDetailHeader(title);
  detailBody.innerHTML = `
    <div class="trend-dashboard">
      <div class="study-detail-actions">
        <button class="ghost small" type="button" data-detail-action="restore">Back</button>
      </div>
      ${renderTrendStats(studyClaims, [
        {
          label: "Compounds",
          value: formatCompactNumber(unique(studyClaims.map((claim) => compoundGraphLabelForClaim(claim)).filter(Boolean)).length),
        },
        {
          label: rightEntityLabel(true),
          value: formatCompactNumber(unique(studyClaims.map(graphRightLabelForClaim).filter(Boolean)).length),
        },
      ])}
      <section class="study-detail-note">
        ${context ? `<div>${escapeHtml(context)}</div>` : ""}
        ${sample ? `<div>Sample: ${escapeHtml(sample)}</div>` : ""}
        ${source ? `<div>${source}</div>` : ""}
      </section>
    </div>
  `;
}

function renderFieldValueDetail(field, value, labelValue = value) {
  const fieldClaims = claimsForFieldValue(field, value);
  if (!fieldClaims.length) return;
  const allAccessFieldClaims = claimsForFieldValue(
    field,
    value,
    activeDetailAllAccessItems.length ? activeDetailAllAccessItems : activeDetailItems
  );

  activeDetailItems = fieldClaims;
  activeDetailAllAccessItems = allAccessFieldClaims;
  setDetailGraphFilter(fieldClaims);
  setDetailHeader(fieldValueDetailTitle(field, labelValue));
  detailBody.innerHTML = `
    <div class="trend-dashboard">
      <div class="study-detail-actions">
        <button class="ghost small" type="button" data-detail-action="restore">Back</button>
      </div>
      ${renderTrendStats(fieldClaims)}
      ${renderAnnualPublicationChart(fieldClaims)}
      ${renderEvidenceDetailGroup(fieldClaims)}
      ${renderMetadataFacetCharts(fieldClaims)}
    </div>
  `;
}

function renderPublicationYearDetail(startValue, endValue, labelValue) {
  const yearClaims = claimsForPublicationYearRange(startValue, endValue);
  if (!yearClaims.length) return;
  const allAccessYearClaims = claimsForPublicationYearRange(
    startValue,
    endValue,
    activeDetailAllAccessItems.length ? activeDetailAllAccessItems : activeDetailItems
  );

  activeDetailItems = yearClaims;
  activeDetailAllAccessItems = allAccessYearClaims;
  setDetailGraphFilter(yearClaims);
  setDetailHeader(`Publications: ${labelValue}`);
  detailBody.innerHTML = `
    <div class="trend-dashboard">
      <div class="study-detail-actions">
        <button class="ghost small" type="button" data-detail-action="restore">Back</button>
      </div>
      ${renderTrendStats(yearClaims)}
      ${renderEvidenceDetailGroup(yearClaims)}
      ${renderMetadataFacetCharts(yearClaims)}
    </div>
  `;
}

function renderSampleHeatmapDetail(startValue, endValue, minValue, maxValue, labelValue) {
  const sampleClaims = claimsForSampleHeatmapCell(startValue, endValue, minValue, maxValue);
  if (!sampleClaims.length) return;
  const allAccessSampleClaims = claimsForSampleHeatmapCell(
    startValue,
    endValue,
    minValue,
    maxValue,
    activeDetailAllAccessItems.length ? activeDetailAllAccessItems : activeDetailItems
  );

  activeDetailItems = sampleClaims;
  activeDetailAllAccessItems = allAccessSampleClaims;
  setDetailGraphFilter(sampleClaims);
  setDetailHeader(`Sample sizes: ${labelValue}`);
  detailBody.innerHTML = `
    <div class="trend-dashboard">
      <div class="study-detail-actions">
        <button class="ghost small" type="button" data-detail-action="restore">Back</button>
      </div>
      ${renderTrendStats(sampleClaims)}
      ${renderEvidenceDetailGroup(sampleClaims)}
      ${renderMetadataFacetCharts(sampleClaims)}
    </div>
  `;
}

function renderOutcomeScaleDetail(scaleValue) {
  const scaleClaims = claimsForOutcomeScale(scaleValue);
  if (!scaleClaims.length) return;
  const allAccessSourceItems = activeDetailAllAccessItems.length
    ? activeDetailAllAccessItems
    : applyFilters({ ignoreAccess: true, ignoreSearch: true });
  const allAccessScaleClaims = claimsForOutcomeScale(scaleValue, allAccessSourceItems, { ignoreAccess: true });

  const scopeKeys = new Set(scaleClaims.map(evidenceScopeKey).filter(Boolean));
  const sourceItems = activeDetailItems.length ? activeDetailItems : applyFilters({ ignoreSearch: true });
  const scopedViewClaims =
    currentEntityViewKey() === "outcome_scale"
      ? scaleClaims
      : sourceItems.filter((claim) => !isOutcomeScaleClaim(claim) && scopeKeys.has(evidenceScopeKey(claim)));
  const detailClaims = scopedViewClaims.length ? scopedViewClaims : scaleClaims;
  const allAccessScopeKeys = new Set(allAccessScaleClaims.map(evidenceScopeKey).filter(Boolean));
  const allAccessScopedViewClaims =
    currentEntityViewKey() === "outcome_scale"
      ? allAccessScaleClaims
      : allAccessSourceItems.filter(
          (claim) => !isOutcomeScaleClaim(claim) && allAccessScopeKeys.has(evidenceScopeKey(claim))
        );
  const allAccessDetailClaims = allAccessScopedViewClaims.length
    ? allAccessScopedViewClaims
    : allAccessScaleClaims;

  activeDetailItems = detailClaims;
  activeDetailAllAccessItems = allAccessDetailClaims;
  setDetailGraphFilter(detailClaims);
  setDetailHeader(`Outcome scale: ${scaleValue}`);
  detailBody.innerHTML = `
    <div class="trend-dashboard">
      <div class="study-detail-actions">
        <button class="ghost small" type="button" data-detail-action="restore">Back</button>
      </div>
      ${renderTrendStats(detailClaims)}
      ${renderEvidenceDetailGroup(detailClaims)}
      ${renderMetadataFacetCharts(detailClaims)}
    </div>
  `;
}

function renderEdgeDetail(compound, target, edgeClaims, allAccessEdgeClaims = edgeClaims) {
  const studies = uniqueStudyCount(edgeClaims);
  activeDetailItems = edgeClaims;
  activeDetailAllAccessItems = allAccessEdgeClaims;
  setDetailHeader(`${compound} → ${target}`);

  detailBody.innerHTML = `
    <div class="trend-dashboard">
      ${renderTrendStats(edgeClaims)}
      ${renderAnnualPublicationChart(edgeClaims)}
      ${renderSpecificPathwayReadoutChart(edgeClaims)}
      ${renderEvidenceDetailGroup(edgeClaims)}
      ${renderMetadataFacetCharts(edgeClaims)}
    </div>
  `;
}

function renderNodeDetail(type, name, nodeClaims, allAccessNodeClaims = nodeClaims) {
  activeDetailItems = nodeClaims;
  activeDetailAllAccessItems = allAccessNodeClaims;
  setDetailHeader(name);

  detailBody.innerHTML = `
    <div class="trend-dashboard">
      ${renderTrendStats(nodeClaims)}
      ${renderAnnualPublicationChart(nodeClaims)}
      ${renderSpecificPathwayReadoutChart(nodeClaims)}
      ${renderEvidenceDetailGroup(nodeClaims)}
      ${renderMetadataFacetCharts(nodeClaims)}
    </div>
  `;
}

function overviewDetailCacheKeyForContext({
  sourceKey = currentSourceKey(),
  sourceClaims = claims,
  evidenceKey = evidenceView,
  viewKey = currentEntityViewKey(),
  accessKey = accessView,
  yearRange = activeYearRange(activeClaimsForMode()),
} = {}) {
  const yearKey = yearRange?.constrained ? `${yearRange.min || ""}-${yearRange.max || ""}` : "all-years";
  const journalKey = expandedChartKeys.has("journals") ? "journals-expanded" : "journals-top";
  return [
    sourceKey,
    claimArrayId(sourceClaims),
    evidenceKey,
    viewKey,
    accessKey,
    yearKey,
    journalKey,
  ].join("|");
}

function currentOverviewDetailCacheKey() {
  if (claimLayer !== "normalized" || selected || detailGraphFilter) return "";
  return overviewDetailCacheKeyForContext();
}

function overviewDetailSnapshot(data, allAccessData = data) {
  const title = `All ${lowerRightEntityLabel(true)}`;
  if (!data.length) {
    return {
      title,
      html: `<div class="detail-empty">${escapeHtml(recordLabelsForItems(data).empty)}</div>`,
    };
  }
  return {
    title,
    html: `
      <div class="trend-dashboard">
        ${renderTrendStats(data, [], allAccessData)}
        ${renderAnnualPublicationChart(data)}
        ${renderEvidenceDetailGroup(data)}
        ${renderMetadataFacetCharts(data)}
      </div>
    `,
  };
}

function createOverviewDetailCacheEntry(data, allAccessData = data) {
  const snapshot = overviewDetailSnapshot(data, allAccessData);
  const container = document.createElement("div");
  container.innerHTML = snapshot.html;
  return {
    ...snapshot,
    container,
    data,
    allAccessData,
  };
}

function rememberOverviewDetail(cacheKey, entry) {
  if (!cacheKey || !entry) return;
  overviewDetailCache.delete(cacheKey);
  overviewDetailCache.set(cacheKey, entry);
  while (overviewDetailCache.size > OVERVIEW_DETAIL_CACHE_LIMIT) {
    const oldestKey = overviewDetailCache.keys().next().value;
    if (oldestKey === activeOverviewDetailCacheKey) {
      const activeEntry = overviewDetailCache.get(oldestKey);
      overviewDetailCache.delete(oldestKey);
      overviewDetailCache.set(oldestKey, activeEntry);
      continue;
    }
    overviewDetailCache.delete(oldestKey);
  }
}

function applyOverviewDetailEntry(cacheKey, entry) {
  activeDetailItems = entry.data;
  activeDetailAllAccessItems = entry.allAccessData;
  if (activeOverviewDetailCacheKey === cacheKey && detailBody.childNodes.length) return;

  stashActiveOverviewDetail();
  detailTitle.textContent = entry.title;
  detailBody.replaceChildren(...Array.from(entry.container.childNodes));
  activeOverviewDetailCacheKey = cacheKey;
  overviewDetailCache.delete(cacheKey);
  overviewDetailCache.set(cacheKey, entry);
}

function restoreCachedOverviewDetail() {
  const cacheKey = currentOverviewDetailCacheKey();
  if (!cacheKey) return false;
  const entry = overviewDetailCache.get(cacheKey);
  if (!entry) return false;
  applyOverviewDetailEntry(cacheKey, entry);
  return true;
}

function clearOverviewDetailCacheForSource(sourceKey) {
  Array.from(overviewDetailCache.keys()).forEach((key) => {
    if (key.startsWith(`${sourceKey}|`)) overviewDetailCache.delete(key);
  });
  Array.from(overviewDetailPrewarmScheduled).forEach((key) => {
    if (key.startsWith(`${sourceKey}|`)) overviewDetailPrewarmScheduled.delete(key);
  });
  if (activeOverviewDetailCacheKey.startsWith(`${sourceKey}|`)) activeOverviewDetailCacheKey = "";
}

function clearOverviewDetailCache() {
  overviewDetailCache.clear();
  overviewDetailPrewarmScheduled.clear();
  activeOverviewDetailCacheKey = "";
}

function rekeyActiveOverviewDetail() {
  const previousKey = activeOverviewDetailCacheKey;
  if (!previousKey) return;
  const entry = overviewDetailCache.get(previousKey);
  const nextKey = currentOverviewDetailCacheKey();
  if (!entry || !nextKey || previousKey === nextKey) return;
  overviewDetailCache.delete(previousKey);
  overviewDetailCache.set(nextKey, entry);
  activeOverviewDetailCacheKey = nextKey;
}

function renderOverviewDetail(data, allAccessData = data) {
  const cacheKey = currentOverviewDetailCacheKey();
  if (!cacheKey) {
    const snapshot = overviewDetailSnapshot(data, allAccessData);
    stashActiveOverviewDetail();
    activeDetailItems = data;
    activeDetailAllAccessItems = allAccessData;
    detailTitle.textContent = snapshot.title;
    detailBody.innerHTML = snapshot.html;
    return;
  }

  let entry = overviewDetailCache.get(cacheKey);
  if (!entry) {
    entry = createOverviewDetailCacheEntry(data, allAccessData);
    rememberOverviewDetail(cacheKey, entry);
  } else {
    entry.data = data;
    entry.allAccessData = allAccessData;
  }
  applyOverviewDetailEntry(cacheKey, entry);
}

function renderSelectedDetailFromData(data, allAccessData = data) {
  if (!selected) return;
  const admittedData = data.filter(isMainGraphAdmitted);
  const admittedAllAccessData = allAccessData.filter(isMainGraphAdmitted);

  if (selected.type === "edge") {
    const edgeClaims = uniqueGraphPropositionClaims(
      admittedData.filter((claim) =>
        claimMatchesGraphEdge(claim, selected.compound, selected.target)
      )
    );
    const allAccessEdgeClaims = uniqueGraphPropositionClaims(
      admittedAllAccessData.filter((claim) =>
        claimMatchesGraphEdge(claim, selected.compound, selected.target)
      )
    );
    renderEdgeDetail(selected.compound, selected.target, edgeClaims, allAccessEdgeClaims);
    return;
  }

  if (selected.type === "compound") {
    const nodeClaims = admittedData.filter((claim) => claimMatchesGraphCompound(claim, selected.name));
    const allAccessNodeClaims = admittedAllAccessData.filter((claim) =>
      claimMatchesGraphCompound(claim, selected.name)
    );
    renderNodeDetail("compound", selected.name, nodeClaims, allAccessNodeClaims);
    return;
  }

  if (selected.type === "target") {
    const nodeClaims = admittedData.filter((claim) => claimMatchesGraphRight(claim, selected.name));
    const allAccessNodeClaims = admittedAllAccessData.filter((claim) =>
      claimMatchesGraphRight(claim, selected.name)
    );
    renderNodeDetail("target", selected.name, nodeClaims, allAccessNodeClaims);
  }
}

function findingsWithEligibleGraphNodes(data) {
  if (evidenceView === "meta_analyses") return data;

  const subjectStudies = new Map();
  const entityStudies = new Map();

  data.forEach((claim) => {
    const compound = compoundGraphLabelForClaim(claim);
    const right = graphRightLabelForClaim(claim);
    const study = studyJoinKey(claim);
    if (!compound || !right || !study) return;
    const subjectSet = subjectStudies.get(compound) || new Set();
    subjectSet.add(study);
    subjectStudies.set(compound, subjectSet);
    const entitySet = entityStudies.get(right) || new Set();
    entitySet.add(study);
    entityStudies.set(right, entitySet);
  });

  return data.filter((claim) => {
    const compound = compoundGraphLabelForClaim(claim);
    const right = graphRightLabelForClaim(claim);
    return (subjectStudies.get(compound)?.size || 0) >= 2 && (entityStudies.get(right)?.size || 0) >= 2;
  });
}

function graphRelationshipKeyForClaim(claim) {
  const compound = compoundGraphLabelForClaim(claim);
  const right = graphRightLabelForClaim(claim);
  return compound && right ? `${compound}|${right}` : "";
}

function fullViewRelationshipKeys() {
  let fullViewClaims = activeClaimsForMode();
  if (accessView === "open") {
    fullViewClaims = fullViewClaims.filter(isOpenAccessClaim);
  }
  return new Set(
    findingsWithEligibleGraphNodes(expandClaimsForGraph(fullViewClaims))
      .map(graphRelationshipKeyForClaim)
      .filter(Boolean),
  );
}

function claimArrayId(items) {
  if (!Array.isArray(items)) return 0;
  if (!claimArrayIds.has(items)) claimArrayIds.set(items, nextClaimArrayId++);
  return claimArrayIds.get(items);
}

function graphDomCacheKey(width, data) {
  if (claimLayer !== "normalized" || selected || detailGraphFilter) {
    return "";
  }
  const graphStage = data.some((claim) => claim?.__graph_bootstrap) ? "bootstrap" : "full";
  const yearMin = yearMinFilter?.value || "";
  const yearMax = yearMaxFilter?.value || "";
  return [
    currentSourceKey(),
    graphStage,
    graphStage === "bootstrap" ? "canonical" : claimArrayId(claims),
    evidenceView,
    currentEntityViewKey(),
    accessView,
    yearMin,
    yearMax,
    Math.round(width),
  ].join("|");
}

function clearGraphDomCacheForSource(sourceKey, { preserveBootstrap = false } = {}) {
  Array.from(graphDomCache.keys()).forEach((key) => {
    if (!key.startsWith(`${sourceKey}|`)) return;
    if (preserveBootstrap && key.startsWith(`${sourceKey}|bootstrap|`)) return;
    graphDomCache.delete(key);
  });
}

function rememberGraphDom(cacheKey, entry) {
  if (!cacheKey) return;
  graphDomCache.delete(cacheKey);
  graphDomCache.set(cacheKey, entry);
  while (graphDomCache.size > GRAPH_DOM_CACHE_LIMIT) {
    graphDomCache.delete(graphDomCache.keys().next().value);
  }
}

function crossfadeCompleteGraph(previousSvg, nextSvg) {
  const token = ++graphSwapToken;
  previousSvg.classList.add("graph-swap-layer", "graph-swap-out");
  nextSvg.classList.add("graph-swap-layer", "graph-swap-in");
  graphEl.appendChild(nextSvg);
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => {
      if (token !== graphSwapToken || !nextSvg.isConnected) return;
      previousSvg.classList.add("graph-swap-active");
      nextSvg.classList.add("graph-swap-active");
    });
  });
  window.setTimeout(() => {
    if (token !== graphSwapToken) return;
    previousSvg.remove();
    nextSvg.classList.remove("graph-swap-layer", "graph-swap-in", "graph-swap-active");
  }, 220);
}

function buildGraph(data) {
  hideTooltip();
  const graphHasDetailBootstrap = data.some((claim) => claim?.__detail_bootstrap);
  const graphIsAggregateBootstrap = data.some((claim) => claim?.__graph_bootstrap) && !graphHasDetailBootstrap;
  const graphStage = graphIsAggregateBootstrap ? "bootstrap" : "full";
  const previousSvg = graphEl.querySelector("svg[data-graph-stage]");
  const crossfadeFromBootstrap = previousSvg?.dataset.graphStage === "bootstrap" && graphStage === "full";
  const width = graphEl.clientWidth || 800;
  const cacheKey = graphDomCacheKey(width, data);
  const cached = cacheKey ? graphDomCache.get(cacheKey) : null;
  if (cached) {
    cached.reset?.();
    if (graphEl.firstElementChild !== cached.svg) {
      graphEl.replaceChildren(cached.svg);
      graphEl.style.setProperty("--kg-graph-height", `${cached.height}px`);
      cached.graphGrid?.style.setProperty("--kg-dynamic-workspace-height", `${cached.workspaceHeight}px`);
    }
    graphDomCache.delete(cacheKey);
    graphDomCache.set(cacheKey, cached);
    return;
  }
  if (!crossfadeFromBootstrap) {
    graphSwapToken += 1;
    graphEl.innerHTML = "";
  }

  const allowedRelationships = graphHasDetailBootstrap ? fullViewRelationshipKeys() : null;
  const expandedData = expandClaimsForGraph(data.filter(isMainGraphAdmitted)).filter(
    claimMatchesIsolatedGraphProjection
  );
  const graphData = allowedRelationships
    ? expandedData.filter((claim) => allowedRelationships.has(graphRelationshipKeyForClaim(claim)))
    : expandedData;
  const rightKey = rightEntityKey();
  const compoundCounts = new Map();
  const rightCounts = new Map();
  const compoundConnections = new Map();
  const rightConnections = new Map();
  const incidentEdgeKeysByCompound = new Map();
  const incidentEdgeKeysByRight = new Map();

  graphData.forEach((claim) => {
    const compound = compoundGraphLabelForClaim(claim);
    const right = graphRightLabelForClaim(claim);
    if (!compound || !right) return;
    const graphCount = graphRecordCount(claim);

    compoundCounts.set(compound, (compoundCounts.get(compound) || 0) + graphCount);
    rightCounts.set(right, (rightCounts.get(right) || 0) + graphCount);

    const compoundSet = compoundConnections.get(compound) || new Set();
    compoundSet.add(right);
    compoundConnections.set(compound, compoundSet);

    const rightSet = rightConnections.get(right) || new Set();
    rightSet.add(compound);
    rightConnections.set(right, rightSet);

    const edgeKey = `${compound}|${right}`;
    const byCompound = incidentEdgeKeysByCompound.get(compound) || new Set();
    byCompound.add(edgeKey);
    incidentEdgeKeysByCompound.set(compound, byCompound);
    const byRight = incidentEdgeKeysByRight.get(right) || new Set();
    byRight.add(edgeKey);
    incidentEdgeKeysByRight.set(right, byRight);
  });

  let compounds = Array.from(compoundCounts.keys()).sort((a, b) => {
    const byClaims = (compoundCounts.get(b) || 0) - (compoundCounts.get(a) || 0);
    if (byClaims !== 0) return byClaims;
    const byDegree = (compoundConnections.get(b)?.size || 0) - (compoundConnections.get(a)?.size || 0);
    if (byDegree !== 0) return byDegree;
    return a.localeCompare(b);
  });

  let targets = Array.from(rightCounts.keys()).sort((a, b) => {
    const byClaims = (rightCounts.get(b) || 0) - (rightCounts.get(a) || 0);
    if (byClaims !== 0) return byClaims;
    const byDegree = (rightConnections.get(b)?.size || 0) - (rightConnections.get(a)?.size || 0);
    if (byDegree !== 0) return byDegree;
    return a.localeCompare(b);
  });

  const compactGraph = width < 520;
  if (compactGraph) {
    const maxMobileNodes = 12;
    compounds = compounds.slice(0, maxMobileNodes);
    targets = targets.slice(0, maxMobileNodes);
  }

  const baseSideMargin = clampNumber(Math.floor(width * 0.16), 96, 190);
  let leftMargin = Math.max(baseSideMargin, GRAPH_LEFT_LABEL_MAX_WIDTH_PX + GRAPH_LABEL_MARGIN_BUFFER_PX);
  let rightMargin = Math.max(
    baseSideMargin,
    GRAPH_RIGHT_LABEL_MAX_WIDTH_PX + GRAPH_LABEL_MARGIN_BUFFER_PX + GRAPH_RIGHT_LABEL_GUTTER_PX
  );
  const minCenterWidth = 48;
  const maxMarginBudget = Math.max(220, width - minCenterWidth);
  const combinedMargins = leftMargin + rightMargin;
  if (combinedMargins > maxMarginBudget) {
    const scale = maxMarginBudget / combinedMargins;
    leftMargin = Math.floor(leftMargin * scale);
    rightMargin = Math.floor(rightMargin * scale);
  }

  const margin = { top: 40, right: rightMargin, bottom: 40, left: leftMargin };
  const minNodeSpacing = compactGraph ? GRAPH_COMPACT_MIN_NODE_SPACING_PX : GRAPH_MIN_NODE_SPACING_PX;
  const baseHeight = compactGraph ? GRAPH_COMPACT_BASE_HEIGHT_PX : GRAPH_BASE_HEIGHT_PX;
  const maxNodeCount = Math.max(compounds.length, targets.length, 1);
  const height = Math.ceil(Math.max(baseHeight, margin.top + margin.bottom + maxNodeCount * minNodeSpacing));
  graphEl.style.setProperty("--kg-graph-height", `${height}px`);
  const graphGrid = graphEl.closest(".graph-grid");
  const graphToolbar = graphEl.closest(".graph-column")?.querySelector(".graph-toolbar");
  const defaultWorkspaceHeight =
    Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--kg-workspace-height")) || 1030;
  const workspaceHeight = Math.ceil(Math.max(defaultWorkspaceHeight, height + (graphToolbar?.offsetHeight || 0)));
  graphGrid?.style.setProperty("--kg-dynamic-workspace-height", `${workspaceHeight}px`);
  const compoundX = margin.left;
  const targetX = width - margin.right;
  const labelOffset = 22;
  const labelMaxLines = 2;
  const leftLabelMaxWidth = Math.min(
    GRAPH_LEFT_LABEL_MAX_WIDTH_PX,
    Math.max(20, compoundX - labelOffset - 10)
  );
  const rightLabelMaxWidth = Math.min(
    GRAPH_RIGHT_LABEL_MAX_WIDTH_PX,
    Math.max(20, width - (targetX + labelOffset) - GRAPH_RIGHT_LABEL_GUTTER_PX - 10)
  );

  const compoundStep = (height - margin.top - margin.bottom) / Math.max(compounds.length, 1);
  const targetStep = (height - margin.top - margin.bottom) / Math.max(targets.length, 1);

  const compoundPositions = new Map();
  const targetPositions = new Map();

  compounds.forEach((compound, index) => {
    compoundPositions.set(compound, {
      x: compoundX,
      y: margin.top + index * compoundStep + compoundStep / 2,
    });
  });

  targets.forEach((target, index) => {
    targetPositions.set(target, {
      x: targetX,
      y: margin.top + index * targetStep + targetStep / 2,
    });
  });

  const edges = new Map();
  const claimsByCompound = new Map();
  const claimsByRight = new Map();
  graphData.forEach((claim) => {
    const compound = compoundGraphLabelForClaim(claim);
    const right = graphRightLabelForClaim(claim);
    if (compound) {
      const list = claimsByCompound.get(compound) || [];
      list.push(claim);
      claimsByCompound.set(compound, list);
    }
    if (right) {
      const list = claimsByRight.get(right) || [];
      list.push(claim);
      claimsByRight.set(right, list);
    }

    if (!compound || !right) return;

    const key = `${compound}|${right}`;
    const existing = edges.get(key) || {
      count: 0,
      rank: 0,
      claims: [],
    };
    const rank = evidenceRank[claim.evidence_level] || 1;
    existing.count += graphRecordCount(claim);
    existing.claims.push(claim);
    if (rank > existing.rank) {
      existing.rank = rank;
    }
    edges.set(key, existing);
  });
  const edgeEntries = Array.from(edges.entries());

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.dataset.graphStage = graphStage;
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  const edgeLayer = document.createElementNS("http://www.w3.org/2000/svg", "g");
  edgeLayer.setAttribute("class", "graph-edge-layer");
  const nodeLayer = document.createElementNS("http://www.w3.org/2000/svg", "g");
  nodeLayer.setAttribute("class", "graph-node-layer");
  svg.appendChild(defs);
  svg.appendChild(edgeLayer);
  svg.appendChild(nodeLayer);
  const compoundColors = new Map(compounds.map((compound, index) => [compound, graphColorForIndex(index, compounds.length)]));
  const targetColors = new Map(targets.map((target, index) => [target, graphColorForIndex(index, targets.length)]));
  const maxEdgeCount = Math.max(
    1,
    ...edgeEntries.map((entry) => entry[1].count || 0)
  );
  const edgeElementByKey = new Map();
  const compoundNodeElements = new Map();
  const rightNodeElements = new Map();
  let currentFocusClasses = new Map();
  let currentMuteRest = false;
  let focusFrame = 0;
  let pendingFocusRequest = null;
  let restoreFocusFrame = 0;

  function addFocusClass(focusClasses, element, focusClass) {
    if (!element) return;
    const currentClass = focusClasses.get(element);
    if (currentClass === "focus-primary") return;
    if (focusClass === "focus-primary" || !currentClass) {
      focusClasses.set(element, focusClass);
    }
  }

  function addNodeFocus(focusClasses, elementMap, name, focusClass) {
    const pair = elementMap.get(name);
    if (!pair) return;
    addFocusClass(focusClasses, pair.node, focusClass);
    addFocusClass(focusClasses, pair.label, focusClass);
  }

  function addEdgeFocus(focusClasses, edgeKey, focusClass) {
    addFocusClass(focusClasses, edgeElementByKey.get(edgeKey), focusClass);
  }

  function applyFocusState(nextFocusClasses, muteRest) {
    const previousFocusClasses = currentFocusClasses;

    previousFocusClasses.forEach((previousClass, element) => {
      const nextClass = nextFocusClasses.get(element);
      if (previousClass !== nextClass) {
        element.classList.remove(previousClass);
      }
    });

    if (currentMuteRest !== muteRest) {
      svg.classList.toggle("focus-active", muteRest);
    }

    nextFocusClasses.forEach((nextClass, element) => {
      const previousClass = previousFocusClasses.get(element);
      if (previousClass !== nextClass) {
        element.classList.add(nextClass);
      }
    });

    currentFocusClasses = nextFocusClasses;
    currentMuteRest = muteRest;
  }

  function scheduleFocusState(nextFocusClasses, muteRest) {
    pendingFocusRequest = { nextFocusClasses, muteRest };
    if (focusFrame) return;
    focusFrame = window.requestAnimationFrame(() => {
      focusFrame = 0;
      const request = pendingFocusRequest;
      pendingFocusRequest = null;
      if (!request) return;
      applyFocusState(request.nextFocusClasses, request.muteRest);
    });
  }

  function focusClassesForNode(nodeType, nodeName) {
    const focusClasses = new Map();
    const edgeKeys =
      nodeType === "compound"
        ? incidentEdgeKeysByCompound.get(nodeName)
        : incidentEdgeKeysByRight.get(nodeName);

    if (edgeKeys) {
      edgeKeys.forEach((edgeKey) => {
        addEdgeFocus(focusClasses, edgeKey, "focus-related");
        const [compound, right] = edgeKey.split("|");
        addNodeFocus(focusClasses, compoundNodeElements, compound, "focus-related");
        addNodeFocus(focusClasses, rightNodeElements, right, "focus-related");
      });
    }

    if (nodeType === "compound") {
      addNodeFocus(focusClasses, compoundNodeElements, nodeName, "focus-primary");
    } else {
      addNodeFocus(focusClasses, rightNodeElements, nodeName, "focus-primary");
    }

    return focusClasses;
  }

  function focusClassesForEdge(edgeKey) {
    const focusClasses = new Map();
    addEdgeFocus(focusClasses, edgeKey, "focus-primary");
    const [compound, right] = edgeKey.split("|");
    addNodeFocus(focusClasses, compoundNodeElements, compound, "focus-related");
    addNodeFocus(focusClasses, rightNodeElements, right, "focus-related");
    return focusClasses;
  }

  function applyFocusForNode(nodeType, nodeName) {
    scheduleFocusState(focusClassesForNode(nodeType, nodeName), false);
  }

  function applyFocusForEdge(edgeKey) {
    scheduleFocusState(focusClassesForEdge(edgeKey), false);
  }

  function applyFocusFromSelection() {
    if (!selected) {
      scheduleFocusState(new Map(), false);
      return;
    }
    if (selected.type === "edge") {
      applyFocusForEdge(`${selected.compound}|${selected.target}`);
      return;
    }
    if (selected.type === "compound") {
      applyFocusForNode("compound", selected.name);
      return;
    }
    if (selected.type === "target") {
      applyFocusForNode("target", selected.name);
      return;
    }
    applyFocusState(new Map(), false);
  }

  function cancelPendingFocusRestore() {
    if (!restoreFocusFrame) return;
    window.cancelAnimationFrame(restoreFocusFrame);
    restoreFocusFrame = 0;
  }

  function restoreFocusAfterPointerLeave() {
    cancelPendingFocusRestore();
    restoreFocusFrame = window.requestAnimationFrame(() => {
      restoreFocusFrame = 0;
      applyFocusFromSelection();
    });
  }

  function prepareBootstrapInteraction() {
    if (!graphIsAggregateBootstrap) return true;
    if (!normalizedCurrentSourceLoaded()) return false;
    if (cacheKey) graphDomCache.delete(cacheKey);
    retainVisibleBootstrapGraph = false;
    return true;
  }

  edgeEntries.forEach(([key, edge], index) => {
    const [compound, target] = key.split("|");
    const cPos = compoundPositions.get(compound);
    const tPos = targetPositions.get(target);
    if (!cPos || !tPos) return;

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const midX = (cPos.x + tPos.x) / 2;
    const curve = 80;
    const d = `M ${cPos.x} ${cPos.y} C ${midX - curve} ${cPos.y}, ${midX + curve} ${tPos.y}, ${tPos.x} ${tPos.y}`;
    path.setAttribute("d", d);
    path.setAttribute("class", "edge");
    const edgeWidth = edgeWidthForCount(edge.count, maxEdgeCount);
    path.style.setProperty("--edge-width", `${edgeWidth.toFixed(2)}px`);
    const compoundColor = compoundColors.get(compound) || graphColorForIndex(0, 1);
    const targetColor = targetColors.get(target) || graphColorForIndex(0, 1);
    const gradientId = `edge-gradient-${index}`;
    const gradient = document.createElementNS("http://www.w3.org/2000/svg", "linearGradient");
    gradient.setAttribute("id", gradientId);
    gradient.setAttribute("gradientUnits", "userSpaceOnUse");
    gradient.setAttribute("x1", `${cPos.x}`);
    gradient.setAttribute("y1", `${cPos.y}`);
    gradient.setAttribute("x2", `${tPos.x}`);
    gradient.setAttribute("y2", `${tPos.y}`);
    const start = document.createElementNS("http://www.w3.org/2000/svg", "stop");
    start.setAttribute("offset", "0%");
    start.setAttribute("stop-color", rgbString(compoundColor));
    start.setAttribute("stop-opacity", "0.78");
    const end = document.createElementNS("http://www.w3.org/2000/svg", "stop");
    end.setAttribute("offset", "100%");
    end.setAttribute("stop-color", rgbString(targetColor));
    end.setAttribute("stop-opacity", "0.72");
    gradient.appendChild(start);
    gradient.appendChild(end);
    defs.appendChild(gradient);
    path.style.stroke = `url(#${gradientId})`;
    path.style.setProperty("--edge-glow", rgbaString(compoundColor, 0.28));
    path.dataset.compound = compound;
    path.dataset.target = target;
    path.dataset.claimCount = `${edge.count}`;
    path.dataset.edgeKey = key;
    if (selected?.type === "edge" && selected.compound === compound && selected.target === target) {
      path.classList.add("selected");
    }
    edgeElementByKey.set(key, path);
    const edgeTooltipHtml = `<strong>${compound} → ${target}</strong><br/>${evidenceCountTooltipHtml(edge.claims)}`;

    path.addEventListener("mouseenter", (event) => {
      cancelPendingFocusRestore();
      path.classList.add("hovered");
      applyFocusForEdge(key);
      showTooltip(edgeTooltipHtml, event);
    });
    path.addEventListener("mousemove", moveTooltip);
    path.addEventListener("mouseleave", () => {
      path.classList.remove("hovered");
      hideTooltip();
      restoreFocusAfterPointerLeave();
    });
    path.addEventListener("click", (event) => {
      event.stopPropagation();
      if (!prepareBootstrapInteraction()) return;
      const sameSelection =
        selected?.type === "edge" && selected.compound === compound && selected.target === target;
      if (sameSelection) {
        if (!isolateSelection) {
          isolateSelection = true;
          requestGraphCenterAfterRender();
          scheduleRender();
          return;
        }
        clearSelection();
        return;
      }

      selected = { type: "edge", compound, target };
      isolateSelection = true;
      requestGraphCenterAfterRender();
      clearSelectedStyles();
      path.classList.add("selected");
      const detailClaims = graphIsAggregateBootstrap
        ? applyFilters({ ignoreSearch: true }).filter((claim) =>
            claimMatchesGraphEdge(claim, compound, target)
          )
        : uniqueGraphPropositionClaims(edge.claims);
      renderEdgeDetail(compound, target, detailClaims);
      applyFocusFromSelection();
      scheduleRender();
    });
    edgeLayer.appendChild(path);
  });

  compoundPositions.forEach((pos, compound) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    node.setAttribute("cx", pos.x);
    node.setAttribute("cy", pos.y);
    node.setAttribute("r", 12);
    node.setAttribute("class", "node compound");
    applyGraphNodeColor(node, compoundColors.get(compound) || graphColorForIndex(0, 1));
    if (selected?.type === "compound" && selected.name === compound) {
      node.classList.add("selected");
    }
    nodeLayer.appendChild(node);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", pos.x - labelOffset);
    label.setAttribute("class", "node-label");
    label.setAttribute("text-anchor", "end");
    setWrappedSvgLabel(label, compound, leftLabelMaxWidth, pos.x - labelOffset, pos.y, labelMaxLines);
    if (selected?.type === "compound" && selected.name === compound) {
      label.classList.add("selected");
    }
    nodeLayer.appendChild(label);
    compoundNodeElements.set(compound, { node, label });

    const nodeClaims = claimsByCompound.get(compound) || [];
    const nodeTooltipHtml = `<strong>${compound}</strong><br/>${evidenceCountTooltipHtml(nodeClaims)}<br/>Connections: ${
      summarizeConnections(nodeClaims, rightKey).length
    }`;
    const enter = (event) => {
      cancelPendingFocusRestore();
      node.classList.add("hovered");
      label.classList.add("hovered");
      applyFocusForNode("compound", compound);
      showTooltip(nodeTooltipHtml, event);
    };
    const leave = () => {
      node.classList.remove("hovered");
      label.classList.remove("hovered");
      hideTooltip();
      restoreFocusAfterPointerLeave();
    };
    const click = (event) => {
      event.stopPropagation();
      if (!prepareBootstrapInteraction()) return;
      const sameSelection = selected?.type === "compound" && selected.name === compound;
      if (sameSelection) {
        if (!isolateSelection) {
          isolateSelection = true;
          requestGraphCenterAfterRender();
          scheduleRender();
          return;
        }
        clearSelection();
        return;
      }

      selected = { type: "compound", name: compound };
      isolateSelection = true;
      requestGraphCenterAfterRender();
      clearSelectedStyles();
      node.classList.add("selected");
      label.classList.add("selected");
      const detailClaims = graphIsAggregateBootstrap
        ? applyFilters({ ignoreSearch: true }).filter((claim) =>
            claimMatchesGraphCompound(claim, compound)
          )
        : nodeClaims;
      renderNodeDetail("compound", compound, detailClaims);
      applyFocusFromSelection();
      scheduleRender();
    };
    node.addEventListener("mouseenter", enter);
    node.addEventListener("mousemove", moveTooltip);
    node.addEventListener("mouseleave", leave);
    node.addEventListener("click", click);
    label.addEventListener("mouseenter", enter);
    label.addEventListener("mousemove", moveTooltip);
    label.addEventListener("mouseleave", leave);
    label.addEventListener("click", click);
  });

  targetPositions.forEach((pos, target) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    node.setAttribute("cx", pos.x);
    node.setAttribute("cy", pos.y);
    node.setAttribute("r", 12);
    node.setAttribute("class", "node target");
    applyGraphNodeColor(node, targetColors.get(target) || graphColorForIndex(0, 1));
    if (selected?.type === "target" && selected.name === target) {
      node.classList.add("selected");
    }
    nodeLayer.appendChild(node);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", pos.x + labelOffset);
    label.setAttribute("class", "node-label");
    setWrappedSvgLabel(label, target, rightLabelMaxWidth, pos.x + labelOffset, pos.y, labelMaxLines);
    if (selected?.type === "target" && selected.name === target) {
      label.classList.add("selected");
    }
    nodeLayer.appendChild(label);
    rightNodeElements.set(target, { node, label });

    const nodeClaims = claimsByRight.get(target) || [];
    const clarifier = conditionGraphClarifier(target);
    const nodeTooltipHtml = `<strong>${target}</strong>${clarifier ? `<br/>${escapeHtml(clarifier)}` : ""}<br/>${evidenceCountTooltipHtml(nodeClaims)}<br/>Compounds: ${
      summarizeConnections(nodeClaims, "compound").length
    }`;
    const enter = (event) => {
      cancelPendingFocusRestore();
      node.classList.add("hovered");
      label.classList.add("hovered");
      applyFocusForNode("target", target);
      showTooltip(nodeTooltipHtml, event);
    };
    const leave = () => {
      node.classList.remove("hovered");
      label.classList.remove("hovered");
      hideTooltip();
      restoreFocusAfterPointerLeave();
    };
    const click = (event) => {
      event.stopPropagation();
      if (!prepareBootstrapInteraction()) return;
      const sameSelection = selected?.type === "target" && selected.name === target;
      if (sameSelection) {
        if (!isolateSelection) {
          isolateSelection = true;
          requestGraphCenterAfterRender();
          scheduleRender();
          return;
        }
        clearSelection();
        return;
      }

      selected = { type: "target", name: target };
      isolateSelection = true;
      requestGraphCenterAfterRender();
      clearSelectedStyles();
      node.classList.add("selected");
      label.classList.add("selected");
      const detailClaims = graphIsAggregateBootstrap
        ? applyFilters({ ignoreSearch: true }).filter((claim) =>
            claimMatchesGraphRight(claim, target)
          )
        : nodeClaims;
      renderNodeDetail("target", target, detailClaims);
      applyFocusFromSelection();
      scheduleRender();
    };
    node.addEventListener("mouseenter", enter);
    node.addEventListener("mousemove", moveTooltip);
    node.addEventListener("mouseleave", leave);
    node.addEventListener("click", click);
    label.addEventListener("mouseenter", enter);
    label.addEventListener("mousemove", moveTooltip);
    label.addEventListener("mouseleave", leave);
    label.addEventListener("click", click);
  });

  if (crossfadeFromBootstrap && previousSvg) {
    crossfadeCompleteGraph(previousSvg, svg);
  } else {
    graphEl.appendChild(svg);
  }
  rememberGraphDom(cacheKey, {
    svg,
    height,
    workspaceHeight,
    graphGrid,
    reset: () => {
      if (focusFrame) window.cancelAnimationFrame(focusFrame);
      focusFrame = 0;
      pendingFocusRequest = null;
      cancelPendingFocusRestore();
      applyFocusState(new Map(), false);
      svg.querySelectorAll(".selected, .hovered").forEach((element) => {
        element.classList.remove("selected", "hovered");
      });
    },
  });

  applyFocusFromSelection();
}

function render() {
  cancelPendingFindingSearchRender();
  let graphFiltered = applyFilters({ ignoreSearch: true }).filter(isMainGraphAdmitted);
  let allAccessGraphFiltered = applyFilters({ ignoreAccess: true, ignoreSearch: true }).filter(
    isMainGraphAdmitted
  );
  if (selected && !selectionIsValid(graphFiltered)) {
    selected = null;
    isolateSelection = false;
    clearSelectedStyles();
    graphFiltered = applyFilters({ ignoreSearch: true }).filter(isMainGraphAdmitted);
    allAccessGraphFiltered = applyFilters({ ignoreAccess: true, ignoreSearch: true }).filter(
      isMainGraphAdmitted
    );
  }
  updateStats();
  const canonicalBootstrap = canonicalOverviewBootstrapClaims();
  if (canonicalBootstrap?.length) {
    retainVisibleBootstrapGraph = true;
    buildGraph(canonicalBootstrap);
  } else {
    const retainingBootstrap =
      retainVisibleBootstrapGraph && Boolean(graphEl.querySelector('svg[data-graph-stage="bootstrap"]'));
    if (!retainingBootstrap) buildGraph(graphFiltered);
  }
  scheduleDeferredSurfaceRender(graphFiltered, allAccessGraphFiltered, true);
  scheduleFindingSearchIndexWarmup();
}

function refreshMainViews() {
  const graphFiltered = applyFilters({ ignoreSearch: true }).filter(isMainGraphAdmitted);
  if (selected && !selectionIsValid(graphFiltered)) {
    selected = null;
    isolateSelection = false;
    clearSelectedStyles();
  }
  updateStats();
  buildGraph(graphFiltered);
  scheduleDeferredSurfaceRender(
    graphFiltered,
    applyFilters({ ignoreAccess: true, ignoreSearch: true }).filter(isMainGraphAdmitted),
    false
  );
}

function scheduleDeferredSurfaceRender(graphFiltered, allAccessGraphFiltered, updateDetail) {
  const token = ++deferredSurfaceRenderToken;
  window.requestAnimationFrame(() => {
    if (token !== deferredSurfaceRenderToken) return;
    if (updateDetail) {
      if (detailGraphFilter) {
        // Keep the current right-panel drilldown visible while refreshing the graph.
      } else if (selected) {
        renderSelectedDetailFromData(graphFiltered, allAccessGraphFiltered);
      } else {
        renderOverviewDetail(graphFiltered, allAccessGraphFiltered);
      }
    }
    window.requestAnimationFrame(() => {
      if (token !== deferredSurfaceRenderToken) return;
      renderCards(findingCardResults(graphFiltered));
      renderBibliography(graphFiltered);
    });
  });
}

function scheduleRender() {
  if (renderScheduled) return;
  renderScheduled = true;
  window.requestAnimationFrame(() => {
    renderScheduled = false;
    render();
    runPendingGraphCenter();
  });
}

function cancelPendingFindingSearchRender() {
  findingSearchRenderToken += 1;
  if (findingSearchTimer) {
    window.clearTimeout(findingSearchTimer);
    findingSearchTimer = 0;
  }
  cardsEl.removeAttribute("aria-busy");
}

function scheduleFindingSearchRender() {
  const token = ++findingSearchRenderToken;
  if (findingSearchTimer) window.clearTimeout(findingSearchTimer);
  cardsEl.setAttribute("aria-busy", "true");
  findingSearchTimer = window.setTimeout(() => {
    findingSearchTimer = 0;
    window.requestAnimationFrame(() => {
      if (token !== findingSearchRenderToken) return;
      const graphFiltered = applyFilters({ ignoreSearch: true });
      renderCards(findingCardResults(graphFiltered));
    });
  }, FINDING_SEARCH_DEBOUNCE_MS);
}

function scheduleFindingSearchIndexWarmup() {
  if (!claims.length || hasFindingSearchQuery()) return;
  const key = `${claimLayer}|${evidenceView}|${currentEntityViewKey()}`;
  if (
    findingSearchWarmupState?.source === claims &&
    findingSearchWarmupState.key === key &&
    ["warming", "complete"].includes(findingSearchWarmupState.status)
  ) {
    return;
  }

  const token = ++findingSearchWarmupToken;
  const source = claims;
  const items = globalFindingSearchClaims();
  let index = 0;
  if (!items.length) {
    findingSearchWarmupState = { source, key, status: "complete" };
    return;
  }
  findingSearchWarmupState = { source, key, status: "warming" };

  function warmChunk(deadline) {
    if (token !== findingSearchWarmupToken || source !== claims) return;
    const started = window.performance?.now?.() ?? Date.now();
    do {
      claimSearchHaystack(items[index]);
      index += 1;
    } while (
      index < items.length &&
      (window.performance?.now?.() ?? Date.now()) - started < 8 &&
      (!deadline || deadline.didTimeout || deadline.timeRemaining() > 1)
    );

    if (index < items.length) {
      scheduleIdleTask(warmChunk);
      return;
    }
    findingSearchWarmupState = { source, key, status: "complete" };
  }

  scheduleIdleTask(warmChunk, 220);
}

function requestGraphCenterAfterRender() {
  centerGraphAfterRender = true;
}

function runPendingGraphCenter() {
  if (!centerGraphAfterRender) return;
  centerGraphAfterRender = false;
  if (centerGraphFrame) {
    window.cancelAnimationFrame(centerGraphFrame);
  }
  centerGraphFrame = window.requestAnimationFrame(() => {
    centerGraphFrame = 0;
    centerGraphInViewport();
  });
}

function centerGraphInViewport() {
  const rect = graphEl.getBoundingClientRect();
  if (!rect.height) return;
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
  if (!viewportHeight) return;
  const graphCenterY = window.scrollY + rect.top + rect.height / 2;
  const targetTop = Math.max(0, graphCenterY - viewportHeight / 2);
  window.scrollTo({ top: targetTop, behavior: "smooth" });
}

function updateSearchPlaceholder() {
  if (!searchInput) return;
  searchInput.placeholder = `Search finding cards by keyword, compound, ${lowerRightEntityLabel(false)}, method, or paper`;
}

function entityCategoryCounts() {
  const key = `${claimLayer}|${evidenceView}`;
  if (entityCategoryCountsMemo?.source === claims && entityCategoryCountsMemo.key === key) {
    return entityCategoryCountsMemo.value;
  }

  const counts = new Map(ENTITY_CATEGORY_OPTIONS.map((option) => [option.key, 0]));
  if (claimLayer !== "normalized") {
    entityCategoryCountsMemo = { source: claims, key, value: counts };
    return counts;
  }

  const visibleClaims = graphViewClaims(expandedClaimsWithUseContextProjections(claims));
  visibleClaims.forEach((claim) => {
    ENTITY_CATEGORY_OPTIONS.forEach((option) => {
      if (claimMatchesEntityViewOption(claim, option)) {
        counts.set(option.key, (counts.get(option.key) || 0) + 1);
      }
    });
  });
  entityCategoryCountsMemo = { source: claims, key, value: counts };
  return counts;
}

function updateEntityKindToggle() {
  if (!entityKindToggle) return;
  const isAvailable = claimLayer === "normalized";
  entityKindToggle.hidden = !isAvailable;
  if (!isAvailable) {
    entityKindToggle.innerHTML = "";
    return;
  }

  const counts = entityCategoryCounts();
  entityKindToggle.innerHTML = ENTITY_CATEGORY_OPTIONS
    .map((option) => {
      const isActive = option.key === currentEntityViewKey();
      const count = counts.get(option.key) || 0;
      return `
        <button
          class="ghost small ${isActive ? "active" : ""}"
          data-entity-view="${escapeHtml(option.key)}"
          role="tab"
          aria-selected="${isActive ? "true" : "false"}"
          aria-label="${escapeHtml(`${option.label}${count ? `, ${count} findings` : ""}`)}"
          type="button"
        >
          ${escapeHtml(option.label)}
        </button>
      `;
    })
    .join("");
}

function updateModeUI() {
  claimLayerButtons.forEach((btn) => {
    const isActive = btn.dataset.claimLayer === claimLayer;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  evidenceViewButtons.forEach((btn) => {
    const isActive = btn.dataset.evidenceView === evidenceView;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  updateEntityKindToggle();
  updateSearchPlaceholder();
}

function switchClaimLayer(nextLayer) {
  if (!claimStores[nextLayer] || claimLayer === nextLayer) return;
  retainVisibleBootstrapGraph = false;
  claimLayer = nextLayer;
  applyClaimLayerStore();
  selected = null;
  isolateSelection = false;
  detailGraphFilter = null;
  clearSelectedStyles();
  updateModeUI();
  syncYearFilterControls(activeClaimsForMode(), true);
  const detailRestored = restoreCachedOverviewDetail();
  if (!detailRestored) clearDetailForTransition();
  loadCurrentClaimsAndRender({
    resetDetail: !detailRestored,
    showGraphBootstrap: nextLayer === "normalized",
  });
}

function switchEvidenceView(nextView) {
  if (!EVIDENCE_VIEW_KEYS.includes(nextView) || evidenceView === nextView) return;
  retainVisibleBootstrapGraph = false;
  evidenceView = nextView;
  applyClaimLayerStore();
  selected = null;
  isolateSelection = false;
  detailGraphFilter = null;
  clearSelectedStyles();
  updateModeUI();
  syncYearFilterControls(activeClaimsForMode(), true);
  const detailRestored = restoreCachedOverviewDetail();
  if (!detailRestored) clearDetailForTransition();
  loadCurrentClaimsAndRender({
    resetDetail: !detailRestored,
    showGraphBootstrap: claimLayer === "normalized",
  });
}

function switchEntityView(nextView) {
  if (!ENTITY_CATEGORY_OPTIONS.some((option) => option.key === nextView)) return;
  if (currentEntityViewKey() === nextView) return;
  retainVisibleBootstrapGraph = false;
  entityViewKey = nextView;
  selected = null;
  isolateSelection = false;
  detailGraphFilter = null;
  clearSelectedStyles();
  updateModeUI();
  syncYearFilterControls(activeClaimsForMode(), true);
  const detailRestored = restoreCachedOverviewDetail();
  if (!detailRestored) clearDetailForTransition();
  loadCurrentClaimsAndRender({ resetDetail: !detailRestored });
}

async function fetchJsonFromCandidates(candidates) {
  const errors = [];
  for (const url of candidates) {
    try {
      const response = await fetch(url, dataFetchOptions);
      if (!response.ok) {
        errors.push(`${url} -> HTTP ${response.status}`);
        continue;
      }
      const data = await response.json();
      return { data, url };
    } catch (error) {
      errors.push(`${url} -> ${error.message}`);
    }
  }
  throw new Error(errors.join("; "));
}

function dataCandidates(path) {
  return [`../${path}`, `/${path}`, path];
}

async function loadGraphPayloadConfig() {
  if (graphPayloadConfigPromise) return graphPayloadConfigPromise;
  graphPayloadConfigPromise = fetchJsonFromCandidates(dataCandidates("data/processed/graph_payload_active.json"))
    .then(({ data }) => data || {})
    .catch(() => ({}));
  return graphPayloadConfigPromise;
}

function loadGraphManifestStats() {
  if (graphManifestPromise) return graphManifestPromise;
  graphManifestPromise = (async () => {
    const config = await loadGraphPayloadConfig();
    const activeManifest = cleanDisplayText(config?.active_manifest || "");
    if (!activeManifest) return null;
    return fetchJsonFromCandidates(dataCandidates(activeManifest)).then(({ data }) => {
      const snapshot = heroStatsFromGraphManifest(data);
      if (snapshot) {
        heroStatsSnapshot = snapshot;
        updateStats();
      }
      return snapshot;
    });
  })()
    .catch(() => null);
  return graphManifestPromise;
}

function renderLoadError(messages) {
  setDetailHeader("Data Load Error");
  detailBody.innerHTML = `
    <div class="detail-empty">
      Start a local static server from the project root (for example: <code>python3 -m http.server</code>), then open <code>/</code>.
    </div>
    <div class="detail-list">
      ${messages.map((msg) => `<div class="detail-item"><div class="meta">${msg}</div></div>`).join("")}
    </div>
  `;
  cardsEl.innerHTML = `<div class="detail-empty">No findings loaded.</div>`;
  graphEl.innerHTML = "";
  if (studyListEl) {
    studyListEl.innerHTML = `<div class="detail-empty">No studies loaded.</div>`;
  }
}

async function loadBibliographyPayloads() {
  bibliographyBySource.all = bibliographyBySource.all || [];
}

const normalizedSourceLoaded = {
  primary: false,
  meta_analyses: false,
  reviews: false,
};

const normalizedSourceTasks = {
  primary: null,
  meta_analyses: null,
  reviews: null,
};

function renderDataLoading() {
  clearDetailForTransition();
  cardsEl.innerHTML = "";
  graphEl.innerHTML = "";
  if (studyListEl) {
    studyListEl.innerHTML = "";
  }
}

function bibliographyPayloadsLoaded() {
  return Object.values(bibliographyBySource).some((rows) => Array.isArray(rows) && rows.length);
}

function enrichAllLoadedClaimsWithBibliography() {
  Object.keys(claimStores).forEach((layer) => {
    const store = claimStores[layer];
    if (store.bySource) {
      Object.keys(store.bySource).forEach((sourceKey) => {
        store.bySource[sourceKey] = enrichClaimsWithBibliographyMetadata(store.bySource[sourceKey] || []);
      });
      store.all = Object.values(store.bySource).flat();
      return;
    }
    store.all = enrichClaimsWithBibliographyMetadata(store.all || []);
  });
  clearOverviewDetailCache();
  activeClaimsMemo = null;
  entityCategoryCountsMemo = null;
}

function activeGraphBootstrapPath(config, sourceKey) {
  const bootstraps = config?.active_graph_bootstraps || {};
  return cleanDisplayText(bootstraps?.[sourceKey]);
}

function activeDetailBootstrapPath(config, sourceKey) {
  const bootstraps = config?.active_detail_bootstraps || {};
  return cleanDisplayText(bootstraps?.[sourceKey]);
}

function isSecondarySourceKey(sourceKey) {
  return META_ANALYSIS_SOURCE_KEYS.has(sourceKey) || REVIEW_SOURCE_KEYS.has(sourceKey);
}

function graphBootstrapClaimsFromPayload(payload, sourceKey) {
  const edges = Array.isArray(payload?.edges) ? payload.edges : [];
  return edges.map((edge, index) => {
    const entityLabel = cleanDisplayText(edge.entity_label);
    const accessLevel = Number(edge.full_text_seen_count || 0) > 0 ? "full_text_seen" : "abstract_only";
    const secondary = isSecondarySourceKey(sourceKey);
    const metaAnalysis = sourceKey === "meta_analyses";
    const item = {
      finding_id: `graph-bootstrap:${index}`,
      projection_type: cleanDisplayText(edge.projection_type || "outcome"),
      relation_type: cleanDisplayText(edge.relation_type),
      kg_relation_type: cleanDisplayText(edge.relation_type),
      compound: cleanDisplayText(edge.compound),
      compound_aliases: Array.isArray(edge.compound_aliases)
        ? edge.compound_aliases.map(cleanDisplayText).filter(Boolean)
        : [],
      graph_overview_subject_label: cleanDisplayText(edge.compound),
      graph_overview_subject_kind: cleanDisplayText(edge.graph_subject_kind),
      graph_subject_kind: cleanDisplayText(edge.graph_subject_kind),
      entity_label: entityLabel,
      graph_entity_label: entityLabel,
      use_context_aliases: Array.isArray(edge.entity_aliases)
        ? edge.entity_aliases.map(cleanDisplayText).filter(Boolean)
        : [],
      graph_parent_label: cleanDisplayText(edge.graph_parent_label),
      graph_parent_kind: cleanDisplayText(edge.graph_parent_kind),
      graph_parent_entity_id: cleanDisplayText(edge.graph_parent_entity_id),
      kg_entity_kind: cleanDisplayText(edge.entity_kind),
      entity_kind: cleanDisplayText(edge.entity_kind),
      kg_domain: cleanDisplayText(edge.domain),
      domain: cleanDisplayText(edge.domain),
      finding_type: cleanDisplayText(edge.finding_type || edge.domain),
      kg_evidence_type: cleanDisplayText(edge.evidence_type || (secondary ? "secondary_literature" : "primary_evidence")),
      paper_assessment_route: secondary ? "secondary_literature" : "primary_evidence",
      paper_type: secondary ? (metaAnalysis ? "meta_analysis" : "review") : "primary_results",
      source_type: secondary ? (metaAnalysis ? "meta_analysis" : "review") : "primary_study",
      access_level: accessLevel,
      source_access_level: accessLevel,
      graph_claim_count: Number(edge.finding_count || 0) || 1,
      graph_study_count: Number(edge.study_count || 0) || 0,
      graph_full_text_claim_count: Number(edge.full_text_seen_count || 0) || 0,
      graph_full_text_study_count: Number(edge.full_text_seen_study_count || 0) || 0,
      __graph_bootstrap: true,
    };
    return item;
  });
}

function detailBootstrapClaimsFromPayload(payload) {
  const fields = Array.isArray(payload?.fields) ? payload.fields : [];
  const values = Array.isArray(payload?.values) ? payload.values : [];
  const rows = Array.isArray(payload?.rows) ? payload.rows : [];
  if (!fields.length || !values.length || !rows.length) return [];

  return rows.map((row) => {
    const raw = {};
    fields.forEach((field, index) => {
      const value = values[Number(row[index]) || 0];
      if (value === null || value === undefined || value === "") return;
      raw[field] = value;
    });
    return {
      ...routeNativeFindingForCurrentUi(raw),
      __detail_bootstrap: true,
    };
  });
}

async function loadGraphBootstrapClaims(sourceKey) {
  const config = await loadGraphPayloadConfig();
  const path = activeGraphBootstrapPath(config, sourceKey);
  if (!path) return [];
  if (graphBootstrapPayloadPromises.has(path)) return graphBootstrapPayloadPromises.get(path);

  const task = fetchJsonFromCandidates(dataCandidates(path))
    .then(({ data }) => {
      const items = graphBootstrapClaimsFromPayload(data, sourceKey);
      graphBootstrapClaimsBySource.set(sourceKey, items);
      return items;
    })
    .catch(() => []);
  graphBootstrapPayloadPromises.set(path, task);
  return task;
}

async function loadDetailBootstrapClaims(sourceKey) {
  const config = await loadGraphPayloadConfig();
  const path = activeDetailBootstrapPath(config, sourceKey);
  if (!path) return [];
  if (detailBootstrapPayloadPromises.has(path)) return detailBootstrapPayloadPromises.get(path);

  const task = fetchJsonFromCandidates(dataCandidates(path))
    .then(({ data }) => detailBootstrapClaimsFromPayload(data))
    .catch(() => []);
  detailBootstrapPayloadPromises.set(path, task);
  return task;
}

function routeNativeSourceKey(finding) {
  const evidenceType = normalizeValue(finding.evidence_type || finding.kg_evidence_type);
  if (evidenceType !== "secondary_literature") return "primary";
  return isMetaAnalysisClaim(finding) ? "meta_analyses" : "reviews";
}

function routeNativeAccessLevel(finding) {
  const depth = normalizeValue(finding.text_depth || finding.access_level || finding.source_access_level);
  if (depth === "article_text" || depth === "full_text" || depth === "full_text_seen") return "full_text_seen";
  if (depth === "secondary_summary") return "secondary_summary";
  return "abstract_only";
}

function routeNativePaperType(value) {
  const type = normalizeValue(value);
  if (type === "primary_study") return "primary_results";
  return cleanDisplayText(value);
}

function routeNativeSourceType(value) {
  const type = normalizeValue(value);
  if (type === "primary") return "primary_study";
  return cleanDisplayText(value);
}

function routeNativeEntityLabel(finding) {
  return (
    cleanDisplayText(finding.entity_label) ||
    cleanDisplayText(finding.graph_entity_label) ||
    cleanDisplayText(finding.raw_entity_label) ||
    cleanDisplayText(finding.outcome_measure)
  );
}

function routeNativeGraphEntityLabel(finding) {
  if (normalizeValue(finding.domain || finding.kg_domain || finding.finding_type) === "pharmacokinetics_exposure") {
    return (
      cleanDisplayText(finding.pk_graph_object_label) ||
      cleanDisplayText(finding.pharmacokinetic_display_label) ||
      routeNativeEntityLabel(finding)
    );
  }
  return routeNativeEntityLabel(finding);
}

function routeNativeFindingForCurrentUi(finding) {
  const entityLabel = routeNativeEntityLabel(finding);
  const graphEntityLabel = routeNativeGraphEntityLabel(finding);
  const entityKind = cleanDisplayText(finding.entity_kind || finding.kg_entity_kind);
  const accessLevel = routeNativeAccessLevel(finding);
  const item = {
    ...finding,
    finding_type: cleanDisplayText(finding.finding_type || finding.domain),
    kg_domain: cleanDisplayText(finding.domain || finding.kg_domain),
    kg_entity_kind: entityKind,
    entity_kind: entityKind,
    kg_evidence_type: cleanDisplayText(finding.evidence_type || finding.kg_evidence_type),
    kg_relation_type: cleanDisplayText(finding.relation_type || finding.kg_relation_type),
    kg_source_name: "routed_extractions",
    paper_type: routeNativePaperType(finding.paper_type),
    source_type: routeNativeSourceType(finding.source_type),
    source_family: cleanDisplayText(finding.source_family),
    paper_assessment_route:
      cleanDisplayText(finding.paper_assessment_route) ||
      (isSecondarySourceKey(routeNativeSourceKey(finding)) ? "secondary_literature" : "primary_evidence"),
    access_level: accessLevel,
    source_access_level: accessLevel,
    evidence_location: cleanDisplayText(finding.evidence_location),
    evidence_locator: cleanDisplayText(finding.evidence_locator || finding.evidence_location),
    timepoint: cleanDisplayText(finding.assessment_timepoint || finding.timepoint),
  };
  item.graph_entity_label = graphEntityLabel || entityLabel;
  return item;
}

async function loadRouteNativeEvidenceSource(sourceKey) {
  const findings = await loadDetailBootstrapClaims(sourceKey);
  if (!Array.isArray(findings)) return false;
  const items = findings
    .filter((finding) => !isHiddenMainGraphItem(finding))
    .filter((finding) => routeNativeSourceKey(finding) === sourceKey)
    .map((finding) => routeNativeFindingForCurrentUi(finding));

  const enrichedItems = bibliographyPayloadsLoaded()
    ? enrichClaimsWithBibliographyMetadata(items)
    : items;
  // The routed detail payload is already canonical. Client-side legacy deduplication
  // collapsed distinct entities from the same paper and changed overview counts.
  claimStores.normalized.bySource[sourceKey] = enrichedItems;
  claimStores.normalized.all = Object.values(claimStores.normalized.bySource).flat();
  normalizedSourceLoaded[sourceKey] = true;
  activeClaimsMemo = null;
  entityCategoryCountsMemo = null;
  clearOverviewDetailCacheForSource(sourceKey);
  clearGraphDomCacheForSource(sourceKey, { preserveBootstrap: true });
  return true;
}

function currentSourceKey() {
  if (evidenceView === "meta_analyses") return "meta_analyses";
  if (evidenceView === "reviews" || evidenceView === "secondary") return "reviews";
  return "primary";
}

function evidenceViewForSourceKey(sourceKey) {
  if (sourceKey === "meta_analyses") return "meta_analyses";
  if (sourceKey === "reviews") return "reviews";
  return "primary";
}

function prewarmOverviewDetailEntry(sourceKey, viewKey, accessKey) {
  const sourceClaims = claimStores.normalized.bySource[sourceKey] || [];
  if (!sourceClaims.length) return;

  const evidenceKey = evidenceViewForSourceKey(sourceKey);
  const unconstrainedYearRange = { constrained: false, min: null, max: null };
  const cacheKey = overviewDetailCacheKeyForContext({
    sourceKey,
    sourceClaims,
    evidenceKey,
    viewKey,
    accessKey,
    yearRange: unconstrainedYearRange,
  });
  if (overviewDetailCache.has(cacheKey)) return;

  const previousState = {
    claimLayer,
    evidenceView,
    entityViewKey,
    accessView,
    claims,
    selected,
    isolateSelection,
    detailGraphFilter,
    activeClaimsMemo,
    yearMin: yearMinFilter?.value || "",
    yearMax: yearMaxFilter?.value || "",
    yearFilter: yearFilterState[viewKey] ? { ...yearFilterState[viewKey] } : null,
  };

  try {
    claimLayer = "normalized";
    evidenceView = evidenceKey;
    entityViewKey = viewKey;
    accessView = accessKey;
    claims = sourceClaims;
    selected = null;
    isolateSelection = false;
    detailGraphFilter = null;
    activeClaimsMemo = null;

    const modeClaims = graphViewClaims(
      claimsForEntityView(expandedClaimsWithUseContextProjections(sourceClaims))
    );
    const bounds = yearBoundsFromClaims(modeClaims);
    if (bounds && yearMinFilter && yearMaxFilter) {
      yearMinFilter.value = String(bounds.min);
      yearMaxFilter.value = String(bounds.max);
    }
    const filtered = applyFiltersToClaims(modeClaims, unconstrainedYearRange, { ignoreSearch: true }).filter(
      isMainGraphAdmitted
    );
    const allAccessFiltered = applyFiltersToClaims(modeClaims, unconstrainedYearRange, {
      ignoreAccess: true,
      ignoreSearch: true,
    }).filter(isMainGraphAdmitted);
    rememberOverviewDetail(cacheKey, createOverviewDetailCacheEntry(filtered, allAccessFiltered));
  } finally {
    claimLayer = previousState.claimLayer;
    evidenceView = previousState.evidenceView;
    entityViewKey = previousState.entityViewKey;
    accessView = previousState.accessView;
    claims = previousState.claims;
    selected = previousState.selected;
    isolateSelection = previousState.isolateSelection;
    detailGraphFilter = previousState.detailGraphFilter;
    activeClaimsMemo = previousState.activeClaimsMemo;
    if (yearMinFilter) yearMinFilter.value = previousState.yearMin;
    if (yearMaxFilter) yearMaxFilter.value = previousState.yearMax;
    if (previousState.yearFilter) {
      yearFilterState[viewKey] = previousState.yearFilter;
    } else {
      delete yearFilterState[viewKey];
    }
  }
}

function scheduleOverviewDetailPrewarmForSource(sourceKey, startDelay = 0) {
  const sourceClaims = claimStores.normalized.bySource[sourceKey] || [];
  if (!sourceClaims.length) return;
  const accessKey = accessView;
  const scheduleKey = [
    sourceKey,
    claimArrayId(sourceClaims),
    accessKey,
    expandedChartKeys.has("journals") ? "journals-expanded" : "journals-top",
  ].join("|");
  if (overviewDetailPrewarmScheduled.has(scheduleKey)) return;
  overviewDetailPrewarmScheduled.add(scheduleKey);

  ENTITY_CATEGORY_OPTIONS.forEach((option, index) => {
    scheduleIdleTask(
      () => prewarmOverviewDetailEntry(sourceKey, option.key, accessKey),
      startDelay + index * 140
    );
  });
}

function normalizedCurrentSourceLoaded() {
  return Boolean(normalizedSourceLoaded[currentSourceKey()]);
}


async function loadNormalizedClaimSource(sourceKey) {
  if (normalizedSourceLoaded[sourceKey]) return;
  if (normalizedSourceTasks[sourceKey]) {
    await normalizedSourceTasks[sourceKey];
    return;
  }

  normalizedSourceTasks[sourceKey] = (async () => {
    if (!(await loadRouteNativeEvidenceSource(sourceKey))) {
      throw new Error("Route-native graph payload is unavailable");
    }
  })();

  try {
    await normalizedSourceTasks[sourceKey];
  } finally {
    normalizedSourceTasks[sourceKey] = null;
  }
}

async function ensureClaimsForCurrentView() {
  await loadNormalizedClaimSource(currentSourceKey());
}

function waitForPaint() {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => window.requestAnimationFrame(resolve));
  });
}

async function renderCurrentGraphBootstrap(loadToken, resetDetail = true) {
  if (claimLayer !== "normalized") return false;
  const sourceKey = currentSourceKey();
  const bootstrapClaims = await loadGraphBootstrapClaims(sourceKey);
  if (loadToken !== currentDataLoadToken) return true;
  if (!bootstrapClaims.length) return false;

  updateModeUI();
  const graphClaims = graphViewClaims(
    claimsForEntityView(expandedClaimsWithUseContextProjections(bootstrapClaims))
  );
  const filtered = graphClaims.length ? applyFiltersToClaims(graphClaims, null, { ignoreSearch: true }) : [];

  if (filtered.length) buildGraph(filtered);
  if (resetDetail) {
    clearDetailForTransition();
    cardsEl.innerHTML = '<div class="detail-empty">Loading findings...</div>';
    if (studyListEl) {
      studyListEl.innerHTML = "";
    }
  }
  return true;
}

function canonicalOverviewBootstrapClaims() {
  if (claimLayer !== "normalized" || selected || detailGraphFilter) return null;

  const detailClaims = activeClaimsForMode();
  const yearRange = activeYearRange(detailClaims);
  if (yearRange.constrained) return null;

  const bootstrapClaims = graphBootstrapClaimsBySource.get(currentSourceKey());
  if (!bootstrapClaims?.length) return null;

  const graphClaims = graphViewClaims(
    claimsForEntityView(expandedClaimsWithUseContextProjections(bootstrapClaims))
  );
  return applyFiltersToClaims(
    graphClaims,
    { constrained: false, min: null, max: null },
    { ignoreSearch: true }
  );
}

async function loadCurrentClaimsAndRender({ showLoading = true, resetDetail = true, showGraphBootstrap = false } = {}) {
  const token = ++currentDataLoadToken;
  const sourceWasLoaded = normalizedCurrentSourceLoaded();
  let bootstrapRendered = false;
  if (showGraphBootstrap) {
    bootstrapRendered = await renderCurrentGraphBootstrap(token, resetDetail);
  }
  if (token !== currentDataLoadToken) return;

  if (showLoading && !bootstrapRendered) {
    renderDataLoading();
  }
  if (bootstrapRendered) {
    retainVisibleBootstrapGraph = true;
    await waitForPaint();
  }
  if (token !== currentDataLoadToken) return;

  try {
    await ensureClaimsForCurrentView();
  } catch (error) {
    if (token === currentDataLoadToken) {
      renderLoadError([`Graph data: ${error.message}`]);
    }
    return;
  }

  if (token !== currentDataLoadToken) return;

  applyClaimLayerStore();
  if (!sourceWasLoaded) updateModeUI();
  syncYearFilterControls(activeClaimsForMode(), true);
  if (resetDetail && !bootstrapRendered) {
    clearDetailForTransition();
  }
  scheduleRender();
}

function loadBibliographyPayloadsInBackground() {
  if (bibliographyPayloadsPromise) return bibliographyPayloadsPromise;
  bibliographyPayloadsPromise = loadBibliographyPayloads()
    .then(() => {
      enrichAllLoadedClaimsWithBibliography();
      applyClaimLayerStore();
      scheduleRender();
    })
    .catch(() => {
      bibliographyPayloadsPromise = null;
    });
  return bibliographyPayloadsPromise;
}

function scheduleIdleTask(callback, delay = 0) {
  window.setTimeout(() => {
    if ("requestIdleCallback" in window) {
      window.requestIdleCallback(callback, { timeout: 3500 });
      return;
    }
    callback();
  }, delay);
}

function preloadNormalizedSourceInBackground(sourceKey, delay) {
  scheduleIdleTask(() => {
    loadNormalizedClaimSource(sourceKey)
      .then(() => {
        scheduleOverviewDetailPrewarmForSource(sourceKey, 900);
        if (currentSourceKey() === sourceKey) {
          applyClaimLayerStore();
          updateModeUI();
          updateStats();
        }
      })
      .catch(() => {});
  }, delay);
}

function preloadLikelyNextData() {
  const saveData = Boolean(window.navigator?.connection?.saveData);
  const activeSourceKey = currentSourceKey();
  const queue = saveData
    ? []
    : activeSourceKey === "primary"
      ? ["meta_analyses", "reviews"]
      : ["primary"];
  const seen = new Set();

  queue.forEach((sourceKey, index) => {
    if (seen.has(sourceKey)) return;
    seen.add(sourceKey);
    preloadNormalizedSourceInBackground(sourceKey, 650 + index * 900);
  });
  scheduleIdleTask(loadBibliographyPayloadsInBackground, saveData ? 3000 : 4200);
}

async function init() {
  await loadGraphManifestStats();
  await loadCurrentClaimsAndRender({ showLoading: true, resetDetail: true, showGraphBootstrap: true });
  scheduleOverviewDetailPrewarmForSource(currentSourceKey());
  preloadLikelyNextData();
}

if (yearMinFilter) {
  yearMinFilter.addEventListener("change", () => {
    retainVisibleBootstrapGraph = false;
    scheduleRender();
  });
}
if (yearMaxFilter) {
  yearMaxFilter.addEventListener("change", () => {
    retainVisibleBootstrapGraph = false;
    scheduleRender();
  });
}
if (yearStepButtons.length) {
  yearStepButtons.forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      const targetId = btn.dataset.target || "";
      const dir = btn.dataset.dir || "";
      const input = document.getElementById(targetId);
      if (!(input instanceof HTMLInputElement) || input.disabled) return;
      if (dir === "up") input.stepUp();
      if (dir === "down") input.stepDown();
      input.dispatchEvent(new Event("change", { bubbles: true }));
      input.focus({ preventScroll: true });
    });
  });
}
if (searchInput) {
  searchInput.addEventListener("input", () => {
    scheduleFindingSearchRender();
  });
}
if (bibliographySearchInput) {
  bibliographySearchInput.addEventListener("input", () => {
    renderBibliography(applyFilters({ ignoreSearch: true }));
  });
}
if (detailBody) {
  detailBody.addEventListener("click", (event) => {
    const accessCard = event.target.closest?.("[data-access-view]");
    if (!accessCard || !detailBody.contains(accessCard)) return;
    event.preventDefault();
    setAccessView(accessCard.dataset.accessView || "");
  });
  detailBody.addEventListener("mouseover", (event) => {
    const target = event.target.closest?.(".sample-heatmap-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.relatedTarget && target.contains(event.relatedTarget)) return;
    target.classList.add("hovered");
    showTooltip(sampleHeatmapTooltipHtml(target), event);
  });
  detailBody.addEventListener("mouseover", (event) => {
    const target = event.target.closest?.(".publication-year-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.relatedTarget && target.contains(event.relatedTarget)) return;
    target.classList.add("hovered");
    showTooltip(publicationYearTooltipHtml(target), event);
  });
  detailBody.addEventListener("mouseover", (event) => {
    const target = event.target.closest?.(".interactive-bar, .composition-filter-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.relatedTarget && target.contains(event.relatedTarget)) return;
    target.classList.add("hovered");
    showTooltip(horizontalBarTooltipHtml(target), event);
  });
  detailBody.addEventListener("mousemove", (event) => {
    const target = event.target.closest?.(".sample-heatmap-target");
    if (!target || !detailBody.contains(target)) return;
    moveTooltip(event);
  });
  detailBody.addEventListener("mousemove", (event) => {
    const target = event.target.closest?.(".publication-year-target");
    if (!target || !detailBody.contains(target)) return;
    moveTooltip(event);
  });
  detailBody.addEventListener("mousemove", (event) => {
    const target = event.target.closest?.(".interactive-bar, .composition-filter-target");
    if (!target || !detailBody.contains(target)) return;
    moveTooltip(event);
  });
  detailBody.addEventListener("mouseout", (event) => {
    const target = event.target.closest?.(".sample-heatmap-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.relatedTarget && target.contains(event.relatedTarget)) return;
    target.classList.remove("hovered");
    hideTooltip();
  });
  detailBody.addEventListener("mouseout", (event) => {
    const target = event.target.closest?.(".publication-year-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.relatedTarget && target.contains(event.relatedTarget)) return;
    target.classList.remove("hovered");
    hideTooltip();
  });
  detailBody.addEventListener("mouseout", (event) => {
    const target = event.target.closest?.(".interactive-bar, .composition-filter-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.relatedTarget && target.contains(event.relatedTarget)) return;
    target.classList.remove("hovered");
    hideTooltip();
  });
  detailBody.addEventListener("focusin", (event) => {
    const target = event.target.closest?.(".sample-heatmap-target");
    if (!target || !detailBody.contains(target)) return;
    target.classList.add("hovered");
    showTooltipForElement(sampleHeatmapTooltipHtml(target), target);
  });
  detailBody.addEventListener("focusin", (event) => {
    const target = event.target.closest?.(".publication-year-target");
    if (!target || !detailBody.contains(target)) return;
    target.classList.add("hovered");
    showTooltipForElement(publicationYearTooltipHtml(target), target);
  });
  detailBody.addEventListener("focusin", (event) => {
    const target = event.target.closest?.(".interactive-bar, .composition-filter-target");
    if (!target || !detailBody.contains(target)) return;
    target.classList.add("hovered");
    showTooltipForElement(horizontalBarTooltipHtml(target), target);
  });
  detailBody.addEventListener("focusout", (event) => {
    const target = event.target.closest?.(".sample-heatmap-target");
    if (!target || !detailBody.contains(target)) return;
    target.classList.remove("hovered");
    hideTooltip();
  });
  detailBody.addEventListener("focusout", (event) => {
    const target = event.target.closest?.(".publication-year-target");
    if (!target || !detailBody.contains(target)) return;
    target.classList.remove("hovered");
    hideTooltip();
  });
  detailBody.addEventListener("focusout", (event) => {
    const target = event.target.closest?.(".interactive-bar, .composition-filter-target");
    if (!target || !detailBody.contains(target)) return;
    target.classList.remove("hovered");
    hideTooltip();
  });
  detailBody.addEventListener("click", (event) => {
    const restoreButton = event.target.closest?.("[data-detail-action='restore']");
    if (restoreButton && detailBody.contains(restoreButton)) {
      restoreCurrentDetailPanel();
      return;
    }

    const target = event.target.closest?.(".sample-heatmap-target");
    if (!target || !detailBody.contains(target)) return;
    event.preventDefault();
    hideTooltip();
    renderSampleHeatmapDetail(
      target.dataset.yearStart || "",
      target.dataset.yearEnd || "",
      target.dataset.sampleMin || "",
      target.dataset.sampleMax || "",
      `${target.dataset.yearLabel || ""}, N=${target.dataset.sampleLabel || ""}`
    );
  });
  detailBody.addEventListener("click", (event) => {
    const target = event.target.closest?.(".publication-year-target");
    if (!target || !detailBody.contains(target)) return;
    event.preventDefault();
    hideTooltip();
    renderPublicationYearDetail(target.dataset.yearStart || "", target.dataset.yearEnd || "", target.dataset.yearLabel || "");
  });
  detailBody.addEventListener("click", (event) => {
    const target = event.target.closest?.(".chart-expand-toggle[data-chart-expand-key]");
    if (!target || !detailBody.contains(target)) return;
    event.preventDefault();
    hideTooltip();
    const key = target.dataset.chartExpandKey || "";
    if (expandedChartKeys.has(key)) {
      expandedChartKeys.delete(key);
    } else {
      expandedChartKeys.add(key);
    }
    const chartCard = target.closest(".trend-card");
    if (key === "journals" && chartCard) {
      chartCard.outerHTML = renderJournalChart(activeDetailItems);
      rekeyActiveOverviewDetail();
    }
  });
  detailBody.addEventListener("click", (event) => {
    const target = event.target.closest?.(".interactive-bar, .composition-filter-target");
    if (!target || !detailBody.contains(target)) return;
    event.preventDefault();
    hideTooltip();
    if (target.dataset.filterField === "outcome_scale_facet") {
      renderOutcomeScaleDetail(target.dataset.filterValue || target.dataset.filterLabel || "");
      return;
    }
    renderFieldValueDetail(target.dataset.filterField || "", target.dataset.filterValue || "", target.dataset.filterLabel || "");
  });
  detailBody.addEventListener("keydown", (event) => {
    const target = event.target.closest?.(".sample-heatmap-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    hideTooltip();
    renderSampleHeatmapDetail(
      target.dataset.yearStart || "",
      target.dataset.yearEnd || "",
      target.dataset.sampleMin || "",
      target.dataset.sampleMax || "",
      `${target.dataset.yearLabel || ""}, N=${target.dataset.sampleLabel || ""}`
    );
  });
  detailBody.addEventListener("keydown", (event) => {
    const target = event.target.closest?.(".publication-year-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    hideTooltip();
    renderPublicationYearDetail(target.dataset.yearStart || "", target.dataset.yearEnd || "", target.dataset.yearLabel || "");
  });
  detailBody.addEventListener("keydown", (event) => {
    const target = event.target.closest?.(".interactive-bar, .composition-filter-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    hideTooltip();
    if (target.dataset.filterField === "outcome_scale_facet") {
      renderOutcomeScaleDetail(target.dataset.filterValue || target.dataset.filterLabel || "");
      return;
    }
    renderFieldValueDetail(target.dataset.filterField || "", target.dataset.filterValue || "", target.dataset.filterLabel || "");
  });
  detailBody.addEventListener("click", (event) => {
    const target = event.target.closest?.(".scale-chip[data-outcome-scale]");
    if (!target || !detailBody.contains(target)) return;
    event.preventDefault();
    renderOutcomeScaleDetail(target.dataset.outcomeScale || "");
  });
  detailBody.addEventListener("click", (event) => {
    const target = event.target.closest?.(".facet-chip[data-filter-field]");
    if (!target || !detailBody.contains(target)) return;
    event.preventDefault();
    hideTooltip();
    renderFieldValueDetail(target.dataset.filterField || "", target.dataset.filterValue || "", target.dataset.filterLabel || "");
  });
}
graphEl.addEventListener("click", (event) => {
  if (event.target === graphEl || event.target.tagName?.toLowerCase() === "svg") {
    clearSelection();
  }
});
claimLayerButtons.forEach((button) => {
  button.addEventListener("click", () => {
    switchClaimLayer(button.dataset.claimLayer);
  });
});
evidenceViewButtons.forEach((button) => {
  button.addEventListener("click", () => {
    switchEvidenceView(button.dataset.evidenceView);
  });
});
if (entityKindToggle) {
  entityKindToggle.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-entity-view]");
    if (!button || !entityKindToggle.contains(button)) return;
    switchEntityView(button.dataset.entityView || "");
  });
}
window.addEventListener("resize", scheduleRender);

init();
