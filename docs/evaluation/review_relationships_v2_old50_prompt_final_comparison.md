# Final prompt on the original 50 reviews

Date: 2026-07-11

## Why this test was needed

The final prompt had previously been tested only on a new set of 50 reviews.
That changed both the prompt and the papers, so the weaker score could not be
attributed to either one. This run applies the final prompt to the original 50
papers and compares it directly with the preceding prompt.

## Controlled comparison

| Same 50 papers | Previous prompt | Final prompt |
|---|---:|---:|
| Good | 40 | 42 |
| Partial | 10 | 8 |
| Poor | 0 | 0 |
| Model calls | 79 | 79 |
| Total tokens | 890,380 | 909,137 |
| Main-graph relationships | 174 | 186 |

The final prompt used 18,757 additional tokens (+2.1%) and improved two papers
from partial to good, with no paper-level regressions.

The two improvements were:

1. The ethnoracial-disparity review now retains both the biological/social
   response pathways and the structural exclusion of BIPOC participants.
2. The translational-agenda paper now retains complex populations,
   psychotherapy standardization, comparator studies, and stakeholder risk as
   parts of one research agenda.

## What this says about the new validation set

The final prompt scored 42 good / 8 partial on the original papers but only
33 good / 17 partial on the 50 new papers. The lower validation score is
therefore largely sample-specific: the new set contains more broad reviews,
hypothesis papers, methodological arguments, and weak-evidence proposals that
expose limitations not well represented in the original sample.

The final prompt is modestly better than the preceding prompt on a controlled
same-paper comparison. It still does not generalize well enough for production
because the unseen sample revealed recurrent failures in evidence strength,
hypothesis wording, and broad-scope completeness.

One additional warning remains: papers with an internal mismatch between their
paper outline and final relationship importance increased from 4 to 14 on the
original sample. These warnings did not generally correspond to worse
paper-level content, but they show that the linked aspect IDs add unreliable
bookkeeping.
