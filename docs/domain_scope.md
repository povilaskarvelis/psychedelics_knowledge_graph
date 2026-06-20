# Domain Scope

## Goal
Build a knowledge graph for psychedelic compounds and related agents, focused on:
- receptor and transporter mechanisms
- compound-to-disorder treatment links
- strong provenance for every claim

## Inclusion Criteria
- Peer-reviewed study. Preprints are retained for corpus audit and
  published-version lookup, but are not promoted into default extraction routes.
- Clear mechanistic or clinical-outcome evidence
- Reported assay/outcome type and target/disorder
- Study year and DOI or stable ID

## Compound List (MVP)
- LSD
- Psilocybin (psilocin)
- Mescaline
- DMT
- 5-MeO-DMT
- MDMA
- Ketamine (including S- and R- enantiomers where reported)

## Target List (MVP)
- 5-HT2A
- 5-HT2C
- 5-HT1A
- SERT (SLC6A4)
- NET (SLC6A2)
- DAT (SLC6A3)
- NMDA receptor

## Disorder List (MVP)
- Treatment-resistant depression
- Major depressive disorder
- Post-traumatic stress disorder
- Alcohol use disorder
- Tobacco use disorder
- Cancer-related anxiety and depression
- Anxiety associated with life-threatening disease

## Notes
- Classic serotonergic psychedelics are primarily 5-HT2A agonists; MDMA and
  ketamine are included as mechanistically adjacent but non-classic agents.
- Evidence grading and provenance rules are defined in `docs/evidence_policy.md`.
- Target and disorder lists can expand once the pipeline is stable.
