#!/usr/bin/env python3
"""Discover literature from web APIs and generate DOI queues for KG ingest.

Default provider is Semantic Scholar because it is better for relevance ranking.
OpenAlex is available for metadata-heavy search, and hybrid merges both.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DISORDER_CANON_PATH = ROOT / "schema" / "disorder_canonicalization.json"

DEFAULT_SEEDS = {
    "mechanistic": [
        "LSD 5-HT2A receptor binding affinity Ki radioligand|LSD|5-HT2A",
        "LSD 5-HT2C receptor binding affinity|LSD|5-HT2C",
        "psilocin 5-HT2A receptor binding affinity|Psilocin|5-HT2A",
        "psilocin 5-HT1A receptor binding affinity|Psilocin|5-HT1A",
        "psilocybin psilocin 5-HT2A agonist receptor|Psilocybin|5-HT2A",
        "DMT 5-HT2A receptor binding affinity|DMT|5-HT2A",
        "DMT sigma-1 receptor binding affinity|DMT|Sigma-1 receptor (SIGMAR1)",
        "psychedelic TAAR1 trace amine receptor 1 binding|DMT|TAAR1",
        "5-MeO-DMT 5-HT1A receptor binding affinity|5-MeO-DMT|5-HT1A",
        "mescaline 5-HT2A receptor binding affinity|Mescaline|5-HT2A",
        "MDMA SERT DAT NET transporter affinity|MDMA|SERT (SLC6A4)",
        "MDMA dopamine transporter DAT affinity|MDMA|DAT (SLC6A3)",
        "MDMA norepinephrine transporter NET affinity|MDMA|NET (SLC6A2)",
        "ibogaine noribogaine kappa opioid receptor binding|Ibogaine|kappa opioid receptor (OPRK1)",
        "ibogaine NMDA receptor binding affinity|Ibogaine|NMDA receptor",
        "ketamine NMDA receptor affinity binding Ki|Ketamine|NMDA receptor",
        "esketamine NMDA receptor affinity binding|S-ketamine|NMDA receptor",
        "arketamine NMDA receptor affinity binding|R-ketamine|NMDA receptor",
        "salvinorin A kappa opioid receptor affinity|Salvinorin A|kappa opioid receptor (OPRK1)",
        "2C-B 5-HT2A receptor binding affinity|2C-B|5-HT2A",
        "DOI 5-HT2A receptor binding affinity|DOI|5-HT2A",
        "psychedelic mGluR2 GRM2 receptor interaction|LSD|mGluR2 (GRM2)",
    ],
    "disorder": [
        "psilocybin treatment-resistant depression randomized trial|Psilocybin|Treatment-resistant depression",
        "psilocybin major depressive disorder randomized trial|Psilocybin|Major depressive disorder",
        "ayahuasca major depressive disorder trial|Ayahuasca|Major depressive disorder",
        "ketamine treatment-resistant depression trial|Ketamine|Treatment-resistant depression",
        "esketamine treatment-resistant depression phase 3|S-ketamine|Treatment-resistant depression",
        "ketamine suicidal ideation randomized trial|Ketamine|Suicidal ideation",
        "MDMA post-traumatic stress disorder randomized trial|MDMA|Post-traumatic stress disorder",
        "LSD anxiety life-threatening disease trial|LSD|distress associated with life-threatening disease",
        "psilocybin cancer anxiety depression trial|Psilocybin|distress associated with life-threatening disease",
        "psilocybin generalized anxiety disorder trial|Psilocybin|Generalized anxiety disorder",
        "MDMA autism spectrum disorder social anxiety trial|MDMA|Autism spectrum disorder",
        "psilocybin obsessive-compulsive disorder trial|Psilocybin|Obsessive-compulsive disorder",
        "psilocybin anorexia nervosa trial|Psilocybin|Anorexia nervosa",
        "psilocybin eating disorders trial|Psilocybin|Eating disorders",
        "psilocybin alcohol use disorder randomized trial|Psilocybin|Alcohol use disorder",
        "psilocybin tobacco use disorder trial|Psilocybin|Tobacco use disorder",
        "ibogaine opioid use disorder trial|Ibogaine|Opioid use disorder",
        "ketamine alcohol use disorder trial|Ketamine|Alcohol use disorder",
        "psilocybin cocaine use disorder trial|Psilocybin|Cocaine use disorder",
        "psilocybin methamphetamine use disorder trial|Psilocybin|Methamphetamine use disorder",
        "psilocybin substance use disorder trial|Psilocybin|Substance use disorder",
        "psilocybin end-of-life anxiety trial|Psilocybin|distress associated with life-threatening disease",
        "LSD cluster headache trial|LSD|Cluster headache",
        "ketamine chronic pain trial|Ketamine|Chronic pain",
    ],
}

AUTO_SEED_TEMPLATES = {
    "mechanistic": {
        "focused": [
            "{compound} {entity} receptor binding affinity Ki",
        ],
        "broad": [
            "{compound} {entity} receptor binding affinity Ki",
            "{compound} {entity} radioligand binding affinity",
            "{compound} {entity} pharmacology assay affinity",
        ],
    },
    "disorder": {
        "focused": [
            "{compound} {entity} randomized clinical trial",
        ],
        "broad": [
            "{compound} {entity} randomized clinical trial",
            "{compound} {entity} phase 2 phase 3 trial",
            "{compound} {entity} therapeutic outcome study",
        ],
    },
}

@dataclass
class Seed:
    query: str
    compound: str
    entity: str


class RateLimitedHttpClient:
    def __init__(self, rps: float, max_retries: int, timeout_sec: int = 30, user_agent: str = "kg-pipeline/0.1"):
        self.rps = max(0.01, rps)
        self.min_interval = 1.0 / self.rps
        self.max_retries = max_retries
        self.timeout_sec = timeout_sec
        self.user_agent = user_agent
        self._last_request_ts = 0.0

    def _wait_for_slot(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_ts
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def get_json(self, url: str, params: Optional[Dict[str, object]] = None, headers: Optional[Dict[str, str]] = None) -> dict:
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True)
        full_url = f"{url}?{query}" if query else url
        request_headers = {"User-Agent": self.user_agent}
        if headers:
            request_headers.update(headers)

        backoff = 2.5
        for attempt in range(self.max_retries + 1):
            self._wait_for_slot()
            try:
                req = Request(full_url, headers=request_headers)
                with urlopen(req, timeout=self.timeout_sec) as response:
                    self._last_request_ts = time.monotonic()
                    body = response.read().decode("utf-8")
                    return json.loads(body)
            except HTTPError as err:
                self._last_request_ts = time.monotonic()
                retryable = err.code in {429, 500, 502, 503, 504}
                if attempt >= self.max_retries or not retryable:
                    raise
                retry_after = err.headers.get("Retry-After") if err.headers else None
                if retry_after and retry_after.isdigit():
                    delay = max(backoff, float(retry_after))
                else:
                    delay = backoff
                time.sleep(delay + random.uniform(0.0, 0.35))
                backoff *= 1.7
            except URLError:
                self._last_request_ts = time.monotonic()
                if attempt >= self.max_retries:
                    raise
                time.sleep(backoff + random.uniform(0.0, 0.35))
                backoff *= 1.7

        raise RuntimeError("Unreachable retry state")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_text(raw: str) -> str:
    lowered = normalize(raw).lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def normalize_doi(raw: str) -> str:
    doi = normalize(raw)
    if not doi:
        return ""
    prefix = "https://doi.org/"
    if doi.lower().startswith(prefix):
        return doi[len(prefix) :]
    return doi


def parse_simple_yaml(path: Path) -> dict:
    if not path.exists():
        return {}

    out: Dict[str, dict] = {}
    current = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and stripped.endswith(":"):
            current = stripped[:-1]
            out[current] = {}
            continue
        if current and line.startswith("  ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            value = value.strip().strip('"').strip("'")
            parsed: object = value
            if value == "":
                parsed = ""
            else:
                try:
                    parsed = float(value) if "." in value else int(value)
                except ValueError:
                    parsed = value
            out[current][key.strip()] = parsed
    return out


def parse_allowlists(path: Path) -> Dict[str, List[str]]:
    if not path.exists():
        return {}

    keys = {"allowed_compounds", "allowed_targets", "allowed_disorders"}
    allowlists = {key: [] for key in keys}
    current_key = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.endswith(":"):
            key = line[:-1]
            current_key = key if key in keys else None
            continue

        if current_key and line.startswith("- "):
            value = line[2:].strip().strip('"').strip("'")
            if value:
                allowlists[current_key].append(value)
            continue

        current_key = None

    return allowlists


def dedupe_values(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in values:
        value = normalize(raw)
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def query_safe_label(label: str) -> str:
    raw = normalize(label)
    if not raw:
        return ""

    match = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", raw)
    if match:
        base = normalize(match.group(1))
        inside = normalize(match.group(2))
        if base and inside:
            return f"{base} {inside}"
        return base or inside

    return raw


def clean_query_text(text: str) -> str:
    tokens = [token for token in normalize(text).split() if token]
    out: List[str] = []
    for token in tokens:
        if out and token.lower() == out[-1].lower():
            continue
        out.append(token)
    return " ".join(out)


def load_disorder_alias_map(path: Path = DISORDER_CANON_PATH) -> Dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {}

    alias_map: Dict[str, str] = {}
    for canonical, aliases in data.items():
        canonical_label = normalize(canonical)
        if not canonical_label:
            continue
        alias_map[normalize_text(canonical_label)] = canonical_label
        if not isinstance(aliases, list):
            continue
        for raw in aliases:
            alias = normalize(raw)
            if not alias:
                continue
            alias_map[normalize_text(alias)] = canonical_label
    return alias_map


DISORDER_ALIAS_MAP = load_disorder_alias_map()


def canonicalize_disorder_label(raw: str) -> str:
    text = normalize(raw)
    if not text:
        return ""
    normalized = normalize_text(text)
    return DISORDER_ALIAS_MAP.get(normalized, text)


def dedupe_seeds(seeds: List["Seed"]) -> List["Seed"]:
    out: List[Seed] = []
    seen = set()
    for seed in seeds:
        key = (
            normalize(seed.query).lower(),
            normalize(seed.compound).lower(),
            normalize(seed.entity).lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(seed)
    return out


def parse_manual_seeds(seed_values: List[str], query_values: List[str]) -> List["Seed"]:
    seeds: List[Seed] = []
    for value in seed_values:
        seeds.append(parse_seed(value))

    for query in query_values:
        q = normalize(query)
        if q:
            seeds.append(Seed(query=q, compound="", entity=""))

    return dedupe_seeds(seeds)


def generate_auto_seeds(
    dataset: str,
    allowlists: Dict[str, List[str]],
    template_mode: str,
    max_compounds: int,
    max_entities: int,
    max_pairs: int,
    max_seeds: int,
) -> List["Seed"]:
    compounds = dedupe_values(allowlists.get("allowed_compounds", []))
    entity_key = "allowed_targets" if dataset == "mechanistic" else "allowed_disorders"
    entities = dedupe_values(allowlists.get(entity_key, []))
    if dataset == "disorder":
        entities = dedupe_values([canonicalize_disorder_label(value) for value in entities])
    templates = AUTO_SEED_TEMPLATES[dataset][template_mode]

    if max_compounds > 0:
        compounds = compounds[:max_compounds]
    if max_entities > 0:
        entities = entities[:max_entities]

    out: List[Seed] = []
    pair_count = 0
    stop = False
    for compound in compounds:
        if stop:
            break
        for entity in entities:
            if max_pairs > 0 and pair_count >= max_pairs:
                stop = True
                break
            pair_count += 1

            entity_query = query_safe_label(entity)
            for template in templates:
                query = clean_query_text(template.format(compound=compound, entity=entity_query))
                if not query:
                    continue
                out.append(Seed(query=query, compound=compound, entity=entity))
                if max_seeds > 0 and len(out) >= max_seeds:
                    stop = True
                    break
            if stop:
                break

    return dedupe_seeds(out)


def parse_seed(text: str) -> Seed:
    parts = [p.strip() for p in text.split("|", 2)]
    if len(parts) != 3:
        raise ValueError(f"Invalid --seed format: `{text}` expected `query|compound|entity`")
    if not parts[0]:
        raise ValueError(f"Invalid --seed format: `{text}` query cannot be empty")
    return Seed(query=parts[0], compound=parts[1], entity=parts[2])


def build_seed_list(
    dataset: str,
    seed_values: List[str],
    query_values: List[str],
    allowlists: Dict[str, List[str]],
    expand_from_config: bool,
    auto_seeds_only: bool,
    auto_template_mode: str,
    auto_max_compounds: int,
    auto_max_entities: int,
    auto_max_pairs: int,
    auto_max_seeds: int,
) -> tuple[List[Seed], Dict[str, int]]:
    manual = parse_manual_seeds(seed_values=seed_values, query_values=query_values)
    default = [parse_seed(value) for value in DEFAULT_SEEDS[dataset]]
    auto = (
        generate_auto_seeds(
            dataset=dataset,
            allowlists=allowlists,
            template_mode=auto_template_mode,
            max_compounds=max(0, auto_max_compounds),
            max_entities=max(0, auto_max_entities),
            max_pairs=max(0, auto_max_pairs),
            max_seeds=max(0, auto_max_seeds),
        )
        if expand_from_config or auto_seeds_only
        else []
    )

    seeds: List[Seed] = []
    if manual:
        seeds.extend(manual)
    elif not auto_seeds_only:
        seeds.extend(default)
    if expand_from_config or auto_seeds_only:
        seeds.extend(auto)

    merged = dedupe_seeds(seeds)
    return merged, {
        "manual": len(manual),
        "default": 0 if manual or auto_seeds_only else len(default),
        "auto": len(auto),
        "final": len(merged),
    }


def authors_from_s2(authors: Iterable[dict], max_names: int = 10) -> str:
    names = []
    for author in authors:
        name = normalize(author.get("name", ""))
        if name:
            names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def authors_from_openalex(authorships: Iterable[dict], max_names: int = 10) -> str:
    names = []
    for authorship in authorships:
        author_obj = authorship.get("author") if isinstance(authorship, dict) else None
        if isinstance(author_obj, dict):
            name = normalize(author_obj.get("display_name", ""))
            if name:
                names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def search_semantic_scholar(
    client: RateLimitedHttpClient,
    api_key: str,
    seed: Seed,
    max_results: int,
    require_doi: bool,
) -> List[dict]:
    endpoint = "https://api.semanticscholar.org/graph/v1/paper/search"
    headers = {"x-api-key": api_key} if api_key else {}

    rows: List[dict] = []
    offset = 0
    while len(rows) < max_results:
        page_size = min(100, max_results - len(rows))
        params = {
            "query": seed.query,
            "limit": page_size,
            "offset": offset,
            "fields": "title,year,externalIds,authors,url",
        }
        payload = client.get_json(endpoint, params=params, headers=headers)
        items = payload.get("data", []) or []
        if not items:
            break

        for item in items:
            external_ids = item.get("externalIds", {}) if isinstance(item, dict) else {}
            doi = normalize_doi(external_ids.get("DOI", ""))
            if require_doi and not doi:
                continue

            row = {
                "doi": doi,
                "openalex_id": "",
                "title": normalize(item.get("title", "")),
                "year": item.get("year", ""),
                "authors": authors_from_s2(item.get("authors", []) or []),
                "compound": seed.compound,
                "entity": seed.entity,
                "query": seed.query,
                "provider": "semantic_scholar",
            }
            rows.append(row)
            if len(rows) >= max_results:
                break

        offset += len(items)
        total = payload.get("total")
        if isinstance(total, int) and offset >= total:
            break

    return rows


def search_openalex(
    client: RateLimitedHttpClient,
    email: str,
    seed: Seed,
    max_results: int,
    require_doi: bool,
) -> List[dict]:
    endpoint = "https://api.openalex.org/works"

    rows: List[dict] = []
    page = 1
    per_page = min(100, max_results)

    while len(rows) < max_results:
        params = {
            "search": seed.query,
            "per-page": per_page,
            "page": page,
            "select": "doi,display_name,publication_year,authorships,ids",
        }
        if email:
            params["mailto"] = email

        payload = client.get_json(endpoint, params=params, headers={})
        items = payload.get("results", []) or []
        if not items:
            break

        for item in items:
            doi = normalize_doi(item.get("doi", ""))
            if require_doi and not doi:
                continue

            ids = item.get("ids", {}) if isinstance(item, dict) else {}
            openalex_id = normalize(ids.get("openalex", ""))
            row = {
                "doi": doi,
                "openalex_id": openalex_id,
                "title": normalize(item.get("display_name", "")),
                "year": item.get("publication_year", ""),
                "authors": authors_from_openalex(item.get("authorships", []) or []),
                "compound": seed.compound,
                "entity": seed.entity,
                "query": seed.query,
                "provider": "openalex",
            }
            rows.append(row)
            if len(rows) >= max_results:
                break

        if len(items) < per_page:
            break
        page += 1

    return rows


def merge_rows(rows: List[dict]) -> List[dict]:
    merged: Dict[str, dict] = {}
    for row in rows:
        doi_key = normalize(row.get("doi", "")).lower()
        title_key = normalize(row.get("title", "")).lower()
        year_key = normalize(row.get("year", ""))
        key = f"doi:{doi_key}" if doi_key else f"title:{title_key}|year:{year_key}"

        existing = merged.get(key)
        if not existing:
            merged[key] = {
                **row,
                "providers": [row.get("provider", "")],
                "queries": [row.get("query", "")],
            }
            continue

        if not normalize(existing.get("authors", "")) and normalize(row.get("authors", "")):
            existing["authors"] = row.get("authors", "")
        if not normalize(existing.get("doi", "")) and normalize(row.get("doi", "")):
            existing["doi"] = row.get("doi", "")
        if not normalize(existing.get("openalex_id", "")) and normalize(row.get("openalex_id", "")):
            existing["openalex_id"] = row.get("openalex_id", "")
        if not normalize(existing.get("title", "")) and normalize(row.get("title", "")):
            existing["title"] = row.get("title", "")
        if not normalize(existing.get("year", "")) and normalize(row.get("year", "")):
            existing["year"] = row.get("year", "")
        if row.get("provider") and row.get("provider") not in existing["providers"]:
            existing["providers"].append(row.get("provider"))
        if row.get("query") and row.get("query") not in existing["queries"]:
            existing["queries"].append(row.get("query"))

    items = list(merged.values())
    items.sort(key=lambda r: (-(int(r.get("year") or 0)), normalize(r.get("title", ""))))
    return items


def write_queue(path: Path, rows: List[dict], dataset: str) -> None:
    entity_name = "target" if dataset == "mechanistic" else "disorder"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# discovered queue ({dataset}) generated at {now_utc()}\n")
        handle.write(f"# doi,compound,{entity_name},optional_study_title,optional_study_year,optional_authors\n")
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow(
                [
                    normalize(row.get("doi", "")),
                    normalize(row.get("compound", "")),
                    normalize(row.get("entity", "")),
                    normalize(row.get("title", "")),
                    normalize(row.get("year", "")),
                    normalize(row.get("authors", "")),
                ]
            )


def read_float(maybe_value: object, default: float) -> float:
    if maybe_value is None:
        return default
    try:
        return float(maybe_value)
    except Exception:
        return default


def read_int(maybe_value: object, default: int) -> int:
    if maybe_value is None:
        return default
    try:
        return int(maybe_value)
    except Exception:
        return default


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover literature and generate DOI queue")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument(
        "--provider",
        choices=["semantic_scholar", "openalex", "hybrid"],
        default="semantic_scholar",
        help="Search backend; default semantic scholar due to relevance quality",
    )
    parser.add_argument("--seed", action="append", default=[], help="Seed as query|compound|entity")
    parser.add_argument("--query", action="append", default=[], help="Query only (compound/entity left blank)")
    parser.add_argument(
        "--expand-seeds-from-config",
        action="store_true",
        help="Generate extra seeds from allowlists in --config (high-recall mode)",
    )
    parser.add_argument(
        "--auto-seeds-only",
        action="store_true",
        help="Use only auto-generated seeds from allowlists (skip defaults unless manual --seed/--query provided)",
    )
    parser.add_argument(
        "--auto-template-mode",
        choices=["focused", "broad"],
        default="focused",
        help="Template breadth for auto-generated seeds (default: focused)",
    )
    parser.add_argument(
        "--auto-max-compounds",
        type=int,
        default=0,
        help="Max compounds used for auto seed generation (0 = all)",
    )
    parser.add_argument(
        "--auto-max-entities",
        type=int,
        default=0,
        help="Max targets/disorders used for auto seed generation (0 = all)",
    )
    parser.add_argument(
        "--auto-max-pairs",
        type=int,
        default=400,
        help="Max compound-entity pairs used for auto seeds (0 = all, default: 400)",
    )
    parser.add_argument(
        "--auto-max-seeds",
        type=int,
        default=1200,
        help="Max auto-generated seeds after templates (0 = all, default: 1200)",
    )
    parser.add_argument("--max-results-per-seed", type=int, default=20)
    parser.add_argument("--max-results", type=int, default=120)
    parser.add_argument("--require-doi", action="store_true", default=True)
    parser.add_argument("--allow-missing-doi", action="store_true")
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument("--semantic-scholar-api-key", default="")
    parser.add_argument("--semantic-scholar-rps", type=float, default=None)
    parser.add_argument("--openalex-email", default="")
    parser.add_argument("--openalex-rps", type=float, default=None)
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument("--queue-out", default="")
    parser.add_argument("--report-out", default="")
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print progress updates while processing seeds",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = parse_simple_yaml(config_path)
    s2_cfg = config.get("semantic_scholar", {}) if isinstance(config.get("semantic_scholar", {}), dict) else {}
    oa_cfg = config.get("openalex", {}) if isinstance(config.get("openalex", {}), dict) else {}

    s2_api_key = args.semantic_scholar_api_key or str(s2_cfg.get("api_key", ""))
    oa_email = args.openalex_email or str(oa_cfg.get("email", ""))

    # Conservative defaults because Semantic Scholar has stricter limits.
    s2_rps = args.semantic_scholar_rps if args.semantic_scholar_rps is not None else read_float(s2_cfg.get("rate_limit_per_sec"), 0.33)
    oa_rps = args.openalex_rps if args.openalex_rps is not None else read_float(oa_cfg.get("rate_limit_per_sec"), 2.0)
    max_retries = args.max_retries if args.max_retries is not None else read_int(s2_cfg.get("max_retries"), 4)

    allowlists = parse_allowlists(config_path)
    seeds, seed_source_counts = build_seed_list(
        dataset=args.dataset,
        seed_values=args.seed,
        query_values=args.query,
        allowlists=allowlists,
        expand_from_config=args.expand_seeds_from_config,
        auto_seeds_only=args.auto_seeds_only,
        auto_template_mode=args.auto_template_mode,
        auto_max_compounds=args.auto_max_compounds,
        auto_max_entities=args.auto_max_entities,
        auto_max_pairs=args.auto_max_pairs,
        auto_max_seeds=args.auto_max_seeds,
    )
    if not seeds:
        raise SystemExit("No seeds found. Add --seed/--query or enable --expand-seeds-from-config.")
    require_doi = args.require_doi and not args.allow_missing_doi

    queue_out = (
        Path(args.queue_out).resolve()
        if args.queue_out
        else ROOT / "data" / "raw" / f"doi_queue.{args.dataset}.discovered.txt"
    )
    report_out = (
        Path(args.report_out).resolve()
        if args.report_out
        else ROOT / "data" / "processed" / f"discovery_report_{args.dataset}.json"
    )

    s2_client = RateLimitedHttpClient(rps=s2_rps, max_retries=max_retries, user_agent="kg-pipeline/semantic-scholar")
    oa_client = RateLimitedHttpClient(rps=oa_rps, max_retries=max_retries, user_agent="kg-pipeline/openalex")

    all_rows: List[dict] = []
    per_seed = []

    seed_total = len(seeds)
    for seed_idx, seed in enumerate(seeds, start=1):
        seed_rows: List[dict] = []
        seed_errors: List[str] = []

        if args.progress:
            pct = (seed_idx - 1) / max(1, seed_total) * 100.0
            print(
                f"PROGRESS: discovery seed {seed_idx}/{seed_total} ({pct:.1f}%) "
                f"query={seed.query}",
                flush=True,
            )

        if args.provider in {"semantic_scholar", "hybrid"}:
            try:
                seed_rows.extend(
                    search_semantic_scholar(
                        client=s2_client,
                        api_key=s2_api_key,
                        seed=seed,
                        max_results=args.max_results_per_seed,
                        require_doi=require_doi,
                    )
                )
            except Exception as err:
                seed_errors.append(f"semantic_scholar: {type(err).__name__}: {err}")

        if args.provider in {"openalex", "hybrid"}:
            try:
                seed_rows.extend(
                    search_openalex(
                        client=oa_client,
                        email=oa_email,
                        seed=seed,
                        max_results=args.max_results_per_seed,
                        require_doi=require_doi,
                    )
                )
            except Exception as err:
                seed_errors.append(f"openalex: {type(err).__name__}: {err}")

        all_rows.extend(seed_rows)
        per_seed.append(
            {
                "query": seed.query,
                "compound": seed.compound,
                "entity": seed.entity,
                "rows_retrieved": len(seed_rows),
                "errors": seed_errors,
            }
        )
        if args.progress:
            pct_done = seed_idx / max(1, seed_total) * 100.0
            print(
                f"PROGRESS: discovery seed {seed_idx}/{seed_total} ({pct_done:.1f}%) "
                f"rows_retrieved={len(seed_rows)} cumulative_raw_rows={len(all_rows)}",
                flush=True,
            )

    merged = merge_rows(all_rows)
    if len(merged) > args.max_results:
        merged = merged[: args.max_results]

    write_queue(queue_out, merged, args.dataset)

    report = {
        "generated_at": now_utc(),
        "dataset": args.dataset,
        "provider": args.provider,
        "require_doi": require_doi,
        "settings": {
            "semantic_scholar_rps": s2_rps,
            "openalex_rps": oa_rps,
            "max_retries": max_retries,
            "max_results_per_seed": args.max_results_per_seed,
            "max_results": args.max_results,
            "expand_seeds_from_config": args.expand_seeds_from_config,
            "auto_seeds_only": args.auto_seeds_only,
            "auto_template_mode": args.auto_template_mode,
            "auto_max_compounds": args.auto_max_compounds,
            "auto_max_entities": args.auto_max_entities,
            "auto_max_pairs": args.auto_max_pairs,
            "auto_max_seeds": args.auto_max_seeds,
        },
        "counts": {
            "seed_count": len(seeds),
            "seed_manual": seed_source_counts["manual"],
            "seed_default": seed_source_counts["default"],
            "seed_auto": seed_source_counts["auto"],
            "raw_rows": len(all_rows),
            "merged_rows": len(merged),
        },
        "queue_out": str(queue_out),
        "per_seed": per_seed,
        "rows": merged,
    }

    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Dataset: {args.dataset}")
    print(f"Provider: {args.provider}")
    print(f"Seeds: {len(seeds)}")
    print(
        "Seed sources: "
        f"manual={seed_source_counts['manual']} "
        f"default={seed_source_counts['default']} "
        f"auto={seed_source_counts['auto']}"
    )
    print(f"Raw rows: {len(all_rows)}")
    print(f"Merged rows: {len(merged)}")
    print(f"Queue: {queue_out}")
    print(f"Report: {report_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
