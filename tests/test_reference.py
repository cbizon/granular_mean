from __future__ import annotations

import hashlib
import zipfile

from brunner.reference import validate_reference_manifest

from granular_mean.reference import materialize_reference


def test_materializes_checksum_verified_reference(
    tmp_path,
    collection_factory,
) -> None:
    source_manifest = collection_factory(
        "generated",
        language="updated-c",
    )
    archive = tmp_path / "reference.zip"
    with zipfile.ZipFile(
        archive,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as bundle:
        for path in source_manifest.parent.rglob("*"):
            if path.is_file():
                bundle.write(
                    path,
                    "generated/"
                    + path.relative_to(source_manifest.parent).as_posix(),
                )
    expected_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
    reference_root = tmp_path / "reference"

    result = materialize_reference(
        archive,
        reference_root,
        expected_sha256=expected_sha256,
    )

    assert result["archive_sha256"] == expected_sha256
    assert (reference_root / "generated/manifest.json").is_file()
    validate_reference_manifest(
        reference_root,
        reference_root / "manifest.json",
    )
