from __future__ import annotations

import numpy as np

from granular_mean.alignment import (
    best_cycle_shift,
    shift_profile_by_cycles,
)


def test_alignment_uses_whole_drive_cycles() -> None:
    reference = np.repeat([0.0, 1.0, 0.0, 1.0], 32)
    reference = np.concatenate((reference, reference[:1]))
    candidate = shift_profile_by_cycles(reference, -1)

    shift, error = best_cycle_shift(
        {"signal": reference},
        {"signal": candidate},
        temporal_period=2,
    )

    assert shift == 1
    assert error == 0.0
