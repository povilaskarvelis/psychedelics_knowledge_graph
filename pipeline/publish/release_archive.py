#!/usr/bin/env python3
"""Keep published browser releases viewable after they are replaced.

Each published release gets a frozen copy of its data pointer and a copy of the
static site it was published with, under ``browser/archive/<slug>/``. The site
copy loads only its own release, so later interface or data-format changes do
not change how an earlier release is displayed. ``browser/archive/index.json``
lists the archived releases for the Methods page and for history pruning.

The release publisher archives each new release. Run this module directly to
archive the release that is live now if it was published before archiving
existed (dry run unless ``--execute``)::

    python3 pipeline/publish/release_archive.py --archive-live --site-ref origin/main
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.query_api.r2_store import (  # noqa: E402
    ObjectStore,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)


ARCHIVE_INDEX_SCHEMA_VERSION = "psychedelics_kg_release_archive_index_v1"
ARCHIVE_DIRNAME = "archive"
ARCHIVE_POINTER_NAME = "pointer.json"
ARCHIVE_INDEX_NAME = "index.json"
ARCHIVE_CACHE_CONTROL = "public, max-age=3600"
INDEX_CACHE_CONTROL = "no-cache, max-age=0, must-revalidate"
LIVE_POINTER_URL = "https://data.psychedelicskg.com/browser/active.json"
DEFAULT_DATA_ORIGIN = "https://data.psychedelicskg.com"
SITE_ORIGIN = "https://psychedelicskg.com"
SNAPSHOT_ROOTS = ("index.html", "methods", "compounds", "ui", "schema")
SNAPSHOT_EXCLUDED = frozenset({"ui/index.html", "ui/methods.html"})
POINTER_REQUIRED_FILES = ("ui/app.js", "ui/methods.js")
ARCHIVED_ROOT_DIRECTORIES = ("/ui/", "/methods/", "/compounds/", "/schema/")
REWRITTEN_SUFFIXES = frozenset({".html", ".js", ".css"})
SLUG_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[0-9a-f]{8}$")
ARCHIVE_ENTRY_FIELDS = (
    "slug",
    "pointer_key",
    "site_entry_key",
    "site_commit",
    "site_tree_dirty",
    "site_tree_sha256",
    "site_version",
    "literature_updated",
    "paper_counts",
    "finding_count",
)

URL_ATTRIBUTE_RE = re.compile(
    r"""(?P<prefix>\b(?P<name>href|src|action|data-[a-z0-9-]+)\s*=\s*)"""
    r"""(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)')""",
    re.IGNORECASE,
)
BASE_TAG_RE = re.compile(r"<base\b[^>]*>", re.IGNORECASE)
HEAD_OPEN_RE = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
BODY_CLOSE_RE = re.compile(r"</body\s*>", re.IGNORECASE)
ROBOTS_META_RE = re.compile(r"""<meta\s+name=["']robots["'][^>]*>\s*""", re.IGNORECASE)
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
SCRIPT_UI_PATH_RE = re.compile(r"""(?<=["'`])/ui/""")
HTML_LEFTOVER_RE = re.compile(
    r"""\b(?:href|src|action|data-[a-z0-9-]+)\s*=\s*["']"""
    r"""(?:/(?:ui|methods|compounds|schema)[/"'?#]|/(?:index\.html)?["'?#])""",
    re.IGNORECASE,
)
SCRIPT_LEFTOVER_RE = re.compile(r"""["'`]/ui/""")


class ArchiveConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class SiteSnapshot:
    directory: Path
    files: tuple[str, ...]
    commit: str
    tree_dirty: bool | None
    tree_sha256: str


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def parse_timestamp(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def archive_slug(release_id: str, published_at: str) -> str:
    """Return a short, stable folder name: publication date plus release hash."""
    if not release_id.strip():
        raise ValueError("An archived release needs a release ID")
    day = parse_timestamp(published_at).date().isoformat()
    digest = hashlib.sha256(release_id.encode("utf-8")).hexdigest()[:8]
    return f"{day}-{digest}"


def archive_root(browser_prefix: str) -> str:
    return f"{browser_prefix.strip('/')}/{ARCHIVE_DIRNAME}"


def archive_prefix(browser_prefix: str, slug: str) -> str:
    if not SLUG_RE.fullmatch(slug):
        raise ValueError(f"Invalid archived release folder: {slug!r}")
    return f"{archive_root(browser_prefix)}/{slug}"


def archive_index_key(browser_prefix: str) -> str:
    return f"{archive_root(browser_prefix)}/{ARCHIVE_INDEX_NAME}"


def archive_slug_of_key(key: str, browser_prefix: str) -> str:
    """Return the archive folder that holds ``key`` ("" for the index)."""
    root = f"{archive_root(browser_prefix)}/"
    if not key.startswith(root):
        raise ValueError(f"Not an archive object: {key}")
    relative = key[len(root):]
    if relative == ARCHIVE_INDEX_NAME:
        return ""
    return relative.split("/", 1)[0]


def release_prefix_of_key(key: str, releases_prefix: str) -> str:
    """Return the two-level release prefix that holds an immutable release object."""
    if not releases_prefix.endswith("/") or not key.startswith(releases_prefix):
        raise ValueError(f"Not a release object: {key}")
    parts = key[len(releases_prefix):].split("/")
    if len(parts) < 3:
        return key
    return f"{releases_prefix}{parts[0]}/{parts[1]}"


# ---------------------------------------------------------------------------
# Archive index


def empty_archive_index() -> dict:
    return {
        "schema_version": ARCHIVE_INDEX_SCHEMA_VERSION,
        "current_release_id": "",
        "releases": [],
    }


def read_archive_index(store: ObjectStore, browser_prefix: str) -> dict:
    key = archive_index_key(browser_prefix)
    if store.head(key) is None:
        return empty_archive_index()
    value = json.loads(store.get_bytes(key))
    if not isinstance(value, dict) or value.get("schema_version") != ARCHIVE_INDEX_SCHEMA_VERSION:
        raise ValueError(f"Unexpected release archive index: {key}")
    releases = value.get("releases")
    if not isinstance(releases, list) or not all(isinstance(entry, dict) for entry in releases):
        raise ValueError(f"Release archive index has an invalid release list: {key}")
    for entry in releases:
        if not str(entry.get("release_id") or "").strip():
            raise ValueError(f"Release archive index has an entry without a release ID: {key}")
    return value


def sorted_entries(entries: Iterable[dict]) -> list[dict]:
    return sorted(
        entries,
        key=lambda entry: (str(entry.get("published_at") or ""), str(entry.get("release_id") or "")),
        reverse=True,
    )


def find_entry(entries: Iterable[dict], release_id: str) -> dict | None:
    for entry in entries:
        if entry.get("release_id") == release_id:
            return entry
    return None


def upsert_entry(entries: Iterable[dict], entry: dict) -> list[dict]:
    release_id = entry["release_id"]
    return [existing for existing in entries if existing.get("release_id") != release_id] + [entry]


def write_archive_index(
    store: ObjectStore,
    browser_prefix: str,
    *,
    entries: Iterable[dict],
    current_release_id: str,
    updated_at: str | None = None,
) -> dict:
    payload = {
        "schema_version": ARCHIVE_INDEX_SCHEMA_VERSION,
        "updated_at": updated_at or now_utc(),
        "current_release_id": current_release_id,
        "releases": sorted_entries(entries),
    }
    key = archive_index_key(browser_prefix)
    data = canonical_json_bytes(payload)
    store.put_bytes(
        key,
        data,
        sha256=sha256_bytes(data),
        content_type="application/json",
        cache_control=INDEX_CACHE_CONTROL,
    )
    if store.get_bytes(key) != data:
        raise RuntimeError("Release archive index failed read-after-write verification")
    return payload


def entry_from_pointer(pointer: dict) -> dict:
    """Describe a published release for the archive index."""
    archive = pointer.get("archive") if isinstance(pointer.get("archive"), dict) else {}
    entry = {
        "release_id": str(pointer.get("release_id") or "").strip(),
        "evidence_release_id": str(pointer.get("evidence_release_id") or "").strip(),
        "run_id": str(pointer.get("run_id") or "").strip(),
        "published_at": str(pointer.get("published_at") or "").strip(),
        "object_prefix": str(pointer.get("object_prefix") or "").strip(),
    }
    defaults = {"paper_counts": {}, "finding_count": None, "site_tree_dirty": None}
    for field in ARCHIVE_ENTRY_FIELDS:
        entry[field] = archive.get(field, defaults.get(field, ""))
    if not entry["release_id"]:
        raise ValueError("A published pointer lacks its release ID")
    return entry


@dataclass(frozen=True)
class RetentionPlan:
    active_release_id: str
    previous: dict | None
    kept: tuple[dict, ...]
    dropped: tuple[dict, ...]


def plan_archive_retention(entries: Iterable[dict], active_release_id: str) -> RetentionPlan:
    """Choose which published releases stay available.

    Kept: the live release, the release published just before it (so pages
    opened before an update keep loading), and the last release of every
    evidence release (the archive). Public refreshes that were replaced by a
    later refresh of the same evidence release are dropped.
    """
    ordered = sorted_entries(entries)[::-1]
    active = find_entry(ordered, active_release_id)
    earlier = [
        entry
        for entry in ordered
        if entry.get("release_id") != active_release_id
        and (active is None or str(entry.get("published_at") or "") <= str(active.get("published_at") or ""))
    ]
    previous = earlier[-1] if earlier else None
    latest_by_evidence: dict[str, dict] = {}
    for entry in ordered:
        latest_by_evidence[str(entry.get("evidence_release_id") or entry["release_id"])] = entry
    kept_ids = {active_release_id}
    if previous is not None:
        kept_ids.add(previous["release_id"])
    kept_ids.update(entry["release_id"] for entry in latest_by_evidence.values())
    kept = tuple(entry for entry in sorted_entries(ordered) if entry["release_id"] in kept_ids)
    dropped = tuple(entry for entry in sorted_entries(ordered) if entry["release_id"] not in kept_ids)
    return RetentionPlan(
        active_release_id=active_release_id,
        previous=previous,
        kept=kept,
        dropped=dropped,
    )


# ---------------------------------------------------------------------------
# Site snapshot


def split_url_suffix(value: str) -> tuple[str, str]:
    for index, character in enumerate(value):
        if character in "?#":
            return value[:index], value[index:]
    return value, ""


def archived_root_path(path: str) -> bool:
    if path in {"/", "/index.html"}:
        return True
    return any(
        path == directory.rstrip("/") or path.startswith(directory)
        for directory in ARCHIVED_ROOT_DIRECTORIES
    )


def relocated_url(value: str, *, site_path: str, url_attribute: bool = True) -> str:
    """Point a site-internal URL at the archived copy under ``site_path``.

    Root-relative links to pages that are archived (explorer, Methods,
    compound pages, ``ui/`` assets) move into the archive; links to pages that
    are not release-specific (About, API, feedback) keep pointing at the live
    site. Directory links gain ``index.html`` because object storage has no
    directory index.
    """
    stripped = value.strip()
    if not stripped or stripped.startswith(("#", "//")) or SCHEME_RE.match(stripped):
        return value
    path, suffix = split_url_suffix(stripped)
    if path.startswith("/"):
        if not archived_root_path(path):
            return value
        if path in {directory.rstrip("/") for directory in ARCHIVED_ROOT_DIRECTORIES}:
            path = f"{path}/"
        path = f"{site_path}{path}"
    elif not url_attribute or not path:
        return value
    if path.endswith("/"):
        path = f"{path}index.html"
    elif path in {".", ".."} or path.endswith(("/.", "/..")):
        path = f"{path}/index.html"
    return f"{path}{suffix}"


def replace_pointer_literals(text: str, *, pointer_url: str, pointer_path: str) -> tuple[str, int]:
    count = text.count(LIVE_POINTER_URL)
    text = text.replace(LIVE_POINTER_URL, pointer_url)
    for quote in ('"', "'", "`"):
        literal = f"{quote}/browser/active.json{quote}"
        count += text.count(literal)
        text = text.replace(literal, f"{quote}{pointer_path}{quote}")
    return text, count


def relocate_html(text: str, *, site_path: str, pointer_url: str, pointer_path: str) -> tuple[str, int]:
    protected: list[str] = []

    def protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"\x00archive-base-{len(protected) - 1}\x00"

    def rewrite(match: re.Match[str]) -> str:
        url_attribute = not match.group("name").lower().startswith("data-")
        if match.group("dq") is not None:
            value = relocated_url(match.group("dq"), site_path=site_path, url_attribute=url_attribute)
            return f'{match.group("prefix")}"{value}"'
        value = relocated_url(match.group("sq"), site_path=site_path, url_attribute=url_attribute)
        return f"{match.group('prefix')}'{value}'"

    text = BASE_TAG_RE.sub(protect, text)
    text, count = replace_pointer_literals(text, pointer_url=pointer_url, pointer_path=pointer_path)
    text = URL_ATTRIBUTE_RE.sub(rewrite, text)
    text = SCRIPT_UI_PATH_RE.sub(f"{site_path}/ui/", text)
    for index, original in enumerate(protected):
        text = text.replace(f"\x00archive-base-{index}\x00", original)
    return text, count


def relocate_script(text: str, *, site_path: str, pointer_url: str, pointer_path: str) -> tuple[str, int]:
    text, count = replace_pointer_literals(text, pointer_url=pointer_url, pointer_path=pointer_path)
    return SCRIPT_UI_PATH_RE.sub(f"{site_path}/ui/", text), count


def format_release_date(published_at: str) -> str:
    day = parse_timestamp(published_at).date()
    return f"{day:%B} {day.day}, {day.year}"


def script_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def archive_head_markup(*, slug: str, pointer_path: str) -> str:
    return (
        '\n    <meta name="robots" content="noindex,follow" />'
        f'\n    <meta name="kg-archived-release" content="{slug}" />'
        f'\n    <meta name="kg-data-pointer" content="{pointer_path}" />'
    )


def archive_banner_markup(*, release_id: str, published_at: str, paper_total: int | None) -> str:
    published = format_release_date(published_at)
    papers = f" ({paper_total:,} papers)" if isinstance(paper_total, int) and paper_total > 0 else ""
    archived_text = (
        f"Archived release, published {published}{papers}. It shows the results and the "
        "site as they were published; later corrections are not included."
    )
    current_text = f"This copy matches the current release, published {published}{papers}."
    return f"""
    <div class="kg-archive-banner" id="kgArchiveBanner" role="region" aria-label="Archived release">
      <p id="kgArchiveBannerText">{archived_text}</p>
      <p class="kg-archive-banner-actions">
        <a href="{SITE_ORIGIN}/">Open the current release</a>
        <a href="{SITE_ORIGIN}/methods/#release-notes">All releases</a>
        <button type="button" id="kgArchiveBannerHide">Hide</button>
      </p>
    </div>
    <style>
      .kg-archive-banner {{ position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 2147483000;
        display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; justify-content: space-between;
        padding: 12px 16px; border: 1px solid #c9a227; border-radius: 8px; background: #1b1810; color: #f3ead2;
        font: 14px/1.45 "IBM Plex Sans", system-ui, sans-serif; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45); }}
      .kg-archive-banner p {{ margin: 0; }}
      .kg-archive-banner-actions {{ display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; }}
      .kg-archive-banner a {{ color: #ffd76a; text-decoration: underline; }}
      .kg-archive-banner button {{ border: 1px solid #6b5a22; border-radius: 6px; background: transparent;
        color: inherit; font: inherit; padding: 2px 10px; cursor: pointer; }}
    </style>
    <script>
      (() => {{
        const banner = document.getElementById("kgArchiveBanner");
        document.getElementById("kgArchiveBannerHide")?.addEventListener("click", () => banner?.remove());
        const host = window.location.hostname;
        if (host !== "psychedelicskg.com" && !host.endsWith(".psychedelicskg.com") &&
            !host.endsWith("psychedelicskg.netlify.app")) return;
        fetch("/browser/active.json", {{ cache: "no-store" }})
          .then((response) => (response.ok ? response.json() : null))
          .then((live) => {{
            if (!live || live.release_id !== {script_json(release_id)}) return;
            const text = document.getElementById("kgArchiveBannerText");
            if (text) text.textContent = {script_json(current_text)};
          }})
          .catch(() => {{}});
      }})();
    </script>
"""


def add_archive_markup(text: str, *, head_markup: str, banner_markup: str) -> str:
    text = ROBOTS_META_RE.sub("", text)
    head = HEAD_OPEN_RE.search(text)
    if head is None:
        raise ValueError("An archived page has no <head> element")
    text = f"{text[:head.end()]}{head_markup}{text[head.end():]}"
    closings = list(BODY_CLOSE_RE.finditer(text))
    if not closings:
        raise ValueError("An archived page has no </body> element")
    last = closings[-1]
    return f"{text[:last.start()]}{banner_markup}{text[last.start():]}"


def iter_snapshot_files(built_site: Path) -> list[str]:
    files: list[str] = []
    for root_name in SNAPSHOT_ROOTS:
        path = built_site / root_name
        if path.is_file():
            files.append(root_name)
        elif path.is_dir():
            files.extend(
                child.relative_to(built_site).as_posix()
                for child in sorted(path.rglob("*"))
                if child.is_file() and child.name != ".DS_Store"
            )
    files = [name for name in files if name not in SNAPSHOT_EXCLUDED]
    for required in ("index.html", "methods/index.html", *POINTER_REQUIRED_FILES):
        if required not in files:
            raise FileNotFoundError(f"The built site has no {required}")
    return files


def tree_sha256(directory: Path, files: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(directory / name).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def prepare_site_snapshot(
    *,
    built_site: Path,
    destination: Path,
    slug: str,
    browser_prefix: str,
    data_origin: str,
    release_id: str,
    published_at: str,
    paper_total: int | None,
) -> tuple[str, ...]:
    """Copy the release-specific pages of a built site and relocate them."""
    site_path = f"/{archive_prefix(browser_prefix, slug)}"
    pointer_path = f"{site_path}/{ARCHIVE_POINTER_NAME}"
    pointer_url = f"{data_origin.rstrip('/')}{pointer_path}"
    files = iter_snapshot_files(built_site)
    rewritten: dict[str, str] = {}
    pointer_counts: dict[str, int] = {}
    for name in files:
        source = built_site / name
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix not in REWRITTEN_SUFFIXES:
            shutil.copy2(source, target)
            continue
        text = source.read_text(encoding="utf-8")
        if source.suffix == ".html":
            text, count = relocate_html(
                text, site_path=site_path, pointer_url=pointer_url, pointer_path=pointer_path
            )
        else:
            text, count = relocate_script(
                text, site_path=site_path, pointer_url=pointer_url, pointer_path=pointer_path
            )
        rewritten[name] = text
        pointer_counts[name] = count

    missing_pointer = [name for name in POINTER_REQUIRED_FILES if not pointer_counts.get(name)]
    if missing_pointer:
        raise ValueError(
            "The site code no longer names the live data pointer "
            f"({LIVE_POINTER_URL}) in {', '.join(missing_pointer)}; update release_archive.py "
            "so archived copies load their own release."
        )
    leftovers = [
        f"{name}: {match.group(0)!r}"
        for name, text in rewritten.items()
        for pattern in ((HTML_LEFTOVER_RE, SCRIPT_LEFTOVER_RE) if name.endswith(".html") else (SCRIPT_LEFTOVER_RE,))
        for match in pattern.finditer(BASE_TAG_RE.sub("", text))
    ]
    leftovers.extend(f"{name}: live data pointer" for name, text in rewritten.items() if "browser/active.json" in text)
    if leftovers:
        raise ValueError("The archived site still refers to the live site: " + "; ".join(leftovers[:10]))

    head_markup = archive_head_markup(slug=slug, pointer_path=pointer_path)
    banner_markup = archive_banner_markup(
        release_id=release_id, published_at=published_at, paper_total=paper_total
    )
    for name, text in rewritten.items():
        if name.endswith(".html"):
            text = add_archive_markup(text, head_markup=head_markup, banner_markup=banner_markup)
        (destination / name).write_text(text, encoding="utf-8")
    return tuple(files)


def git_output(arguments: list[str], cwd: Path) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def source_tree_state(source_root: Path) -> tuple[str, bool | None]:
    """Return the commit and whether the site files differ from it."""
    try:
        commit = git_output(["rev-parse", "HEAD"], source_root)
        status = git_output(
            ["status", "--porcelain", "--", *SNAPSHOT_ROOTS, "release-metadata.json", "scripts"],
            source_root,
        )
    except (OSError, subprocess.CalledProcessError):
        return "", None
    return commit, bool(status)


def export_git_tree(ref: str, destination: Path, repository: Path = ROOT) -> str:
    """Write the files of ``ref`` to ``destination`` and return its commit."""
    commit = git_output(["rev-parse", "--verify", f"{ref}^{{commit}}"], repository)
    destination.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(
        ["git", "archive", "--format=tar", commit], cwd=repository, check=True, capture_output=True
    )
    subprocess.run(["tar", "-x", "-C", str(destination)], input=archive.stdout, check=True)
    return commit


def build_site(source_root: Path, destination: Path) -> Path:
    environment = dict(os.environ)
    environment["DIST_DIR"] = str(destination)
    subprocess.run(
        ["bash", str(source_root / "scripts" / "build_site.sh")],
        cwd=source_root,
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return destination


def read_release_metadata(source_root: Path | None) -> dict:
    if source_root is None:
        return {}
    path = source_root / "release-metadata.json"
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def build_site_snapshot(
    *,
    work_dir: Path,
    slug: str,
    browser_prefix: str,
    data_origin: str,
    release_id: str,
    published_at: str,
    paper_total: int | None,
    site_source_root: Path | None = None,
    site_build_dir: Path | None = None,
    commit: str = "",
    tree_dirty: bool | None = None,
) -> SiteSnapshot:
    """Build (or reuse) the static site and prepare its archived copy."""
    if site_build_dir is None:
        if site_source_root is None:
            raise ValueError("A site snapshot needs a source tree or a built site")
        site_build_dir = build_site(site_source_root, work_dir / "built_site")
    destination = work_dir / "archived_site"
    files = prepare_site_snapshot(
        built_site=site_build_dir,
        destination=destination,
        slug=slug,
        browser_prefix=browser_prefix,
        data_origin=data_origin,
        release_id=release_id,
        published_at=published_at,
        paper_total=paper_total,
    )
    return SiteSnapshot(
        directory=destination,
        files=files,
        commit=commit,
        tree_dirty=tree_dirty,
        tree_sha256=tree_sha256(destination, files),
    )


def archive_metadata(
    *,
    slug: str,
    browser_prefix: str,
    site: SiteSnapshot | None,
    release_metadata: dict,
    paper_counts: dict,
    finding_count: int | None,
) -> dict:
    prefix = archive_prefix(browser_prefix, slug)
    return {
        "slug": slug,
        "pointer_key": f"{prefix}/{ARCHIVE_POINTER_NAME}",
        "site_entry_key": f"{prefix}/index.html" if site is not None else "",
        "site_commit": site.commit if site is not None else "",
        "site_tree_dirty": site.tree_dirty if site is not None else None,
        "site_tree_sha256": site.tree_sha256 if site is not None else "",
        "site_version": str(release_metadata.get("version") or ""),
        "literature_updated": str(release_metadata.get("literature_updated") or ""),
        "paper_counts": paper_counts,
        "finding_count": finding_count,
    }


def manifest_paper_counts(manifest: dict) -> tuple[dict, int | None]:
    counts = ((manifest.get("summary_stats") or {}).get("paper_counts") or {})
    selected = {
        key: counts[key]
        for key in ("total", "primary_studies", "reviews", "meta_analyses")
        if isinstance(counts.get(key), int)
    }
    row_count = manifest.get("row_count")
    return selected, row_count if isinstance(row_count, int) else None


# ---------------------------------------------------------------------------
# Uploads


def site_content_type(path: Path) -> str:
    return {
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json",
    }.get(path.suffix) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def upload_site_snapshot(
    store: ObjectStore,
    snapshot: SiteSnapshot,
    *,
    browser_prefix: str,
    slug: str,
    replace: bool = False,
) -> dict[str, int]:
    prefix = archive_prefix(browser_prefix, slug)
    counts = {"uploaded": 0, "existing": 0}
    for name in snapshot.files:
        path = snapshot.directory / name
        key = f"{prefix}/{name}"
        digest = sha256_file(path)
        size = path.stat().st_size
        existing = store.head(key)
        if existing is not None and existing.size == size and existing.metadata.get("sha256") == digest:
            counts["existing"] += 1
            continue
        if existing is not None and not replace:
            raise ArchiveConflict(f"An archived site file differs from this snapshot: {key}")
        store.upload_file(
            key,
            path,
            sha256=digest,
            content_type=site_content_type(path),
            cache_control=ARCHIVE_CACHE_CONTROL,
        )
        uploaded = store.head(key)
        if uploaded is None or uploaded.size != size or uploaded.metadata.get("sha256") != digest:
            raise RuntimeError(f"Archived site file failed verification: {key}")
        counts["uploaded"] += 1
    return counts


def write_archive_pointer(store: ObjectStore, key: str, data: bytes, *, replace: bool = False) -> str:
    """Store a release's frozen data pointer; an existing pointer must match."""
    if store.head(key) is not None:
        if store.get_bytes(key) == data:
            return "existing"
        if not replace:
            raise ArchiveConflict(f"An archived data pointer differs from this release: {key}")
    store.put_bytes(
        key,
        data,
        sha256=sha256_bytes(data),
        content_type="application/json",
        cache_control=ARCHIVE_CACHE_CONTROL,
    )
    if store.get_bytes(key) != data:
        raise RuntimeError(f"Archived data pointer failed read-after-write verification: {key}")
    return "uploaded"


def read_existing_archive_pointer(store: ObjectStore, browser_prefix: str, slug: str) -> dict | None:
    key = f"{archive_prefix(browser_prefix, slug)}/{ARCHIVE_POINTER_NAME}"
    if store.head(key) is None:
        return None
    value = json.loads(store.get_bytes(key))
    return value if isinstance(value, dict) else None


# ---------------------------------------------------------------------------
# Command line: archive the live release, or list the archive


def live_pointer(store: ObjectStore, browser_prefix: str) -> dict | None:
    key = f"{browser_prefix.strip('/')}/active.json"
    if store.head(key) is None:
        return None
    value = json.loads(store.get_bytes(key))
    if not isinstance(value, dict):
        raise ValueError(f"The live browser pointer is not a JSON object: {key}")
    return value


def live_release_is_archived(live: dict, index: dict) -> bool:
    """Whether the live release has an archived site copy."""
    if (live.get("archive") or {}).get("site_entry_key"):
        return True
    entry = find_entry(index["releases"], str(live.get("release_id") or "").strip())
    return bool((entry or {}).get("site_entry_key"))


def unarchived_live_release_message(release_id: str) -> str:
    return (
        f"The live release {release_id} has no archived copy, so replacing it would leave "
        "it unviewable. Archive it first with `python3 pipeline/publish/release_archive.py "
        "--archive-live --site-ref <git ref of the site that displays it> --execute`, or "
        "publish with --allow-unarchived-outgoing to replace it without an archived copy."
    )


def local_counts_for_release(release_id: str) -> tuple[dict, int | None]:
    """Paper and finding counts from the local payload manifest, if it is this release."""
    pointer_path = ROOT / "data" / "processed" / "graph_payload_active.json"
    if not pointer_path.is_file():
        return {}, None
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    if str(pointer.get("public_release_id") or "") != release_id:
        return {}, None
    manifest_path = ROOT / str(pointer.get("active_manifest") or "")
    if not manifest_path.is_file():
        return {}, None
    return manifest_paper_counts(json.loads(manifest_path.read_text(encoding="utf-8")))


def archive_live_release(
    *,
    store: ObjectStore,
    browser_prefix: str,
    site_ref: str,
    data_origin: str,
    execute: bool,
    output_dir: Path | None = None,
    replace_site: bool = False,
) -> dict:
    live = live_pointer(store, browser_prefix)
    if live is None:
        raise FileNotFoundError("No live browser release is published")
    release_id = str(live.get("release_id") or "").strip()
    published_at = str(live.get("published_at") or "").strip()
    if not release_id or not published_at:
        raise ValueError("The live browser pointer lacks release_id or published_at")
    index = read_archive_index(store, browser_prefix)
    existing = find_entry(index["releases"], release_id)
    if existing and existing.get("site_entry_key") and not replace_site:
        return {"status": "already_archived", "entry": existing}

    slug = str((existing or {}).get("slug") or "") or archive_slug(release_id, published_at)
    paper_counts, finding_count = local_counts_for_release(release_id)
    with tempfile.TemporaryDirectory(prefix="release-archive-") as tmp:
        work_dir = Path(tmp)
        source_root = work_dir / "source"
        commit = export_git_tree(site_ref, source_root)
        snapshot = build_site_snapshot(
            work_dir=work_dir,
            slug=slug,
            browser_prefix=browser_prefix,
            data_origin=data_origin,
            release_id=release_id,
            published_at=published_at,
            paper_total=paper_counts.get("total"),
            site_source_root=source_root,
            commit=commit,
            tree_dirty=False,
        )
        metadata = archive_metadata(
            slug=slug,
            browser_prefix=browser_prefix,
            site=snapshot,
            release_metadata=read_release_metadata(source_root),
            paper_counts=paper_counts,
            finding_count=finding_count,
        )
        frozen = {**live, "archive": metadata}
        frozen_bytes = canonical_json_bytes(frozen)
        site_bytes = sum((snapshot.directory / name).stat().st_size for name in snapshot.files)
        result: dict[str, Any] = {
            "status": "planned",
            "release_id": release_id,
            "slug": slug,
            "site_commit": commit,
            "site_files": len(snapshot.files),
            "site_bytes": site_bytes,
            "site_url": f"{SITE_ORIGIN}/{metadata['site_entry_key']}",
        }
        if output_dir is not None:
            shutil.copytree(snapshot.directory, output_dir / slug, dirs_exist_ok=True)
            (output_dir / slug / ARCHIVE_POINTER_NAME).write_bytes(frozen_bytes)
            result["output_dir"] = str(output_dir / slug)
        if not execute:
            return result
        result["site_upload"] = upload_site_snapshot(
            store, snapshot, browser_prefix=browser_prefix, slug=slug, replace=replace_site
        )
        result["pointer_upload"] = write_archive_pointer(
            store, metadata["pointer_key"], frozen_bytes, replace=replace_site
        )
        current = live_pointer(store, browser_prefix) or {}
        write_archive_index(
            store,
            browser_prefix,
            entries=upsert_entry(index["releases"], entry_from_pointer(frozen)),
            current_release_id=str(current.get("release_id") or release_id),
        )
        result["status"] = "archived"
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--archive-live", action="store_true", help="Archive the live release.")
    mode.add_argument("--list", action="store_true", help="Print the archived releases.")
    mode.add_argument(
        "--check-live",
        action="store_true",
        help="Exit with status 3 if the live release has no archived copy (run before publishing).",
    )
    parser.add_argument(
        "--site-ref",
        default="",
        help="Git commit or branch whose site displays the live release (for example origin/main).",
    )
    parser.add_argument("--execute", action="store_true", help="Upload. Without it, only build and report.")
    parser.add_argument("--output-dir", type=Path, help="Also write the archived copy here for inspection.")
    parser.add_argument("--replace-site", action="store_true", help="Replace an existing archived copy.")
    parser.add_argument("--browser-prefix", default=os.environ.get("PKG_R2_BROWSER_PREFIX", "browser"))
    parser.add_argument(
        "--data-origin", default=os.environ.get("PKG_PUBLIC_DATA_ORIGIN", DEFAULT_DATA_ORIGIN)
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from services.query_api.config import R2Settings, normalize_r2_prefix
    from services.query_api.r2_store import R2ObjectStore

    settings = R2Settings.from_env(required=True, env_prefix="PKG_R2", default_object_prefix="browser")
    assert settings is not None
    store = R2ObjectStore(settings)
    browser_prefix = normalize_r2_prefix(args.browser_prefix, variable_name="PKG_R2_BROWSER_PREFIX")
    if args.check_live:
        live = live_pointer(store, browser_prefix)
        if live is None or live_release_is_archived(live, read_archive_index(store, browser_prefix)):
            print("The live release has an archived copy (or no release is live).")
            return 0
        print(unarchived_live_release_message(str(live.get("release_id") or "")), file=sys.stderr)
        return 3
    if args.list:
        index = read_archive_index(store, browser_prefix)
        for entry in index["releases"]:
            marker = "current" if entry["release_id"] == index.get("current_release_id") else "       "
            site = f"{SITE_ORIGIN}/{entry['site_entry_key']}" if entry.get("site_entry_key") else "no site copy"
            total = (entry.get("paper_counts") or {}).get("total", "?")
            print(f"{marker}  {entry.get('published_at', '')[:10]}  {total} papers  {site}")
        return 0
    if not args.site_ref:
        raise SystemExit("--site-ref is required with --archive-live")
    result = archive_live_release(
        store=store,
        browser_prefix=browser_prefix,
        site_ref=args.site_ref,
        data_origin=args.data_origin,
        execute=args.execute,
        output_dir=args.output_dir.resolve() if args.output_dir else None,
        replace_site=args.replace_site,
    )
    print(json.dumps(result, indent=2, default=str))
    if result["status"] == "planned":
        print("Dry run: nothing was uploaded. Re-run with --execute to archive the live release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
