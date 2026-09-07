# Author identity audit — 2026-09-06

**Follow-up completed:** see [review pass 2](review_pass_2.md) for the current
results. The sections below preserve the initial audit and its then-unresolved
cases. All 13 different-name same-paper identity collisions listed by that audit
have now been corrected in staging; the rest of the broader queue is not fully
reviewed.

Scope: author identities and ordered authorship links in the locally active
`research_area_routing_20260906_release_candidate` KG. This is a corpus-wide
candidate scan plus a source review of the Carhart-Harris group, not a completed
review of all candidates. No external classification model was called.

## Findings

- 64,880 author identities across 116,802 authorship rows.
- 2,424 candidate name groups containing 5,841 identities. These are review
  candidates, not confirmed duplicates or counts of affected papers.
- 837 of those groups contain multiple ORCIDs. This can mean different people,
  duplicate ORCID registrations, or erroneous metadata; do not merge on name.
- 13 OpenAlex profiles have conflicting ORCIDs across 122 authorship rows.
  The existing builder keeps those profiles out of ORCID consolidation.
- 271 rows repeat an author ID within a paper, affecting 88 papers. These include
  possible duplicate metadata and possible false merges of different people.
- No duplicate author positions or orphan authorship links were found.

Candidate examples include Matthias Liechti (8 identities), Joshua Rosenblat
(10), David Nutt (5, with two ORCIDs), and Leor Roseman (6). These groups have not
yet had source-level adjudication. Shared collaborators only prioritize review;
they do not establish identity.

Possible false merges needing source-level adjudication include:

| DOI | Names sharing one identity in our tables | ORCID |
| --- | --- | --- |
| 10.1002/hup.2836 | Ana Paula Jesus-Nunes; Lucas C. Quarantini | 0000-0002-0389-1940 |
| 10.1007/s11306-023-02034-6 | Sophie Geyrhofer; Joanne E. Harvey | 0000-0001-5687-2586 |
| 10.1007/s11306-023-02034-6 | Robert A. Keyzers; Susan Schenk | 0000-0002-7786-8313 |

These were detected by inspecting the local ordered authorship rows, not
resolved by verifying which author owns each ORCID. They remain uncorrected.
The builder can currently propagate an erroneous shared ORCID across profiles;
this is a separate problem from missing middle initials.

## Reviewed correction: Robin Carhart-Harris

Decision: merge the following seven one-paper identities into
`orcid:0000-0002-6062-7150`, preferred name `Robin Carhart-Harris`.
The existing identity has 223 distinct papers; the reviewed union has 230.
Reviewer: Codex, source-based review, 2026-09-06. This is not a human review label.

His [Imperial profile](https://profiles.imperial.ac.uk/r.carhart-harris) identifies
the ORCID. Publication records below tie the variant names, paper authorship,
and institutional research context to that identity. The conclusion combines
those records with local authorship and collaborator evidence; name similarity
alone was not the basis for merging.

| Additional identity | DOI | Supporting publication record |
| --- | --- | --- |
| openalex:A5138024465 | 10.1093/nc/niaf069 | [Imperial](https://www.imperial.ac.uk/psychedelic-research-centre/research/publications/?id=1666554&noscript=noscript&respub-t4-action=citation.html) |
| openalex:A5121018397 | 10.1177/28314425251392251 | [Imperial](https://www.imperial.ac.uk/psychedelic-research-centre/research/publications/?id=1641851&noscript=noscript&respub-t4-action=citation.html) |
| openalex:A5120966307 | 10.1177/28314425251382930 | [Publisher author list](https://journals.sagepub.com/doi/abs/10.1177/28314425251382930) |
| openalex:A5140218191 | 10.1192/bjp.2026.10687 | [Oxford archive](https://ora.ox.ac.uk/objects/uuid%3A717e5a94-b3b5-43f8-8d2f-28e8e4d5444a) |
| openalex:A5137807234 | 10.3389/fphar.2026.1840956 | [Imperial](https://www.imperial.ac.uk/psychedelic-research-centre/research/publications/?id=1669457&noscript=noscript&respub-t4-action=citation.html), [publisher](https://doi.org/10.3389/fphar.2026.1840956) |
| openalex:A5139833133 | 10.1002/hbm.70596 | [Oxford archive](https://ora.ox.ac.uk/objects/uuid%3A76fdc725-4229-4622-8878-18c4d88a45ed) |
| local_author:68f24c41ea20b520 | 10.1080/09515089.2026.2657452 | [Imperial](https://www.imperial.ac.uk/psychedelic-research-centre/research/publications/?id=1660856&noscript=noscript&respub-t4-action=citation.html) |

The reviewed registry now includes six additional OpenAlex profile IDs and the
exact local fallback alias. Source display names remain intact. Authorships
resolved through reviewed OpenAlex mappings now carry
`curated_openalex_to_orcid`; local aliases carry `curated_name_to_orcid`.
Observed ORCID conflicts still raise an error rather than silently overriding
source evidence. No global middle-initial removal rule was introduced.

## Deliverables and remaining work

`summary.json`, `name_candidates.json`, and the CSV queues are the baseline scan.
`possible_false_merges.csv` narrows repeated IDs to entries with different source
names; spelling variants still need review. Candidate generation handles middle
names, accents and Unicode dashes for review purposes. It does not exhaustively
cover initials-only names, surname reordering, or merged IDs across papers.

The corrected author tables are built separately under
`data/processed/release_staging/author_identity_20260906`. They have not replaced
the active local graph or been deployed to psychedelicsKG.com. This preserves
the previously validated routing release while author changes are evaluated.

Next review priorities: suspected cross-person merges, conflicting identifiers,
then high-paper-count split groups. Record each decision and its source evidence
in the registry; leave uncertain cases in the queue. Re-run the audit on every
author build so new upstream profile splits are visible. The audit is currently
a standalone command, not yet wired into the release gate.

## Follow-up

The subsequent targeted review and local rebuild are documented in [pass 3](pass3/review.md). Earlier counts above describe the earlier audit state.
