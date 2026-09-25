# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Unit tests for the macOS build orchestration.

Regression protection for the macOS CI failure where libMesh's bundled
NetGen sources do not compile against newer Homebrew LLVM libc++ paired
with the Xcode SDK (SDK math.h isnan/isinf/signbit function-like macros
break <complex> parsing in nglib's gzstream.cpp). Rabbit never uses
NetGen, so the macOS libMesh build disables it via the documented
libMesh configure option.
"""

from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build.darwin as darwin


def _run_build_libmesh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[list[str]]:
    """Run darwin.build_libmesh with all side effects mocked out."""
    commands: list[list[str]] = []

    def fake_run(
        cmd: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(
        darwin, "ensure_moose_repo", lambda *args: None
    )
    monkeypatch.setattr(
        darwin, "ensure_moose_submodules", lambda *args: None
    )
    monkeypatch.setattr(darwin.subprocess, "run", fake_run)

    repo_dir = tmp_path / "repo"
    moose_dir = tmp_path / "moose"
    repo_dir.mkdir(exist_ok=True)
    moose_dir.mkdir(exist_ok=True)
    darwin.build_libmesh(
        repo_dir, moose_dir, Path("zigcc"), Path("zigcxx")
    )
    return commands


def test_libmesh_disables_netgen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The macOS libMesh configure must skip the NetGen contrib package."""
    commands = _run_build_libmesh(tmp_path, monkeypatch)
    assert len(commands) == 1
    assert "--disable-netgen" in commands[0]
    assert "--with-mpi" in commands[0]


def test_libmesh_skipped_when_already_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A completed libMesh install must not trigger any build command."""
    commands = _run_build_libmesh(tmp_path, monkeypatch)
    assert len(commands) == 1
    lib_dir = tmp_path / "moose" / "libmesh" / "installed" / "lib"
    lib_dir.mkdir(parents=True)
    (lib_dir / "libmesh_opt.a").write_bytes(b"fake")

    commands2 = _run_build_libmesh(tmp_path, monkeypatch)
    assert commands2 == []
