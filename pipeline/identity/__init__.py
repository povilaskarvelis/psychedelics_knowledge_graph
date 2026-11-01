"""Source identity: which text belongs to which paper.

Field-agnostic engine code shared by ingest, full-text, extraction and graph
stages:

- ``register``: reviewed identity decisions, one append-only file;
- ``works``: the relations between identifiers of one work;
- ``migrate``: gathers decisions still kept in older per-incident files.

Run ``python -m pipeline.identity --help`` for the commands.
"""
