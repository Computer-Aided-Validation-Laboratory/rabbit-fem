# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Unit tests for the serial/MPI build variant handling.

The default ``rabbit-fem`` wheel is the serial/SMP build; ``rabbit-fem-mpi``
is the opt-in multi-rank build. The staged ``variant.txt`` marker tells the
runtime which binary it wraps so preconditioner defaults adapt and
multi-rank misuse of the serial binary fails loudly instead of silently
computing independent serial solves.
"""

from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from rabbit import cli
from rabbit.sims import simulations

import build.common as build_common


def _write_marker(tmp_path: Path, text: str) -> Path:
    """Write a fake variant marker and point the CLI at it."""
    marker = tmp_path / "variant.txt"
    marker.write_text(text, encoding="utf-8")
    return marker


def test_is_mpi_binary_reads_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The staged marker decides, tolerating case and whitespace."""
    marker = _write_marker(tmp_path, "mpi\n")
    monkeypatch.setattr(cli, "_variant_marker_path", lambda: marker)
    assert cli.is_mpi_binary() is True

    marker.write_text("  Serial\n", encoding="utf-8")
    assert cli.is_mpi_binary() is False


def test_is_mpi_binary_missing_marker_falls_back_to_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-marker wheels predate serial builds (except always-serial Win)."""
    monkeypatch.setattr(
        cli, "_variant_marker_path", lambda: tmp_path / "absent.txt"
    )
    monkeypatch.setattr(sys, "platform", "linux")
    assert cli.is_mpi_binary() is True
    monkeypatch.setattr(sys, "platform", "win32")
    assert cli.is_mpi_binary() is False


@pytest.mark.parametrize(
    ("env_vars", "expected"),
    [
        ({}, 1),
        ({"OMPI_COMM_WORLD_SIZE": "1"}, 1),
        ({"OMPI_COMM_WORLD_SIZE": "4"}, 4),
        ({"PMI_SIZE": "3"}, 3),
        ({"OMPI_COMM_WORLD_SIZE": "bogus"}, 1),
    ],
)
def test_mpi_launch_size(
    monkeypatch: pytest.MonkeyPatch,
    env_vars: dict[str, str],
    expected: int,
) -> None:
    """Rank count comes from launcher env vars, defaulting to serial."""
    for key in ("OMPI_COMM_WORLD_SIZE", "PMI_SIZE"):
        monkeypatch.delenv(key, raising=False)
    for key, val in env_vars.items():
        monkeypatch.setenv(key, val)
    assert cli.mpi_launch_size() == expected


def test_format_cli_args_serial_falls_back_to_ilu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Serial builds get ILU since their PETSc has no Hypre."""
    monkeypatch.setattr(cli, "is_mpi_binary", lambda: False)
    assert cli.format_cli_args(["sim.i"]) == [
        "-i",
        "sim.i",
        "-pc_type",
        "ilu",
    ]


