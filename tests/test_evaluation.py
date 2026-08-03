from __future__ import annotations

from granular_mean.collection import load_collection
from granular_mean.evaluation import (
    evaluate_collections,
    mean_pattern_normalized_rmse,
)
from granular_mean.report import write_comparison_report


def test_identical_collections_have_zero_error_and_render_report(
    tmp_path,
    collection_factory,
) -> None:
    reference = load_collection(
        collection_factory("reference", language="updated-c"),
        expected_language="updated-c",
    )
    candidate = load_collection(
        collection_factory("candidate", language="python"),
        expected_language="python",
    )

    details, images = evaluate_collections(
        reference,
        candidate,
        include_overlaps=True,
        paper_path=None,
    )

    assert details["contract_completion"]["complete"] is True
    assert mean_pattern_normalized_rmse(details) == 0.0
    assert (
        details["cases"]["a"]["overlaps"]["error"][
            "normalized_rmse"
        ]
        == 0.0
    )
    assert len(images["cd"]) == 2

    output = tmp_path / "comparison.html"
    write_comparison_report(details, images, output)
    rendered = output.read_text()
    assert "Granular Figure 1 comparison" in rendered
    assert "Updated-C reference" in rendered
    assert "white is higher" in rendered
