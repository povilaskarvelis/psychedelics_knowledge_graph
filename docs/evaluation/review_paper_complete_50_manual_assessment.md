# Manual assessment of 50 paper-complete review extractions

Date: 2026-07-11  
Annotator: Codex, by direct inspection of the supplied paper text, extraction
outputs, normalized findings, and normalization audit. No evaluator model was
used for these judgments.

## Assessment basis

The cohort contains every routed domain extraction for 50 reviews (186 domain
tasks). Twenty-nine papers had article text in the extraction corpus. For the
other 21, the assessment is necessarily limited to what is stated in the title
and abstract. `Extraction` assesses the union of all domain outputs for the
paper. `Graph` assesses what survived conversion and normalization. `Routing`
asks whether the psychedelic relationships are genuinely central to the paper,
not merely present somewhere in it.

Ratings are deliberately coarse:

- **good**: the main paper-level relationships are represented without a
  material change in meaning;
- **partial**: important components are present, but a central relationship,
  qualification, or organizing frame is missing or distorted;
- **poor**: the output misses or misstates the paper's defining contribution.

## Overall result

| Stage | Good | Partial | Poor / overreach |
|---|---:|---:|---:|
| All-domain extraction union | 38 | 9 | 3 |
| Normalized graph bundle | 13 | 17 | 20 |
| Routing fit | 41 good | 5 mixed | 4 overreach |

This is the central result: running every tagged domain substantially improves
topic recall, but it does not solve paper-level centrality. The largest loss is
after extraction. Thirty-seven of 50 graph bundles are partial or poor even
though only 12 of 50 extraction unions are partial or poor.

The normalization audit contains 161 held rows, all of which had already been
marked `main_focus` or `substantial_topic` by extraction. Sixty-seven held rows
were marked `main_focus`. The largest hold reasons are broad compound/class
labels (45), unmapped entities (40), compound combinations (24), and unmapped
compounds (22). Seven papers with non-empty extraction bundles produce no graph
findings at all.

## Paper-by-paper assessment

