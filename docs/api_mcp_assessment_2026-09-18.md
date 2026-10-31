# API and MCP assessment — 18 September 2026

The existing architecture is a good foundation: REST and MCP share one query service, the exporter uses an explicit field allowlist, and relationships are deduplicated and restricted to `main_graph`. The most valuable next step is to make the public contract more reliable and easier to interpret, then expand a small number of useful operations. Broad access to extracted findings or arbitrary graph queries would be premature.

This was an assessment only. No application code, data release, deployment, or configuration was changed. The review includes current uncommitted work in the workspace; it does not assume that work is deployed.

## Verified state

| Item | Live service/site | Active local catalogue |
| --- | --- | --- |
| Run | `living_update_20260917_author_identity_reviewed` | `living_update_20260917_author_identity_reviewed` |
| API artifact generated | 18 September 2026 | 17 September 2026 |
| Papers/reports | 22,516 | 22,516 |
| Relationships | 66,147 | 66,147 |
| Concepts | 8,281 | 8,281 |
| Author identities | 64,158 | 64,158 |

The live browser pointer and API now return the **same September release ID**: `living_update_20260917_author_identity_reviewed:public:335768f912d24f0092f40a196452713a`. The data release is current. The API behavior fixes assessed here remain a separate application deployment concern and should be verified through OpenAPI and live request checks after the service is redeployed.

REST metadata, facets, and OpenAPI responded successfully. Remote MCP initialization, tool discovery, and a `search_concepts` call also succeeded. MCP negotiated protocol `2025-11-25` and advertised nine tools. There is no evidence here that a protocol or framework upgrade is needed to restore basic functionality.

