from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from granular_mean.cases import CASES, PHASES_PER_CYCLE


@pytest.fixture
def trajectory_factory(tmp_path: Path):
    def create(
        case_id: str,
        *,
        particle_count: int = 4,
        collision_value: int = 0,
        export_cycles: int | None = None,
        name: str | None = None,
    ) -> Path:
        case = CASES[case_id]
        cycle_count = export_cycles or case.export_cycles
        frames = cycle_count * PHASES_PER_CYCLE + 1
        time = np.arange(frames) / (
            PHASES_PER_CYCLE * case.normalized_frequency
        )
        phase = (
            np.arange(frames) % PHASES_PER_CYCLE
        ) / PHASES_PER_CYCLE
        positions = np.zeros(
            (frames, particle_count, 3),
            dtype=np.float32,
        )
        positions[:, :, 0] = np.arange(particle_count) * 2.0 + 1.0
        positions[:, :, 1] = np.arange(particle_count) * 2.0 + 1.0
        positions[:, :, 2] = 2.0
        velocities = np.zeros_like(positions)
        spins = np.zeros_like(positions)
        diameters = np.ones(particle_count, dtype=np.float64)
        plate_z = np.zeros(frames)
        plate_vz = np.ones(frames)
        counts = np.full(
            (frames - 1, 3),
            collision_value,
            dtype=np.int64,
        )
        output = tmp_path / (name or f"{case_id}.npz")
        np.savez(
            output,
            time=time,
            drive_phase=phase,
            positions=positions,
            velocities=velocities,
            angular_velocities=spins,
            diameters=diameters,
            plate_z=plate_z,
            plate_vz=plate_vz,
            collision_counts=counts,
        )
        return output

    return create


@pytest.fixture
def collection_factory(tmp_path: Path, trajectory_factory):
    def create(
        name: str,
        *,
        language: str,
        particle_count: int = 4,
        export_cycles: int | None = None,
    ) -> Path:
        root = tmp_path / name
        root.mkdir()
        cases = {}
        for case_id, case in CASES.items():
            source = trajectory_factory(
                case_id,
                particle_count=particle_count,
                export_cycles=export_cycles,
                name=f"{name}-{case_id}.npz",
            )
            trajectory = root / f"{case_id}.npz"
            shutil.copy2(source, trajectory)
            case_value = {
                "trajectory": trajectory.name,
                "particle_count": particle_count,
                "box_width": 100.0,
                "box_height": 52.6315789474,
                "seed": 16532,
            }
            if language == "python":
                case_value.update(
                    {
                        "simulation_cycle": (
                            case.equilibration_cycles
                            + (export_cycles or case.export_cycles)
                        ),
                        "walltime_seconds": 12.5,
                    }
                )
            cases[case_id] = case_value
        manifest = {
            "schema_version": "1.0",
            "implementation": {"language": language},
            "cases": cases,
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        return manifest_path

    return create
