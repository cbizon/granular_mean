from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "provision-sterling-reference.sh"
MANIFEST_DIGEST = "4daf66508f3f468c39485d53ef371389c049bd27fc9286d2724a656987d51ab6"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _run_provisioner(
    tmp_path: Path,
    *,
    context: str = "bizon@sterling",
    upload_pod_exists: bool = False,
    validation_status: int = 0,
    recorded_digest: str = MANIFEST_DIGEST,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log_path = tmp_path / "kubectl.log"
    reference_dir = tmp_path / "reference"
    reference_dir.mkdir()
    (reference_dir / "manifest.json").write_text("{}\n")

    _write_executable(
        fake_bin / "shasum",
        f"""#!/bin/sh
printf '%s  %s\\n' '{MANIFEST_DIGEST}' "$3"
""",
    )
    _write_executable(
        fake_bin / "kubectl",
        """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_KUBECTL_LOG"

if [ "$*" = "config current-context" ]; then
    printf '%s\\n' "$FAKE_CONTEXT"
    exit 0
fi

case "$*" in
    "get pod granular-mean-reference-upload "*)
        if [ "$FAKE_UPLOAD_POD_EXISTS" = "true" ]; then
            printf '%s\\n' "pod/granular-mean-reference-upload"
            exit 0
        fi
        exit 1
        ;;
    *"granular-reference-validate"*)
        exit "$FAKE_VALIDATION_STATUS"
        ;;
    "get pvc granular-mean-reference-v1 "*)
        printf '%s' "$FAKE_MANIFEST_DIGEST"
        exit 0
        ;;
esac

exit 0
""",
    )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "FAKE_CONTEXT": context,
            "FAKE_KUBECTL_LOG": str(log_path),
            "FAKE_MANIFEST_DIGEST": recorded_digest,
            "FAKE_UPLOAD_POD_EXISTS": str(upload_pod_exists).lower(),
            "FAKE_VALIDATION_STATUS": str(validation_status),
            "GRANULAR_MEAN_REFERENCE_DIR": str(reference_dir),
        }
    )
    result = subprocess.run(
        [str(SCRIPT)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    commands = log_path.read_text().splitlines() if log_path.exists() else []
    return result, commands


def _command_index(commands: list[str], fragment: str) -> int:
    return next(
        index
        for index, command in enumerate(commands)
        if fragment in command
    )


def test_provisioner_uploads_validates_annotates_and_cleans_up(
    tmp_path: Path,
) -> None:
    result, commands = _run_provisioner(tmp_path)

    assert result.returncode == 0, result.stderr
    assert f"Reference provisioned and validated: {MANIFEST_DIGEST}" in (
        result.stdout
    )
    assert _command_index(
        commands,
        "apply -n bizon -f "
        f"{ROOT}/deploy/sterling-reference-network-policy.yaml",
    ) < _command_index(
        commands,
        "apply -n bizon -f "
        f"{ROOT}/deploy/sterling-reference-upload.yaml",
    )
    assert _command_index(
        commands,
        "find /reference -mindepth 1",
    ) < _command_index(commands, "cp -n bizon")
    assert _command_index(
        commands,
        "dev.brunner/reference-manifest-sha256- --overwrite",
    ) < _command_index(
        commands,
        "find /reference -mindepth 1",
    )
    assert _command_index(
        commands,
        "granular-reference-validate --reference-root /reference",
    ) < _command_index(
        commands,
        f"dev.brunner/reference-manifest-sha256={MANIFEST_DIGEST}",
    )
    assert _command_index(
        commands,
        "annotate pvc granular-mean-reference-v1",
    ) < _command_index(
        commands,
        "delete pod granular-mean-reference-upload",
    )
    assert _command_index(
        commands,
        "delete pod granular-mean-reference-upload",
    ) < _command_index(
        commands,
        "delete -n bizon -f "
        f"{ROOT}/deploy/sterling-reference-network-policy.yaml",
    )


def test_provisioner_cleans_up_without_annotating_after_validation_failure(
    tmp_path: Path,
) -> None:
    result, commands = _run_provisioner(tmp_path, validation_status=42)

    assert result.returncode == 42
    assert not any(
        f"dev.brunner/reference-manifest-sha256={MANIFEST_DIGEST}" in command
        for command in commands
    )
    assert any(
        "delete pod granular-mean-reference-upload" in command
        for command in commands
    )
    assert any(
        "sterling-reference-network-policy.yaml" in command
        and command.startswith("delete ")
        for command in commands
    )


def test_provisioner_rejects_the_wrong_kubernetes_context(
    tmp_path: Path,
) -> None:
    result, commands = _run_provisioner(tmp_path, context="other@cluster")

    assert result.returncode == 1
    assert "expected 'bizon@sterling'" in result.stderr
    assert commands == ["config current-context"]


def test_provisioner_removes_an_annotation_that_cannot_be_verified(
    tmp_path: Path,
) -> None:
    result, commands = _run_provisioner(
        tmp_path,
        recorded_digest="incorrect",
    )

    assert result.returncode == 1
    assert "PVC annotation verification failed" in result.stderr
    assert sum(
        "dev.brunner/reference-manifest-sha256- --overwrite" in command
        for command in commands
    ) == 2
    assert "Reference provisioned and validated" not in result.stdout


def test_provisioner_rejects_an_existing_upload_pod(
    tmp_path: Path,
) -> None:
    result, commands = _run_provisioner(
        tmp_path,
        upload_pod_exists=True,
    )

    assert result.returncode == 1
    assert "upload pod granular-mean-reference-upload already exists" in (
        result.stderr
    )
    assert not any(command.startswith("apply ") for command in commands)
