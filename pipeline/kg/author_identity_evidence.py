"""Provider evidence for author identities, cached across builds.

Two free sources supply identity evidence that does not depend on name
similarity:

- OpenAlex author profiles. OpenAlex first assigns a new work's authors to new
  single-work profiles and later merges them into the established profile. A
  single-profile request for a merged ID returns the surviving profile, so
  looking up each cached ID gives the current profile. Single-record requests
  are free; only the request rate is limited.
- ORCID public records. A record states the researcher's names and the works
  (DOIs) listed on it. A listed DOI with a compatible byline name is evidence
  that the authorship belongs to that ORCID; a byline name that matches none of
  the record's names, on a DOI the record does not list, is evidence that the
  ORCID was attached to the wrong author.

Crossref author ORCIDs are deliberately not used: they are sparse and
publisher-entered without verification, and both wrong ORCIDs found in the
8 Nov 2026 review came from Crossref deposits.

Both caches are shared across runs so that a build only queries IDs that are new
or older than the refresh interval. Each run records the evidence it used.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_DIR = ROOT / "data" / "processed" / "author_identity_sources"
OPENALEX_RESOLUTION_CACHE_NAME = "openalex_author_resolution.json"
ORCID_RECORD_CACHE_NAME = "orcid_records.json"
DEFAULT_MAX_AGE_DAYS = 60
EVIDENCE_CACHE_VERSION = "1.0"

ORCID_ID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
OPENALEX_AUTHOR_RE = re.compile(r"^A\d+$")

# Latin look-alike letters from other scripts that appear inside Latin-script
# bylines (e.g. "Νikolaos S. Τhomaidis", where Ν and Τ are Greek).
HOMOGLYPHS = str.maketrans(
    {
        "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
        "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
        "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
        "Р": "P", "С": "C", "Т": "T", "Х": "X", "а": "a", "е": "e", "о": "o",
        "р": "p", "с": "c", "х": "x", "у": "y", "ο": "o",
    }
)
FOLD_EXTRA = str.maketrans({"ı": "i"})
HYPHENS = str.maketrans({c: "-" for c in "‐‑‒–—−­"})
NON_LATIN_LETTER_RE = re.compile(r"[Ͱ-ϿЀ-ӿ֐-ۿ฀-๿぀-ヿ㐀-鿿가-힯]")
LATIN_LETTER_RE = re.compile(r"[A-Za-zÀ-ɏ]")
TITLE_RE = re.compile(
    r"^(?:(?:prof(?:essor)?|dr|mr|mrs|ms|sir|dame)\.?\s+)+|"
    r",?\s+(?:m\.?\s?d\.?|ph\.?\s?d\.?|pharm\.?\s?d\.?|msc|bsc|mph|frcp(?:c)?)\.?$",
    re.I,
)
NON_PERSON_PHRASE_RE = re.compile(
    r"(?i)^\(?(?:on behalf of|for the|the)\s|\d{3,}|\bid_orcid\b|"
    r"\b(?:study group|research group|working group|study investigators|collaborator group|"
    r"task force|working party|sub-project|réseau)\b"
)
NON_PERSON_WORD_RE = re.compile(
    r"(?i)\b(?:group|consortium|collaborat\w*|investigators|committee|society|association|"
    r"foundation|network|university|hospital|department|institute)\b"
)
NAME_PARTICLES = {"de", "da", "do", "dos", "das", "di", "del", "della", "van", "von", "der", "den", "la", "le", "du", "e", "y"}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _age_days(timestamp: str) -> float:
    try:
        then = dt.datetime.fromisoformat(timestamp)
    except (TypeError, ValueError):
        return float("inf")
    if then.tzinfo is None:
        then = then.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - then).total_seconds() / 86400


def openalex_short(value: object) -> str:
    text = str(value or "").strip().rstrip("/").rsplit("/", 1)[-1].upper()
    return text if OPENALEX_AUTHOR_RE.match(text) else ""


# --- names ---------------------------------------------------------------


def fold(value: object) -> str:
    """Comparison form: homoglyphs and hyphens unified, accents removed, casefolded."""
    text = unicodedata.normalize("NFKC", str(value or "")).translate(HOMOGLYPHS).translate(HYPHENS)
    text = unicodedata.normalize("NFKD", text.translate(FOLD_EXTRA))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("ł", "l").replace("Ł", "L").replace("ø", "o").replace("Ø", "O").replace("ß", "ss")
    return text.casefold()


def name_tokens(value: object) -> list[str]:
    """Ordered name tokens; "Surname, Given" is put back into given-first order."""
    text = fold(value)
    if text.count(",") == 1:
        surname, given = (part.strip() for part in text.split(","))
        if surname and given:
            text = f"{given} {surname}"
    text = TITLE_RE.sub(" ", text)
    tokens: list[str] = []
    for token in re.findall(r"[^\W\d_]+(?:-[^\W\d_]+)*", text):
        tokens.extend(part for part in token.split("-") if part)
    return tokens


def _surname_and_given(tokens: list[str]) -> tuple[set[str], list[str]]:
    if not tokens:
        return set(), []
    # Compound surnames ("Garcia Romeu", "de Souza Queiroz") are matched through
    # any shared surname token of two or more letters.
    return {tokens[-1]}, tokens[:-1]


def names_compatible(left: object, right: object) -> bool:
    """True when two bylines can name the same person.

    Requires a shared surname token and compatible first given-name initials.
    Also accepts swapped given/family order ("Su Min" / "Min Su"). This is a
    consistency check used with provider evidence, never a merge rule.
    """
    a, b = name_tokens(left), name_tokens(right)
    if not a or not b:
        return False
    if sorted(a) == sorted(b):
        return True
    long_a = {t for t in a if len(t) >= 2}
    long_b = {t for t in b if len(t) >= 2}
    for x, y in ((a, b), (a[::-1], b), (a, b[::-1])):
        surname_x, given_x = _surname_and_given(x)
        surname_y, given_y = _surname_and_given(y)
        shared_surname = bool((surname_x & long_b) or (surname_y & long_a))
        if not shared_surname:
            continue
        if not given_x or not given_y:
            return True
        if given_x[0][0] == given_y[0][0]:
            return True
        # Bylines that list a second given name first ("H. Valerie Curran" /
        # "Valerie H. Curran") share an initial in another position.
        if {g[0] for g in given_x} & {g[0] for g in given_y}:
            return True
    return False


def share_surname(left: object, right: object) -> bool:
    """True when any name token of two or more letters is shared."""
    a = {t for t in name_tokens(left) if len(t) >= 2}
    b = {t for t in name_tokens(right) if len(t) >= 2}
    return bool(a & b)


def bylines_consistent(left: object, right: object) -> bool:
    """Stricter than names_compatible: every given-name initial present in both
    bylines agrees in order ("E.N Andrade" and "E.O Andrade" do not)."""
    if not names_compatible(left, right):
        return False
    a, b = name_tokens(left), name_tokens(right)
    if sorted(a) == sorted(b):
        return True
    given_a, given_b = a[:-1], b[:-1]
    return all(x[0] == y[0] for x, y in zip(given_a, given_b))


def has_latin_name(value: object) -> bool:
    return bool(LATIN_LETTER_RE.search(str(value or ""))) and not NON_LATIN_LETTER_RE.search(
        str(value or "").translate(HOMOGLYPHS)
    )


def is_non_person_byline(value: object) -> bool:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not text:
        return False
    if NON_PERSON_PHRASE_RE.search(text):
        return True
    # A group word alone is not enough: "Ann Network" can be a person.
    return bool(NON_PERSON_WORD_RE.search(text)) and len(text.split()) >= 3


ORCID_IN_NAME_RE = re.compile(r"(?i)\b(?:id_orcid|orcid)?[:\s]*(?:https?://orcid\.org/)?\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b")


def clean_person_name(value: object) -> str:
    """Display form of a person's byline; the source string is kept elsewhere."""
    text = unicodedata.normalize("NFC", str(value or "")).strip()
    text = ORCID_IN_NAME_RE.sub(" ", text).strip()
    # OpenAlex display names sometimes carry a record number: "Xiuli Wang (151314)"
    text = re.sub(r"\s*\(\d+\)$", "", text)
    if not text:
        return ""
    if has_latin_name(text.translate(HOMOGLYPHS)) and NON_LATIN_LETTER_RE.search(text):
        text = text.translate(HOMOGLYPHS)
    text = text.translate(HYPHENS)
    text = unicodedata.normalize("NFC", text.replace("ı́", "í").replace("ı́", "í"))
    if text.count(",") == 1:
        surname, given = (part.strip() for part in text.split(","))
        if surname and given and not re.search(r"\b(?:jr|sr|ii|iii|iv)\.?$", given, re.I):
            text = f"{given} {surname}"
    previous = None
    while previous != text:
        previous = text
        text = TITLE_RE.sub("", text).strip(" ,")
    # "DavidE. Nichols" -> "David E. Nichols"
    text = re.sub(r"(?<=[a-zß-ÿ])(?=[A-Z]\.)", " ", text)
    # Stray single capital after a full surname ("Jordi Riba A", "Maurizio Fava M. D")
    text = re.sub(r"(?<=[a-zß-ÿ]{2})(?:\s+[A-Z]\.?)+$", "", text)
    if text.isupper() and len(re.sub(r"[^A-Z]", "", text)) > 3:
        text = " ".join(
            part if re.fullmatch(r"(?:[A-Z]\.)+|[A-Z]", part)
            else part.lower() if index and part.lower() in NAME_PARTICLES
            else part.capitalize()
            for index, part in enumerate(text.split())
        )
        text = re.sub(r"-(\w)", lambda m: "-" + m.group(1).upper(), text)
    return re.sub(r"\s+", " ", text).strip()


