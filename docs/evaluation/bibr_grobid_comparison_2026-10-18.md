# BIBR and GROBID PDF extraction comparison

18 October 2026. Evaluation artifacts are in `data/processed/evaluation/bibr_grobid_20261018/`.

**Recommendation: use BIBR for evidence-bearing tables and difficult PDF layouts, while retaining GROBID for fast bulk processing and bibliographic fields.** This pilot supports a real table-extraction advantage and better front-matter extraction from BIBR. It does not establish a universal replacement: ordinary text retention is high for both, some reference fields are better in GROBID, and this BIBR cloud configuration is much slower.

## Local results

Both tools produced outputs for all eight PDFs. After the CPU reference-parser workaround, all eight BIBR exports passed its own blocking validation gate; warnings still identify omissions and fallbacks. These checks are AI-assisted and exploratory, with publisher/PMC XML as the reference and selected pages visually reviewed by Codex, rather than a separately human-annotated benchmark.

| Measure | GROBID | BIBR |
|---|---:|---:|
| DOI exact match | 7/8 | 8/8 |
| Author full-name F1 | 0.903 | 1.000 |
| Abstract ROUGE-L | 0.682 | 0.982 |
| Reference matching F1 | 0.974 | 0.981 |
| Matched-reference journal accuracy | 94.6% | 84.5% |
| Matched-reference volume accuracy | 97.9% | 96.0% |
| Matched-reference page accuracy | 94.0% | 93.3% |
| PDF-confirmed body character-fragment retention | 99.03% | 99.95% |
| PDF-confirmed body five-token-fragment retention | 93.66% | 99.73% |
| Printed table-cell text found anywhere in export | 85.4% | 99.1% |
| Printed table-cell text found in explicit table records | 34.4% | 99.1% |
| Time for the same first three sequential papers | 21.2 seconds | 670.3 seconds |

Scores are means over papers. Table means cover 923 eligible cell-text probes across seven papers; they measure text presence, not independently established cell or row accuracy. Character-fragment retention tolerates spacing and punctuation changes. Five-token scores are sensitive to chemical superscripts and word boundaries, which explains much of their larger apparent gap. Neither body metric measures the fraction of scientific facts correctly understood.

The first three timing pairs cover 56 PDF pages and ran without the later parallel BIBR worker. BIBR took about **32 times as long** on those pairs. Across all eight papers the per-paper medians were 3.0 seconds for GROBID and 261 seconds for BIBR. Those later timings include overlapping workers, and describe an Apple M4 Pro with 24 GB RAM plus Gemini API calls, not the authors' RTX 5090 configuration.

Under the authors' strict bibliographic pass rule, BIBR passes **6/8** and GROBID **2/8**. Their title scores are 6/8 and 3/8. Several failures are harmless scientific-typography differences; both tools fail the docking title and the kappa-receptor title under that rule. These pass rates should not be interpreted as whole-paper scientific accuracy. The reference-matching difference is small on this sample, while BIBR's table benefit includes source-verified recovery of omitted numeric outcomes.

The [per-paper comparison CSV](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/bibr_grobid_20261018/per_paper_comparison.csv) and [machine-readable summary](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/bibr_grobid_20261018/overall_comparison.json) contain the underlying scores. Eight purposively selected English PDFs do not support an unweighted corpus-wide accuracy estimate. The local test does not include a separate image-only scan cohort.

## Published evidence

BIBR's authors have released a [300-paper JATS benchmark](https://github.com/scienceverse/bibr-jats-eval), with gold records, per-paper scores, selection scripts, and a [detailed report](https://github.com/scienceverse/bibr-jats-eval/blob/main/docs/reports/2026-10-15-jats-eval-v1.md). Recomputing the published CSVs reproduces the reported paper-pass counts:

| Cohort | Papers | BIBR passes | GROBID passes | BIBR alone passes | GROBID alone passes |
|---|---:|---:|---:|---:|---:|
| Behavioural science | 200 | 182 (91.0%) | 123 (61.5%) | 61 | 2 |
| Other fields | 100 | 91 (91.0%) | 63 (63.0%) | 29 | 1 |

This checks the arithmetic of the authors' scores. Raw extraction outputs are not distributed, so this audit cannot independently verify each scored prediction. The gold and recent journal-based selection are public; the claimed pre-scoring freeze history and complete training-exclusion inputs are not publicly inspectable.

The pass rule requires a sufficiently similar title, exact DOI, author-name F1 of at least 0.9, and reference-matching F1 of at least 0.8. **It does not require correct body text, tables, statistical results, or a correct knowledge graph.** Abstract quality is reported separately and is not part of the paper-pass rule.

The reported held-out configuration used the fine-tuned Qwen3.5 4B extractor and PaddleOCR-VL-1.6 on an RTX 5090, against the full GROBID 0.9.0 image. The papers are recent, English, open access, and drawn from selected journals. Image-only scan results compare an OCR system with GROBID without OCR; they do not establish superiority to GROBID preceded by a separate OCR step.

