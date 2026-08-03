from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from granular_mean.cases import CASES, FigureCase
from granular_mean.trajectory import Trajectory, load_trajectory


@dataclass(frozen=True)
class CaseFiles:
    case: FigureCase
    trajectory_path: Path
    particle_count: int
    box_width: float
    box_height: float
    seed: int
    simulation_cycle: int | None
    walltime_seconds: float | None

    def load_trajectory(self) -> Trajectory:
        return load_trajectory(
            self.trajectory_path,
            self.case,
            expected_particles=self.particle_count,
        )


@dataclass(frozen=True)
class ArtifactCollection:
    root: Path
    manifest_path: Path
    implementation: dict[str, object]
    cases: dict[str, CaseFiles]


def _safe_file(root: Path, value: str) -> Path:
    if not value:
        raise ValueError("manifest paths cannot be empty")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"manifest path escapes collection root: {value}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(
                f"manifest path contains a symlink: {value}"
            )
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"manifest path escapes collection root: {value}")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _required_mapping(
    value: object,
    *,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def load_collection(
    manifest_path: Path,
    *,
    expected_language: str,
) -> ArtifactCollection:
    manifest_path = manifest_path.resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    root = manifest_path.parent
    data = _required_mapping(
        json.loads(manifest_path.read_text()),
        label="collection manifest",
    )
    if data.get("schema_version") != "1.0":
        raise ValueError("unsupported collection schema version")
    implementation = _required_mapping(
        data.get("implementation"),
        label="implementation",
    )
    if implementation.get("language") != expected_language:
        raise ValueError(
            "collection implementation language is "
            f"{implementation.get('language')!r}, "
            f"expected {expected_language!r}"
        )
    case_values = _required_mapping(data.get("cases"), label="cases")
    if set(case_values) != set(CASES):
        raise ValueError(
            "collection cases differ from the benchmark cases: "
            f"{sorted(case_values)}"
        )

    cases = {}
    for case_id, case in CASES.items():
        value = _required_mapping(
            case_values[case_id],
            label=f"case {case_id}",
        )
        required = {
            "trajectory",
            "particle_count",
            "box_width",
            "box_height",
            "seed",
        }
        missing = required - set(value)
        if missing:
            raise ValueError(
                f"case {case_id} is missing fields: {sorted(missing)}"
            )
        cases[case_id] = CaseFiles(
            case=case,
            trajectory_path=_safe_file(root, str(value["trajectory"])),
            particle_count=int(value["particle_count"]),
            box_width=float(value["box_width"]),
            box_height=float(value["box_height"]),
            seed=int(value["seed"]),
            simulation_cycle=(
                int(value["simulation_cycle"])
                if "simulation_cycle" in value
                else None
            ),
            walltime_seconds=(
                float(value["walltime_seconds"])
                if "walltime_seconds" in value
                else None
            ),
        )
    return ArtifactCollection(
        root=root,
        manifest_path=manifest_path,
        implementation=implementation,
        cases=cases,
    )


def validate_reference_collection(
    reference_root: Path,
    *,
    load_trajectories: bool = False,
) -> ArtifactCollection:
    collection = load_collection(
        reference_root / "generated/manifest.json",
        expected_language="updated-c",
    )
    if load_trajectories:
        for case_id, case_files in collection.cases.items():
            trajectory = case_files.load_trajectory()
            expected_cycles = CASES[case_id].export_cycles
            if trajectory.cycle_count != expected_cycles:
                raise ValueError(
                    f"reference case {case_id} contains "
                    f"{trajectory.cycle_count} cycles, "
                    f"expected {expected_cycles}"
                )
    return collection
