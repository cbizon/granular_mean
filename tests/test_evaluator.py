from __future__ import annotations

import json
import shutil
import sys
from dataclasses import replace

from brunner.contract import load_output_contract
from brunner.evaluation import evaluation_spec, execute_evaluation
from brunner.reference import build_reference_manifest
from brunner.trial import TrialIdentity, create_trial

from granular_mean.cases import CASES
from granular_mean.definition import build_definition


def test_brunner_evaluates_identical_synthetic_collections(
    tmp_path,
    collection_factory,
    monkeypatch,
) -> None:
    definition = build_definition()
    contract = load_output_contract(definition.contract_path)
    reference_source = collection_factory(
        "reference-source",
        language="updated-c",
    )
    reference_root = tmp_path / "reference"
    generated = reference_root / "generated"
    shutil.copytree(reference_source.parent, generated)
    build_reference_manifest(
        reference_root,
        reference_root / "manifest.json",
        metadata={
            "benchmark_id": definition.benchmark_id,
            "benchmark_version": definition.version,
            "contract_sha256": contract.sha256,
        },
    )
    definition = replace(
        definition,
        reference=replace(
            definition.reference,
            root=reference_root,
        ),
    )
    trial = create_trial(
        definition,
        contract,
        tmp_path / "runs",
        TrialIdentity(
            test_id="synthetic",
            provider="codex",
            model="test-model",
            effort="low",
        ),
    )

    candidate_source = collection_factory(
        "candidate-source",
        language="python",
    )
    submission = trial / "workspace/submission"
    submission.mkdir()
    manifest = json.loads(candidate_source.read_text())
    for case_id in CASES:
        source = candidate_source.parent / f"{case_id}.npz"
        target = submission / f"{case_id}.npz"
        shutil.copy2(source, target)
        manifest["cases"][case_id]["trajectory"] = target.name
    (submission / "manifest.json").write_text(json.dumps(manifest))
    (submission / "run-status.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "submission_manifest": "submission/manifest.json",
                "completed_units": list(CASES),
                "limitations": [],
            }
        )
    )
    monkeypatch.setenv("GRANULAR_MEAN_INCLUDE_OVERLAPS", "false")

    spec = evaluation_spec(definition, contract)
    spec = replace(
        spec,
        command=(
            sys.executable,
            "-m",
            "granular_mean.evaluator",
        ),
        reference_validate_command=(
            sys.executable,
            "-m",
            "granular_mean.reference_validation",
        ),
    )
    result = execute_evaluation(
        spec,
        trial,
        reference_root=reference_root,
    )

    assert result["status"] == "complete"
    assert result["summary"]["contract_complete"] is True
    assert result["metrics"]["mean_pattern_normalized_rmse"] == 0.0
    assert (trial / "evaluation/comparison.html").is_file()
    assert (trial / "evaluation/details.json").is_file()
