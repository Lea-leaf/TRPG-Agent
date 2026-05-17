from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

from app.rag.retriever import TRPGHybridRetriever  # noqa: E402

DEFAULT_CASES_PATH = BACKEND_DIR / "tests" / "fixtures" / "rag_eval_cases.json"
DEFAULT_REPORT_PATH = BACKEND_DIR / "data" / "rag_build_reports" / "rag_baseline_eval.json"


@dataclass(slots=True)
class EvalCase:
    id: str
    query: str
    expected_terms: list[str]
    expected_category: str | None


def _load_cases(path: Path) -> list[EvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        EvalCase(
            id=item["id"],
            query=item["query"],
            expected_terms=list(item["expected_terms"]),
            expected_category=item.get("expected_category"),
        )
        for item in payload
    ]


def _hit_terms(text: str, expected_terms: list[str]) -> list[str]:
    return [term for term in expected_terms if term.lower() in text.lower()]


def _evaluate_case(retriever: TRPGHybridRetriever, case: EvalCase, top_k: int) -> dict[str, Any]:
    docs = retriever.search(case.query, top_k=top_k)
    joined = "\n".join(doc.page_content for doc in docs)
    hit_terms = _hit_terms(joined, case.expected_terms)
    category_hit = (
        case.expected_category is None
        or any(doc.metadata.get("category") == case.expected_category for doc in docs)
    )
    term_hit = len(hit_terms) == len(case.expected_terms)

    return {
        "id": case.id,
        "query": case.query,
        "passed": term_hit and category_hit,
        "term_hit": term_hit,
        "category_hit": category_hit,
        "hit_terms": hit_terms,
        "expected_terms": case.expected_terms,
        "expected_category": case.expected_category,
        "results": [
            {
                "category": doc.metadata.get("category"),
                "section": doc.metadata.get("section") or doc.metadata.get("title"),
                "source": doc.metadata.get("source"),
                "page_start": doc.metadata.get("page_start"),
                "page_end": doc.metadata.get("page_end"),
                "preview": " ".join(doc.page_content.split())[:260],
            }
            for doc in docs
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="运行规则 RAG 召回基线评测。")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--top-k", type=int, default=6)
    args = parser.parse_args()

    cases = _load_cases(args.cases)
    retriever = TRPGHybridRetriever()
    results = [_evaluate_case(retriever, case, args.top_k) for case in cases]
    passed = sum(1 for item in results if item["passed"])

    report = {
        "total": len(results),
        "passed": passed,
        "pass_rate": round(passed / len(results), 3) if results else 0,
        "top_k": args.top_k,
        "results": results,
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["total", "passed", "pass_rate", "top_k"]}, ensure_ascii=False, indent=2))
    print(f"Report: {args.report}")


if __name__ == "__main__":
    main()
