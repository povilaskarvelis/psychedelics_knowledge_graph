from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


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
    paper_ids: list[str] = Field(default_factory=list)
    dois: list[str] = Field(default_factory=list)
    paper_types: list[str] = Field(default_factory=list)
    paper_subtypes: list[str] = Field(default_factory=list)
    author_ids: list[str] = Field(default_factory=list)
    author_names: list[str] = Field(default_factory=list)
    concept_ids: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)


class PaperQuery(BaseModel):
    filters: PaperFilters = Field(default_factory=PaperFilters)
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = None


class RelationshipFilters(YearRange):
    paper_ids: list[str] = Field(default_factory=list)
    dois: list[str] = Field(default_factory=list)
    paper_types: list[str] = Field(default_factory=list)
    paper_subtypes: list[str] = Field(default_factory=list)
    author_ids: list[str] = Field(default_factory=list)
    author_names: list[str] = Field(default_factory=list)
    concept_ids: list[str] = Field(
        default_factory=list,
        description="Match a concept at either end of the relationship.",
    )
    subject_ids: list[str] = Field(default_factory=list)
    object_ids: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)


class RelationshipQuery(BaseModel):
    filters: RelationshipFilters = Field(default_factory=RelationshipFilters)
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = None
