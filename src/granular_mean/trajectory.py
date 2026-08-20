from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from granular_mean.cases import MEAN_DIAMETER, PHASES_PER_CYCLE, FigureCase


REQUIRED_ARRAYS = (
    "time",
    "drive_phase",
    "positions",
    "velocities",
    "angular_velocities",
    "diameters",
    "plate_z",
    "plate_vz",
    "collision_counts",
)
PHASE_GRID_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Trajectory:
    path: Path
    time: np.ndarray
    drive_phase: np.ndarray
    positions: np.ndarray
    velocities: np.ndarray
    angular_velocities: np.ndarray
    diameters: np.ndarray
    plate_z: np.ndarray
    plate_vz: np.ndarray
    collision_counts: np.ndarray

    @property
    def frame_count(self) -> int:
        return int(self.time.shape[0])

    @property
    def particle_count(self) -> int:
        return int(self.diameters.shape[0])

    @property
    def cycle_count(self) -> int:
        return (self.frame_count - 1) // PHASES_PER_CYCLE


def _require_shape(
    name: str,
    value: np.ndarray,
    shape: tuple[int, ...],
) -> None:
    if value.shape != shape:
        raise ValueError(f"{name} has shape {value.shape}, expected {shape}")


def _require_real_finite(name: str, value: np.ndarray) -> None:
    if value.dtype.kind not in "fiu":
        raise ValueError(
            f"{name} must be a real numeric array, got {value.dtype}"
        )
    if not np.all(np.isfinite(value)):
        raise ValueError(f"{name} contains NaN or infinite values")


def _circular_grid_error(
    value: np.ndarray,
    expected: np.ndarray,
    *,
    period: float,
) -> float:
    difference = ((value - expected + period / 2.0) % period) - period / 2.0
    return float(np.max(np.abs(difference)))


def _normalized_drive_phase(
    value: np.ndarray,
    frame_count: int,
) -> np.ndarray:
    expected = (
        np.arange(frame_count, dtype=np.float64) % PHASES_PER_CYCLE
    ) / PHASES_PER_CYCLE
    if (
        _circular_grid_error(value, expected, period=1.0)
        <= PHASE_GRID_TOLERANCE
    ):
        return expected

    radians = expected * (2.0 * np.pi)
    if (
        _circular_grid_error(value, radians, period=2.0 * np.pi)
        <= PHASE_GRID_TOLERANCE * 2.0 * np.pi
    ):
        return expected

    raise ValueError(
        "drive_phase is not a phase-zero 32-bin cycle grid in normalized "
        "cycle fractions or radians"
    )


def load_trajectory(
    path: Path,
    case: FigureCase,
    expected_particles: int | None = None,
) -> Trajectory:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    with np.load(path, allow_pickle=False) as archive:
        names = set(archive.files)
        required = set(REQUIRED_ARRAYS)
        missing = required - names
        unexpected = names - required
        if missing:
            raise ValueError(f"{path} is missing arrays: {sorted(missing)}")
        if unexpected:
            raise ValueError(
                f"{path} contains unexpected arrays: {sorted(unexpected)}"
            )
        arrays = {
            name: np.asarray(archive[name])
            for name in REQUIRED_ARRAYS
        }

    for name, value in arrays.items():
        _require_real_finite(name, value)

    frame_count = int(arrays["time"].shape[0])
    if (
        frame_count <= PHASES_PER_CYCLE
        or (frame_count - 1) % PHASES_PER_CYCLE
    ):
        raise ValueError(
            "trajectory must contain one or more whole drive cycles"
        )
    particle_count = int(arrays["diameters"].shape[0])
    if expected_particles is not None and particle_count != expected_particles:
        raise ValueError(
            f"particle count is {particle_count}, "
            f"expected {expected_particles}"
        )
    if particle_count < 1:
        raise ValueError("trajectory contains no particles")

    _require_shape("time", arrays["time"], (frame_count,))
    _require_shape("drive_phase", arrays["drive_phase"], (frame_count,))
    _require_shape(
        "positions",
        arrays["positions"],
        (frame_count, particle_count, 3),
    )
    _require_shape(
        "velocities",
        arrays["velocities"],
        (frame_count, particle_count, 3),
    )
    _require_shape(
        "angular_velocities",
        arrays["angular_velocities"],
        (frame_count, particle_count, 3),
    )
    _require_shape("diameters", arrays["diameters"], (particle_count,))
    _require_shape("plate_z", arrays["plate_z"], (frame_count,))
    _require_shape("plate_vz", arrays["plate_vz"], (frame_count,))
    _require_shape(
        "collision_counts",
        arrays["collision_counts"],
        (frame_count - 1, 3),
    )

    if np.any(arrays["diameters"] <= 0):
        raise ValueError("all particle diameters must be positive")
    mean_diameter = float(np.mean(arrays["diameters"]))
    if not np.isclose(mean_diameter, MEAN_DIAMETER, rtol=1e-3, atol=1e-3):
        raise ValueError(
            f"mean particle diameter is {mean_diameter}, expected 1"
        )
    if np.any(np.diff(arrays["time"]) <= 0):
        raise ValueError("time must be strictly increasing")

    arrays["drive_phase"] = _normalized_drive_phase(
        arrays["drive_phase"],
        frame_count,
    )

    collision_counts = arrays["collision_counts"]
    if np.any(collision_counts < 0):
        raise ValueError("collision counts must be nonnegative")
    if collision_counts.dtype.kind == "f" and not np.all(
        collision_counts == np.floor(collision_counts)
    ):
        raise ValueError("collision counts must be integers")

    return Trajectory(path=path, **arrays)


def last_cycles(
    trajectory: Trajectory,
    cycle_count: int,
) -> Trajectory:
    if cycle_count < 1 or cycle_count > trajectory.cycle_count:
        raise ValueError(
            f"cannot select {cycle_count} cycles from "
            f"{trajectory.cycle_count}-cycle trajectory"
        )
    start = (trajectory.cycle_count - cycle_count) * PHASES_PER_CYCLE
    return Trajectory(
        path=trajectory.path,
        time=trajectory.time[start:],
        drive_phase=trajectory.drive_phase[start:],
        positions=trajectory.positions[start:],
        velocities=trajectory.velocities[start:],
        angular_velocities=trajectory.angular_velocities[start:],
        diameters=trajectory.diameters,
        plate_z=trajectory.plate_z[start:],
        plate_vz=trajectory.plate_vz[start:],
        collision_counts=trajectory.collision_counts[start:],
    )