def display_name_score(value: str) -> tuple:
    """Sort key: higher is a better display name for a person."""
    tokens = name_tokens(value)
    given = tokens[:-1]
    full_given = any(len(t) >= 2 for t in given)
    return (
        has_latin_name(value),
        "�" not in value,
        full_given,
        not value.isupper(),
        len(tokens),
        len(value),
    )


# --- HTTP -----------------------------------------------------------------


class RateLimiter:
    def __init__(self, rps: float):
        self.interval = 1.0 / rps if rps > 0 else 0.0
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = self.next_at - now
            self.next_at = max(now, self.next_at) + self.interval
        if delay > 0:
            time.sleep(delay)


def get_json(
    url: str, *, limiter: RateLimiter, headers: dict[str, str], timeout: float = 30.0, retries: int = 5
) -> tuple[str, Any]:
    """Return ("ok", payload), ("not_found", None) or ("error", message)."""
    last_error = ""
    for attempt in range(retries):
        limiter.wait()
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return "ok", json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410):
                return "not_found", None
            last_error = f"HTTP {exc.code}"
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After", "")
                time.sleep(float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 2.0 * (attempt + 1))
                continue
            if exc.code < 500:
                return "error", last_error
        except Exception as exc:  # pragma: no cover - network path
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(1.5 * (attempt + 1))
    return "error", last_error


