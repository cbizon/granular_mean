from __future__ import annotations

import json

import numpy as np

from granular_mean.collection import load_collection
from granular_mean.evaluation import (
    evaluate_collections,
    jsonable,
    mean_pattern_normalized_rmse,
)
from granular_mean.report import (
    rewrite_archived_comparison_report,
    write_comparison_report,
)


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
    assert "Phase-conditioned physical dynamics" in rendered
    assert "Center-of-mass height" in rendered
    assert "Mean vertical velocity" in rendered
    assert "Phase-conditioned rotational dynamics" in rendered
    assert "Rotational kinetic energy" in rendered
    assert "Collision rates per particle per cycle" in rendered
    assert "Total overlap counts" in rendered
    assert "reference-line" in rendered
    assert "candidate-line" in rendered
    assert "<svg" in rendered

    details_path = tmp_path / "details.json"
    details_path.write_text(json.dumps(jsonable(details)))
    archived = output.read_text()
    regenerated_path = rewrite_archived_comparison_report(
        details_path,
        output,
    )
    regenerated = regenerated_path.read_text()
    assert output.read_text() == archived
    assert regenerated_path.name == "comparison-physical.html"
    assert "Phase-conditioned physical dynamics" in regenerated
    assert "Total overlap counts" in regenerated


def test_candidate_validation_failure_is_recorded_per_case(
    tmp_path,
    collection_factory,
) -> None:
    reference = load_collection(
        collection_factory("reference-failure", language="updated-c"),
        expected_language="updated-c",
    )
    candidate_manifest = collection_factory(
        "candidate-failure",
        language="python",
    )
    candidate = load_collection(
        candidate_manifest,
        expected_language="python",
    )
    bad_path = candidate.cases["a"].trajectory_path
    with np.load(bad_path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    arrays["drive_phase"] = arrays["drive_phase"] + 0.01
    np.savez(bad_path, **arrays)

    details, images = evaluate_collections(
        reference,
        candidate,
        include_overlaps=False,
        paper_path=None,
    )

    assert details["contract_completion"]["complete"] is False
    assert details["contract_completion"]["failed_cases"] == ["a"]
    assert details["cases"]["a"]["status"] == "failed"
    assert details["cases"]["a"]["error"]["type"] == "ValueError"
    assert details["cases"]["b"]["status"] == "complete"
    assert images["a"] == []
    assert mean_pattern_normalized_rmse(details) == 0.0

    output = tmp_path / "failed-comparison.html"
    write_comparison_report(details, images, output)
    rendered = output.read_text()
    assert "not evaluated" in rendered
    assert "phase-zero 32-bin cycle grid" in rendered
