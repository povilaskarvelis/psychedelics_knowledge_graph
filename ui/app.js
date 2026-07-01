const graphEl = document.getElementById("graph");
const cardsEl = document.getElementById("cards");
const yearMinFilter = document.getElementById("yearMinFilter");
const yearMaxFilter = document.getElementById("yearMaxFilter");
const yearStepButtons = document.querySelectorAll(".year-step");
const searchInput = document.getElementById("searchInput");
const bibliographySearchInput = document.getElementById("bibliographySearchInput");
const fullTextOnlyToggle = document.getElementById("fullTextOnlyToggle");
const tooltip = document.getElementById("tooltip");
const detailTitle = document.querySelector("#graphDetail h3");
const detailBody = document.getElementById("detailBody");
const modeButtons = document.querySelectorAll("[data-mode]");
const claimLayerButtons = document.querySelectorAll("[data-claim-layer]");
const evidenceViewButtons = document.querySelectorAll("[data-evidence-view]");
const entityKindToggle = document.querySelector("[data-entity-kind-toggle]");
const studiesStatCard = document.getElementById("studiesStatCard");
const bibliographyPanel = document.getElementById("bibliographyPanel");
const studyListEl = document.getElementById("studyList");
const dataFetchOptions =
  ["", "localhost", "127.0.0.1", "::1"].includes(window.location.hostname) ? { cache: "no-store" } : {};

if (tooltip && tooltip.parentElement !== document.body) {
  document.body.appendChild(tooltip);
}

const stats = {
  compounds: document.querySelector('[data-stat="compounds"]'),
  conditions: document.querySelector('[data-stat="conditions"]'),
  targets: document.querySelector('[data-stat="targets"]'),
  studies: document.querySelector('[data-stat="studies"]'),
};
const statDetails = {
  studies: document.querySelector('[data-stat-detail="studies"]'),
};

const HERO_STAT_KEYS = ["studies", "compounds", "conditions", "targets"];
const evidenceRank = { low: 1, medium: 2, high: 3 };
const MAX_GRAPH_EDGES = 500;
/** Chunk size for progressive rendering (IntersectionObserver loads more while scrolling). */
const LIST_CHUNK_SIZE = 120;

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
  "#49bfb5",
  "#c89b45",
  "#9f86c0",
  "#7f9fcf",
  "#b96c8b",
  "#9ac5ae",
  "#c7825c",
  "#7d8492",
];
const SYSTEM_COLORS = {
  clinical: "#49bfb5",
  preclinical: "#c89b45",
  in_vitro: "#7f9fcf",
  in_vivo: "#b96c8b",
  ex_vivo: "#9f86c0",
  observational: "#9ac5ae",
  unknown: "#7d8492",
};
const PUBLICATION_YEAR_COLOR = "#3faea6";
const SAMPLE_SIZE_HEATMAP_COLOR = "#c89b45";
const COGNITION_NODE_LABELS = [
  "Attention",
  "Cognitive flexibility",
  "Emotional processing",
  "Executive function",
  "Fear extinction",
  "Fear memory",
  "Inhibitory control",
  "Memory",
  "Recognition memory",
  "Reward processing",
  "Social cognition",
  "Spatial memory",
  "Working memory",
];
const BEHAVIORAL_EFFECT_NODE_LABELS = [
  "Conditioned place preference",
  "Drug discrimination",
  "Drug seeking",
  "Drug self-administration",
  "Head-twitch response",
  "Motor coordination",
  "Pain behavior",
  "Psychomotor sensitization",
  "Sensorimotor gating",
  "Social interaction",
  "Stress-coping behavior",
  "Threat avoidance",
];
const ENTITY_VIEW_OPTIONS = {
  disorders: [
    { key: "condition_indication", label: "Conditions", singular: "Condition", lowerPlural: "conditions", lowerSingular: "condition" },
    {
      key: "safety_adverse_event",
      label: "Safety",
      singular: "Safety event",
      lowerPlural: "safety events",
      lowerSingular: "safety event",
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
      label: "Therapy context",
      singular: "Therapy context",
      lowerPlural: "therapy context nodes",
      lowerSingular: "therapy context node",
    },
    {
      key: "public_health_measure",
      label: "Naturalistic use",
      singular: "Naturalistic use pattern",
      lowerPlural: "naturalistic use patterns",
      lowerSingular: "naturalistic use pattern",
    },
  ],
  mechanistic: [
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
  ],
};
const ENTITY_CATEGORY_OPTIONS = [
  ...ENTITY_VIEW_OPTIONS.disorders.map((option) => ({ mode: "disorders", ...option })),
  ...ENTITY_VIEW_OPTIONS.mechanistic.map((option) => ({ mode: "mechanistic", ...option })),
];
const DETAIL_PANEL_PROFILE_DEFAULT = {
  experimentalSystem: false,
  sampleSizes: false,
  populationModel: false,
  comparators: false,
  followUpWindows: false,
  assayFamilies: false,
  mechanisticRelationshipTypes: false,
  safetyContexts: false,
  doseRouteSessionContexts: false,
  studyDesigns: true,
  outcomeScales: false,
  publicHealthTopics: false,
  publicHealthDataSources: false,
  trialRegistration: false,
};
const DETAIL_PANEL_PROFILE_BY_VIEW = {
  clinical_default: {
    sampleSizes: true,
    populationModel: true,
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
    populationModel: true,
    doseRouteSessionContexts: true,
    comparators: true,
    followUpWindows: true,
    outcomeScales: true,
    trialRegistration: true,
  },
  symptom_problem: {
    sampleSizes: true,
    populationModel: true,
    doseRouteSessionContexts: true,
    comparators: true,
    followUpWindows: true,
    outcomeScales: true,
    trialRegistration: true,
  },
  safety_adverse_event: {
    sampleSizes: true,
    populationModel: true,
    safetyContexts: true,
    doseRouteSessionContexts: true,
    trialRegistration: true,
  },
  cognitive_behavioral_construct: {
    sampleSizes: true,
    populationModel: true,
    doseRouteSessionContexts: true,
    comparators: true,
    followUpWindows: true,
    trialRegistration: true,
  },
  behavioral_effect: {
    sampleSizes: true,
    populationModel: true,
    doseRouteSessionContexts: true,
    comparators: true,
    followUpWindows: true,
    trialRegistration: true,
  },
  subjective_experience_construct: {
    sampleSizes: true,
    populationModel: true,
    doseRouteSessionContexts: true,
    followUpWindows: true,
    trialRegistration: true,
  },
  intervention_component: {
    sampleSizes: true,
    populationModel: true,
    doseRouteSessionContexts: true,
  },
  public_health_measure: {
    sampleSizes: true,
    populationModel: true,
    publicHealthDataSources: true,
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
    populationModel: true,
    assayFamilies: true,
    mechanisticRelationshipTypes: true,
  },
};
const ROUTE_NATIVE_DISPLAY_MODE_BY_DOMAIN = {
  molecular_target: "mechanistic",
  molecular_pathway_readout: "mechanistic",
  brain_system: "mechanistic",
  clinical_outcome: "disorders",
  safety_tolerability: "disorders",
  cognitive_behavioral: "disorders",
  subjective_experience: "disorders",
  real_world_public_health: "disorders",
  intervention_context: "disorders",
};
const ROUTE_NATIVE_MECHANISTIC_ENTITY_KINDS = new Set([
  "target",
  "pathway_process",
  "molecular_readout",
  "biomarker_readout",
  "system_family",
  "brain_region",
  "brain_network",
  "neural_circuit",
]);

let claims = [];
let disorderClaims = [];
const claimStores = {
  normalized: { mechanistic: [], disorders: [] },
  extracted: { mechanistic: [], disorders: [] },
};
let bibliographyByMode = {
  mechanistic: [],
  disorders: [],
};
let graphPreviewByMode = {
  mechanistic: { primary: [], secondary: [] },
  disorders: { primary: [], secondary: [] },
};
let selected = null;
let isolateSelection = false;
let mode = "disorders";
let claimLayer = "normalized";
let evidenceView = "primary";
const EVIDENCE_VIEW_KEYS = ["primary", "meta_analyses", "reviews", "secondary"];
const SECONDARY_EVIDENCE_VIEW_KEYS = new Set(["meta_analyses", "reviews", "secondary"]);
let entityView = {
  disorders: "condition_indication",
  mechanistic: "target_system",
};
let renderScheduled = false;
let activeDetailItems = [];
let detailGraphFilter = null;
const expandedChartKeys = new Set();
let currentDataLoadToken = 0;
let heroStatsSnapshot = null;
let graphManifestPromise = null;
let graphPayloadConfigPromise = null;
let routeNativeEvidencePayloadPromise = null;
let routeNativeEvidencePreviewPromise = null;
let bibliographyPayloadsPromise = null;
let tooltipFrame = 0;
let pendingTooltipPoint = null;
let tooltipSize = { width: 240, height: 40 };
const yearFilterState = {
  mechanistic: { min: "", max: "" },
  disorders: { min: "", max: "" },
};

const defaultDetail = {
  title: "Graph Detail",
};

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
const GRAPH_LABEL_MAX_WIDTH_PX = 190;
const GRAPH_RIGHT_LABEL_GUTTER_PX = 42;
const GRAPH_BASE_HEIGHT_PX = 820;
const GRAPH_COMPACT_BASE_HEIGHT_PX = 560;
const GRAPH_MIN_NODE_SPACING_PX = 40;
const GRAPH_COMPACT_MIN_NODE_SPACING_PX = 38;
const HIDDEN_MAIN_GRAPH_DOMAINS = new Set(["pharmacokinetics_exposure"]);

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

