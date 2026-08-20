from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

import numpy as np

from granular_mean.alignment import (
    best_cycle_shift,
    shift_profile_by_cycles,
)
from granular_mean.collection import ArtifactCollection, CaseFiles
from granular_mean.metrics import (
    collision_rates,
    order_parameter_profile,
    phase_conditioned,
    profile_error,
    scalar_profiles,
)
from granular_mean.overlaps import overlap_profiles
from granular_mean.report import representative_images
from granular_mean.trajectory import last_cycles


CANDIDATE_DATA_ERRORS = (
    BadZipFile,
    EOFError,
    IndexError,
    KeyError,
    OSError,
    TypeError,
    ValueError,
)


def jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {
            key: jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def _compare_profile_sets(
    reference: dict[str, np.ndarray],
    candidate: dict[str, np.ndarray],
    shift_cycles: int,
) -> dict[str, object]:
    shifted = {
        name: shift_profile_by_cycles(value, shift_cycles)
        for name, value in candidate.items()
    }
    return {
        "errors": {
            name: profile_error(value, shifted[name])
            for name, value in reference.items()
        },
        "reference_cycle_means": {
            name: np.mean(value[:-1], axis=0)
            for name, value in reference.items()
        },
        "candidate_cycle_means": {
            name: np.mean(value[:-1], axis=0)
            for name, value in shifted.items()
        },
    }


def _compare_dynamics(
    reference: dict[str, np.ndarray],
    candidate: dict[str, np.ndarray],
    shift_cycles: int,
) -> dict[str, object]:
    shifted = {
        name: shift_profile_by_cycles(value, shift_cycles)
        for name, value in candidate.items()
    }
    reference_phase = {
        name: phase_conditioned(value)
        for name, value in reference.items()
    }
    candidate_phase = {
        name: phase_conditioned(value)
        for name, value in shifted.items()
    }
    return {
        "full_profile": {
            name: profile_error(reference[name], shifted[name])
            for name in reference
        },
        "phase_conditioned": {
            name: profile_error(
                reference_phase[name],
                candidate_phase[name],
            )
            for name in reference
        },
        "reference_phase_conditioned": reference_phase,
        "candidate_phase_conditioned": candidate_phase,
    }


def _paper_consistency(
    reference_case: CaseFiles,
    candidate_order: dict[str, np.ndarray],
    paper: dict[str, Any] | None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "candidate_cycle_means": {
            name: float(np.mean(value[:-1]))
            for name, value in candidate_order.items()
        },
        "expected_pattern": reference_case.case.pattern,
    }
    if paper is None:
        return result
    panel_names = paper["case_panels"][reference_case.case.case_id]
    comparable = ("dominant_wavelength", "q2", "q4", "q6")
    panel_means = {
        name: float(
            np.mean(
                [
                    paper["panels"][panel]["metrics"][name]
                    for panel in panel_names
                ]
            )
        )
        for name in comparable
    }
    result["paper_panel_means"] = panel_means
    result["absolute_differences"] = {
        name: abs(
            panel_means[name]
            - result["candidate_cycle_means"][name]
        )
        for name in comparable
    }
    return result


def _case_evaluation(
    reference_case: CaseFiles,
    candidate_case: CaseFiles,
    *,
    include_overlaps: bool,
    paper: dict[str, Any] | None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    full_reference = reference_case.load_trajectory()
    full_candidate = candidate_case.load_trajectory()
    comparison_cycles = min(
        full_reference.cycle_count,
        full_candidate.cycle_count,
    )
    reference = last_cycles(full_reference, comparison_cycles)
    candidate = last_cycles(full_candidate, comparison_cycles)

    reference_scalars = scalar_profiles(reference)
    candidate_scalars = scalar_profiles(candidate)
    alignment_names = ("com_height", "layer_depth", "rms_velocity")
    shift, alignment_error = best_cycle_shift(
        {
            name: reference_scalars[name]
            for name in alignment_names
        },
        {
            name: candidate_scalars[name]
            for name in alignment_names
        },
        reference_case.case.temporal_period,
    )

    reference_order = order_parameter_profile(
        reference,
        reference_case.box_width,
    )
    candidate_order = order_parameter_profile(
        candidate,
        candidate_case.box_width,
    )
    scalar_names = (
        "com_height",
        "layer_depth",
        "mean_velocity",
        "rms_velocity",
    )
    rotational_names = (
        "mean_spin",
        "rms_spin",
        "rotational_kinetic_energy",
    )
    reference_collisions = collision_rates(reference)
    candidate_collisions = collision_rates(candidate)
    result: dict[str, object] = {
        "status": "complete",
        "simulation": {
            "cycle": candidate_case.simulation_cycle,
            "walltime_seconds": candidate_case.walltime_seconds,
            "reference_particle_count": reference.particle_count,
            "candidate_particle_count": candidate.particle_count,
            "reference_export_cycles": full_reference.cycle_count,
            "candidate_export_cycles": full_candidate.cycle_count,
            "expected_candidate_export_cycles": (
                candidate_case.case.export_cycles
            ),
            "comparison_cycles": comparison_cycles,
            "export_cycle_count_matches": (
                full_candidate.cycle_count
                == candidate_case.case.export_cycles
            ),
        },
        "alignment": {
            "integer_drive_cycle_shift": shift,
            "normalized_rmse": alignment_error,
        },
        "updated_c_fidelity": _compare_profile_sets(
            reference_order,
            candidate_order,
            shift,
        ),
        "paper_consistency": _paper_consistency(
            reference_case,
            candidate_order,
            paper,
        ),
        "scalar_dynamics": _compare_dynamics(
            {
                name: reference_scalars[name]
                for name in scalar_names
            },
            {
                name: candidate_scalars[name]
                for name in scalar_names
            },
            shift,
        ),
        "rotational_dynamics": _compare_dynamics(
            {
                name: reference_scalars[name]
                for name in rotational_names
            },
            {
                name: candidate_scalars[name]
                for name in rotational_names
            },
            shift,
        ),
        "collision_rates": {
            "columns": [
                "ball_ball",
                "stationary_wall",
                "bottom_plate",
            ],
            "reference": reference_collisions,
            "candidate": candidate_collisions,
            "errors": {
                name: profile_error(
                    reference_collisions[name],
                    (
                        shift_profile_by_cycles(
                            candidate_collisions[name],
                            shift,
                        )
                        if name == "phase_conditioned"
                        else candidate_collisions[name]
                    ),
                )
                for name in ("total", "phase_conditioned")
            },
        },
    }
    if include_overlaps:
        reference_overlaps = overlap_profiles(
            reference,
            reference_case.box_width,
            reference_case.box_height,
        )
        candidate_overlaps = overlap_profiles(
            candidate,
            candidate_case.box_width,
            candidate_case.box_height,
        )
        shifted_candidate = shift_profile_by_cycles(
            candidate_overlaps,
            shift,
        )
        result["overlaps"] = {
            "columns": [
                "ball_ball",
                "stationary_wall",
                "bottom_plate",
            ],
            "reference_total": reference_overlaps.sum(axis=0),
            "candidate_total": candidate_overlaps.sum(axis=0),
            "error": profile_error(
                reference_overlaps,
                shifted_candidate,
            ),
            "reference_phase_conditioned": phase_conditioned(
                reference_overlaps
            ),
            "candidate_phase_conditioned": phase_conditioned(
                shifted_candidate
            ),
        }

    images = representative_images(
        reference_case.case.case_id,
        reference,
        candidate,
        reference_order,
        shift,
        reference_case.box_width,
        candidate_case.box_width,
    )
    return result, images


def evaluate_collections(
    reference: ArtifactCollection,
    candidate: ArtifactCollection,
    *,
    include_overlaps: bool,
    paper_path: Path | None,
) -> tuple[dict[str, Any], dict[str, list[dict[str, object]]]]:
    paper = None
    if paper_path is not None and paper_path.is_file():
        paper = json.loads(paper_path.read_text())

    case_results = {}
    report_images = {}
    for case_id in reference.cases:
        try:
            case_result, case_images = _case_evaluation(
                reference.cases[case_id],
                candidate.cases[case_id],
                include_overlaps=include_overlaps,
                paper=paper,
            )
        except CANDIDATE_DATA_ERRORS as error:
            candidate_case = candidate.cases[case_id]
            case_result = {
                "status": "failed",
                "simulation": {
                    "cycle": candidate_case.simulation_cycle,
                    "walltime_seconds": candidate_case.walltime_seconds,
                    "candidate_particle_count": candidate_case.particle_count,
                    "expected_candidate_export_cycles": (
                        candidate_case.case.export_cycles
                    ),
                    "export_cycle_count_matches": False,
                },
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            }
            case_images = []
        case_results[case_id] = case_result
        report_images[case_id] = case_images

    failed_cases = sorted(
        case_id
        for case_id, case in case_results.items()
        if case["status"] == "failed"
    )
    contract_complete = all(
        case["status"] == "complete"
        and case["simulation"]["export_cycle_count_matches"]
        for case in case_results.values()
    )
    details = {
        "schema_version": "1.0",
        "contract_completion": {
            "complete": contract_complete,
            "cases": sorted(candidate.cases),
            "failed_cases": failed_cases,
        },
        "include_overlaps": include_overlaps,
        "cases": case_results,
    }
    return jsonable(details), report_images


def mean_pattern_normalized_rmse(
    details: dict[str, Any],
) -> float | None:
    errors = [
        metric["normalized_rmse"]
        for case in details["cases"].values()
        if case["status"] == "complete"
        for metric in case["updated_c_fidelity"]["errors"].values()
    ]
    if not errors:
        return None
    return float(np.mean(errors))
