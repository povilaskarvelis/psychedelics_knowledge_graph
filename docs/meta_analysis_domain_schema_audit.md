# Meta-Analysis Domain Schema Audit

Generated: 2026-06-24

This was a no-model audit of the current meta-analysis extraction schemas
against local article-text inputs. The runner uses:

- paper type and text depth to select the prompt
- domain route to select `schema/extraction_profiles/meta_analysis/<domain>.schema.json`
- the same domain schema for `article_text` and `abstract_only`

## Summary

The domain-specific meta-analysis schemas mostly match the kinds of meta-analysis
results present in local examples. The useful common fields are already in
`synthesis_results[]`: result role, analysis type, contrast type, population,
intervention/exposure, comparator, endpoint, effect metric, effect size, CI,
p value, study and participant counts, heterogeneity, network fields, locator,
and supporting quote.

Two schema issues were found and fixed:

- All synthesis domain-result fields had no JSON Schema descriptions. Short
  descriptions were added to every domain schema so the schema itself carries
  field meaning.
- Molecular-target meta-analyses often need target-specific context beyond the
  common effect-size fields. The molecular-target schema now captures target
  evidence category, tissue/region, comparator/reference, target-level
  effect/change, ligand/probe, and selectivity/off-target context.

No individual included-study DOI extraction was added. The inspected examples
support keeping that out of the first extraction contract.

## Domain Checks

| Domain | Local examples inspected | Schema fit |
| --- | --- | --- |
| `clinical_outcome` | `10.1001/jamanetworkopen.2025.24119`; `10.1001/jamapsychiatry.2022.3352`; `10.7759/cureus.15070` | Mostly fits, with added clinical detail. Examples report clinical population, intervention/comparator, outcome scale, endpoint category, response/remission definitions or rates, score direction, effect sizes, CIs, study counts, follow-up windows, and moderator/meta-regression variables. Added clinical endpoint category, benefit-basis, response/remission definitions, and moderator/predictor fields. |
| `safety_tolerability` | `10.1001/jamanetworkopen.2024.5960`; `10.1001/jamapsychiatry.2024.2546`; `10.1038/s41386-024-01865-8`; `10.3389/fphar.2025.1681060`; `10.12809/hkmj209194` | Needed added safety detail. Examples report acute vs delayed windows, raw event counts/rates, nonserious events requiring medical or psychiatric attention, transient vs persistent events, discontinuation, AE ascertainment/reporting quality, and risk contexts such as neuropsychiatric history or cardiovascular exclusions. Added fields for assessment window, numerator/denominator, medical/psychiatric attention, duration/resolution, ascertainment/reporting method, and risk/population context. |
| `molecular_target` | `10.1016/j.csbj.2025.12.023`; `10.1016/j.neubiorev.2016.02.003`; `10.1176/appi.ajp.2015.15040465`; `10.1038/s41398-024-03187-1`; `10.1038/s41398-025-03638-3`; `10.3389/fphar.2021.739053`; `10.1017/s0033291716000064` | Needed more target context. Examples include network-predicted druggable targets, SERT/PET availability by brain region, NMDA-antagonist target-class trials, psychedelic receptor affinity/activity, 5-HT2A radioligand occupancy, salvinorin A/kappa-opioid receptor agonism, and selectivity or off-target caveats. Added target evidence category, comparator/reference, target-level effect/change, ligand/probe, and selectivity/off-target context, alongside the existing tissue/region field. |
| `molecular_pathway_readout` | `10.1038/s41380-022-01652-1`; `10.1038/s41380-024-02830-z`; `10.1038/mp.2017.190`; `10.1016/j.csbj.2025.12.023`; `10.1038/s41398-025-03654-3`; `10.1038/s41398-025-03638-3`; `10.1038/tp.2016.71` | Needed more readout context. Examples include blood biomarkers as baseline predictors or longitudinal response correlates, peripheral BDNF changes after psychoplastogens, ketamine effects on dopamine levels, pathway enrichment/network analyses, and inflammatory or neuroprotective pathway readouts. Added readout category, readout relationship, comparator/reference, timing, dose/exposure context, and data source/feature set. |
| `brain_system` | `10.1038/s41591-026-04287-9`; `10.1016/j.neubiorev.2016.02.003`; `10.1038/mp.2017.190`; `10.1016/j.nicl.2025.103874`; `10.1017/s109285292610087x`; `10.1038/s41398-024-03187-1`; `10.3389/fphar.2021.739053`; `10.3390/ph16040568` | Needed more neural context. Examples include coordinate-based treatment-response meta-analysis, PET/SPECT receptor or transporter availability by brain region, dopamine levels by region, reward-circuit fMRI, resting-state psychedelic circuit mega-analysis, task-based psychedelic activation meta-analysis, and sleep/EEG synthesis. Added analysis method, neural effect/change, circuit relationship, spatial/network context, dose/exposure context, and clinical/behavioral context. |
| `cognitive_behavioral` | `10.1038/s41598-025-25610-3`; `10.1038/s41598-024-74810-w`; `10.1007/s00213-024-06742-2`; `10.1002/hup.1270`; `10.1017/s0033291716000258`; `10.1038/s41598-024-65391-9`; `10.1038/s41398-025-03638-3`; `10.1038/tp.2016.71`; `10.3389/fpsyg.2023.1176564`; `10.3389/fnins.2022.1011103` | Needed more behavioral task context. Examples include empathy and emotion recognition by valence, attention/executive-function reaction time and accuracy, visuospatial memory task categories, executive-function subdomains, false-memory outcomes, ketamine cognition/social functioning, animal addiction and pain behavior, and confounding from polydrug/cannabis use. Added construct category, task condition/subdomain, outcome metric, behavioral effect/change, moderator/subgroup, and confounding/adjustment context. |
| `subjective_experience` | `10.1001/jamanetworkopen.2020.4693`; `10.1177/0269881121992676`; `10.1038/s41386-023-01588-2`; `10.1038/s44184-024-00091-w`; `10.1177/0269881115609019`; `10.1371/journal.pone.0258849`; `10.1016/j.jpainsymman.2026.03.012`; `10.1177/02698811251319455`; `10.1016/j.bpsgos.2025.100521`; `10.1038/s41398-024-03187-1` | Needed more subjective-experience context. Examples include ketamine psychotomimetic and dissociative symptoms, psilocybin/LSD dose-response scale dimensions, MEQ30 mystical-experience factors, subjective-effect correlations with therapeutic outcome, MDMA social connection, qualitative serious-illness and finitude themes, NLP language markers, and dissociation-induction methods. Added construct category, scale/subscale/dimension, comparator/reference, assessment context, subjective effect/change, valence/quality, and dose-response/moderator context. |
| `pharmacokinetics_exposure` | `10.1001/jamanetworkopen.2020.4693`; `10.1007/s00213-022-06083-y`; `10.1016/j.eclinm.2023.102127`; `10.1038/s41380-022-01652-1`; `10.1038/s41386-023-01588-2`; `10.1038/s41398-025-03638-3`; `10.1177/0269881121992676`; `10.3389/fcomp.2025.1652190` | Needed more exposure-modifier context. Examples include ketamine bolus/infusion and route effects, MDMA/psilocybin drug interactions with psychiatric medications, CYP-mediated MDMA interaction risk, oral psilocybin dose normalization to micrograms per kilogram, LSD dose-response up to 200 micrograms base, ketamine/esketamine dose and route conversion to intravenous racemic ketamine equivalents, ketamine/metabolite blood levels by responder status, salvinorin A route distributions and delivery limitations, and computational PK/digital-twin modeling. Added evidence category, dose standardization/equivalence, comparator/reference, co-exposure/modifier, metabolic/transport pathway, and exposure-response or PK-effect context. |
| `intervention_context` | `10.1001/jamanetworkopen.2025.54843`; `10.3389/fpsyt.2024.1439347`; `10.1089/psymed.2023.0054`; `10.1038/s41386-024-01865-8`; `10.1002/npr2.12485`; `10.1007/s12325-021-01732-8`; `10.1016/j.jpainsymman.2026.03.012`; `10.3390/curroncol32070380`; `10.3389/fpsyt.2023.1268832`; `10.1556/2054.2023.00294` | Needed more protocol and care-model context. Examples include psychological therapy quantity, preparation and integration hours, diverse psilocybin psychological protocols, manualized vs nonmanualized support, therapist personal experience and training, MDMA-assisted psychotherapy structure, ketamine maintenance and adjunctive strategies, serious-illness/cancer therapeutic context, biomedical vs psychedelic ketamine care models, music/session preferences, and stakeholder implementation barriers. Added intervention model/orientation, component quantity/intensity, adjunctive or co-intervention strategy, provider/facilitator context, protocol standardization/fidelity, and implementation/acceptability context. |
| `real_world_public_health` | `10.3310/hta13060`; `10.1556/2054.2023.00294`; `10.3389/fphar.2021.739966`; `10.1177/20420986261436104`; `10.1111/j.1360-0443.2007.02041.x` | Needed more real-world context. Examples include recreational/ecstasy exposure patterns, stakeholder attitudes, pregnancy exposure counseling, social-cognitive determinants of use, observational comparison groups, and implementation or policy implications. Added fields for topic category, data source/study design, exposure pattern/intensity, comparison/reference group, confounding/adjustment, and policy/practice implication. |
| `general_topic` | No local `secondary_meta_analysis` article-text sample in `article_text_inputs_audit.csv`. | Schema remains a fallback coverage shape. It should not be a main KG evidence route. |
| `general_topic_coverage` | No local `secondary_meta_analysis` article-text sample in `article_text_inputs_audit.csv`. | Same as `general_topic`: keep for broad coverage/accounting, not as a preferred KG evidence route. |

