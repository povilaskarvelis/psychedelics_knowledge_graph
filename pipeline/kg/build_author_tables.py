#!/usr/bin/env python3
"""Build author identity and ordered paper authorship tables for the KG.

The graph payloads should group author facets by stable IDs rather than display
names. This stage resolves authorships for the exact paper set in
`data/processed/kg/papers.parquet`. It may retain unresolved names in memory for
auditing, but it refuses to write release author tables unless at least 95% of
authorship rows have an OpenAlex or ORCID identity.
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
from collections import Counter
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
DEFAULT_IDENTITY_OVERRIDES = ROOT / "pipeline" / "kg" / "author_identity_overrides.json"
KG_AUTHOR_TABLE_VERSION = "0.2"
MIN_STRUCTURED_AUTHORSHIP_RATE = 0.95
MIN_OFFLINE_CACHE_COVERAGE = 0.95

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
NON_IDENTITY_OPENALEX_AUTHOR_IDS = {"A9999999999", "A5317838346"}


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


def load_identity_overrides(path: Path) -> dict[str, dict[str, str]]:
    """Load explicit, reviewed mappings without inferring identity from names."""

    if not path.is_file():
        return {
            "openalex_to_orcid": {},
            "local_name_to_orcid": {},
            "preferred_name_by_orcid": {},
        }
    payload = read_json(path)
    records = payload.get("overrides", [])
    if not isinstance(records, list):
        raise ValueError(f"Identity overrides must contain an overrides array: {path}")

    openalex_to_orcid: dict[str, str] = {}
    local_name_to_orcid: dict[str, str] = {}
    preferred_name_by_orcid: dict[str, str] = {}
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"Identity override {index} is not an object: {path}")
        orcid = normalize_orcid(record.get("orcid", ""))
        preferred_name = normalize(record.get("preferred_name", ""))
        reason = normalize(record.get("reason", ""))
        if not orcid or not preferred_name or not reason:
            raise ValueError(
                f"Identity override {index} requires a valid ORCID, preferred_name, and reason: {path}"
            )
        preferred_name_by_orcid[orcid] = preferred_name
        for value in record.get("openalex_author_ids", []):
            openalex_id = normalize_openalex_id(value)
            previous = openalex_to_orcid.get(openalex_id)
            if previous and previous != orcid:
                raise ValueError(f"OpenAlex author {openalex_id} maps to multiple ORCIDs in {path}")
            openalex_to_orcid[openalex_id] = orcid
        for value in record.get("local_name_aliases", []):
            name = canonical_name(value)
            previous = local_name_to_orcid.get(name)
            if previous and previous != orcid:
                raise ValueError(f"Author name {value!r} maps to multiple ORCIDs in {path}")
            local_name_to_orcid[name] = orcid
    return {
        "openalex_to_orcid": openalex_to_orcid,
        "local_name_to_orcid": local_name_to_orcid,
        "preferred_name_by_orcid": preferred_name_by_orcid,
    }


def paper_dois(papers: pd.DataFrame) -> set[str]:
    return {
        doi
        for value in papers.get("doi", [])
        if (doi := normalize_doi(value))
    }


def successful_cache_coverage(papers: pd.DataFrame, cache: dict[str, Any]) -> tuple[int, int, float]:
    """Return successful OpenAlex cache entries for the DOI-bearing paper set."""

    dois = paper_dois(papers)
    works_by_doi = cache.get("works_by_doi", {})
    successful = sum(
        1
        for doi in dois
        if isinstance(works_by_doi.get(doi), dict)
        and normalize(works_by_doi[doi].get("status", "")) == "ok"
        and bool(works_by_doi[doi].get("authorships"))
    )
    rate = successful / len(dois) if dois else 0.0
    return successful, len(dois), rate


def structured_authorship_coverage(paper_authors: pd.DataFrame) -> tuple[int, int, float]:
    """Return authorship rows backed by stable OpenAlex or ORCID identities."""

    total = len(paper_authors)
    if not total or "author_id" not in paper_authors.columns:
        return 0, total, 0.0
    structured_mask = (
        paper_authors["author_id"]
        .fillna("")
        .astype(str)
        .str.startswith(("openalex:", "orcid:"))
    )
    if "identity_confidence" in paper_authors.columns:
        structured_mask &= paper_authors["identity_confidence"].ne(
            "openalex_author_id_orcid_conflict"
        )
    structured = int(structured_mask.sum())
    return structured, total, structured / total


def require_offline_cache_coverage(papers: pd.DataFrame, cache: dict[str, Any], cache_path: Path) -> None:
    successful, total, rate = successful_cache_coverage(papers, cache)
    if rate < MIN_OFFLINE_CACHE_COVERAGE:
        raise RuntimeError(
            "Offline author resolution refused: OpenAlex cache "
            f"{cache_path} contains successful authorships for {successful}/{total} "
            f"DOI-bearing papers ({rate:.1%}); at least {MIN_OFFLINE_CACHE_COVERAGE:.0%} "
            "is required. Seed this run with an explicit AUTHOR_CACHE_SEED or run "
            "without --offline to refresh the cache. Existing author tables were not changed."
        )


def require_structured_authorship_coverage(paper_authors: pd.DataFrame) -> tuple[int, int, float]:
    structured, total, rate = structured_authorship_coverage(paper_authors)
    if rate < MIN_STRUCTURED_AUTHORSHIP_RATE:
        raise RuntimeError(
            "Author table build refused: only "
            f"{structured}/{total} authorship rows ({rate:.1%}) have an OpenAlex or "
            f"ORCID identity; at least {MIN_STRUCTURED_AUTHORSHIP_RATE:.0%} is required. "
            "Existing author tables were not changed."
        )
    return structured, total, rate


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
    missing = [
        doi
        for doi in dois
        if refresh
        or doi not in works_by_doi
        or normalize((works_by_doi.get(doi) or {}).get("status", "")) == "error"
    ]
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
    if openalex_short_id(openalex_author_id) in NON_IDENTITY_OPENALEX_AUTHOR_IDS:
        openalex_author_id = ""
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


def alias_confidence_for_target(value: object) -> str:
    confidence = normalize(value)
    if confidence == "orcid":
        return "name_alias_to_orcid"
    if confidence == "openalex_author_id":
        return "name_alias_to_openalex_author_id"
    return "name_alias_to_structured_author_id"


def authorships_for_paper(paper: dict[str, Any], cache: dict[str, Any]) -> tuple[list[dict[str, str]], str, str]:
    doi = normalize_doi(paper.get("doi", ""))
    cached = cache.get("works_by_doi", {}).get(doi, {}) if doi else {}
    status = normalize(cached.get("status", ""))
    if status == "ok" and cached.get("authorships"):
        return cached["authorships"], "openalex", normalize(cached.get("work_openalex_id", ""))
    local = split_local_author_string(paper.get("authors", ""))
    return local, f"fallback_{status or 'missing'}", normalize(cached.get("work_openalex_id", ""))


def apply_exact_name_aliases(paper_authors: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    if paper_authors.empty:
        return paper_authors, {"name_alias_authorship_rows": 0, "name_alias_author_ids": 0, "name_alias_names": 0}

    out = paper_authors.copy()
    local_mask = out["author_id"].astype(str).str.startswith("local_author:")
    structured = out[~local_mask & out["canonical_name"].astype(str).str.strip().ne("")]
    if structured.empty:
        return out, {"name_alias_authorship_rows": 0, "name_alias_author_ids": 0, "name_alias_names": 0}

    structured_ids_by_name = structured.groupby("canonical_name")["author_id"].nunique()
    safe_names = set(structured_ids_by_name[structured_ids_by_name == 1].index)
    alias_mask = local_mask & out["canonical_name"].isin(safe_names)
    if not alias_mask.any():
        return out, {"name_alias_authorship_rows": 0, "name_alias_author_ids": 0, "name_alias_names": 0}

    target_rows = (
        structured[structured["canonical_name"].isin(safe_names)]
        .sort_values(["canonical_name", "identity_confidence", "author_id"])
        .drop_duplicates("canonical_name")
        .set_index("canonical_name")
    )

    aliased_author_ids = set(out.loc[alias_mask, "author_id"])
    for idx in out.index[alias_mask]:
        name = out.at[idx, "canonical_name"]
        target = target_rows.loc[name]
        out.at[idx, "author_id"] = target["author_id"]
        if not normalize(out.at[idx, "openalex_author_id"]):
            out.at[idx, "openalex_author_id"] = normalize(target.get("openalex_author_id", ""))
        if not normalize(out.at[idx, "orcid"]):
            out.at[idx, "orcid"] = normalize(target.get("orcid", ""))
        out.at[idx, "identity_confidence"] = alias_confidence_for_target(target.get("identity_confidence", ""))

    return out, {
        "name_alias_authorship_rows": int(alias_mask.sum()),
        "name_alias_author_ids": len(aliased_author_ids),
        "name_alias_names": len(set(out.loc[alias_mask, "canonical_name"])),
    }


def apply_orcid_identities(
    paper_authors: pd.DataFrame,
    identity_overrides: dict[str, dict[str, str]] | None = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Canonicalize identities by ORCID only when the evidence is unambiguous."""

    empty_stats = {
        "openalex_profiles_linked_to_orcid": 0,
        "openalex_profiles_with_conflicting_orcids": 0,
        "openalex_profiles_merged_by_shared_orcid": 0,
        "authorship_rows_canonicalized_to_orcid": 0,
        "curated_openalex_profile_mappings": 0,
        "curated_local_name_mappings": 0,
    }
    if paper_authors.empty:
        return paper_authors, empty_stats

    out = paper_authors.copy()
    overrides = identity_overrides or {}
    openalex_overrides = overrides.get("openalex_to_orcid", {})
    local_name_overrides = overrides.get("local_name_to_orcid", {})

    curated_openalex_rows = 0
    for index in out.index:
        openalex_id = normalize_openalex_id(out.at[index, "openalex_author_id"])
        curated_orcid = openalex_overrides.get(openalex_id, "")
        observed_orcid = normalize_orcid(out.at[index, "orcid"])
        if curated_orcid:
            if observed_orcid and observed_orcid != curated_orcid:
                raise ValueError(
                    f"Curated ORCID {curated_orcid} conflicts with observed ORCID "
                    f"{observed_orcid} for {openalex_id}"
                )
            out.at[index, "orcid"] = curated_orcid
            curated_openalex_rows += 1

    local_mask = out["author_id"].astype(str).str.startswith("local_author:")
    curated_local_mask = local_mask & out["canonical_name"].map(
        lambda value: canonical_name(value) in local_name_overrides
    )
    for index in out.index[curated_local_mask]:
        orcid = local_name_overrides[canonical_name(out.at[index, "canonical_name"])]
        out.at[index, "author_id"] = f"orcid:{orcid}"
        out.at[index, "orcid"] = orcid
        out.at[index, "identity_confidence"] = "curated_name_to_orcid"

    openalex_rows = out[out["openalex_author_id"].fillna("").astype(str).str.strip().ne("")]
    observed = openalex_rows[openalex_rows["orcid"].fillna("").astype(str).str.strip().ne("")]
    orcids_by_openalex = observed.groupby("openalex_author_id")["orcid"].agg(
        lambda values: sorted({normalize_orcid(value) for value in values if normalize_orcid(value)})
    )
    conflicts = {openalex_id for openalex_id, values in orcids_by_openalex.items() if len(values) > 1}
    safe_mapping = {
        normalize_openalex_id(openalex_id): values[0]
        for openalex_id, values in orcids_by_openalex.items()
        if len(values) == 1
    }

    canonicalized_rows = 0
    if conflicts:
        conflict_mask = out["openalex_author_id"].isin(conflicts)
        out.loc[conflict_mask, "orcid"] = ""
        out.loc[conflict_mask, "identity_confidence"] = "openalex_author_id_orcid_conflict"
    for index in out.index:
        openalex_id = normalize_openalex_id(out.at[index, "openalex_author_id"])
        orcid = safe_mapping.get(openalex_id, "")
        if not orcid:
            continue
        out.at[index, "author_id"] = f"orcid:{orcid}"
        out.at[index, "orcid"] = orcid
        out.at[index, "identity_confidence"] = "orcid"
        canonicalized_rows += 1

    profiles_per_orcid: Counter[str] = Counter(safe_mapping.values())
    return out, {
        "openalex_profiles_linked_to_orcid": len(safe_mapping),
        "openalex_profiles_with_conflicting_orcids": len(conflicts),
        "openalex_profiles_merged_by_shared_orcid": sum(
            count - 1 for count in profiles_per_orcid.values() if count > 1
        ),
        "authorship_rows_canonicalized_to_orcid": canonicalized_rows,
        "curated_openalex_profile_mappings": len(openalex_overrides),
        "curated_local_name_mappings": int(curated_local_mask.sum()),
    }


