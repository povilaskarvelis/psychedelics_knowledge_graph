# Author identity review, 8 Nov 2026

Build examined: `data/processed/kg_routed_runs/text_provenance_20261108`
(70,697 author identities, 127,876 authorships: 37,054 ORCID identities,
30,405 OpenAlex-only identities, 3,238 name-only identities).

## Summary

Author identities are split far more often than the audit summary suggests.
Frederick S. Barrett has 9 identities: one ORCID identity (41 authorships) and
8 OpenAlex-only identities with one or two authorships each. The same pattern
affects most of the field's most-published authors.

| Measure | Value |
|---|---|
| Exact-name groups with more than one identity | 2,304 groups, 5,580 identities, 15,255 authorships |
| of which: one ORCID identity plus others | 1,081 groups, 2,434 identities, 9,409 authorships |
| of which: two or more ORCIDs | 797 groups (mostly common names of different people; some are one person with two ORCIDs) |
| of which: no ORCID | 426 groups |
| 200 most-published names that are split | 85 |

Examples: David B. Yaden 9 identities, Johannes G. Ramaekers 8, Hannes Kettner 6,
Albert Garcia-Romeu 7, Matthias E. Liechti 5, David E. Nichols 8,
Franz X. Vollenweider 4, Matthew W. Johnson 5, Roland R. Griffiths 3.

The exact-name count is a lower bound: name variants ("D.J. Nutt",
"ME Liechti", "Jan Ramaekers", "K.C. Rice") are not in it.

## Cause 1: stale OpenAlex author IDs (largest effect)

The OpenAlex works cache was fetched mostly in June–July 2026 (22,505 of
28,464 works). OpenAlex first assigns a new work's authors to new single-work
profiles and merges them into the established profile later. The build uses the
author IDs as they were at fetch time and never re-resolves them.

All 8 Barrett IDs now redirect in the live OpenAlex API to A5005540871
(ORCID 0000-0001-7443-3237).

Live check of 2,037 OpenAlex-only IDs that share an exact name with another
identity, plus a random 1,500 other OpenAlex-only IDs (60 returned 404):

| Set | Checked | Now redirect | Redirect onto an identity already in the graph |
|---|---|---|---|
| Shared-name IDs | 2,037 | 921 (45%) | 797 (625 onto ORCID identities) + 28 via the redirected profile's ORCID |
| Other IDs | 1,500 | 105 (7%) | 27 |

For the shared-name groups, re-resolution reduces 3,472 identities to 2,678, and
522 of 1,414 groups become a single identity. Extrapolated to the remaining
~28,400 OpenAlex-only IDs, roughly 2,000 further IDs redirect, mostly to profiles
not otherwise in the graph.

This is provider evidence, not name matching, so it is consistent with the rule
that names alone never merge identities.

**Fix:** add a step to `pipeline/kg/build_author_tables.py` that resolves every
OpenAlex author ID through `GET /authors/{id}` (merged IDs redirect to the
surviving profile), caches the mapping with its query date, and applies it
before ORCID canonicalisation. About 31,000 requests; at the client's 3 req/s
this is ~3 h, cached thereafter.

## Cause 2: separate profiles that OpenAlex has not merged

Re-resolution does not fix:

- Older variant-name profiles: "D.J. Nutt" (A5113636502, 35 works, no ORCID),
  "Jan G. Ramaekers" (A5104355183, 23 works), "ME Liechti", "F.X. Vollenweider",
  "K.C. Rice", "R. A. GLENNON".
- One person with two ORCIDs: David B. Yaden (0000-0002-9604-6227 and
  0000-0002-5561-4515), Matthew W. Johnson (0000-0001-7068-0513 and
  0000-0002-6391-2088), David E. Nichols (0000-0002-1129-1697 and
  0000-0002-8025-9295, 264 OpenAlex works on the second).

Non-ORCID identities that share surname and first initial with exactly one ORCID
identity but have a different name string: 3,151 identities, 4,407 authorships.
This is an upper bound and includes different people (e.g. "Shiny Mathew" vs
Sanjay J. Mathew, "Bernhard Roth" vs Bryan L. Roth).