The held-out behavioural-science reference-matching means are 0.933 for BIBR and 0.953 for GROBID. On the other fields they are 0.950 and 0.934. GROBID's journal, volume, page, and printed-reference DOI scores are generally stronger. Subsequent BIBR fixes raised the behavioural-science pass rate to 95.5% and reference matching to 0.971, but those are development results after inspecting this set. The authors disclose that distinction.

## Local test design

The paired pilot uses eight project PDFs, 217 pages, and 593 JATS reference entries. The sample covers two psilocybin cancer trials, animal behaviour, medicinal chemistry, receptor structures, docking, and a Frontiers qualitative study. It is a purposive sample with available PDF/JATS pairs, not a random corpus sample. None of its DOIs appears in the public 325-paper benchmark and pilot list; this does not prove exclusion from BIBR's private training or development data.

| Paper | PDF pages |
|---|---:|
| Griffiths 2016, psilocybin cancer trial, `10.1177/0269881116675513` | 17 |
| Ross 2016, psilocybin cancer trial, `10.1177/0269881116675512` | 16 |
| Salvinorin A and ketamine attention study, `10.1007/s00213-010-1834-7` | 23 |
| AMDA receptor study, `10.1021/jm800771x` | 47 |
| Human kappa-opioid receptor structure, `10.1038/nature10939` | 8 |
| Hallucinogen-activated serotonin receptor, `10.1016/j.cell.2020.08.024` | 38 |
| Bespoke receptor docking, `10.1038/s41586-022-05258-z` | 53 |
| Ketamine-assisted couple therapy, `10.3389/fpsyg.2026.1843151` | 15 |

Two additional candidate clinical PDFs were excluded during preparation because the DOI search returned no corresponding PMCID suitable for the JATS retrieval: `10.1016/S2215-0366(16)30065-7` and `10.1056/NEJMoa2206443`. Those exclusions happened before either parser was scored.

Gold comes from publisher/PMC JATS, using the authors' public projection script and checking fields against the PDF text layer. Every selected title and author surname was found in its PDF. One Nature 2012 abstract differed between the author manuscript JATS and the published PDF. Its answer key was corrected from the rendered published page before inspecting predictions or scoring; the original and corrected text are retained in `gold_corrections.json`. Gold scored against itself passes all eight papers.

Both tools receive the same complete PDFs. GROBID consolidation and BIBR Crossref enrichment are disabled. Missing predictions remain in the denominator. The primary bibliographic scores use BIBR's unmodified public evaluator, metrics version 5, and its public TEI converter.

- **GROBID:** the project's running `grobid/grobid:0.9.0-crf` container, with raw reference and affiliation strings included.
- **BIBR:** version 0.7.3, commit `cd7150ae49b817d5c817cf2189b472a484d9ec6e`, dependencies installed from its lockfile. Metadata uses Gemini 3.5 Flash Lite; cloud OCR uses the documented default Gemini 3 Flash Preview. Local layout/classifier/reference models use ONNX, references use the default NER parser and geometric segmentation, and `NER_DEVICE=cpu` is explicit.

**This is a supported Gemini configuration, not a replication of the authors' fine-tuned 4B/Paddle configuration.** The local GROBID CRF image also differs from their full image. Runtime results describe this machine and these settings.

Body-text diagnostics measure the retention of five-token text fragments from JATS main-body paragraphs. An additional source-only diagnostic restricts those fragments to ones also present in the PDF's native text, reducing manuscript-versus-published wording effects. These measure text coverage, not correct sentence order, section classification, semantic understanding, or downstream evidence extraction.

An exploratory, formatting-tolerant diagnostic uses 50-character fragments after removing spaces/punctuation and normalizing case and accents, again limited to fragments confirmed in the PDF. It was added after inspecting chemistry paragraphs with low token-fragment scores: four of the lowest-scoring paragraphs still had 99.75–100% normalized-character partial similarity in GROBID. Superscripts and word boundaries explain much of that apparent token loss. Both diagnostics are reported; token recall must not be read as the proportion of scientific facts retained. The comparison also credits GROBID's back-matter divisions, matching BIBR's complete non-reference text stream, rather than dropping text merely because GROBID labeled it an annex.

Table diagnostics measure the presence of printed multiword/numeric JATS cell text, both anywhere in the export and inside explicit table records. They do not establish correct row/column alignment. Rendered-page checks separately inspect selected numeric values and their columns.

## Operational findings

A plain pip installation encountered dependency-resolution failures. Installing the source checkout with the published `uv.lock` succeeded. The missing system `libmagic` dependency was installed separately. BIBR's first Nature smoke run failed in the NER model's CoreML execution provider, leaving references incomplete and quarantining the result. The CLI's CPU layout setting did not force the separate NER model onto CPU. An explicit `NER_DEVICE=cpu` smoke test passed with `CPUExecutionProvider`, without modifying BIBR's source. The failed attempt and interrupted initial batch are retained separately from the final CPU run.

