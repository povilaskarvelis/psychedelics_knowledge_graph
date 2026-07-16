"""Versioned, resumable literature discovery for the living corpus."""

from .strategy import SearchDefinition, SearchExecution, build_search_plan

__all__ = ["SearchDefinition", "SearchExecution", "build_search_plan"]
