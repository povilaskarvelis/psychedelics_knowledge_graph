from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator


FILTER_LIST_MAX_ITEMS = 100
FILTER_VALUE_MAX_LENGTH = 500
CURSOR_MAX_LENGTH = 2048
FilterValue = Annotated[str, StringConstraints(max_length=FILTER_VALUE_MAX_LENGTH)]


class YearRange(BaseModel):
    year_from: int | None = Field(default=None, ge=1800, le=2200)
    year_to: int | None = Field(default=None, ge=1800, le=2200)

    @model_validator(mode="after")
    def validate_year_range(self) -> "YearRange":
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("year_from must be less than or equal to year_to")
        return self


class PaperFilters(YearRange):
    query: str | None = Field(
        default=None,
        max_length=300,
        description="Case-insensitive match across title, DOI, journal, and credited author names.",
    )
    paper_ids: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    dois: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    paper_types: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    paper_subtypes: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    author_ids: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    author_names: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    concept_ids: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    subject_labels: list[FilterValue] = Field(
        default_factory=list,
        max_length=FILTER_LIST_MAX_ITEMS,
        description="Match papers with an exact relationship subject label. Prefer subject IDs for durable integrations.",
    )
    object_labels: list[FilterValue] = Field(
        default_factory=list,
        max_length=FILTER_LIST_MAX_ITEMS,
        description="Match papers with an exact relationship object label. Prefer object IDs for durable integrations.",
    )
    domains: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    relation_types: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    subject_kinds: list[FilterValue] = Field(
        default_factory=list,
        max_length=FILTER_LIST_MAX_ITEMS,
        description="Match papers with a relationship whose subject has one of these contextual kinds.",
    )
    object_kinds: list[FilterValue] = Field(
        default_factory=list,
        max_length=FILTER_LIST_MAX_ITEMS,
        description="Match papers with a relationship whose object has one of these contextual kinds.",
    )


class PaperQuery(BaseModel):
    filters: PaperFilters = Field(default_factory=PaperFilters)
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=CURSOR_MAX_LENGTH)


class RelationshipFilters(YearRange):
    paper_ids: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    dois: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    paper_types: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    paper_subtypes: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    author_ids: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    author_names: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    concept_ids: list[FilterValue] = Field(
        default_factory=list,
        max_length=FILTER_LIST_MAX_ITEMS,
        description="Match a concept at either end of the relationship.",
    )
    subject_ids: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    object_ids: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    subject_labels: list[FilterValue] = Field(
        default_factory=list,
        max_length=FILTER_LIST_MAX_ITEMS,
        description="Match an exact subject label. Prefer subject IDs for durable integrations.",
    )
    object_labels: list[FilterValue] = Field(
        default_factory=list,
        max_length=FILTER_LIST_MAX_ITEMS,
        description="Match an exact object label. Prefer object IDs for durable integrations.",
    )
    domains: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    relation_types: list[FilterValue] = Field(
        default_factory=list, max_length=FILTER_LIST_MAX_ITEMS
    )
    subject_kinds: list[FilterValue] = Field(
        default_factory=list,
        max_length=FILTER_LIST_MAX_ITEMS,
        description="Match the relationship-scoped subject kind.",
    )
    object_kinds: list[FilterValue] = Field(
        default_factory=list,
        max_length=FILTER_LIST_MAX_ITEMS,
        description="Match the relationship-scoped object kind.",
    )


class RelationshipQuery(BaseModel):
    filters: RelationshipFilters = Field(default_factory=RelationshipFilters)
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=CURSOR_MAX_LENGTH)
