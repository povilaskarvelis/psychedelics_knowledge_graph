"""Generate author-identity review candidates; name similarity never merges IDs."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd


def name_parts(value: str) -> list[str]:
    value = ''.join('-' if unicodedata.category(c) == 'Pd' else c for c in value)
    value = unicodedata.normalize('NFKD', value.casefold())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.findall(r'[^\W\d_]+(?:-[^\W\d_]+)*', value)


def audit(kg_dir: Path, out_dir: Path) -> dict:
    authors = pd.read_parquet(kg_dir / 'authors.parquet').fillna('')
    links = pd.read_parquet(kg_dir / 'paper_authors.parquet').fillna('')
    papers = pd.read_parquet(kg_dir / 'papers.parquet').fillna('')
    groups = defaultdict(list)
    for row in authors.to_dict('records'):
        parts = name_parts(row['display_name'])
        if len(parts) >= 2 and len(parts[0]) > 2:
            groups[(parts[0], parts[-1])].append(row)
    papers_by_author = links.groupby('author_id')['paper_id'].agg(set).to_dict()
    authors_by_paper = links.groupby('paper_id')['author_id'].agg(set).to_dict()
    coauthors = {}
    def collaborators(author_id):
        if author_id not in coauthors:
            coauthors[author_id] = set().union(*(authors_by_paper[p] for p in papers_by_author.get(author_id, set()))) - {author_id}
        return coauthors[author_id]
    rows = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        ids = {m['author_id'] for m in members}
        orcids = sorted({m['orcid'] for m in members if m['orcid']})
        shared = 0
        for i, a in enumerate(members):
            for b in members[i+1:]:
                shared = max(shared, len((collaborators(a['author_id']) & collaborators(b['author_id'])) - ids))
        rows.append({
            'name_key': ' '.join(key), 'identity_count': len(ids),
            'paper_count': len(set().union(*(papers_by_author.get(x, set()) for x in ids))),
            'names': sorted({m['display_name'] for m in members}),
            'author_ids': sorted(ids), 'orcids': orcids,
            'max_shared_coauthors': shared,
            'status': 'identifier_conflict_review' if len(orcids) > 1 else 'name_similarity_review',
            'identities': [{k: m[k] for k in ('author_id','display_name','orcid','paper_count','identity_confidence')} for m in members],
        })
    rows.sort(key=lambda r: (-r['paper_count'], r['name_key']))
    duplicate_positions = links[links.duplicated(['paper_id','author_position'], keep=False)]
    duplicate_identities = links[links.duplicated(['paper_id','author_id'], keep=False)]
    # A repeated ID with different names can indicate a false merge or merely a
    # duplicate source entry with spelling variants. Preserve both for review.
    name_counts = duplicate_identities.groupby(['paper_id', 'author_id'])['display_name'].transform('nunique')
    differing_names = duplicate_identities[name_counts.gt(1)]
    conflicts = links[links.identity_confidence.eq('openalex_author_id_orcid_conflict')]
    orphan_links = links[~links.paper_id.isin(papers.paper_id) | ~links.author_id.isin(authors.author_id)]
    report = {
        'schema_version': 'author_identity_audit_v1', 'kg_dir': str(kg_dir.resolve()),
        'author_identities': len(authors), 'authorship_rows': len(links),
        'candidate_name_groups': len(rows),
        'candidate_identities': sum(r['identity_count'] for r in rows),
        'groups_with_multiple_orcids': sum(len(r['orcids']) > 1 for r in rows),
        'orcid_conflict_profiles': int(conflicts.openalex_author_id.nunique()),
        'orcid_conflict_authorship_rows': len(conflicts),
        'repeated_author_on_same_paper_rows': len(duplicate_identities),
        'papers_with_repeated_authors': int(duplicate_identities.paper_id.nunique()),
        'repeated_identity_groups_with_different_names': int(len(differing_names[['paper_id', 'author_id']].drop_duplicates())),
        'duplicate_position_rows': len(duplicate_positions), 'orphan_authorship_rows': len(orphan_links),
        'limitations': 'Candidate groups are not verified duplicates. Common names, different middle names, and multiple ORCIDs require source review. Shared coauthors only prioritize review. Initial-only names and reordered surnames are not exhaustively matched.',
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    (out_dir / 'name_candidates.json').write_text(json.dumps(rows, indent=2, ensure_ascii=False) + '\n')
    for name, frame in [('repeated_authors',duplicate_identities), ('possible_false_merges',differing_names), ('duplicate_positions',duplicate_positions), ('orcid_conflicts',conflicts)]:
        frame.to_csv(out_dir / f'{name}.csv', index=False)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kg-dir', required=True, type=Path)
    parser.add_argument('--out-dir', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.kg_dir, args.out_dir), indent=2))
