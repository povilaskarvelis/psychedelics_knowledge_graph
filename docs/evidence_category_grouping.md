# Shared evidence categories

Explore's detail charts and Analyze's Evidence coverage use the same facet
functions in `ui/app.js`. Chart labels and click filters must both use those
functions; aggregating only the visible legend leaves raw categories in coverage
and can produce different counts on drill-down.

## Grouping decisions

- **Study design:** prefer the curated design category; classify remaining
  descriptions into the existing study families, comparative studies, or method
  development/validation. Unclassified descriptions become “Other study designs”.
  Blinding, controls, and crossover alone do not establish randomization. Titles
  do not establish design. Explicit curated RCT classifications remain authoritative.
- **Population/model:** retain human, animal, cell/tissue, and computational
  groups. Distinguish explicitly mixed populations from unclassified ones.
- **Experimental system:** share clinical, in vivo, in vitro, ex vivo,
  computational, mixed, and unspecified groups. Specific cell preparations belong
  to in vitro; an anatomical location alone does not establish a system.
- **Assay/method:** use the same assay families as Explore. Brain readouts such
  as functional connectivity remain in Explore's brain-measure chart and are not
  added as competing method categories beside fMRI or EEG.
- **Comparator and follow-up:** retain the existing groups. A field marked
  “normalized” still passes through grouping if its value is not canonical.
  Missing metadata, explicit absence of a comparator, and inapplicability remain
  distinct.
- **Outcomes:** retain normalized named instruments (e.g. MADRS and PHQ-9).
  These are distinct measurements, not protocol descriptions to collapse together.
- **Other Explore facets:** administration route, dosing schedule, session context,
  review approach/contribution, public-health context, and open-science indicators
  already use bounded categories. Authors, journals, funders, compounds, and topics
  remain entity identities rather than broad methodological groups.

Raw descriptions remain in the stored extraction. Drill-down still opens the
underlying findings and source papers. Grouping changes display and filtering,
not the stored extraction or the number of papers.

## Corpus review, 2026-09-07

Inspected the active `author_identity_20260906_reviewed` detail payloads:
82,302 primary finding rows, 1,806 meta-analysis rows, and 13,024 review rows.
The primary-row label counts below include the missing-value bucket and precede
scope/date/admission filters; they are not publication counts.

| Facet | Before | After |
| --- | ---: | ---: |
| Study design | 830 | 32 |
| Experimental system | 217 | 7 |
| Population/model | 6 | 7 |
| Comparator | 10 | 10 |
| Follow-up | 12 | 12 |
| Assay family | 26 | 26 |

This audit checks category proliferation and consistency, not the correctness of
every source classification. Unclear values remain explicit rather than being
assigned a more specific design or system without evidence.

Regression checks: `node --test tests/test_evidence_facets.cjs tests/test_research_model.cjs`.
These load the production facet functions and cover category collapse, uncertain
randomization, missingness, mixed systems, and shared Explore/coverage counts and
filters with repeated findings from the same paper.
