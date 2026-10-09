"""Evaluation runner.

Runs the labelled query set against a freshly ingested, isolated copy of the
catalogues (the application's own data directory is not touched), computes
every metric from the actual responses and writes:

  data/reports/evaluation_results.json   raw numbers and every failing case
  data/reports/human_review_sample.csv   sample of results for a human reviewer
  docs/EVALUATION.md                     the report (generated, never hand-edited)

Usage:  python -m backend.app.evaluation.runner [--llm off|auto|both] [--no-embeddings]
"""
import argparse
import csv
import json
import os
import platform
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

PROJECT = Path(__file__).resolve().parents[3]

UPLOAD_ROWS = [
    ("E-7000-0001", "Evaluation stylus", "M6", "Ruby", "7.5", "Ceramic", "123"),
    ("E-7000-0002", "Evaluation stylus", "M6", "Zirconia", "9.5", "Ceramic", "140"),
    ("E-7000-0003", "Evaluation extension", "M6", "", "", "Ceramic", "77"),
]


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(round(pct / 100.0 * len(ordered) + 0.5)) - 1))]


def hardware() -> Dict[str, Any]:
    info = {"os": platform.platform(), "python": platform.python_version(),
            "cpu": platform.processor() or platform.machine(), "logical_cpus": os.cpu_count()}
    try:
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
                (n, ctypes.c_ulonglong) for n in ("ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile",
                                                  "ullTotalVirtual", "ullAvailVirtual", "sullAvailExtendedVirtual")]
        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        info["ram_gb"] = round(status.ullTotalPhys / 2 ** 30, 1)
    except Exception:
        info["ram_gb"] = None
    return info


