# Field protocols (draft)

This directory drafts a separation between the field-agnostic pipeline (the engine) and the decisions that make the graph specific to psychedelic research (the field protocol). The aim is that a graph for another field can be built by writing a new protocol, not by changing pipeline code.

Nothing here is read by the pipeline yet. No existing file was changed to create it.

| Path | Content |
|---|---|
| [SPEC.md](SPEC.md) | The protocol format: files, keys, rule types, change management, graph card, open decisions. |
| [psychedelics/](psychedelics/) | The current psychedelics decisions in that format, read from the repository on 30 October 2026. Where a decision still lives in code, the file names the location. |
| [psychedelics/MIGRATION.md](psychedelics/MIGRATION.md) | How much field content the code holds, where it is, and an order of work with a test per step. |
| [psychedelics/vocabularies/](psychedelics/vocabularies/) | Two concept schemes converted from Python rule tables, verified against the originals. |
| [psychedelics/migration/](psychedelics/migration/) | Scan inputs, manual classification and the generated reports. |
| [tools/](tools/) | `scan_field_coupling.py` (measures field content in code), `export_concept_scheme.py` (converts a rule table to a concept scheme). |
| [base/](base/) | Placeholder for base profiles shared by several protocols. |

Re-run the measurement after each refactoring step:

```bash
python protocols/tools/scan_field_coupling.py --config protocols/psychedelics/migration/scan_config.json --overrides protocols/psychedelics/migration/classification_overrides.json --out-dir protocols/psychedelics/migration
```

The scan uses Node.js and the acorn parser installed under `artifacts/` for the browser scripts. Without them it scans Python only and says so.