| # | DOI | Source | Paper-defining bundle that should govern the graph | Extraction | Graph | Routing | Main diagnosis |
|---:|---|---|---|---|---|---|---|
| 1 | 10.1002/hup.351 | abstract | MDMA acute desired and adverse effects; longer-term mood, cognitive, and neurotoxicity concerns | good | partial | good | Regional, rebound-mood, and higher-cognition claims are lost or duplicated after normalization. |
| 2 | 10.1002/jcph.266 | abstract | MDMA pharmacology and exposure, together with context, produce both desired prosocial effects and acute harms | good | partial | good | Rave/environment context and differentiated toxicities are compressed into broad nodes. |
| 3 | 10.1007/s00213-022-06106-8 | article | A translational PK/PD and cognitive-task framework for separating hallucinatory or mystical effects from antidepressant effects | partial | partial | good | Domain rows recover components but not the paper's methodological relationship between them. |
| 4 | 10.1007/s11910-024-01353-y | article | Psychedelic neurochemistry and brain-network changes as an account of self-awareness | good | poor | good | Central class-level relationships are held; isolated named-compound details remain. |
| 5 | 10.1007/s11916-025-01437-5 | abstract | Ketamine for opioid use disorder in people with chronic pain, including mechanism and safety | good | good | good | No material paper-level failure in the available abstract. |
| 6 | 10.1007/s40473-015-0052-3 | article | Clinical status of ketamine for mood and anxiety disorders, linked to NMDA/plasticity mechanisms and safety | good | good | good | Main clinical and mechanistic bundle survives. |
| 7 | 10.1007/s40501-025-00346-z | article | Whether ketamine-assisted psychotherapy adds value over ketamine for TRD; evidence is preliminary and insufficient | good | good | good | Relationship survives, but the uncertainty must remain visible on the edge/card. |
| 8 | 10.1016/bs.irn.2025.02.003 | abstract | Clinical pharmacology of serotonergic psychedelics and MDMA: targets, PK, subjective effects, tolerance, and harms | good | poor | good | Broad class and multi-compound relationships are held, leaving an MDMA-skewed fragment. |
| 9 | 10.1016/j.biopha.2025.118199 | abstract | Ketamine, esketamine, and arketamine for TRD in Alzheimer disease and older adults | good | poor | good | Five useful extracted items yield no graph findings because the central compound grouping is not representable. |
| 10 | 10.1016/j.bpsgos.2025.100610 | article | Bibliometric landscape and therapeutic shifts in TRD research | poor | poor | good | A paper-to-research-topic contribution is forced into compound-to-condition rows and misstates the paper. |
| 11 | 10.1016/j.brainresbull.2016.04.016 | article | DMT pharmacology: endogenous role, targets, PK, effects, and safety | good | partial | good | Core DMT material survives, but speculative clinical/context rows receive too much weight and some central detail is lost. |
| 12 | 10.1016/j.conb.2015.11.001 | abstract | NMDA antagonism and downstream plasticity/circuit mechanisms in depression | good | good | good | Main abstract-visible relationship is retained. |
| 13 | 10.1016/j.drugpo.2018.11.014 | abstract | Multi-drug chemsex practices and harms among men who have sex with men | poor | poor | overreach | Ketamine is peripheral to the stated scope, but the routed bundle makes it appear to define the paper. |
| 14 | 10.1016/j.drugpo.2021.103473 | abstract | The absence and pattern of NIH funding for psychedelic-assisted therapy trials | good | poor | good | Correct abstract-level extraction, but the funding relationship yields no graph finding. |
| 15 | 10.1016/j.forsciint.2018.01.006 | abstract | LSD toxicity, including reported severe and fatal outcomes | good | good | good | Main abstract-visible safety relationship survives. |
| 16 | 10.1016/j.neubiorev.2020.03.017 | abstract | Long-term psychological, cognitive, clinical, and safety outcomes of classic psychedelics | good | poor | good | Central abstract-level class synthesis is held; selected named-compound fragments remain. |
| 17 | 10.1016/j.neubiorev.2025.106239 | abstract | Human neuroimaging evidence on psilocybin's neurocognitive and functional-connectivity effects | good | partial | good | Default-mode-network material survives, but much of the connectivity and self/sensory/social synthesis does not. |
| 18 | 10.1016/j.neuropharm.2012.05.022 | abstract | mGlu2/3 and mGlu5 receptors as antidepressant targets; ketamine is supporting context | partial | poor | overreach | Routing and compound anchoring turn the abstract-visible glutamate-receptor scope into a ketamine paper. |
| 19 | 10.1016/j.neuropharm.2022.109348 | abstract | Post-ketamine glutamatergic antidepressant strategies, their mechanisms, efficacy, and safety | good | partial | good | Mechanistic pathways survive better than the comparative clinical and safety synthesis stated in the abstract. |
| 20 | 10.1016/j.pnpbp.2026.111634 | abstract | Prospective evidence on longer-term mental and physical health after ayahuasca | good | partial | good | Some depression and public-health content survives, while safety and neurometabolic conclusions are incomplete. |
| 21 | 10.1016/s2215-0366(22)00317-0 | abstract | Maintenance ketamine for depression: durability, efficacy, safety, addiction risk, and tachyphylaxis | good | good | good | Main bundle survives; grouped safety could preserve specific longer-term risks more explicitly. |
| 22 | 10.1037/pha0000490 | abstract | Ethnoracial disparities and ethnopsychopharmacology in psychedelic-assisted psychotherapy | good | poor | good | Four extracted relationships yield no graph finding because the subject is class-level and contextual. |
| 23 | 10.1080/10550887.2023.2174785 | article | Psychological, biological, and cultural relationships between spirituality and substance-use disorders | poor | poor | overreach | Psilocybin is one application within a broader spirituality review but becomes the apparent paper identity. |
| 24 | 10.1080/14728214.2021.1898588 | abstract | Dextromethorphan, alone or with bupropion, for depression across preclinical and clinical evidence | good | good | mixed | Extraction and graph are coherent, but the compound's inclusion within the psychedelic KG is a scope-policy decision. |
| 25 | 10.1080/14740338.2022.2063273 | abstract | HPPD frequency, risk factors, prevention, and treatment after hallucinogen exposure | good | poor | good | The paper is intrinsically class-level; four extracted items yield no graph finding. |
| 26 | 10.1080/17460441.2025.2562017 | abstract | Validity and limits of NMDA-antagonist schizophrenia models for drug discovery | good | poor | good | The graph retains a ketamine-to-NMDA fragment but loses model validity and behavioral phenotype relationships. |
| 27 | 10.1089/psymed.2023.0017 | article | A translational agenda for preventing psychedelic research gaps from becoming practice pitfalls | partial | poor | good | The current compound-edge schema cannot represent a research agenda; no graph finding remains. |
| 28 | 10.1093/ijnp/pyab039 | article | How psychiatric medications modify ketamine efficacy and adverse effects | partial | poor | good | The defining drug-drug interaction pairs are not graph anchors; generic ketamine effects remain instead. |
| 29 | 10.1124/pr.115.011478 | article | Broad class review of psychedelic pharmacology, mechanisms, effects, therapeutic evidence, and safety | good | partial | good | Many named details survive, but the class-level organizing synthesis is held. |
| 30 | 10.1177/28314425251364182 | abstract | DPT and DET evidence for addiction outcomes and safety | good | partial | good | DPT-alcohol material survives, while DET and much of safety do not. |
| 31 | 10.1192/bjp.2024.277 | article | MDMA-assisted exposure and response prevention for OCD, supported by fear-extinction and plasticity mechanisms | good | partial | good | The central EX/RP combination is held while a narrower family-based EX/RP context survives. |
| 32 | 10.1590/0101-60830000000027 | article | Biomarkers as a route to better mood-disorder therapeutics; ketamine is an example | partial | poor | mixed | The graph makes ketamine the paper identity and loses the biomarker-development frame. |
| 33 | 10.18203/2394-6040.ijcmph20260152 | article | Mechanisms and management of TRD, with ketamine and psychedelics among several emerging approaches | partial | partial | mixed | All-domain extraction recovers more, but psilocybin/DMN and esketamine receive more paper-level prominence than warranted. |
| 34 | 10.2147/dddt.s356284 | article | Esketamine publication trends, hotspots, and future research directions | good | poor | good | The two extracted bibliometric themes yield no graph findings; a paper-to-topic form is missing. |
| 35 | 10.33448/rsd-v12i14.44436 | article | Cognitive effects of psychedelics in healthy volunteers, alongside the review's overall safety conclusion | good | good | good | Main cognitive bundle survives; isolated minor adverse events should not outrank the review-level safety conclusion. |
| 36 | 10.3389/fnana.2022.795231 | article | Structural and functional brain changes, memory, and executive harms associated with long-term ketamine abuse | good | partial | good | Central regional and white-matter findings are compressed into neurotoxicity, and memory is over-normalized to spatial memory. |
| 37 | 10.3389/fnbeh.2011.00001 | article | Comparative drug-induced psychosis models involving LSD, amphetamine, cannabis, and PCP | good | poor | mixed | A multi-model review is reduced to LSD-5-HT2A and ketamine-glutamate fragments; local `main_focus` labels are misleading globally. |
| 38 | 10.3389/fphar.2021.749068 | article | Potential serotonergic-psychedelic use in autism: social behavior, mechanisms, clinical promise, and safety | good | partial | good | Main topics are recovered, but class-level 5-HT2A and seizure relationships are held and social-behavior rows duplicate. |
| 39 | 10.3389/fpsyg.2025.1469559 | article | MDMA therapy for trauma as a synergy among inner healing intelligence, witnessing, and therapist attitude | good | partial | good | Distinct central constructs collapse into the same non-directive-support node. |
| 40 | 10.3390/brainsci15050424 | article | Multi-drug clinical psychopharmacology and harms of chemsex | partial | poor | overreach | MDMA and ketamine are relevant subsets, but the graph presents them as the whole paper and drops other central drug harms. |
| 41 | 10.3390/cells11040645 | article | Whether ketamine plus lamotrigine improves mood outcomes, dissociation, or craving; human evidence is inconclusive | good | poor | good | Normalization strips lamotrigine and converts combination findings into ordinary ketamine edges. |
| 42 | 10.3390/molecules31030545 | article | Ibogaine reduces withdrawal/craving but has an overlapping cardiac-risk window; its main value may be as a lead for safer analogues | good | partial | good | Efficacy and safety components survive, but hERG/habenular combination rows and the paper's lead-compound conclusion do not. |
| 43 | 10.3390/ph18040499 | article | LSD clinical uses, PK, brain-network effects, psychotherapy context, subjective effects, and safety | good | good | good | The broad review is represented with only secondary losses. |
| 44 | 10.3390/ph18040555 | article | Psilocybin clinical uses, mechanisms, PK, psychotherapeutic integration, and safety | good | good | good | The broad review is represented with only secondary losses. |
| 45 | 10.3390/ph18060867 | article | Anti-inflammatory effects of antidepressant classes, including ketamine/esketamine, in depression | partial | partial | mixed | The psychedelic-scoped subset is extracted, but the graph overstates ketamine as the paper focus and turns biomarker changes into a TRD efficacy edge. |
| 46 | 10.54254/2753-8818/32/20240910 | article | Limited evidence for cannabis and psychedelics in military/veteran mental health, including MDMA for PTSD | good | partial | good | MDMA-PTSD survives, while the multi-compound scope and ibogaine/5-MeO-DMT evidence are lost. |
| 47 | 10.64239/pi-capst1804 | abstract | Esketamine for youth depression and its reported effects on processing speed, working memory, and verbal learning | good | good | good | The abstract-visible bundle survives; no article-text completeness claim can be made. |
| 48 | 10.7324/japs.2024.177533 | article | Growth and thematic structure of ketamine-and-depression research | partial | poor | good | Extracted themes are plausible, but all four are held and the actual bibliometric relationship is absent. |
| 49 | 10.7759/cureus.105219 | article | Esketamine as a possible dual treatment for TRD with SUD, including craving/drug seeking and glutamatergic mechanisms | good | good | good | Main bundle survives with appropriate preliminary-evidence caveats. |
| 50 | 10.7759/cureus.30214 | article | Psilocybin therapeutic evidence across cancer distress, TRD, addictions, OCD, and headache, with 5-HT2A mechanism and safety | good | good | good | Main bundle survives. |

