from __future__ import annotations

import argparse
import os
from pathlib import Path

from granular_mean.collection import validate_reference_collection


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="granular-reference-validate"
    )
    parser.add_argument(
        "--reference-root",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--load-trajectories",
        action="store_true",
    )
    arguments = parser.parse_args()
    root = arguments.reference_root
    if root is None:
        value = os.environ.get("BRUNNER_REFERENCE_ROOT")
        if not value:
            raise RuntimeError(
                "set BRUNNER_REFERENCE_ROOT or pass --reference-root"
            )
        root = Path(value)
    validate_reference_collection(
        root.resolve(),
        load_trajectories=arguments.load_trajectories,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