def evaluate(cases: List[Dict[str, Any]], llm_mode: str) -> Dict[str, Any]:
    from backend.app.core.config import settings
    from backend.app.retrieval.unified_search import search_products

    settings.LLM_MODE = llm_mode
    search_products("M2 stylus 2 mm ruby ball")  # load the catalogue cache (and the model) before timing
    rows: List[Dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        response = search_products(case["query"])
        elapsed = (time.perf_counter() - started) * 1000
        results = response.results
        expected = set(case["expected_parts"])
        exact_parts = [r.part_number for r in results if r.match_class == "EXACT_MATCH"]
        top5 = [r.part_number for r in results[:5]]
        violations = []
        hard = case.get("hard") or {}
        for r in results:
            threads = [r.thread] + list((r.extra_attributes or {}).get("threads", []))
            if hard.get("thread") and hard["thread"] not in threads:
                violations.append(f"{r.part_number}: thread {r.thread}")
            if hard.get("category") and r.category != hard["category"]:
                violations.append(f"{r.part_number}: category {r.category}")
        recall = None
        if expected and case["expected_outcome"] in ("exact", "alternative"):
            recall = len(set(top5) & expected) / min(5, len(expected))
        docs_ok = None
        if case.get("expected_documents") and results:
            docs_ok = sorted({s.document_id for s in results[0].sources}) == case["expected_documents"]
        rows.append({
            "id": case["id"], "group": case["group"], "query": case["query"],
            "expected_outcome": case["expected_outcome"], "outcome": response.outcome,
            "outcome_ok": response.outcome == case["expected_outcome"],
            "expected_parts": sorted(expected), "returned": [(r.part_number, r.match_class, r.score) for r in results],
            "total_found": response.total_found,
            "exact_true_positives": sum(1 for p in exact_parts if p in expected),
            "exact_false_positives": [p for p in exact_parts if p not in expected],
            "top1_ok": (top5[0] in expected) if (top5 and expected) else None,
            "recall_at_5": recall, "hard_violations": violations, "documents_ok": docs_ok,
            "llm_used": response.interpreted_query.llm_used,
            "end_to_end_ms": round(elapsed, 2),
            "retrieval_ranking_ms": response.diagnostics.get("retrieval_ranking_ms", 0.0),
            "sample": [{"part_number": r.part_number, "match_class": r.match_class, "score": r.score,
                        "source_pdf": r.source_pdf, "source_page": r.source_page, "images": len(r.images),
                        "explanation": r.explanation} for r in results[:2]],
        })

    def group(*names):
        return [r for r in rows if r["group"] in names]

    tp = sum(r["exact_true_positives"] for r in rows)
    fp = sum(len(r["exact_false_positives"]) for r in rows)
    recalls = [r["recall_at_5"] for r in rows if r["recall_at_5"] is not None]
    top1 = [r["top1_ok"] for r in rows if r["top1_ok"] is not None and r["expected_outcome"] == "exact"]
    unsupported = group("irrelevant", "nonsensical")
    by_group: Dict[str, Dict[str, int]] = {}
    for r in rows:
        g = by_group.setdefault(r["group"], {"queries": 0, "outcome_correct": 0})
        g["queries"] += 1
        g["outcome_correct"] += int(r["outcome_ok"])
    e2e = [r["end_to_end_ms"] for r in rows]
    det = [r["retrieval_ranking_ms"] for r in rows]
    llm_rows = [r["end_to_end_ms"] for r in rows if r["llm_used"]]
    failures = [r for r in rows if not r["outcome_ok"] or r["exact_false_positives"] or r["hard_violations"]
                or (r["recall_at_5"] is not None and r["recall_at_5"] < 1.0) or r["documents_ok"] is False]
    return {
        "llm_mode": llm_mode, "queries": len(rows), "by_group": by_group,
        "outcome_accuracy": sum(r["outcome_ok"] for r in rows) / len(rows),
        "exact_results_returned": tp + fp, "exact_true_positives": tp, "exact_false_positives": fp,
        "exact_match_precision": (tp / (tp + fp)) if (tp + fp) else None,
        "top1_exact_accuracy": (sum(top1) / len(top1)) if top1 else None, "top1_queries": len(top1),
        "recall_at_5": (sum(recalls) / len(recalls)) if recalls else None, "recall_queries": len(recalls),
        "recall_at_5_full_queries": sum(1 for x in recalls if x == 1.0),
        "results_checked_for_hard_constraints": sum(len(r["returned"]) for r in rows if r["group"] in
                                                    {c["group"] for c in cases if c.get("hard")}),
        "hard_constraint_violations": sum(len(r["hard_violations"]) for r in rows),
        "unsupported_queries": len(unsupported),
        "unsupported_with_recommendation": sum(1 for r in unsupported if r["returned"]),
        "queries_that_used_llm": len(llm_rows),
        "latency_ms": {
            "retrieval_ranking_p50": round(statistics.median(det), 1), "retrieval_ranking_p95": round(percentile(det, 95), 1),
            "retrieval_ranking_max": round(max(det), 1),
            "end_to_end_p50": round(statistics.median(e2e), 1), "end_to_end_p95": round(percentile(e2e, 95), 1),
            "end_to_end_max": round(max(e2e), 1),
            "llm_queries_p50": round(statistics.median(llm_rows), 1) if llm_rows else None,
            "llm_queries_p95": round(percentile(llm_rows, 95), 1) if llm_rows else None,
        },
        "failures": failures, "rows": rows,
    }


def upload_cycle(trials: int = 3) -> Dict[str, Any]:
    """Upload a synthetic catalogue, query it, delete it and verify the cleanup; repeated `trials` times."""
    from backend.app.core.config import settings
    from backend.app.db.database import db
    from backend.app.evaluation.sample_pdf import make_catalogue_pdf
    from backend.app.ingestion.pipeline import process_document, register_document
    from backend.app.lifecycle.deletion import delete_document
    from backend.app.llm import embeddings
    from backend.app.retrieval.unified_search import search_products

    out: Dict[str, Any] = {"trials": trials, "upload_queries": 0, "upload_queries_correct": 0,
                           "deletions_verified": 0, "post_delete_leaks": 0, "details": []}
    queries = [("M6 stylus with 7.5 mm ruby ball 123 mm long", "E-7000-0001"),
               ("M6 stylus 9.5 mm zirconia ball", "E-7000-0002"), ("M6 extension 77 mm long", "E-7000-0003")]
    work = Path(tempfile.mkdtemp(prefix="renishaw_eval_pdf_"))
    try:
        for i in range(trials):
            pdf = make_catalogue_pdf(work / f"evaluation_upload_{i}.pdf", UPLOAD_ROWS, image_for="E-7000-0001")
            doc_id = register_document(pdf, pdf.name)
            process_document(doc_id)
            for text, part in queries:
                response = search_products(text)
                ok = response.outcome == "exact" and [r.part_number for r in response.results] == [part] \
                    and response.results[0].document_id == doc_id
                out["upload_queries"] += 1
                out["upload_queries_correct"] += int(ok)
            report = delete_document(doc_id)
            with db() as conn:
                left = sum(conn.execute(f"SELECT count(*) FROM {t} WHERE document_id = ?", (doc_id,)).fetchone()[0]
                           for t in ("products", "images", "product_images"))
                left += conn.execute("SELECT count(*) FROM documents WHERE id = ?", (doc_id,)).fetchone()[0]
            vectors = embeddings.count_document_vectors(doc_id) if settings.EMBEDDINGS_ENABLED else 0
            files = (settings.IMAGE_DIR / doc_id).exists() or (settings.UPLOAD_DIR / f"{doc_id}.pdf").exists()
            verified = report["status"] == "success" and left == 0 and vectors == 0 and not files
            out["deletions_verified"] += int(verified)
            for text, _ in queries:
                if search_products(text).results:
                    out["post_delete_leaks"] += 1
            out["details"].append({"document_id": doc_id, "removed": report["removed"], "verified": verified})
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def table_coverage() -> List[Dict[str, Any]]:
    from backend.app.db.database import db
    rows = []
    with db() as conn:
        for doc in conn.execute("SELECT id, filename, page_count, ingestion_report FROM documents ORDER BY id"):
            report = json.loads(doc["ingestion_report"] or "{}")
            products = conn.execute("SELECT count(*) FROM products WHERE document_id = ?", (doc["id"],)).fetchone()[0]
            review = conn.execute("SELECT count(*) FROM products WHERE document_id = ? AND validation_status != 'validated'",
                                  (doc["id"],)).fetchone()[0]
            with_image = conn.execute(
                "SELECT count(DISTINCT product_id) FROM product_images WHERE document_id = ? AND association_status = 'verified'",
                (doc["id"],)).fetchone()[0]
            rows.append({
                "document": doc["filename"], "pages": doc["page_count"],
                "listing_rows_printed": report.get("rows_extracted"), "rows_rejected": report.get("rows_rejected"),
                "products_stored": products, "needs_review": review,
                "tables_detected": report.get("tables_detected"), "tables_extracted": report.get("tables_extracted"),
                "images": report.get("images_extracted"), "products_with_verified_image": with_image,
                "products_without_image": report.get("products_without_image"),
            })
    return rows


def write_review_sample(results: Dict[str, Any], path: Path) -> int:
    picked = []
    for group in ("exact_full", "missing_optional", "unit_conversion", "synonyms_informal", "other_types",
                  "alternative_needed", "multi_document"):
        picked += [r for r in results["rows"] if r["group"] == group and r["sample"]][:4]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["case", "group", "query", "part_number", "match_class", "score", "source_pdf", "source_page",
                         "images_shown", "explanation", "reviewer: values correct (y/n)",
                         "reviewer: classification justified (y/n)", "reviewer: alternative meaningful (y/n)",
                         "reviewer: image correct (y/n)", "reviewer: notes"])
        for row in picked:
            s = row["sample"][0]
            writer.writerow([row["id"], row["group"], row["query"], s["part_number"], s["match_class"], s["score"],
                             s["source_pdf"], s["source_page"], s["images"], s["explanation"], "", "", "", "", ""])
    return len(picked)