## What the scripts show

The current review prompt tells each routed domain to build a
`substantive_coverage_inventory` "in the selected scope." That means there is
not one paper inventory. There are up to ten independent domain inventories.
Likewise, `main_focus` is assigned inside each domain call. It therefore means
"main within this routed slice," not "main to the paper." Combining all tagged
domains cannot recover that missing cross-domain ordering after the fact.

The converter then admits every review item labeled `main_focus` or
`substantial_topic`, with no paper-level budget or rank. The normalizer requires
one registered compound and one graphable entity per edge. It explicitly holds
broad compound classes and multi-compound labels. These rules are reasonable
for atomic primary-study edges, but they are destructive for reviews whose
defining contribution is often class-level, comparative, combinatorial,
bibliometric, methodological, or contextual.

There is also a dangerous asymmetry: a multi-compound label may sometimes be
held completely, but when the text contains only one registered focal compound
plus an unregistered co-intervention, the registered compound can survive by
itself. That is how a ketamine-plus-lamotrigine conclusion becomes a ketamine
relationship. This is not merely missing data; it changes the proposition.

## Diagnosis and order of work

1. **Do not expand this exact extraction design to more reviews yet.** The
   50-paper paper-complete batch is already large enough to show that missing
   routed domains are not the main bottleneck.
