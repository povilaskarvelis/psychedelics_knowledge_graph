# Author identity review — pass 3, 2026-09-06

## Scope and results

Reviewed all 13 conflicting-ORCID profiles (122 authorship rows) and all 76 papers with repeated identities flagged after pass 2. This is a targeted review, not a claim that every author identity in the corpus has been independently verified.

- Four conflicting profiles corrected: Jay Yang, Holly Moore, Jordi Segura, and Yeow-Kuan Chong. Five source rows carried an ORCID whose public owner was a different person. Correcting those rows allowed consistent identifiers to propagate within those four profiles.
- Nine conflicting profiles, covering 99 rows, remain explicitly unresolved after checking ORCID owner records, available affiliations/works, and publication metadata. These were investigated, not skipped.
- Corrections applied to 68 of the original 76 papers. Five papers preserve individual plus group/investigator credits. Three retain source-level repetition that could not be resolved safely.
- Three of the 68 corrected papers still have a narrower unresolved question: competing author-list versions (10.1002/hup.1242), or two same-name authors with different affiliations (10.1002/advs.202303503 and 10.1016/j.jad.2020.01.002). Thus six papers retain an unresolved question in total.
- A rebuild exposed one additional duplicated Tung-Hsia Liu entry on 10.1016/j.jpsychires.2023.01.009. Crossref lists one entry; that duplicate was also corrected.
- Final total: 69 paper-specific author-list reviews, removing 104 excess entries. Repairs also reassign profiles that source duplication had shifted onto subsequent authors, and clear unsupported identifiers to name-only identities.

Graph paper-detail citation text uses the reviewed ordered names, including names whose structured profile is unresolved. Original metadata is retained. Review records include publication links, reviewer/date, rationale, and a fingerprint of the original ordered author list. Source drift stops the build for renewed review. Repeated names are never globally deduplicated.

## Final local tables

| Measure | Value |
|---|---:|
| Papers | 22,137 |
| Author identities | 64,852 |
| Authorship rows | 116,698 |
| Remaining conflicting ORCID profiles | 9 |
| Papers with repeated identity credits | 11 |
| Remaining different-name identity collisions within papers | 0 |
| Duplicate author positions / orphan authorships | 0 / 0 |

The 11 papers with repeated credits comprise five retained group-credit lists and six unresolved source/identity cases. They are not 11 confirmed duplicate errors. The broad name audit still has 2,416 candidate groups; these are possible matches, not verified errors, and were outside this targeted pass.

Earlier reviewed identities retain their paper totals: Robin Carhart-Harris 230, Matthias E. Liechti 181, Joshua D. Rosenblat 121, Leor Roseman 78, and David Nutt 136. Other initial-only name variants are not claimed resolved by these totals.

The papers, findings, entities, evidence edges and original OpenAlex cache are byte-identical to the preceding research-area release. Changes are confined to author resolution and rebuilt derived artifacts. Graph views cover 21,375 papers; the query corpus covers all 22,137 papers, so counts depend on view/filters.

## Evidence and review state

- `identifier_conflict_decisions.json`: all 13 profile decisions and source evidence.
- `repeated_author_decisions.json`: the original 76 paper decisions.
- `remaining_paper_review_decisions.json`: six attempted-but-unresolved paper questions, including partial corrections.
- `followup_duplicate_decision.json`: additional duplicate discovered during rebuilding.
- `source_metadata.json` and `orcid_activities.json`: retrieved source records.
- `remaining/`: fresh audit of the corrected tables.
- `verification.json`: counts, unchanged evidence-file checks and corrected sample lists.
- Author correction registry: `pipeline/kg/author_identity_overrides.json`.

Validation: 58 focused author-resolution, audit, evidence-export, query-export and promotion tests passed. Full local exports, active-pointer and local-bundle checks passed. Browser verification confirmed one Robin search identity and corrected two-author citation text on the He/Ron paper. Details are recorded in `verification.json`. No production deployment is part of this pass.

Local preview: http://127.0.0.1:8011/?data-source=local

Active local run: `author_identity_20260906_reviewed`. Evidence release `author_identity_20260906_reviewed:380a2d4dc6314e219c09196d50914902`; derived artifact revision `author_identity_20260906_reviewed:public:947f000220844993b95ebf242c68b114`. “Public” in this local artifact label does not mean deployed to psychedelicsKG.com.
