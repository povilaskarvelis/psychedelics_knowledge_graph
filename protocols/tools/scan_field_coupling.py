#!/usr/bin/env python3
"""Measure field-specific knowledge embedded in pipeline and UI code.

Draft tool for the field-protocol migration described in protocols/SPEC.md.
It reads the repository and writes reports; it changes nothing else.

Usage:
    python protocols/tools/scan_field_coupling.py \
        --config protocols/psychedelics/migration/scan_config.json \
        --overrides protocols/psychedelics/migration/classification_overrides.json \
        --out-dir protocols/psychedelics/migration

What is measured
1. Literal tables: assignments whose value is a list, tuple, set or dict (or a
   re.compile call) holding at least four string literals, or a single regex
   longer than 80 characters. Each table receives a class:
       S  scope and anchor-entity identity
       V  concept vocabulary and rules
       B  bindings to protocol structure (evidence-domain IDs, node kinds,
          per-domain field names); these should be derived from the protocol
       E  base vocabulary shared by biomedical evidence work
       G  engine code without field content
   and, for S, V and E, a reuse level: field, discipline or general.
   Automatic rules assign a first class; classification_overrides.json then
   replaces it for tables that were reviewed by hand.
2. Inline vocabulary regexes: re.* calls outside tables whose literal pattern
   contains at least two words. These are normalization rules written as code.
3. Logic coupling: lines outside tables containing a string literal that names
   an evidence domain or node kind, matches a field term or names the anchor
   type, and lines whose identifiers contain the anchor name.

JavaScript is scanned through Node.js and acorn when both are available.
The counts are approximate by design; see protocols/psychedelics/MIGRATION.md.
"""
from __future__ import annotations

import argparse
import ast
import collections
import csv
import datetime as dt
import json
import pathlib
import re
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
CLASSES = ("S", "V", "B", "E", "G")
DESTINATION = {
    "S": "scope.yaml / entities.yaml",
    "V": "vocabularies/*.yaml or views.yaml",
    "B": "derived from domains.yaml and schema role annotations",
    "E": "base profile shared by biomedical protocols",
    "G": "engine",
}
SCOPE_NAME = re.compile(
    r"SCOPE|EXCLUDED|IN_SCOPE|OUT_OF_SCOPE|SYNONYMS|CLASS_TERMS|ACRONYM|KETAMINE|LSD_|MDA_|DOI_COMPOUND|"
    r"PSYCHEDELIC_CLASS|CLASS_LEVEL|SUBJECT_CLASS|NON_ATOMIC|COMPOUND_KEYS|CONTROL_COMPOUND|UNREGISTERED|"
    r"SUBSTANCE_USE|ALLOWED_COMPOUND", re.I)
RULE_NAME = re.compile(
    r"_RULES|_PATTERNS|_FALLBACKS|SUPERSEDES|REFINEMENTS|_LABELS|_ORDER|_OVERRIDES|_CLARIFIERS|THEME|FAMILY|"
    r"TOPIC|CONSTRUCT|ENDPOINT|MEASURE|_TERMS|PARENT|PLACEHOLDER_KEYS|NOT_GRAPHABLE|_RE$")
BASE_NAME = re.compile(
    r"STUDY_DESIGN|PUBLICATION|PAPER_TYPE|REVIEW_|META_ANALYSIS|POPULATION|COMPARATOR|FOLLOW_?UP|ROUTE|"
    r"ADMINISTRATION|SAMPLE_SIZE|PK_PARAMETER|MATRIX|DIRECTION|PRISMA|BIBLIOGRAPHY|DOSING|SESSION_CONTEXT|"
    r"SEVERITY|SERIOUS|OUTCOME_MEASURE|EVIDENCE_STRATUM|RESULT_ROLE|STUDY_COUNT|ASSAY_FAMILY|"
    r"MECHANISTIC_RELATIONSHIP|SECONDARY_PAPER|NON_PRIMARY|PRIMARY_PAPER|NON_SOURCE|NARRATIVE|CONTAINER|"
    r"CONFERENCE|PLACEHOLDER_ABSTRACT|PREPRINT|STUDY_SYSTEM|EXPERIMENTAL_SYSTEM|METHODOLOGICAL_VALIDITY|"
    r"CLINICAL_FOLLOW|TIME|NUMBER", re.I)
DOMAIN_FIELD_NAME = re.compile(
    r"public_health|subjective|cognitive|molecular|pk_|pharmacokinetic|safety|clinical|brain|intervention|"
    r"real_world|construct|compound|condition|disorder|target|readout|pathway|assay|psychedelic|use_context|"
    r"withdrawal|combination", re.I)
WORDY = re.compile(r"[a-z]{4,}", re.I)


