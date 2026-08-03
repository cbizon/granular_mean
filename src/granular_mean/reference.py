from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from brunner.contract import load_output_contract
from brunner.reference import build_reference_manifest

from granular_mean.collection import validate_reference_collection


ROOT = Path(__file__).resolve().parents[2]
REFERENCE_ARCHIVE_NAME = "granular-benchmark-reference-v1.zip"
REFERENCE_ARCHIVE_SHA256 = (
    "eb4c942abedb100519a58e39867dd2ea0ee148090df82d5dc12fe753ba7c5d09"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member(info: zipfile.ZipInfo) -> PurePosixPath:
    member = PurePosixPath(info.filename)
    if (
        member.is_absolute()
        or ".." in member.parts
        or not member.parts
        or member.parts[0] != "generated"
    ):
        raise ValueError(
            f"unsafe reference archive member: {info.filename!r}"
        )
    file_type = (info.external_attr >> 16) & 0o170000
    if file_type == stat.S_IFLNK:
        raise ValueError(
            f"reference archive contains a symlink: {info.filename!r}"
        )
    return member


def _extract_archive(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if not members:
            raise ValueError("reference archive is empty")
        for info in members:
            member = _safe_member(info)
            output = destination.joinpath(*member.parts)
            if info.is_dir():
                output.mkdir(parents=True, exist_ok=True)
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, output.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)


def materialize_reference(
    archive: Path,
    reference_root: Path,
    *,
    expected_sha256: str = REFERENCE_ARCHIVE_SHA256,
    force: bool = False,
    load_trajectories: bool = False,
    build_manifest: bool = True,
) -> dict[str, object]:
    archive = archive.expanduser().resolve()
    reference_root = reference_root.expanduser().resolve()
    if not archive.is_file():
        raise FileNotFoundError(archive)
    observed_sha256 = sha256_file(archive)
    if observed_sha256 != expected_sha256:
        raise ValueError(
            "reference archive checksum mismatch: "
            f"{observed_sha256} != {expected_sha256}"
        )

    reference_root.mkdir(parents=True, exist_ok=True)
    target = reference_root / "generated"
    if target.exists() and not force:
        raise FileExistsError(
            f"reference already exists: {target}; pass --force to replace it"
        )

    with tempfile.TemporaryDirectory(
        prefix=".granular-reference-",
        dir=reference_root.parent,
    ) as temporary:
        temporary_root = Path(temporary)
        _extract_archive(archive, temporary_root)
        validate_reference_collection(
            temporary_root,
            load_trajectories=load_trajectories,
        )
        extracted = temporary_root / "generated"
        if target.exists():
            shutil.rmtree(target)
        extracted.replace(target)

    manifest = None
    if build_manifest:
        contract = load_output_contract(
            ROOT / "output-contract.json",
            expected_benchmark_id="granular-figure1",
        )
        manifest = build_reference_manifest(
            reference_root,
            reference_root / "manifest.json",
            metadata={
                "benchmark_id": "granular-figure1",
                "benchmark_version": "2.0.0",
                "contract_sha256": contract.sha256,
                "source_archive": archive.name,
                "source_archive_sha256": observed_sha256,
            },
        )
    return {
        "archive": str(archive),
        "archive_sha256": observed_sha256,
        "reference_root": str(reference_root),
        "manifest_sha256": (
            manifest.get("sha256")
            if manifest is not None
            else None
        ),
    }


def _default_archive() -> Path:
    configured = os.environ.get("GRANULAR_MEAN_REFERENCE_ARCHIVE")
    if configured:
        return Path(configured)
    sibling = (
        ROOT.parent
        / "granular_benchmark"
        / "artifacts"
        / REFERENCE_ARCHIVE_NAME
    )
    if sibling.is_file():
        return sibling
    raise RuntimeError(
        "pass --archive or set GRANULAR_MEAN_REFERENCE_ARCHIVE"
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="granular-reference")
    parser.add_argument("--archive", type=Path)
    parser.add_argument(
        "--reference-root",
        type=Path,
        default=ROOT / "reference",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--load-trajectories",
        action="store_true",
    )
    arguments = parser.parse_args()
    result = materialize_reference(
        arguments.archive or _default_archive(),
        arguments.reference_root,
        force=arguments.force,
        load_trajectories=arguments.load_trajectories,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
