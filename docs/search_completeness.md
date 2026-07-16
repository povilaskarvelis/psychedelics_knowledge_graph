# Checking Search Completeness

No literature search can prove that it found every relevant report. The
current expanding-corpus search therefore treats completeness as an operational
retrieval property, not an estimate of recall: every configured query must be
fully paginated and reconciled, but promotion does not depend on a small sample
of known papers.

The repository still contains the historical **known relevant study set** for
provenance, but the living-search pipeline no longer reads it, tests it, uses it
as a promotion gate, or uses it as an implicit citation-search seed cohort.
The pilot was useful while the strategy was being formed; at the current corpus
scale it is neither a recall estimate nor a useful acceptance test.

## Operational completeness gates

The current living-search runner adds retrieval checks that are separate from
known-study coverage. For every query and date partition it records the
provider's total, every retrieved provider ID, pagination state, errors, and
the exact query and search surface. A query is incomplete when counts do not
reconcile, a provider returns an error, or a request budget pauses the run.

V3 separates retrieval completeness from descriptive search diagnostics. A run
can be promoted when every selected execution is mechanically complete. The
initial small known-record pilot has been retired. Provider-ID records without
DOIs remain in an identifier resolution queue and do not disappear during DOI
enrichment. See
[`pipeline/discovery/README.md`](../pipeline/discovery/README.md) for the full
operating procedure.

These gates establish that the configured search was retrieved completely;
they do not prove that the configured concepts and information sources capture
all relevant literature. Source overlap, citation searching, and later strategy
review remain separate activities rather than promotion requirements.

OpenAlex publication-date updates do not identify every older work newly added
to its index. Created-date filtering is a paid-plan feature, so standard
free-plan operations use periodic all-time OpenAlex reruns for that recovery;
the run manifest records whether a created-date stream was included.