# --- caches ---------------------------------------------------------------


def read_cache(path: Path) -> dict[str, Any]:
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("entries"), dict):
            return data
    return {"version": EVIDENCE_CACHE_VERSION, "entries": {}}


def write_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cache, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def keys_to_query(
    keys: Iterable[str], entries: dict[str, Any], *, max_age_days: float, refresh: bool = False
) -> list[str]:
    todo = []
    for key in sorted(set(keys)):
        entry = entries.get(key)
        if refresh or not isinstance(entry, dict) or entry.get("status") == "error":
            todo.append(key)
        elif _age_days(entry.get("queried_at", "")) > max_age_days:
            todo.append(key)
    return todo


def _run_lookups(
    keys: list[str],
    fetch: Callable[[str], dict[str, Any]],
    cache: dict[str, Any],
    cache_path: Path,
    *,
    workers: int,
    label: str,
    checkpoint_every: int = 1000,
) -> None:
    entries = cache["entries"]
    if not keys:
        return
    print(f"{label}: querying {len(keys)} records", flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for key, entry in zip(keys, pool.map(fetch, keys)):
            entries[key] = entry
            done += 1
            if checkpoint_every and done % checkpoint_every == 0:
                write_cache(cache_path, cache)
                print(f"{label}: {done}/{len(keys)}", flush=True)
    write_cache(cache_path, cache)


def resolve_openalex_profiles(
    author_ids: Iterable[str],
    cache_path: Path,
    *,
    api_key: str = "",
    rps: float | None = None,
    max_age_days: float = DEFAULT_MAX_AGE_DAYS,
    offline: bool = False,
    refresh: bool = False,
) -> dict[str, Any]:
    """Map each OpenAlex author ID to its current (surviving) profile."""
    cache = read_cache(cache_path)
    ids = {openalex_short(value) for value in author_ids} - {""}
    if not offline:
        # Single-profile requests are free; 10 req/s without a key, 30 with one.
        rate = rps or (20.0 if api_key else 8.0)
        limiter = RateLimiter(rate)
        headers = {"Accept": "application/json", "User-Agent": "psychedelics-kg-author-identity/1.0"}

        def fetch(short_id: str) -> dict[str, Any]:
            params = {"select": "id,display_name,orcid,works_count"}
            if api_key:
                params["api_key"] = api_key
            url = f"https://api.openalex.org/authors/{short_id}?" + urllib.parse.urlencode(params)
            status, payload = get_json(url, limiter=limiter, headers=headers)
            entry: dict[str, Any] = {"status": status, "queried_at": now_utc()}
            if status == "ok":
                entry.update(
                    {
                        "resolved_id": openalex_short(payload.get("id", "")),
                        "orcid": str(payload.get("orcid") or "").rstrip("/").rsplit("/", 1)[-1],
                        "display_name": str(payload.get("display_name") or ""),
                        "works_count": int(payload.get("works_count") or 0),
                    }
                )
            elif status == "error":
                entry["error"] = payload
            return entry

        todo = keys_to_query(ids, cache["entries"], max_age_days=max_age_days, refresh=refresh)
        # Requests take ~1 s, so the worker count, not the limiter, sets the pace.
        _run_lookups(todo, fetch, cache, cache_path, workers=int(rate * 1.5), label="OpenAlex author profiles")
    return {key: cache["entries"][key] for key in ids if key in cache["entries"]}


def parse_orcid_record(payload: dict[str, Any]) -> dict[str, Any]:
    person = payload.get("person") or {}
    name = person.get("name") or {}

    def value(node: Any) -> str:
        return str((node or {}).get("value") or "").strip() if isinstance(node, dict) else ""

    other_names = [
        str(item.get("content") or "").strip()
        for item in ((person.get("other-names") or {}).get("other-name") or [])
        if isinstance(item, dict) and str(item.get("content") or "").strip()
    ]
    dois: set[str] = set()
    groups = (((payload.get("activities-summary") or {}).get("works") or {}).get("group") or [])
    for group in groups:
        for ext in ((group.get("external-ids") or {}).get("external-id") or []):
            if str(ext.get("external-id-type", "")).lower() == "doi":
                doi = str(ext.get("external-id-value") or "").strip().lower()
                doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", doi)
                if doi:
                    dois.add(doi)
    return {
        "given_names": value(name.get("given-names")),
        "family_name": value(name.get("family-name")),
        "credit_name": value(name.get("credit-name")),
        "other_names": sorted(set(other_names)),
        "dois": sorted(dois),
        "works_listed": len(groups),
    }


def orcid_record_names(record: dict[str, Any]) -> list[str]:
    names = []
    full = " ".join(p for p in (record.get("given_names", ""), record.get("family_name", "")) if p)
    for candidate in [full, record.get("credit_name", ""), *record.get("other_names", [])]:
        if candidate and candidate not in names:
            names.append(candidate)
    return names


def fetch_orcid_records(
    orcids: Iterable[str],
    cache_path: Path,
    *,
    rps: float = 12.0,
    max_age_days: float = DEFAULT_MAX_AGE_DAYS,
    offline: bool = False,
    refresh: bool = False,
) -> dict[str, Any]:
    """Names and listed DOIs from ORCID public records (public API limit 24 req/s)."""
    cache = read_cache(cache_path)
    ids = {str(value).strip().upper() for value in orcids if ORCID_ID_RE.match(str(value).strip().upper())}
    if not offline:
        limiter = RateLimiter(rps)
        headers = {"Accept": "application/json", "User-Agent": "psychedelics-kg-author-identity/1.0"}

        def fetch(orcid: str) -> dict[str, Any]:
            status, payload = get_json(f"https://pub.orcid.org/v3.0/{orcid}/record", limiter=limiter, headers=headers)
            entry: dict[str, Any] = {"status": status, "queried_at": now_utc()}
            if status == "ok":
                entry.update(parse_orcid_record(payload))
            elif status == "error":
                entry["error"] = payload
            return entry

        todo = keys_to_query(ids, cache["entries"], max_age_days=max_age_days, refresh=refresh)
        _run_lookups(todo, fetch, cache, cache_path, workers=int(rps * 1.5), label="ORCID records")
    return {key: cache["entries"][key] for key in ids if key in cache["entries"]}


class AuthorEvidence:
    """Live, cached provider evidence used by one author-table build."""

    def __init__(
        self,
        evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
        *,
        openalex_api_key: str = "",
        openalex_rps: float | None = None,
        orcid_rps: float = 12.0,
        max_age_days: float = DEFAULT_MAX_AGE_DAYS,
        offline: bool = False,
        refresh: bool = False,
    ):
        self.evidence_dir = Path(evidence_dir)
        self.openalex_api_key = openalex_api_key
        self.openalex_rps = openalex_rps
        self.orcid_rps = orcid_rps
        self.max_age_days = max_age_days
        self.offline = offline
        self.refresh = refresh

    def openalex_profiles(self, author_ids: Iterable[str]) -> dict[str, Any]:
        return resolve_openalex_profiles(
            author_ids,
            self.evidence_dir / OPENALEX_RESOLUTION_CACHE_NAME,
            api_key=self.openalex_api_key,
            rps=self.openalex_rps,
            max_age_days=self.max_age_days,
            offline=self.offline,
            refresh=self.refresh,
        )

    def orcid_records(self, orcids: Iterable[str]) -> dict[str, Any]:
        return fetch_orcid_records(
            orcids,
            self.evidence_dir / ORCID_RECORD_CACHE_NAME,
            rps=self.orcid_rps,
            max_age_days=self.max_age_days,
            offline=self.offline,
            refresh=self.refresh,
        )

    def describe(self) -> dict[str, Any]:
        return {
            "evidence_dir": str(self.evidence_dir),
            "offline": self.offline,
            "max_age_days": self.max_age_days,
        }


class StaticAuthorEvidence:
    """Fixed evidence for tests and for builds that must not query providers."""

    def __init__(self, profiles: dict[str, Any] | None = None, records: dict[str, Any] | None = None):
        self.profiles = profiles or {}
        self.records = records or {}

    def openalex_profiles(self, author_ids: Iterable[str]) -> dict[str, Any]:
        ids = {openalex_short(value) for value in author_ids}
        return {key: value for key, value in self.profiles.items() if key in ids}

    def orcid_records(self, orcids: Iterable[str]) -> dict[str, Any]:
        wanted = set(orcids)
        return {key: value for key, value in self.records.items() if key in wanted}

    def describe(self) -> dict[str, Any]:
        return {"evidence_dir": "", "offline": True, "static": True}