2. **Add a review-only paper frame before domain extraction.** It should record
   the review question, the paper-defining compound/class/intervention units,
   the major conclusions and qualifications, and a short ordered list of
   paper-level relationship IDs. For article text, it should use objectives,
   dedicated sections/tables, repeated synthesis, and conclusions—not merely
   reuse the title/abstract routing tags.
3. **Make domain rows link back to that frame.** Each row needs a
   `paper_relationship_id`, plus two separate prominence fields:
   `domain_prominence` and `paper_prominence`. A locally central row should not
   become globally central automatically.
4. **Preserve non-atomic review propositions.** Add graph forms for compound
   classes, combination/regimen nodes, paper-to-topic relationships, and
   interaction/modifier relationships. Until those forms exist, hold the whole
   proposition; never silently reduce a combination to one compound.
5. **Carry certainty and synthesis meaning into graph visibility.** Mixed,
   insufficient, descriptive, bibliometric, and agenda-setting relationships
   should not look like affirmative efficacy findings.
6. **Add a paper-level admission step for reviews only.** Select a small set of
   paper-defining and major-supporting relationships from the linked frame,
   deduplicate cross-domain restatements, and keep peripheral/subset material in
   the paper detail view rather than the main graph.
7. **Rerun the same 50 after those changes.** This is the development set. Once
   the 50 improve against these manual judgments, run a new disjoint set of 50
   as validation. Running more papers before fixing the representation would
   mostly produce more instances of already-diagnosed failures.

This should be implemented as a review-specific branch. The current routed,
atomic pipeline can remain in place for primary studies, where one-compound,
one-entity edges are a much better fit.
