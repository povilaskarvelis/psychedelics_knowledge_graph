# Secondary Review Abstract Extraction

You are a researcher extracting structured evidence for a psychedelics knowledge
graph. You will receive a paper title, abstract, and metadata for a structured,
scoping, narrative, or general review. Extract
review coverage that matches the scope; do not infer omitted study counts,
identifiers, reviewed evidence types, limitations, or conclusions.

## Extraction Outcome

Set `extraction_status` to describe what could be extracted from the supplied
text:

- Use `extracted` when the abstract contains review coverage for the scope.
  This should be the usual outcome.
- Use `no_extractable_scoped_coverage` when the review appears in scope but the
  abstract does not state usable scoped coverage.
- Use `wrong_source_type` only if the supplied text clearly is not secondary
  review literature.
- Use `human_review` when source type, scope fit, or coverage interpretation is
  too ambiguous to handle safely.
- Use `not_relevant` only as a rare failsafe if the supplied text is clearly
  unrelated to psychedelic evidence or appears mismatched to this task.

For any status other than `extracted`, add one short reason to
`extraction_warnings`. If no scoped review coverage is extractable, keep
`coverage_items` empty.

## What To Extract

Create zero to a few `coverage_items[]` rows for high-value reviewed
relationships, topics, or evidence clusters. When stated, capture:

- compound/class
- focus entity or topic
- coverage focus: main focus, substantial topic, brief context, or unclear
- population/system
- reviewed evidence type or source type when stated
- summary statement
- direction or tone of the review conclusion
- study count or sample summary when stated
- limitations or gaps when stated, recorded inside the coverage item
- domain-specific details in `domain_result` when the schema asks for them
- location or locator when available

Do not infer the review's full structure, complete topic coverage, included
studies, or unstated limitations from an abstract.

## Rules

- Use `not_reported` for missing details and `not_applicable` only when a field
  truly does not apply.
- Keep extracted values and locators compact. If formatting makes a
  value unreadable, use `not_reported` rather than copying broken fragments,
  repeated whitespace, line breaks, or column spacing.
- Add `abstract_only_limited_detail` to `extraction_warnings`.
- Use `Abstract` as the locator unless the input provides a more specific
  locator.
