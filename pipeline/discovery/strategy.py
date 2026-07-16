"""Build auditable provider-specific search plans from versioned concepts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, Sequence

from pipeline.review.deterministic_prescreen_rules import (
    CLINICAL_OUTCOME_SYNONYMS,
    COMPOUND_SYNONYMS,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STRATEGY_PATH = Path(__file__).with_name("search_strategy.v3.json")
DEFAULT_CONFIG_PATH = ROOT / "pipeline" / "config.example.yaml"
DEFAULT_HISTORY_PATH = ROOT / "data" / "processed" / "discovery" / "search_history.json"
SUPPORTED_PROVIDERS = ("pubmed", "openalex")
SUPPORTED_DATASETS = ("mechanistic", "disorder", "general")
SUPPORTED_LAYERS = ("core", "scope", "targeted_pairs", "scope_delta")
AMBIGUOUS_ACRONYMS = {
    "dmt",
    "dob",
    "doc",
    "doet",
    "doi",
    "dom",
    "dipt",
    "dpt",
    "lsa",
    "mda",
    "stp",
    "tma",
}


@dataclass(frozen=True)
class SearchDefinition:
    search_id: str
    dataset: str
    provider: str
    layer: str
    search_type: str
    module_id: str
    query: str
    compound: str = ""
    entity: str = ""
    entity_type: str = ""
    search_surface: str = "fulltext"


@dataclass(frozen=True)
class SearchExecution:
    execution_id: str
    search_id: str
    dataset: str
    provider: str
    layer: str
    search_type: str
    module_id: str
    query: str
    compound: str
    entity: str
    entity_type: str
    search_surface: str
    date_basis: str
    start_date: str
    end_date: str
    protocol_id: str
    strategy_hash: str
    scope_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def slug(value: object, max_length: int = 72) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", clean(value).lower()).strip("_")
    return text[:max_length] or "search"


def stable_hash(payload: object, length: int = 16) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def load_json(path: Path, default: object | None = None) -> object:
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def load_strategy(path: Path = DEFAULT_STRATEGY_PATH) -> dict:
    payload = load_json(Path(path), {})
    if not isinstance(payload, dict):
        raise ValueError(f"Search strategy must be a JSON object: {path}")
    required = {"schema_version", "protocol_id", "providers", "modules"}
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"Search strategy is missing required fields: {', '.join(missing)}")
    return payload


def parse_validation_allowlists(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, list[str]]:
    """Read the nested validation allowlists without requiring a YAML package."""

    wanted = {
        "allowed_compounds",
        "allowed_targets",
        "allowed_brain_regions_and_networks",
        "allowed_cognitive_behavioral_tasks",
        "allowed_disorders",
    }
    out = {name: [] for name in wanted}
    in_validation = False
    current = ""
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0:
            in_validation = stripped == "validation:"
            current = ""
            continue
        if not in_validation:
            continue
        if indent == 2 and stripped.endswith(":"):
            candidate = stripped[:-1]
            current = candidate if candidate in wanted else ""
            continue
        if current and indent >= 4 and stripped.startswith("- "):
            value = stripped[2:].strip().strip('"').strip("'")
            if value and value not in out[current]:
                out[current].append(value)
    return out


def scope_hash(scope: dict[str, list[str]]) -> str:
    normalized = {
        key: sorted({normalized_key(value) for value in values if clean(value)})
        for key, values in sorted(scope.items())
    }
    return stable_hash(normalized, 24)


def _synonyms(label: str, mapping: dict[str, set[str]]) -> list[str]:
    key = normalized_key(label).replace(" ", "-")
    candidates: set[str] = {clean(label)}
    for map_key, values in mapping.items():
        if normalized_key(map_key) == normalized_key(label) or normalized_key(map_key).replace(" ", "-") == key:
            candidates.update(clean(value) for value in values)
    # Never rely on bare ambiguous acronyms. Their full chemical names remain.
    safe = [value for value in candidates if value and value.lower() not in AMBIGUOUS_ACRONYMS]
    if safe:
        return sorted(set(safe), key=lambda value: (len(value), value.lower()))
    return [clean(label)]


def compound_terms(label: str) -> list[str]:
    return _synonyms(label, COMPOUND_SYNONYMS)


def openalex_compound_terms(label: str) -> list[str]:
    """Return high-specificity aliases that are safe for OpenAlex text search.

    OpenAlex tokenizes punctuation and short code-like phrases aggressively.
    Variants such as ``2c c`` or ``4 ho met`` therefore retrieve large numbers
    of unrelated records. Keep the canonical label and descriptive aliases,
    but collapse punctuation-only variants onto the canonical form and reject
    whitespace-separated chemical codes.
    """

    canonical = clean(label)
    canonical_key = normalized_key(canonical)
    source_aliases = compound_terms(label)
    values = [] if canonical.lower() in AMBIGUOUS_ACRONYMS else [canonical]
    for alias in source_aliases:
        value = clean(alias)
        if not value or value.lower() == canonical.lower():
            continue
        if normalized_key(value) == canonical_key:
            continue
        tokens = re.findall(r"[A-Za-z0-9]+", value)
        if " " in value and len(tokens) >= 2 and all(len(token) <= 4 for token in tokens):
            continue
        values.append(value)
    return _dedupe(values)


def openalex_compound_identity_query(strategy: dict, label: str) -> str:
    """Build a high-specificity OpenAlex identity query for one compound."""

    contexts = strategy.get("openalex_ambiguous_compound_contexts", {})
    context_terms = contexts.get(label, []) if isinstance(contexts, dict) else []
    terms = openalex_compound_terms(label)
    if not context_terms:
        return openalex_block(terms)
    canonical_key = normalized_key(label)
    safe_block = openalex_block(
        term for term in terms if normalized_key(term) != canonical_key
    )
    disambiguated = f"{_quote_phrase(label)} AND {openalex_block(context_terms)}"
    return f"({safe_block} OR ({disambiguated}))" if safe_block else f"({disambiguated})"


def openalex_core_compound_terms(strategy: dict, label: str) -> list[str]:
    """Exclude labels requiring contextual disambiguation from broad core blocks."""

    contexts = strategy.get("openalex_ambiguous_compound_contexts", {})
    context_terms = contexts.get(label, []) if isinstance(contexts, dict) else []
    terms = openalex_compound_terms(label)
    if not context_terms:
        return terms
    canonical_key = normalized_key(label)
    return [term for term in terms if normalized_key(term) != canonical_key]


def disorder_terms(label: str) -> list[str]:
    return _synonyms(label, CLINICAL_OUTCOME_SYNONYMS)


def entity_terms(label: str, entity_type: str) -> list[str]:
    if entity_type == "indication":
        return disorder_terms(label)
    raw = clean(label)
    terms = {raw}
    parenthetical = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", raw)
    if parenthetical:
        terms.add(parenthetical.group(1).strip())
        terms.add(parenthetical.group(2).strip())
    terms.add(raw.replace(" receptor", "")) if raw.lower().endswith(" receptor") else None
    return sorted((term for term in terms if term), key=lambda value: (len(value), value.lower()))


def _quote_phrase(term: str) -> str:
    escaped = clean(term).replace('"', "")
    return f'"{escaped}"' if re.search(r"[^A-Za-z0-9_]", escaped) else escaped


def _pubmed_term(term: str, field: str = "Text Word") -> str:
    return f'{_quote_phrase(term)}[{field}]'


def pubmed_block(
    terms: Iterable[str],
    *,
    controlled_terms: Iterable[str] = (),
    substance_terms: Iterable[str] = (),
) -> str:
    values = [_pubmed_term(term) for term in _dedupe(terms)]
    values.extend(_pubmed_term(term, "MeSH Terms") for term in _dedupe(controlled_terms))
    values.extend(_pubmed_term(term, "Supplementary Concept") for term in _dedupe(substance_terms))
    values = _dedupe(values)
    if not values:
        return ""
    return values[0] if len(values) == 1 else "(" + " OR ".join(values) + ")"


def openalex_block(terms: Iterable[str]) -> str:
    # Commas delimit OpenAlex filters after URL decoding. Remove punctuation
    # commas from chemical names so field-scoped pair queries cannot be parsed
    # as accidental extra filters.
    values = [_quote_phrase(term.replace(",", " ")) for term in _dedupe(terms)]
    if not values:
        return ""
    return values[0] if len(values) == 1 else "(" + " OR ".join(values) + ")"


def _dedupe(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = clean(raw)
        marker = value.lower()
        if not value or marker in seen:
            continue
        seen.add(marker)
        out.append(value)
    return out


def _chunk_terms(values: Sequence[str], max_chars: int = 1750, max_terms: int = 45) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    current_size = 0
    for value in _dedupe(values):
        addition = len(value) + 8
        if current and (len(current) >= max_terms or current_size + addition > max_chars):
            chunks.append(current)
            current = []
            current_size = 0
        current.append(value)
        current_size += addition
    if current:
        chunks.append(current)
    return chunks


def _make_query(
    provider: str,
    left_terms: Sequence[str],
    right_terms: Sequence[str],
    *,
    left_controlled: Sequence[str] = (),
    right_controlled: Sequence[str] = (),
    left_substances: Sequence[str] = (),
) -> str:
    if provider == "pubmed":
        left = pubmed_block(
            left_terms,
            controlled_terms=left_controlled,
            substance_terms=left_substances,
        )
        right = pubmed_block(right_terms, controlled_terms=right_controlled)
    elif provider == "openalex":
        left = openalex_block(left_terms)
        right = openalex_block(right_terms)
    else:
        raise ValueError(f"Unsupported provider: {provider}")
    return " AND ".join(block for block in (left, right) if block)


def _bounded_openalex_term_pairs(
    left_terms: Sequence[str],
    right_terms: Sequence[str],
    *,
    max_query_chars: int,
) -> list[tuple[list[str], list[str]]]:
    """Partition a Boolean cross-product without changing its logical coverage."""

    pending: list[tuple[list[str], list[str]]] = [(_dedupe(left_terms), _dedupe(right_terms))]
    bounded: list[tuple[list[str], list[str]]] = []
    while pending:
        left, right = pending.pop(0)
        query = _make_query("openalex", left, right)
        if len(query) <= max_query_chars:
            bounded.append((left, right))
            continue

        left_size = len(openalex_block(left))
        right_size = len(openalex_block(right))
        splittable = []
        if len(left) > 1:
            splittable.append((left_size, "left"))
        if len(right) > 1:
            splittable.append((right_size, "right"))
        if not splittable:
            raise ValueError(
                f"OpenAlex query exceeds {max_query_chars} characters and cannot be split: {query[:160]}"
            )

        _size, side = max(splittable)
        if side == "left":
            midpoint = len(left) // 2
            pending.insert(0, (left[midpoint:], right))
            pending.insert(0, (left[:midpoint], right))
        else:
            midpoint = len(right) // 2
            pending.insert(0, (left, right[midpoint:]))
            pending.insert(0, (left, right[:midpoint]))
    return bounded


def _definition(
    *,
    provider: str,
    dataset: str,
    layer: str,
    search_type: str,
    module_id: str,
    query: str,
    compound: str = "",
    entity: str = "",
    entity_type: str = "",
    search_surface: str = "fulltext",
) -> SearchDefinition:
    identity = {
        "provider": provider,
        "dataset": dataset,
        "layer": layer,
        "search_type": search_type,
        "module_id": module_id,
        "compound": compound,
        "entity": entity,
        "query": query,
        "search_surface": search_surface,
    }
    label = "_".join(filter(None, (dataset, layer, module_id, slug(compound), slug(entity))))
    search_id = f"{slug(label)}_{provider}_{stable_hash(identity, 12)}"
    return SearchDefinition(
        search_id=search_id,
        dataset=dataset,
        provider=provider,
        layer=layer,
        search_type=search_type,
        module_id=module_id,
        query=query,
        compound=compound,
        entity=entity,
        entity_type=entity_type,
        search_surface=search_surface,
    )


def _core_definitions(strategy: dict, scope: dict[str, list[str]], providers: Sequence[str]) -> list[SearchDefinition]:
    definitions: list[SearchDefinition] = []
    compounds = scope.get("allowed_compounds", [])
    pubmed_compound_terms = list(strategy.get("compound_class_terms", []))
    openalex_compound_aliases = list(strategy.get("compound_class_terms", []))
    for compound in compounds:
        pubmed_compound_terms.extend(compound_terms(compound))
        openalex_compound_aliases.extend(openalex_core_compound_terms(strategy, compound))
    pubmed_compound_chunks = _chunk_terms(pubmed_compound_terms)
    class_controlled = list(strategy.get("compound_class_controlled_terms", []))
    for module in strategy.get("modules", []):
        if not isinstance(module, dict):
            continue
        dataset = clean(module.get("dataset"))
        module_id = clean(module.get("module_id"))
        right_terms = list(module.get("terms", []))
        if module.get("use_allowed_disorders"):
            for disorder in scope.get("allowed_disorders", []):
                right_terms.extend(disorder_terms(disorder))
        right_terms = _dedupe(right_terms)
        for provider in providers:
            search_surface = (
                clean(strategy["providers"]["openalex"].get("core_search_surface", "fulltext"))
                if provider == "openalex"
                else "text_word_and_controlled_vocabulary"
            )
            if provider == "openalex":
                max_chars = int(strategy["providers"]["openalex"].get("max_search_query_chars", 1400))
                term_pairs = _bounded_openalex_term_pairs(
                    openalex_compound_aliases,
                    right_terms,
                    max_query_chars=max_chars,
                )
            else:
                term_pairs = [(chunk, right_terms) for chunk in pubmed_compound_chunks]
            for chunk_index, (left_terms, bounded_right_terms) in enumerate(term_pairs, start=1):
                query = _make_query(
                    provider,
                    left_terms,
                    bounded_right_terms,
                    left_controlled=class_controlled,
                    right_controlled=list(module.get("controlled_terms", [])),
                )
                definitions.append(
                    _definition(
                        provider=provider,
                        dataset=dataset,
                        layer="core",
                        search_type="two_block_core",
                        module_id=f"{module_id}_compound_chunk_{chunk_index:02d}",
                        query=query,
                        entity_type="domain",
                        search_surface=search_surface,
                    )
                )
    return definitions


def _scope_definitions(
    strategy: dict,
    compounds: Sequence[str],
    providers: Sequence[str],
    *,
    layer: str = "scope",
    all_time_delta: bool = False,
) -> list[SearchDefinition]:
    definitions: list[SearchDefinition] = []
    for compound in compounds:
        for provider in providers:
            if provider == "openalex":
                query = openalex_compound_identity_query(strategy, compound)
            else:
                query = _make_query(
                    provider,
                    compound_terms(compound),
                    [],
                    left_substances=[compound],
                )
            definitions.append(
                _definition(
                    provider=provider,
                    dataset="general",
                    layer=layer,
                    search_type="historical_compound_identity" if all_time_delta else "compound_identity",
                    module_id="compound_identity",
                    query=query,
                    compound=compound,
                    entity_type="compound_scope",
                    search_surface=(
                        clean(strategy["providers"]["openalex"].get("scope_search_surface", "title_and_abstract"))
                        if provider == "openalex"
                        else "text_word_and_controlled_vocabulary"
                    ),
                )
            )
    return definitions


def _targeted_pair_definitions(
    strategy: dict,
    scope: dict[str, list[str]],
    providers: Sequence[str],
) -> list[SearchDefinition]:
    """Build only explicitly configured, justified compound-entity searches."""

    definitions: list[SearchDefinition] = []
    pair_surface = clean(strategy["providers"]["openalex"].get("pair_search_surface", "title_and_abstract"))
    configured = strategy.get("targeted_pairs", [])
    if not isinstance(configured, list):
        raise ValueError("targeted_pairs must be a list")
    max_pairs = int(strategy.get("planning", {}).get("max_targeted_pairs", 100))
    if len(configured) > max_pairs:
        raise ValueError(f"Configured targeted pairs exceed max_targeted_pairs={max_pairs}")

    allowed_compounds = {normalized_key(value) for value in scope.get("allowed_compounds", [])}
    entity_lists = {
        "target": scope.get("allowed_targets", []),
        "brain_region_or_network": scope.get("allowed_brain_regions_and_networks", []),
        "cognitive_behavioral_task": scope.get("allowed_cognitive_behavioral_tasks", []),
        "indication": scope.get("allowed_disorders", []),
    }
    module_ids = {
        "target": "targeted_target_pair",
        "brain_region_or_network": "targeted_brain_system_pair",
        "cognitive_behavioral_task": "targeted_cognitive_task_pair",
        "indication": "targeted_indication_pair",
    }
    datasets = {
        "target": "mechanistic",
        "brain_region_or_network": "mechanistic",
        "cognitive_behavioral_task": "mechanistic",
        "indication": "disorder",
    }
    for item in configured:
        if not isinstance(item, dict):
            raise ValueError("Each targeted pair must be an object")
        compound = clean(item.get("compound"))
        entity = clean(item.get("entity"))
        kind = clean(item.get("entity_type"))
        rationale = clean(item.get("rationale"))
        if not compound or normalized_key(compound) not in allowed_compounds:
            raise ValueError(f"Targeted pair uses an out-of-scope compound: {compound or '<missing>'}")
        if kind not in entity_lists:
            raise ValueError(f"Unsupported targeted-pair entity_type: {kind or '<missing>'}")
        allowed_entities = {normalized_key(value) for value in entity_lists[kind]}
        if not entity or normalized_key(entity) not in allowed_entities:
            raise ValueError(f"Targeted pair uses an out-of-scope {kind}: {entity or '<missing>'}")
        if not rationale:
            raise ValueError(f"Targeted pair requires a rationale: {compound} + {entity}")
        for provider in providers:
            aliases = openalex_compound_terms(compound) if provider == "openalex" else compound_terms(compound)
            query = _make_query(
                provider,
                aliases,
                entity_terms(entity, kind),
                left_substances=[compound],
                right_controlled=[entity] if provider == "pubmed" else [],
            )
            definitions.append(
                _definition(
                    provider=provider,
                    dataset=datasets[kind],
                    layer="targeted_pairs",
                    search_type="targeted_pair",
                    module_id=module_ids[kind],
                    query=query,
                    compound=compound,
                    entity=entity,
                    entity_type=kind,
                    search_surface=(pair_surface if provider == "openalex" else "text_word_and_controlled_vocabulary"),
                )
            )
    return definitions


def latest_scope_snapshot(history: dict, strategy: dict) -> dict[str, list[str]]:
    runs = history.get("runs", []) if isinstance(history, dict) else []
    for run in reversed(runs if isinstance(runs, list) else []):
        if not isinstance(run, dict) or run.get("status") != "promoted":
            continue
        if not run.get("establishes_scope_baseline", False):
            continue
        snapshot = run.get("scope_snapshot")
        if isinstance(snapshot, dict):
            return {key: list(values) for key, values in snapshot.items() if isinstance(values, list)}
    legacy = strategy.get("legacy_scope_snapshot", {})
    return {key: list(values) for key, values in legacy.items() if isinstance(values, list)}


def scope_delta(previous: dict[str, list[str]], current: dict[str, list[str]]) -> dict[str, list[str]]:
    delta: dict[str, list[str]] = {}
    for key, values in current.items():
        previous_keys = {normalized_key(value) for value in previous.get(key, [])}
        delta[key] = [value for value in values if normalized_key(value) not in previous_keys]
    return delta


def build_definitions(
    strategy: dict,
    scope: dict[str, list[str]],
    *,
    providers: Sequence[str],
    layers: Sequence[str],
    history: dict | None = None,
    include_scope_delta: bool = True,
) -> tuple[list[SearchDefinition], dict[str, list[str]]]:
    providers = tuple(provider for provider in providers if provider in SUPPORTED_PROVIDERS)
    selected_layers = set(layers)
    definitions: list[SearchDefinition] = []
    if "core" in selected_layers:
        definitions.extend(_core_definitions(strategy, scope, providers))
    if "scope" in selected_layers:
        definitions.extend(_scope_definitions(strategy, scope.get("allowed_compounds", []), providers))
    if "targeted_pairs" in selected_layers:
        definitions.extend(_targeted_pair_definitions(strategy, scope, providers))

    previous = latest_scope_snapshot(history or {}, strategy)
    # The legacy manifest can identify the compound gap exactly, but it did not
    # preserve an authoritative target/disorder snapshot. Treat those unknown
    # categories as already covered on the first versioned run instead of scheduling
    # thousands of spurious all-time delta queries. Subsequent promoted runs
    # persist the complete scope snapshot and make these diffs exact.
    for key in ("allowed_targets", "allowed_brain_regions_and_networks", "allowed_cognitive_behavioral_tasks", "allowed_disorders"):
        if not previous.get(key):
            previous[key] = list(scope.get(key, []))
    delta = scope_delta(previous, scope)
    if include_scope_delta and any(delta.values()):
        added_compounds = delta.get("allowed_compounds", [])
        if added_compounds:
            definitions.extend(
                _scope_definitions(
                    strategy,
                    added_compounds,
                    providers,
                    layer="scope_delta",
                    all_time_delta=True,
                )
            )

    unique: dict[str, SearchDefinition] = {}
    for definition in definitions:
        unique[definition.search_id] = definition
    openalex_limit = int(strategy["providers"]["openalex"].get("max_search_query_chars", 1400))
    oversized = [
        definition
        for definition in unique.values()
        if definition.provider == "openalex" and len(definition.query) > openalex_limit
    ]
    if oversized:
        example = oversized[0]
        raise ValueError(
            f"OpenAlex query {example.search_id} has {len(example.query)} characters; limit is {openalex_limit}"
        )
    return sorted(unique.values(), key=lambda item: item.search_id), delta


def _parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(clean(value))


def last_promoted_end_date(history: dict, protocol_id: str) -> str:
    dates: list[str] = []
    for run in history.get("runs", []) if isinstance(history, dict) else []:
        if not isinstance(run, dict):
            continue
        if run.get("status") != "promoted" or run.get("protocol_id") != protocol_id:
            continue
        if not run.get("advances_standard_update_coverage", False):
            continue
        value = clean(run.get("coverage_end_date"))
        try:
            _parse_date(value)
        except (TypeError, ValueError):
            continue
        dates.append(value)
    return max(dates) if dates else ""


def date_window(
    strategy: dict,
    history: dict,
    *,
    mode: str,
    start_date: str = "",
    end_date: str = "",
    today: dt.date | None = None,
) -> tuple[str, str]:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    end = _parse_date(end_date) if end_date else today
    if start_date:
        start = _parse_date(start_date)
    elif mode == "full":
        start = _parse_date(clean(strategy.get("full_search_start_date", "1800-01-01")))
    elif mode == "update":
        last_end = last_promoted_end_date(history, clean(strategy.get("protocol_id")))
        baseline = last_end or clean(strategy.get("legacy_coverage_end_date"))
        start = _parse_date(baseline) - dt.timedelta(days=max(0, int(strategy.get("update_overlap_days", 0))))
    else:
        raise ValueError(f"Unsupported search mode: {mode}")
    if start > end:
        raise ValueError(f"Search start date {start} is after end date {end}")
    return start.isoformat(), end.isoformat()


def build_search_plan(
    *,
    strategy_path: Path = DEFAULT_STRATEGY_PATH,
    config_path: Path = DEFAULT_CONFIG_PATH,
    history_path: Path = DEFAULT_HISTORY_PATH,
    mode: str,
    providers: Sequence[str] = SUPPORTED_PROVIDERS,
    datasets: Sequence[str] = SUPPORTED_DATASETS,
    layers: Sequence[str] = ("core", "scope"),
    start_date: str = "",
    end_date: str = "",
    include_index_updates: bool = True,
    include_openalex_index_updates: bool = False,
    include_scope_delta: bool = True,
    allow_large_plan: bool = False,
    today: dt.date | None = None,
) -> tuple[list[SearchExecution], dict]:
    strategy_path = Path(strategy_path)
    config_path = Path(config_path)
    history_path = Path(history_path)
    strategy = load_strategy(strategy_path)
    scope = parse_validation_allowlists(config_path)
    history_payload = load_json(history_path, {})
    history = history_payload if isinstance(history_payload, dict) else {}
    definitions, delta = build_definitions(
        strategy,
        scope,
        providers=providers,
        layers=layers,
        history=history,
        include_scope_delta=include_scope_delta and mode == "update",
    )
    selected_datasets = set(datasets)
    definitions = [definition for definition in definitions if definition.dataset in selected_datasets]
    window_start, window_end = date_window(
        strategy,
        history,
        mode=mode,
        start_date=start_date,
        end_date=end_date,
        today=today,
    )
    strategy_digest = stable_hash(strategy, 24)
    current_scope_hash = scope_hash(scope)
    selected_providers = set(providers)
    selected_datasets = set(datasets)
    selected_layers = set(layers)
    complete_provider_scope = set(SUPPORTED_PROVIDERS) <= selected_providers
    complete_dataset_scope = set(SUPPORTED_DATASETS) <= selected_datasets
    complete_update_layers = {"core", "scope"} <= selected_layers
    expected_update_start = window_start
    if mode == "update":
        expected_update_start = date_window(
            strategy,
            history,
            mode="update",
            start_date="",
            end_date=window_end,
            today=today,
        )[0]
    update_window_has_no_gap = _parse_date(window_start) <= _parse_date(expected_update_start)
    advances_standard_update_coverage = bool(
        mode == "update"
        and complete_provider_scope
        and complete_dataset_scope
        and complete_update_layers
        and include_index_updates
        and include_scope_delta
        and update_window_has_no_gap
    )
    full_start = clean(strategy.get("full_search_start_date", "1800-01-01"))
    establishes_scope_baseline = bool(
        advances_standard_update_coverage
        or (
            mode == "full"
            and complete_provider_scope
            and complete_dataset_scope
            and {"core", "scope"} <= selected_layers
            and _parse_date(window_start) <= _parse_date(full_start)
        )
    )
    history_runs = history.get("runs", []) if isinstance(history, dict) else []
    prior_runs = [
        run
        for run in history_runs
        if isinstance(run, dict)
        and run.get("status") == "promoted"
        and run.get("protocol_id") == clean(strategy.get("protocol_id"))
    ]
    prior_run = max(
        prior_runs,
        key=lambda run: (clean(run.get("promoted_at_utc")), clean(run.get("coverage_end_date"))),
        default={},
    )
    previous_strategy_hash = clean(prior_run.get("strategy_hash"))
    strategy_changed_since_last_promoted = bool(
        previous_strategy_hash and previous_strategy_hash != strategy_digest
    )
    executions: list[SearchExecution] = []
    for definition in definitions:
        date_bases = ["publication"]
        if mode == "update" and include_index_updates and definition.layer != "scope_delta":
            if definition.provider == "pubmed":
                date_bases.append("entrez")
            elif definition.provider == "openalex" and include_openalex_index_updates:
                date_bases.append("created")
        for date_basis in date_bases:
            execution_start = (
                clean(strategy.get("full_search_start_date", "1800-01-01"))
                if definition.layer == "scope_delta"
                else window_start
            )
            identity = {
                "search_id": definition.search_id,
                "date_basis": date_basis,
                "start_date": execution_start,
                "end_date": window_end,
                "protocol_id": strategy["protocol_id"],
                "strategy_hash": strategy_digest,
                "scope_hash": current_scope_hash,
            }
            executions.append(
                SearchExecution(
                    execution_id=f"exec_{stable_hash(identity, 20)}",
                    search_id=definition.search_id,
                    dataset=definition.dataset,
                    provider=definition.provider,
                    layer=definition.layer,
                    search_type=definition.search_type,
                    module_id=definition.module_id,
                    query=definition.query,
                    compound=definition.compound,
                    entity=definition.entity,
                    entity_type=definition.entity_type,
                    search_surface=definition.search_surface,
                    date_basis=date_basis,
                    start_date=execution_start,
                    end_date=window_end,
                    protocol_id=clean(strategy["protocol_id"]),
                    strategy_hash=strategy_digest,
                    scope_hash=current_scope_hash,
                )
            )
    executions.sort(key=lambda item: (item.provider, item.dataset, item.layer, item.search_id, item.date_basis))
    max_executions = int(strategy.get("planning", {}).get("max_query_executions", 1000))
    if len(executions) > max_executions and not allow_large_plan:
        raise ValueError(
            f"Search plan has {len(executions)} executions, exceeding max_query_executions="
            f"{max_executions}; revise the strategy or pass the explicit large-plan override"
        )
    # The small known-record set was useful during initial strategy development,
    # but it is not a recall estimator or a gate for the current expanding
    # corpus. Keep yield diagnostics and retrieval checks; do not load or test
    # the legacy set in newly planned runs.
    calibration = {
        "known_relevant_check_enabled": False,
        "required_for_promotion": False,
        "disabled_reason": "Retired pilot calibration; not used by the living-search protocol.",
    }
    reclassification_dimensions = {
        key: values
        for key, values in delta.items()
        if key != "allowed_compounds" and values
    }
    metadata = {
        "schema_version": "living_search_plan_v3",
        "protocol_id": clean(strategy["protocol_id"]),
        "strategy_path": str(strategy_path.resolve()),
        "strategy_hash": strategy_digest,
        "config_path": str(config_path.resolve()),
        "scope_hash": current_scope_hash,
        "scope_snapshot": scope,
        "scope_delta": delta,
        "downstream_reclassification_required": reclassification_dimensions,
        "mode": mode,
        "coverage_start_date": window_start,
        "coverage_end_date": window_end,
        "include_index_updates": include_index_updates,
        "include_openalex_index_updates": bool(
            include_index_updates and include_openalex_index_updates and mode == "update"
        ),
        "openalex_index_update_limitation": (
            "OpenAlex created-date filtering requires a paid plan; periodic all-time reruns recover older newly indexed records."
            if mode == "update" and not include_openalex_index_updates
            else ""
        ),
        "include_scope_delta": bool(include_scope_delta and mode == "update"),
        "advances_standard_update_coverage": advances_standard_update_coverage,
        "establishes_scope_baseline": establishes_scope_baseline,
        "previous_strategy_hash": previous_strategy_hash,
        "strategy_changed_since_last_promoted": strategy_changed_since_last_promoted,
        "historical_recovery_recommended": bool(
            mode == "update" and strategy_changed_since_last_promoted
        ),
        "query_generation_policy": {
            "automatic_pair_grid": False,
            "targeted_pairs_configured": len(strategy.get("targeted_pairs", [])),
            "max_query_executions": max_executions,
            "large_plan_override": bool(allow_large_plan),
        },
        "calibration": calibration,
        "providers": list(providers),
        "datasets": list(datasets),
        "layers": list(layers),
        "execution_count": len(executions),
        "execution_counts": {
            "by_provider": {provider: sum(item.provider == provider for item in executions) for provider in providers},
            "by_dataset": {dataset: sum(item.dataset == dataset for item in executions) for dataset in datasets},
            "by_layer": {layer: sum(item.layer == layer for item in executions) for layer in SUPPORTED_LAYERS},
            "by_date_basis": {
                basis: sum(item.date_basis == basis for item in executions)
                for basis in sorted({item.date_basis for item in executions})
            },
        },
    }
    return executions, metadata
