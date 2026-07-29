#!/usr/bin/env python3
"""Build compound-centred research views from the active routed evidence release."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from html import escape
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ORDER = ("primary", "meta_analyses", "reviews")
SOURCE_LABELS = {
    "primary": "Primary studies",
    "meta_analyses": "Meta-analyses",
    "reviews": "Reviews",
}
CATEGORY_DEFINITIONS = (
    {
        "key": "conditions",
        "label": "Conditions & symptoms",
        "kinds": {"condition_indication", "symptom_problem"},
    },
    {
        "key": "safety",
        "label": "Safety & tolerability",
        "kinds": {"safety_adverse_event"},
    },
    {
        "key": "cognition_behavior",
        "label": "Cognition & behavior",
        "kinds": {"cognitive_behavioral_construct"},
    },
    {
        "key": "subjective_effects",
        "label": "Subjective effects",
        "kinds": {"subjective_experience_construct"},
    },
    {
        "key": "treatment_context",
        "label": "Treatment context",
        "kinds": {"intervention_component"},
    },
    {
        "key": "real_world",
        "label": "Real-world evidence",
        "kinds": {"public_health_measure", "exposure_context"},
    },
    {
        "key": "brain",
        "label": "Brain systems & measures",
        "kinds": {"brain_region", "brain_network", "neural_circuit", "brain_measure"},
    },
    {
        "key": "molecular_effects",
        "label": "Molecular effects",
        "kinds": {"pathway_process", "biomarker_readout"},
    },
    {
        "key": "targets",
        "label": "Targets",
        "kinds": {"target", "system_family"},
    },
    {
        "key": "pharmacokinetics",
        "label": "Pharmacokinetics",
        "kinds": {"pharmacokinetic_parameter", "compound"},
        "domains": {"pharmacokinetics_exposure"},
    },
)
CATEGORY_BY_KEY = {item["key"]: item for item in CATEGORY_DEFINITIONS}
FIELD_NAMES = (
    "domain",
    "compound",
    "entity_label",
    "graph_entity_label",
    "graph_parent_label",
    "entity_kind",
    "study_doi",
    "openalex_id",
    "study_title",
    "study_year",
    "study_journal",
    "authors",
    "text_depth",
)


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not slug:
        raise ValueError(f"Cannot create a slug for compound {value!r}")
    return slug


def normalized_doi(value: Any) -> str:
    doi = clean_text(value).casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix) :]
    return doi.strip()


def columnar_value(
    row: list[int],
    values: list[Any],
    field_indices: dict[str, int],
    field: str,
) -> Any:
    index = field_indices.get(field)
    if index is None or index >= len(row):
        return ""
    value_index = int(row[index] or 0)
    if value_index <= 0 or value_index >= len(values):
        return ""
    return values[value_index]


def category_key_for_finding(domain: Any, entity_kind: Any) -> str:
    normalized_domain = clean_text(domain).casefold()
    normalized_kind = clean_text(entity_kind).casefold()
    if normalized_domain == "pharmacokinetics_exposure":
        return "pharmacokinetics"
    for definition in CATEGORY_DEFINITIONS:
        if normalized_kind in definition["kinds"]:
            return str(definition["key"])
    return ""


def paper_identity(source: str, finding: dict[str, Any]) -> tuple[str, str]:
    doi = normalized_doi(finding.get("study_doi"))
    openalex = clean_text(finding.get("openalex_id"))
    title = clean_text(finding.get("study_title"))
    identity = doi or openalex.casefold() or title.casefold()
    if not identity:
        return "", ""
    digest = hashlib.sha1(f"{source}|{identity}".encode("utf-8")).hexdigest()[:16]
    return f"{source}-{digest}", doi


def paper_record(
    source: str,
    finding: dict[str, Any],
    paper_id: str,
    doi: str,
) -> dict[str, Any]:
    openalex = clean_text(finding.get("openalex_id"))
    url = f"https://doi.org/{doi}" if doi else ""
    if not url and openalex:
        openalex_key = openalex.rsplit("/", 1)[-1]
        url = f"https://openalex.org/{openalex_key}"
    year_value = finding.get("study_year")
    try:
        year = int(year_value) if year_value not in ("", None) else None
    except (TypeError, ValueError):
        year = None
    return {
        "id": paper_id,
        "source": source,
        "title": clean_text(finding.get("study_title")) or "Untitled publication",
        "year": year,
        "journal": clean_text(finding.get("study_journal")),
        "authors": clean_text(finding.get("authors")),
        "doi": doi,
        "url": url,
    }


def empty_source_bucket() -> dict[str, Any]:
    return {
        "findings": 0,
        "full_text_findings": 0,
        "paper_ids": set(),
    }


def decode_compound_findings(
    detail_path: Path,
    source: str,
    compound: str,
) -> tuple[list[dict[str, Any]], str]:
    payload = json.loads(detail_path.read_text(encoding="utf-8"))
    fields = payload.get("fields") or []
    values = payload.get("values") or []
    rows = payload.get("rows") or []
    field_indices = {field: fields.index(field) for field in FIELD_NAMES if field in fields}
    compound_key = compound.casefold()
    findings: list[dict[str, Any]] = []

    for row in rows:
        row_compound = clean_text(
            columnar_value(row, values, field_indices, "compound")
        )
        if row_compound.casefold() != compound_key:
            continue
        finding = {
            field: columnar_value(row, values, field_indices, field)
            for field in FIELD_NAMES
        }
        finding["compound"] = row_compound
        findings.append(finding)

    return findings, clean_text(payload.get("generated_at"))


def build_compound_payload(
    compound: str,
    detail_paths: dict[str, Path],
    *,
    release_id: str = "",
    concept_allowlist: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    category_store: dict[str, dict[str, Any]] = {}
    for definition in CATEGORY_DEFINITIONS:
        category_store[str(definition["key"])] = {
            "key": definition["key"],
            "label": definition["label"],
            "sources": {source: empty_source_bucket() for source in SOURCE_ORDER},
            "concepts": {},
        }

    papers: dict[str, dict[str, Any]] = {}
    generated_at = ""
    matched_findings = 0

    for source in SOURCE_ORDER:
        findings, source_generated_at = decode_compound_findings(
            detail_paths[source], source, compound
        )
        generated_at = max(generated_at, source_generated_at)
        matched_findings += len(findings)
        for finding in findings:
            domain = finding.get("domain")
            entity_kind = finding.get("entity_kind")
            category_key = category_key_for_finding(domain, entity_kind)
            if not category_key:
                continue
            entity_label = clean_text(
                finding.get("graph_entity_label") or finding.get("entity_label")
            )
            if category_key == "molecular_effects":
                entity_label = clean_text(
                    finding.get("graph_parent_label") or entity_label
                )
            if not entity_label:
                continue
            allowed_concepts = (concept_allowlist or {}).get(category_key)
            if allowed_concepts is not None and entity_label.casefold() not in allowed_concepts:
                continue
            paper_id, doi = paper_identity(source, finding)
            if not paper_id:
                continue
            if paper_id not in papers:
                papers[paper_id] = paper_record(
                    source, finding, paper_id, doi
                )

            category = category_store[category_key]
            category_source = category["sources"][source]
            category_source["findings"] += 1
            category_source["paper_ids"].add(paper_id)
            if clean_text(finding.get("text_depth")).casefold() == "article_text":
                category_source["full_text_findings"] += 1

            concept_key = entity_label.casefold()
            concept = category["concepts"].setdefault(
                concept_key,
                {
                    "label": entity_label,
                    "label_counts": Counter(),
                    "kind": clean_text(entity_kind),
                    "sources": {
                        source_key: empty_source_bucket()
                        for source_key in SOURCE_ORDER
                    },
                },
            )
            concept["label_counts"][entity_label] += 1
            concept_source = concept["sources"][source]
            concept_source["findings"] += 1
            concept_source["paper_ids"].add(paper_id)
            if clean_text(finding.get("text_depth")).casefold() == "article_text":
                concept_source["full_text_findings"] += 1

    if matched_findings == 0:
        raise ValueError(f"No routed findings found for compound {compound!r}")

    categories: list[dict[str, Any]] = []
    for definition in CATEGORY_DEFINITIONS:
        category = category_store[str(definition["key"])]
        concepts: list[dict[str, Any]] = []
        for concept in category["concepts"].values():
            preferred_label = sorted(
                concept["label_counts"].items(),
                key=lambda item: (-item[1], item[0].casefold()),
            )[0][0]
            source_payload = {}
            for source in SOURCE_ORDER:
                bucket = concept["sources"][source]
                paper_ids = sorted(
                    bucket["paper_ids"],
                    key=lambda paper_id: (
                        -(papers[paper_id].get("year") or 0),
                        papers[paper_id]["title"].casefold(),
                    ),
                )
                source_payload[source] = {
                    "studies": len(paper_ids),
                    "findings": bucket["findings"],
                    "full_text_findings": bucket["full_text_findings"],
                    "paper_ids": paper_ids,
                }
            concepts.append(
                {
                    "label": preferred_label,
                    "kind": concept["kind"],
                    "sources": source_payload,
                }
            )
        concepts.sort(
            key=lambda concept: (
                -sum(
                    concept["sources"][source]["studies"]
                    for source in SOURCE_ORDER
                ),
                -sum(
                    concept["sources"][source]["findings"]
                    for source in SOURCE_ORDER
                ),
                concept["label"].casefold(),
            )
        )

        category_sources = {}
        for source in SOURCE_ORDER:
            bucket = category["sources"][source]
            category_sources[source] = {
                "studies": len(bucket["paper_ids"]),
                "findings": bucket["findings"],
                "full_text_findings": bucket["full_text_findings"],
            }
        categories.append(
            {
                "key": category["key"],
                "label": category["label"],
                "sources": category_sources,
                "concepts": concepts,
            }
        )

    return {
        "schema_version": "compound_research_view_v1",
        "compound": {"label": compound, "slug": slugify(compound)},
        "release": {
            "id": release_id,
            "generated_at": generated_at,
        },
        "source_labels": SOURCE_LABELS,
        "categories": categories,
        "papers": papers,
    }


def count_cell(count: int, source_label: str) -> str:
    display = str(count) if count else "—"
    accessible = f"{count} {source_label.casefold()}"
    return (
        f'<span class="compound-count" aria-label="{escape(accessible)}">'
        f"{escape(display)}</span>"
    )


def render_concept_rows(category: dict[str, Any]) -> str:
    rows = []
    for index, concept in enumerate(category["concepts"]):
        extra = "\n              data-extra-concept hidden" if index >= 12 else ""
        counts = "".join(
            count_cell(
                int(concept["sources"][source]["studies"]),
                SOURCE_LABELS[source],
            )
            for source in SOURCE_ORDER
        )
        rows.append(
            f"""
            <button
              class="compound-concept-row"
              type="button"
              data-category-key="{escape(category['key'])}"
              data-concept-index="{index}"
              aria-label="View literature for {escape(concept['label'])}"{extra}
            >
              <span class="compound-concept-name">{escape(concept['label'])}</span>
              {counts}
            </button>"""
        )
    remaining = max(0, len(category["concepts"]) - 12)
    show_more = ""
    if remaining:
        show_more = (
            f'<button class="compound-show-more" type="button" '
            f'data-show-more="{escape(category["key"])}">Show {remaining} more</button>'
        )
    return "".join(rows) + show_more


def render_category_rows(payload: dict[str, Any]) -> str:
    rows = []
    for index, category in enumerate(payload["categories"]):
        is_open = index == 0
        counts = "".join(
            count_cell(
                int(category["sources"][source]["studies"]),
                SOURCE_LABELS[source],
            )
            for source in SOURCE_ORDER
        )
        rows.append(
            f"""
          <div class="compound-area{" is-open" if is_open else ""}" data-area="{escape(category['key'])}">
            <button
              class="compound-area-row"
              type="button"
              data-area-toggle="{escape(category['key'])}"
              aria-expanded="{"true" if is_open else "false"}"
              aria-controls="compound-area-{escape(category['key'])}"
            >
              <span class="compound-area-name">{escape(category['label'])}</span>
              {counts}
            </button>
            <div
              class="compound-area-detail"
              id="compound-area-{escape(category['key'])}"
              {"hidden" if not is_open else ""}
            >
              {render_concept_rows(category)}
            </div>
          </div>"""
        )
    return "".join(rows)


def render_compound_page(payload: dict[str, Any]) -> str:
    compound = payload["compound"]["label"]
    slug = payload["compound"]["slug"]
    title = f"{compound} research map | Psychedelics Knowledge Graph"
    description = (
        f"Explore research connected to {compound} across conditions, safety, "
        "cognition, subjective effects, treatment context, brain systems, "
        "molecular effects, targets, real-world evidence, and pharmacokinetics."
    )
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="description" content="{escape(description)}" />
    <title>{escape(title)}</title>
    <link rel="canonical" href="https://psychedelicskg.com/compounds/{escape(slug)}/" />
    <link rel="icon" href="/favicon.ico" sizes="32x32" />
    <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
    <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="Psychedelics Knowledge Graph" />
    <meta property="og:title" content="{escape(title)}" />
    <meta property="og:description" content="{escape(description)}" />
    <meta property="og:url" content="https://psychedelicskg.com/compounds/{escape(slug)}/" />
    <meta name="twitter:card" content="summary" />
    <meta name="twitter:title" content="{escape(title)}" />
    <meta name="twitter:description" content="{escape(description)}" />
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-8M798XF54S"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag() {{ window.dataLayer.push(arguments); }}
      gtag("js", new Date());
      gtag("config", "G-8M798XF54S");
    </script>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap"
      rel="stylesheet"
    />
    <link rel="stylesheet" href="/ui/styles.css?v=20260728-compound-charts-v3" />
  </head>
  <body class="methods-page compound-page" data-compound-data="/compounds/{escape(slug)}/data.json">
    <div class="bg" aria-hidden="true"></div>
    <header class="site-header" data-site-header>
      <div class="site-header-inner">
        <button
          class="site-nav-toggle"
          type="button"
          aria-expanded="false"
          aria-controls="siteNav"
          data-site-nav-toggle
        >
          <span class="site-nav-toggle-icon" aria-hidden="true"></span>
          <span>Menu</span>
        </button>
        <nav class="site-nav" id="siteNav" aria-label="Primary" data-site-nav>
          <a class="site-nav-link site-nav-back" href="/"><span aria-hidden="true">←</span> Back to graph</a>
          <a class="site-nav-link" href="/about/">About</a>
          <a class="site-nav-link" href="/methods/">Methods</a>
          <a class="site-nav-link" href="/api/">API</a>
          <a class="site-nav-link" href="/feedback/?source=compound-{escape(slug)}">Leave feedback</a>
        </nav>
      </div>
    </header>

    <header class="compound-intro">
      <h1>{escape(compound)}</h1>
      <p>
        Research connected to {escape(compound)} across clinical, safety,
        experiential, behavioral, brain, molecular, real-world, and
        pharmacokinetic evidence.
      </p>
    </header>

    <main class="compound-content">
      <div class="compound-workspace">
        <section class="compound-matrix" aria-labelledby="compoundAreasHeading">
          <div class="compound-section-heading">
            <div class="compound-heading-copy">
              <h2 id="compoundAreasHeading">Research map</h2>
              <p id="compoundAreasDescription">Select an area or concept to trace its connected literature.</p>
            </div>
            <div class="compound-explorer-controls">
              <div class="segmented-toggle compound-view-toggle" role="tablist" aria-label="Compound view">
                <button class="ghost small active" type="button" data-compound-view="map" role="tab" aria-selected="true">Map</button>
                <button class="ghost small" type="button" data-compound-view="charts" role="tab" aria-selected="false">Charts</button>
                <button class="ghost small" type="button" data-compound-view="table" role="tab" aria-selected="false">Table</button>
              </div>
              <div class="segmented-toggle compound-graph-source-toggle" role="tablist" aria-label="Research literature source">
                <button class="ghost small active" type="button" data-compound-graph-source="primary" role="tab" aria-selected="true">Primary studies</button>
                <button class="ghost small" type="button" data-compound-graph-source="meta_analyses" role="tab" aria-selected="false">Meta-analyses</button>
                <button class="ghost small" type="button" data-compound-graph-source="reviews" role="tab" aria-selected="false">Reviews</button>
              </div>
            </div>
          </div>
          <div class="compound-graph-view">
            <div class="compound-graph-shell">
              <div
                class="compound-graph"
                id="compoundGraph"
                aria-label="{escape(compound)} research connections"
              ></div>
              <div class="compound-graph-tooltip" id="compoundGraphTooltip" role="tooltip" hidden></div>
            </div>
            <p class="compound-graph-note">
              Line weight represents the number of unique source papers. Color identifies
              the research area; labels and position carry the same distinction without color.
            </p>
          </div>
          <div class="compound-chart-view">
            <div class="compound-chart-grid">
              <section class="compound-chart-section compound-coverage-section" aria-labelledby="compoundCoverageHeading">
                <div class="compound-chart-heading">
                  <h3 id="compoundCoverageHeading">Research coverage</h3>
                  <p>Unique source papers connected to each research area.</p>
                </div>
                <div id="compoundCoverageChart" class="compound-coverage-chart"></div>
              </section>
              <div class="compound-chart-detail-column">
                <section class="compound-chart-section compound-timeline-section" aria-labelledby="compoundTimelineHeading">
                  <div class="compound-chart-heading">
                    <h3 id="compoundTimelineHeading">Publication history</h3>
                    <p id="compoundTimelineContext">Select an area to examine its publication trajectory.</p>
                  </div>
                  <div class="compound-chart-svg-shell">
                    <div id="compoundTimelineChart" class="compound-timeline-chart"></div>
                  </div>
                </section>
                <section class="compound-chart-section compound-entity-section" aria-labelledby="compoundEntityHeading">
                  <div class="compound-chart-heading">
                    <h3 id="compoundEntityHeading">Entity coverage</h3>
                    <p id="compoundEntityContext">Entities ranked by unique source papers in the selected research area.</p>
                  </div>
                  <div id="compoundEntityChart" class="compound-entity-chart"></div>
                </section>
              </div>
              <section class="compound-chart-section compound-overlap-section" aria-labelledby="compoundOverlapHeading">
                <div class="compound-chart-heading">
                  <h3 id="compoundOverlapHeading">Cross-domain overlap</h3>
                  <p>The diagonal shows area totals; the lower triangle shows shared papers. Select a cell to inspect its literature.</p>
                </div>
                <div class="compound-chart-svg-shell compound-overlap-shell">
                  <div id="compoundOverlapChart" class="compound-overlap-chart"></div>
                </div>
              </section>
            </div>
            <div class="compound-chart-tooltip" id="compoundChartTooltip" role="tooltip" hidden></div>
            <p class="compound-chart-note">
              Values are unique source papers in the current release. Research areas overlap,
              and publication volume does not indicate efficacy or evidence quality.
            </p>
          </div>
          <div class="compound-table-view">
            <div class="compound-table-header" aria-hidden="true">
              <span>Area or concept</span>
              <span>Primary studies</span>
              <span>Meta-analyses</span>
              <span>Reviews</span>
            </div>
            <div class="compound-area-list">
              {render_category_rows(payload)}
            </div>
            <p class="compound-count-note">
              Counts are unique source papers connected to the compound and concept
              in this release. They describe coverage, not efficacy or evidence quality.
            </p>
          </div>
        </section>

        <aside class="compound-literature" aria-labelledby="compoundLiteratureHeading">
          <div class="compound-literature-heading">
            <h2 id="compoundLiteratureHeading">Literature</h2>
            <p id="compoundLiteratureContext">
              Select a concept to see the publications connected to it.
            </p>
          </div>
          <ol class="compound-paper-list" id="compoundPaperList"></ol>
          <button class="compound-paper-more" id="compoundPaperMore" type="button" hidden>Show more</button>
        </aside>
      </div>
    </main>

    <footer class="footer">
      <div class="footer-inner">
        <nav class="footer-links" aria-label="Project information">
          <a href="https://github.com/povilaskarvelis/psychedelics_knowledge_graph" target="_blank" rel="noopener noreferrer">GitHub</a>
          <a href="https://github.com/povilaskarvelis/psychedelics_knowledge_graph/blob/main/CITATION.cff" target="_blank" rel="noopener noreferrer">Cite this project</a>
          <a href="https://github.com/povilaskarvelis/psychedelics_knowledge_graph/blob/main/LICENSES.md" target="_blank" rel="noopener noreferrer">Licenses</a>
        </nav>
        <div class="footer-identity">
          <span>
            Created and maintained by
            <a href="https://povilaskarvelis.github.io/" target="_blank" rel="noopener noreferrer">Povilas Karvelis</a>
          </span>
        </div>
      </div>
    </footer>
    <script src="/ui/site-nav.js?v=20260717-site-nav"></script>
    <script src="/ui/compound.js?v=20260728-compound-charts-v3"></script>
  </body>
</html>
"""