def first_nonempty(values: Iterable[object]) -> str:
    for value in values:
        text = normalize(value)
        if text:
            return text
    return ""


def best_author_source(values: Iterable[object]) -> str:
    items = [normalize(value) for value in values if normalize(value)]
    if "openalex" in items:
        return "openalex"
    if items:
        return "local_authors_string"
    return ""


def best_author_identity_confidence(author_id: str, values: Iterable[object]) -> str:
    if author_id.startswith("orcid:"):
        return "orcid"
    if author_id.startswith("openalex:"):
        return "openalex_author_id"
    items = [normalize(value) for value in values if normalize(value)]
    for candidate in ("orcid_from_author_string", "name_alias_to_orcid", "name_alias_to_openalex_author_id", "name_only"):
        if candidate in items:
            return candidate
    return items[0] if items else ""


def build_authors_from_authorships(paper_authors: pd.DataFrame) -> pd.DataFrame:
    if paper_authors.empty:
        return pd.DataFrame()

    author_rows = []
    for author_id, group in paper_authors.groupby("author_id", sort=False):
        names = Counter(normalize(value) for value in group["display_name"] if normalize(value))
        display_name = sorted(names.items(), key=lambda item: (-item[1], item[0]))[0][0] if names else ""
        author_rows.append(
            {
                "author_id": author_id,
                "display_name": display_name,
                "canonical_name": canonical_name(display_name),
                "openalex_author_id": first_nonempty(group["openalex_author_id"]),
                "openalex_author_ids_json": json.dumps(
                    sorted(
                        {
                            normalize_openalex_id(value)
                            for value in group["openalex_author_id"]
                            if normalize_openalex_id(value)
                        }
                    ),
                    ensure_ascii=False,
                ),
                "orcid": first_nonempty(group["orcid"]),
                "source": best_author_source(group["source"]),
                "identity_confidence": best_author_identity_confidence(author_id, group["identity_confidence"]),
                "display_names_json": json.dumps(sorted(names), ensure_ascii=False),
            }
        )

    authors = pd.DataFrame(author_rows)
    counts = paper_authors.groupby("author_id").agg(
        paper_count=("paper_id", "nunique"),
        authorship_count=("paper_id", "size"),
        first_author_paper_count=("is_first_author", "sum"),
        last_author_paper_count=("is_last_author", "sum"),
    )
    authors = authors.merge(counts, on="author_id", how="left")
    for column in ("paper_count", "authorship_count", "first_author_paper_count", "last_author_paper_count"):
        authors[column] = authors[column].fillna(0).astype(int)
    return authors.sort_values(["paper_count", "display_name"], ascending=[False, True]).reset_index(drop=True)


