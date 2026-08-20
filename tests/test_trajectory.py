from __future__ import annotations

import numpy as np
import pytest

from granular_mean.cases import CASES
from granular_mean.trajectory import load_trajectory


def test_loads_valid_normalized_trajectory(trajectory_factory) -> None:
    trajectory = load_trajectory(
        trajectory_factory("a"),
        CASES["a"],
        expected_particles=4,
    )

    assert trajectory.frame_count == 129
    assert trajectory.particle_count == 4
    assert trajectory.cycle_count == 4


def test_loads_radian_drive_phase_as_normalized_cycle_fraction(
    tmp_path,
    trajectory_factory,
) -> None:
    source = trajectory_factory("a")
    with np.load(source, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    arrays["drive_phase"] = arrays["drive_phase"] * (2.0 * np.pi)
    radians = tmp_path / "radians.npz"
    np.savez(radians, **arrays)

    trajectory = load_trajectory(radians, CASES["a"], expected_particles=4)

    expected = (np.arange(trajectory.frame_count) % 32) / 32
    np.testing.assert_array_equal(trajectory.drive_phase, expected)


def test_rejects_unexpected_arrays(
    tmp_path,
    trajectory_factory,
) -> None:
    source = trajectory_factory("a")
    with np.load(source, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    arrays["debug"] = np.asarray([1])
    bad = tmp_path / "unexpected.npz"
    np.savez(bad, **arrays)

    with pytest.raises(ValueError, match="unexpected arrays"):
        load_trajectory(bad, CASES["a"])


def test_rejects_non_normalized_mean_diameter(
    tmp_path,
    trajectory_factory,
) -> None:
    source = trajectory_factory("a")
    with np.load(source, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    arrays["diameters"] = np.full(4, 0.95)
    bad = tmp_path / "diameter.npz"
    np.savez(bad, **arrays)

    with pytest.raises(ValueError, match="mean particle diameter"):
        load_trajectory(bad, CASES["a"])


def test_rejects_non_phase_zero_grid(
    tmp_path,
    trajectory_factory,
) -> None:
    source = trajectory_factory("a")
    with np.load(source, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    arrays["drive_phase"] = arrays["drive_phase"] + 0.01
    bad = tmp_path / "phase.npz"
    np.savez(bad, **arrays)

    with pytest.raises(ValueError, match="phase-zero"):
        load_trajectory(bad, CASES["a"])
