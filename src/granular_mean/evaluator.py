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
    evaluate_collections,
    mean_pattern_normalized_rmse,
)
from granular_mean.report import write_comparison_report


FALSE_VALUES = {"0", "false", "no"}


def main() -> int:
    evaluation_input = load_evaluation_input()
    if evaluation_input.reference_root is None:
        raise RuntimeError(
            "granular evaluation requires a trusted reference bundle"
        )

    reference = validate_reference_collection(
        evaluation_input.reference_root
    )
    candidate = load_collection(
        evaluation_input.submission.manifest_path,
        expected_language="python",
    )
    include_overlaps = (
        os.environ.get(
            "GRANULAR_MEAN_INCLUDE_OVERLAPS",
            "true",
        ).lower()
        not in FALSE_VALUES
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

    write_evaluation_result(
        evaluation_input,
        status="complete",
        summary={
            "contract_complete": details["contract_completion"][
                "complete"
            ],
            "cases_evaluated": len(details["cases"]),
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
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
