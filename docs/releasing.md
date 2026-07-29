# Releasing and archiving

GitHub Releases are the source of versioned software snapshots. Zenodo archives
each release, registers a version-specific DOI, and links the software to an
archive in Software Heritage.

## One-time setup

1. Sign in to [Zenodo](https://zenodo.org/) with the GitHub account that owns the
   repository.
2. In the Zenodo profile menu, open **GitHub**, select **Sync now**, find
   `povilaskarvelis/psychedelics_knowledge_graph`, and enable it.
3. Link the creator's ORCID account to the Zenodo profile.
4. Complete these steps before publishing the first GitHub Release. Zenodo only
   ingests releases made after the repository is enabled.

The repository uses `CITATION.cff` as the shared GitHub and Zenodo metadata
source. Do not add `.zenodo.json` unless Zenodo-specific fields such as grants
or communities are required; when both files exist, Zenodo ignores
`CITATION.cff`.

## Release checklist

1. Choose the next [Semantic Version](https://semver.org/). Use `0.x` versions
   while public interfaces and data contracts may still change incompatibly.
2. Update `version` and `date-released` in `CITATION.cff`.
3. Add the release entry and comparison link to `CHANGELOG.md`.
4. Validate the citation file and run the relevant test suite.
5. Commit and push the release preparation to `main`.
6. Create an annotated tag and push it:

   ```bash
   git tag -a vX.Y.Z -m "Psychedelics Knowledge Graph vX.Y.Z"
   git push origin vX.Y.Z
   ```

7. Create the GitHub Release from that tag. Use the matching title
   `Psychedelics Knowledge Graph vX.Y.Z`. Summarize user-facing changes without
   repeating the version or date already displayed by GitHub.
8. Wait for Zenodo to finish processing the release. Verify its files,
   metadata, version-specific DOI, and Software Heritage archival status.
9. Add the version-specific DOI to `CITATION.cff` on `main`. Keep the stable
   Zenodo concept DOI badge and citation links in `README.md` up to date.

For reproducible research, cite the version-specific DOI. The concept DOI is
useful when referring to the evolving project without selecting one version.

## Software and data citations

The GitHub–Zenodo integration archives the repository source as a **Software**
record. It does not make the separately hosted, immutable Cloudflare R2 exports
part of that archived snapshot.

When the public bulk export is ready for reuse, publish each data snapshot as a
separate Zenodo **Dataset** record. Include the release manifest, checksums,
schemas, provenance documentation, and data files; link the dataset and software
records with related identifiers. This lets readers cite the software version
and the exact data snapshot independently.