def load_config(path: pathlib.Path) -> dict:
    config = json.loads(path.read_text())
    config["field_re"] = re.compile(config["field_term_pattern"], re.I)
    config["anchor_re"] = re.compile("|".join(map(re.escape, config["anchor_terms"])), re.I)
    config["anchor_ident_re"] = re.compile(config["anchor_identifier_pattern"], re.I)
    names = set()
    for registry in config.get("anchor_registry_files", []):
        data = json.loads((ROOT / registry).read_text())
        for entry in data.get(config.get("anchor_registry_key", ""), []):
            names.add(entry["label"].lower())
            names.update(alias.lower() for alias in entry.get("aliases", []))
    strategy = config.get("search_strategy_file")
    if strategy and (ROOT / strategy).exists():
        snapshot = json.loads((ROOT / strategy).read_text()).get("legacy_scope_snapshot", {})
        names.update(c.lower() for c in snapshot.get("allowed_compounds", []))
    config["anchor_names"] = {n for n in names if len(n) >= 3}
    return config


def python_files(config: dict) -> list[pathlib.Path]:
    files = []
    for root in config["python_roots"]:
        files.extend(p for p in sorted((ROOT / root).rglob("*.py")) if "__pycache__" not in p.parts)
    return files


def literal_strings(node: ast.AST) -> list[str]:
    values: list[str] = []
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for element in node.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                values.append(element.value)
            elif isinstance(element, (ast.Tuple, ast.List, ast.Set, ast.Dict)):
                values += literal_strings(element)
    elif isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                values.append(key.value)
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                values.append(value.value)
            elif isinstance(value, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
                values += literal_strings(value)
    elif isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in {"frozenset", "set", "tuple", "list"}:
        for arg in node.args:
            values += literal_strings(arg)
    return values


def python_tables(path: pathlib.Path) -> list[dict]:
    tree = ast.parse(path.read_text())
    rows = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        name = target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else None
        if not name:
            continue
        items = literal_strings(value)
        regex_chars = 0
        if isinstance(value, ast.Call) and getattr(value.func, "attr", "") == "compile":
            for arg in value.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    items.append(arg.value)
                    regex_chars += len(arg.value)
        if len(items) >= 4 or regex_chars > 80:
            rows.append(dict(file=str(path.relative_to(ROOT)), name=name, line=node.lineno,
                             end=getattr(node, "end_lineno", node.lineno), items=items))
    return rows


def natural_share(items: list[str]) -> float:
    if not items:
        return 0.0
    natural = sum(1 for s in items if (" " in s or any(c.isupper() for c in s)) and not re.fullmatch(r"[a-z0-9_.\-/]+", s))
    return natural / len(items)


def looks_like_regex(items: list[str]) -> bool:
    return any((s.startswith("/") and s.endswith("/")) or "\\b" in s or "(?" in s for s in items)


def automatic_class(row: dict, config: dict) -> tuple[str, str]:
    name, items = row["name"], row["items"]
    text = " ".join(items)
    field_hit = bool(config["field_re"].search(text)) or any(s.lower() in config["anchor_names"] for s in items)
    structure_hit = any(s in config["domain_ids"] or s in config["node_kinds"] for s in items)
    natural = natural_share(items)
    if SCOPE_NAME.search(name) or (field_hit and re.search(r"compound|subject|substance", name, re.I)):
        return "S", "scope or anchor-entity identity"
    if field_hit and natural >= 0.3:
        return "V", "field vocabulary (field terms present)"
    if structure_hit and not field_hit:
        return "B", "names evidence domains or node kinds"
    if RULE_NAME.search(name) and natural >= 0.3 and not BASE_NAME.search(name):
        return "V", "concept rules or labels"
    if BASE_NAME.search(name) and natural >= 0.2:
        return "E", "base evidence vocabulary"
    if DOMAIN_FIELD_NAME.search(name) and "FIELDS" in name:
        return "B", "domain-specific field names"
    if looks_like_regex(items) and natural < 0.3 and config["field_re"].search(text):
        return "S", "field regex"
    if looks_like_regex(items) and name.endswith("_RE"):
        return ("E" if BASE_NAME.search(name) else "V"), "regex rule"
    return "G", "engine"


def load_overrides(path: pathlib.Path | None) -> dict:
    if not path or not path.exists():
        return {}
    table = {}
    for entry in json.loads(path.read_text())["overrides"]:
        for name in entry["names"]:
            table[(entry.get("file"), name)] = (entry["class"], entry["reuse"])
    return table


def classify(rows: list[dict], config: dict, overrides: dict) -> None:
    for row in rows:
        cls, rule = automatic_class(row, config)
        reuse = ""
        key = (row["file"], row["name"]) if (row["file"], row["name"]) in overrides else (None, row["name"])
        if key in overrides:
            cls, reuse = overrides[key]
            rule = "manual review"
        if cls in {"B", "G"}:
            reuse = "n/a"
        elif not reuse:
            reuse = "field" if cls == "S" else "discipline"
        row.update(cls=cls, reuse=reuse, rule=rule, destination=DESTINATION[cls])


def python_logic(path: pathlib.Path, table_lines: set[int], config: dict) -> dict:
    source = path.read_text()
    tree = ast.parse(source)
    domain_or_kind, field, anchor = set(), set(), set()
    inline = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.lineno not in table_lines:
            value = node.value
            if value in config["domain_ids"] or value in config["node_kinds"]:
                domain_or_kind.add(node.lineno)
            if config["field_re"].search(value):
                field.add(node.lineno)
            if config["anchor_re"].search(value):
                anchor.add(node.lineno)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "re" and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str) and node.lineno not in table_lines
                and len(WORDY.findall(node.args[0].value)) >= 2):
            inline += 1
    lines = source.splitlines()
    identifier_lines = sum(1 for i, line in enumerate(lines, 1)
                           if i not in table_lines and not line.strip().startswith("#") and config["anchor_ident_re"].search(line))
    return dict(total_lines=len(lines), domain_or_kind_lines=len(domain_or_kind), field_term_lines=len(field),
                anchor_literal_lines=len(anchor), anchor_identifier_lines=identifier_lines,
                any_protocol_literal_lines=len(domain_or_kind | field | anchor), inline_vocabulary_regexes=inline)


