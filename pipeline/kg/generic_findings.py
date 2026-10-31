"""Preserve fallback measurements without inventing a clinical graph endpoint."""
from pipeline.extract.io_utils import normalize

REPORTED_MEASUREMENT_KIND = "reported_measurement"
GENERAL_FINDING_FIELDS = (
    "best_domain_guess", "entity_or_endpoint", "measure_or_method",
    "population_or_system", "dose_or_context", "why_general_fallback",
)


def reported_measurement_label(row: dict) -> str:
    # The extraction schema distinguishes an endpoint from its sample/system.
    # Never substitute a population as a diagnosis when the endpoint is absent.
    for field in ("entity_or_endpoint", "measure_or_method", "graph_entity_label", "entity_label"):
        value = normalize(row.get(field, ""))
        if value and value.casefold().replace("_", " ") not in {"not reported", "not applicable", "unspecified", "none", "n/a"}:
            return value
    return "Reported finding"