The override file has 25 profile-alias reviews and 4 ORCID-alias reviews. The
audit lists 2,883 candidate name groups; none have been reviewed since the build
was run without a baseline (`baseline_dir` empty, so all "new_*" counts are 0).

**Fix:** after re-resolution, generate a ranked review queue (by authorship
count, with shared coauthors and shared topics as evidence) and record decisions
as `profile_alias_reviews` / `orcid_alias_reviews`. Prioritising identities with
10+ authorships covers the visible cases with a small number of decisions.

## Cause 3: wrong ORCID on individual authorships

Some authorships carry another person's ORCID, so different people share one
identity:

| ORCID | Identity name | Wrong authorship |
|---|---|---|
| 0000-0003-0151-2270 | Richard Chambers | Jake Payne, 10.1002/brb3.71043 |
| 0000-0002-4021-8907 | Hans-Jürgen Möller | Changsu Han, 10.3390/ph17091143 |
| 0000-0001-8503-7387 | Dana Strauss | Jordan Sloshower, 10.1556/2054.2024.00429 |
| 0000-0002-2682-3780 | Wei Yan | Lijia Chang, 10.1016/j.brainresbull.2021.10.013 |
| 0000-0002-4729-7601 | Ellen M. Leslie | Ellen L. Wessel, 10.1111/dar.13196 |

184 authorship rows share no name token with their identity's name; most are
transliterations or abbreviations, a small number are errors like those above.
The audit's `possible_false_merges.csv` is empty, so the current check does not
detect them.

**Fix:** a name-consistency check for ORCID-assigned authorships (surname not
matching any name on the ORCID identity, after transliteration) that queues rows
for `authorship_overrides`.

## Cause 4: display names

The display name is the most frequent name string, ties broken alphabetically
(`build_authors_from_authorships`). Problems:

| Problem | Identities | Examples |
|---|---|---|
| Abbreviated form chosen over full name | — | A. Roig, P. Baldinger, A. Ali, I. Romero |
| Non-Latin script chosen | 146 | Αλεξάνδρα Κορδά, Белозерцева Ирина Владимировна |
| Greek letters inside Latin names | — | Νikolaos S. Τhomaidis, Klaas Ε. Stephan |
| Unicode hyphen U+2010 | 2,415 | Albert Garcia‐Romeu (site search normalises this) |
| Dotless ı + combining accent, not NFC | 79 | Magı́ Farré, Jordi Camı́, Jiřı́ Horáček |
| Encoding errors | 39 | J�rgen A. Engel, Torbj�rn U. C. J�rbe |
| All capitals | 315 | D. E. NICHOLS, BRIAN J. MORRIS |
| Titles and degrees | 19 | Prof. Dr. Matthias E. Liechti, Maurizio Fava M. D |
| Missing space | 15 | DavidE. Nichols, AmyJ. Stringer |
| Trailing stray letters | — | Jordi Riba A, Arpana Agrawal A |
| "Surname, Given" | 65 | Peacock, Amy; Ryan, Mark |
| Not a person | ~35 | on behalf of the Euro-DEN Research Group; 7450 Summit Cir, Davison, MI 48423; id_orcid 0000-0001-8558-3396 Juruena |

**Fix:** NFC normalisation, hyphen and homoglyph repair, removal of titles and
stray suffixes; choose the longest Latin-script full name among the identity's
names (ORCID record name where available); move group and consortium authors
out of the person table.

## Other structural findings (already in the audit)

- 86 authorship rows on 20 profiles with conflicting ORCIDs.
- 78 repeated-author rows on 13 papers; 5 same-paper same-name groups.
- 3,238 name-only identities (3,512 authorships) from papers OpenAlex did not
  match.

## Suggested order

1. OpenAlex author-ID re-resolution (Cause 1).
2. Display-name normalisation and non-person removal (Cause 4).
3. ORCID name-consistency check (Cause 3).
4. Ranked review queue for remaining variant profiles and duplicate ORCIDs
   (Cause 2), decided by review.