def javascript_scan(config: dict, config_path: pathlib.Path) -> tuple[list[dict], dict, str]:
    node = shutil.which("node")
    acorn = next((ROOT / c for c in config.get("acorn_candidates", []) if (ROOT / c).exists()), None)
    files = [f for f in config.get("js_files", []) if (ROOT / f).exists()]
    if not node or not acorn or not files:
        return [], {}, "skipped (node or acorn not available)"
    helper = pathlib.Path(__file__).with_name("scan_js_literals.cjs")
    result = subprocess.run([node, str(helper), str(acorn), str(config_path), *files],
                            cwd=ROOT, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return data["tables"], data["logic"], f"scanned with {acorn.relative_to(ROOT)}"


def git_state() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"head": run("rev-parse", "--short", "HEAD"), "changed_files": len([l for l in run("status", "--short").splitlines() if l.strip()])}


def area_of(file: str) -> str:
    parts = file.split("/")
    if parts[0] == "pipeline" and len(parts) > 2:
        return "/".join(parts[:2])
    return parts[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--overrides", type=pathlib.Path)
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    overrides = load_overrides(args.overrides)

    tables = []
    logic = {}
    for path in python_files(config):
        try:
            file_tables = python_tables(path)
        except SyntaxError:
            continue
        tables += file_tables
        lines = {ln for t in file_tables for ln in range(t["line"], t["end"] + 1)}
        logic[str(path.relative_to(ROOT))] = python_logic(path, lines, config)
    js_tables, js_logic, js_status = javascript_scan(config, args.config.resolve())
    tables += js_tables
    logic.update(js_logic)
    classify(tables, config, overrides)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with open(args.out_dir / "code_tables.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["class", "reuse", "destination", "file", "line", "end", "lines", "items", "name", "rule", "sample"])
        for t in sorted(tables, key=lambda t: (CLASSES.index(t["cls"]), t["file"], t["line"])):
            writer.writerow([t["cls"], t["reuse"], t["destination"], t["file"], t["line"], t["end"], t["end"] - t["line"] + 1,
                             len(t["items"]), t["name"], t["rule"], " | ".join(s[:40] for s in t["items"][:5])])
    fields = ["total_lines", "domain_or_kind_lines", "field_term_lines", "anchor_literal_lines",
              "anchor_identifier_lines", "any_protocol_literal_lines", "inline_vocabulary_regexes"]
    with open(args.out_dir / "logic_coupling.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["file", *fields])
        for file, counts in sorted(logic.items()):
            writer.writerow([file, *(counts[f] for f in fields)])

    by_class = collections.defaultdict(lambda: {"tables": 0, "lines": 0, "items": 0})
    by_language = collections.defaultdict(lambda: collections.Counter())
    by_area = collections.defaultdict(lambda: collections.Counter())
    for t in tables:
        key = f"{t['cls']}/{t['reuse']}"
        span = t["end"] - t["line"] + 1
        by_class[key]["tables"] += 1
        by_class[key]["lines"] += span
        by_class[key]["items"] += len(t["items"])
        by_language["javascript" if t["file"].endswith(".js") else "python"][t["cls"]] += span
        by_area[area_of(t["file"])][t["cls"]] += span
    logic_by_area = collections.defaultdict(lambda: collections.Counter())
    for file, counts in logic.items():
        logic_by_area[area_of(file)].update(counts)
    summary = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "repository": git_state(),
        "javascript": js_status,
        "table_lines_by_class_and_reuse": dict(sorted(by_class.items())),
        "table_lines_by_language": {k: dict(v) for k, v in by_language.items()},
        "table_lines_by_area": {k: dict(v) for k, v in sorted(by_area.items())},
        "logic_coupling_by_area": {k: dict(v) for k, v in sorted(logic_by_area.items())},
        "logic_coupling_totals": dict(sum((collections.Counter(c) for c in logic.values()), collections.Counter())),
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    protocol_lines = sum(v["lines"] for k, v in by_class.items() if not k.startswith("G"))
    all_lines = sum(v["lines"] for v in by_class.values())
    print(f"{len(tables)} literal tables, {all_lines} lines; protocol content in {protocol_lines} lines "
          f"({100 * protocol_lines / max(all_lines, 1):.0f}%). JavaScript: {js_status}. Reports in {args.out_dir}")


if __name__ == "__main__":
    main()