def test_format_cli_args_mpi_keeps_input_hypre(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MPI builds keep the .i file's Hypre preconditioner untouched."""
    monkeypatch.setattr(cli, "is_mpi_binary", lambda: True)
    assert cli.format_cli_args(["sim.i"]) == ["-i", "sim.i"]


def test_format_cli_args_explicit_pc_type_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit -pc_type is never overridden on serial builds."""
    monkeypatch.setattr(cli, "is_mpi_binary", lambda: False)
    args = cli.format_cli_args(["-i", "sim.i", "-pc_type", "jacobi"])
    assert args.count("-pc_type") == 1
    assert "jacobi" in args


def test_format_cli_args_info_flags_skip_ilu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Informational flags must not gain solver arguments."""
    monkeypatch.setattr(cli, "is_mpi_binary", lambda: False)
    assert cli.format_cli_args(["--version"]) == ["--version"]


def test_cli_main_refuses_multirank_serial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Serial CLI under mpirun -n>1 must fail loudly, not silently."""
    fake_bin = tmp_path / "rabbit"
    fake_bin.write_bytes(b"fake")
    fake_bin.chmod(0o755)
    monkeypatch.setattr(cli, "get_binary_path", lambda: fake_bin)
    monkeypatch.setattr(cli, "is_mpi_binary", lambda: False)
    monkeypatch.setenv("OMPI_COMM_WORLD_SIZE", "4")
    monkeypatch.setattr(sys, "argv", ["rabbit", "sim.i"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


def _fake_process() -> subprocess.CompletedProcess[str]:
    """Completed process stand-in so run_rabbit never executes."""
    return subprocess.CompletedProcess(args=[], returncode=0)


def test_run_rabbit_refuses_multirank_serial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Library entry point guards like the CLI does."""
    fake_bin = tmp_path / "rabbit"
    fake_bin.write_bytes(b"fake")
    fake_bin.chmod(0o755)
    monkeypatch.setattr(cli, "get_binary_path", lambda: fake_bin)
    monkeypatch.setattr(cli, "is_mpi_binary", lambda: False)
    monkeypatch.setenv("OMPI_COMM_WORLD_SIZE", "2")
    with pytest.raises(RuntimeError, match="rabbit-fem-mpi"):
        simulations.run_rabbit("sim.i", cwd=tmp_path)


def test_run_rabbit_serial_injects_ilu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Serial run_rabbit adds ILU; MPI leaves the command alone."""
    fake_bin = tmp_path / "rabbit"
    fake_bin.write_bytes(b"fake")
    fake_bin.chmod(0o755)
    monkeypatch.setattr(cli, "get_binary_path", lambda: fake_bin)
    monkeypatch.delenv("OMPI_COMM_WORLD_SIZE", raising=False)
    monkeypatch.delenv("PMI_SIZE", raising=False)

    seen: list[list[str]] = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kwargs: seen.append(cmd) or _fake_process(),
    )
    monkeypatch.setattr(cli, "is_mpi_binary", lambda: False)
    simulations.run_rabbit("sim.i", cwd=tmp_path)
    assert "-pc_type" in seen[0] and "ilu" in seen[0]

    seen.clear()
    monkeypatch.setattr(cli, "is_mpi_binary", lambda: True)
    simulations.run_rabbit("sim.i", cwd=tmp_path)
    assert "-pc_type" not in seen[0]


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [(None, False), ("0", False), ("1", True), ("yes", False)],
)
def test_is_mpi_build_reads_env(
    monkeypatch: pytest.MonkeyPatch, env_value: str | None, expected: bool
) -> None:
    """Only RABBIT_MPI=1 selects the MPI variant; default is serial."""
    if env_value is None:
        monkeypatch.delenv("RABBIT_MPI", raising=False)
    else:
        monkeypatch.setenv("RABBIT_MPI", env_value)
    assert build_common.is_mpi_build() is expected


def test_ensure_serial_mpi_fallback_appends_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The MooseConfig.h fallback is applied exactly once, serial only."""
    monkeypatch.setenv("RABBIT_MPI", "0")
    cfg = tmp_path / "moose" / "framework" / "include" / "base"
    cfg.mkdir(parents=True)
    header = cfg / "MooseConfig.h"
    header.write_text("// generated\n", encoding="utf-8")
    build_common.ensure_serial_mpi_fallback(tmp_path / "moose")
    first = header.read_text(encoding="utf-8")
    assert "typedef int MPI_Comm;" in first
    build_common.ensure_serial_mpi_fallback(tmp_path / "moose")
    assert header.read_text(encoding="utf-8") == first


def test_ensure_serial_mpi_fallback_skips_mpi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MPI builds must never see the fallback typedef."""
    monkeypatch.setenv("RABBIT_MPI", "1")
    cfg = tmp_path / "moose" / "framework" / "include" / "base"
    cfg.mkdir(parents=True)
    header = cfg / "MooseConfig.h"
    header.write_text("// generated\n", encoding="utf-8")
    build_common.ensure_serial_mpi_fallback(tmp_path / "moose")
    assert header.read_text(encoding="utf-8") == "// generated\n"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="serial MOOSE patches are POSIX-consumed; Windows patching "
    "is owned by install_dependencies_windows.ps1",
)
def test_apply_serial_patches_idempotent(tmp_path: Path) -> None:
    """Patches apply to pristine sources and tolerate re-application."""
    import shutil

    if shutil.which("patch") is None:
        pytest.skip("patch utility not available")
    moose_dir = tmp_path / "moose"
    target = moose_dir / "framework" / "src" / "utils"
    target.mkdir(parents=True)
    (target / "MemoryUtils.C").write_text(
        '#include <unistd.h>\n#include <mpi.h>\n', encoding="utf-8"
    )
    repo_dir = tmp_path / "repo"
    patch_dir = repo_dir / "patches" / "serial"
    patch_dir.mkdir(parents=True)
    (patch_dir / "moose.patch").write_text(
        "diff --git a/framework/src/utils/MemoryUtils.C "
        "b/framework/src/utils/MemoryUtils.C\n"
        "--- a/framework/src/utils/MemoryUtils.C\n"
        "+++ b/framework/src/utils/MemoryUtils.C\n"
        "@@ -1,2 +1,4 @@\n"
        " #include <unistd.h>\n"
        "+#ifdef LIBMESH_HAVE_MPI\n"
        " #include <mpi.h>\n"
        "+#endif\n",
        encoding="utf-8",
    )
    build_common.apply_serial_patches(moose_dir, repo_dir)
    patched = (target / "MemoryUtils.C").read_text(encoding="utf-8")
    assert "#ifdef LIBMESH_HAVE_MPI" in patched
    build_common.apply_serial_patches(moose_dir, repo_dir)
    assert (target / "MemoryUtils.C").read_text(
        encoding="utf-8"
    ) == patched
