from __future__ import annotations

import json

from brunner.contract import load_output_contract
from brunner.staging import stage_challenge

from granular_mean.definition import ROOT, build_definition


def test_definition_and_contract_are_valid() -> None:
    definition = build_definition()
    definition.validate()
    contract = load_output_contract(
        definition.contract_path,
        expected_benchmark_id=definition.benchmark_id,
    )

    assert contract.work_unit_ids == (
        "a",
        "b",
        "cd",
        "e",
        "f",
        "g",
        "h",
    )
    assert len(contract.data["artifacts"]) == 7


def test_stage_preserves_task_and_excludes_trusted_material(
    tmp_path,
) -> None:
    definition = build_definition()
    contract = load_output_contract(definition.contract_path)
    destination = tmp_path / "staged"

    staged = stage_challenge(definition, contract, destination)
    prompt = (destination / "PROMPT.md").read_text()
    normalized_prompt = " ".join(prompt.split())

    assert staged.workspace == destination.resolve()
    assert "Implement the simulation described there in Python" in prompt
    assert "Do not look for another" in prompt
    assert "Use the paper as the authoritative source" in prompt
    assert (
        "its visible patterns must not be used to construct, prescribe, "
        "initialize, or transform the trajectories"
    ) in normalized_prompt
    assert "Panel a: Gamma=3.0, f*=0.27, 4 exported cycles." in prompt
    assert "square pattern" not in prompt
    assert "stripe pattern" not in prompt
    assert "alternating hexagons" not in prompt
    cases = json.loads((destination / "cases.json").read_text())["cases"]
    assert all("pattern" not in case for case in cases.values())
    assert "completed_units" in prompt
    assert "{{BRUNNER_OUTPUT_CONTRACT}}" not in prompt
    assert (destination / "sources/bizon1998a.pdf").is_file()
    assert not (destination / "reference").exists()
    assert not (destination / "figure1-paper.json").exists()
    assert (ROOT / "reference/paper/figure1-paper.json").is_file()
