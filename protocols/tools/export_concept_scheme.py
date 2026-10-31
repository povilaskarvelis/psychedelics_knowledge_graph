#!/usr/bin/env python3
"""Write one concept scheme in the draft protocol format from its current sources.

A concept scheme in the current pipeline can be split across a vocabulary file
(labels and aliases), a Python rule table of (label, regex) pairs and a Python
dict of exact keys. This tool reads those sources without importing pipeline
code, merges them by label and writes one YAML file. The pipeline does not read
the output; it is a worked example for protocols/SPEC.md section 5.6.

Example:
    python protocols/tools/export_concept_scheme.py \
        --kind subjective_experience_construct \
        --header protocols/psychedelics/migration/scheme_headers/subjective_experience_construct.yaml \
        --vocabulary schema/kg_node_vocabularies.json \
        --rules pipeline/kg/build_evidence_tables.py:SUBJECTIVE_EXPERIENCE_RULES \
        --exact-keys pipeline/kg/build_evidence_tables.py:SUBJECTIVE_EXPERIENCE_LABEL_FALLBACKS \
        --out protocols/psychedelics/vocabularies/subjective_experience_construct.yaml
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
FLAG_NAMES = {"I": "IGNORECASE", "IGNORECASE": "IGNORECASE", "M": "MULTILINE", "MULTILINE": "MULTILINE",
              "S": "DOTALL", "DOTALL": "DOTALL", "X": "VERBOSE", "VERBOSE": "VERBOSE"}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_assignment(path: pathlib.Path, name: str) -> ast.AST:
    tree = ast.parse(path.read_text())
    for node in tree.body:
        target = node.targets[0] if isinstance(node, ast.Assign) else node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(target, ast.Name) and target.id == name:
            return node
    raise SystemExit(f"{name} not found in {path}")


def flags_of(call: ast.Call) -> list[str]:
    names = []
    for arg in list(call.args[1:]) + [k.value for k in call.keywords if k.arg == "flags"]:
        for node in ast.walk(arg):
            if isinstance(node, ast.Attribute) and node.attr in FLAG_NAMES:
                names.append(FLAG_NAMES[node.attr])
    return sorted(set(names))


def compiled_pattern(node: ast.AST) -> dict | None:
    if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "compile" and node.args:
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return {"pattern": first.value, "flags": flags_of(node)}
    return None


def read_rules(spec: str) -> tuple[list[tuple[str, dict]], dict]:
    file, name = spec.rsplit(":", 1)
    path = ROOT / file
    node = find_assignment(path, name)
    rules = []
    for element in node.value.elts:
        label = next((e.value for e in element.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)), None)
        pattern = next((p for p in (compiled_pattern(e) for e in element.elts) if p), None)
        if label and pattern:
            rules.append((label, pattern))
    return rules, {"path": file, "name": name, "lines": f"{node.lineno}-{node.end_lineno}", "sha256": sha256(path)}


def read_exact_keys(spec: str) -> tuple[dict[str, str], dict]:
    file, name = spec.rsplit(":", 1)
    path = ROOT / file
    node = find_assignment(path, name)
    mapping = {k.value: v.value for k, v in zip(node.value.keys, node.value.values)
               if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)}
    return mapping, {"path": file, "name": name, "lines": f"{node.lineno}-{node.end_lineno}", "sha256": sha256(path)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--kind", required=True)
    parser.add_argument("--header", type=pathlib.Path, required=True)
    parser.add_argument("--vocabulary", help="JSON vocabulary with node_kinds.<kind> entries")
    parser.add_argument("--rules", help="file.py:NAME of a tuple of (label, re.compile(...)) pairs")
    parser.add_argument("--exact-keys", help="file.py:NAME of a dict mapping normalized keys to labels")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()

    concepts: dict[str, dict] = {}
    sources = []

    def concept(label: str) -> dict:
        return concepts.setdefault(label, {"label": label, "aliases": [], "exact_keys": [], "patterns": [],
                                           "ids": {}, "defined_in": []})

    if args.vocabulary:
        path = ROOT / args.vocabulary
        entries = json.loads(path.read_text())["node_kinds"].get(args.kind, [])
        sources.append({"path": args.vocabulary, "key": f"node_kinds.{args.kind}", "entries": len(entries), "sha256": sha256(path)})
        for entry in entries:
            item = concept(entry["label"])
            item["aliases"] = list(entry.get("aliases", []))
            item["ids"] = {k: v for k, v in (entry.get("ids") or {}).items() if v}
            item["status"] = entry.get("status", "")
            item["defined_in"].append("vocabulary_file")
    if args.rules:
        rules, provenance = read_rules(args.rules)
        provenance["entries"] = len(rules)
        sources.append(provenance)
        for order, (label, pattern) in enumerate(rules, 1):
            item = concept(label)
            item["patterns"].append({"order": order, **pattern})
            if "rule_table" not in item["defined_in"]:
                item["defined_in"].append("rule_table")
    if args.exact_keys:
        mapping, provenance = read_exact_keys(args.exact_keys)
        provenance["entries"] = len(mapping)
        sources.append(provenance)
        for key, label in mapping.items():
            item = concept(label)
            item["exact_keys"].append(key)
            if "exact_key_table" not in item["defined_in"]:
                item["defined_in"].append("exact_key_table")

    header = yaml.safe_load(args.header.read_text())
    ordered = sorted(concepts.values(), key=lambda c: min([p["order"] for p in c["patterns"]] or [10_000]))
    for item in ordered:
        for key in ("aliases", "exact_keys", "patterns", "ids"):
            if not item[key]:
                item.pop(key)
        if not item.get("status"):
            item.pop("status", None)
    only = {name: sorted(c["label"] for c in ordered if c["defined_in"] == [name])
            for name in ("vocabulary_file", "rule_table", "exact_key_table")}
    document = {
        **header,
        "generated_from": sources,
        "consistency": {
            "concepts": len(ordered),
            "only_in_vocabulary_file": only["vocabulary_file"],
            "only_in_rule_table": only["rule_table"],
            "only_in_exact_key_table": only["exact_key_table"],
        },
        "concepts": ordered,
    }
    # A large width keeps every regex on one line; folded scalars are hard to review.
    text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=10_000, default_flow_style=False)
    banner = (f"# Generated by protocols/tools/export_concept_scheme.py from the sources listed under\n"
              f"# generated_from. The pipeline still reads those sources, not this file.\n")
    args.out.write_text(banner + text)

    # Round-trip check: every pattern and exact key must read back unchanged.
    reread = {c["label"]: c for c in yaml.safe_load(args.out.read_text())["concepts"]}
    for item in ordered:
        back = reread[item["label"]]
        assert [p["pattern"] for p in back.get("patterns", [])] == [p["pattern"] for p in item.get("patterns", [])], item["label"]
        assert back.get("exact_keys", []) == item.get("exact_keys", []), item["label"]
    print(f"{args.out}: {len(ordered)} concepts; patterns and exact keys verified after reading back")


if __name__ == "__main__":
    main()