def active_payload_paths(
    active_pointer: Path,
) -> tuple[dict[str, Path], dict[str, Path], str]:
    pointer = json.loads(active_pointer.read_text(encoding="utf-8"))
    path_groups = {}
    for pointer_key, label in (
        ("active_detail_bootstraps", "detail"),
        ("active_graph_bootstraps", "graph"),
    ):
        mapping = pointer.get(pointer_key) or {}
        missing = [source for source in SOURCE_ORDER if not mapping.get(source)]
        if missing:
            raise ValueError(
                f"Active pointer lacks {label} bootstraps for: {', '.join(missing)}"
            )
        path_groups[label] = {
            source: (ROOT / clean_text(mapping[source])).resolve()
            for source in SOURCE_ORDER
        }
    for path in [*path_groups["detail"].values(), *path_groups["graph"].values()]:
        if not path.is_file():
            raise FileNotFoundError(path)
    return (
        path_groups["detail"],
        path_groups["graph"],
        clean_text(pointer.get("public_release_id") or pointer.get("release_id")),
    )


def graph_concept_allowlist(
    compound: str,
    graph_paths: dict[str, Path],
) -> dict[str, set[str]]:
    allowed = {
        str(definition["key"]): set()
        for definition in CATEGORY_DEFINITIONS
        if definition["key"] != "pharmacokinetics"
    }
    compound_key = compound.casefold()
    for source in SOURCE_ORDER:
        payload = json.loads(graph_paths[source].read_text(encoding="utf-8"))
        for edge in payload.get("edges") or []:
            if clean_text(edge.get("compound")).casefold() != compound_key:
                continue
            category_key = category_key_for_finding(
                edge.get("domain"), edge.get("entity_kind")
            )
            entity_label = clean_text(edge.get("entity_label"))
            if category_key in allowed and entity_label:
                allowed[category_key].add(entity_label.casefold())
    return allowed


def write_compound_page(
    payload: dict[str, Any],
    output_root: Path,
) -> Path:
    slug = payload["compound"]["slug"]
    output_dir = output_root / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(
        render_compound_page(payload), encoding="utf-8"
    )
    (output_dir / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--active-pointer",
        type=Path,
        default=ROOT / "data/processed/graph_payload_active.json",
    )
    parser.add_argument(
        "--compound",
        action="append",
        dest="compounds",
        help="Compound label to build; may be supplied more than once.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "compounds",
    )
    args = parser.parse_args()
    compounds = args.compounds or ["Psilocybin"]
    detail_paths, graph_paths, release_id = active_payload_paths(
        args.active_pointer.resolve()
    )

    for compound in compounds:
        clean_compound = clean_text(compound)
        payload = build_compound_payload(
            clean_compound,
            detail_paths,
            release_id=release_id,
            concept_allowlist=graph_concept_allowlist(clean_compound, graph_paths),
        )
        output_dir = write_compound_page(payload, args.output_root.resolve())
        print(
            f"Built {payload['compound']['label']} compound view in {output_dir}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
