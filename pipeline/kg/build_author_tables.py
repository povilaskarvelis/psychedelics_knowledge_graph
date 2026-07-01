#!/usr/bin/env python3
"""Build author identity and ordered paper authorship tables for the KG.

The graph payloads should group author facets by stable IDs rather than display
names. This stage resolves authorships for the exact paper set in
`data/processed/kg/papers.parquet`, using OpenAlex when possible and falling
back to local name-only IDs when needed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    yaml = None

try:
    from pipeline.extract.io_utils import normalize, write_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.io_utils import normalize, write_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KG_DIR = ROOT / "data" / "processed" / "kg"
DEFAULT_PAPERS = DEFAULT_KG_DIR / "papers.parquet"
DEFAULT_CACHE = DEFAULT_KG_DIR / "openalex_author_cache.json"
DEFAULT_AUTHORS = DEFAULT_KG_DIR / "authors.parquet"
DEFAULT_PAPER_AUTHORS = DEFAULT_KG_DIR / "paper_authors.parquet"
DEFAULT_REPORT = DEFAULT_KG_DIR / "author_resolution_report.json"
KG_AUTHOR_TABLE_VERSION = "0.1"

UNKNOWN_AUTHOR_VALUES = {
    "",
    "unknown",
    "unknown author",
    "unknown authors",
    "not available",
    "n/a",
    "na",
    "none",
}
ORCID_RE = re.compile(r"(?:https?://orcid\.org/|orcid[:\s]+|id_orcid\s+)?(\d{4}-\d{4}-\d{4}-[\dXx]{4})")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize_doi(value: object) -> str:
    text = normalize(value)
    text = re.sub(r"^doi:\s*", "", text, flags=re.I)
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.I)
    return text.strip().lower()


def doi_url(doi: str) -> str:
    return f"https://doi.org/{doi}"


def normalize_openalex_id(value: object) -> str:
    text = normalize(value)
    if not text:
        return ""
    if text.startswith("http://openalex.org/"):
        return "https://openalex.org/" + text.rsplit("/", 1)[-1]
    if text.startswith("https://openalex.org/"):
        return text
    if re.match(r"^[WA]\d+$", text):
        return f"https://openalex.org/{text}"
    return text


def openalex_short_id(value: object) -> str:
    text = normalize_openalex_id(value)
    if not text:
        return ""
    return text.rstrip("/").rsplit("/", 1)[-1]


def normalize_orcid(value: object) -> str:
    match = ORCID_RE.search(normalize(value))
    return match.group(1).upper() if match else ""


def canonical_name(value: object) -> str:
    text = normalize(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()


def local_author_id(name: str) -> str:
    digest = hashlib.sha1(canonical_name(name).encode("utf-8")).hexdigest()[:16]
    return f"local_author:{digest}"


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists() or yaml is None:
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": KG_AUTHOR_TABLE_VERSION, "works_by_doi": {}}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {"version": KG_AUTHOR_TABLE_VERSION, "works_by_doi": {}}
    data.setdefault("version", KG_AUTHOR_TABLE_VERSION)
    data.setdefault("works_by_doi", {})
    return data


def write_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cache, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


class OpenAlexClient:
    def __init__(self, *, api_key: str = "", email: str = "", rps: float = 3.0, timeout: float = 30.0):
        self.api_key = api_key
        self.email = email
        self.min_interval = 1.0 / rps if rps and rps > 0 else 0.0
        self.timeout = timeout
        self.last_request_at = 0.0

    def get_json(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if self.api_key:
            params["api_key"] = self.api_key
        if self.email:
            params["mailto"] = self.email

        elapsed = time.monotonic() - self.last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        url = endpoint + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "psychedelics-kg-author-resolution/0.1",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            self.last_request_at = time.monotonic()
            return json.loads(response.read().decode("utf-8"))


def compact_authorships(work: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    authorships = work.get("authorships", []) if isinstance(work, dict) else []
    for index, authorship in enumerate(authorships if isinstance(authorships, list) else [], start=1):
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author") if isinstance(authorship.get("author"), dict) else {}
        display_name = normalize(author.get("display_name", ""))
        openalex_author_id = normalize_openalex_id(author.get("id", ""))
        orcid = normalize_orcid(author.get("orcid", ""))
        raw_author_name = normalize(authorship.get("raw_author_name", ""))
        if not display_name and raw_author_name:
            display_name = raw_author_name
        rows.append(
            {
                "position": index,
                "author_position": normalize(authorship.get("author_position", "")),
                "display_name": display_name,
                "raw_author_name": raw_author_name,
                "openalex_author_id": openalex_author_id,
                "orcid": orcid,
            }
        )
    return rows


def compact_work(work: dict[str, Any]) -> dict[str, Any]:
    ids = work.get("ids", {}) if isinstance(work.get("ids"), dict) else {}
    return {
        "status": "ok",
        "queried_at": now_utc(),
        "work_openalex_id": normalize_openalex_id(work.get("id", "")) or normalize_openalex_id(ids.get("openalex", "")),
        "doi": normalize_doi(work.get("doi", "")),
        "title": normalize(work.get("display_name", "")),
        "publication_year": normalize(work.get("publication_year", "")),
        "authorships": compact_authorships(work),
    }


def fetch_openalex_batch(client: OpenAlexClient, dois: list[str], retries: int = 3) -> dict[str, dict[str, Any]]:
    if not dois:
        return {}
    endpoint = "https://api.openalex.org/works"
    params = {
        "filter": "doi:" + "|".join(doi_url(doi) for doi in dois),
        "per-page": str(len(dois)),
        "select": "id,doi,display_name,publication_year,ids,authorships",
    }
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            payload = client.get_json(endpoint, params.copy())
            results = payload.get("results", []) if isinstance(payload, dict) else []
            out = {}
            for item in results if isinstance(results, list) else []:
                compact = compact_work(item if isinstance(item, dict) else {})
                doi = normalize_doi(compact.get("doi", ""))
                if doi:
                    out[doi] = compact
            return out
        except Exception as exc:  # pragma: no cover - network/runtime path
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(1.5 * attempt)
    return {doi: {"status": "error", "queried_at": now_utc(), "doi": doi, "error": last_error} for doi in dois}


def refresh_cache_for_papers(
    papers: pd.DataFrame,
    cache: dict[str, Any],
    *,
    client: OpenAlexClient,
    cache_path: Path,
    batch_size: int,
    refresh: bool,
    checkpoint_every: int,
) -> dict[str, Any]:
    works_by_doi = cache.setdefault("works_by_doi", {})
    dois = sorted({normalize_doi(value) for value in papers.get("doi", []) if normalize_doi(value)})
    missing = [doi for doi in dois if refresh or doi not in works_by_doi]
    if not missing:
        return cache

    total_batches = (len(missing) + batch_size - 1) // batch_size
    for batch_index, start in enumerate(range(0, len(missing), batch_size), start=1):
        batch = missing[start : start + batch_size]
        results = fetch_openalex_batch(client, batch)
        found = set()
        for doi, item in results.items():
            works_by_doi[doi] = item
            if item.get("status") == "ok":
                found.add(doi)
        for doi in batch:
            if doi in found:
                continue
            if doi in results and results[doi].get("status") == "error":
                works_by_doi[doi] = results[doi]
            elif doi not in works_by_doi or refresh:
                works_by_doi[doi] = {"status": "not_found", "queried_at": now_utc(), "doi": doi}
        write_cache(cache_path, cache)
        if checkpoint_every and batch_index % checkpoint_every == 0:
            print(f"Resolved OpenAlex author batch {batch_index}/{total_batches}", flush=True)
    return cache


def split_local_author_string(authors: object) -> list[dict[str, str]]:
    text = normalize(authors)
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"\s*;\s*", text) if part.strip()]
    rows: list[dict[str, str]] = []
    for part in parts:
        orcid = normalize_orcid(part)
        cleaned = ORCID_RE.sub("", part).strip(" ,;")
        if orcid and (not cleaned or normalize(cleaned).casefold() in {"id_orcid", "orcid"}):
            if rows and not rows[-1].get("orcid"):
                rows[-1]["orcid"] = orcid
            continue
        if normalize(cleaned).casefold() in UNKNOWN_AUTHOR_VALUES:
            continue
        rows.append({"display_name": cleaned or part, "orcid": orcid})
    return rows


def author_identity_from_openalex(row: dict[str, str]) -> dict[str, str]:
    name = normalize(row.get("display_name", "")) or normalize(row.get("raw_author_name", ""))
    openalex_author_id = normalize_openalex_id(row.get("openalex_author_id", ""))
    orcid = normalize_orcid(row.get("orcid", ""))
    if openalex_author_id:
        author_id = f"openalex:{openalex_short_id(openalex_author_id)}"
        confidence = "openalex_author_id"
    elif orcid:
        author_id = f"orcid:{orcid}"
        confidence = "orcid"
    else:
        author_id = local_author_id(name)
        confidence = "name_only"
    return {
        "author_id": author_id,
        "display_name": name,
        "canonical_name": canonical_name(name),
        "openalex_author_id": openalex_author_id,
        "orcid": orcid,
        "source": "openalex",
        "identity_confidence": confidence,
    }


def author_identity_from_local(row: dict[str, str]) -> dict[str, str]:
    name = normalize(row.get("display_name", ""))
    orcid = normalize_orcid(row.get("orcid", ""))
    if orcid:
        author_id = f"orcid:{orcid}"
        confidence = "orcid_from_author_string"
    else:
        author_id = local_author_id(name)
        confidence = "name_only"
    return {
        "author_id": author_id,
        "display_name": name,
        "canonical_name": canonical_name(name),
        "openalex_author_id": "",
        "orcid": orcid,
        "source": "local_authors_string",
        "identity_confidence": confidence,
    }


def authorships_for_paper(paper: dict[str, Any], cache: dict[str, Any]) -> tuple[list[dict[str, str]], str, str]:
    doi = normalize_doi(paper.get("doi", ""))
    cached = cache.get("works_by_doi", {}).get(doi, {}) if doi else {}
    status = normalize(cached.get("status", ""))
    if status == "ok" and cached.get("authorships"):
        return cached["authorships"], "openalex", normalize(cached.get("work_openalex_id", ""))
    local = split_local_author_string(paper.get("authors", ""))
    return local, f"fallback_{status or 'missing'}", normalize(cached.get("work_openalex_id", ""))


def build_tables(papers: pd.DataFrame, cache: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    author_rows_by_id: dict[str, dict[str, Any]] = {}
    name_counts_by_id: dict[str, Counter] = defaultdict(Counter)
    authorship_rows: list[dict[str, Any]] = []
    paper_status_counts: Counter = Counter()

    for paper in papers.fillna("").to_dict(orient="records"):
        paper_id = normalize(paper.get("paper_id", ""))
        doi = normalize_doi(paper.get("doi", ""))
        paper_openalex_id = normalize_openalex_id(paper.get("openalex_id", ""))
        rows, source_status, work_openalex_id = authorships_for_paper(paper, cache)
        paper_status_counts[source_status] += 1
        if not rows:
            paper_status_counts["no_authors"] += 1
            continue

        parsed_rows = []
        for index, row in enumerate(rows, start=1):
            if source_status == "openalex":
                identity = author_identity_from_openalex(row)
                author_position_label = normalize(row.get("author_position", ""))
                source = "openalex"
            else:
                identity = author_identity_from_local(row)
                author_position_label = ""
                source = source_status
            if not normalize(identity["display_name"]):
                continue
            parsed_rows.append((index, author_position_label, identity, source))

        last_index = len(parsed_rows)
        for index, author_position_label, identity, source in parsed_rows:
            existing = author_rows_by_id.get(identity["author_id"])
            if existing is None:
                author_rows_by_id[identity["author_id"]] = dict(identity)
            else:
                if not existing.get("openalex_author_id") and identity.get("openalex_author_id"):
                    existing["openalex_author_id"] = identity["openalex_author_id"]
                if not existing.get("orcid") and identity.get("orcid"):
                    existing["orcid"] = identity["orcid"]
                if existing.get("source") != "openalex" and identity.get("source") == "openalex":
                    existing["source"] = "openalex"
                    existing["identity_confidence"] = identity["identity_confidence"]
            name_counts_by_id[identity["author_id"]][identity["display_name"]] += 1
            authorship_rows.append(
                {
                    "paper_id": paper_id,
                    "doi": doi,
                    "paper_openalex_id": paper_openalex_id or work_openalex_id,
                    "author_id": identity["author_id"],
                    "display_name": identity["display_name"],
                    "canonical_name": identity["canonical_name"],
                    "openalex_author_id": identity["openalex_author_id"],
                    "orcid": identity["orcid"],
                    "author_position": index,
                    "author_position_label": author_position_label,
                    "is_first_author": index == 1,
                    "is_last_author": index == last_index,
                    "source": source,
                    "identity_confidence": identity["identity_confidence"],
                }
            )

    paper_authors = pd.DataFrame(authorship_rows)
    author_rows = []
    for author_id, row in author_rows_by_id.items():
        names = name_counts_by_id[author_id]
        display_name = sorted(names.items(), key=lambda item: (-item[1], item[0]))[0][0] if names else row["display_name"]
        author_rows.append(
            {
                **row,
                "display_name": display_name,
                "canonical_name": canonical_name(display_name),
                "display_names_json": json.dumps(sorted(names), ensure_ascii=False),
            }
        )

    authors = pd.DataFrame(author_rows)
    if not paper_authors.empty:
        counts = paper_authors.groupby("author_id").agg(
            paper_count=("paper_id", "nunique"),
            authorship_count=("paper_id", "size"),
            first_author_paper_count=("is_first_author", "sum"),
            last_author_paper_count=("is_last_author", "sum"),
        )
        authors = authors.merge(counts, on="author_id", how="left")
    for column in ("paper_count", "authorship_count", "first_author_paper_count", "last_author_paper_count"):
        if column not in authors.columns:
            authors[column] = 0
        authors[column] = authors[column].fillna(0).astype(int)

    if not authors.empty:
        authors = authors.sort_values(["paper_count", "display_name"], ascending=[False, True]).reset_index(drop=True)
    if not paper_authors.empty:
        paper_authors = paper_authors.sort_values(["paper_id", "author_position", "display_name"]).reset_index(drop=True)

    report = build_report(papers, cache, authors, paper_authors, paper_status_counts)
    return authors, paper_authors, report


def build_report(
    papers: pd.DataFrame,
    cache: dict[str, Any],
    authors: pd.DataFrame,
    paper_authors: pd.DataFrame,
    paper_status_counts: Counter,
) -> dict[str, Any]:
    works_by_doi = cache.get("works_by_doi", {})
    cache_status = Counter(normalize(item.get("status", "")) or "missing" for item in works_by_doi.values() if isinstance(item, dict))
    no_openalex = []
    no_authors = []
    paper_ids_with_authors = set(paper_authors["paper_id"]) if not paper_authors.empty else set()
    for paper in papers.fillna("").to_dict(orient="records"):
        doi = normalize_doi(paper.get("doi", ""))
        item = works_by_doi.get(doi, {}) if doi else {}
        status = normalize(item.get("status", "missing"))
        if status != "ok":
            no_openalex.append(
                {
                    "doi": doi,
                    "title": normalize(paper.get("title", "")),
                    "status": status,
                    "error": normalize(item.get("error", "")),
                }
            )
        if normalize(paper.get("paper_id", "")) not in paper_ids_with_authors:
            no_authors.append({"doi": doi, "title": normalize(paper.get("title", "")), "status": status})

    confidence_counts = (
        paper_authors["identity_confidence"].value_counts().to_dict() if not paper_authors.empty else {}
    )
    source_counts = paper_authors["source"].value_counts().to_dict() if not paper_authors.empty else {}
    author_confidence_counts = authors["identity_confidence"].value_counts().to_dict() if not authors.empty else {}
    author_source_counts = authors["source"].value_counts().to_dict() if not authors.empty else {}
    capped_input_author_strings = 0
    if "authors" in papers.columns:
        capped_input_author_strings = int(
            papers["authors"].fillna("").astype(str).map(lambda value: len(split_local_author_string(value)) >= 10).sum()
        )

    return {
        "generated_at": now_utc(),
        "kg_author_table_version": KG_AUTHOR_TABLE_VERSION,
        "paper_count": int(len(papers)),
        "paper_status_counts": dict(sorted(paper_status_counts.items())),
        "openalex_cache_status_counts": dict(sorted(cache_status.items())),
        "paper_author_rows": int(len(paper_authors)),
        "unique_authors": int(len(authors)),
        "authorship_identity_confidence_counts": {str(k): int(v) for k, v in sorted(confidence_counts.items())},
        "authorship_source_counts": {str(k): int(v) for k, v in sorted(source_counts.items())},
        "author_identity_confidence_counts": {str(k): int(v) for k, v in sorted(author_confidence_counts.items())},
        "author_source_counts": {str(k): int(v) for k, v in sorted(author_source_counts.items())},
        "input_author_strings_with_10_or_more_names": capped_input_author_strings,
        "openalex_unresolved_paper_examples": no_openalex[:25],
        "no_author_paper_examples": no_authors[:25],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve KG paper authors into identity/authorship tables")
    parser.add_argument("--papers", default=str(DEFAULT_PAPERS), help="Input kg/papers.parquet")
    parser.add_argument("--out-dir", default=str(DEFAULT_KG_DIR), help="Output KG directory")
    parser.add_argument("--cache", default=str(DEFAULT_CACHE), help="OpenAlex author cache JSON")
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.local.yaml"), help="Optional local config YAML")
    parser.add_argument("--openalex-email", default=os.getenv("OPENALEX_EMAIL", ""))
    parser.add_argument("--openalex-api-key", default=os.getenv("OPENALEX_API_KEY", ""))
    parser.add_argument("--openalex-rps", type=float, default=None)
    parser.add_argument("--openalex-timeout", type=float, default=15.0)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--checkpoint-every", type=int, default=20)
    parser.add_argument("--refresh", action="store_true", help="Refresh cached OpenAlex lookups")
    parser.add_argument("--offline", action="store_true", help="Do not query OpenAlex; use cache/local author strings only")
    args = parser.parse_args()

    papers_path = Path(args.papers)
    out_dir = Path(args.out_dir)
    cache_path = Path(args.cache)
    if not papers_path.exists():
        raise FileNotFoundError(f"Missing KG papers table: {papers_path}")

    config = load_config(Path(args.config))
    openalex_cfg = config.get("openalex", {}) if isinstance(config.get("openalex"), dict) else {}
    email = args.openalex_email or normalize(openalex_cfg.get("email", ""))
    api_key = args.openalex_api_key or normalize(openalex_cfg.get("api_key", ""))
    rps = args.openalex_rps if args.openalex_rps is not None else float(openalex_cfg.get("rate_limit_per_sec", 3.0) or 3.0)

    papers = pd.read_parquet(papers_path)
    cache = read_json(cache_path)
    if not args.offline:
        client = OpenAlexClient(api_key=api_key, email=email, rps=rps, timeout=args.openalex_timeout)
        cache = refresh_cache_for_papers(
            papers,
            cache,
            client=client,
            cache_path=cache_path,
            batch_size=max(1, args.batch_size),
            refresh=args.refresh,
            checkpoint_every=max(0, args.checkpoint_every),
        )
        write_cache(cache_path, cache)

    authors, paper_authors, report = build_tables(papers, cache)
    out_dir.mkdir(parents=True, exist_ok=True)
    authors.to_parquet(out_dir / "authors.parquet", index=False)
    paper_authors.to_parquet(out_dir / "paper_authors.parquet", index=False)
    write_json(out_dir / "author_resolution_report.json", report)

    print(f"Papers: {report['paper_count']}")
    print(f"Paper authorships: {report['paper_author_rows']}")
    print(f"Unique authors: {report['unique_authors']}")
    print(f"Paper status counts: {report['paper_status_counts']}")
    print(f"Authorship confidence: {report['authorship_identity_confidence_counts']}")
    print(f"Authors table: {out_dir / 'authors.parquet'}")
    print(f"Paper authors table: {out_dir / 'paper_authors.parquet'}")
    print(f"Report: {out_dir / 'author_resolution_report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