5. Run the author audit with the current release as baseline so new-split gates
   are effective.

## Implemented, 9 Nov 2026

Built into `pipeline/kg/build_author_tables.py` (new module
`pipeline/kg/author_identity_evidence.py`), so every build applies it:

1. **OpenAlex profile merges.** Every cached OpenAlex author ID is looked up
   with the free single-record endpoint; merged IDs return the surviving
   profile. A merge is followed only when the byline can name the surviving
   profile's researcher, and the surviving profile's current ORCID replaces
   stale cached ORCIDs under the same condition.
2. **ORCID public records.** Removes an ORCID from a byline that matches none
   of the record's names, when the surname differs (and the DOI is not on the
   record) or the record owner is a coauthor on the same paper. Assigns an
   authorship to an ORCID identity when exactly one same-surname ORCID record
   lists the DOI and the names match.
3. **Same-paper guard.** Any evidence change that puts one identity on two
   positions of a paper with disagreeing bylines is reverted.
4. **Display names and non-person bylines** (cleaning only; source strings
   kept).
5. **Audit:** ranked `split_identity_review_queue.csv`,
   `identity_name_mismatches.csv`, split counts against the baseline; the
   routed build uses the active release as baseline when none is given.

Crossref was considered and not used (unverified ORCIDs; source of the errors).

Cost: OpenAlex single-record lookups and ORCID public records are free. The
first run queried 67,660 OpenAlex profiles (~56 min at 20 req/s with the
configured key) and 18,205 ORCID records (~25 min). Later builds query only new
records and records older than 60 days (about a minute with a warm cache).

### Result on `text_provenance_20261108` (tables written to a scratch directory)

| Measure | Before | After |
|---|---|---|
| Author identities | 70,697 | 68,979 |
| Name groups with one ORCID identity plus others | 1,452 | 833 |
| Authorships outside the person's ORCID identity in those groups | 2,391 | 1,215 |
| Authorship rows withheld for conflicting ORCIDs | 86 | 4 |
| Authorships whose byline cannot name their identity | 31 | 4 |
| Structured authorship coverage | 97.19% | 97.40% |

Evidence applied: 3,471 merged OpenAlex profiles (82 merges rejected because
the byline did not match the surviving profile), 315 authorships assigned by
ORCID records, 10 wrong ORCIDs removed (Jake Payne, Changsu Han /
Hans-Jürgen Möller, Yoshihiro Noda, Lijia Chang, Jan Vorster, Agnieszka Bysiek,
two coauthors carrying Tânia Gaspar's ORCID), 1 same-paper merge reverted
(E.N / E.O Andrade), 34 group and address bylines separated, 6,343 byline
display forms cleaned. The audit's structural gates pass against the 8 Nov build.

Examples: Frederick S. Barrett 9 → 1 identity (51 authorships); Albert
Garcia-Romeu 7 → 1; Hannes Kettner 6 → 1; Matthias E. Liechti 5 → 1;
David B. Yaden 9 → 2 (second ORCID); Johannes G. Ramaekers 8 → 3.

### Not resolved automatically

- People with two ORCIDs (Yaden, M. W. Johnson, D. E. Nichols) and older
  variant profiles OpenAlex has not merged ("Jan G. Ramaekers", "D.J. Nutt",
  "Kenner C. Rice" 12 authorships) — ranked in the review queue.
- Added 9 Nov after review: an OpenAlex profile without an ORCID joins the
  single ORCID identity with the same full name (written-out given name) when
  they never share a paper and share at least 2 coauthors (3 for two-word
  names). On `text_provenance_20261108` this joins 129 profiles (237
  authorships); 35 two-word names with only 2 shared coauthors stay in the
  review queue. Check of all 129 against OpenAlex affiliations: 90 share an
  institution; the other 39 were checked by their papers and coauthor teams
  (same topic and research group in every case). No wrong join was found.
  Profiles whose bylines are initials ("K C Rice") are not joined.
