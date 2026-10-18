# Extract original findings with their scientific comparisons

## Task and input

Extract the central original findings in the assigned scientific domain from the supplied research source. Use its metadata for identification and its source text for scientific claims. Return the supplied domain JSON schema. The source may be an abstract or an article packet with section, table and figure locators. Other papers, your background knowledge and prior screening decisions do not supply missing evidence.

## Eligible evidence

The project concerns classic psychedelics, MDMA and related entactogens, ketamine/esketamine/arketamine and analogues, ibogaine/noribogaine, salvinorin A, and related psychedelic compounds. Original experimental, observational, qualitative, descriptive and null findings can qualify. Research on an eligible drug's mechanisms, exposure, nonmedical toxicity, or modification of its effects can qualify in humans, animals, tissue, cells or simulations. An unrelated stimulant, cannabinoid or generic receptor experiment does not qualify merely through a structural resemblance or an NPS label. Ketamine work solely about anesthesia, sedation, analgesia or veterinary anesthesia is outside scope; substantive psychiatric outcomes and otherwise eligible drug mechanisms remain eligible regardless of setting.

A paper's inclusion does not make every result eligible. Keep nonpsychedelic controls and mechanistic perturbations within the relevant psychedelic comparison. A drug appearing only as a reagent, tracer, historical exposure or comparator to characterize another treatment does not establish a focal drug effect. A complete intervention package and a mixed exposure must retain their identities when components were not tested independently.

## Assigned scientific domain

{{DOMAIN_SCOPE}}

## Select results before filling fields

Identify the original experiments or analyses that supply central findings for this domain. For article text, inspect the Results/Findings and relevant tables and figure captions as well as the abstract; the abstract's emphasis is not an exhaustive result inventory. For an abstract, use only what it states, without reconstructing full-text methods or secondary analyses.

Cover distinct main experiments and the contrasts needed to interpret them. Include a central null, opposing result, failed replication, lack of rescue, dose/time restriction or subgroup difference when it materially limits a retained finding. Preserve qualitative and descriptive results without requiring inferential statistics. Central coverage takes priority over many repetitive markers from one experiment. Do not fill unrelated domains or create standalone items for background, cited findings, isolated methods or nonpsychedelic controls.

## Form one interpretable observation per item

An observation links a focal exposure or predictor to a measured outcome in a specific comparison. Separate items when exposure, outcome, comparator, experimental preparation, analysis population, timing or conclusion differs materially. Preserve a true interaction or package as one comparison. A compact series of values may share an item only when every value's condition, time and denominator remain explicit and the conclusions are consistent.

Before transcribing a number, identify its table row or figure panel, outcome column, treatment/contrast, analyzed sample and measurement time. Attach the value, uncertainty and statistical test to that same observation. A number appearing nearby is not evidence of that assignment. Keep participant counts distinct from animals, cells, spines, specimens, encounters and documents; retain nested sampling when reported. A study-wide sample is context, not an endpoint denominator. For pooled sex/cohort totals, preserve how many belong to each experiment rather than copying the pooled total into every experiment.

Use the actual comparison: placebo or active control, within-person baseline, dose contrast, predictor association, or a descriptive result without a comparator. Keep endpoint-specific predictors with their reported outcomes. A within-group change is not evidence of superiority to the other arm. A nonsignificant comparison means no detected difference, not equivalence. Keep statistical direction separate from clinical benefit or harm.

## Preserve scientific roles and measurement meaning

Name the measured entity or construct precisely; a parent graph category groups it but does not replace it. Distinguish receptor identity from its endogenous ligand; measured binding from a functional response or tracer signal; expression from phosphorylation, concentration, release or enzyme activity; anatomical location from cell population or subcellular structure. Use a controlled label only when its defined meaning fits. The word “perception” in an attitude study does not establish a sensory alteration.

Record the experimental preparation for this finding. Human protein origin does not make a simulation clinical research. Excised intact tissue is an ex-vivo preparation, whereas cultured cells are an in-vitro cell model. Describe mixed in-vivo dosing/ex-vivo measurement explicitly. Preserve the actual species independently of the preparation. Randomized design requires source evidence of random allocation; a phase number alone is insufficient.

For safety and context, distinguish observed adverse events from anticipated risks, eligibility restrictions and recommended care. Assign management actions to the event for which the source reports them. Separate recreational co-exposures from medication administered during treatment. Observed animal proxies retain their species and task; they are not diagnoses in human participants. Keep a measured experience, an observed interaction and a reported attitude distinct. Context associated with an outcome is not automatically an independently effective intervention component.

## Handle missing or damaged evidence

Use `not_reported` for missing information and `not_applicable` only when a field does not apply. Retain an interpretable qualitative result when a numerical value is uncertain. If row/column attribution, symbols, units or values are unreadable or inconsistent, leave the affected value unavailable and add a specific warning with its source locator. Do not guess a repair from plausibility or memory. Do not replace all suspicious units uniformly: a local concentration can legitimately differ from another experimental regimen. A warning does not license a confident contradictory value elsewhere in the item.

{{STRUCTURED_FIELDS}}

## Output and final check

Return only one JSON object matching the supplied schema and exact enums. Preserve task/route identity. Use the supplied article locators or `Abstract` for abstract-only evidence. Add `abstract_only_limited_detail` for an abstract. Keep statistics and locators concise, with sufficient labels to recover the comparison.

Use `extracted` if there is usable original scoped evidence; otherwise use `no_extractable_scoped_evidence`, `wrong_source_type`, `not_relevant` or `human_review` according to the source, with an empty items array and a short reason in warnings. Missing statistics, qualitative evidence and null results do not by themselves justify abstention.

Check that every item's labels, summary, statistics and sample descriptions agree; that central limiting contrasts are represented; and that each asserted number is bound to its own source analysis. Preserve useful rich detail, while keeping unrelated results and speculative repairs out of factual fields.
