# Assessing Literature Search Coverage

No bibliographic search can guarantee that it has identified every eligible
report. Psychedelics Knowledge Graph therefore documents both the completeness
of database retrieval and the known limits of its search strategy.

## Database retrieval checks

For every query and date range, the pipeline records:

- the database and exact search query;
- the number of results reported by the database;
- every retrieved database identifier;
- the completion of result pagination; and
- any errors or interruptions.

A search run is complete when all result pages have been retrieved successfully
and the number of retrieved records matches the number reported by the database.
Runs interrupted by database errors or request limits remain incomplete until
retrieval resumes and these checks pass.

## Coverage of the literature

Complete retrieval confirms that the pipeline obtained all results returned by
the specified queries. The coverage of relevant literature also depends on the
databases searched, their indexing practices, the search terms, and the
availability and accuracy of bibliographic metadata. Database overlap, query
yield, and the search terms are reviewed separately.

During early development, a small set of known relevant studies was used to
help test the search strategy. That set is retained to document the development
process, but it is not sufficiently representative to estimate recall for the
current evidence base. A formal recall estimate would require an appropriate
reference standard.

OpenAlex publication-date filters do not identify every older work that has
recently been added to the index. The pipeline therefore periodically repeats
OpenAlex searches across all publication years.
