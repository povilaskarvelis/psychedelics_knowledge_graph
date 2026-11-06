"""Source identity: which text belongs to which paper.

Field-agnostic engine code shared by ingest, full-text, extraction and graph
stages:

- ``evidence``: identifiers, titles and document kinds, compared one way;
- ``verify``: the rule that a text belongs to a paper;
- ``model_reports``: extraction-model statements that a text is another work;
- ``register``: reviewed identity decisions, one append-only file;
- ``works``: the relations between identifiers of one work;
- ``audit``: the read-only review queue of texts and records to decide;
- ``decide``: checks reviewed decisions and appends them;
- ``bindings``: the verdict table, which texts the pipeline may read;
- ``gate``: whether one stored text may be read for one paper;
- ``apply``: builds the verdict table and lists the papers whose text changes;
- ``migrate``: gathers decisions still kept in older per-incident files.

Run ``python -m pipeline.identity --help`` for the commands.
"""
