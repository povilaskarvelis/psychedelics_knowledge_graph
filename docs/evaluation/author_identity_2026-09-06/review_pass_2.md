# Author identity review pass 2 — 2026-09-06

Reviewed by Codex using publication metadata, institutional profiles, and direct
ORCID public records. No external classification model or human-review claim.

## Results

The staged author layer corrects **134 authorship identities relative to the
active graph**, including the seven Carhart-Harris corrections from pass 1.
This pass therefore adds **127 corrections**. These are paper-author links,
not counts of papers or people. All 116,802 authorship rows, original names,
paper associations, and author positions are preserved.

| Researcher | Separate baseline identities | Corrected identities | Distinct papers |
| --- | ---: | ---: | ---: |
| Robin Carhart-Harris | 8 | 1 | 230 |
| Matthias E. Liechti | 8 | 1 | 181 |
| Joshua D. Rosenblat | 10 | 1 | 121 |
| Leor Roseman | 6 | 1 | 78 |
| David Nutt | 5 | 1 | 136 |

All **13 different-name same-paper identity collisions** detected in pass 1
are resolved. These included Lucas Quarantini/Ana Paula Jesus-Nunes,
Sophie Geyrhofer/Joanne Harvey, Robert Keyzers/Susan Schenk,
Bruce Greyson/Vanessa Charland-Verville, Sarah Eller/Tiago Franco de Oliveira,
Roger McIntyre/Angela Kwan, Zhenglu Wang/Xiqing Li, Zihang Pan/Roger McIntyre,
Friederike Holze/Felix Müller, Rachel Sousa-Ho/Venkat Bhat,
Pablo Del Pozo-Herce/Elena Chover-Sierra, and Nisha/Arun Ravindran.
McIntyre/Kwan collided on two papers. Related erroneous profile propagation
was corrected on additional papers as well.

The graph had propagated an ORCID assigned to one person onto another. Some
wrong associations are present in publisher/Crossref metadata, so a refresh
would reproduce them. Institutional and direct ORCID records supplied the
independent identity evidence. For example, [Joanne Harvey's institutional
profile](https://people.wgtn.ac.nz/joanne.harvey) and [Robert Keyzers's
profile](https://people.wgtn.ac.nz/robert.keyzers) establish their identifiers.

The first retrieval left Sophie Geyrhofer's ORCID disputed because a publisher
page attached it to Jan Vorster. The [direct ORCID owner
record](https://pub.orcid.org/v3.0/0000-0002-7764-4053/person) identifies Sophie;
her valid existing link was retained and the other paper corrected to it.

David Nutt required a larger correction: **54 of the 79 papers** assigned to
OpenAlex profile A5101507504 appear in his [Imperial-linked ORCID public works
record](https://pub.orcid.org/v3.0/0000-0002-1286-1401/activities). Combined with
the profile's consistent full name and collaborator context, that supports
correcting the corpus profile association for all 79 papers. The other 25 are
identified explicitly in the decision record as profile-level inference.
This is not a declaration that the two ORCID accounts are globally equivalent.

## Provenance and implementation

The existing registry now supports both reviewed profile merges and corrections
to a specific DOI/author position. **98 scoped review records** address source
identity errors; the remaining changes use reviewed profile/name mappings and
exact-name fallback resolution. A review record can validate a row whose final
identity was already correct, so review-record count differs from change count.

Each scoped record includes expected source name/identifiers, replacement
identifiers, sources, reason, reviewer and review date. The tables retain
`source_author_id`, `source_orcid`, `source_openalex_author_id`, and
`identity_review_id`. The source cache remains unchanged. Builds fail if an
expected source record changes, decisions overlap, or identity propagation
reintroduces a rejected ORCID. Unreviewed name similarity never triggers these
new corrections.

- [Decisions and sources](review_pass_2_decisions.json)
- [Every changed paper-author identity](pass2_identity_changes.csv)
- [Verification totals](pass2_verification.json)
- [Remaining candidate queue](pass2_remaining/name_candidates.json)
- [Remaining audit summary](pass2_remaining/summary.json)

Seventeen focused tests pass, including source preservation, stale-source
rejection, conflicting review decisions, and prevention of rejected-ORCID
reintroduction. Four existing author-export tests also pass. Full-corpus comparison verified the intended identity changes
and unchanged paper links, author order, and original names.

## What remains

This is a completed priority review pass, not completion of the entire audit.
The remaining scan contains **2,417 candidate name groups** (not proven errors),
including **835 groups with multiple ORCIDs**, plus **13 OpenAlex profiles with
conflicting ORCIDs** across 122 authorships. Those profiles have not been
adjudicated in this pass. Also, 245 repeated author rows on 76 papers remain;
they now have identical source names within each repeated identity group and
need checking against author lists before any deduplication.

Zihang Pan and Pablo Del Pozo-Herce are separated from the wrong people using
their OpenAlex identities, without inventing replacement ORCIDs. Such absence
of a verified ORCID does not make the correction an unresolved cross-person
merge. Additional splits among Roger McIntyre's newer profiles also remain.

The corrected author tables are under
`data/processed/release_staging/author_identity_20260906_pass2`.
**The active local graph and psychedelicsKG.com are unchanged.** Graph payloads
must be rebuilt and checked with this author layer before local promotion or
production publication. The audit remains a standalone command, not an
automatic release gate.
