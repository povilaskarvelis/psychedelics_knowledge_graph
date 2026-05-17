# Pair-Grid Audit Summary

- Generated: 2026-05-17T12:39:15.269912+00:00
- Protocol: `comprehensive_baseline_v1`
- Provider: `both`
- Providers run: `openalex, pubmed`
- Query variant mode: `conservative`
- Status: `completed`

## Final Queues

| Dataset | Pair-grid discovered DOIs | Pair-grid new vs existing corpus | Boolean new DOIs | Final all-layer new DOIs | Pair-grid incremental new beyond Boolean |
| --- | ---: | ---: | ---: | ---: | ---: |
| mechanistic | 4584 | 2502 | 3636 | 2502 | 2502 |
| disorder | 3407 | 1892 | 2417 | 1892 | 1892 |

## Family Rollup

| Provider | Dataset | Family | Chunks | Seeds | Raw rows | Merged rows | Provider errors | New vs existing corpus | Rediscovered | Invalid |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| openalex | disorder | pair_core | 4 | 3717 | 0 | 0 | 3717 | 0 | 0 | 0 |
| openalex | mechanistic | pair_core | 6 | 5520 | 7816 | 1091 | 4623 | 349 | 742 | 0 |
| pubmed | disorder | pair_core | 4 | 3717 | 11915 | 3633 | 0 | 1917 | 1709 | 7 |
| pubmed | mechanistic | pair_core | 6 | 5520 | 11712 | 3960 | 0 | 2206 | 1752 | 2 |

## Outputs

- `mechanistic` pair-grid new queue: `/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/raw/search_strategies/comprehensive_baseline_v1/pair_grid_openalex_pubmed_direct_v1/combined/mechanistic_new_dois.txt`
- `mechanistic` all-layer final new queue: `/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/raw/search_strategies/comprehensive_baseline_v1/pair_grid_openalex_pubmed_direct_v1/all_layers_combined/mechanistic_new_dois.txt`
- `disorder` pair-grid new queue: `/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/raw/search_strategies/comprehensive_baseline_v1/pair_grid_openalex_pubmed_direct_v1/combined/disorder_new_dois.txt`
- `disorder` all-layer final new queue: `/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/raw/search_strategies/comprehensive_baseline_v1/pair_grid_openalex_pubmed_direct_v1/all_layers_combined/disorder_new_dois.txt`
