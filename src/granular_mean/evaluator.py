from __future__ import annotations

import json
import os

from brunner.evaluator import (
    load_evaluation_input,
    write_evaluation_result,
)

from granular_mean.collection import (
    load_collection,
    validate_reference_collection,
)
from granular_mean.evaluation import (
    CANDIDATE_DATA_ERRORS,
    evaluate_collections,
    mean_pattern_normalized_rmse,
)
from granular_mean.report import write_comparison_report


FALSE_VALUES = {"0", "false", "no"}


def _collection_failure_details(
    error: BaseException,
    *,
    include_overlaps: bool,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "contract_completion": {
            "complete": False,
            "cases": [],
            "failed_cases": [],
        },
        "include_overlaps": include_overlaps,
        "cases": {},
        "collection_error": {
            "type": type(error).__name__,
            "message": str(error),
        },
    }


def main() -> int:
    evaluation_input = load_evaluation_input()
    if evaluation_input.reference_root is None:
        raise RuntimeError(
            "granular evaluation requires a trusted reference bundle"
        )

    reference = validate_reference_collection(
        evaluation_input.reference_root
    )
    include_overlaps = (
        os.environ.get(
            "GRANULAR_MEAN_INCLUDE_OVERLAPS",
            "true",
        ).lower()
        not in FALSE_VALUES
    )
    try:
        candidate = load_collection(
            evaluation_input.submission.manifest_path,
            expected_language="python",
        )
        details, images = evaluate_collections(
            reference,
            candidate,
            include_overlaps=include_overlaps,
            paper_path=(
                evaluation_input.reference_root
                / "paper/figure1-paper.json"
            ),
        )
    except CANDIDATE_DATA_ERRORS as error:
        details = _collection_failure_details(
            error,
            include_overlaps=include_overlaps,
        )
        images = {}

    details_path = (
        evaluation_input.trial_root / "evaluation/details.json"
    )
    details_path.write_text(
        json.dumps(details, indent=2, sort_keys=True) + "\n"
    )
    report_path = (
        evaluation_input.trial_root / "evaluation/comparison.html"
    )
    write_comparison_report(details, images, report_path)

    failed_cases = details["contract_completion"]["failed_cases"]
    collection_error = details.get("collection_error")
    failed = bool(failed_cases or collection_error)
    error = None
    if failed:
        error = {
            "type": "CandidateDataInvalid",
            "message": (
                str(collection_error["message"])
                if collection_error
                else "candidate trajectory validation failed"
            ),
            "failed_cases": failed_cases,
        }

    write_evaluation_result(
        evaluation_input,
        status="failed" if failed else "complete",
        summary={
            "contract_complete": details["contract_completion"][
                "complete"
            ],
            "cases_evaluated": len(details["cases"]),
            "cases_failed": failed_cases,
            "include_overlaps": include_overlaps,
        },
        metrics={
            "mean_pattern_normalized_rmse": (
                mean_pattern_normalized_rmse(details)
            ),
            "cases": details["cases"],
        },
        reports=[
            {
                "path": "evaluation/comparison.html",
                "media_type": "text/html",
                "title": "Granular Figure 1 comparison",
                "primary": True,
            },
            {
                "path": "evaluation/details.json",
                "media_type": "application/json",
                "title": "Complete deterministic metrics",
            },
        ],
        error=error,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
