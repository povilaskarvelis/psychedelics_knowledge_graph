"""Mechanical source-kind checks; never scientific screening decisions."""
import re
from pipeline.extract.io_utils import normalize

VERSION="extraction_source_text_quality_v1"
NAVIGATION = [
    r"^\s*(?:ADVERTISEMENT|RETURN TO ISSUE|This article is cited by).{0,2000}(?:Article Views|Altmetric|Abstract)",
    r"^\s*(?:Log in or Register|Log in|Subscribe to journal|\[Log in|Register for).{0,1800}(?:Subscribe|Advanced Search|Purchase|Next Article|Favorites)",
    r"^\s*This article describes an experiment.{0,1200}THE EDITORS\s*$",
]

def abstract_quality_flags(abstract: str) -> list[str]:
    text=normalize(abstract)
    if not text:return ["missing_abstract"]
    # A page may contain both navigation and a real Abstract section. Such a
    # mixed transcript needs parsing; it is not established to lack an abstract.
    abstract_section=re.search(r"\bAbstract(?:\s*[:\n]\s*|\s+|(?=[A-Z]))(?!and\b|Citation\b|references\b)([A-Z][\s\S]{100,})",text)
    if not abstract_section and any(re.search(p,text,re.I|re.S) for p in NAVIGATION):return ["publisher_navigation_or_editorial_instead_of_abstract"]
    return []
