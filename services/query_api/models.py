from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


LiteratureSource = Literal["primary", "meta_analyses", "reviews"]
QueryScope = Literal["main_graph", "all_normalized"]
DetailLevel = Literal["summary", "full"]


class FindingFilters(BaseModel):
    compound_ids: list[str] = Field(default_factory=list)
    compounds: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    entity_labels: list[str] = Field(default_factory=list)
    entity_kinds: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    evidence_types: list[str] = Field(default_factory=list)
    literature_sources: list[LiteratureSource] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    directions: list[str] = Field(default_factory=list)
    text_depth: list[str] = Field(default_factory=list)
    paper_ids: list[str] = Field(default_factory=list)
    study_dois: list[str] = Field(default_factory=list)
    year_from: int | None = Field(default=None, ge=1800, le=2200)
    year_to: int | None = Field(default=None, ge=1800, le=2200)
    query: str | None = Field(
        default=None,
        max_length=300,
        description="Case-insensitive text match across compound, entity, title, DOI, and outcome.",
    )

    @model_validator(mode="after")
    def validate_year_range(self) -> "FindingFilters":
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("year_from must be less than or equal to year_to")
        return self


class FindingQuery(BaseModel):
    filters: FindingFilters = Field(default_factory=FindingFilters)
    scope: QueryScope = "main_graph"
    detail_level: DetailLevel = "summary"
    fields: list[str] = Field(
        default_factory=list,
        max_length=40,
        description="Optional public finding fields to return. Overrides detail_level.",
    )
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = None


class AggregateQuery(BaseModel):
    filters: FindingFilters = Field(default_factory=FindingFilters)
    scope: QueryScope = "main_graph"
    group_by: list[str] = Field(
        default_factory=lambda: ["compound", "entity_label"],
        min_length=1,
        max_length=4,
    )
    limit: int = Field(default=50, ge=1, le=200)


class NeighborQuery(BaseModel):
    scope: QueryScope = "main_graph"
    literature_sources: list[LiteratureSource] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=200)
