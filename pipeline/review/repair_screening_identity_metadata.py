"""Fetch bounded primary bibliographic evidence for known screening conflicts."""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import time
from urllib.parse import quote
import xml.etree.ElementTree as ET
import requests
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pipeline.ingest.metadata_utils import strip_markup

DEFAULT = ROOT / "data/processed/model_runs/luna_v5_20261017/screening_correction_20261019"


def plain(value):
    return strip_markup(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT)
    args = parser.parse_args()
    base = args.root.parent / "fulltext_recovery_20261018/browser_full_pass_20261018/manual_chrome_batches_20261019/batch_001/retained_reason_triage_20261019.json"
    records = json.loads(base.read_text())["heuristic_flags"]["title_abstract_identity_concern"]
    out = args.root / "metadata_repair"
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "PsychedelicKnowledgeGraph/1.0 (bounded bibliographic identity audit)"
    calls = 0
    pubmed_lookups = 0
    for record in records:
        doi = record["doi"]
        key = __import__("hashlib").sha256(doi.encode()).hexdigest()[:20]
        target = out / (key + ".json")
        if target.exists():
            continue
        result = {"doi": doi, "original_title": record["study_title"], "status": "unresolved", "provenance": [], "fields": {}}
        url = "https://api.crossref.org/works/" + quote(doi, safe="")
        try:
            response = session.get(url, timeout=25)
            calls += 1
            response.raise_for_status()
            payload = response.json()
            (out / (key + ".crossref.json")).write_text(json.dumps(payload, ensure_ascii=False))
            message = payload["message"]
            if str(message.get("DOI", "")).lower() != doi:
                raise ValueError("Crossref DOI identity mismatch")
            result["fields"] = {"study_title": plain((message.get("title") or [""])[0]), "abstract": plain(message.get("abstract", "")), "publication_type": message.get("type", ""), "language": message.get("language", "")}
            result["provenance"].append({"provider": "Crossref", "url": url, "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()})
            time.sleep(.25)
            if not result["fields"]["abstract"] and pubmed_lookups < 10:
                pubmed_lookups += 1
                search = session.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params={"db": "pubmed", "retmode": "json", "term": doi + "[AID]", "retmax": 2}, timeout=25)
                calls += 1
                search.raise_for_status()
                pmids = search.json()["esearchresult"]["idlist"]
                time.sleep(.4)
                if len(pmids) == 1:
                    paper = session.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", params={"db": "pubmed", "retmode": "xml", "id": pmids[0]}, timeout=25)
                    calls += 1
                    paper.raise_for_status()
                    (out / (key + ".pubmed.xml")).write_text(paper.text)
                    xml = ET.fromstring(paper.text)
                    article = xml.find(".//PubmedArticle")
                    ids = [e.text.lower() for e in article.findall(".//ArticleId[@IdType='doi']") if e.text]
                    if doi not in ids:
                        raise ValueError("PubMed DOI identity mismatch")
                    title = article.find(".//ArticleTitle")
                    abstract = article.findall(".//Abstract/AbstractText")
                    result["fields"].update(study_title=plain("".join(title.itertext())) if title is not None else result["fields"]["study_title"], abstract=" ".join(plain("".join(a.itertext())) for a in abstract), language=" | ".join(a.text for a in article.findall(".//Language") if a.text))
                    result["provenance"].append({"provider": "PubMed", "pmid": pmids[0], "url": paper.url, "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()})
                    time.sleep(.4)
            if result["fields"].get("study_title") and len(result["fields"].get("abstract", "")) >= 100:
                result["status"] = "authoritative_title_and_abstract"
            else:
                result["status"] = "identity_confirmed_abstract_unavailable"
        except Exception as exc:
            result["error"] = str(exc)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(doi, result["status"], result["fields"].get("study_title", "")[:100], flush=True)
    print("API calls this execution:", calls, flush=True)


if __name__ == "__main__":
    main()