## Notes For Testing

When we run model pilots, the highest-value checks are:

- whether abstract-only meta-analysis outputs leave unavailable full-article
  fields empty rather than hallucinating them
- whether molecular-target outputs distinguish binding/affinity, functional
  activity, occupancy or availability, network-predicted targets, and
  target-class intervention evidence
- whether pathway/readout outputs distinguish treatment-induced changes,
  baseline predictors, response associations, pathway enrichment, and
  network-association evidence
- whether brain-system outputs distinguish analysis method, neural effect/change,
  circuit relationship, spatial/network context, and clinical or behavioral
  linkage without turning neural effects into clinical benefit/harm
- whether cognitive/behavioral outputs distinguish construct category, task
  condition or subdomain, outcome metric, behavioral effect/change, moderators,
  and confounding or adjustment context
- whether subjective-experience outputs distinguish scale dimension or theme,
  valence or quality, dose-response or moderator context, and explicit outcome
  linkage without treating all altered-state discussion as extractable
  subjective evidence
- whether PK/exposure outputs distinguish measured or synthesized exposure
  evidence from ordinary trial dose context, and capture dose standardization,
  comparator/reference, co-exposure/modifier, metabolic or transport pathway,
  and exposure-response or PK-effect context
- whether intervention-context outputs distinguish central intervention
  components from ordinary trial procedures, and capture therapy model,
  component quantity, adjunctive strategies, provider/facilitator context,
  protocol standardization, and implementation or acceptability context
- whether non-clinical domains keep `result_direction` as `not_applicable`
- whether broad/noisy real-world examples should be excluded upstream or routed
  to `general_topic_coverage`