Live sources: [API metadata](https://psychedelics-kg-api.onrender.com/api/v1/meta), [browser release pointer](https://data.psychedelicskg.com/browser/active.json), [OpenAPI](https://psychedelics-kg-api.onrender.com/openapi.json), [public API guide](https://psychedelicskg.com/api/). These are moving endpoints; the table records this assessment's observations.

## Priorities

| Priority | Recommendation | Reason |
| --- | --- | --- |
| 1 | Define a conservative default relationship scope and explicit eligibility policy | `main_graph` is not equivalent to the polished overview or to completed semantic review. |
| 1 | Reject unsupported filters and clarify multi-concept queries | Currently a plausible request can silently become an unfiltered search. |
| 1 | Release the approved September data, with live parity verification | Production lacks recent routing and author-identity corrections. |
| 2 | Improve relationship interpretation and response contracts | Agents need to distinguish research coverage from scientific conclusions. |
| 2 | Add website-view queries and scoped descriptive summaries | These offer useful new functionality without exposing raw findings. |
| 2 | Bind pagination to query identity and improve MCP ergonomics | Prevent accidental omissions and make tools easier to use correctly. |
| 3 | Add validated study-context/provenance filters | Useful, but current underlying fields need explicit missing/mixed-value handling. |
| 3 | Improve operational visibility and reproducible dependency builds | Reduce stale releases and deployment surprises. |

## 1. Make the quality boundary explicit

The exporter checks `graph_admission_status == "main_graph"`, then projects and deduplicates the edges. It does not independently evaluate unresolved semantic review or reproduce the website overview transformation. See [export_query_api.py](../pipeline/publish/export_query_api.py).

Three different concepts currently need to be distinguished:

- **Graph admission:** a finding/edge passed the existing admission rules.
- **Website presentation:** views apply category restrictions, subject projections, parent grouping, and report-count thresholds.
- **Public API eligibility:** whether the resulting statement can safely be used without the detail and qualifications shown in an evidence card.

In the September catalogue, **9,001 of 66,147 relationships match none of the ten category presets**. These include 4,295 symptom relationships, 2,954 pharmacokinetic-parameter relationships, 865 brain-measure relationships, 565 compound-object relationships, 278 cognitive/behavioral relationships outside the preset label lists, and 44 public-health relationships outside that preset's domain restriction. This measures preset coverage, not error rate. These relationships may be useful; they should not automatically become the default answer to an agent expecting the site's curated categories.

Within categories, the overview also groups detailed molecular/intervention concepts under parents. The API retains the detailed concepts. Thus simply applying `graph_views.filters` does not reproduce the displayed overview. See [graph_view_contract.json](../schema/graph_view_contract.json) and `overview_graph_projections` / `overview_graph_projection` in [export_evidence_payload.py](../pipeline/publish/export_evidence_payload.py).

The current local data also contains:

- 60 `main_graph` findings with research-area status `pending` and no adjudication status, contributing 52 distinct public relationship keys.
- 385 `main_graph` findings marked `needs_human_review`, all from meta-analysis types, contributing 221 distinct public relationship keys.

These are **review signals, not confirmed errors or automatic exclusion counts**. Some relationship keys may also have acceptable support from other findings. In addition, 1,865 other `pending` main-graph findings already have confirmed/corrected adjudication outcomes: blindly excluding every `pending` row would wrongly discard reviewed material.

**Recommendation:** define a versioned eligibility policy that resolves final adjudication before legacy flags, separates unresolved relationship meaning from review of omitted statistical detail, and evaluates eligibility before relationship deduplication. Keep internal review notes private. Publish only a concise scope label and aggregate coverage/limitation information.

Offer a first-class website-view scope as the recommended agent entry point. Retain broader catalogue queries as an explicitly documented scope if they remain useful; avoid silently changing existing v1 behavior. Add parity tests against the actual published view/projection rules. A website category is a useful baseline, not proof that every field displayed in its evidence cards is ready for a stable API.

## 2. Prevent plausible queries from returning the wrong scope

The REST request models use Pydantic's default handling of extra fields. Unsupported fields are ignored. I reproduced this against production:

```json
{
  "filters": {
    "graph_view": "condition_indication",
    "subject_ids": ["compound:psilocybin"]
  },
  "limit": 1
}
```

The paper endpoint returned HTTP 200 with **22,137 total papers**, the complete live catalogue. Neither filter was applied. `subject_ids` exists for relationship queries but not paper queries; the paper model's label-field descriptions nevertheless advise preferring subject/object IDs.

There is also an easy semantic trap: `concept_ids` means **any listed concept at either endpoint**, not “all these concepts together.” Locally, psilocybin alone matched 1,917 papers, major depressive disorder alone matched 840, and putting both IDs in the list matched 2,575 papers. That is correct OR behavior, but likely to surprise someone asking for psilocybin-and-depression research.

**Recommendation:**

- Reject unknown fields at both request-envelope and nested-filter levels; return actionable validation errors.
- Validate controlled vocabularies and report unknown IDs instead of making invalid values indistinguishable from a valid search with no matches.
- Add `subject_ids` and `object_ids` to paper search, applying both to the same relationship; this gives a clear way to retrieve compound–outcome pairs.
- Document OR within lists, AND across filter fields, and same-relationship matching. If adding “all concepts,” distinguish co-occurrence anywhere in a paper from a direct relationship between the requested concepts.
- Echo normalized filters and effective scope in response metadata.

Evidence: [models.py](../services/query_api/models.py), `paper_where` and `relationship_where` in [repository.py](../services/query_api/repository.py).

## 3. Complete the release lifecycle

Publish the approved September candidate after resolving the eligibility decisions above. The existing shared release ID, checksums, private runtime bucket, and release-aware cursors are worth preserving.

The service syncs R2 once on startup. Updating the remote pointer does not itself refresh an already-running process. The deployment guide documents a deploy hook or manual restart, but the shorter agent-access guide leaves that operational dependency less obvious. Publication also switches browser and API pointers sequentially, not as one cross-service transaction.

**Recommendation:** make successful publication require a post-publication check that the browser pointer, REST `/meta`, and MCP `get_release_info` all expose the intended release. Make restart/hook status explicit. A bounded background refresh could be added later, preserving the last verified release on failure. Report source coverage date separately from artifact build time so a rebuilt catalogue is not mistaken for newly updated literature.

Evidence: [app.py](../services/query_api/app.py), [refresh_public_release.sh](../scripts/refresh_public_release.sh), [R2 deployment](r2_deployment.md).

## 4. Strengthen interpretation and documentation

The current exclusions are sensible, but removing result direction, study context, and qualifications does not make a predicate self-explanatory. Names such as `reports_safety_signal` and `has_cognitive_behavioral_effect` can be over-read as established harm or a demonstrated effect.

Add brief interpretation rules to MCP instructions, the agent guide, and schema metadata:

- A relationship is a literature-retrieval link, not proof of benefit, harm, causation, or effectiveness.
- Paper/report counts are not independent-study counts; reviews and meta-analyses must remain separate from primary research.
- Missing relationships do not establish absence of evidence.
- Unknown or absent metadata must remain unknown, not be interpreted as a negative finding.

Specific documentation fixes:

- Replace the claim that category presets reproduce website views with a precise distinction between category membership and overview projection/grouping.
- Explain catalogue-only records: locally, 2,988 papers have no public relationship and 781 have no broad paper classification. Do not promise every returned record is classified or contributes graph evidence.
- Clarify author coverage. The September manifest reports 97.84% structured authorship coverage; returned `authors` arrays can be incomplete. Add per-paper completeness/count metadata rather than implying a complete citation author list.
- Emphasize `observed_kinds`, `observed_domains`, and contextual relationship kinds. I found 217 concepts whose legacy singular kind differs from at least one object role. Existing observed-role support is good; do not replace it with the legacy field.
- Fix the relationship table's declared grain: its metadata omits `domain`, although deduplication and IDs include it.
- Reconcile [evidence_policy.md](evidence_policy.md) with implementation: it describes two-report relationship support for primary studies and reviews, while the graph bootstrap uses node-support thresholds and allows one-report review/meta-analysis nodes. Agree the intended rule before rewriting the policy.
- Document truncated paper relationships, how to continue through relationship search, error/retry behavior, and which text fields search actually covers. Paper text search does not search abstracts or evidence quotations.

## 5. Useful additions, in order

| Addition | Value | Admission condition |
| --- | --- | --- |
| `view_id` plus an explicit category/overview scope | Agents can request Conditions, Safety, Targets, etc. without reconstructing predicates | Use one shared view/projection contract; test against published browser data. |
| Scoped counts and facets | Papers by year, paper type, compound, or topic without downloading every page | Count distinct reports, disclose denominator and scope, separate primary/review/meta-analysis. |
| A compact topic summary with supporting paper links | Useful entry point for “what literature is represented here?” | Descriptive counts and citations only; no automated effectiveness ranking or evidence-strength claim. |
| MCP `get_author` | Completes an operation REST already supports | Reuse existing service and identity rules. |
| Provenance and coverage summaries | Distinguish abstract-only/full-text extraction and missing coverage | Retain mixed/unknown states and derive summaries from the eligible supporting findings. |
| Broad population/model and study-design filters | Separates human, animal, cell-model, and design contexts | Audit and version mappings first; filter at the same supporting-finding scope as the requested relationship. |

The last addition is attractive but should not be a direct export of arbitrary extraction strings. Among local main-graph findings, 40,035 have no controlled population/model category and 30,347 have no controlled study-design category. The UI supplements these with contextual fallbacks. Those counts do not prove the browser lacks usable labels, but they show that copying the raw category columns would not reproduce the UI. Validate the shared mapping and preserve mixed populations/designs rather than assigning one convenient paper-level label.

Defer granular finding search, effect-size/statistical queries, quote search, dosage comparisons, confidence rankings, unrestricted SQL/Cypher, and bulk downloads. Each needs a separate reviewed contract; none is necessary for the improvements above.

## 6. Improve machine contracts and MCP usability

REST success responses and MCP output schemas currently describe generic objects (`additionalProperties: true`). `/schema` documents stored tables, but does not fully define nested query responses, pagination, truncation, computed concept roles, and errors.

Add typed response models shared by REST and MCP, including structured errors and response metadata. Expose limits and field descriptions in MCP input schemas, add explicit read-only/idempotent tool annotations, and describe recovery from unavailable data or release changes. Retain the existing release/schema MCP resources.

Cursors contain only release ID and offset. Locally, a cursor from an unfiltered paper search was accepted for a psilocybin-filtered search and skipped the first matching record. Bind cursors to normalized filters, endpoint, scope, and ordering as well as release. Document restarting pagination after a release change.

The nine current tools are enough for core retrieval. Prefer a few well-defined additions over many overlapping tools with long, subtly different argument lists.

## 7. Operational improvements

The configured service is a free preview instance and the agent guide documents wake-up delays. Consider an always-on instance if reliable agent access becomes important; assess this with actual latency and failure observations rather than assuming a paid tier is necessary.

Add lightweight monitoring for readiness, intended-versus-served release, query latency, and failed synchronizations. Preserve the distinction between process health and data readiness. Rate limits are delegated to the hosting layer in the documentation; this review did not verify hosting-account configuration.

Dependency ranges permit substantially different builds over time. Pin or lock a tested deployment set and update it deliberately. The focused tests passed against a fresh environment but emitted two dependency deprecation warnings. That supports reproducible builds and planned maintenance, not an urgent framework migration.

## Validation and limits

Read-only inspection covered the service, MCP wrapper, export contract, view/projection code, active local database, manifests, current review indicators, documentation, and live public endpoints. The local database was opened read-only for catalogue inspection; internal Parquet tables were queried without modification.

Executed:

```text
pytest -q tests/test_query_api.py tests/test_export_query_api.py
          tests/test_query_api_r2_sync.py tests/test_build_query_api_bundle.py
          tests/test_publish_query_api_r2.py
19 passed; 2 dependency deprecation warnings
```

Additional checks reproduced live unsupported-filter behavior, verified remote MCP operation, measured local preset coverage and review indicators, and demonstrated OR filtering and cross-query cursor reuse. Existing tests passing does not cover these missing behavioral guarantees.

This was not a paper-by-paper scientific validation, an exhaustive security audit, a load test, or an inspection of private hosting settings. Relationship counts associated with review flags identify material to evaluate; they are not counts of false claims.

Recommended first implementation package: strict query validation, endpoint-specific paper filters, a documented conservative scope/eligibility policy, clarified interpretation guidance, and a checked release of the approved September data. Follow with website-view operations and descriptive summaries. Richer study-context filters can then be added after their mappings pass parity and missingness checks.