function unique(values) {
  return Array.from(new Set(values)).sort();
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

const PATHWAY_READOUT_FAMILY_RULES = [
  {
    label: "Gut microbiome",
    pattern: /\b(gut|microbiome|microbiota|microbial|bacteri\w*|fecal|faecal|short chain fatty acids?|scfa)\b/,
  },
  {
    label: "Inflammation",
    pattern:
      /\b(inflamm\w*|cytokine\w*|interleukin\w*|il[- ]?\d+\w*|tnf|nf[- ]?kappa[- ]?b|nf[- ]?kb|cox[- ]?2|prostaglandin\w*|microglia\w*|astrocyt\w*|glial|gfap|iba[- ]?1|complement|crp|hmgb1|tlr[- ]?4|tgf[- ]?beta)\b/,
  },
  {
    label: "Cellular stress",
    pattern:
      /\b(oxidative stress|reactive oxygen|\bros\b|lipid peroxidation|malondialdehyde|\bmda\b|glutathione|\bgsh\b|\bsod\b|catalase|apoptosis|caspase|cell death|necrosis|hsp[- ]?70|heat shock|neurotox\w*|toxicity|toxic marker|neurofilament|\bnfl\b|s100b)\b/,
  },
  {
    label: "Neuroplasticity",
    pattern:
      /\b(bdnf|trkb|trk b|ngf|gdnf|vegf|igf[- ]?1|insulin[- ]like growth factor|neurotroph\w*|growth factor\w*|plasticity|synaptic|synapse|dendritic|spine|neurogenesis|neurite|synaptogenesis|long[- ]?term potentiation|ltp|long[- ]?term depression|ltd|psd[- ]?95|synaptophysin|arc|sv2a|synaptic vesicle|perineuronal net)\b/,
  },
  {
    label: "Intracellular signaling",
    pattern:
      /\b(erk|mapk|mtor|mtorc1|akt|camp|creb|pka|pkc|plc|pi3k|gsk[- ]?3|p70s6k|stat3|jnk|phosphorylation|phosphorylated|phospho|second messenger\w*|kinase\w*|signal(?:ing|ling)|phosphoinositide)\b/,
  },
  {
    label: "Immediate early gene activation",
    pattern:
      /\b(c[- ]?fos|fosb|egr[- ]?1|immediate early|neuronal activation|neural activation|neural activity|neuronal activity)\b/,
  },
  {
    label: "Serotonin signaling",
    pattern: /\b(serotonin|5[- ]?hydroxytryptamine|5[- ]?hiaa|5[- ]?ht\d?[a-z]?|sert|slc6a4)\b/,
  },
  {
    label: "Dopamine signaling",
    pattern: /\b(dopamine|\bdopa\b|dopac|\bhva\b|\bdat\b|slc6a3|d[1-5][ -]?receptor)\b/,
  },
  {
    label: "Glutamate signaling",
    pattern: /\b(glutamate|glutamatergic|ampa|nmda|nmdar|ampar|mglur|mglu\d?|glua\d?|glun\d?|vglut)\b/,
  },
  {
    label: "GABA signaling",
    pattern: /\b(gaba|gabaergic|gabr|gad[- ]?65|gad[- ]?67)\b/,
  },
  {
    label: "Epigenetic regulation",
    pattern: /\b(epigen\w*|dna methylation|methylation|histone\w*|chromatin)\b/,
  },
  {
    label: "Genetic moderators",
    pattern: /\b(polymorphism\w*|genotype\w*|phenotype interaction|allele\w*|rs\d+)\b/,
  },
  {
    label: "Gene expression",
    pattern: /\b(gene expression|transcript\w*|transcriptom\w*|mrna|rna|mirna|microrna)\b/,
  },
  {
    label: "Drug metabolism",
    pattern: /\b(cyp\d+\w*|cytochrome p450|ugt\d*\w*|monoamine oxidase|mao[- ]?[ab]?|comt|metabolic enzyme\w*|in vitro metabolism)\b/,
  },
  {
    label: "Endocrine response",
    pattern: /\b(cortisol|corticosterone|acth|prolactin|hormone\w*|endocrine|melatonin|oxytocin|vasopressin)\b/,
  },
  {
    label: "Norepinephrine signaling",
    pattern: /\b(norepinephrine|noradrenaline|\bne\b|\bna\b|slc6a2|net\b)\b/,
  },
  {
    label: "Neuronal excitability",
    pattern:
      /\b(firing rate|spik(?:e|ing)|calcium imaging|calcium flux|electrophysiolog\w*|oscillation\w*|gamma|theta|field potential\w*|currents?|\bepscs?\b|\bipscs?\b|\bmepscs?\b|\bmipscs?\b)\b/,
  },
  {
    label: "Receptor regulation",
    pattern:
      /\b(receptor\w*|transport(?:er|ers)|availability|binding potential|densit(?:y|ies)|occupancy|trafficking|surface expression|internalization|uptake site)\b/,
  },
];

function usesPathwayReadoutFamilies() {
  return claimLayer === "normalized" && mode === "mechanistic" && currentEntityViewKey() === "pathway_readout";
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
  const rule = PATHWAY_READOUT_FAMILY_RULES.find((item) => item.pattern.test(text));
  return rule?.label || "Other molecular effects";
}

function specificPathwayReadoutLabel(claim) {
  return (
    graphLabel(claim?.target) ||
    meaningfulText(claim?.graph_entity_label) ||
    meaningfulText(claim?.raw_entity_label) ||
    meaningfulText(claim?.canonical_entity)
  );
}

function pathwayReadoutFamilyForClaim(claim) {
  const nativeLabel = meaningfulText(claim?.molecular_effect_label);
  if (nativeLabel) return nativeLabel;
  const specificLabel = specificPathwayReadoutLabel(claim);
  if (!specificLabel) return "";
  const labelText = pathwayReadoutMatchText([
    specificLabel,
    claim?.graph_entity_label,
    claim?.raw_entity_label,
    claim?.canonical_entity,
  ]);
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
  return rule?.label || "Other molecular effects";
}

function graphRightLabelForClaim(claim) {
  const rightKey = rightEntityKey();
  const right = graphLabel(claim?.[rightKey]);
  if (!right) return "";
  if (usesPathwayReadoutFamilies()) return pathwayReadoutFamilyForClaim(claim);
  return right;
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
  return sameGraphLabel(compoundGraphLabel(claim?.compound), compound);
}

function claimMatchesGraphRight(claim, right) {
  return sameGraphLabel(graphRightLabelForClaim(claim), right);
}

function claimMatchesGraphEdge(claim, compound, right) {
  return claimMatchesGraphCompound(claim, compound) && claimMatchesGraphRight(claim, right);
}

function rightEntityKey() {
  return mode === "mechanistic" ? "target" : "disorder";
}

function entityViewOptionsForMode() {
  return ENTITY_VIEW_OPTIONS[mode] || [];
}

function currentEntityViewKey() {
  const options = entityViewOptionsForMode();
  const selectedKey = entityView[mode];
  if (options.some((option) => option.key === selectedKey)) return selectedKey;
  return options[0]?.key || "";
}

function currentEntityViewOption() {
  const key = currentEntityViewKey();
  return entityViewOptionsForMode().find((option) => option.key === key) || null;
}

function detailPanelProfileForKey(key) {
  return {
    ...DETAIL_PANEL_PROFILE_DEFAULT,
    ...(DETAIL_PANEL_PROFILE_BY_VIEW[key] || {}),
  };
}

function currentDetailPanelProfile() {
  const fallbackKey = mode === "mechanistic" ? "mechanistic_default" : "clinical_default";
  if (claimLayer !== "normalized") return detailPanelProfileForKey(fallbackKey);
  return detailPanelProfileForKey(currentEntityViewKey() || fallbackKey);
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
  const activeKinds = new Set(entityKindsForViewOption(option));
  if (activeKinds.size && !activeKinds.has(entityKindForClaim(claim))) return false;
  const activeDomains = new Set(entityDomainsForViewOption(option).map(normalizeValue).filter(Boolean));
  if (activeDomains.size && !activeDomains.has(normalizeValue(claim.kg_domain || claim.domain || claim.finding_type))) return false;
  const activeLabels = new Set(entityLabelsForViewOption(option).map(normalizeValue).filter(Boolean));
  if (activeLabels.size && !activeLabels.has(normalizeValue(graphRightLabelForClaim(claim)))) return false;
  return true;
}

function rightEntityLabel(plural = true) {
  if (claimLayer !== "normalized") {
    return mode === "mechanistic"
      ? plural
        ? "Mechanistic nodes"
        : "Mechanistic node"
      : plural
        ? "Clinical nodes"
        : "Clinical node";
  }
  const option = currentEntityViewOption();
  if (!option) return mode === "mechanistic" ? (plural ? "Targets" : "Target") : plural ? "Conditions" : "Condition";
  return plural ? option.label : option.singular;
}

function lowerRightEntityLabel(plural = true) {
  if (claimLayer !== "normalized") {
    return mode === "mechanistic"
      ? plural
        ? "mechanistic nodes"
        : "mechanistic node"
      : plural
        ? "clinical nodes"
        : "clinical node";
  }
  const option = currentEntityViewOption();
  if (!option) return mode === "mechanistic" ? (plural ? "targets" : "target") : plural ? "conditions" : "condition";
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
  const baseClaims = mode === "mechanistic" ? claims : disorderClaims;
  return graphViewClaims(claimsForEntityView(baseClaims));
}

function passesAccessAndYearFilters(claim, yearRange) {
  if (fullTextOnlyToggle?.checked && claimSourceAccessLevel(claim) !== "full_text_seen") {
    return false;
  }
  if (yearRange?.constrained) {
    const year = parseYearValue(claim.study_year);
    if (year === null) return false;
    if (year < yearRange.min || year > yearRange.max) return false;
  }
  return true;
}

function activeOutcomeScaleClaims() {
  if (mode !== "disorders" || evidenceView !== "primary") return [];
  const yearRange = activeYearRange(activeClaimsForMode());
  return graphViewClaims(disorderClaims)
    .filter((claim) => isOutcomeScaleClaim(claim))
    .filter((claim) => passesAccessAndYearFilters(claim, yearRange));
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
  const compound = normalizeValue(claim.compound);
  if (!study || !compound) return "";
  return `${study}|compound:${compound}`;
}

function outcomeScaleClaimsForChart(items) {
  const scaleItems = items.filter((claim) => isOutcomeScaleClaim(claim));
  if (scaleItems.length) return scaleItems;

  const activeScaleClaims = activeOutcomeScaleClaims();
  const scopeKeys = new Set(items.map(evidenceScopeKey).filter(Boolean));
  if (!scopeKeys.size) return activeScaleClaims;
  return activeScaleClaims.filter((claim) => scopeKeys.has(evidenceScopeKey(claim)));
}

function setDetailGraphFilter(items) {
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

function applyClaimLayerStore() {
  const store = claimStores[claimLayer] || claimStores.normalized;
  claims = store.mechanistic || [];
  disorderClaims = store.disorders || [];
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

function secondaryLiteratureClaims(baseClaims) {
  return baseClaims.filter(isSecondaryLiteratureClaim);
}

function isSecondaryEvidenceView(view = evidenceView) {
  return SECONDARY_EVIDENCE_VIEW_KEYS.has(view);
}

function recordLabelsForItems(items = []) {
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

function claimIdentity(claim, index) {
  const rightKey = claim.target !== undefined ? "target" : "disorder";
  const parts = [
    claim.compound || "",
    claim[rightKey] || "",
    claim.study_doi || "",
    claim.openalex_id || "",
    claim.mechanism_type || "",
    claim.assay_type || "",
    claim.assay_family || "",
    claim.action_type || "",
    claim.affinity_type || "",
    claim.affinity_value || "",
    claim.outcome_type || "",
    claim.outcome_measure || "",
    claim.sample_size_total || "",
    claim.timepoint || "",
    claim.comparator || "",
    claim.evidence_locator || "",
    claim.supporting_quote || "",
  ];
  const key = parts.join("|");
  return key.replace(/\|/g, "") ? key : `claim-${index}`;
}

function dedupeClaims(items) {
  const seen = new Set();
  const out = [];
  items.forEach((claim, index) => {
    const key = claimIdentity(claim, index);
    if (seen.has(key)) return;
    seen.add(key);
    out.push(claim);
  });
  return out;
}

function graphViewClaims(baseClaims) {
  const visibleClaims = baseClaims.filter((claim) => !isHiddenMainGraphItem(claim));
  if (isSecondaryEvidenceView()) return secondaryLiteratureClaims(visibleClaims);
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

  const bounds = yearBoundsFromClaims(data);
  if (!bounds) {
    yearMinFilter.value = "";
    yearMaxFilter.value = "";
    yearMinFilter.disabled = true;
    yearMaxFilter.disabled = true;
    yearFilterState[mode] = { min: "", max: "" };
    return;
  }

  yearMinFilter.disabled = false;
  yearMaxFilter.disabled = false;
  yearMinFilter.min = String(bounds.min);
  yearMinFilter.max = String(bounds.max);
  yearMaxFilter.min = String(bounds.min);
  yearMaxFilter.max = String(bounds.max);

  const state = yearFilterState[mode] || { min: "", max: "" };
  let minYear = parseYearValue(forceReset ? "" : state.min);
  let maxYear = parseYearValue(forceReset ? "" : state.max);

  if (minYear === null) minYear = bounds.min;
  if (maxYear === null) maxYear = bounds.max;

  minYear = clampNumber(minYear, bounds.min, bounds.max);
  maxYear = clampNumber(maxYear, bounds.min, bounds.max);
  if (minYear > maxYear) {
    [minYear, maxYear] = [maxYear, minYear];
  }

  yearFilterState[mode] = { min: String(minYear), max: String(maxYear) };
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
  yearFilterState[mode] = { min: String(minYear), max: String(maxYear) };

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
  node.style.setProperty("--node-glow", rgbaString(color, 0.44));
}

function estimateLabelWidth(label) {
  const text = (label || "").toString();
  return Math.max(40, Math.ceil(text.length * 6.8));
}

function estimateGraphLabelWidth(label) {
  return Math.min(GRAPH_LABEL_MAX_WIDTH_PX, estimateLabelWidth(label));
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

function wrapLabelToLines(label, maxWidthPx, maxLines = 2) {
  const rawText = (label || "").toString().trim();
  if (!rawText) return [""];
  if (measureLabelWidth(rawText) <= maxWidthPx) return [rawText];

  const words = rawText.split(/\s+/).filter(Boolean);
  if (words.length === 1) {
    return [fitLabelToWidth(rawText, maxWidthPx)];
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

function studyDesignLabel(design) {
  const normalized = normalizeValue(design);
  if (
    !normalized ||
    ["unknown", "pending_curation", "not_reported", "not_applicable", "not reported", "not applicable"].includes(
      normalized
    )
  ) {
    return "";
  }

  const text = normalized.replace(/[_/()-]+/g, " ").replace(/\s+/g, " ").trim();
  if (/phase\s*3/.test(text) && /randomi[sz]ed|controlled|trial/.test(text)) return "Phase 3 RCT";
  if (/phase\s*2/.test(text) && /randomi[sz]ed|controlled|trial/.test(text)) return "Phase 2 RCT";
  if (/randomi[sz]ed|randomised|double blind|controlled trial|placebo controlled|crossover|cross over/.test(text)) return "RCT";
  if (/open label/.test(text)) return "Open label";
  if (/single arm|single-arm|uncontrolled pilot|pre post|pre-post|phase\s*1/.test(text)) return "Single-arm trial";
  if (/dose finding|dose response|rising tolerance/.test(text)) return "Dose finding";
  if (/post hoc/.test(text)) return "Post-hoc";
  if (/follow up|followup/.test(text)) return "Follow-up";
  if (/wastewater|wbe\b|sewage/.test(text)) return "Wastewater surveillance";
  if (/pharmacovigilance|disproportionality|faers|adverse event reporting/.test(text)) return "Pharmacovigilance";
  if (/case control|cross sectional|observational|naturalistic|survey|internet survey|prospective|real world|real-world|cohort|registry|medical records?|target trial/.test(text)) {
    return "Observational";
  }
  if (/qualitative|ethnographic|user generated|reddit|interview/.test(text)) return "Qualitative";
  if (/retrospective|chart review|case series|single arm effectiveness/.test(text)) return "Retrospective";
  if (/case report/.test(text)) return "Case report";
  if (/case series/.test(text)) return "Case series";
  if (/ex vivo|slice|patch clamp|electrophysiolog/.test(text)) return "Ex vivo experiment";
  if (
    /preclinical|animal|mouse|mice|rat|rats|in vivo|between subjects?|between-subjects?|vehicle controlled|saline|conditioned place preference|\bcpp\b|antagonist blockade|pharmacological challenge|pharmacological interaction|genotype|knockout|cums|chronic mild stress|prenatal|neonatal|binge regimen|fear conditioning|paradigm|pretreatment/.test(
      text
    )
  ) {
    return "Preclinical experiment";
  }
  if (/clinical trial/.test(text)) return "Clinical trial";
  if (/binding|radioligand|competition/.test(text)) return "Binding assay";
  if (/functional receptor|potency|uptake/.test(text)) return "Functional assay";
  if (/in vitro|cell based|cell-based|enzyme assay|pharmacology study|correlation study/.test(text)) return "In vitro assay";
  if (/computational|in silico|modeling|modelling|admet/.test(text)) return "Computational";
  if (/pka|pk a|pka determination|chemical/.test(text)) return "Chemical assay";
  if (/experimental|within subject|pretreatment/.test(text)) return "Experimental";
  return "";
}

function studyDesignFacetLabel(claim) {
  const raw = meaningfulText(claim.study_design);
  if (!raw) return "";
  const normalized = normalizeValue(raw).replace(/[_/()-]+/g, " ").replace(/\s+/g, " ").trim();
  if (!normalized || normalized === "secondary literature") return "";
  if (/network meta|meta analysis|meta-analysis/.test(normalized)) return "Meta-analysis";
  if (/systematic review/.test(normalized)) return "Systematic review";
  if (/scoping review/.test(normalized)) return "Scoping review";
  if (/narrative review|literature review|\breview\b/.test(normalized)) return "Review";
  const label = studyDesignLabel(raw);
  if (label) return label;

  const populationModel = populationModelFacetLabel(claim);
  if (["Mouse model", "Rat model", "Animal model"].includes(populationModel)) return "Preclinical experiment";
  if (["In vitro cell model", "In vitro model"].includes(populationModel)) return "In vitro assay";
  if (populationModel === "Ex vivo tissue model") return "Ex vivo experiment";
  return displayFieldLabel(raw);
}

const STUDY_DESIGN_ORDER = [
  "RCT",
  "Phase 2 RCT",
  "Phase 3 RCT",
  "Open label",
  "Single-arm trial",
  "Clinical trial",
  "Observational",
  "Retrospective",
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
  "Dose finding",
  "Post-hoc",
  "Follow-up",
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

function openAccessFacetLabel(claim) {
  const isOpen = normalizeValue(claim.open_access_is_oa || claim.unpaywall_is_oa);
  const status = normalizeValue(claim.open_access_status || claim.unpaywall_oa_status);
  if (isOpen === "true" || ["gold", "green", "hybrid", "bronze", "diamond"].includes(status)) return "Open access";
  return "Paywalled";
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

function trialRegistrationFacetLabel(claim) {
  return meaningfulText(claim.trial_registry_ids) ? "Registered trial" : "Registration not reported";
}

function populationModelFacetLabel(claim) {
  const system = normalizeValue(meaningfulText(claim.system));
  const species = normalizeValue(meaningfulText(claim.species));
  const model = normalizeValue(meaningfulText(claim.model_or_system));
  const population = normalizeValue(meaningfulText(claim.population));
  const text = [population, species, model, system].filter(Boolean).join(" ");

  if (!text) return "";
  if (/\b(admet|computational|in silico|docking|modeling|modelling)\b/.test(text)) return "Computational model";
  if (/\b(hek|cho|hela|cell|cells|transfected|culture|organoid)\b/.test(text)) return "In vitro cell model";
  if (/\b(ex vivo|slice|synaptosome|tissue|brain tissue|cortical tissue)\b/.test(text)) return "Ex vivo tissue model";
  if (/\b(rat|rats|rattus)\b/.test(text)) return "Rat model";
  if (/\b(mouse|mice|mus musculus)\b/.test(text)) return "Mouse model";
  if (/\b(animal|rodent|preclinical|in vivo|zebrafish|drosophila)\b/.test(text)) return "Animal model";
  if (/\b(veteran|veterans|military)\b/.test(text)) return "Veterans";
  if (/\b(adolescent|adolescents|youth|young people|children|pediatric|paediatric)\b/.test(text)) return "Adolescents & youth";
  if (/\b(older adults|elderly|aged)\b/.test(text)) return "Older adults";
  if (
    /\bhealthy\b/.test(text) &&
    /\b(adults?|humans?|volunteers?|participants?|subjects?|controls?|males?|females?)\b/.test(text)
  ) {
    return "Healthy volunteers";
  }
  if (
    /\b(patient|patients|clinical|diagnos|disorder|depression|depressive|ptsd|anxiety|pain|cancer|terminal|life-threatening|substance|dependence|addiction|parkinson|schizophrenia|bipolar|ocd|migraine|anorexia|eating disorder|body dysmorphic|bdd|borderline|suicid\w*)\b/.test(
      text
    )
  ) {
    return "Clinical population";
  }
  if (
    /\b(recreational|community|survey|general population|respondents|users|people who use|nonclinical|non clinical|lifetime use|website|newsletter|members|immigrants|refugees|ceremon(?:y|ies|ial)|retreat)\b/.test(
      text
    )
  ) {
    return "Community sample";
  }
  if (/\b(adults?|humans?|volunteers?|participants?|subjects?|individuals?)\b/.test(text)) return "Human participants";
  if (system === "clinical") return "Human participants";
  if (system === "in_vitro") return "In vitro model";
  if (system === "ex_vivo") return "Ex vivo tissue model";
  return "Mixed/unclear sample";
}

const POPULATION_MODEL_ORDER = [
  "Clinical population",
  "Healthy volunteers",
  "Human participants",
  "Community sample",
  "Veterans",
  "Adolescents & youth",
  "Older adults",
  "Mouse model",
  "Rat model",
  "Animal model",
  "In vitro cell model",
  "In vitro model",
  "Ex vivo tissue model",
  "Computational model",
  "Mixed/unclear sample",
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
  "Ceremony & retreat",
  "Microdosing",
  "Dose-ranging",
  "Repeated dosing",
  "Single-dose session",
  "Preclinical injection",
];

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
    if (!labels.includes(label)) labels.push(label);
  };
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

const PUBLIC_HEALTH_TOPIC_ORDER = [
  "Microdosing",
  "Recreational use",
  "Self-treatment",
  "Ceremonial/retreat use",
  "Polysubstance use",
  "Prevalence & trends",
  "Problematic use",
  "Drug checking & adulteration",
  "Emergency/toxicology reports",
  "Wastewater & market signals",
  "Access to services",
  "Legal/criminal justice",
  "Other naturalistic topic",
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

function publicHealthTopicFacetLabel(claim) {
  const graphLabel = meaningfulText(claim.public_health_graph_label || claim.graph_entity_label || claim.entity_label);
  if (PUBLIC_HEALTH_TOPIC_ORDER.some((label) => normalizeValue(label) === normalizeValue(graphLabel))) return graphLabel;
  const text = [
    claim.public_health_topic_category,
    claim.public_health_measure,
    claim.raw_entity_label,
    claim.exposure_or_policy,
    claim.exposure_or_intervention,
    claim.population,
    claim.population_or_setting,
    claim.setting,
    claim.study_design,
    claim.data_source_or_study_design,
    claim.association_or_trend,
    claim.time_window,
    claim.study_title,
    claim.dose,
    claim.support,
    claim.supporting_quote,
  ]
    .map(cleanDisplayText)
    .filter(Boolean)
    .join(" ")
    .replace(/[_/()+–—-]+/g, " ")
    .replace(/\s+/g, " ")
    .toLowerCase();

  if (!text.trim()) return "";
  if (/\bmicrodos\w*\b/.test(text)) return "Microdosing";
  if (/\b(drug checking|amnesty bins?|seized samples?|adulter\w*|substitution|unexpected drug|unexpected detection|portable gc|gc[- ]?ms|festival testing|harm reduction information|information source|trip sitter|sitter|babysitter)\b/.test(text)) {
    return "Drug checking & adulteration";
  }
  if (/\b(wastewater|sewage|drug load|mass load|population normalised|population normalized|pndl|pnl|population consumption|per inhabitant consumption|estimated daily consumption|consumption based on metabolic rate|cryptomarket|darknet|market|purchase|availability|easy to obtain|obtain|price)\b/.test(text)) {
    return "Wastewater & market signals";
  }
  if (/\b(poison cent(?:er|re)s?|poison control|emergency|ed visit|emergency medical treatment|emt|hospitali[sz]|intensive care|icu|fatalit\w*|fatal|death|mortality|coronial|forensic|postmortem|post mortem|toxicology|toxicological|toxicosurveillance|intoxication|overdose|adverse event reports?|faers|reporting odds ratio|serum concentration|blood analysis|urine analysis|hair analysis|drug concentration in hair|suspected dfsa|suicid\w*)\b/.test(text)) {
    return "Emergency/toxicology reports";
  }
  if (/\b(ceremon\w*|ritual\w*|retreat|ayahuasca shamanisms?|shamanic|intention setting|sacralization|naturalistic ceremonial)\b/.test(text)) {
    return "Ceremonial/retreat use";
  }
  if (/\b(polysubstance|poly drug|polydrug|co use|concomitant|combined with|combination|cannabis taken alongside|additional substances?|one or more additional substances|mdma mda|mdma methamphetamine)\b/.test(text)) {
    return "Polysubstance use";
  }
  if (/\b(self treat\w*|self medicat\w*|perceived benefit|therapeutic benefit|psychotherapeutic benefit|medical reasons?|psychiatric improvement|symptom improvement|treatment outcomes?|cluster headache|busting|preventive efficacy|abortive efficacy|healing|trauma|cravings?|life changes|quality of life|wellbeing|well being)\b/.test(text)) {
    return "Self-treatment";
  }
  if (/\b(access|service delivery|care delivery|implementation|early access|prescrib\w*|prescription|treatment availability|certified treatment centers?|provider|social workers?|psychiatrists?|attitudes|acceptability|appropriateness|feasibility|patient characteristics|social determinants|atuc)\b/.test(text)) {
    return "Access to services";
  }
  if (/\b(policy|regulat\w*|legal|criminal\w*|crime|arrest\w*|prison|incarcerat\w*|violence|intimate partner violence|classification|drug harms?|scheduling)\b/.test(text)) {
    return "Legal/criminal justice";
  }
  if (/\b(misuse|abuse liability|dependen\w*|addict\w*|diversion|nonmedical|non medical|substance use disorder|use disorder|sud\b|drug abuse|drug dependence|alcohol abuse|problematic|compulsive|obsessive|over eager|tolerance|withdrawal|craving)\b/.test(text)) {
    return "Problematic use";
  }
  if (/\b(recreational|first time use|club|club going|nightlife|dance event|festival|rave|party|naturalistic|pattern of use|use patterns?|route of administration|administration route|frequency|user profiles?|future use|preference|intentions to use|novelty|subjective experience themes|motivations for use|primary reason for use)\b/.test(text)) {
    return "Recreational use";
  }
  if (/\b(epidemiology|prevalence|incidence|lifetime use|past year|past 12 month|use prevalence|trend|demographic|risk factors?|age of initiation|population based|survey|odds of past year|quality of life score|correlates?)\b/.test(text)) {
    return "Prevalence & trends";
  }
  return "Other naturalistic topic";
}

function publicHealthDataSourceFacetLabel(claim) {
  const text = [
    claim.study_design,
    claim.setting,
    claim.population,
    claim.public_health_measure,
    claim.public_health_topic_category,
    claim.support,
  ]
    .map(cleanDisplayText)
    .filter(Boolean)
    .join(" ")
    .replace(/[_/()+-]+/g, " ")
    .replace(/\s+/g, " ")
    .toLowerCase();

  if (!text) return "";
  if (/\b(wastewater|sewage|wbe|population normal(?:ised|ized)|population normalised|population normalized|mass load|daily loads?|pndl|pnl)\b/.test(text)) {
    return "Wastewater";
  }
  if (/\b(drug checking|amnesty bins?|seized samples?|portable gc ms|gc ms|unexpected drug|suspected dfsa|adulterat\w*|substitution)\b/.test(text)) {
    return "Drug checking";
  }
  if (
    /\b(poison centers?|poison centres?|toxicology|toxicological|toxicosurveillance|intoxication|fatalit\w*|fatal poisoning|overdose|emergency department|hair analysis|urine analysis|blood analysis|serum concentration|drug concentration in hair)\b/.test(
      text
    )
  ) {
    return "Poison center/toxicology";
  }
  if (/\b(survey|questionnaire|respondents?|online panel|global drug survey|gds|nsduh|national survey|venue intercept|web based)\b/.test(text)) {
    return "Survey";
  }
  if (/\b(qualitative|interview|ethnograph\w*|focus group|lived experience|narrative|self experiments?)\b/.test(text)) {
    return "Qualitative/interview";
  }
  if (/\b(registry|administrative|medical records?|electronic health|claims data|hospital records?|treatment centers?|rems|certified treatment centers?|arrests?|crime records?|mortality records?)\b/.test(text)) {
    return "Administrative/registry";
  }
  if (/\b(cohort|case control|case-control|longitudinal|follow up|follow-up|retrospective|prospective|observational)\b/.test(text)) {
    return "Observational cohort";
  }
  return "Other/unclear source";
}

const MECHANISTIC_ASSAY_FAMILY_ORDER = [
  "Binding / affinity",
  "Functional activity",
  "Behavioral assay",
  "Protein expression / proteomics",
  "Electrophysiology",
  "Neurochemical levels",
  "Gene expression",
  "Imaging / connectivity",
  "Immunoassay / histology",
  "Computational / in silico",
  "Transporter / uptake",
  "Signaling / phosphorylation",
  "Enzyme / metabolism",
  "Other / mixed method",
];
const MECHANISTIC_RELATIONSHIP_TYPE_ORDER = [
  "Binding/affinity",
  "Agonism/antagonism",
  "Transporter uptake",
  "Neurotransmitter release",
  "Expression change",
  "Connectivity change",
  "Plasticity marker",
  "Toxicity marker",
  "Other/mixed relationship",
];

function mechanisticRelationshipTypeFacetLabel(claim) {
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

function mechanisticAssayFamilyFacetLabel(claim) {
  const normalized = meaningfulText(claim.assay_family_normalized || claim.normalized_assay_family);
  if (normalized) return normalized;

  const text = normalizeValue([claim.assay_family, claim.assay_type].map(meaningfulText).filter(Boolean).join(" "))
    .replace(/[_/()+-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!text || ["none", "not applicable", "not_applicable", "not reported", "not_reported", "unknown", "uncertain"].includes(text)) {
    return "";
  }

  if (/\b(radioligand|binding|affinity|competition|displacement|scatchard|autoradiograph|receptor density)\b/.test(text)) {
    return "Binding / affinity";
  }
  if (
    /\b(electrophysiolog\w*|patch clamp|voltage clamp|current clamp|field potential|field potentials|f?epsp|ipsc|epsc|tevc|whole cell|extracellular recording|eeg|ecog|synaptic transmission|synaptic plasticity|theta burst)\b/.test(text)
  ) {
    return "Electrophysiology";
  }
  if (
    /\b(behavior\w*|behaviour\w*|behavioral pharmacology|drug discrimination|head twitch|htr|locomot|nocicept|antinocicept|forced swim|tail suspension|open field|prepulse)\b/.test(
      text
    )
  ) {
    return "Behavioral assay";
  }
  if (
    /\b(functional connectivity|neuroimaging|imaging|fmri|phmri|pet|mri|connectivity|calcium imaging|autoradiography|magnetic resonance spectroscopy|spectroscopy|mrs)\b/.test(text)
  ) {
    return "Imaging / connectivity";
  }
  if (
    /\b(microdialysis|hplc|uhplc|neurotransmitter|monoamine|dopamine|serotonin|norepinephrine|noradrenaline|glutamate|gaba|release|metabolite|tissue content|neurochemical assay|electrochemical|voltammetry|fscv)\b/.test(
      text
    )
  ) {
    return "Neurochemical levels";
  }
  if (/\b(transport|transporter|uptake|reuptake|efflux|sert|dat|net)\b/.test(text)) return "Transporter / uptake";
  if (
    /\b(gene expression|mrna|qpcr|qrt pcr|rt qpcr|rna seq|rnaseq|transcript|microarray|in situ hybridization|genomic|immediate early gene|fos|arc)\b/.test(
      text
    )
  ) {
    return "Gene expression";
  }
  if (
    /\b(western|immunoblot|protein expression|protein levels?|protein quantification|measurement of protein|proteomics?|mass spectrometry|synaptic expression|brain derived neurotrophic factor|bdnf|psd)\b/.test(
      text
    )
  ) {
    return "Protein expression / proteomics";
  }
  if (
    /\b(elisa|immunoassay|immunohistochemistry|immunofluorescence|histolog|staining|confocal|light sheet|cytometric bead array|flow cytometry|cytokine production|cytokine assay|milliplex|chemokine)\b/.test(
      text
    )
  ) {
    return "Immunoassay / histology";
  }
  if (/\b(expression assay|expression measurement|expression in|expression analysis|detection of expression|gene expression|mrna|transcript)\b/.test(text)) {
    return "Gene expression";
  }
  if (/\b(phosphorylation|phospho|phosphoinositide|kinase|mtor|erk|akt|camp pathway|signal transduction|pathway activation)\b/.test(text)) {
    return "Signaling / phosphorylation";
  }
  if (
    /\b(functional|activity|activation|agonis\w*|antagonis\w*|pharmacological antagonism|pharmacological blockade|pharmacological classification|g protein|beta arrestin|arrestin|bret|camp|ip1|inositol|calcium|recruitment|potency|efficacy|modulation)\b/.test(
      text
    )
  ) {
    return "Functional activity";
  }
  if (/\b(computational|in silico|docking|modeling|modelling|prediction|admet|simulation|molecular dynamics)\b/.test(text)) {
    return "Computational / in silico";
  }
  if (/\b(enzyme|enzymatic|metabolic|metabolism|esterase|pka|pk a|chemical assay|pka determination)\b/.test(text)) {
    return "Enzyme / metabolism";
  }
  return "Other / mixed method";
}

const CLINICAL_COMPARATOR_ORDER = [
  "Placebo / vehicle",
  "Active placebo",
  "Baseline / pre-post",
  "No comparator / single-arm",
  "Dose / route comparison",
  "Active treatment comparator",
  "Treatment as usual / standard care",
  "Observational / matched controls",
  "Comparator not reported",
  "Not applicable",
  "Other / mixed comparator",
];

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
  if (normalized) return normalized;

  const text = normalizeValue(meaningfulText(claim.comparator))
    .replace(/[_/()+-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!text || ["not_reported", "not reported", "unknown", "uncertain"].includes(text)) return "Comparator not reported";
  if (["not_applicable", "not applicable", "n/a", "na"].includes(text)) return "Not applicable";
  if (/\b(no comparator|no control|no comparative|uncontrolled|single arm|no treatment|no ketamine|no analgesia|none)\b/.test(text)) {
    return "No comparator / single-arm";
  }
  if (
    /\b(baseline|pre treatment|pre intervention|pre retreat|pre dose|previous treatments?|retrospective pre|pre operation|preoperation|pretreatment|before infusion|preinfusion|before psychedelic|intake|time period before|pre study|study exit|after first pap|post dosing|before the second infusion)\b/.test(
      text
    )
  ) {
    return "Baseline / pre-post";
  }
  if (/\b(midazolam|niacin|diphenhydramine|active placebo|psychoactive placebo|1 mg psilocybin|5 mg psilocybin|low dose)\b/.test(text)) {
    return "Active placebo";
  }
  if (/\b(placebo|saline|normal saline|isotonic saline|0\.9% saline|vehicle|lactose|nitrogen|water)\b/.test(text)) {
    return "Placebo / vehicle";
  }
  if (
    /\b(\d+(?:\.\d+)?\s*(?:mg|mcg|ug|μg|µg|g|ml)|dose|doses?)\b/.test(text) &&
    /\b(ket|ketamine|esketamine|psilocybin|comp360|mdma|dmt|lsd|nitrous|cannabidiol)\b/.test(text)
  ) {
    return "Dose / route comparison";
  }
  if (
    /\b(iv ketamine|intravenous ketamine|intranasal esketamine|in esketamine|esketamine alone|ketamine alone|ketamine therapy|es ketamine therapy|r s ketamine|oral ketamine|subcutaneous versus intranasal|four infusion|injectable r s ketamine|racemic ketamine|s ketamine|r ketamine|esk in|mdma alone|psilocybin alone|intrathecal psilocin|ketamine only|2r 6r hnk|ibogaine|other routes of administration)\b/.test(
      text
    )
  ) {
    return "Dose / route comparison";
  }
  if (
    /\b(treatment as usual|treatment-as-usual|standard care|standard of care|usual care|conventional|community of practice|mbsr|routine treatment|rwt|standard postpartum care|linkage alone|outpatient medication management|waitlist)\b/.test(
      text
    )
  ) {
    return "Treatment as usual / standard care";
  }
  if (
    /\b(healthy comparison|comparison group|matched controls?|control group|controls?|non users?|non mdma users?|non responders?|nonresponders?|younger patients?|unmedicated|anxious mdd|no change|non aia|patients without|patients with no|non early improvers?|no lifetime|subjects who had no|normative sample|reference category|men|women|unipolar depression|low trauma|trauma type absent|without pain|other chronic pain|mild pain|non pain|healthy individuals?|males?|female|socially isolated|with low insomnia|non obese|without comorbid|do not suffer|without diabetes|without hyperlipidemia|did not have|did not receive|responders?|abstinent users?|neuroleptic free|adults without)\b/.test(
      text
    )
  ) {
    return "Observational / matched controls";
  }
  if (
    /\b(ect|electro convulsive|electroconvulsive|escitalopram|antidepressants?|ssri|oad|quetiapine|lithium|rtms|methadone|ketorolac|fentanyl|sufentanil|remifentanil|acetaminophen|hydromorphone|morphine|opioid|analgesic|propofol|etomidate|bupivacaine|dexamethasone|gabapentin|tramadol|diclofenac|metoclopramide|psychotherapy|therapy alone|thiopental|methohexital|dexmedetomidine|lorazepam|prochlorperazine|aminophylline|lidocaine|anaesthetic|benzodiazepines?|medication management|valproate|lexapro|ketamine|esketamine|mdma|lsd|ayahuasca|dextromethorphan|pethidine|imipramine|duloxetine|sertraline|magnesium sulfate|budesonide|methamphetamine|opiates|psychostimulants|antidepressivos)\b/.test(
      text
    )
  ) {
    return "Active treatment comparator";
  }
  return "Other / mixed comparator";
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

function studyDesignBadgeHtml(design) {
  const label = studyDesignLabel(design);
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

function reviewBadgeHtml(claim) {
  return claim.needs_human_review ? chipHtml("review", "needs review", "needs_review") : "";
}

function claimBadgeHtml(claim) {
  const secondary = isSecondaryLiteratureClaim(claim);
  return [
    reviewBadgeHtml(claim),
    secondary ? "" : systemBadgeHtml(claim.system),
    secondary || mode !== "disorders" ? "" : studyDesignBadgeHtml(claim.study_design),
    accessLevelBadgeHtml(claim.access_level),
    secondary ? literatureTypeBadgeHtml(claim) : "",
  ]
    .filter(Boolean)
    .join("");
}

function setDetailHeader(title) {
  detailTitle.textContent = title;
}

function renderDetailEmpty() {
  detailBody.innerHTML = '<div class="detail-empty">No selection yet.</div>';
}

function clearSelectedStyles() {
  graphEl.querySelectorAll(".selected").forEach((el) => el.classList.remove("selected"));
}

function clearSelection() {
  selected = null;
  isolateSelection = false;
  detailGraphFilter = null;
  clearSelectedStyles();
  setDetailHeader(defaultDetail.title);
  renderDetailEmpty();
  hideTooltip();
  scheduleRender();
}

function showTooltip(content, event) {
  if (tooltip.innerHTML !== content) {
    tooltip.innerHTML = content;
  }
  tooltip.style.opacity = "1";
  tooltip.style.transform = "translateY(0)";
  tooltipSize = {
    width: tooltip.offsetWidth || tooltipSize.width,
    height: tooltip.offsetHeight || tooltipSize.height,
  };
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
      };
    }
  }

  const authors = splitAuthorNames(claimAuthors(claim)).map(meaningfulAuthorName).filter(Boolean);
  const name = role === "last" ? authors[authors.length - 1] || "" : authors[0] || "";
  return name ? { id: name, name } : { id: "", name: "" };
}

function firstAuthorName(claim) {
  return authorRoleIdentity(claim, "first").name;
}

function lastAuthorName(claim) {
  return authorRoleIdentity(claim, "last").name;
}

function firstAuthorFacetValue(claim) {
  const author = authorRoleIdentity(claim, "first");
  return author.name ? { value: author.id || author.name, label: author.name } : "";
}

function lastAuthorFacetValue(claim) {
  const author = authorRoleIdentity(claim, "last");
  return author.name ? { value: author.id || author.name, label: author.name } : "";
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
  return [...claimStores.normalized.disorders, ...claimStores.normalized.mechanistic].filter(
    (claim) => !isHiddenMainGraphItem(claim)
  );
}

function loadedHeroStats() {
  const totalClaims = normalizedKgClaims();
  return {
    compounds: unique(totalClaims.map((claim) => compoundGraphLabel(claim.compound)).filter(Boolean)).length,
    conditions: unique(
      claimStores.normalized.disorders
        .filter((claim) => !isHiddenMainGraphItem(claim))
        .filter((claim) => entityKindForClaim(claim) === "condition_indication")
        .map((claim) => graphLabel(claim.disorder))
        .filter(Boolean)
    ).length,
    targets: unique(
      claimStores.normalized.mechanistic
        .filter((claim) => !isHiddenMainGraphItem(claim))
        .filter((claim) => entityKindForClaim(claim) === "target")
        .map((claim) => graphLabel(claim.target))
        .filter(Boolean)
    ).length,
    studies: uniqueStudyCount(totalClaims),
  };
}

function statNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) return null;
  return Math.trunc(number);
}

function heroStatsFromGraphManifest(manifest) {
  const summary =
    manifest?.summary_stats?.default ||
    manifest?.summary_stats?.views?.primary_with_secondary ||
    manifest?.summary_stats;
  if (!summary || typeof summary !== "object") return null;

  const coverage = summary.graph_study_coverage || {};
  const values = {
    studies: statNumber(summary.study_count ?? summary.studies),
    compounds: statNumber(summary.compound_count ?? summary.compounds),
    conditions: statNumber(summary.condition_count ?? summary.conditions),
    targets: statNumber(summary.target_count ?? summary.targets),
    studyCandidates: statNumber(
      coverage.candidate_count ?? summary.graph_candidate_study_count ?? summary.candidate_study_count
    ),
    studiesNotInGraph: statNumber(
      coverage.not_in_graph_count ?? summary.graph_excluded_study_count ?? summary.studies_not_in_graph_count
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
  completed.studyCandidates = values?.studyCandidates ?? null;
  completed.studiesNotInGraph = values?.studiesNotInGraph ?? null;
  return completed;
}

function setHeroStatValues(values) {
  const completeValues = completeHeroStats(values);
  HERO_STAT_KEYS.forEach((key) => {
    if (!stats[key]) return;
    if (key === "studies" && completeValues.studyCandidates !== null) {
      stats[key].textContent = `${formatCompactNumber(completeValues.studies)} / ${formatCompactNumber(
        completeValues.studyCandidates
      )}`;
      return;
    }
    stats[key].textContent = formatCompactNumber(completeValues[key]);
  });
  const studiesDetail = statDetails.studies;
  if (studiesDetail) {
    const notInGraph = completeValues.studiesNotInGraph;
    studiesDetail.textContent = notInGraph !== null ? `${formatCompactNumber(notInGraph)} not in graph` : "";
  }
  if (studiesStatCard) {
    const included = formatCompactNumber(completeValues.studies);
    const candidates =
      completeValues.studyCandidates !== null ? ` of ${formatCompactNumber(completeValues.studyCandidates)} candidate studies` : "";
    const missing =
      completeValues.studiesNotInGraph !== null ? `; ${formatCompactNumber(completeValues.studiesNotInGraph)} not in graph` : "";
    studiesStatCard.setAttribute("aria-label", `Open study bibliography. ${included}${candidates} in graph${missing}.`);
    studiesStatCard.title = completeValues.studyCandidates !== null ? `${included}${candidates} in graph${missing}` : "";
  }
}

function updateStats() {
  const rightLabelEl = stats.conditions?.previousElementSibling;
  const targetLabelEl = stats.targets?.previousElementSibling;
  if (rightLabelEl) rightLabelEl.textContent = "Conditions";
  if (targetLabelEl) targetLabelEl.textContent = "Targets";

  setHeroStatValues(heroStatsSnapshot);
}

function applyFilters() {
  return applyFiltersToClaims(activeClaimsForMode());
}

function applyFiltersToClaims(activeClaims) {
  const yearRange = activeYearRange(activeClaims);
  const fullTextOnly = Boolean(fullTextOnlyToggle?.checked);

  const baseFiltered = activeClaims.filter((claim) => {
    if (fullTextOnly && claimSourceAccessLevel(claim) !== "full_text_seen") {
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

  if (selected.type === "edge") {
    return detailFiltered.filter((claim) => claimMatchesGraphEdge(claim, selected.compound, selected.target));
  }
  if (selected.type === "compound") {
    return detailFiltered.filter((claim) => claimMatchesGraphCompound(claim, selected.name));
  }
  if (selected.type === "target") {
    return detailFiltered.filter((claim) => claimMatchesGraphRight(claim, selected.name));
  }
  return detailFiltered;
}

function selectionIsValid(data) {
  if (!selected) return true;
  if (selected.type === "edge") {
    return data.some((claim) => claimMatchesGraphEdge(claim, selected.compound, selected.target));
  }
  if (selected.type === "compound") {
    return data.some((claim) => claimMatchesGraphCompound(claim, selected.name));
  }
  if (selected.type === "target") {
    return data.some((claim) => claimMatchesGraphRight(claim, selected.name));
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

function createClaimCardElement(claim) {
  const card = document.createElement("div");
  card.className = "card";

  const secondary = isSecondaryLiteratureClaim(claim);
  const badges = claimBadgeHtml(claim);

  const doiValue = meaningfulText(claim.study_doi);
  const openAlexId = meaningfulText(claim.openalex_id);
  const doiHref = doiUrl(doiValue);
  const sourceLine = doiHref
    ? claimFieldLine(
        "DOI",
        `<a href="${doiHref}" target="_blank" rel="noopener noreferrer">${escapeHtml(
          doiValue
        )}</a>`
      )
    : openAlexId
      ? claimFieldLine("OpenAlex", escapeHtml(String(openAlexId)))
      : "";

  const relation = claimRelationText(claim);
  const authors = claimAuthors(claim);
  const journal = meaningfulText(claim.study_journal || claim.journal);

  const mechanismSummary = [
    cleanDisplayText(claim.mechanism_type),
    cleanDisplayText(claim.action_type),
  ]
    .filter(Boolean)
    .filter((part, index, parts) => parts.indexOf(part) === index)
    .join(" • ");
  const assaySummary = [
    cleanDisplayText(claim.assay_type),
    cleanDisplayText(claim.assay_family),
    cleanDisplayText(claim.model_or_system),
  ]
    .filter(Boolean)
    .filter((part, index, parts) => parts.indexOf(part) === index)
    .join(" • ");
  const doseRouteSummary = compactUniqueParts([claim.dose, claim.route || claim.route_of_administration]).join(" • ");
  const pkAnalyte = compactUniqueParts([claim.metabolite_or_analyte, claim.compound_or_analyte]).join(" • ");
  const pkMatrix = compactUniqueParts([claim.matrix, claim.matrix_or_sample_type]).join(" • ");
  const pkMethod = compactUniqueParts([claim.model_or_method, claim.study_design]).join(" • ");
  const pkObject = compactUniqueParts([claim.pk_graph_object_label, claim.pk_graph_object_kind]).join(" • ");
  const publicHealthEstimate = compactUniqueParts([claim.estimate_value, claim.estimate_unit]).join(" ");
  const mainFinding = claimMainFindingText(claim);
  const mainFindingLine = !secondary && mainFinding
    ? `<div class="card-main-finding"><span class="card-field-label">${
        mode === "mechanistic" ? "Finding" : "Outcome"
      }:</span> ${escapeHtml(mainFinding)}</div>`
    : "";

  const evidenceLines = secondary
    ? ""
    : mode === "disorders"
      ? isRealWorldPublicHealthClaim(claim)
        ? [
            claimFieldLineFromValue("Measure", claim.public_health_measure),
            claimFieldLineFromValue("Category", claim.public_health_topic_category),
            claimFieldLineFromValue("Estimate", publicHealthEstimate),
            claimFieldLineFromValue("Setting", claim.setting),
            claimFieldLineFromValue("Population", claim.population),
            claimFieldLineFromValue("Time window", claim.time_window),
          ].join("")
        : [
            claimFieldLineFromValue("Scale", claim.outcome_measure_normalized),
            claimFieldLineFromValue("Sample", sampleSizeText(claim)),
            claimFieldLineFromValue("Context", claim.clinical_context_condition),
            claimFieldLineFromValue("Population", claim.population),
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
        : [
            claimFieldLineFromValue("Mechanism", mechanismSummary),
            claimFieldLineFromValue("Assay", assaySummary),
            claimFieldLineFromValue("Species", claim.species),
          ].join("");
  const studyTitle = cleanDisplayText(claim.study_title);
  const studyLine = studyTitle
    ? `${escapeHtml(studyTitle)}${
        claim.study_year != null && String(claim.study_year) !== ""
          ? ` (${escapeHtml(String(claim.study_year))})`
          : ""
      }`
    : "not available";

  card.innerHTML = `
      <div class="card-header">
        <h3>${relation}</h3>
        <div class="badge-row">${badges}</div>
      </div>
      <div class="meta">
        ${mainFindingLine}
        ${claimFieldLine("Study", studyLine)}
        ${claimFieldLine("Authors", escapeHtml(authors || "not available"))}
        ${sourceLine ? sourceLine : ""}
        ${claimFieldLine("Journal", escapeHtml(journal || "not available"))}
        ${secondary ? "" : claimFieldLineFromValue("Trial registry", claim.trial_registry_ids)}
        ${evidenceLines}
      </div>
    `;

  return card;
}

function renderCards(data) {
  const searchValue = normalizeValue(searchInput?.value);
  const rightKey = rightEntityKey();
  const cardData = !searchValue
    ? data
    : data.filter((claim) => {
        const haystack = [
          claim.compound,
          claim[rightKey],
          claim.mechanism_type,
          claim.assay_type,
          claim.assay_family,
          claim.action_type,
          claim.study_title,
          claim.affinity_type,
          claim.outcome_type,
          claim.outcome_domain,
          claim.outcome_measure_normalized,
          claim.sample_size_total,
          claim.sample_size_by_arm,
          claim.population,
          claim.intervention_or_exposure,
          claim.public_health_graph_label,
          claim.public_health_topic_category,
          claim.public_health_measure,
          claim.exposure_or_policy,
          claim.exposure_or_intervention,
          claim.setting,
          claim.estimate_value,
          claim.estimate_unit,
          claim.association_or_trend,
          claim.time_window,
          claim.data_source_or_study_design,
          claim.comparison_or_reference_group,
          claim.policy_or_practice_implication,
          claim.comparator,
          claim.dose,
          claim.route,
          claim.route_of_administration,
          claim.compound_or_analyte,
          claim.primary_graph_anchor_kind,
          claim.pk_relationship_type,
          claim.pk_relationship_label,
          claim.pk_graph_object_kind,
          claim.pk_graph_object_label,
          claim.analyte_type,
          claim.metabolite_or_analyte,
          claim.matrix,
          claim.matrix_or_sample_type,
          claim.pk_or_exposure_parameter,
          claim.value,
          claim.unit,
          claim.sampling_time_or_window,
          claim.study_design,
          claim.dose_standardization_or_equivalence,
          claim.comparator_or_reference,
          claim.co_exposure_or_modifier,
          claim.metabolic_or_transport_target,
          claim.metabolic_or_transport_pathway,
          claim.model_or_method,
          claim.interaction_or_potentiation_context,
          claim.exposure_response_or_pk_effect,
          claim.exposure_response_implication,
          claim.synthesis_interpretation,
          claim.timepoint,
          claim.adverse_events,
          claim.support,
          claim.supporting_quote,
          claim.raw_entity_label,
          claim.entity_role,
          claim.clinical_context_condition,
          claim.graph_entity_label,
          claim.graph_exclusion_reason,
          claim.normalization_status,
          claim.normalization_notes,
          claim.canonical_compound,
          claim.canonical_entity,
          claim.paper_assessment_route,
          claim.paper_type,
          claim.source_family,
          claim.source_type,
          claimAuthors(claim),
          claim.study_doi,
          claim.openalex_id,
          graphRightLabelForClaim(claim),
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(searchValue);
      });

  disconnectCardsLoadObserver();
  cardsEl.innerHTML = "";

  if (!cardData.length) {
    return;
  }

  let rendered = 0;

  function appendCardsChunk() {
    const end = Math.min(rendered + LIST_CHUNK_SIZE, cardData.length);
    for (let i = rendered; i < end; i += 1) {
      cardsEl.appendChild(createClaimCardElement(cardData[i]));
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

function bibliographyLookup(modeKey) {
  const rows = bibliographyByMode[modeKey] || [];
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

function enrichClaimsWithBibliographyMetadata(items, modeKey) {
  const lookup = bibliographyLookup(modeKey);
  return items.map((claim) => {
    const doiKey = normalizeValue(normalizeDoi(claim.study_doi));
    const openAlexKey = normalizeValue(claim.openalex_id);
    const entry = (doiKey && lookup.byDoi.get(doiKey)) || (openAlexKey && lookup.byOpenAlex.get(openAlexKey));
    if (!entry) return claim;
    return {
      ...claim,
      study_journal: claim.study_journal || entry.journal,
      publication_type: claim.publication_type || entry.publicationType,
      publication_date: claim.publication_date || entry.publicationDate,
      publisher: claim.publisher || entry.publisher,
      trial_registry_ids: claim.trial_registry_ids || entry.trialRegistryIds,
      authors: claimAuthors(claim) ? claim.authors : entry.authors,
    };
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
    addBibliographyContext(baseEntry, claim.compound, graphRightLabelForClaim(claim) || claim[rightKey]);
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
  const payloadRows = bibliographyByMode[mode] || [];
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
  return normalizeValue(
    [
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
  const bibliographyQuery = normalizeValue(bibliographySearchInput?.value);
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

function focusBibliography() {
  if (!bibliographyPanel) return;
  loadBibliographyPayloadsInBackground();
  bibliographyPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  bibliographyPanel.classList.add("focused");
  setTimeout(() => bibliographyPanel.classList.remove("focused"), 700);
}

function summarizeConnections(items, key) {
  const map = new Map();
  items.forEach((item) => {
    const label =
      key === "compound"
        ? compoundGraphLabel(item[key])
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

function claimRelationText(claim) {
  const rightKey = rightEntityKey();
  const compound = meaningfulText(claim.compound) || "Unknown compound";
  const graphEntity =
    meaningfulText(claim[rightKey]) ||
    meaningfulText(claim.raw_entity_label) ||
    meaningfulText(claim.graph_entity_label) ||
    `Non-graph ${lowerRightEntityLabel(false)}`;
  return `${compound} → ${graphEntity}`;
}

function isPharmacokineticsClaim(claim) {
  return normalizeValue(claim?.kg_domain || claim?.domain || claim?.finding_type) === "pharmacokinetics_exposure";
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

function claimMainFindingText(claim) {
  if (mode === "mechanistic") {
    const value = [
      meaningfulText(claim.affinity_value),
      meaningfulText(claim.affinity_unit),
    ]
      .filter(Boolean)
      .join(" ");
    if (value) {
      return compactUniqueParts([claim.affinity_type || "Measure", value]).join(" · ");
    }
    return compactUniqueParts([claim.mechanism_type, claim.action_type, claim.assay_type]).join(" · ");
  }

  if (isRealWorldPublicHealthClaim(claim)) {
    const estimate = compactUniqueParts([claim.estimate_value, claim.estimate_unit]).join(" ");
    return compactUniqueParts([claim.public_health_measure, estimate, claim.association_or_trend]).join(" · ");
  }

  const outcome = meaningfulText(claim.outcome_measure) || displayOutcomeType(claim.outcome_type);
  const scale = meaningfulText(claim.outcome_measure_normalized);
  const parts = compactUniqueParts([outcome, scale]);
  return parts.join(" · ");
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
    return [graphLabel(claim.disorder)].filter(Boolean);
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

function evidenceCountTooltipHtml(items) {
  const studyCount = uniqueStudyCount(items);
  const recordCount = items.length;
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
    const label = key === "compound" ? compoundGraphLabel(claim[key]) : graphLabel(claim[key]);
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

function summarizeAuthorRoleEvidence(items) {
  const map = new Map();

  items.forEach((claim, index) => {
    const study = studyKey(claim, index);
    const claimKey = claim.kg_claim_id || claim.external_id || `${study}|${index}`;
    [
      ["first", firstAuthorFacetValue(claim)],
      ["last", lastAuthorFacetValue(claim)],
    ].forEach(([role, rawValue]) => {
      const label = rawValue && typeof rawValue === "object" ? meaningfulText(rawValue.label || rawValue.value) : "";
      const value = rawValue && typeof rawValue === "object" ? meaningfulText(rawValue.value || rawValue.id || label) : "";
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
      entry.label = entry.label || label;
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

  const preparedEntries = orderedFacetEntries(entries, options.order || [])
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
  const limitedEntries = limitCompositionEntries(preparedEntries, options.maxEntries || 7).map((entry) =>
    entry.isAggregate ? { ...entry, displayLabel: "Other" } : entry
  );
  const valueKey = options.valueKey || "studies";
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
  const colorForEntry = (index) => chartFillSoft(palette[index % palette.length]);
  const segments = limitedEntries
    .map((entry, index) => {
      const value = Number(entry[valueKey]) || 0;
      const width = (value / total) * 100;
      const label = entry.displayLabel || entry.label;
      return `<span class="trend-stack-segment${compositionTargetClass(entry)}" ${compositionFilterAttrs(
        entry,
        filterField
      )} style="width: ${width.toFixed(2)}%; background: ${colorForEntry(index)}" title="${escapeHtml(
        `${label}: ${formatCompactNumber(entry.studies)} studies, ${formatCompactNumber(entry.count)} findings`
      )}"></span>`;
    })
    .join("");
  const legend = limitedEntries
    .map((entry, index) => {
      const value = Number(entry[valueKey]) || 0;
      const label = entry.displayLabel || entry.label;
      return `
        <span class="trend-legend-item${compositionTargetClass(entry)}" ${compositionFilterAttrs(entry, filterField)}>
          <i style="background: ${colorForEntry(index)}"></i>
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
  const accessEntries = summarizeFacetEvidence(items, openAccessFacetLabel);
  const shouldShowTrialRegistration = evidenceView === "primary" && profile.trialRegistration && hasRegisteredTrial(items);
  const trialEntries = shouldShowTrialRegistration ? summarizeFacetEvidence(items, trialRegistrationFacetLabel) : [];
  const publicationEntries = summarizeFacetEvidence(items, publicationTypeFacetLabel).slice(0, 8);
  const publicationTitle = isSecondaryEvidenceView() ? "Literature types" : "Publication types";
  const trialRegistrationChart =
    shouldShowTrialRegistration
      ? renderFacetChipChart(trialEntries, "Trial registration", "trial_registration_facet", {
          order: ["Registered trial", "Registration not reported"],
          extraClass: "chip-tone-pink",
          emptyText: "No trial-registration metadata in this selection.",
        })
      : "";

  return `
    ${renderFacetChipChart(accessEntries, "Access", "open_access_facet", {
      order: ["Open access", "Paywalled"],
      extraClass: "chip-tone-teal",
      emptyText: "No access metadata in this selection.",
    })}
    ${trialRegistrationChart}
    ${renderFacetChipChart(publicationEntries, publicationTitle, "publication_type_facet", {
      extraClass: isSecondaryEvidenceView() ? "chip-tone-amber" : "chip-tone-gray",
      emptyText: `No ${publicationTitle.toLowerCase()} metadata in this selection.`,
    })}
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
      const title = `${entry.label}: ${formatCompactNumber(entry.studies)} studies, ${formatCompactNumber(
        entry.claims
      )} findings; first author in ${formatCompactNumber(entry.firstStudies)}, last author in ${formatCompactNumber(
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
            <span>First <b>${formatCompactNumber(entry.firstStudies)}</b></span>
            <span>Last <b>${formatCompactNumber(entry.lastStudies)}</b></span>
            <span>Findings <b>${formatCompactNumber(entry.claims)}</b></span>
          </div>
        </div>
      `;
    })
    .join("");

  return trendCardHtml("Authors", "", `<div class="author-rank-list">${rows}</div>`, "author-role-card");
}

function renderJournalChart(items) {
  const journalEntries = summarizeFacetEvidence(items, (claim) => claim.study_journal);
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
    palette: ["#7f9fcf", "#49bfb5", "#c89b45", "#9f86c0", "#b96c8b", "#9ac5ae", "#c7825c", "#7d8492"],
    emptyText: "No assay-family metadata in this selection.",
  });
}

function renderMechanisticRelationshipTypeChart(items) {
  if (evidenceView !== "primary" || !currentDetailPanelProfile().mechanisticRelationshipTypes) return "";
  const relationshipEntries = summarizeFacetEvidence(items, mechanisticRelationshipTypeFacetLabel);
  return renderFacetCompositionChart(relationshipEntries, "Relationship types", "mechanistic_relationship_type_facet", {
    hideWhenEmpty: true,
    order: MECHANISTIC_RELATIONSHIP_TYPE_ORDER,
    maxEntries: 9,
    palette: ["#49bfb5", "#7f9fcf", "#c89b45", "#9f86c0", "#9ac5ae", "#b96c8b", "#c7825c", "#7d8492"],
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
    palette: ["#b96c8b", "#c89b45", "#49bfb5", "#9f86c0", "#7f9fcf", "#c7825c", "#7d8492"],
    emptyText: "No safety-context metadata in this selection.",
  });
}

function renderDoseRouteSessionContextChart(items) {
  if (evidenceView !== "primary" || !currentDetailPanelProfile().doseRouteSessionContexts) return "";
  const contextEntries = summarizeMultiFacetEvidence(items, doseRouteSessionFacetLabels);
  return renderFacetChipChart(contextEntries, "Administration context", "dose_route_session_facet", {
    hideWhenEmpty: true,
    order: DOSE_ROUTE_SESSION_CONTEXT_ORDER,
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
    palette: ["#7f9fcf", "#9f86c0", "#9ac5ae", "#c89b45", "#b96c8b", "#49bfb5", "#c7825c", "#7d8492"],
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
    palette: ["#49bfb5", "#7f9fcf", "#9ac5ae", "#c89b45", "#c7825c", "#b96c8b", "#9f86c0", "#7d8492"],
    emptyText: "No follow-up window metadata in this selection.",
  });
}

function renderPublicHealthTopicChart(items) {
  if (evidenceView !== "primary" || !currentDetailPanelProfile().publicHealthTopics) return "";
  const topicEntries = summarizeFacetEvidence(items, publicHealthTopicFacetLabel);
  return renderFacetCompositionChart(topicEntries, "Naturalistic topics", "public_health_topic_facet", {
    hideWhenEmpty: true,
    order: PUBLIC_HEALTH_TOPIC_ORDER,
    maxEntries: 8,
    palette: ["#49bfb5", "#c89b45", "#9ac5ae", "#7f9fcf", "#b96c8b", "#9f86c0", "#c7825c", "#7d8492"],
    emptyText: "No naturalistic-use topic metadata in this selection.",
  });
}

function renderPublicHealthDataSourceChart(items) {
  if (evidenceView !== "primary" || !currentDetailPanelProfile().publicHealthDataSources) return "";
  const sourceEntries = summarizeFacetEvidence(items, publicHealthDataSourceFacetLabel);
  return renderFacetCompositionChart(sourceEntries, "Data sources", "public_health_data_source_facet", {
    hideWhenEmpty: true,
    order: PUBLIC_HEALTH_DATA_SOURCE_ORDER,
    maxEntries: 8,
    palette: ["#7f9fcf", "#b96c8b", "#49bfb5", "#c89b45", "#9f86c0", "#9ac5ae", "#c7825c", "#7d8492"],
    emptyText: "No data-source metadata in this selection.",
  });
}

function renderEvidenceCompositionFacetCharts(items) {
  if (evidenceView !== "primary") return "";
  const profile = currentDetailPanelProfile();

  const populationModelEntries = profile.populationModel ? summarizeFacetEvidence(items, populationModelFacetLabel) : [];
  const designEntries = profile.studyDesigns ? summarizeFacetEvidence(items, studyDesignFacetLabel) : [];

  return `
    ${renderPublicHealthDataSourceChart(items)}
    ${renderPublicHealthTopicChart(items)}
    ${renderSafetyContextChart(items)}
    ${renderDoseRouteSessionContextChart(items)}
    ${
      profile.populationModel
        ? renderFacetCompositionChart(populationModelEntries, "Population & model", "population_model_facet", {
            hideWhenEmpty: true,
            order: POPULATION_MODEL_ORDER,
            maxEntries: 15,
            palette: ["#9ac5ae", "#9f86c0", "#c89b45", "#7f9fcf", "#b96c8b", "#49bfb5", "#7d8492"],
          })
        : ""
    }
    ${renderClinicalComparatorChart(items)}
    ${renderClinicalFollowUpWindowChart(items)}
    ${renderMechanisticRelationshipTypeChart(items)}
    ${renderMechanisticAssayFamilyChart(items)}
    ${
      profile.studyDesigns
        ? renderFacetCompositionChart(designEntries, "Study designs", "study_design_facet", {
            hideWhenEmpty: true,
            order: STUDY_DESIGN_ORDER,
            maxEntries: 12,
            palette: ["#c89b45", "#7f9fcf", "#9f86c0", "#49bfb5", "#b96c8b", "#c7825c", "#7d8492"],
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
      const byCount = b.count - a.count;
      if (byCount !== 0) return byCount;
      const byStudies = b.studies - a.studies;
      if (byStudies !== 0) return byStudies;
      return a.label.localeCompare(b.label);
    });
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
  if (span <= 18) return 1;
  if (span <= 36) return 2;
  if (span <= 80) return 5;
  return 10;
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

  return [...entries].sort((a, b) => {
    const aIndex = order.indexOf(a.label);
    const bIndex = order.indexOf(b.label);
    if (aIndex !== -1 || bIndex !== -1) {
      return (aIndex === -1 ? 999 : aIndex) - (bIndex === -1 ? 999 : bIndex);
    }
    const byCount = b.count - a.count;
    if (byCount !== 0) return byCount;
    return a.label.localeCompare(b.label);
  });
}

function limitCompositionEntries(entries, maxEntries = 5) {
  if (entries.length <= maxEntries) return entries;
  const visible = entries.slice(0, maxEntries - 1);
  const otherCount = entries.slice(maxEntries - 1).reduce((sum, entry) => sum + entry.count, 0);
  const otherStudies = entries.slice(maxEntries - 1).reduce((sum, entry) => sum + (entry.studies || 0), 0);
  return [...visible, { label: "other", count: otherCount, studies: otherStudies, isAggregate: true }];
}

function colorForCategory(label, index, field = "") {
  const normalized = normalizeValue(label) || "unknown";
  if (field === "system" && SYSTEM_COLORS[normalized]) return SYSTEM_COLORS[normalized];
  return CATEGORY_COLORS[index % CATEGORY_COLORS.length];
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

/** Overview trend charts (#rrggbb only): soften fills slightly; alpha near 1 so colors stay saturated. */
function chartFillSoft(hexColor, alpha = 0.96) {
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

function renderTrendStats(items, extraStats = []) {
  const labels = recordLabelsForItems(items);
  const stats = [
    { label: labels.summary, value: formatCompactNumber(items.length) },
    { label: "Studies", value: formatCompactNumber(uniqueStudyCount(items)) },
    ...extraStats,
  ];

  return `
    <div class="trend-summary-grid">
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
            PUBLICATION_YEAR_COLOR
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
  const canExpand = Boolean(expandKey && entries.length > maxEntries);
  const isExpanded = canExpand && expandedChartKeys.has(expandKey);
  const visibleEntries = canExpand && !isExpanded ? entries.slice(0, maxEntries) : entries;
  const maxValue = Math.max(1, ...entries.map((entry) => Number(entry[valueKey]) || 0));
  const expandControl = canExpand
    ? `
      <div class="trend-chart-actions">
        <button class="chart-expand-toggle" type="button"
          data-chart-expand-key="${escapeHtml(expandKey)}"
          aria-expanded="${escapeHtml(String(isExpanded))}">
          ${isExpanded ? `Show top ${formatCompactNumber(maxEntries)}` : `Show all ${formatCompactNumber(entries.length)}`}
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
  const entries = summarizeOutcomeScaleEvidence(scaleItems);
  if (!entries.length) {
    return "";
  }

  const chips = entries
    .map(
      (entry) => `
        <button class="scale-chip" type="button"
          data-outcome-scale="${escapeHtml(entry.label)}"
          title="${escapeHtml(entry.label)}: ${entry.count} findings"
          aria-label="Show ${escapeHtml(entry.count)} findings using ${escapeHtml(entry.label)}">
          <strong>${escapeHtml(entry.label)}</strong>
          <em>${formatCompactNumber(entry.count)}</em>
        </button>
      `
    )
    .join("");

  return trendCardHtml(
    "Outcome scales",
    "",
    `<div class="scale-chip-grid">${chips}</div>`,
    "evidence-card chip-tone-blue"
  );
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
  `;
}

function renderCompositionChart(items, field, title, options = {}) {
  let entries = sortCompositionEntries(countByField(items, field, options), field);
  if (!entries.length) {
    return trendCardHtml(title, "Finding composition", '<div class="trend-empty">No categorized evidence.</div>');
  }
  entries = limitCompositionEntries(entries, options.maxEntries || 6);

  const total = entries.reduce((sum, entry) => sum + entry.count, 0);
  const segments = entries
    .map((entry, index) => {
      const width = total ? (entry.count / total) * 100 : 0;
      return `<span class="trend-stack-segment${compositionTargetClass(entry)}" ${compositionFilterAttrs(
        entry,
        field
      )} style="width: ${width.toFixed(2)}%; background: ${chartFillSoft(
        colorForCategory(entry.label, index, field)
      )}" title="${escapeHtml(displayFieldLabel(entry.label))}: ${entry.count}"></span>`;
    })
    .join("");
  const legend = entries
    .map(
      (entry, index) => `
        <span class="trend-legend-item${compositionTargetClass(entry)}" ${compositionFilterAttrs(entry, field)}>
          <i style="background: ${chartFillSoft(colorForCategory(entry.label, index, field))}"></i>
          ${escapeHtml(displayFieldLabel(entry.label))} <strong>${formatCompactNumber(entry.count)}</strong>
        </span>
      `
    )
    .join("");

  const compositionSubtitle =
    options.subtitle !== undefined
      ? options.subtitle
      : "Findings";
  return trendCardHtml(
    title,
    compositionSubtitle,
    `
      <div class="trend-stack">${segments}</div>
      <div class="trend-legend">${legend}</div>
    `
  );
}

function renderExperimentalSystemChart(items) {
  if (evidenceView !== "primary") return "";
  if (!currentDetailPanelProfile().experimentalSystem) return "";
  return renderCompositionChart(items, "system", "Experimental system");
}

function renderSpecificPathwayReadoutChart(items) {
  if (!usesPathwayReadoutFamilies()) return "";
  const entries = summarizeFacetEvidence(items, specificPathwayReadoutLabel).slice(0, 20);
  return renderFacetChipChart(entries, "Specific molecular findings", "specific_pathway_readout", {
    extraClass: "chip-tone-teal",
    emptyText: "No specific labels in this selection.",
  });
}

function renderDetailClaimCards(items) {
  const labels = recordLabelsForItems(items);
  if (!items.length) {
    return trendCardHtml(labels.section, "", `<div class="trend-empty">${escapeHtml(labels.empty)}</div>`);
  }

  const sortedClaims = [...items].sort((a, b) => {
    const yearDiff = (parseYearValue(b.study_year) || 0) - (parseYearValue(a.study_year) || 0);
    if (yearDiff !== 0) return yearDiff;
    return (a.study_title || "").localeCompare(b.study_title || "");
  });

  const rightKey = rightEntityKey();
  const body = `
    <div class="detail-claim-cards">
      ${sortedClaims
        .map((claim) => {
          const secondary = isSecondaryLiteratureClaim(claim);
          const relation = claimRelationText(claim);
          const doiHref = doiUrl(claim.study_doi);
          const source = doiHref
            ? `<a href="${doiHref}" target="_blank" rel="noopener noreferrer">${escapeHtml(claim.study_doi)}</a>`
            : claim.openalex_id
            ? `<a href="${openAlexUrl(claim.openalex_id)}" target="_blank" rel="noopener noreferrer">${escapeHtml(claim.openalex_id)}</a>`
            : "";
          const mainLine = secondary
            ? secondaryCoverageText(claim)
            : mode === "mechanistic"
              ? `${claim.affinity_value ? claim.affinity_type || "Measure" : claim.mechanism_type || "Mechanism"} ${
                  claim.affinity_value || claim.action_type || claim.assay_type || "reported"
                } ${claim.affinity_unit || ""}`.trim()
              : `${meaningfulText(claim.outcome_type) || "Outcome"}${
                  meaningfulText(claim.outcome_measure_normalized)
                    ? ` · ${meaningfulText(claim.outcome_measure_normalized)}`
                    : meaningfulText(claim.outcome_measure)
                      ? ` · ${meaningfulText(claim.outcome_measure)}`
                      : ""
                }`;
          const contextLine = secondary
            ? [literatureTypeLabel(claim), evidenceLocationText(claim)].filter(Boolean).join(" · ")
            : mode === "mechanistic"
              ? `System: ${claim.system || "unknown"} · Species: ${claim.species || "unknown"}`
              : `Population: ${claim.population || "unknown"}`;
          const sampleLine =
            !secondary && mode === "disorders"
              ? [
                  sampleSizeText(claim) ? `Sample: ${sampleSizeText(claim)}` : "",
                  meaningfulText(claim.timepoint) ? `Timepoint: ${meaningfulText(claim.timepoint)}` : "",
                  meaningfulText(claim.comparator) ? `Comparator: ${meaningfulText(claim.comparator)}` : "",
                ]
                  .filter(Boolean)
                  .join(" · ")
              : "";
          const journalLine = [claim.study_journal, claim.publication_type]
            .map(cleanDisplayText)
            .filter(Boolean)
            .join(" · ");

          return `
            <article class="detail-claim-card">
              <h5>${escapeHtml(relation)}</h5>
              <div class="detail-claim-meta">
                <div>${escapeHtml(mainLine)}</div>
                <div>${escapeHtml(contextLine)}</div>
                ${sampleLine ? `<div>${escapeHtml(sampleLine)}</div>` : ""}
                <div>${escapeHtml(cleanDisplayText(claim.study_title) || "Unknown study")}${claim.study_year ? ` (${escapeHtml(claim.study_year)})` : ""}</div>
                ${journalLine ? `<div>${escapeHtml(journalLine)}</div>` : ""}
                ${source ? `<div>${source}</div>` : ""}
              </div>
              <div class="badge-row">${claimBadgeHtml(claim)}</div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;

  return trendCardHtml(labels.section, "", body);
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

function claimsForStudyKey(studyKeyValue) {
  return activeDetailItems.filter((claim, index) => studyKey(claim, index) === studyKeyValue);
}

function claimsForFieldValue(field, value) {
  if (!field || !value) return [];
  const normalizedValue = normalizeValue(value);
  if (field === "author_role") {
    return activeDetailItems.filter((claim) =>
      ["first", "last"].some((role) => normalizeValue(authorRoleIdentity(claim, role).id) === normalizedValue)
    );
  }
  return activeDetailItems.filter((claim) => {
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
  if (field === "open_access_facet") return `Access: ${value}`;
  if (field === "trial_registration_facet") return `Trial registration: ${value}`;
  if (field === "population_model_facet") return `Population & model: ${value}`;
  if (field === "assay_family_facet") return `Assay family: ${value}`;
  if (field === "mechanistic_relationship_type_facet") return `Relationship type: ${value}`;
  if (field === "safety_context_facet") return `Safety context: ${value}`;
  if (field === "dose_route_session_facet") return `Administration context: ${value}`;
  if (field === "comparator_facet") return `Comparator: ${value}`;
  if (field === "follow_up_window_facet") return `Follow-up window: ${value}`;
  if (field === "study_design_facet") return `Study design: ${value}`;
  if (field === "public_health_topic_facet") return `Naturalistic topic: ${value}`;
  if (field === "public_health_data_source_facet") return `Data source: ${value}`;
  if (field === "publication_type_facet") return `Publication type: ${value}`;
  return `${displayFieldLabel(field)}: ${value}`;
}

function fieldValueForClaim(claim, field) {
  if (field === "open_access_facet") return openAccessFacetLabel(claim);
  if (field === "trial_registration_facet") return trialRegistrationFacetLabel(claim);
  if (field === "population_model_facet") return populationModelFacetLabel(claim);
  if (field === "assay_family_facet") return mechanisticAssayFamilyFacetLabel(claim);
  if (field === "mechanistic_relationship_type_facet") return mechanisticRelationshipTypeFacetLabel(claim);
  if (field === "safety_context_facet") return safetyContextFacetLabel(claim);
  if (field === "dose_route_session_facet") return doseRouteSessionFacetLabels(claim);
  if (field === "comparator_facet") return clinicalComparatorFacetLabel(claim);
  if (field === "follow_up_window_facet") return clinicalFollowUpWindowFacetLabel(claim);
  if (field === "study_design_facet") return studyDesignFacetLabel(claim);
  if (field === "public_health_topic_facet") return publicHealthTopicFacetLabel(claim);
  if (field === "public_health_data_source_facet") return publicHealthDataSourceFacetLabel(claim);
  if (field === "publication_type_facet") return publicationTypeFacetLabel(claim);
  if (field === "specific_pathway_readout") return specificPathwayReadoutLabel(claim);
  if (field === "first_author") return authorRoleIdentity(claim, "first").id || firstAuthorName(claim);
  if (field === "last_author") return authorRoleIdentity(claim, "last").id || lastAuthorName(claim);
  return cleanDisplayText(claim[field]);
}

function claimsForPublicationYearRange(startValue, endValue) {
  const start = Number(startValue);
  const end = Number(endValue || startValue);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return [];
  return activeDetailItems.filter((claim) => {
    const year = parseYearValue(claim.study_year);
    return year !== null && year >= start && year <= end;
  });
}

function claimsForSampleHeatmapCell(startValue, endValue, minValue, maxValue) {
  const start = Number(startValue);
  const end = Number(endValue || startValue);
  const min = Number(minValue);
  const parsedMax = maxValue === "" ? Number.POSITIVE_INFINITY : Number(maxValue);
  const max = Number.isFinite(parsedMax) ? parsedMax : Number.POSITIVE_INFINITY;
  if (!Number.isFinite(start) || !Number.isFinite(end) || !Number.isFinite(min)) return [];

  const matchingStudies = new Set();
  activeDetailItems.forEach((claim, index) => {
    const year = parseYearValue(claim.study_year);
    const sampleSize = parseSampleSize(sampleSizeText(claim));
    if (year === null || sampleSize === null) return;
    if (year < start || year > end || sampleSize < min || sampleSize > max) return;
    matchingStudies.add(studyKey(claim, index));
  });
  if (!matchingStudies.size) return [];
  return activeDetailItems.filter((claim, index) => matchingStudies.has(studyKey(claim, index)));
}

function claimsForOutcomeScale(scaleValue) {
  const scaleKey = normalizeValue(scaleValue);
  if (!scaleKey) return [];
  return outcomeScaleClaimsForChart(activeDetailItems).filter((claim) =>
    outcomeScaleLabelsForClaim(claim).some((scale) => normalizeValue(scale) === scaleKey)
  );
}

function restoreCurrentDetailPanel() {
  clearDetailGraphFilter();
  const filtered = applyFilters();
  refreshMainViews();
  if (selected) {
    renderSelectedDetailFromData(filtered);
    return;
  }
  renderOverviewDetail(filtered);
}

function renderStudyDetail(studyKeyValue) {
  const studyClaims = claimsForStudyKey(studyKeyValue);
  if (!studyClaims.length) return;

  activeDetailItems = studyClaims;
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
          value: formatCompactNumber(unique(studyClaims.map((claim) => compoundGraphLabel(claim.compound)).filter(Boolean)).length),
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
      ${renderDetailClaimCards(studyClaims)}
    </div>
  `;
}

function renderFieldValueDetail(field, value, labelValue = value) {
  const fieldClaims = claimsForFieldValue(field, value);
  if (!fieldClaims.length) return;

  activeDetailItems = fieldClaims;
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
      ${renderDetailClaimCards(fieldClaims)}
    </div>
  `;
}

function renderPublicationYearDetail(startValue, endValue, labelValue) {
  const yearClaims = claimsForPublicationYearRange(startValue, endValue);
  if (!yearClaims.length) return;

  activeDetailItems = yearClaims;
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
      ${renderDetailClaimCards(yearClaims)}
    </div>
  `;
}

function renderSampleHeatmapDetail(startValue, endValue, minValue, maxValue, labelValue) {
  const sampleClaims = claimsForSampleHeatmapCell(startValue, endValue, minValue, maxValue);
  if (!sampleClaims.length) return;

  activeDetailItems = sampleClaims;
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
      ${renderDetailClaimCards(sampleClaims)}
    </div>
  `;
}

function renderOutcomeScaleDetail(scaleValue) {
  const scaleClaims = claimsForOutcomeScale(scaleValue);
  if (!scaleClaims.length) return;

  const scopeKeys = new Set(scaleClaims.map(evidenceScopeKey).filter(Boolean));
  const sourceItems = activeDetailItems.length ? activeDetailItems : applyFilters();
  const scopedViewClaims =
    currentEntityViewKey() === "outcome_scale"
      ? scaleClaims
      : sourceItems.filter((claim) => !isOutcomeScaleClaim(claim) && scopeKeys.has(evidenceScopeKey(claim)));
  const detailClaims = scopedViewClaims.length ? scopedViewClaims : scaleClaims;

  activeDetailItems = detailClaims;
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
      ${renderDetailClaimCards(detailClaims)}
    </div>
  `;
}

function renderEdgeDetail(compound, target, edgeClaims) {
  const studies = uniqueStudyCount(edgeClaims);
  activeDetailItems = edgeClaims;
  setDetailHeader(`${compound} → ${target}`);

  detailBody.innerHTML = `
    <div class="trend-dashboard">
      ${renderTrendStats(edgeClaims)}
      ${renderAnnualPublicationChart(edgeClaims)}
      ${renderSpecificPathwayReadoutChart(edgeClaims)}
      ${renderEvidenceDetailGroup(edgeClaims)}
      ${renderMetadataFacetCharts(edgeClaims)}
      ${renderDetailClaimCards(edgeClaims)}
    </div>
  `;
}

function renderNodeDetail(type, name, nodeClaims) {
  activeDetailItems = nodeClaims;
  setDetailHeader(name);

  detailBody.innerHTML = `
    <div class="trend-dashboard">
      ${renderTrendStats(nodeClaims)}
      ${renderAnnualPublicationChart(nodeClaims)}
      ${renderSpecificPathwayReadoutChart(nodeClaims)}
      ${renderEvidenceDetailGroup(nodeClaims)}
      ${renderMetadataFacetCharts(nodeClaims)}
      ${renderDetailClaimCards(nodeClaims)}
    </div>
  `;
}

function renderOverviewDetail(data) {
  activeDetailItems = data;
  setDetailHeader(`All ${lowerRightEntityLabel(true)}`);

  if (!data.length) {
    detailBody.innerHTML = `<div class="detail-empty">${escapeHtml(recordLabelsForItems(data).empty)}</div>`;
    return;
  }

  detailBody.innerHTML = `
    <div class="trend-dashboard">
      ${renderTrendStats(data)}
      ${renderAnnualPublicationChart(data)}
      ${renderEvidenceDetailGroup(data)}
      ${renderMetadataFacetCharts(data)}
    </div>
  `;
}

function renderSelectedDetailFromData(data) {
  if (!selected) return;

  if (selected.type === "edge") {
    const edgeClaims = data.filter((claim) => claimMatchesGraphEdge(claim, selected.compound, selected.target));
    renderEdgeDetail(selected.compound, selected.target, edgeClaims);
    return;
  }

  if (selected.type === "compound") {
    const nodeClaims = data.filter((claim) => claimMatchesGraphCompound(claim, selected.name));
    renderNodeDetail("compound", selected.name, nodeClaims);
    return;
  }

  if (selected.type === "target") {
    const nodeClaims = data.filter((claim) => claimMatchesGraphRight(claim, selected.name));
    renderNodeDetail("target", selected.name, nodeClaims);
  }
}

function buildGraph(data) {
  graphEl.innerHTML = "";

  const rightKey = rightEntityKey();
  const compoundCounts = new Map();
  const rightCounts = new Map();
  const compoundConnections = new Map();
  const rightConnections = new Map();
  const incidentEdgeKeysByCompound = new Map();
  const incidentEdgeKeysByRight = new Map();

  data.forEach((claim) => {
    const compound = compoundGraphLabel(claim.compound);
    const right = graphRightLabelForClaim(claim);
    if (!compound || !right) return;

    compoundCounts.set(compound, (compoundCounts.get(compound) || 0) + 1);
    rightCounts.set(right, (rightCounts.get(right) || 0) + 1);

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

  const width = graphEl.clientWidth || 800;
  const compactGraph = width < 520;
  if (compactGraph) {
    const maxMobileNodes = 12;
    compounds = compounds.slice(0, maxMobileNodes);
    targets = targets.slice(0, maxMobileNodes);
  }

  const longestLeftLabelPx = Math.max(80, ...compounds.map(estimateGraphLabelWidth));
  const longestRightLabelPx = Math.max(80, ...targets.map(estimateGraphLabelWidth));
  const baseSideMargin = clampNumber(Math.floor(width * 0.18), 110, 220);
  let leftMargin = Math.max(baseSideMargin, longestLeftLabelPx + 28);
  let rightMargin = Math.max(baseSideMargin, longestRightLabelPx + 28 + GRAPH_RIGHT_LABEL_GUTTER_PX);
  const minCenterWidth = 120;
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
  const labelMaxLines = compactGraph ? 1 : 2;
  const leftLabelMaxWidth = Math.min(GRAPH_LABEL_MAX_WIDTH_PX, Math.max(20, compoundX - labelOffset - 10));
  const rightLabelMaxWidth = Math.min(
    GRAPH_LABEL_MAX_WIDTH_PX,
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
  data.forEach((claim) => {
    const compound = compoundGraphLabel(claim.compound);
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
    existing.count += 1;
    existing.claims.push(claim);
    if (rank > existing.rank) {
      existing.rank = rank;
    }
    edges.set(key, existing);
  });
  let edgeEntries = Array.from(edges.entries());
  if (edgeEntries.length > MAX_GRAPH_EDGES) {
    edgeEntries = edgeEntries
      .sort((a, b) => {
        const edgeA = a[1];
        const edgeB = b[1];
        const byCount = (edgeB.count || 0) - (edgeA.count || 0);
        if (byCount !== 0) return byCount;
        return (edgeB.rank || 0) - (edgeA.rank || 0);
      })
      .slice(0, MAX_GRAPH_EDGES);
  }

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  svg.appendChild(defs);
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
    applyFocusState(focusClassesForNode(nodeType, nodeName), true);
  }

  function applyFocusForEdge(edgeKey) {
    applyFocusState(focusClassesForEdge(edgeKey), true);
  }

  function applyFocusFromSelection() {
    if (!selected) {
      applyFocusState(new Map(), false);
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
    path.style.setProperty("--edge-glow", rgbaString(compoundColor, 0.36));
    path.dataset.compound = compound;
    path.dataset.target = target;
    path.dataset.claimCount = `${edge.count}`;
    path.dataset.edgeKey = key;
    if (selected?.type === "edge" && selected.compound === compound && selected.target === target) {
      path.classList.add("selected");
    }
    edgeElementByKey.set(key, path);

    path.addEventListener("mouseenter", (event) => {
      cancelPendingFocusRestore();
      path.classList.add("hovered");
      applyFocusForEdge(key);
      showTooltip(
        `<strong>${compound} → ${target}</strong><br/>${evidenceCountTooltipHtml(edge.claims)}`,
        event
      );
    });
    path.addEventListener("mousemove", moveTooltip);
    path.addEventListener("mouseleave", () => {
      path.classList.remove("hovered");
      hideTooltip();
      restoreFocusAfterPointerLeave();
    });
    path.addEventListener("click", (event) => {
      event.stopPropagation();
      const sameSelection =
        selected?.type === "edge" && selected.compound === compound && selected.target === target;
      if (sameSelection) {
        if (!isolateSelection) {
          isolateSelection = true;
          scheduleRender();
          return;
        }
        clearSelection();
        return;
      }

      selected = { type: "edge", compound, target };
      isolateSelection = false;
      clearSelectedStyles();
      path.classList.add("selected");
      renderEdgeDetail(compound, target, edge.claims);
      applyFocusFromSelection();
      scheduleRender();
    });
    svg.appendChild(path);
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
    svg.appendChild(node);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", pos.x - labelOffset);
    label.setAttribute("class", "node-label");
    label.setAttribute("text-anchor", "end");
    setWrappedSvgLabel(label, compound, leftLabelMaxWidth, pos.x - labelOffset, pos.y, labelMaxLines);
    if (selected?.type === "compound" && selected.name === compound) {
      label.classList.add("selected");
    }
    svg.appendChild(label);
    compoundNodeElements.set(compound, { node, label });

    const nodeClaims = claimsByCompound.get(compound) || [];
    const enter = (event) => {
      cancelPendingFocusRestore();
      node.classList.add("hovered");
      label.classList.add("hovered");
      applyFocusForNode("compound", compound);
      showTooltip(
        `<strong>${compound}</strong><br/>${evidenceCountTooltipHtml(nodeClaims)}<br/>Connections: ${
          summarizeConnections(nodeClaims, rightKey).length
        }`,
        event
      );
    };
    const leave = () => {
      node.classList.remove("hovered");
      label.classList.remove("hovered");
      hideTooltip();
      restoreFocusAfterPointerLeave();
    };
    const click = (event) => {
      event.stopPropagation();
      const sameSelection = selected?.type === "compound" && selected.name === compound;
      if (sameSelection) {
        if (!isolateSelection) {
          isolateSelection = true;
          scheduleRender();
          return;
        }
        clearSelection();
        return;
      }

      selected = { type: "compound", name: compound };
      isolateSelection = false;
      clearSelectedStyles();
      node.classList.add("selected");
      label.classList.add("selected");
      renderNodeDetail("compound", compound, nodeClaims);
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
    svg.appendChild(node);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", pos.x + labelOffset);
    label.setAttribute("class", "node-label");
    setWrappedSvgLabel(label, target, rightLabelMaxWidth, pos.x + labelOffset, pos.y, labelMaxLines);
    if (selected?.type === "target" && selected.name === target) {
      label.classList.add("selected");
    }
    svg.appendChild(label);
    rightNodeElements.set(target, { node, label });

    const nodeClaims = claimsByRight.get(target) || [];
    const enter = (event) => {
      cancelPendingFocusRestore();
      node.classList.add("hovered");
      label.classList.add("hovered");
      applyFocusForNode("target", target);
      showTooltip(
        `<strong>${target}</strong><br/>${evidenceCountTooltipHtml(nodeClaims)}<br/>Compounds: ${
          summarizeConnections(nodeClaims, "compound").length
        }`,
        event
      );
    };
    const leave = () => {
      node.classList.remove("hovered");
      label.classList.remove("hovered");
      hideTooltip();
      restoreFocusAfterPointerLeave();
    };
    const click = (event) => {
      event.stopPropagation();
      const sameSelection = selected?.type === "target" && selected.name === target;
      if (sameSelection) {
        if (!isolateSelection) {
          isolateSelection = true;
          scheduleRender();
          return;
        }
        clearSelection();
        return;
      }

      selected = { type: "target", name: target };
      isolateSelection = false;
      clearSelectedStyles();
      node.classList.add("selected");
      label.classList.add("selected");
      renderNodeDetail("target", target, nodeClaims);
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

  graphEl.appendChild(svg);
  if (edges.size > edgeEntries.length) {
    const note = document.createElement("div");
    note.className = "graph-truncation-note";
    note.textContent = `Showing top ${edgeEntries.length} of ${edges.size} edges (ranked by finding count).`;
    graphEl.appendChild(note);
  }

  applyFocusFromSelection();
}

function render() {
  const filtered = applyFilters();
  if (selected && !selectionIsValid(filtered)) {
    selected = null;
    isolateSelection = false;
  }
  if (detailGraphFilter) {
    // Keep the current right-panel drilldown visible while refreshing the graph.
  } else if (selected) {
    renderSelectedDetailFromData(filtered);
  } else {
    renderOverviewDetail(filtered);
  }
  updateStats();
  renderCards(filtered);
  buildGraph(filtered);
  renderBibliography(filtered);
}

function refreshMainViews() {
  const filtered = applyFilters();
  if (selected && !selectionIsValid(filtered)) {
    selected = null;
    isolateSelection = false;
    clearSelectedStyles();
  }
  updateStats();
  renderCards(filtered);
  buildGraph(filtered);
  renderBibliography(filtered);
}

function scheduleRender() {
  if (renderScheduled) return;
  renderScheduled = true;
  window.requestAnimationFrame(() => {
    renderScheduled = false;
    render();
  });
}

function waitForPaint() {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => window.requestAnimationFrame(resolve));
  });
}

function updateSearchPlaceholder() {
  if (!searchInput) return;
  if (mode === "mechanistic") {
    searchInput.placeholder = `Search compounds, ${lowerRightEntityLabel(true)}, or assays`;
  } else {
    searchInput.placeholder = `Search compounds, ${lowerRightEntityLabel(true)}, or outcomes`;
  }
}

function updateEntityKindToggle() {
  if (!entityKindToggle) return;
  const isAvailable = claimLayer === "normalized";
  entityKindToggle.hidden = !isAvailable;
  if (!isAvailable) {
    entityKindToggle.innerHTML = "";
    return;
  }

  entityKindToggle.innerHTML = ENTITY_CATEGORY_OPTIONS
    .map((option) => {
      const isActive = option.mode === mode && option.key === currentEntityViewKey();
      const modeClaims = option.mode === "mechanistic" ? claims : disorderClaims;
      const count = graphViewClaims(modeClaims).filter((claim) => claimMatchesEntityViewOption(claim, option)).length;
      return `
        <button
          class="ghost small ${isActive ? "active" : ""}"
          data-entity-view="${escapeHtml(option.key)}"
          data-entity-mode="${escapeHtml(option.mode)}"
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
  modeButtons.forEach((btn) => {
    const isActive = btn.dataset.mode === mode;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
  });
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
  if (fullTextOnlyToggle) fullTextOnlyToggle.disabled = false;
  fullTextOnlyToggle?.closest(".access-toggle")?.classList.remove("disabled");
}

function switchMode(nextMode) {
  if (mode === nextMode) return;
  mode = nextMode;
  selected = null;
  isolateSelection = false;
  detailGraphFilter = null;
  clearSelectedStyles();
  updateModeUI();
  syncYearFilterControls(activeClaimsForMode());
  setDetailHeader(defaultDetail.title);
  renderDetailEmpty();
  loadCurrentClaimsAndRender({ showGraphPreview: true });
}

function switchClaimLayer(nextLayer) {
  if (!claimStores[nextLayer] || claimLayer === nextLayer) return;
  claimLayer = nextLayer;
  applyClaimLayerStore();
  selected = null;
  isolateSelection = false;
  detailGraphFilter = null;
  clearSelectedStyles();
  updateModeUI();
  syncYearFilterControls(activeClaimsForMode(), true);
  setDetailHeader(defaultDetail.title);
  renderDetailEmpty();
  loadCurrentClaimsAndRender({ showGraphPreview: true });
}

function switchEvidenceView(nextView) {
  if (!EVIDENCE_VIEW_KEYS.includes(nextView) || evidenceView === nextView) return;
  evidenceView = nextView;
  selected = null;
  isolateSelection = false;
  detailGraphFilter = null;
  clearSelectedStyles();
  updateModeUI();
  syncYearFilterControls(activeClaimsForMode(), true);
  setDetailHeader(defaultDetail.title);
  renderDetailEmpty();
  loadCurrentClaimsAndRender({ showGraphPreview: true });
}

function switchEntityView(nextView, nextMode = mode) {
  const targetMode = ["disorders", "mechanistic"].includes(nextMode) ? nextMode : mode;
  const options = ENTITY_VIEW_OPTIONS[targetMode] || [];
  if (!options.some((option) => option.key === nextView)) return;
  if (mode === targetMode && currentEntityViewKey() === nextView) return;
  mode = targetMode;
  entityView = { ...entityView, [targetMode]: nextView };
  selected = null;
  isolateSelection = false;
  detailGraphFilter = null;
  clearSelectedStyles();
  updateModeUI();
  syncYearFilterControls(activeClaimsForMode(), true);
  setDetailHeader(defaultDetail.title);
  renderDetailEmpty();
  loadCurrentClaimsAndRender({ showGraphPreview: true });
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

function joinPayloadPath(dir, fileName) {
  return `${(dir || "").replace(/\/+$/, "")}/${fileName}`;
}

function uniquePaths(paths) {
  return Array.from(new Set(paths.filter(Boolean)));
}

async function loadGraphPayloadConfig() {
  if (graphPayloadConfigPromise) return graphPayloadConfigPromise;
  graphPayloadConfigPromise = fetchJsonFromCandidates(dataCandidates("data/processed/graph_payload_active.json"))
    .then(({ data }) => data || {})
    .catch(() => ({}));
  return graphPayloadConfigPromise;
}

async function resolveGraphPayloadPaths(paths) {
  const config = await loadGraphPayloadConfig();
  const activeDir = cleanDisplayText(config?.active_payload_dir || "");
  const activeManifest = cleanDisplayText(config?.active_manifest || "");
  const out = [];
  for (const path of paths) {
    const fileName = path.split("/").pop();
    if (activeManifest && fileName === "graph_payload_manifest.json") {
      out.push(activeManifest);
    } else if (activeDir && /^graph_(?:payload|preview)_/.test(fileName || "")) {
      out.push(joinPayloadPath(activeDir, fileName));
    }
    out.push(path);
  }
  return uniquePaths(out);
}

function loadGraphManifestStats() {
  if (graphManifestPromise) return graphManifestPromise;
  graphManifestPromise = (async () => {
    const paths = await resolveGraphPayloadPaths(["data/processed/graph_payload_manifest.json"]);
    return fetchJsonFromCandidates(paths.flatMap((path) => dataCandidates(path))).then(({ data }) => {
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
  const payloads = [
    {
      key: "mechanistic",
      candidates: [
        "../data/processed/bibliography_payload_mechanistic.json",
        "/data/processed/bibliography_payload_mechanistic.json",
        "data/processed/bibliography_payload_mechanistic.json",
      ],
    },
    {
      key: "disorders",
      candidates: [
        "../data/processed/bibliography_payload_disorder.json",
        "/data/processed/bibliography_payload_disorder.json",
        "data/processed/bibliography_payload_disorder.json",
      ],
    },
  ];

  await Promise.all(
    payloads
      .filter(({ key }) => !(bibliographyByMode[key] || []).length)
      .map(async ({ key, candidates }) => {
        try {
          const { data } = await fetchJsonFromCandidates(candidates);
          bibliographyByMode[key] = bibliographyFromPayload(data);
        } catch (_error) {
          bibliographyByMode[key] = [];
        }
      })
  );
}

const normalizedSourceLoaded = {
  mechanistic: { primary: false, secondary: false },
  disorders: { primary: false, secondary: false },
};

const normalizedSourceTasks = {
  mechanistic: { primary: null, secondary: null },
  disorders: { primary: null, secondary: null },
};

const graphPreviewLoaded = {
  mechanistic: { primary: false, secondary: false },
  disorders: { primary: false, secondary: false },
};

const graphPreviewTasks = {
  mechanistic: { primary: null, secondary: null },
  disorders: { primary: null, secondary: null },
};

function renderDataLoading() {
  setDetailHeader(defaultDetail.title);
  renderDetailEmpty();
  cardsEl.innerHTML = "";
  graphEl.innerHTML = "";
  if (studyListEl) {
    studyListEl.innerHTML = "";
  }
}

function bibliographyPayloadsLoaded() {
  return Object.values(bibliographyByMode).some((rows) => Array.isArray(rows) && rows.length);
}

function enrichAllLoadedClaimsWithBibliography() {
  Object.keys(claimStores).forEach((layer) => {
    claimStores[layer].mechanistic = enrichClaimsWithBibliographyMetadata(
      claimStores[layer].mechanistic,
      "mechanistic"
    );
    claimStores[layer].disorders = enrichClaimsWithBibliographyMetadata(claimStores[layer].disorders, "disorders");
  });
}

function routeNativeFindingsFromPayload(payload) {
  return Array.isArray(payload?.findings) ? payload.findings : null;
}

async function loadActiveRouteNativeFindings(preview = false) {
  const config = await loadGraphPayloadConfig();
  const path = cleanDisplayText(preview ? config?.active_evidence_preview : config?.active_evidence_payload);
  if (!path) return null;

  const promiseKey = preview ? "routeNativeEvidencePreviewPromise" : "routeNativeEvidencePayloadPromise";
  if (preview && routeNativeEvidencePreviewPromise) return routeNativeEvidencePreviewPromise;
  if (!preview && routeNativeEvidencePayloadPromise) return routeNativeEvidencePayloadPromise;

  const task = fetchJsonFromCandidates(dataCandidates(path))
    .then(({ data }) => routeNativeFindingsFromPayload(data))
    .catch(() => null);

  if (promiseKey === "routeNativeEvidencePreviewPromise") {
    routeNativeEvidencePreviewPromise = task;
  } else {
    routeNativeEvidencePayloadPromise = task;
  }
  return task;
}

function routeNativeDisplayMode(finding) {
  const domain = normalizeValue(finding.domain || finding.kg_domain || finding.finding_type);
  if (HIDDEN_MAIN_GRAPH_DOMAINS.has(domain)) return "";
  if (ROUTE_NATIVE_DISPLAY_MODE_BY_DOMAIN[domain]) return ROUTE_NATIVE_DISPLAY_MODE_BY_DOMAIN[domain];
  const entityKind = normalizeValue(finding.entity_kind || finding.kg_entity_kind);
  return ROUTE_NATIVE_MECHANISTIC_ENTITY_KINDS.has(entityKind) ? "mechanistic" : "disorders";
}

function routeNativeSourceKey(finding) {
  const evidenceType = normalizeValue(finding.evidence_type || finding.kg_evidence_type);
  return evidenceType === "secondary_literature" ? "secondary" : "primary";
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

function routeNativeFindingForCurrentUi(finding, modeKey) {
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
      (routeNativeSourceKey(finding) === "secondary" ? "secondary_literature" : "primary_evidence"),
    access_level: accessLevel,
    source_access_level: accessLevel,
    evidence_location: cleanDisplayText(finding.evidence_location),
    evidence_locator: cleanDisplayText(finding.evidence_locator || finding.evidence_location),
    timepoint: cleanDisplayText(finding.assessment_timepoint || finding.timepoint),
  };
  if (modeKey === "mechanistic") {
    item.target = graphEntityLabel || entityLabel;
  } else {
    item.disorder = entityLabel;
  }
  return item;
}

async function loadRouteNativeEvidenceSource(modeKey, sourceKey, preview = false) {
  const findings = await loadActiveRouteNativeFindings(preview);
  if (!Array.isArray(findings)) return false;
  const items = findings
    .filter((finding) => !isHiddenMainGraphItem(finding))
    .filter((finding) => routeNativeDisplayMode(finding) === modeKey)
    .filter((finding) => routeNativeSourceKey(finding) === sourceKey)
    .map((finding) => routeNativeFindingForCurrentUi(finding, modeKey));

  if (preview) {
    graphPreviewByMode[modeKey][sourceKey] = items;
    graphPreviewLoaded[modeKey][sourceKey] = true;
    return true;
  }

  const enrichedItems = bibliographyPayloadsLoaded()
    ? enrichClaimsWithBibliographyMetadata(items, modeKey)
    : items;
  claimStores.normalized[modeKey] = dedupeClaims([
    ...(claimStores.normalized[modeKey] || []),
    ...enrichedItems,
  ]);
  normalizedSourceLoaded[modeKey][sourceKey] = true;
  return true;
}

async function loadGraphPreviewSource(modeKey, sourceKey) {
  if (graphPreviewLoaded[modeKey][sourceKey]) return;
  if (graphPreviewTasks[modeKey][sourceKey]) {
    await graphPreviewTasks[modeKey][sourceKey];
    return;
  }

  graphPreviewTasks[modeKey][sourceKey] = (async () => {
    if (!(await loadRouteNativeEvidenceSource(modeKey, sourceKey, true))) {
      throw new Error("Route-native graph preview payload is unavailable");
    }
  })();

  try {
    await graphPreviewTasks[modeKey][sourceKey];
  } finally {
    graphPreviewTasks[modeKey][sourceKey] = null;
  }
}

function currentSourceKey() {
  return isSecondaryEvidenceView() ? "secondary" : "primary";
}

function normalizedCurrentSourceLoaded() {
  return Boolean(normalizedSourceLoaded[mode]?.[currentSourceKey()]);
}

function activeGraphPreviewClaims() {
  const sourceKey = currentSourceKey();
  const baseClaims = graphPreviewByMode[mode]?.[sourceKey] || [];
  return graphViewClaims(claimsForEntityView(baseClaims));
}

async function renderCurrentGraphPreview(loadToken, resetDetail = true) {
  if (normalizedCurrentSourceLoaded()) return false;
  const sourceKey = currentSourceKey();

  try {
    await loadGraphPreviewSource(mode, sourceKey);
  } catch (_error) {
    return false;
  }

  if (loadToken !== currentDataLoadToken) return true;

  const previewClaims = activeGraphPreviewClaims();
  if (!previewClaims.length) return false;

  updateModeUI();
  syncYearFilterControls(previewClaims, true);
  const filtered = applyFiltersToClaims(previewClaims);
  if (selected && !selectionIsValid(filtered)) {
    selected = null;
    isolateSelection = false;
    clearSelectedStyles();
  }
  updateStats();
  buildGraph(filtered);
  if (resetDetail) {
    setDetailHeader(defaultDetail.title);
    if (selected) {
      renderSelectedDetailFromData(filtered);
    } else {
      renderOverviewDetail(filtered);
    }
    if (cardsEl) {
      cardsEl.innerHTML = '<div class="detail-empty">Loading findings...</div>';
    }
    if (studyListEl) {
      studyListEl.innerHTML = "";
    }
  }
  return true;
}

async function loadNormalizedClaimSource(modeKey, sourceKey) {
  if (normalizedSourceLoaded[modeKey][sourceKey]) return;
  if (normalizedSourceTasks[modeKey][sourceKey]) {
    await normalizedSourceTasks[modeKey][sourceKey];
    return;
  }

  normalizedSourceTasks[modeKey][sourceKey] = (async () => {
    if (!(await loadRouteNativeEvidenceSource(modeKey, sourceKey, false))) {
      throw new Error("Route-native graph payload is unavailable");
    }
  })();

  try {
    await normalizedSourceTasks[modeKey][sourceKey];
  } finally {
    normalizedSourceTasks[modeKey][sourceKey] = null;
  }
}

async function ensureClaimsForCurrentView() {
  await loadNormalizedClaimSource(mode, currentSourceKey());
}

async function loadCurrentClaimsAndRender({ showLoading = true, resetDetail = true, showGraphPreview = false } = {}) {
  const token = ++currentDataLoadToken;
  let previewRendered = false;
  if (showGraphPreview) {
    previewRendered = await renderCurrentGraphPreview(token, resetDetail);
  }
  if (token !== currentDataLoadToken) return;

  if (showLoading && !previewRendered) {
    renderDataLoading();
  }
  if (previewRendered) {
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
  updateModeUI();
  syncYearFilterControls(activeClaimsForMode(), true);
  if (resetDetail) {
    setDetailHeader(defaultDetail.title);
    renderDetailEmpty();
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

function preloadNormalizedSourceInBackground(modeKey, sourceKey, delay) {
  scheduleIdleTask(() => {
    loadNormalizedClaimSource(modeKey, sourceKey)
      .then(() => {
        applyClaimLayerStore();
        updateModeUI();
        updateStats();
      })
      .catch(() => {});
  }, delay);
}

function preloadLikelyNextData() {
  const alternateMode = mode === "mechanistic" ? "disorders" : "mechanistic";
  const saveData = Boolean(window.navigator?.connection?.saveData);
  const queue = saveData
    ? [[alternateMode, "primary"]]
    : [
        [alternateMode, "primary"],
        [mode, evidenceView === "primary" ? "secondary" : "primary"],
        [alternateMode, "secondary"],
      ];
  const seen = new Set();

  queue.forEach(([modeKey, sourceKey], index) => {
    const key = `${modeKey}:${sourceKey}`;
    if (seen.has(key)) return;
    seen.add(key);
    preloadNormalizedSourceInBackground(modeKey, sourceKey, 650 + index * 900);
  });
  scheduleIdleTask(loadBibliographyPayloadsInBackground, saveData ? 3000 : 4200);
}

async function init() {
  await loadGraphManifestStats();
  await loadCurrentClaimsAndRender({ showLoading: true, resetDetail: true, showGraphPreview: true });
  preloadLikelyNextData();
}

if (yearMinFilter) {
  yearMinFilter.addEventListener("change", scheduleRender);
}
if (yearMaxFilter) {
  yearMaxFilter.addEventListener("change", scheduleRender);
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
    renderCards(applyFilters());
  });
}
if (bibliographySearchInput) {
  bibliographySearchInput.addEventListener("input", () => {
    renderBibliography(applyFilters());
  });
}
if (fullTextOnlyToggle) {
  fullTextOnlyToggle.addEventListener("change", scheduleRender);
}
if (studiesStatCard) {
  studiesStatCard.addEventListener("click", focusBibliography);
  studiesStatCard.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      focusBibliography();
    }
  });
}
if (detailBody) {
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
    }
  });
  detailBody.addEventListener("click", (event) => {
    const target = event.target.closest?.(".interactive-bar, .composition-filter-target");
    if (!target || !detailBody.contains(target)) return;
    event.preventDefault();
    hideTooltip();
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
modeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    switchMode(button.dataset.mode);
  });
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
    switchEntityView(button.dataset.entityView || "", button.dataset.entityMode || mode);
  });
}
window.addEventListener("resize", scheduleRender);

init();