def build_tables(
    papers: pd.DataFrame,
    cache: dict[str, Any],
    identity_overrides: dict[str, dict[str, str]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
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
    if not paper_authors.empty:
        paper_authors, orcid_stats = apply_orcid_identities(paper_authors, identity_overrides)
        paper_authors, alias_stats = apply_exact_name_aliases(paper_authors)
        paper_authors = paper_authors.sort_values(["paper_id", "author_position", "display_name"]).reset_index(drop=True)
    else:
        orcid_stats = apply_orcid_identities(paper_authors, identity_overrides)[1]
        alias_stats = {"name_alias_authorship_rows": 0, "name_alias_author_ids": 0, "name_alias_names": 0}
    authors = build_authors_from_authorships(paper_authors)

    report = build_report(papers, cache, authors, paper_authors, paper_status_counts)
    report["orcid_identity_resolution_counts"] = orcid_stats
    report["name_alias_resolution_counts"] = alias_stats

    preferred_names = (identity_overrides or {}).get("preferred_name_by_orcid", {})
    if not authors.empty and preferred_names:
        for index in authors.index:
            author_id = normalize(authors.at[index, "author_id"])
            if not author_id.startswith("orcid:"):
                continue
            preferred_name = preferred_names.get(author_id.removeprefix("orcid:"), "")
            if preferred_name:
                authors.at[index, "display_name"] = preferred_name
                authors.at[index, "canonical_name"] = canonical_name(preferred_name)
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
    structured_rows, total_rows, structured_rate = structured_authorship_coverage(paper_authors)
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
        "structured_authorship_rows": structured_rows,
        "unresolved_authorship_rows": total_rows - structured_rows,
        "structured_authorship_rate": structured_rate,
        "minimum_structured_authorship_rate": MIN_STRUCTURED_AUTHORSHIP_RATE,
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
    parser.add_argument(
        "--identity-overrides",
        default=str(DEFAULT_IDENTITY_OVERRIDES),
        help="Reviewed OpenAlex/ORCID identity correction registry",
    )
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.local.yaml"), help="Optional local config YAML")
    parser.add_argument("--openalex-email", default=os.getenv("OPENALEX_EMAIL", ""))
    parser.add_argument("--openalex-api-key", default=os.getenv("OPENALEX_API_KEY", ""))
    parser.add_argument("--openalex-rps", type=float, default=None)
    parser.add_argument("--openalex-timeout", type=float, default=15.0)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--checkpoint-every", type=int, default=20)
    parser.add_argument("--refresh", action="store_true", help="Refresh cached OpenAlex lookups")
    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Do not query OpenAlex. Requires the existing cache to resolve at least "
            f"{MIN_OFFLINE_CACHE_COVERAGE:.0%} of DOI-bearing papers.".replace("%", "%%")
        ),
    )
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
    identity_overrides = load_identity_overrides(Path(args.identity_overrides))
    if args.offline:
        require_offline_cache_coverage(papers, cache, cache_path)
    else:
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

    authors, paper_authors, report = build_tables(papers, cache, identity_overrides)
    require_structured_authorship_coverage(paper_authors)
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