The first three BIBR papers ran sequentially. The 53-page docking paper was later assigned to a second process to reduce waiting; the worker schedule is recorded in `protocol.json`. Summed per-paper seconds for overlapping work are not elapsed batch throughput. Runtime comparisons should use the initial sequential pairs or explicitly describe overlap. BIBR's export token counts do not fully meter the separate cloud OCR calls, and invoice cost was not measured.

The authors describe the Apple Silicon local 4B/2B configuration as experimental and only smoke-tested in their [limitations](https://bibr.org/limitations/). The hosted demo currently requires tester approval, so this pilot uses the documented cloud configuration and existing API credentials.

## Source checks

The Frontiers paper has one printed author, David O. Avruch. GROBID exported eight author records, including the handling editor, a reviewer, and people discussed in the paper. This independently reproduces the authors' reported Frontiers failure mode.

In Griffiths 2016, Table 2 on PDF page 5, the printed systolic-pressure row has low-dose `142.20 (2.45)` and high-dose `155.26 (2.87)***`. GROBID put both into one cell spanning two columns. BIBR retained two separate cells under the correct dose headings. Both also retained the diastolic-pressure and heart-rate values. This is a concrete table-structure improvement on an inspected example, not a corpus-wide table accuracy estimate.

The same PDF's Table 7, on page 10, provides a more consequential example. Its community-observer total scores are `81.62 (1.61)`, `93.79 (1.70)`, and `94.41 (1.66)` at baseline, after session 2, and six months. GROBID's TEI omits these values; BIBR retains them in their correct columns. The FACIT-Sp row is also retained by BIBR, including `44.92 (2.71)`, `68.13 (3.62)`, and `70.79 (3.17)`. These were checked against the rendered page. Preserving such outcome data is more relevant to this knowledge graph than a better author list alone.

The official title score is particularly sensitive to scientific typography. GROBID's readable titles for the AMDA, serotonin receptor, and docking papers fail because of spaces, hyphens, or subscript rendering. The Nature title uses a different representation of kappa. These failures need to be distinguished from Ross 2016, where the title is absent. A low official paper-pass rate alone therefore overstates the practical metadata loss on this sample.

BIBR has a counterexample in the Nature 2012 bibliography: it exports 41 entries against 49 in the PDF-checked answer key, with reference-region recovery and truncation warnings. In the Cell 2020 paper, the printed reference about the Hungarian algorithm has journal `J. Chem. Inf. Model`; GROBID preserves that field while BIBR leaves its structured journal field empty. Counting a discovered reference as a match does not establish that every field is correct.

## Implications for the knowledge graph

The current extraction code consumes source-packet text and explicit table records. BIBR's section/text tables and HTML tables would need an adapter into that packet format, with the original PDF hash, page locations, headings, labels, and column headers retained. Its JSON is not a direct replacement for the TEI stored by the GROBID converter. A successful schema check also needs to be distinguished from factual correctness and from a complete bibliography.

The strongest observed use case is recovering evidence-bearing tables from PDFs whose GROBID output loses values or cell structure. Combining that table content with GROBID's bibliography is a plausible design. The pilot does not test the downstream scientific extraction model or show how many additional correct graph relations such a combination would produce.

## Reproduction and artifacts

The benchmark script is `data/processed/evaluation/bibr_grobid_20261018/run_benchmark.py`. Its `prepare`, `run`, `run_bibr`, and `score` stages freeze gold, call GROBID, call BIBR, and calculate content diagnostics. Its `evaluate` stage runs BIBR's unmodified `python -m evaluation.evaluate` for both tools, calculates the content diagnostics, and writes the comparison CSV/JSON and final artifact hashes. Both tools use the same `gold` directory and `expected_ids.json`.

For BIBR, the experiment's environment overrides are `NER_DEVICE=cpu`, `ML_RUNTIME=onnx`, `OCR_BACKEND=gemini`, `OCR_VISION_MODEL=gemini-3-flash-preview`, `LLM_PROVIDER=google`, and `LLM_MODEL=gemini-3.5-flash-lite`. The Google API key is supplied through the environment. `run_bibr` resumes by skipping existing paper outputs; a fresh repeat requires archiving those outputs first. `--only-ids` assigns a subset to a worker; concurrent workers must have disjoint selections.

The directory preserves the cohort, input and gold hashes, raw JATS/provenance, gold PDF checks, TEI and JSON predictions, timings, logs, package versions, and the public-benchmark arithmetic audit. Model and configuration details also appear in BIBR's exports. Source clones and the locked Python environment are under `/tmp`; their exact Git commits are in `protocol.json`.