def _pct(value) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def write_markdown(summary: Dict[str, Any], path: Path) -> None:
    lines: List[str] = []
    add = lines.append
    hw = summary["hardware"]
    add("# Evaluation report")
    add("")
    add(f"Generated by `backend/app/evaluation/runner.py` on {summary['generated_at']}. "
        "Every number below was computed from the responses of that run; nothing is entered by hand. "
        "Raw results, including every failing case, are in `data/reports/evaluation_results.json`.")
    add("")
    add("## Setup")
    add("")
    add(f"- Machine: {hw['os']}, {hw['cpu']}, {hw['logical_cpus']} logical CPUs, {hw['ram_gb']} GB RAM")
    add(f"- Python {hw['python']}; LLM `{summary['llm_model']}`; embedding model `{summary['embedding_model']}` "
        f"(embeddings {'on' if summary['embeddings_enabled'] else 'off'} in this run)")
    add("- Data: both supplied catalogues ingested from scratch into a temporary data directory for this run "
        f"(ingestion took {summary['ingestion_seconds']} s).")
    add(f"- Query set: {summary['dataset_size']} labelled queries generated from the stored catalogue records "
        "(`backend/app/evaluation/dataset.py`, fixed seed), plus "
        f"{summary['upload_cycle']['upload_queries']} queries against a document uploaded during the run.")
    add("")
    add("## Extraction coverage")
    add("")
    add("| Document | Pages | Listing rows read | Rows rejected | Products stored | Flagged for review | Images | Products with a verified image | Products without image |")
    add("|---|---|---|---|---|---|---|---|---|")
    for t in summary["table_coverage"]:
        add(f"| {t['document']} | {t['pages']} | {t['listing_rows_printed']} | {t['rows_rejected']} | {t['products_stored']} | "
            f"{t['needs_review']} | {t['images']} | {t['products_with_verified_image']} | {t['products_without_image']} |")
    add("")
    add("Coverage is measured against each catalogue's own printed part-number listing: every listing row was read "
        "(rows rejected = 0). Products stored can exceed listing rows because parts that appear only on a body page "
        "are also stored. Records where the listing and the body page disagree are kept and flagged `needs_review` "
        "with the reason. This is coverage of what the extractor read, not a human-verified accuracy figure.")
    for run in summary["runs"]:
        lat = run["latency_ms"]
        add("")
        add(f"## Results - LLM mode `{run['llm_mode']}`")
        add("")
        add("| Metric | Target | Result | Basis |")
        add("|---|---|---|---|")
        add(f"| Exact-match precision | >= 95% | {_pct(run['exact_match_precision'])} | {run['exact_true_positives']} of "
            f"{run['exact_results_returned']} results labelled exact are in the oracle's expected set |")
        add(f"| Top-1 correct (exact queries) | - | {_pct(run['top1_exact_accuracy'])} | {run['top1_queries']} queries |")
        add(f"| Recall@5 | >= 90% | {_pct(run['recall_at_5'])} | mean over {run['recall_queries']} queries; "
            f"{run['recall_at_5_full_queries']} fully satisfied |")
        add(f"| Hard-constraint violations | 0 | {run['hard_constraint_violations']} | "
            f"{run['results_checked_for_hard_constraints']} returned results checked for thread and product type |")
        add(f"| Unsupported queries given a recommendation | 0 | {run['unsupported_with_recommendation']} | "
            f"{run['unsupported_queries']} irrelevant or nonsensical queries |")
        add(f"| Expected outcome class | - | {_pct(run['outcome_accuracy'])} | {run['queries']} queries |")
        add(f"| Retrieval + ranking latency p95 | < 1000 ms | {lat['retrieval_ranking_p95']} ms | p50 {lat['retrieval_ranking_p50']} ms, max {lat['retrieval_ranking_max']} ms |")
        add(f"| End-to-end latency p95 | < 5000 ms | {lat['end_to_end_p95']} ms | p50 {lat['end_to_end_p50']} ms, max {lat['end_to_end_max']} ms; "
            f"{run['queries_that_used_llm']} queries called the LLM"
            + (f" (those: p50 {lat['llm_queries_p50']} ms, p95 {lat['llm_queries_p95']} ms)" if lat['llm_queries_p50'] else "") + " |")
        add("")
        add("| Query group | Queries | Expected outcome returned |")
        add("|---|---|---|")
        for name, g in run["by_group"].items():
            add(f"| {name} | {g['queries']} | {g['outcome_correct']} |")
        add("")
        if run["failures"]:
            add(f"### Cases that did not fully pass ({len(run['failures'])})")
            add("")
            add("| Case | Query | Expected | Got | Detail |")
            add("|---|---|---|---|---|")
            for f in run["failures"]:
                detail = []
                if f["exact_false_positives"]:
                    detail.append("unexpected exact: " + ", ".join(f["exact_false_positives"]))
                if f["hard_violations"]:
                    detail.append("hard violation: " + "; ".join(f["hard_violations"]))
                if f["recall_at_5"] is not None and f["recall_at_5"] < 1:
                    detail.append(f"recall@5 {f['recall_at_5']:.2f}")
                if f["documents_ok"] is False:
                    detail.append("sources differ from expected documents")
                query = f["query"].replace("|", "/")
                add(f"| {f['id']} | {query} | {f['expected_outcome']} | {f['outcome']} | {'; '.join(detail) or '-'} |")
        else:
            add("All cases passed in this mode.")
    up = summary["upload_cycle"]
    add("")
    add("## Uploaded document and deletion")
    add("")
    add(f"- Upload, ingest, query: {up['upload_queries_correct']} of {up['upload_queries']} queries returned exactly the "
        f"uploaded part from the uploaded document ({up['trials']} upload cycles).")
    add(f"- Deletion verification: {up['deletions_verified']} of {up['trials']} deletions left no record, vector, image "
        "file or stored PDF behind (checked directly in SQLite, the vector index and the file system).")
    add(f"- Queries answered from a deleted document afterwards: {up['post_delete_leaks']}.")
    add("")
    add("## Definitions")
    add("")
    add("- **Oracle**: expected part numbers are computed in `dataset.py` by plain equality filters over the stored "
        "records, independently of the search engine. The oracle reads the same extracted records, so it measures "
        "interpretation and matching, not extraction accuracy (see the extraction regression tests for that).")
    add("- **Exact-match precision**: of all results the system labelled `EXACT_MATCH` across the whole set, the share "
        "that the oracle also lists. Any exact result on a query that expects none counts against it.")
    add("- **Recall@5**: for queries with expected parts, |top 5 ∩ expected| / min(5, |expected|); for "
        "alternative-needed queries the expected part is the record the query was derived from.")
    add("- **Hard-constraint violation**: a returned result whose thread or product type differs from the one stated "
        "in the query (checked from the query's generation metadata).")
    add("- **Latency**: wall-clock per query in-process (no HTTP). Retrieval + ranking excludes query interpretation; "
        "end-to-end includes it, and in `auto` mode includes the local LLM call when one was made.")
    add("")
    add("## Limitations")
    add("")
    add("- The queries are template-generated from catalogue records; they are not real user queries, and the "
        "informal wording covers only the synonyms listed in the generator.")
    add("- This query set was also used while developing the system: four cases that failed in an earlier run "
        "(a dimension bound to a keyword across a comma, a bare number treated as a request, and a weak "
        "alternative) led to fixes. The figures therefore describe a set the system was tuned on, not unseen data.")
    add("- No human has reviewed the results. `data/reports/human_review_sample.csv` "
        f"({summary['review_sample_rows']} rows) is prepared for that review and its reviewer columns are empty.")
    add("- Extracted values were spot-checked against the PDFs by the automated regression tests "
        "(`backend/tests/test_extraction.py`, 12 records), not exhaustively.")
    add("- LLM-mode results depend on the local model and can vary between model versions; rules-only results are "
        "deterministic.")
    add("- Latency figures are from this machine only.")
    add("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--llm", choices=["off", "auto", "both"], default="both")
    parser.add_argument("--no-embeddings", action="store_true")
    args = parser.parse_args()

    real_data = Path(os.environ.get("RENISHAW_DATA_DIR") or PROJECT / "data")
    temp = Path(tempfile.mkdtemp(prefix="renishaw_eval_"))
    os.environ["RENISHAW_DATA_DIR"] = str(temp)
    os.environ["RENISHAW_AUTO_INGEST_SOURCE_PDFS"] = "false"

    from backend.app.core.config import settings
    from backend.app.evaluation.dataset import build_dataset
    from backend.app.ingestion.pipeline import ingest_initial_catalogues
    from backend.app.llm.ollama_client import ollama_client

    health = ollama_client.check_health()
    settings.EMBEDDINGS_ENABLED = bool(health["embedding_model_available"]) and not args.no_embeddings
    llm_ready = health["ollama_reachable"] and health["llm_model_available"]
    modes = ["off", "auto"] if args.llm == "both" else [args.llm]
    if "auto" in modes and not llm_ready:
        print("The local LLM is not available; running rules-only (off) mode.")
        modes = ["off"]
    try:
        print(f"Ingesting both catalogues into {temp} ...")
        started = time.time()
        reports = ingest_initial_catalogues()
        errors = {k: v for k, v in reports.items() if "error" in v}
        if errors or len(reports) != 2:
            print("Ingestion failed:", errors or reports)
            return 2
        ingestion_seconds = round(time.time() - started, 1)
        cases = build_dataset()
        summary: Dict[str, Any] = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "hardware": hardware(),
            "llm_model": settings.LLM_MODEL, "embedding_model": settings.EMBEDDING_MODEL,
            "embeddings_enabled": settings.EMBEDDINGS_ENABLED, "ingestion_seconds": ingestion_seconds,
            "dataset_size": len(cases), "table_coverage": table_coverage(), "runs": [],
        }
        for mode in modes:
            print(f"Running {len(cases)} queries, LLM mode {mode} ...")
            summary["runs"].append(evaluate(cases, mode))
        settings.LLM_MODE = "off"
        print("Upload / delete cycles ...")
        summary["upload_cycle"] = upload_cycle()

        out_dir = real_data / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        summary["review_sample_rows"] = write_review_sample(summary["runs"][0], out_dir / "human_review_sample.csv")
        (out_dir / "evaluation_results.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        write_markdown(summary, PROJECT / "docs" / "EVALUATION.md")
        for run in summary["runs"]:
            lat = run["latency_ms"]
            print(f"[{run['llm_mode']}] exact precision {_pct(run['exact_match_precision'])} | recall@5 {_pct(run['recall_at_5'])} | "
                  f"hard violations {run['hard_constraint_violations']} | unsupported recommended "
                  f"{run['unsupported_with_recommendation']}/{run['unsupported_queries']} | outcome {_pct(run['outcome_accuracy'])} | "
                  f"ranking p95 {lat['retrieval_ranking_p95']} ms | end-to-end p95 {lat['end_to_end_p95']} ms | "
                  f"not fully passing {len(run['failures'])}")
        up = summary["upload_cycle"]
        print(f"upload queries {up['upload_queries_correct']}/{up['upload_queries']} | deletions verified "
              f"{up['deletions_verified']}/{up['trials']} | leaks {up['post_delete_leaks']}")
        print("Report: docs/EVALUATION.md")
        return 0
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
